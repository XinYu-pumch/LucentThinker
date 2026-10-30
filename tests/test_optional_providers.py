import asyncio
import copy
import json
import shutil
from dataclasses import replace
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app import config, settings_store, store
from app.agent import research
from app.llm_providers import registry
from app.provider import ChatModel, ProviderError, DeepSeek

pytestmark = pytest.mark.skipif('opencode_go' not in registry.catalog(), reason='Optional Go module is disabled or removed')

MODELS = {'chat': 'deepseek-v4.1-flash', 'responses': 'grok-4.7',
          'messages': 'claude-haiku-5-5', 'google': 'gemini-4-argon-contributor'}


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(config, 'DATA', tmp_path)
    monkeypatch.setattr(config, 'API_KEY', 'fixture-deepseek')
    monkeypatch.setattr(config, 'SECRETS', set())
    monkeypatch.setattr(store, 'DB', tmp_path / 'research.sqlite3')
    monkeypatch.setattr(settings_store, 'SETTINGS_FILE', tmp_path / 'settings.json')
    monkeypatch.setattr(settings_store, 'DISCOVERED', {})
    store.init()


def model_settings(protocol):
    module = registry.get('opencode_go')
    return config.ModelSettings(model=MODELS[protocol], base_url=module.BASE,
                                api_key='fixture-go-secret', provider='opencode_go',
                                request_attempts=2, retry_delay=0)


def response(protocol, text='', calls=(), length=False, stream=True):
    """Minimal native replies with actual usage and signed continuation state."""
    calls = [{'id': 'call_'+str(i), 'name': name, 'args': args} for i, (name, args) in enumerate(calls)]
    if protocol == 'chat':
        m = {'role': 'assistant', 'content': text, 'reasoning_content': 'PRIVATE'}
        if calls:
            m['tool_calls'] = [{'id': c['id'], 'type': 'function', 'function': {'name': c['name'], 'arguments': json.dumps(c['args'])}} for c in calls]
        usage = {'prompt_tokens': 10, 'completion_tokens': 5, 'total_tokens': 15, 'prompt_cache_hit_tokens': 4, 'prompt_cache_miss_tokens': 6}
        stop = 'length' if length else 'tool_calls' if calls else 'stop'
        full = {'choices': [{'message': m, 'finish_reason': stop}], 'usage': usage}
        delta = copy.deepcopy(m)
        for i, c in enumerate(delta.get('tool_calls', [])): c['index'] = i
        events = [{'choices': [{'index': 0, 'delta': delta, 'finish_reason': stop}]}, {'choices': [], 'usage': usage}]
    elif protocol == 'responses':
        items = [{'type': 'reasoning', 'id': 'rs1', 'summary': [], 'encrypted_content': 'SIGNED_REASONING'}]
        if text:
            items.append({'type': 'message', 'id': 'm1', 'role': 'assistant', 'status': 'completed',
                          'content': [{'type': 'output_text', 'text': text, 'annotations': []}]})
        items += [{'type': 'function_call', 'id': 'fc'+str(i), 'call_id': c['id'], 'name': c['name'], 'arguments': json.dumps(c['args']), 'status': 'completed'} for i, c in enumerate(calls)]
        full = {'object': 'response', 'status': 'incomplete' if length else 'completed',
                'incomplete_details': {'reason': 'max_output_tokens'} if length else None,
                'output': items, 'usage': {'input_tokens': 10, 'output_tokens': 5, 'total_tokens': 15, 'input_tokens_details': {'cached_tokens': 4}}}
        events = [{'type': 'response.output_text.delta', 'delta': text},
                  {'type': 'response.incomplete' if length else 'response.completed', 'response': full}]
    elif protocol == 'messages':
        blocks = [{'type': 'thinking', 'thinking': 'PRIVATE', 'signature': 'SIGNED_THOUGHT'}]
        if text:
            blocks.append({'type': 'text', 'text': text})
        blocks += [{'type': 'tool_use', 'id': c['id'], 'name': c['name'], 'input': c['args']} for c in calls]
        usage = {'input_tokens': 4, 'cache_read_input_tokens': 4, 'cache_creation_input_tokens': 2, 'output_tokens': 5}
        stop = 'max_tokens' if length else 'tool_use' if calls else 'end_turn'
        full = {'type': 'message', 'content': blocks, 'usage': usage, 'stop_reason': stop}
        events = [{'type': 'message_start', 'message': {'usage': {**usage, 'output_tokens': 0}}}]
        for i, b in enumerate(blocks):
            b = copy.deepcopy(b)
            if b['type'] == 'tool_use':
                args = json.dumps(b['input']); b['input'] = {}
                events += [{'type': 'content_block_start', 'index': i, 'content_block': b},
                           {'type': 'content_block_delta', 'index': i, 'delta': {'type': 'input_json_delta', 'partial_json': args[:3]}},
                           {'type': 'content_block_delta', 'index': i, 'delta': {'type': 'input_json_delta', 'partial_json': args[3:]}}]
            else:
                events.append({'type': 'content_block_start', 'index': i, 'content_block': b})
            events.append({'type': 'content_block_stop', 'index': i})
        events += [{'type': 'message_delta', 'delta': {'stop_reason': stop}, 'usage': {'output_tokens': 5}}, {'type': 'message_stop'}]
    else:
        parts = [{'text': 'PRIVATE', 'thought': True, 'thoughtSignature': 'SIGNED_THOUGHT'}]
        if text:
            parts.append({'text': text})
        parts += [{'functionCall': {'name': c['name'], 'args': c['args']}, 'thoughtSignature': 'SIGNED_CALL'} for c in calls]
        full = {'candidates': [{'index': 0, 'content': {'role': 'model', 'parts': parts}, 'finishReason': 'MAX_TOKENS' if length else 'STOP'}],
                'usageMetadata': {'promptTokenCount': 10, 'candidatesTokenCount': 3, 'thoughtsTokenCount': 2, 'totalTokenCount': 15, 'cachedContentTokenCount': 4}}
        events = [full]
    if not stream:
        return httpx.Response(200, json=full)
    return httpx.Response(200, headers={'content-type': 'text/event-stream'},
                         text=''.join('data: '+json.dumps(e)+'\n\n' for e in events)+'data: [DONE]\n\n')


