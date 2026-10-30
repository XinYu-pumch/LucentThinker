import copy
import json
import shutil
from dataclasses import replace

import httpx
import pytest
from fastapi.testclient import TestClient
from app import config, settings_store, store
from app.agent import research
from app.llm_providers import registry
from app.provider import ChatModel, ProviderError

pytestmark = pytest.mark.skipif('fourrouter_argon' not in registry.catalog(), reason='Optional Argon module disabled')

@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(store, 'DB', tmp_path/'test.sqlite3')
    monkeypatch.setattr(settings_store, 'SETTINGS_FILE', tmp_path/'settings.json')
    monkeypatch.setattr(config, 'API_KEY', 'fixture-web')
    monkeypatch.setattr(config, 'SECRETS', set())
    store.init()


def settings(level='high'):
    return config.ModelSettings(model='gemini-4-argon', base_url='https://4router.net/v1',
        api_key='fixture-secret', provider='fourrouter_argon', reasoning_effort=level, request_attempts=1)


def reply(text='', calls=(), stream=True, finish='STOP'):
    parts=[{'text':'PRIVATE_THOUGHT', 'thought':True, 'thoughtSignature':'SIGNED_THOUGHT'}]
    if text: parts.append({'text':text})
    parts += [{'functionCall':{'name':name,'args':args, 'id':f'native_{i}'},'thoughtSignature':f'SIGNED_CALL_{i}'} for i,(name,args) in enumerate(calls)]
    # Observed in live 4router SSE after the function call, rejected on replay.
    parts.append({'text':''})
    data={'candidates':[{'index':0,'content':{'role':'model','parts':parts},'finishReason':finish}],
          'usageMetadata':{'promptTokenCount':10,'candidatesTokenCount':3,'thoughtsTokenCount':7,'totalTokenCount':20,'cachedContentTokenCount':4}}
    if not stream:return httpx.Response(200,json=data)
    return httpx.Response(200,headers={'content-type':'text/event-stream'},text='data: '+json.dumps(data)+'\n\n')


@pytest.mark.parametrize('level',['low','medium','high'])
@pytest.mark.parametrize('stream',[True,False])
async def test_native_wire_tool_roundtrip_usage(level,stream):
    requests=[]
    def handle(req):
        requests.append(req)
        return reply('progress' if len(requests)==1 else 'done', [('echo',{'text':'a'}),('echo',{'text':'b'})] if len(requests)==1 else [],stream)
    model=ChatModel(settings(level),'main',client=httpx.AsyncClient(transport=httpx.MockTransport(handle)))
    tools=[{'type':'function','function':{'name':'echo','parameters':{'type':'object','properties':{'text':{'type':'string'}}}}}]
    history=[{'role':'system','content':'SYSTEM'},{'role':'user','content':'TASK'}]
    try:
        first=await model.complete(history,tools)
        assert first.finish_reason=='tool_calls' and len(first.message['tool_calls'])==2
        assert first.usage=={'prompt_tokens':10,'completion_tokens':10,'total_tokens':20,'completion_tokens_details':{'reasoning_tokens':7},'prompt_tokens_details':{'cached_tokens':4}}
        history.append(first.message)
        history += [{'role':'tool','tool_call_id':c['id'],'content':'RESULT_'+str(i)} for i,c in enumerate(first.message['tool_calls'])]
        out=await model.complete(history,purpose='final')
        assert out.message['content']=='done'
        a,b=[json.loads(r.content) for r in requests]
        assert a['generationConfig']=={'thinkingConfig':{'thinkingLevel':level,'includeThoughts':True}}
        assert 'tools' in a and 'tools' not in b
        assert 'SIGNED_CALL_0' in json.dumps(b) and 'SIGNED_THOUGHT' in json.dumps(b)
        assert all(part != {'text':''} for c in b['contents'] for part in c['parts'])
        results=[p['functionResponse'] for c in b['contents'] for p in c['parts'] if 'functionResponse' in p]
        assert [r['response']['result'] for r in results]==['RESULT_0','RESULT_1']
        assert [r['id'] for r in results]==['native_0','native_1']
        for req in requests:
            assert str(req.url)=='https://4router.net/v1beta/models/gemini-4-argon:streamGenerateContent?alt=sse'
            assert 'x-opencode-session' not in req.headers
            body=json.loads(req.content)
            assert not any(k in body for k in ('thinking','reasoning_effort','max_tokens','max_output_tokens'))
            assert 'maxOutputTokens' not in body['generationConfig']
    finally:await model.close()


