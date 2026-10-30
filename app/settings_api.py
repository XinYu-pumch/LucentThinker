import time
from typing import Literal
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from . import config, settings_store as settings
from .provider import ChatModel, DeepSeek, ProviderError

router = APIRouter(prefix='/api/settings')

class ProfileDraft(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: str | None = None
    name: str
    base_url: str
    api_key: str | None = None
    model: str = ''
    provider: str = 'openai'
    thinking: Literal['enabled','disabled'] | None = None
    reasoning_effort: str | None = None
    thinking_config: dict | None = None
    go_reasoning: str | None = None
    reasoning_budget: int | None = Field(default=None, strict=True)
    temperature: float | None = None
    top_p: float | None = None
    concurrency: int = Field(default=1, ge=1, strict=True)
    activate_role: Literal['main','summary'] | None = None

class WebSettings(BaseModel):
    api_key: str | None = None
    credential_profile: str | None = None
    search_count: int = Field(default=10, ge=1, strict=True)

class ModelSelection(BaseModel):
    model_config = ConfigDict(extra='forbid')
    main: str
    summary: str

class ResearchSettings(BaseModel):
    model_config = ConfigDict(extra='forbid')
    iteration_tier: Literal['quick','standard','deep','custom'] = 'deep'
    max_iterations: int = Field(default=200, ge=1, strict=True)
    keep_tool_result: Literal[-1,5] = -1
    context_compress_limit: Literal[0,5] = 5
    memory_mode: Literal['strict','followup'] = 'strict'
    preset: Literal['demo','keep5_max200'] = 'demo'
    search_count: int = Field(default=20, ge=1, strict=True)

class ResearchProfileDraft(ResearchSettings):
    name: str

class ResearchProfileName(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str

@router.get('')
def read(): return settings.public()

@router.post('/profiles')
def save(body: ProfileDraft):
    ident = settings.save_profile(body.model_dump(exclude_unset=True),body.activate_role)
    return {'id':ident,'settings':settings.public()}

@router.delete('/profiles/{ident}')
def delete(ident: str):
    settings.delete_profile(ident)
    return settings.public()

@router.post('/active/{role}/{ident}')
def active(role: str,ident: str):
    settings.activate(role,ident)
    return settings.public()

@router.put('/active')
def select_models(body: ModelSelection):
    settings.select_models(body.main, body.summary)
    return settings.public()

@router.post('/profiles/{ident}/reveal')
def reveal(ident: str):
    profile = settings.load()['profiles'].get(ident)
    if not profile: raise HTTPException(404,'配置不存在')
    return JSONResponse({'api_key':profile['api_key']},headers={'Cache-Control':'no-store'})

@router.post('/models')
async def discover(body: ProfileDraft):
    profile = settings.draft(body.model_dump())
    client = ChatModel(settings.to_model(profile),'main')
    try:
        raw = await client.models()
        models = [m for m in raw.get('data',[]) if isinstance(m,dict) and isinstance(m.get('id'),str)]
        settings.cache_models(profile,models)
        return {'ok':True,'models':config.redact(models),'unmapped_models':raw.get('unmapped_models',[])}
    except ProviderError as exc: return {'ok':False,'message':str(exc),'models':[]}
    finally: await client.close()

async def run_test(body, tools=False):
    profile = settings.draft(body.model_dump())
    return await run_profile_test(profile, tools)

async def run_profile_test(profile, tools=False, probe=False):
    from .llm_diagnostics import Capture, negative_probe
    capture = Capture()
    client = ChatModel(settings.to_model(profile),'main', observer=capture)
    started = time.monotonic()
    schema = [{'type':'function','function':{'name':'connection_echo','description':'Echo the input to verify native tool calling.','parameters':{'type':'object','properties':{'text':{'type':'string'}},'required':['text'],'additionalProperties':False}}}] if tools else None
    prompt = 'A box has 17 red and 23 blue beads. Remove 8 red and add 6 blue. What fraction is red? Return only the final fraction.' if profile.get('thinking_config') or profile.get('provider') != 'openai' else 'hellow'
    messages = [{'role':'user','content':'First call connection_echo with text hellow. After the tool returns, reply with its result in plain text.' if tools else prompt}]
    try:
        response = await client.complete(messages,schema,purpose='connection_test')
        thinking = capture.report(client.settings, response)
        first_body = capture.body
        reply = response.message.get('content') or ''
        calls = response.message.get('tool_calls') or []
        valid_tool = False
        if tools:
            import json
            for c in calls:
                try:
                    valid_tool |= c.get('function',{}).get('name')=='connection_echo' and json.loads(c['function']['arguments']).get('text')=='hellow'
                except (ValueError,KeyError,AttributeError): pass
        ok = valid_tool if tools else bool(reply.strip()) and response.finish_reason!='length'
        round_trip = None
        followup_usage = None
        if tools and valid_tool:
            # Native protocols also need to accept signed continuation and tool results.
            history = [*messages, response.message]
            history += [{'role':'tool','tool_call_id':c['id'],'content':'hellow'} for c in calls]
            follow = await client.complete(history, purpose='connection_test')
            followup_usage = follow.usage
            round_trip = bool((follow.message.get('content') or '').strip()) and not follow.message.get('tool_calls') and follow.finish_reason!='length'
            ok = ok and round_trip
            reply = follow.message.get('content') or reply
        if probe and ok and not tools:
            thinking['probe'] = await negative_probe(client, first_body, messages)
        return config.redact({'ok':ok,'model':response.model,'reply':reply,'tool_calls':calls,'usage':response.usage,
                'thinking': thinking,
                'tool_round_trip':round_trip,
                'followup_usage':followup_usage,
                'elapsed_seconds':round(time.monotonic()-started,2),'message':'工具调用兼容' if tools and ok else ('收到模型回复' if ok else '未获得有效测试响应')})
    except ProviderError as exc: return {'ok':False,'message':str(exc),'elapsed_seconds':round(time.monotonic()-started,2)}
    finally: await client.close()

@router.post('/test')
async def test(body: ProfileDraft): return await run_test(body)

@router.post('/test-tools')
async def test_tools(body: ProfileDraft): return await run_test(body,True)

@router.put('/web')
def save_web(body: WebSettings):
    settings.save_web(body.model_dump(exclude_unset=True))
    return settings.public()

@router.post('/web/reveal')
def reveal_web(independent: bool = False):
    key = settings.load()['web'].get('api_key', '') if independent else settings.web_key()
    return JSONResponse({'api_key': key},headers={'Cache-Control':'no-store'})

@router.post('/web/test/{service}')
async def test_web(service: str, body: WebSettings):
    if service not in ('search','fetch'): raise HTTPException(404,'未知网页服务')
    doc = settings.load()
    if body.credential_profile:
        if body.credential_profile not in doc['profiles']: raise HTTPException(422,'配置不存在')
        if doc['profiles'][body.credential_profile].get('provider') not in ('openai','deepseek'):
            raise HTTPException(422,'网页服务需要 DeepSeek Key，不能复用专用供应商凭据。')
        key = doc['profiles'][body.credential_profile]['api_key']
    else: key = body.api_key if body.api_key is not None else doc['web'].get('api_key','')
    client = DeepSeek(api_key=key)
    try:
        count = body.search_count if 'search_count' in body.model_fields_set else doc['web']['search_count']
        result = await client.search('DeepSeek official','DeepSeek official',count) if service=='search' else await client.fetch('https://api-docs.deepseek.com/')
        ok = bool(result.get('results')) if service=='search' else bool(result.get('content'))
        return {'ok':ok,'message':f'{service} '+('成功' if ok else '没有返回内容'),
                'requested_count':count if service=='search' else None,
                'result_count':len(result.get('results',[])), 'content_chars':len(result.get('content') or '')}
    except ProviderError as exc: return {'ok':False,'message':str(exc)}
    finally: await client.close()

@router.put('/research')
def save_research(body: ResearchSettings):
    settings.save_research(body.model_dump(exclude_unset=True))
    return settings.public()

@router.post('/research-profiles')
def create_research_profile(body: ResearchProfileDraft):
    ident = settings.save_research_profile(body.model_dump(exclude_unset=True))
    return {'id': ident, 'settings': settings.public()}

@router.put('/research-profiles/{ident}')
def update_research_profile(ident: str, body: ResearchSettings):
    settings.save_research_profile(body.model_dump(exclude_unset=True), ident)
    return settings.public()

@router.patch('/research-profiles/{ident}')
def rename_research_profile(ident: str, body: ResearchProfileName):
    settings.rename_research_profile(ident, body.name)
    return settings.public()

@router.post('/research-profiles/{ident}/activate')
def select_research_profile(ident: str):
    settings.activate_research_profile(ident)
    return settings.public()

@router.delete('/research-profiles/{ident}')
def remove_research_profile(ident: str):
    settings.delete_research_profile(ident)
    return settings.public()

class SupplierDraft(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str
    base_url: str = ''
    api_key: str | None = None

class AddedModels(BaseModel):
    model_config = ConfigDict(extra='forbid')
    models: list[str]
    manual: bool = False

class ModelParameters(BaseModel):
    model_config = ConfigDict(extra='forbid')
    concurrency: int = Field(default=1, ge=1, strict=True)
    thinking: Literal['enabled','disabled'] | None = None
    reasoning_effort: str | None = None
    thinking_config: dict | None = None
    go_reasoning: str | None = None
    reasoning_budget: int | None = Field(default=None, strict=True)
    temperature: float | None = None
    top_p: float | None = None

@router.post('/suppliers')
def create_supplier(body: SupplierDraft):
    ident=settings.save_supplier(body.model_dump(exclude_unset=True))
    return {'id':ident,'settings':settings.public()}

@router.put('/suppliers/{ident}')
def update_supplier(ident: str,body: SupplierDraft):
    settings.save_supplier(body.model_dump(exclude_unset=True),ident)
    return settings.public()

@router.delete('/suppliers/{ident}')
def remove_supplier(ident: str):
    settings.delete_supplier(ident)
    return settings.public()

@router.post('/suppliers/{ident}/reveal')
def reveal_supplier(ident: str):
    return JSONResponse({'api_key':settings.supplier(ident).get('api_key','')},headers={'Cache-Control':'no-store'})

@router.post('/suppliers/{ident}/discover')
async def discover_supplier(ident: str):
    profile=settings.supplier_profile(ident)
    client=ChatModel(settings.to_model(profile),'main')
    try:
        raw=await client.models()
        models=settings.cache_supplier_models(ident,profile,raw.get('data',[]))
        present = {m['id'] for m in models}
        missing = [p['model'] for p in settings.load()['profiles'].values() if p['supplier_id'] == ident and p['model'] not in present]
        return {'ok':True,'models':models,'unmapped_models':raw.get('unmapped_models',[]),'saved_missing_models':missing}
    except ProviderError as exc: return {'ok':False,'message':str(exc),'models':[]}
    finally: await client.close()

@router.post('/suppliers/{ident}/models')
def add_models(ident: str,body: AddedModels):
    added=settings.add_supplier_models(ident,body.models,body.manual)
    return {'added':added,'settings':settings.public()}

@router.put('/suppliers/{ident}/models/{pid}')
def update_model(ident: str,pid: str,body: ModelParameters):
    settings.update_supplier_model(ident,pid,body.model_dump(exclude_unset=True))
    return settings.public()

@router.delete('/suppliers/{ident}/models/{pid}')
def remove_model(ident: str,pid: str):
    settings.delete_supplier_model(ident,pid)
    return settings.public()

@router.post('/suppliers/{ident}/models/{pid}/test')
async def test_supplier_model(ident: str,pid: str,body: ModelParameters, tools: bool=False, probe: bool=False):
    profile=settings.supplier_profile(ident,pid,body.model_dump(exclude_unset=True))
    return await run_profile_test(profile,tools,True) if probe else await run_profile_test(profile,tools)
