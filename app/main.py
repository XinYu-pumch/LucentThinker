import asyncio
import json
import hashlib
import re
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request, Query
from typing import Literal
from fastapi.responses import FileResponse, StreamingResponse, Response, JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from . import config, store, settings_store
from .agent import research, history_context
from .provider import ChatModel, ProviderError

TASKS = {}

def task_finished(rid, task):
    TASKS.pop(rid, None)
    # Cancellation before the coroutine starts, or setup failures before its
    # try/finally, must also close the record and freeze its end time.
    cancelled = task.cancelled()
    error = None if cancelled else task.exception()
    if not cancelled and error is None: return
    run = store.get_run(rid)
    if run and run['status'] == 'running':
        text = '研究已停止。' if cancelled else '研究初始化失败（'+type(error).__name__+'）。'
        store.update(rid, status='cancelled' if cancelled else 'failed', error=text)
        store.event(rid, 'cancelled' if cancelled else 'error', {'text': text})

@asynccontextmanager
async def lifespan(app):
    store.init()
    settings_store.ensure()
    yield
    tasks = list(TASKS.values())
    for task in tasks: task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)

app = FastAPI(title='LucentThinker', lifespan=lifespan, docs_url=None, redoc_url=None)
from .settings_api import router as settings_router
app.include_router(settings_router)

@app.exception_handler(ValueError)
async def bad_value(request, exc):
    return JSONResponse({'detail':config.redact(str(exc))}, status_code=422)

@app.middleware('http')
async def local_only(request: Request, call_next):
    host = request.url.hostname
    if host not in ('127.0.0.1', 'localhost', '::1', 'testserver'):
        return Response('Local access only', status_code=403)
    origin = request.headers.get('origin')
    if origin and origin != str(request.base_url).rstrip('/'):
        return Response('Cross-origin request rejected', status_code=403)
    if request.headers.get('sec-fetch-site') == 'cross-site':
        return Response('Cross-site request rejected', status_code=403)
    response = await call_next(request)
    if request.url.path.startswith('/api/settings') or request.url.path in ('/', '/api/config'):
        response.headers['Cache-Control'] = 'no-store'
    elif request.url.path.startswith('/static/'):
        response.headers['Cache-Control'] = 'no-cache'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
    return response

@app.get('/')
def index():
    static = config.ROOT / 'app/static'
    html = (static / 'index.html').read_text()
    def versioned(match):
        digest = hashlib.sha256((static / match[2]).read_bytes()).hexdigest()[:16]
        return match[1] + match[2] + '?v=' + digest + match[3]
    # New HTML must never execute a cached script from a previous release.
    html = re.sub(r'((?:src|href)="/static/)([^"?]+)(")', versioned, html)
    html = html.replace('<head>', '<head><meta name="lucent-base" content="' + config.URL_PREFIX + '">')
    if config.URL_PREFIX:
        html = html.replace('="/static/', '="' + config.URL_PREFIX + '/static/').replace('href="/"', 'href="' + config.URL_PREFIX + '/"')
    return HTMLResponse(html)

@app.get('/api/config')
def settings():
    doc = settings_store.load()
    public = settings_store.public(doc)
    return {'model': doc['profiles'].get(doc['active']['main'],{}).get('display_name','请选择主模型'), 'configured': bool(settings_store.web_key(doc)),
            'settings':public, 'iteration_tiers':config.ITERATION_TIERS,
            'presets': config.PRESETS, 'models': {r: public['profiles'].get(doc['active'][r],{}).get('capabilities',{}) for r in ('main', 'summary')},
            'memory_modes': ['strict', 'followup']}

@app.post('/api/check')
async def check():
    results = {}
    for role in ('main', 'summary'):
        provider = ChatModel(config.model_settings(role), role)
        try:
            data = await provider.models()
            models = [m['id'] for m in data.get('data', [])]
            results[role] = {'ok': provider.settings.model in models, 'models': models}
        except ProviderError as exc:
            results[role] = {'ok': False, 'error': str(exc)}
        finally: await provider.close()
    ok = all(r['ok'] for r in results.values())
    return {'ok': ok, 'roles': results, 'message': '两个模型 ID 均已验证可用' if ok else '部分模型验证失败，请检查服务端配置'}

@app.get('/api/conversations')
def list_conversations(): return store.conversations()

class ProjectName(BaseModel):
    name: str = Field(min_length=1, max_length=120)

@app.get('/api/projects')
def list_projects(): return store.projects()

@app.post('/api/projects')
def create_project(body: ProjectName):
    return {'id': store.new_project(body.name)}