async def test_research_and_extraction_independent_contexts():
    requests={'main':[],'summary':[]}
    actions=[[('search',{'query':'q','progress':'查找'})],
             [('scrape_and_extract_info',{'source_id':1,'info_to_extract':'Exact fact','progress':'读取'})],
             [('finish_research',{'status':'ready','summary':'done','unresolved_questions':[]})],[]]
    def handle(role):
        def receive(req):
            requests[role].append(json.loads(req.content))
            text=req.content.decode()
            if role=='summary':
                assert 'PRIVATE_MAIN_TASK' not in text and 'PAGE_ONLY' in text
                return reply('EXTRACTED_FACT')
            assert 'PAGE_ONLY' not in text
            i=len(requests[role])-1
            if i==2:assert 'EXTRACTED_FACT' in text
            return reply('Report [1]' if i==3 else '',actions[i])
        return receive
    class Web:
        async def search(self,*args):return {'results':[{'title':'Page','url':'https://example.org/a','snippet':'LEAD'}]}
        async def fetch(self,url):return {'content':'PAGE_ONLY'}
        async def close(self):pass
    models={r:settings() for r in requests}
    rid=store.new_run(store.new_conversation(),'PRIVATE_MAIN_TASK',config_snapshot=config.snapshot(models=models))
    await research(rid,models=models,main=ChatModel(models['main'],'main',client=httpx.AsyncClient(transport=httpx.MockTransport(handle('main')))),
                   summary=ChatModel(models['summary'],'summary',client=httpx.AsyncClient(transport=httpx.MockTransport(handle('summary')))),web=Web())
    run=store.get_run(rid)
    assert run['status']=='completed',run['error']
    assert len(requests['main'])==4 and len(requests['summary'])==1
    assert 'https://example.org/a' in run['answer']


def test_fixed_configuration_and_module_independence(tmp_path,monkeypatch):
    from app.main import app
    module=registry.get('fourrouter_argon')
    template=module.public_config()['template']
    with TestClient(app) as api:
        for changes in ({'model':'other'},{'base_url':'https://other.invalid/v1'},{'reasoning_effort':'max'},{'concurrency':0}):
            assert api.post('/api/settings/profiles',json={**template,**changes}).status_code==422
        result=api.post('/api/settings/profiles',json={**template,'api_key':'fixture-secret','concurrency':3})
        assert result.status_code==200
        pid=result.json()['id'];p=settings_store.load()['profiles'][pid]
        assert p['concurrency']==3 and p['reasoning_effort']=='high' and p['thinking'] is None
        assert 'fixture-secret' not in result.text
        assert api.put('/api/settings/web',json={'credential_profile':pid}).status_code==422
        root=tmp_path/'providers';shutil.copytree(registry.ROOT,root);monkeypatch.setattr(registry,'ROOT',root)
        shutil.rmtree(root/'opencode_go',ignore_errors=True)
        assert registry.get('fourrouter_argon').public_config()['fixed_model']=='gemini-4-argon'
        shutil.rmtree(root/'fourrouter_argon')
        data=api.get('/api/config').json()['settings']
        assert 'fourrouter_argon' not in data['providers']
        assert data['profiles'][pid]['capabilities']['unavailable']
        assert registry.get('deepseek') is None


async def test_catalog_only_exposes_fixed_model():
    def handle(req):
        assert str(req.url)=='https://4router.net/v1/models'
        assert 'x-opencode-session' not in req.headers
        return httpx.Response(200,json={'data':[{'id':'gemini-4-argon','supported_endpoint_types':['gemini','openai']},{'id':'other'}]})
    model=ChatModel(settings(),'main',client=httpx.AsyncClient(transport=httpx.MockTransport(handle)))
    try:
        data=await model.models()
        assert len(data['data'])==1
        assert data['data'][0]['reasoning_levels']==['low','medium','high']
    finally:await model.close()


def test_decoder_usage_errors_and_length():
    module=registry.get('fourrouter_argon')
    assert module.normalize_usage({})=={}
    assert module.normalize_usage({'promptTokenCount':10})=={'prompt_tokens':10}
    for finish in ('SAFETY',None):
        decoder=module.Decoder('google','gemini-4-argon')
        decoder.decode({'candidates':[{'finishReason':finish}]})
        with pytest.raises(ValueError):decoder.result()
    decoder=module.Decoder('google','gemini-4-argon')
    decoder.decode({'candidates':[{'finishReason':'MAX_TOKENS','content':{'parts':[{'text':'partial'}]}}]})
    result=decoder.result()
    assert result['choices'][0]['finish_reason']=='length'
    assert result['choices'][0]['message']['content']=='partial'