@pytest.mark.parametrize('protocol', MODELS)
@pytest.mark.parametrize('stream', [True, False])
async def test_native_tools_roundtrip_and_usage(protocol, stream):
    observed = []
    def handler(req):
        observed.append(req)
        return response(protocol, 'progress' if len(observed) == 1 else 'done',
                        [('search', {'query': 'x'}), ('search', {'query': 'y'})] if len(observed) == 1 else [], stream=stream)
    client = ChatModel(model_settings(protocol), 'main', client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    history = [{'role': 'system', 'content': 'SYSTEM'}, {'role': 'user', 'content': 'TASK'}]
    tools = [{'type': 'function', 'function': {'name': 'search', 'description': 'find', 'parameters': {'type': 'object', 'properties': {'query': {'type': 'string'}}}}}]
    try:
        out = await client.complete(history, tools)
        assert out.message['content'] == 'progress'
        assert len(out.message['tool_calls']) == 2 and out.finish_reason == 'tool_calls'
        assert out.usage['prompt_tokens'] == 10 and out.usage['completion_tokens'] == 5 and out.usage['total_tokens'] == 15
        history.append(out.message)
        history += [{'role': 'tool', 'tool_call_id': c['id'], 'content': 'RESULT_'+str(i)} for i,c in enumerate(out.message['tool_calls'])]
        final = await client.complete(history, purpose='final')
        assert final.message['content'] == 'done'
        a, b = [json.loads(r.content) for r in observed]
        assert 'RESULT_0' in json.dumps(b) and 'RESULT_1' in json.dumps(b)
        assert 'tools' in a and 'tools' not in b
        assert observed[0].headers['x-opencode-session'] == observed[1].headers['x-opencode-session']
        assert observed[0].headers['user-agent'] == 'LucentThinker/0.1.0'
        assert str(observed[0].url).startswith('https://opencode.ai/inference/go/')
        if protocol == 'messages':
            assert observed[0].headers['anthropic-version'] == '2023-06-01'
            assert a['max_tokens'] == 128000 and 'SIGNED_THOUGHT' in json.dumps(b)
        else:
            assert 'max_tokens' not in a and 'max_output_tokens' not in a
        if protocol == 'responses':
            assert a['store'] is False and 'SIGNED_REASONING' in json.dumps(b)
            assert len([i for i in b['input'] if i.get('type') == 'function_call_output']) == 2
        if protocol == 'google':
            assert 'SIGNED_CALL' in json.dumps(b) and 'functionResponse' in json.dumps(b)
    finally:
        await client.close()


class Web:
    async def search(self, *args):
        return {'results': [{'title': 'Page', 'url': 'https://example.org/page', 'snippet': 'SNIPPET'}]}
    async def fetch(self, url):
        return {'content': 'PAGE_BODY_ONLY', 'title': 'Page'}
    async def close(self): pass


@pytest.mark.parametrize('protocol', MODELS)
async def test_full_research_and_independent_extraction(protocol):
    requests = {'main': [], 'summary': []}
    actions = [[('search', {'query': 'question', 'progress': '查找'})],
               [('scrape_and_extract_info', {'source_id': 1, 'info_to_extract': 'target', 'progress': '核对'})],
               [('finish_research', {'status': 'ready', 'summary': 'done', 'unresolved_questions': []})], []]
    def handler(role):
        def receive(req):
            requests[role].append(req)
            if role == 'summary':
                assert 'MAIN_PRIVATE_TASK' not in req.content.decode()
                assert 'PAGE_BODY_ONLY' in req.content.decode()
                return response(protocol, 'EXTRACTED_FACT')
            index = len(requests[role])-1
            assert 'PAGE_BODY_ONLY' not in req.content.decode()
            if index == 2: assert 'EXTRACTED_FACT' in req.content.decode()
            return response(protocol, 'answer [1]' if index == 3 else '', actions[index])
        return receive
    models = {r: model_settings(protocol) for r in requests}
    clients = {r: ChatModel(models[r], r, client=httpx.AsyncClient(transport=httpx.MockTransport(handler(r)))) for r in requests}
    rid = store.new_run(store.new_conversation(), 'MAIN_PRIVATE_TASK', config_snapshot=config.snapshot(models=models))
    await research(rid, main=clients['main'], summary=clients['summary'], web=Web())
    saved = store.get_run(rid)
    assert saved['status'] == 'completed', saved['error']
    assert 'https://example.org/page' in saved['answer']
    assert saved['usage']['main']['calls'] == 4 and saved['usage']['summary']['calls'] == 1
    headers = [r.headers['x-opencode-session'] for r in requests['main']]
    assert len(set(headers)) == 1 and requests['summary'][0].headers['x-opencode-session'] not in headers
    audits = store.requests(rid)
    detail = store.requests(rid, audits[0]['id'])[0]
    assert detail['request']['wire_request']['protocol'] == protocol
    assert 'fixture-go-secret' not in json.dumps(detail)


async def test_sessions_retry_separate_extractions_and_conversations():
    seen = []
    def handler(req):
        seen.append(req.headers['x-opencode-session'])
        if len(seen) == 1: return httpx.Response(503, json={'error': {'message': 'temporary'}})
        return response('chat', 'ok')
    a = ChatModel(model_settings('chat'), 'summary', client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    b = ChatModel(model_settings('chat'), 'main', client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    try:
        for client in (a, a, b): await client.complete([{'role':'user','content':'hi'}])
        assert seen[0] == seen[1] and len(set(seen)) == 3
    finally:
        await a.close(); await b.close()


@pytest.mark.parametrize('protocol', MODELS)
async def test_truncation_keeps_partial_text(protocol):
    model = ChatModel(model_settings(protocol),'main', client=httpx.AsyncClient(transport=httpx.MockTransport(lambda _: response(protocol, 'PARTIAL', length=True))))
    try:
        result = await model.complete([{'role':'user','content':'hi'}])
        assert result.finish_reason == 'length' and result.message['content'] == 'PARTIAL'
    finally: await model.close()


@pytest.mark.parametrize('protocol', ['responses', 'messages', 'google'])
async def test_broken_native_stream_is_not_success(protocol):
    model = ChatModel(model_settings(protocol),'main',client=httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200,headers={'content-type':'text/event-stream'},text='data: {}\n\n'))))
    try:
        with pytest.raises(ProviderError): await model.complete([{'role':'user','content':'hi'}])
    finally: await model.close()