@app.patch('/api/projects/{pid}')
def rename_project(pid: str, body: ProjectName):
    store.rename_project(pid, body.name)
    return {'ok': True}

class ConversationProject(BaseModel):
    project_id: str = Field(default=store.DEFAULT_PROJECT_ID, min_length=1)

@app.post('/api/conversations')
def create_conversation(body: ConversationProject | None = None):
    return {'id': store.new_conversation(body.project_id if body else store.DEFAULT_PROJECT_ID)}

@app.get('/api/conversations/search')
def search_conversations(q: str = Query('', max_length=200),
                         scope: Literal['all', 'title', 'content'] = 'all',
                         limit: int = Query(30, ge=1, le=50), offset: int = Query(0, ge=0)):
    return store.search_conversations(q, scope, limit, offset)

class ConversationBatch(BaseModel):
    ids: list[str] = Field(min_length=1)

class ConversationMove(ConversationBatch):
    project_id: str = Field(min_length=1)

@app.post('/api/conversations/move')
def move_conversations(body: ConversationMove):
    return {'ok': True, 'moved': store.move_conversations(body.ids, body.project_id)}

@app.post('/api/conversations/delete')
def delete_conversations(body: ConversationBatch):
    try:
        cleanup = store.delete_conversations(body.ids)
    except store.ConversationRunningError as exc:
        raise HTTPException(409, str(exc)) from None
    return {'ok': True, 'deleted': len(set(body.ids)), 'storage_cleanup': cleanup}

@app.get('/api/conversations/{cid}')
def conversation(cid: str):
    result = store.get_conversation(cid)
    if not result: raise HTTPException(404, '会话不存在')
    return result

@app.delete('/api/conversations/{cid}')
def delete_conversation(cid: str):
    try:
        cleanup = store.delete(cid, require_stopped=True)
    except store.ConversationRunningError as exc:
        raise HTTPException(409, str(exc)) from None
    if cleanup is None:
        raise HTTPException(404, '会话不存在')
    return {'ok': True, 'storage_cleanup': cleanup}

class ConversationTitle(BaseModel):
    title: str = Field(min_length=1)

@app.patch('/api/conversations/{cid}')
def rename_conversation(cid: str, payload: ConversationTitle):
    title = payload.title.strip()
    if not title: raise HTTPException(422, '名称不能为空')
    if not store.rename_conversation(cid, title): raise HTTPException(404, '会话不存在')
    return {'ok': True, 'title': title}

class Prompt(BaseModel):
    question: str = Field(min_length=1)
    mode: str | None = None
    memory_mode: str | None = None
    max_iterations: int | None = Field(default=None,ge=1)
    keep_tool_result: int | None = None
    context_compress_limit: int | None = None
    main_profile: str | None = None
    summary_profile: str | None = None
    language: Literal['zh', 'en'] | None = None

@app.post('/api/conversations/{cid}/runs')
async def start(cid: str, prompt: Prompt):
    current = conversation(cid)
    if not prompt.question.strip(): raise HTTPException(422, '请输入研究问题')
    doc = settings_store.load()
    defaults = doc['research']
    prompt.mode = prompt.mode or defaults['preset']
    prompt.memory_mode = prompt.memory_mode or defaults['memory_mode']
    if prompt.mode not in config.PRESETS or prompt.memory_mode not in ('strict', 'followup'): raise HTTPException(422, '未知上下文预设或历史模式')
    if any(r['status'] == 'running' for r in current['runs']): raise HTTPException(409, '当前会话已有研究正在进行')
    for role in ('main','summary'):
        selected = getattr(prompt,role+'_profile')
        if selected is not None: doc['active'][role]=selected
        if doc['active'][role] not in doc['profiles']: raise HTTPException(422,'请在输入区选择有效的主模型和摘要模型')
    models = {r: config.model_settings(r,doc) for r in ('main','summary')}
    execution = {k:getattr(prompt,k) if getattr(prompt,k) is not None else defaults[k] for k in ('max_iterations','keep_tool_result','context_compress_limit')}
    if execution['keep_tool_result'] not in (-1,5) or execution['context_compress_limit'] not in (0,5): raise HTTPException(422,'未知上下文或重试策略')
    execution.update(runner='benchmark_retry' if execution['context_compress_limit'] else 'gradio_single', retry_with_summary=not bool(execution['context_compress_limit']))
    web_key = settings_store.web_key(doc)
    snapshot = config.snapshot(prompt.mode,prompt.memory_mode,models,execution,{'base_url':config.BASE_URL,'configured':bool(web_key),'credential_profile':doc['web'].get('credential_profile'),'search_count':defaults['search_count'],'search_path':'/v1/tools/search','fetch_path':'/v1/tools/fetch'})
    selected_research = doc['research_profiles'][doc['active_research_profile']]
    snapshot['research_profile'] = {'id': selected_research['id'], 'name': selected_research['name']}
    if prompt.language is not None:
        from .prompts import apply_language
        apply_language(snapshot, prompt.language)
    memory = history_context(current) if prompt.memory_mode == 'followup' else []
    rid = store.new_run(cid, prompt.question.strip(), prompt.mode, snapshot, memory)
    task = asyncio.create_task(research(rid, models=models, web_api_key=web_key))
    TASKS[rid] = task
    task.add_done_callback(lambda finished: task_finished(rid, finished))
    run = store.get_run(rid)
    return {k:run[k] for k in ('id', 'config_snapshot', 'created', 'started_at', 'finished_at', 'duration_seconds')}

@app.post('/api/runs/{rid}/cancel')
async def cancel(rid: str):
    if not store.get_run(rid): raise HTTPException(404, '研究不存在')
    if rid in TASKS:
        task = TASKS[rid]
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
    return {'ok': True}

@app.get('/api/runs/{rid}/events')
async def events(rid: str, request: Request, after: int = 0):
    if not store.get_run(rid): raise HTTPException(404, '研究不存在')
    try: cursor = max(after, int(request.headers.get('last-event-id', '0')))
    except ValueError: cursor = after
    async def stream():
        nonlocal cursor
        while True:
            if await request.is_disconnected(): return
            for item in store.events(rid, cursor):
                cursor = item['id']
                yield f"id: {cursor}\ndata: {json.dumps(item, ensure_ascii=False)}\n\n"
            run = store.get_run(rid)
            if not run or run['status'] != 'running':
                yield 'event: closed\ndata: {}\n\n'
                return
            yield ': heartbeat\n\n'
            await asyncio.sleep(0.7)
    return StreamingResponse(stream(), media_type='text/event-stream', headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})

@app.get('/api/conversations/{cid}/export')
def export(cid: str):
    current = conversation(cid)
    chunks = ['# ' + current['title'], 'Generated by LucentThinker']
    for run in current['runs']:
        # The saved answer already owns its reference list. Discovered sources
        # include uncited search leads and belong in the source/debug views.
        chunks += ['## ' + run['question'], run['answer'] or run['error'] or '研究尚未完成']
    return Response('\n\n'.join(chunks), media_type='text/markdown', headers={'Content-Disposition': 'attachment; filename="LucentThinker.md"'})

@app.get('/api/runs/{rid}/export')
def export_answer(rid: str):
    run = store.get_run(rid)
    if not run: raise HTTPException(404, '研究不存在')
    if run['status'] == 'running': raise HTTPException(409, '请等待本次回答结束，或先停止生成后再导出')
    if not run['answer'].strip(): raise HTTPException(409, '本次研究没有可导出的回答')
    suffix = '' if run['status'] == 'completed' else '-partial'
    # The answer already contains its own citations. Export it verbatim, without
    # the question, other turns, debug events, or uncited discovered sources.
    return Response(run['answer'], media_type='text/markdown', headers={
        'Content-Disposition': f'attachment; filename="LucentThinker-{run["id"]}{suffix}.md"',
        'Cache-Control': 'no-store'})

@app.get('/api/runs/{rid}/details')
def details(rid: str, include_history: bool = True, include_events: bool = True):
    run = store.get_run(rid)
    if not run: raise HTTPException(404, '研究不存在')
    return {'run': run, 'history': store.messages(rid) if include_history else None, 'requests': store.requests(rid), 'events': store.events(rid) if include_events else None}

@app.get('/api/runs/{rid}/requests/{request_id}')
def request_detail(rid: str, request_id: int):
    rows = store.requests(rid, request_id)
    if not rows: raise HTTPException(404, '请求不存在')
    result = rows[0]
    if result['status'] not in ('completed','incomplete'): result['stream_chunks'] = store.chunks(request_id)
    return result

@app.get('/api/runs/{rid}/history')
def history(rid: str):
    if not store.get_run(rid): raise HTTPException(404,'研究不存在')
    return store.messages(rid)

@app.get('/api/runs/{rid}/search-responses')
def raw_search_responses(rid: str):
    if not store.get_run(rid): raise HTTPException(404, '研究不存在')
    return store.search_responses(rid)

app.mount('/static' , StaticFiles(directory=config.ROOT / 'app/static'), name='static')