def test_per_model_parameters_and_rejection():
    module = registry.get('opencode_go')
    for protocol in MODELS:
        cfg = replace(model_settings(protocol), reasoning_effort='high')
        plan = module.prepare(cfg, {'messages':[{'role':'user','content':'hi'}]}, 'fixture-session')
        body = plan['body']
        if protocol == 'chat': assert body['thinking'] == {'type':'enabled'} and body['reasoning_effort']=='high'
        if protocol == 'responses': assert body['reasoning']=={'effort':'high'}
        if protocol == 'messages': assert body['output_config']=={'effort':'high'} and body['thinking']['type']=='adaptive'
        if protocol == 'google': assert body['generationConfig']['thinkingConfig']=={'thinkingLevel':'high','includeThoughts':True}
    with pytest.raises(ValueError): module.prepare(replace(model_settings('google'),reasoning_effort='max'),{'messages':[]},'session')
    with pytest.raises(ValueError): module.prepare(replace(model_settings('chat'),model='unknown'),{'messages':[]},'session')


@pytest.mark.parametrize('protocol,level', [('google', x) for x in ('low', 'medium', 'high')]
                         + [('chat', x) for x in ('low', 'high', 'max')])
@pytest.mark.parametrize('role', ['main', 'summary'])
async def test_go_saved_effort_reaches_native_request(protocol, level, role):
    """UI/API values survive persistence and role selection all the way to HTTP."""
    from app.main import app
    sid = 'builtin_opencode_go'
    settings_store.save_supplier({'api_key': 'fixture-go-secret'}, sid)
    settings_store.cache_supplier_models(sid, settings_store.supplier_profile(sid), [{'id': MODELS[protocol]}])
    pid, = settings_store.add_supplier_models(sid, [MODELS[protocol]])
    with TestClient(app) as api:
        values = {'reasoning_effort': level}
        if protocol == 'chat': values['thinking'] = 'enabled'
        result = api.put(f'/api/settings/suppliers/{sid}/models/{pid}', json=values)
        assert result.status_code == 200, result.text
        assert api.put('/api/settings/active', json={'main': pid, 'summary': pid}).status_code == 200
    cfg = config.model_settings(role)
    assert cfg.reasoning_effort == level
    seen = []
    def handler(req):
        body = json.loads(req.content); seen.append(body)
        if protocol == 'google':
            assert body['generationConfig']['thinkingConfig'] == {'thinkingLevel': level, 'includeThoughts': True}
            assert 'reasoning_effort' not in body and 'thinking' not in body
        else:
            assert body['thinking'] == {'type': 'enabled'} and body['reasoning_effort'] == level
            assert 'generationConfig' not in body
        return response(protocol, 'ok')
    model = ChatModel(cfg, role, client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    try:
        await model.complete([{'role': 'user', 'content': 'hi'}])
        assert len(seen) == 1
    finally:
        await model.close()


def test_go_defaults_legacy_settings_and_thinking_toggle():
    module = registry.get('opencode_go')
    for protocol, expected in [('google', 'medium'), ('chat', 'high')]:
        cfg = model_settings(protocol)
        profile = {'name': 'Go', 'model': cfg.model, 'provider': cfg.provider,
                   'base_url': cfg.base_url, 'api_key': cfg.api_key}
        saved = settings_store.validated_profile(profile)
        assert saved['reasoning_effort'] == expected
        legacy = {**saved, 'thinking': None, 'reasoning_effort': None}
        assert settings_store.to_model(legacy).reasoning_effort == expected
        assert legacy['reasoning_effort'] is None  # Do not rewrite historical snapshots.
        body = module.prepare(cfg, {'messages': []}, 'session')['body']
        assert (body['generationConfig']['thinkingConfig']['thinkingLevel'] if protocol == 'google'
                else body['reasoning_effort']) == expected
    saved = settings_store.validated_profile({**profile, 'thinking': 'disabled', 'reasoning_effort': 'max', 'temperature': .4})
    assert saved['thinking'] == 'disabled' and saved['reasoning_effort'] == 'max'
    cfg = settings_store.to_model(saved)
    body = module.prepare(cfg, {'messages': []}, 'session')['body']
    assert body['thinking'] == {'type': 'disabled'} and 'reasoning_effort' not in body
    assert body['temperature'] == .4
    enabled = module.prepare(replace(cfg, thinking='enabled'), {'messages': []}, 'session')['body']
    assert enabled['reasoning_effort'] == 'max' and 'temperature' not in enabled
    for protocol, value in [('google', 'max'), ('google', 'none'), ('chat', 'medium'), ('chat', 'xhigh')]:
        cfg = model_settings(protocol)
        with pytest.raises(ValueError):
            settings_store.validated_profile({**profile, 'model': cfg.model, 'reasoning_effort': value})
    with pytest.raises(ValueError):
        settings_store.validated_profile({**profile, 'model': MODELS['google'], 'thinking': 'disabled'})
    with pytest.raises(ValueError):
        module.prepare(replace(model_settings('chat'), thinking='invalid'), {'messages': []}, 'session')


async def test_catalog_headers_filters_and_ordinary_isolation():
    requests=[]
    def handler(req):
        requests.append(req)
        return httpx.Response(200,json={'data':[{'id':MODELS['chat']},{'id':'unknown-model'}]})
    go=ChatModel(model_settings('chat'),'main',client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    ordinary=ChatModel(replace(model_settings('chat'),provider='openai',profile_name='opencode_go'),'main',client=httpx.AsyncClient(base_url='https://ordinary.invalid/',transport=httpx.MockTransport(handler)))
    try:
        data=await go.models();assert len(data['data'])==1 and data['unmapped_models']==['unknown-model']
        await ordinary.models()
        assert requests[0].headers['x-opencode-session'] and 'x-opencode-session' not in requests[1].headers
    finally: await go.close();await ordinary.close()


def test_settings_and_module_removal(tmp_path,monkeypatch):
    from app.main import app
    module=registry.get('opencode_go')
    body={'name':'Go','model':MODELS['chat'],'provider':'opencode_go','base_url':module.BASE,'api_key':'fixture-go-secret','reasoning_effort':'max'}
    with TestClient(app) as api:
        result=api.post('/api/settings/profiles',json=body);assert result.status_code==200,result.text
        pid=result.json()['id'];assert 'fixture-go-secret' not in result.text
        original=settings_store.load()['active'].copy()
        assert api.put('/api/settings/active',json={'main':pid,'summary':pid}).status_code==200
        assert api.put('/api/settings/web',json={'credential_profile':pid}).status_code==422
        assert api.post('/api/settings/web/test/search',json={'credential_profile':pid}).status_code==422
        assert api.post('/api/settings/profiles',json={**body,'base_url':'https://other.invalid'}).status_code==422
        copy_root=tmp_path/'modules';shutil.copytree(registry.ROOT,copy_root)
        monkeypatch.setattr(registry,'ROOT',copy_root)
        # Physical removal, not just an empty registry: ordinary app remains usable.
        shutil.rmtree(copy_root/'opencode_go')
        cfg=api.get('/api/config');assert cfg.status_code==200
        assert cfg.json()['settings']['profiles'][pid]['capabilities']['unavailable']
        cid=api.post('/api/conversations').json()['id']
        assert api.post(f'/api/conversations/{cid}/runs',json={'question':'test'}).status_code==422
        assert api.put('/api/settings/active',json=original).status_code==200
        assert api.delete('/api/settings/profiles/'+pid).status_code==200
        assert api.get('/api/config').status_code==200
        with pytest.raises(ValueError):registry.get('opencode_go')


def test_usage_missing_fields_and_cache_math():
    module=registry.get('opencode_go')
    for protocol in MODELS:
        assert module.normalize_usage({},protocol)=={}
    usage=module.normalize_usage({'input_tokens':5,'cache_read_input_tokens':7,
        'cache_creation_input_tokens':3,'output_tokens':11},'messages')
    assert usage=={'prompt_tokens':15,'completion_tokens':11,'total_tokens':26,
                   'prompt_tokens_details':{'cached_tokens':7}}
    assert 'completion_tokens' not in module.normalize_usage({'promptTokenCount':20},'google')


async def test_cancel_closes_native_stream_and_records_usage():
    from app.telemetry import Telemetry
    entered=asyncio.Event();closed=asyncio.Event()
    class Stream(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b'data: {"type":"message_start","message":{"usage":{"input_tokens":5,"output_tokens":0}}}\n\n'
            entered.set()
            await asyncio.Event().wait()
        async def aclose(self):closed.set()
    rid=store.new_run(store.new_conversation(),'cancel',config_snapshot={})
    telemetry=Telemetry(rid)
    client=ChatModel(model_settings('messages'),'main',telemetry,
        client=httpx.AsyncClient(transport=httpx.MockTransport(lambda _:httpx.Response(200,headers={'content-type':'text/event-stream'},stream=Stream()))))
    task=asyncio.create_task(client.complete([{'role':'user','content':'test'}]))
    try:
        await asyncio.wait_for(entered.wait(),3);task.cancel()
        with pytest.raises(asyncio.CancelledError):await task
        assert closed.is_set()
        request=store.requests(rid)[0];assert request['status']=='cancelled'
        detail=store.requests(rid,request['id'])[0]
        assert detail['response']['usage']['prompt_tokens']==5
    finally:await client.close()


async def test_deepseek_web_and_ordinary_chat_do_not_receive_go_headers():
    requests=[]
    def handler(req):
        requests.append(req)
        return response('chat','ok') if req.url.path.endswith('completions') else httpx.Response(200,json={'content':'page'})
    ordinary=ChatModel(replace(model_settings('chat'),provider='openai',base_url='https://example.invalid'),
        'main',client=httpx.AsyncClient(base_url='https://example.invalid/',transport=httpx.MockTransport(handler)))
    web=DeepSeek(api_key='fixture-deepseek',client=httpx.AsyncClient(base_url='https://api.deepseek.com',transport=httpx.MockTransport(handler)))
    try:
        await ordinary.complete([{'role':'user','content':'test'}]);await web.fetch('https://example.org')
        assert all('x-opencode-session' not in r.headers for r in requests)
    finally:await ordinary.close();await web.close()


def test_disabling_registry_keeps_ordinary_models(tmp_path,monkeypatch):
    root=tmp_path/'modules';shutil.copytree(registry.ROOT,root)
    (root/'registry.json').write_text('{"providers":[]}')
    monkeypatch.setattr(registry,'ROOT',root)
    assert registry.catalog()=={} and registry.get('openai') is None and registry.get('deepseek') is None
    with pytest.raises(ValueError):registry.get('opencode_go')


@pytest.mark.parametrize('protocol',['messages','responses','google'])
def test_keep5_operates_on_results_without_losing_native_continuation(protocol):
    from app.context import request_view,OMITTED
    module=registry.get('opencode_go');history=[{'role':'user','content':'ORIGINAL_TASK'}]
    for i in range(7):
        decoder=module.Decoder(protocol,MODELS[protocol])
        full=json.loads(response(protocol,calls=[('search',{'query':str(i)})],stream=False).content)
        decoder.decode(full);m=decoder.result()['choices'][0]['message'];history.append(m)
        history.append({'role':'tool','tool_call_id':m['tool_calls'][0]['id'],'content':'RESULT_'+str(i)})
    saved=copy.deepcopy(history)
    for keep in (-1,5):
        view=request_view(history,keep)
        plan=module.prepare(model_settings(protocol),{'messages':view},'fixture')
        wire=json.dumps(plan['body'])
        assert 'ORIGINAL_TASK' in wire and ('SIGNED_' in wire)
        assert wire.count(OMITTED)==(0 if keep==-1 else 2)
        assert 'RESULT_6' in wire
    assert history==saved
