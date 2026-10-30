import asyncio
import copy
import json
from dataclasses import replace
from pathlib import Path
import httpx
import pytest
from fastapi.testclient import TestClient
from app import config, store, settings_store
from app.agent import research, history_context
from app.context import request_view, OMITTED
from app.provider import ChatModel, ProviderError, ContextLimitError
from app.extraction import scrape_and_extract_info
from app.telemetry import Telemetry
from app.tool_schema import parse_call, TOOLS


@pytest.fixture(autouse=True)
def database(tmp_path, monkeypatch):
    monkeypatch.setattr(store, 'DB', tmp_path / 'test.sqlite3')
    monkeypatch.setattr(settings_store, 'SETTINGS_FILE', tmp_path / 'settings.json')
    monkeypatch.setattr(settings_store, 'DISCOVERED', {})
    monkeypatch.setattr(config, 'SECRETS', set())
    store.init()


def call(name, args, ident='tool1'):
    if name in ('search', 'scrape_and_extract_info') and isinstance(args, dict):
        args = {'progress': '核对本次研究所需的来源。', **args}
    return {'id': ident, 'type': 'function', 'function': {'name': name, 'arguments': json.dumps(args)}}


def msg(text=None, *calls):
    m = {'role': 'assistant', 'content': text, 'reasoning_content': 'protocol-reasoning'}
    if calls: m['tool_calls'] = list(calls)
    return m


def finish(text='Evidence sufficient', status='ready', gaps=None):
    return msg(None, call('finish_research', {'status': status, 'summary': text, 'unresolved_questions': gaps or []}, 'finish'))


def response(message, **extra):
    return {'choices': [{'message': message, 'finish_reason': extra.pop('finish_reason', 'stop')}],
            'model': 'deepseek-flash', 'usage': {'prompt_tokens': 100, 'completion_tokens': 20, 'total_tokens': 120}, **extra}


class Script:
    def __init__(self, outputs):
        self.outputs, self.payloads = list(outputs), []
    def handler(self, request):
        self.payloads.append(json.loads(request.content))
        assert self.outputs, 'Unexpected model call'
        output = self.outputs.pop(0)
        if callable(output): output = output(self.payloads[-1])
        if isinstance(output, httpx.Response): return output
        return httpx.Response(200, json=output if 'choices' in output else response(output))
    def model(self, role, **overrides):
        settings = replace(config.model_settings(role), api_key='test-credential', request_attempts=1, retry_delay=0, **overrides)
        return ChatModel(settings, role, client=httpx.AsyncClient(base_url='https://mock.invalid/', transport=httpx.MockTransport(self.handler)))


class Web:
    def __init__(self, empty=False, fail=False, body=None):
        self.searches, self.fetches, self.empty, self.fail, self.body = [], [], empty, fail, body
    async def search(self, query, question, count=10):
        self.searches.append(query)
        if self.fail: raise ProviderError('search unavailable')
        return {'results': [] if self.empty else [{'title': 'Evidence', 'url': 'https://example.org/a', 'snippet': 'SEARCH_EVIDENCE_' + query, 'summary': 'HIDDEN_SEARCH_SUMMARY_' + query}, {'title': 'B', 'url': 'https://example.org/b', 'snippet':'B lead'}]}
    async def fetch(self, url):
        self.fetches.append(url)
        if self.fail: raise ProviderError('fetch unavailable')
        return {'title': 'Page', 'content': self.body or ('RAW_PAGE_A' if url.endswith('/a') else 'RAW_PAGE_B')}
    async def close(self): pass


def newrun(preset='demo', **changes):
    snap = config.snapshot(preset)
    snap.update(changes)
    return store.new_run(store.new_conversation(), 'MAIN_PRIVATE_TASK research question', preset, snap)


async def execute(outputs, summaries=(), preset='demo', web=None, **changes):
    main, summary = Script(outputs), Script(summaries)
    rid = newrun(preset, **changes)
    await research(rid, main=main.model('main'), summary=summary.model('summary'), web=web or Web())
    return rid, main, summary


@pytest.mark.asyncio
async def test_full_model_driven_flow_and_summary_isolation():
    outputs = [msg('Find evidence', call('search', {'query': 'first'})),
               msg('Read A', call('scrape_and_extract_info', {'source_id': 1, 'info_to_extract': 'Exact number and date A'})),
               msg('Read B', call('scrape_and_extract_info', {'source_id': 2, 'info_to_extract': 'Exact definition B'})),
               msg('Verify discrepancy', call('search', {'query': 'second'})),
               finish('Evidence sufficient'), msg('结论来自来源 [1] 和 [2]。')]
    rid, main, summary = await execute(outputs, [msg('EXTRACTED_A: 42 on 2026-01-01'), msg('EXTRACTED_B: definition')])
    run = store.get_run(rid)
    assert run['status'] == 'completed', run['error']
    assert len(main.payloads) == 6 and len(summary.payloads) == 2
    assert 'SEARCH_EVIDENCE_first' in json.dumps(main.payloads[1])
    assert 'EXTRACTED_A' in json.dumps(main.payloads[2])
    assert 'EXTRACTED_B' in json.dumps(main.payloads[3])
    for payload in main.payloads:
        assert 'RAW_PAGE_' not in json.dumps(payload)
    for i, payload in enumerate(summary.payloads):
        text = json.dumps(payload)
        assert 'MAIN_PRIVATE_TASK' not in text and 'SEARCH_EVIDENCE' not in text and 'EXTRACTED_' not in text
        assert ('RAW_PAGE_A' if i == 0 else 'RAW_PAGE_B') in text
        assert ('RAW_PAGE_B' if i == 0 else 'RAW_PAGE_A') not in text
        assert 'tools' not in payload and len(payload['messages']) == 2
    assert all('tools' in p for p in main.payloads[:-1])
    assert 'tools' not in main.payloads[-1]
    assert 'Markdown' in main.payloads[-1]['messages'][-1]['content']
    assert '\\boxed' not in main.payloads[-1]['messages'][-1]['content']
    assert run['usage']['main']['calls'] == 6 and run['usage']['summary']['calls'] == 2
    assert run['usage']['main_iterations'] == 5
    assert run['usage']['search_calls'] == 2 and run['usage']['extraction_calls'] == 2
    assert len(store.requests(rid)) == 8
    assert {e['kind'] for e in store.events(rid)} >= {'tool_start', 'tool_done', 'fetch_start', 'extraction_done', 'done'}


@pytest.mark.parametrize('preset,omitted', [('demo', 0), ('keep5_max200', 3)])
async def test_actual_retention_does_not_mutate_saved_history(preset, omitted):
    outputs = [msg('analysis ' + str(i), call('search', {'query': str(i)})) for i in range(7)] + [finish('ready'), msg('answer [1]')]
    rid, main, _ = await execute(outputs, preset=preset)
    assert store.get_run(rid)['status'] == 'completed'
    sent = main.payloads[-1]['messages']
    tools = [m for m in sent if m['role'] == 'tool']
    assert len(tools) == 8 and sum(t['content'] == OMITTED for t in tools) == omitted
    assert sent[1]['content'].startswith('MAIN_PRIVATE_TASK')
    assert len([m for m in sent if m['role'] == 'assistant']) == 8
    journal = store.messages(rid)
    assert all(m['message']['content'] != OMITTED for m in journal if m['message']['role'] == 'tool')
    assert len([m for m in journal if m['message']['role'] == 'tool']) == 8


def test_retention_counts_messages_not_rounds():
    messages = [{'role': 'user', 'content': 'original'}]
    for i in range(8):
        messages += [{'role': 'assistant', 'content': str(i)}, {'role': 'tool', 'tool_call_id': str(i), 'content': str(i)}]
    messages += [{'role': 'user', 'content': 'control'}]
    original = copy.deepcopy(messages)
    view = request_view(messages, 5)
    assert len([m for m in view if m.get('content') == OMITTED]) == 3
    assert messages == original and view[0] == original[0] and view[-1] == original[-1]


async def test_duplicate_rollback_four_times_then_real_execution():
    web = Web()
    outputs = [msg(None, call('search', {'query': 'same'})) for _ in range(6)] + [finish('done'), msg('final [1]')]
    rid, main, _ = await execute(outputs, web=web)
    assert store.get_run(rid)['status'] == 'completed'
    assert web.searches == ['same', 'same']
    rolled = [r for r in store.messages(rid) if r['rolled_back'] == 'duplicate_call']
    assert len(rolled) == 4
    assert store.get_run(rid)['usage']['main_iterations'] == 3
    assert len([m for m in main.payloads[-1]['messages'] if m['role'] == 'tool']) == 3


async def test_empty_search_rollbacks_then_error_feedback():
    outputs = [msg(None, call('search', {'query': 'q' + str(i)})) for i in range(5)] + [finish('no evidence'), msg('No evidence found.')]
    rid, main, _ = await execute(outputs, web=Web(empty=True))
    assert store.get_run(rid)['status'] == 'completed'
    assert len([r for r in store.messages(rid) if r['rolled_back'] == 'tool_execution_error' and r['message']['role'] == 'tool']) == 4
    assert '"results": []' in main.payloads[-2]['messages'][-1]['content']


async def test_extraction_failure_is_returned_to_main():
    class FetchFailure(Web):
        async def search(self,*args): return {'results':[{'url':'https://example.org/a','snippet':'lead'}]}
        async def fetch(self,url): raise ProviderError('fetch unavailable')
    rid, main, summary = await execute([msg(None, call('search', {'query':'discover'})), msg(None, call('scrape_and_extract_info', {'source_id': 1, 'info_to_extract': 'fact'})), finish('try other method'), msg('Unable to verify.')], web=FetchFailure())
    result = json.loads(main.payloads[2]['messages'][-1]['content'])
    assert result['success'] is False and 'fetch unavailable' in result['error']
    assert not summary.payloads and store.get_run(rid)['status'] == 'completed'


async def test_page_is_sent_in_full_beyond_previous_char_cap():
    body = 'abcdef ' * 100000 + 'END_OF_FULL_PAGE'
    web = Web(body=body)
    rid, main, summary = await execute([msg(None, call('search', {'query':'discover'})), msg(None,call('scrape_and_extract_info',{'source_id': 1, 'info_to_extract':'numbers'})),finish('ready'),msg('answer [1]')], [msg('Extracted')],web=web)
    assert store.get_run(rid)['status']=='completed'
    assert summary.payloads[0]['messages'][1]['content'].endswith(body)
    result=json.loads(main.payloads[2]['messages'][-1]['content'])
    assert result['scrape_stats']['displayed_char_count']==len(body)
    assert result['scrape_stats']['all_content_displayed'] is True
    assert result['scrape_stats']['truncation_reasons']==[]


async def test_summary_output_limit_is_failure_not_success():
    rid, main, _ = await execute([msg(None, call('search', {'query':'discover'})), msg(None, call('scrape_and_extract_info', {'source_id': 1, 'info_to_extract': 'fact'})), finish('ready'), msg('Incomplete.')], [response(msg('truncated'), finish_reason='length')])
    assert not json.loads(main.payloads[2]['messages'][-1]['content'])['success']
    assert store.get_run(rid)['usage']['summary']['errors'] == 1


async def test_iteration_limit_demo_forces_separate_final():
    rid, main, _ = await execute([msg(None, call('search', {'query': 'q'})), msg('final [1]')], max_iterations=1)
    assert store.get_run(rid)['end_reason'] == 'iteration_limit'
    assert len(main.payloads) == 2 and 'tools' not in main.payloads[-1]
    assert 'maximum number' in main.payloads[-1]['messages'][-1]['content']


async def test_keep5_outer_attempts_restart_without_shared_history():
    outputs = [msg(None, call('search', {'query': 'q' + str(i)})) for i in range(6)] + [msg('final [6]')]
    rid, main, _ = await execute(outputs, preset='keep5_max200', max_iterations=1)
    run = store.get_run(rid)
    assert run['status'] == 'completed' and run['usage']['research_attempts'] == 6
    assert len(main.payloads) == 7
    assert all(len(p['messages']) == 2 for p in main.payloads[:6])
    assert not any(r['purpose'] == 'failure_summary' for r in store.requests(rid))
    assert len({m['attempt'] for m in store.messages(rid)}) == 6


async def test_reported_usage_never_triggers_local_context_rollback():
    first=response(msg(None,call('search',{'query':'q'})),usage={'prompt_tokens':1048000,'completion_tokens':100,'total_tokens':1048100})
    rid,main,_=await execute([first,finish('ready'),msg('answer [1]')])
    assert store.get_run(rid)['status']=='completed'
    assert any(m['role']=='tool' for m in main.payloads[-1]['messages'])
    assert not any(m['rolled_back'] for m in store.messages(rid))


async def test_provider_context_error_fails_without_trimming_or_final_retry():
    rid,main,_=await execute([msg(None,call('search',{'query':'q'})),httpx.Response(400,json={'error':'context length exceeded'})])
    assert store.get_run(rid)['status']=='failed'
    assert store.get_run(rid)['end_reason']=='provider_context_limit'
    assert len(main.payloads)==2 and 'tools' in main.payloads[-1]
    assert not any(m['rolled_back'] for m in store.messages(rid))
    assert any(m['message']['role']=='tool' for m in store.messages(rid))


async def test_small_advertised_window_does_not_prevent_full_input():
    rid=newrun()
    main=Script([finish('ready'),msg('answer')])
    await research(rid,main=main.model('main',context_window=1,max_tokens=None),summary=Script([]).model('summary'),web=Web())
    assert store.get_run(rid)['status']=='completed'
    assert main.payloads[0]['messages'][1]['content'].startswith('MAIN_PRIVATE_TASK')
    assert 'max_tokens' not in main.payloads[0]


async def test_invalid_tool_arguments_are_feedback_not_execution():
    invalid = call('search', {})
    invalid['function']['arguments'] = '[]'
    rid, main, _ = await execute([msg(None, invalid), finish(), msg('No evidence.')])
    assert store.get_run(rid)['end_reason'] == 'model_finished'
    assert 'JSON object' in main.payloads[1]['messages'][-1]['content']
    assert store.get_run(rid)['usage']['search_calls'] == 0
    assert not any(m['rolled_back'] for m in store.messages(rid))


def test_strict_json_schema_rejects_repair_aliases_and_unknown_tools():
    for native in (call('scrape_and_extract_info', {'url': 'https://example.org', 'description': 'date'}),
                   call('unsupported', {}), call('search', {'query': 'q', 'extra': None})):
        with pytest.raises(ValueError): parse_call(native)
    malformed = call('search', {})
    for raw in ("{query: 'climate', count: 3,}", '{"query":"q","count":NaN}'):
        malformed['function']['arguments'] = raw
        with pytest.raises(ValueError): parse_call(malformed)
    native = call('scrape_and_extract_info', {'source_id': 1, 'info_to_extract':'date'})
    assert parse_call(native) == ('scrape_and_extract_info', {'source_id': 1, 'info_to_extract':'date', 'progress': '核对本次研究所需的来源。'})


async def test_final_tool_request_never_executed_and_retried():
    web = Web()
    rid, main, _ = await execute([finish('ready'), msg(None, call('search', {'query': 'not allowed'})), msg('final')], web=web)
    assert not web.searches and store.get_run(rid)['status'] == 'completed'
    assert all('tools' not in p for p in main.payloads[1:])


async def test_cancel_marks_actual_request_and_journal():
    started = asyncio.Event()
    async def handler(request):
        started.set()
        await asyncio.Event().wait()
    settings = replace(config.model_settings('main'), api_key='test')
    main = ChatModel(settings, 'main', client=httpx.AsyncClient(base_url='https://mock.invalid/', transport=httpx.MockTransport(handler)))
    rid = newrun()
    task = asyncio.create_task(research(rid, main=main, summary=Script([]).model('summary'), web=Web()))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError): await task
    assert store.get_run(rid)['status'] == 'cancelled'
    assert store.requests(rid)[0]['status'] == 'cancelled'


def test_snapshot_defaults_and_credential_redaction(monkeypatch):
    demo = config.snapshot()
    assert (demo['max_iterations'], demo['keep_tool_result'], demo['context_compress_limit'], demo['retry_with_summary']) == (50, -1, 0, True)
    keep = config.snapshot('keep5_max200')
    assert (keep['max_iterations'], keep['keep_tool_result'], keep['context_compress_limit'], keep['retry_with_summary']) == (200, 5, 5, False)
    monkeypatch.setenv('SUMMARY_LLM_API_KEY', 'secret-test-key')
    rid = newrun()
    original = store.get_run(rid)['config_snapshot']
    monkeypatch.setenv('MAIN_LLM_MODEL_NAME', 'changed')
    assert store.get_run(rid)['config_snapshot'] == original
    store.event(rid, 'test', {'text': 'secret-test-key', 'api_key': 'secret-test-key'})
    assert store.events(rid)[0]['data'] == {'text': '[REDACTED]'}


def test_api_debug_security_and_restart():
    from app.main import app
    rid = newrun()
    store.begin_request(rid, 'main', 'research', 1, 1, {'model': 'test', 'messages': []})
    with TestClient(app) as client:
        assert store.get_run(rid)['status'] == 'interrupted'
        assert client.get('/api/config').json()['presets']['demo']['max_iterations'] == 50
        d = client.get('/api/runs/' + rid + '/details').json()
        assert d['requests'][0]['status'] == 'interrupted'
        request_id = d['requests'][0]['id']
        assert client.get(f'/api/runs/{rid}/requests/{request_id}').json()['request']['messages'] == []
        assert client.get('/api/config', headers={'Host': 'evil.invalid'}).status_code == 403
        assert client.post('/api/conversations', headers={'Origin': 'https://evil.invalid'}).status_code == 403


def test_followup_preserves_all_completed_questions_answers_and_sources():
    sources=[{'id':i,'url':f'https://e.org/{i}','title':str(i)} for i in range(30)]
    runs=[{'status':'completed','question':str(i),'answer':'A'*20000+'TAIL','sources':sources} for i in range(10)]
    context=history_context({'runs':runs})
    assert len(context)==10 and context[0]['question']=='0'
    assert all(c['answer'].endswith('TAIL') and len(c['answer'])==20004 and len(c['sources'])==30 for c in context)
    assert config.snapshot()['memory_mode']=='strict'

async def test_unknown_tool_feedback_without_execution():
    rid, main, _ = await execute([msg(None, call('unsupported', {}))] * 5 + [finish('ready'), msg('final')])
    assert store.get_run(rid)['status'] == 'completed'
    assert 'Unknown tool' in main.payloads[-2]['messages'][-1]['content']
    assert not any(r['rolled_back'] for r in store.messages(rid))


async def test_multiple_tools_one_iteration_keep5_counts_each_result():
    calls = [call('search', {'query': str(i)}, ident=str(i)) for i in range(7)]
    rid, main, _ = await execute([msg(None, *calls), finish('ready'), msg('final [1]')], preset='keep5_max200')
    tools = [m for m in main.payloads[1]['messages'] if m['role']=='tool']
    assert len(tools) == 7 and sum(m['content']==OMITTED for m in tools) == 2
    assert store.get_run(rid)['usage']['main_iterations'] == 2


async def test_extraction_context_error_returns_failure_without_any_shortened_retry():
    body='sample ' * 100000 + 'FULL_END'
    rid,main,summary=await execute([msg(None, call('search', {'query':'discover'})), msg(None,call('scrape_and_extract_info',{'source_id': 1, 'info_to_extract':'fact'})),finish('ready'),msg('Incomplete.')],[httpx.Response(400,json={'error':'context length exceeded'})],web=Web(body=body))
    assert len(summary.payloads)==1 and summary.payloads[0]['messages'][1]['content'].endswith(body)
    result=json.loads(main.payloads[2]['messages'][-1]['content'])
    assert not result['success'] and result['model_used'] is None
    assert result['scrape_stats']['all_content_displayed'] is True


async def test_protocol_rollback_never_leaves_orphaned_tools():
    # A successful first call and duplicate second call cause a whole-interaction rollback.
    outputs = [msg(None, call('search', {'query':'a'})),
               msg(None, call('search', {'query':'b'}, 'b'), call('search', {'query':'a'}, 'a')),
               finish('ready'), msg('final [1]')]
    rid, main, _ = await execute(outputs)
    for payload in main.payloads:
        pending = set()
        for m in payload['messages']:
            if m['role']=='assistant':
                assert not pending
                pending = {c['id'] for c in m.get('tool_calls', [])}
            elif m['role']=='tool':
                assert m['tool_call_id'] in pending
                pending.remove(m['tool_call_id'])
            else: assert not pending
        assert not pending
    assert any(m['rolled_back']=='duplicate_call' and m['message']['role']=='tool' for m in store.messages(rid))


def test_citations_registered_ids_are_authoritative_not_model_urls():
    from app.citations import reconcile
    sources = [{'id':1,'url':'https://example.org/other'}, {'id':20,'url':'https://example.org/a'}]
    answer, check = reconcile('Facts [1][2].\n[1] A https://example.org/a\n[2] B https://unknown.org/', sources)
    assert answer.startswith('Facts [1][引用无法匹配 2]')
    assert check['conflicting_ids'] == [1] and check['unmatched_ids'] == [2]
    assert 'https://example.org/other' in answer and 'https://unknown.org/' not in answer
    assert '引用冲突' in answer


def test_citation_tracking_parameters_do_not_invalidate_registered_id():
    from app.citations import reconcile
    sources=[{'id':112,'url':'https://m.sohu.com/a/933571084_498271/?pvid=a&scm=b&spm=c#1'}]
    answer, check = reconcile('Fact [112]\n[112] Page https://m.sohu.com/a/933571084_498271/',sources)
    assert '[112]' in answer and not check['conflicting_ids'] and not check['unmatched_ids']
    assert sources[0]['url'] in answer


def test_citation_inline_links_rebound_but_document_parameters_preserved():
    from app.citations import reconcile
    sources=[{'id':1,'url':'https://e.org/page?id=1'},{'id':2,'url':'https://e.org/b'}]
    answer, check = reconcile('Claim [1](https://e.org/page?id=2 "B")[2](https://e.org/b) [9](https://e.org/b) `code [100]`',sources)
    assert '[1](<https://e.org/page?id=1>)' in answer and 'id=2' not in answer
    assert check['conflicting_ids']==[1] and check['unmatched_ids']==[9]
    assert '`code [100]`' in answer and '[引用无法匹配 9]' in answer


def test_api_default_strict_and_explicit_followup(monkeypatch):
    import app.main as api_module
    async def no_network(rid, **kwargs):
        store.update(rid, status='completed', answer='test')
    monkeypatch.setattr(api_module, 'research', no_network)
    with TestClient(api_module.app) as client:
        cid = client.post('/api/conversations').json()['id']
        previous = store.new_run(cid, 'Prior question')
        store.update(previous, status='completed', answer='PRIOR_ANSWER')
        first = client.post(f'/api/conversations/{cid}/runs', json={'question':'Independent question'}).json()
        strict = store.get_run(first['id'])
        assert strict['mode']=='demo' and strict['memory_context']==[]
        assert strict['config_snapshot']['tools']==config.snapshot(web={'search_count': settings_store.load()['research']['search_count']})['tools']
        second = client.post(f'/api/conversations/{cid}/runs', json={'question':'Follow up','memory_mode':'followup'}).json()
        assert 'PRIOR_ANSWER' in json.dumps(store.get_run(second['id'])['memory_context'])


async def test_length_keeps_partial_output_and_does_not_retry_or_increase_local_limit(monkeypatch):
    # Explicit provider metadata keeps this test independent of local data/ files.
    monkeypatch.setattr(config, 'verified_metadata', lambda base, model: {'id': model, 'max_output_tokens': 393216})
    script=Script([response(msg('PARTIAL_OUTPUT'),finish_reason='length')])
    rid=newrun()
    await research(rid,main=script.model('main'),summary=Script([]).model('summary'),web=Web())
    run=store.get_run(rid)
    assert run['status']=='incomplete' and run['answer']=='PARTIAL_OUTPUT'
    assert len(script.payloads)==1
    assert script.payloads[0]['max_tokens']==393216
    assert not any(m['rolled_back'] for m in store.messages(rid))


def test_malformed_reference_url_is_flagged_not_a_crash():
    from app.citations import reconcile
    answer, check = reconcile('Fact [1]\n[1] Broken https://[bad', [{'id':1,'url':'https://example.org'}])
    assert check['conflicting_ids']==[1] and '[1]' in answer and '引用冲突' in answer

async def test_search_wire_limits_block_invalid_text_without_http_and_keep_count():
    from app.provider import DeepSeek
    payloads=[]
    def handler(request):
        payloads.append(json.loads(request.content))
        return httpx.Response(200,json={'results':[]})
    web=DeepSeek(api_key='search-secret',client=httpx.AsyncClient(base_url='https://mock.invalid',transport=httpx.MockTransport(handler)))
    query='研'*128;question='问'*128
    try:
        for q, intent in [(query+'超',question),(query,question+'超'),(query,''),(query,' '),(query,None)]:
            with pytest.raises(ValueError): await web.search(q,intent,1000)
        assert not payloads
        await web.search(query,question,1000)
        assert payloads==[{'query':query,'count':1000,'ori_question':question,'need_content':True}]
        with pytest.raises(ValueError,match='128'): parse_call(call('search',{'query':query+'超'}))
    finally: await web.close()


def test_profile_crud_activation_reveal_and_no_secret_in_public_api():
    from app.main import app
    with TestClient(app) as client:
        body={'name':'Saved endpoint','base_url':'https://compatible.example/v1/chat/completions','model':'model-a','api_key':'PROFILE_SECRET','provider':'openai'}
        result=client.post('/api/settings/profiles',json=body)
        assert result.status_code==200,result.text
        ident=result.json()['id']
        assert 'PROFILE_SECRET' not in result.text
        settings=client.get('/api/settings').json()
        assert settings['profiles'][ident]['base_url']=='https://compatible.example/v1'
        assert settings['profiles'][ident]['configured'] is True
        revealed=client.post(f'/api/settings/profiles/{ident}/reveal')
        assert revealed.json()['api_key']=='PROFILE_SECRET'
        assert revealed.headers['cache-control']=='no-store'
        assert settings_store.SETTINGS_FILE.stat().st_mode & 0o777 == 0o600
        assert client.post(f'/api/settings/active/main/{ident}').status_code==200
        assert client.delete(f'/api/settings/profiles/{ident}').status_code==422
        frozen=config.model_settings('main')
        edited={**body,'id':ident,'api_key':None,'name':'Edited profile','model':'model-b'}
        assert client.post('/api/settings/profiles',json=edited).status_code==200
        assert config.model_settings('main').model=='model-b' and frozen.model=='model-a'
        assert frozen.api_key=='PROFILE_SECRET'
        changed={**edited,'base_url':'https://other.example/v1'}
        assert client.post('/api/settings/profiles',json=changed).status_code==422
        assert client.post('/api/settings/active/main/main').status_code==200
        assert client.delete(f'/api/settings/profiles/{ident}').status_code==200
        assert ident not in settings_store.load()['profiles']
        assert 'PROFILE_SECRET' not in json.dumps(client.get('/api/config').json())


def test_model_discovery_test_hello_and_generic_payload(monkeypatch):
    import app.settings_api as settings_api
    from app.main import app
    observed=[]
    def handler(request):
        if request.method=='GET':
            assert str(request.url)=='https://compatible.example/v1/models'
            return httpx.Response(200,json={'data':[{'id':'model-a','max_output_tokens':999999,'context_window':1234567}]})
        p=json.loads(request.content);observed.append(p)
        return httpx.Response(200,json=response(msg('hellow back')))
    real=ChatModel
    monkeypatch.setattr(settings_api,'ChatModel',lambda settings,role,**kwargs:real(settings,role,**kwargs,client=httpx.AsyncClient(base_url=settings.base_url+'/',transport=httpx.MockTransport(handler))))
    with TestClient(app) as client:
        body={'name':'Compatible','base_url':'https://compatible.example/v1','api_key':'secret','model':'model-a','provider':'openai'}
        assert client.post('/api/settings/models',json=body).json()['models'][0]['id']=='model-a'
        ident=client.post('/api/settings/profiles',json=body).json()['id']
        p=settings_store.to_model(settings_store.load()['profiles'][ident])
        assert p.max_tokens==999999
        result=client.post('/api/settings/test',json={**body,'id':ident,'api_key':None}).json()
        assert result['ok'] and result['reply']=='hellow back'
        assert observed[0]['messages']==[{'role':'user','content':'hellow'}]
        assert observed[0]['max_tokens']==999999
        assert 'thinking' not in observed[0] and 'reasoning_effort' not in observed[0]


def test_research_settings_independent_tiers_and_large_user_question(monkeypatch):
    import app.main as api_module
    monkeypatch.setattr(config, 'verified_metadata', lambda base, model: {'id': model, 'max_output_tokens': 393216})
    captured=[]
    async def no_network(rid,**kwargs):
        captured.append(kwargs)
        store.update(rid,status='completed',answer='ok')
    monkeypatch.setattr(api_module,'research',no_network)
    with TestClient(api_module.app) as client:
        body={'iteration_tier':'custom','max_iterations':1200,'keep_tool_result':-1,'context_compress_limit':0,'memory_mode':'strict','preset':'demo'}
        assert client.put('/api/settings/research',json=body).status_code==200
        cid=client.post('/api/conversations').json()['id']
        question='完整问题' * 20000+'END'
        result=client.post(f'/api/conversations/{cid}/runs',json={'question':question}).json()
        saved=store.get_run(result['id'])
        assert saved['question']==question
        assert saved['config_snapshot']['max_iterations']==1200
        assert saved['config_snapshot']['keep_tool_result']==-1
        assert saved['config_snapshot']['context_compress_limit']==0
        assert saved['config_snapshot']['input_policy']=='full_content_provider_validated'
        assert saved['config_snapshot']['main_model']['max_tokens']==393216
        assert saved['config_snapshot']['summary_model']['max_tokens']==393216
        assert captured[0]['web_api_key']==settings_store.web_key()
        assert client.put('/api/settings/research',json={**body,'max_iterations':0}).status_code==422


async def test_streamed_content_tools_and_usage_are_assembled_and_persisted():
    chunks=[{'id':'c1','model':'model','choices':[{'index':0,'delta':{'role':'assistant','content':'hello ','reasoning_content':'internal '},'finish_reason':None}]},
        {'choices':[{'index':0,'delta':{'content':'world','tool_calls':[{'index':0,'id':'tool1','function':{'name':'search','arguments':'{"query":'}}]},'finish_reason':None}]},
        {'choices':[{'index':0,'delta':{'tool_calls':[{'index':0,'function':{'arguments':'"q","progress":"查找来源"}'}}]},'finish_reason':'tool_calls'}]},
        {'choices':[],'usage':{'prompt_tokens':10,'completion_tokens':20,'total_tokens':30}}]
    content=''.join('data: '+json.dumps(c)+'\n\n' for c in chunks)+'data: [DONE]\n\n'
    script=httpx.MockTransport(lambda req:httpx.Response(200,content=content,headers={'Content-Type':'text/event-stream'}))
    rid=newrun();telemetry=Telemetry(rid)
    model=ChatModel(replace(config.model_settings('main'),api_key='mock-stream-credential'),'main',telemetry,client=httpx.AsyncClient(base_url='https://mock.invalid',transport=script))
    try:
        output=await model.complete([{'role':'user','content':'question'}],TOOLS)
        assert output.message['content']=='hello world'
        assert parse_call(output.message['tool_calls'][0])==('search',{'query':'q','progress':'查找来源'})
        assert output.usage['total_tokens']==30
        req=store.requests(rid)[0]
        assert store.chunks(req['id'])[0]==chunks
        assert telemetry.usage['main']['calls']==1
    finally: await model.close()


async def test_final_stream_length_preserves_answer_and_marks_incomplete():
    main=Script([finish('ready')])
    final_chunks=[{'model':'deepseek-flash','choices':[{'index':0,'delta':{'content':'FULL_PARTIAL_ANSWER'},'finish_reason':None}]},
                  {'choices':[{'index':0,'delta':{},'finish_reason':'length'}],'usage':{'prompt_tokens':1,'completion_tokens':1,'total_tokens':2}}]
    main.outputs.append(httpx.Response(200,content=''.join('data: '+json.dumps(c)+'\n\n' for c in final_chunks)+'data: [DONE]\n\n',headers={'Content-Type':'text/event-stream'}))
    rid=newrun()
    await research(rid,main=main.model('main'),summary=Script([]).model('summary'),web=Web())
    saved=store.get_run(rid)
    assert saved['status']=='incomplete' and saved['answer']=='FULL_PARTIAL_ANSWER'
    assert len(main.payloads)==2 and 'tools' not in main.payloads[-1]
    assert any(e['kind']=='answer_delta' for e in store.events(rid))
    assert not any(m['rolled_back'] for m in store.messages(rid))


async def test_broken_stream_keeps_chunks_without_claiming_complete():
    rid=newrun();telemetry=Telemetry(rid)
    data='data: '+json.dumps({'choices':[{'index':0,'delta':{'content':'received text'}}]})+'\n\n'
    model=ChatModel(replace(config.model_settings('main'),api_key='mock-stream-credential'),'main',telemetry,client=httpx.AsyncClient(base_url='https://mock.invalid',transport=httpx.MockTransport(lambda req:httpx.Response(200,content=data,headers={'Content-Type':'text/event-stream'}))))
    try:
        with pytest.raises(ProviderError,match='结束标记'):
            await model.complete([{'role':'user','content':'question'}],purpose='final')
        assert store.get_run(rid)['answer']=='received text'
        assert store.requests(rid)[0]['status']=='failed'
        assert store.chunks(store.requests(rid)[0]['id'])
    finally: await model.close()


def test_web_key_is_independent_and_config_reveal_requires_same_origin():
    from app.main import app
    with TestClient(app) as client:
        assert client.put('/api/settings/web',json={'api_key':'WEB_ONLY','credential_profile':None}).status_code==200
        assert settings_store.web_key()=='WEB_ONLY'
        assert config.model_settings('main').api_key!='WEB_ONLY'
        assert client.post('/api/settings/web/reveal',headers={'Origin':'https://evil.invalid'}).status_code==403
        assert client.post('/api/settings/web/reveal').json()['api_key']=='WEB_ONLY'
        assert 'WEB_ONLY' not in client.get('/api/settings').text

async def test_main_can_fix_service_rejection_with_explicit_search_intent():
    class RejectThenAccept(Web):
        def __init__(self): super().__init__(); self.questions=[]
        async def search(self,query,question,count=10):
            self.questions.append(question)
            if question.startswith('MAIN_PRIVATE_TASK'): raise ProviderError('ori_question must be between 1 and 128 characters',code=400)
            return await super().search(query,question,count)
    web=RejectThenAccept()
    rid,main,_=await execute([msg(None,call('search',{'query':'query'})),msg(None,call('search',{'query':'query','search_intent':'Focused question'})),finish('ready'),msg('final [1]')],web=web)
    assert store.get_run(rid)['status']=='completed'
    assert '128 characters' in main.payloads[1]['messages'][-1]['content']
    assert web.questions==['MAIN_PRIVATE_TASK research question','Focused question']
    assert not any(m['rolled_back'] for m in store.messages(rid))


async def test_long_query_feedback_allows_model_rewrite_without_truncating():
    web=Web()
    rid,main,_=await execute([msg(None,call('search',{'query':'研'*129})),msg(None,call('search',{'query':'short query'})),finish('ready'),msg('final [1]')],web=web)
    assert store.get_run(rid)['status']=='completed'
    assert web.searches==['short query']
    assert '128' in main.payloads[1]['messages'][-1]['content']
    original=main.payloads[1]['messages'][-2]['tool_calls'][0]['function']['arguments']
    assert json.loads(original)['query']=='研'*129
    assert not any(m['rolled_back'] for m in store.messages(rid))

@pytest.mark.asyncio
async def test_search_snippet_only_with_raw_response_audit():
    class RichWeb(Web):
        async def search(self,*args):
            return {'results':[{'url':'https://example.org/a','title':'Official policy','snippet':'PUBLIC_SNIPPET',
                'summary':'SECRET_SUMMARY_SENTINEL','content':'SECRET_BODY_SENTINEL','site_name':'Official'}]}
    rid,main,_=await execute([msg(None,call('search',{'query':'policy'})),finish('Ready'),msg('Answer [1]')],web=RichWeb())
    assert store.get_run(rid)['status']=='completed'
    payload=json.dumps(main.payloads)
    assert 'PUBLIC_SNIPPET' in payload and 'SECRET_SUMMARY_SENTINEL' not in payload and 'SECRET_BODY_SENTINEL' not in payload
    raw=store.search_responses(rid)
    assert raw[0]['response']['results'][0]['summary']=='SECRET_SUMMARY_SENTINEL'
    assert raw[0]['response']['results'][0]['content']=='SECRET_BODY_SENTINEL'
    with TestClient(__import__('app.main',fromlist=['app']).app) as client:
        assert client.get(f'/api/runs/{rid}/search-responses').json()==raw
    assert any(e['kind']=='evidence_status' and e['data']['original_extractions']==0 for e in store.events(rid))

@pytest.mark.asyncio
@pytest.mark.parametrize('empty_body',[False,True])
async def test_fetch_failure_uses_exact_summary_via_independent_model(empty_body):
    class FailingFetch(Web):
        async def fetch(self,url):
            self.fetches.append(url)
            if empty_body:return {'content':''}
            raise ProviderError('FETCH_DENIED',code=403)
    outputs=[msg(None,call('search',{'query':'fallback source'})),
             msg(None,call('scrape_and_extract_info',{'source_id': 1, 'info_to_extract':'Rate and effective date'})),
             finish('Ready with limitation'),msg('Limited result [1]')]
    web=FailingFetch()
    rid,main,summary=await execute(outputs,[msg('Summary-only evidence: extracted rate')],web=web)
    run=store.get_run(rid)
    assert run['status']=='completed',run['error']
    assert len(web.fetches)==1 and len(summary.payloads)==1
    payload=summary.payloads[0]
    assert len(payload['messages'])==2
    text=json.dumps(payload)
    assert 'HIDDEN_SEARCH_SUMMARY_fallback source' in text and 'MAIN_PRIVATE_TASK' not in text
    assert 'search_summary' in text and 'fetch_error' in text
    assert 'HIDDEN_SEARCH_SUMMARY_fallback source' not in json.dumps(main.payloads)
    results=[json.loads(r['message']['content']) for r in store.messages(rid) if r['message']['role']=='tool']
    result=next(r for r in results if 'extracted_info' in r)
    assert result['success'] and result['degraded'] and result['content_source']=='search_summary'
    assert result['fallback_search_response_id']==store.search_responses(rid)[0]['id']
    assert result['fetch_error'] and 'Summary-only evidence' in result['extracted_info']
    assert not run['sources'][0]['fetched'] and run['sources'][0]['read_status']=='search_summary_fallback'
    assert run['usage']['fallback_extractions']==1 and run['usage']['original_extractions']==0

@pytest.mark.asyncio
async def test_fetch_success_never_uses_search_summary_and_still_extracts():
    outputs=[msg(None,call('search',{'query':'policy'})),msg(None,call('scrape_and_extract_info',{'source_id': 1, 'info_to_extract':'Exact rate'})),finish('Ready'),msg('Answer [1]')]
    rid,main,summary=await execute(outputs,[msg('EXTRACTED_ONLY')],web=Web(body='ENTIRE_FETCH_BODY'))
    assert store.get_run(rid)['status']=='completed'
    assert 'ENTIRE_FETCH_BODY' in json.dumps(summary.payloads)
    assert 'HIDDEN_SEARCH_SUMMARY_policy' not in json.dumps(summary.payloads)
    assert 'ENTIRE_FETCH_BODY' not in json.dumps(main.payloads) and 'EXTRACTED_ONLY' in json.dumps(main.payloads)
    result=[json.loads(r['message']['content']) for r in store.messages(rid) if r['message']['role']=='tool' and 'extracted_info' in json.loads(r['message']['content'])][-1]
    assert result['content_source']=='fetch_body' and not result['degraded']
    assert store.get_run(rid)['usage']['original_extractions']==1


def test_summary_fallback_never_crosses_index_attempt_or_run_and_is_deleted():
    rid=newrun();other=newrun()
    row=store.record_search(rid,1,1,{'query':'q'},{'results':[{'url':'https://example.org/a','summary':'A'},{'url':'https://example.org/b','summary':'B'}]})
    bindings=[{'search_response_id':row,'result_index':0}]
    assert store.search_fallback(rid,1,bindings)['text']=='A'
    assert store.search_fallback(rid,1,[{'search_response_id':row,'result_index':1}])['text']=='B'
    assert store.search_fallback(rid,1,[{'search_response_id':row,'result_index':2}]) is None
    assert store.search_fallback(rid,2,bindings) is None
    assert store.search_fallback(other,1,bindings) is None
    store.delete(store.get_run(rid)['conversation_id'])
    assert store.search_responses(rid)==[] and store.search_fallback(rid,1,bindings) is None


@pytest.mark.asyncio
async def test_extraction_model_failure_does_not_switch_to_search_summary():
    outputs=[msg(None,call('search',{'query':'policy'})),msg(None,call('scrape_and_extract_info',{'source_id': 1, 'info_to_extract':'Exact rate'})),finish('Cannot confirm'),msg('Unverified [1]')]
    rid,main,summary=await execute(outputs,[httpx.Response(400,json={'error':{'message':'context length exceeded'}})])
    assert len(summary.payloads)==1 and 'HIDDEN_SEARCH_SUMMARY_policy' not in json.dumps(summary.payloads)
    result=[json.loads(r['message']['content']) for r in store.messages(rid) if r['message']['role']=='tool' and 'extracted_info' in json.loads(r['message']['content'])][-1]
    assert not result['success'] and not result['degraded']
    assert store.get_run(rid)['usage']['fallback_extractions']==0


@pytest.mark.parametrize('content', ['SEARCH_FULL_BODY', '', '   ', None, {'not': 'text'}])
async def test_fetch_fallback_prefers_content_then_summary_with_isolated_request(content):
    class FallbackWeb(Web):
        async def search(self, *args):
            return {'results': [{'url':'https://example.org/a','title':'A','snippet':'lead',
                                 'content':content,'summary':'BACKUP_SUMMARY'}]}
        async def fetch(self, url):
            raise ProviderError('Fetch failed', code=504)
    rid, main, summary = await execute([
        msg(None, call('search', {'query':'q'})),
        msg(None, call('scrape_and_extract_info', {'source_id': 1, 'info_to_extract':'Find the date'})),
        finish(), msg('Answer [1]')], [msg('Extracted date')], web=FallbackWeb())
    assert store.get_run(rid)['status']=='completed'
    source='search_content' if content=='SEARCH_FULL_BODY' else 'search_summary'
    supplied='SEARCH_FULL_BODY' if source=='search_content' else 'BACKUP_SUMMARY'
    payload=summary.payloads[0]
    assert len(summary.payloads)==1 and len(payload['messages'])==2
    assert payload['messages'][1]['content'].endswith(supplied)
    assert source in payload['messages'][1]['content'] and 'MAIN_PRIVATE_TASK' not in json.dumps(payload)
    assert 'SEARCH_FULL_BODY' not in json.dumps(main.payloads) and 'BACKUP_SUMMARY' not in json.dumps(main.payloads)
    result=json.loads(main.payloads[2]['messages'][-1]['content'])
    assert result['degraded'] and result['content_source']==source
    assert store.get_run(rid)['sources'][0]['read_status']==source+'_fallback'
    coverage=next(e['data'] for e in store.events(rid) if e['kind']=='evidence_status')
    assert coverage['fallback_extractions']==1 and coverage['original_extractions']==0
    assert coverage[source+'_extractions']==1


def test_fallback_prefers_older_content_over_newer_summary_and_scopes_it():
    rid=newrun();bindings=[]
    for attempt,query,item in [(1,'old',{'content':'OLD_BODY','summary':'OLD_SUMMARY'}),(1,'new',{'content':'','summary':'NEW_SUMMARY'}),(2,'other',{'content':'OTHER_ATTEMPT'})]:
        row=store.record_search(rid,attempt,1,{'query':query},{'results':[{'url':'https://e.org/a',**item}]})
        bindings.append({'search_response_id':row,'result_index':0})
    fallback=store.search_fallback(rid,1,bindings)
    assert fallback['text']=='OLD_BODY' and fallback['query']=='old'
    assert store.search_fallback(newrun(),1,bindings) is None


async def test_successful_fetch_does_not_use_either_search_backup():
    class RichWeb(Web):
        async def search(self,*args):
            return {'results':[{'url':'https://example.org/a','content':'SEARCH_BODY','summary':'SEARCH_SUMMARY','snippet':'lead'}]}
    rid, main, summary=await execute([
        msg(None,call('search',{'query':'q'})),
        msg(None,call('scrape_and_extract_info',{'source_id': 1, 'info_to_extract':'date'})),
        finish(),msg('Report [1]')], [msg('Date extracted')],web=RichWeb(body='FETCH_BODY'))
    assert store.get_run(rid)['status']=='completed'
    assert summary.payloads[0]['messages'][1]['content'].endswith('FETCH_BODY')
    assert 'SEARCH_BODY' not in json.dumps(summary.payloads) and 'SEARCH_SUMMARY' not in json.dumps(summary.payloads)
    assert 'FETCH_BODY' not in json.dumps(main.payloads)


async def test_plain_text_does_not_end_research_and_finish_is_explicit():
    rid, main, _=await execute([msg('I am ready'),msg(None,call('search',{'query':'q'})),
                              finish('Enough evidence'),msg('Report [1]')])
    assert store.get_run(rid)['status']=='completed' and store.get_run(rid)['usage']['main_iterations']==3
    assert 'Plain text does not end research' in main.payloads[1]['messages'][-1]['content']
    assert all('tools' in p for p in main.payloads[:3]) and 'tools' not in main.payloads[-1]
    assert json.loads(main.payloads[-1]['messages'][-2]['content'])['next_phase']=='final'
    assert config.snapshot()['action_protocol']=='validated_source_ids_public_progress_explicit_finish'


async def test_finish_cannot_be_mixed_with_unexecuted_search_and_can_report_blocked():
    web=Web()
    end=finish('Remaining gap','blocked',['No official policy available'])['tool_calls'][0]
    rid, main, _=await execute([msg(None,call('search',{'query':'must not execute'}),end),
                              finish('Remaining gap','blocked',['No official policy available']),msg('Incomplete evidence.')], web=web)
    assert not web.searches and store.get_run(rid)['end_reason']=='model_blocked'
    assert all('validation_error' in m['content'] for m in main.payloads[1]['messages'][-2:])
    assert 'No official policy available' in json.dumps(main.payloads[-1])
    assert 'Do not claim' not in store.get_run(rid)['answer']


@pytest.mark.parametrize('args', [ {'status':'ready','summary':'x'},
    {'status':'yes','summary':'x','unresolved_questions':[]},
    {'status':'ready','summary':' ','unresolved_questions':[]},
    {'status':'ready','summary':'x','unresolved_questions':[5]} ])
def test_finish_schema_rejects_invalid_state(args):
    with pytest.raises(ValueError): parse_call(call('finish_research',args))


def test_duplicate_json_keys_rejected():
    action=call('search',{})
    action['function']['arguments']='{"query":"one","query":"two"}'
    with pytest.raises(ValueError,match='Duplicate'):parse_call(action)


def test_inline_citation_at_line_start_does_not_erase_claim():
    from app.citations import reconcile
    answer,check=reconcile('[1](https://e.org/a) supports this detailed claim.',[{'id':1,'url':'https://e.org/a'}])
    assert 'supports this detailed claim.' in answer and not any(check.values())


def test_startup_waits_for_readiness_then_opens_once_and_handles_failure():
    from scripts.open_when_ready import open_when_ready
    launched=[]; states=iter([False, True])
    assert open_when_ready(8765,1,launch=launched.append,alive=lambda:True,ready=lambda:next(states))
    assert launched==['http://127.0.0.1:8765']
    launched.clear()
    assert not open_when_ready(8765,1,launch=launched.append,alive=lambda:False,ready=lambda:True)
    assert not launched
    assert not open_when_ready(8765,1,timeout=0,launch=launched.append,alive=lambda:True,ready=lambda:False)
    assert not launched


def test_builtin_deepseek_template_has_no_credentials_and_preserves_profiles():
    original=settings_store.load()
    doc=settings_store.public(original)
    template=doc['templates']['deepseek']
    assert template['name']=='默认 DeepSeek' and template['provider']=='deepseek'
    assert template['base_url']=='https://api.deepseek.com' and template['model']=='deepseek-flash'
    assert 'api_key' not in template and 'templates' not in original
    with TestClient(__import__('app.main',fromlist=['app']).app) as client:
        assert client.get('/api/settings').json()['templates']['deepseek']==template
        created=client.post('/api/settings/profiles',json={**template,'api_key':'DUMMY_PRESET_KEY'}).json()
        assert created['settings']['active']==original['active']
        assert created['settings']['profiles'][created['id']]['configured']
        assert 'DUMMY_PRESET_KEY' not in json.dumps(created)


def test_incompatible_usage_never_breaks_model_record_and_is_not_counted():
    rid=newrun();telemetry=Telemetry(rid)
    for raw in ({'prompt_tokens':'100','completion_tokens':None,'total_tokens':-1}, ['unexpected']):
        cid=telemetry.start('main','research',1,1,{'model':'test','messages':[]})
        telemetry.end(cid,'main',{'usage':raw})
    assert telemetry.usage['main']['calls']==2
    assert telemetry.usage['main']['usage_missing_calls']==2
    assert telemetry.usage['main']['prompt_tokens']==0
    assert len([e for e in store.events(rid) if e['kind']=='model_end'])==2


def test_partial_stream_usage_survives_cancel_and_web_attempts_persist_immediately():
    rid=newrun();telemetry=Telemetry(rid)
    cid=telemetry.start('summary','page_extraction',1,1,{'model':'test','messages':[]})
    usage={'prompt_tokens':50,'completion_tokens':10,'total_tokens':60,'prompt_cache_hit_tokens':32,'prompt_cache_miss_tokens':18}
    telemetry.chunk(cid,'summary','page_extraction',[{'choices':[],'usage':usage}])
    telemetry.end(cid,'summary',error='cancelled',status='cancelled')
    assert store.requests(rid,cid)[0]['response']['usage']==usage
    assert telemetry.usage['summary']['total_tokens']==60
    telemetry.emit('web_request',service='fetch',attempt=1)
    telemetry.emit('web_request',service='fetch',attempt=2)
    assert store.get_run(rid)['usage']['fetch_http_requests']==2
    assert store.get_run(rid)['usage']['fetch_calls']==0


def test_app_shutdown_cancels_running_research_and_keeps_partial_records(monkeypatch):
    import app.main as api_module
    async def waiting_handler(request):
        await asyncio.Event().wait()
    def local_research(rid, **kwargs):
        model=ChatModel(replace(config.model_settings('main'),api_key='test-shutdown'), 'main',
                        client=httpx.AsyncClient(base_url='https://mock.invalid/',transport=httpx.MockTransport(waiting_handler)))
        return research(rid,main=model,summary=Script([]).model('summary'),web=Web())
    monkeypatch.setattr(api_module,'research',local_research)
    with TestClient(api_module.app) as client:
        cid=client.post('/api/conversations').json()['id']
        rid=client.post(f'/api/conversations/{cid}/runs',json={'question':'Shutdown test'}).json()['id']
        import time
        deadline=time.monotonic()+3
        while not store.requests(rid) and time.monotonic()<deadline:time.sleep(.01)
        assert store.requests(rid)
    assert store.get_run(rid)['status']=='cancelled'
    assert store.requests(rid)[0]['status']=='cancelled'
    assert store.messages(rid)

@pytest.mark.parametrize('saved_url', [
    'https://example.org/report.pdf#47#1',
    'https://example.org/download?u=A%2bb%3d&n=Other%2FName&empty=#3#1',
])
async def test_source_id_passes_exact_saved_url_and_bound_material(saved_url):
    class BoundWeb(Web):
        async def search(self, *args):
            return {'results':[{'title':'Original title','url':saved_url,'snippet':'lead','content':'BOUND_BODY','summary':'BOUND_SUMMARY'}]}
        async def fetch(self,url):
            self.fetches.append(url)
            raise ProviderError('fetch unavailable')
    web=BoundWeb()
    rid,main,summary=await execute([
        msg(None,call('search',{'query':'q'})),
        msg(None,call('scrape_and_extract_info',{'source_id':1,'info_to_extract':'date'})),
        finish(),msg('Answer [1]')], [msg('Extracted date')],web=web)
    assert web.fetches==[saved_url]
    assert summary.payloads[0]['messages'][1]['content'].endswith('BOUND_BODY')
    result=json.loads(main.payloads[2]['messages'][-1]['content'])
    assert result['url']==saved_url and result['source_id']==1 and result['fallback_result_index']==0
    start=next(e['data'] for e in store.events(rid) if e['kind']=='tool_start' and e['data']['tool']=='scrape_and_extract_info')
    assert 'url' not in start['model_arguments'] and start['arguments']['url']==saved_url
    assert start['arguments']['search_response_id']==result['fallback_search_response_id']


async def test_unknown_source_selection_is_feedback_without_network_or_rollback():
    web=Web()
    rid,main,summary=await execute([msg(None,call('scrape_and_extract_info',{'source_id':999,'info_to_extract':'date'})),finish(status='blocked'),msg('No verified source.')],web=web)
    assert not web.fetches and not summary.payloads
    assert json.loads(main.payloads[1]['messages'][-1]['content'])['validation_error']
    assert any(e['kind']=='tool_error' for e in store.events(rid))
    assert not any(m['rolled_back'] for m in store.messages(rid))


async def test_old_attempt_source_ids_cannot_trigger_fetch():
    from app.agent import Engine
    rid=newrun();t=Telemetry(rid);web=Web();engine=Engine(rid,None,None,web,t)
    await engine.tool('search',{'query':'q','progress':'Find'},1,1)
    result=await engine.tool('scrape_and_extract_info',{'source_id':1,'info_to_extract':'date','progress':'Read'},1,2)
    assert result['validation_error'] and not web.fetches


@pytest.mark.parametrize('args', [
    {'url':'https://example.org/a','info_to_extract':'date','progress':'Read'},
    {'source_id':1,'url':'https://evil.invalid/','info_to_extract':'date','progress':'Read'},
    {'source_id':'1','info_to_extract':'date','progress':'Read'},
    {'source_id':True,'info_to_extract':'date','progress':'Read'},
    {'source_id':1,'info_to_extract':'date','progress':''},
])
def test_reading_rejects_model_urls_invalid_ids_and_empty_public_progress(args):
    with pytest.raises(ValueError): parse_call(call('scrape_and_extract_info',args))


def test_missing_progress_is_rejected_without_invention():
    native={'type':'function','function':{'name':'search','arguments':'{"query":"q"}'}}
    with pytest.raises(ValueError,match='progress'): parse_call(native)
    with pytest.raises(ValueError): parse_call(call('search',{'query':'q','ori_question':'changed original'}))


async def test_original_question_is_program_supplied_and_progress_not_sent_to_search():
    class QuestionWeb(Web):
        async def search(self,*args): self.args=args;return await super().search(*args)
    web=QuestionWeb()
    rid,main,_=await execute([msg(None,call('search',{'query':'q','progress':'公开行动说明'})),finish(),msg('Report [1]')],web=web)
    assert web.args==('q',store.get_run(rid)['question'],10)


def test_public_content_and_provider_reasoning_are_emitted_separately():
    rid=newrun();t=Telemetry(rid)
    cid=t.start('main','research',1,1,{'model':'mock','messages':[]})
    t.chunk(cid,'main','research',[{'choices':[{'index':0,'delta':{'content':'公开进展','reasoning_content':'NOT_PUBLIC'}}]}])
    events=store.events(rid)
    assert next(e['data'] for e in events if e['kind']=='note_delta')=={'call_id':cid,'text':'公开进展'}
    assert not any(e['kind']=='model_end' for e in events)
    assert next(e['data']['text'] for e in events if e['kind']=='reasoning_delta') == 'NOT_PUBLIC'
    assert all('NOT_PUBLIC' not in json.dumps(e) for e in events if e['kind']!='reasoning_delta')


def test_rename_conversation_preserves_research_and_delete_checks_running():
    from app.main import app
    with TestClient(app) as client:
        rid=newrun();cid=store.get_run(rid)['conversation_id'];before=store.get_run(rid)
        assert client.patch('/api/conversations/'+cid,json={'title':' 新名称 '}).status_code==200
        assert client.get('/api/conversations/'+cid).json()['title']=='新名称'
        assert store.get_run(rid)==before
        assert client.patch('/api/conversations/'+cid,json={'title':'  '}).status_code==422
        assert client.patch('/api/conversations/missing',json={'title':'x'}).status_code==404
        assert client.patch('/api/conversations/'+cid,json={'title':'x'},headers={'Origin':'https://evil.invalid'}).status_code==403
        assert client.delete('/api/conversations/'+cid).status_code==409
        store.update(rid,status='completed')
        assert client.delete('/api/conversations/'+cid).status_code==200
        assert client.get('/api/conversations/'+cid).status_code==404


def test_reference_titles_and_links_are_generated_from_saved_registry():
    from app.citations import append_registered_references
    answer=append_registered_references('Fact [7]. Unknown [999]. `code [8]`',[
        {'id':7,'title':'Saved [Title]','url':'https://e.org/doc?ID=A%2bb#3#1'},
        {'id':8,'title':'Not cited','url':'https://e.org/other'}])
    assert '[7](<https://e.org/doc?ID=A%2bb#3#1>) Saved \\[Title\\] — <https://e.org/doc?ID=A%2bb#3#1>' in answer
    assert 'Not cited' not in answer and '[999](' not in answer


@pytest.mark.parametrize('length',[1,128,129,1010])
def test_search_context_boundary_preserves_original_and_uses_query_when_needed(length):
    from app.search_policy import resolve_search_context
    original='问'*length
    text,source=resolve_search_context('short query',original)
    assert (text,source)==((original,'original_question') if length<=128 else ('short query','query'))
    assert original=='问'*length
    assert resolve_search_context('short query',original,'聚焦意图')==('聚焦意图','search_intent')


def test_search_intent_schema_and_parser_agree_at_128_char_boundary():
    schema=TOOLS[0]['function']['parameters']['properties']['search_intent']
    assert schema['minLength']==1 and schema['maxLength']==128
    assert parse_call(call('search',{'query':'q','search_intent':'研'*128}))[1]['search_intent']=='研'*128
    for intent in ('研'*129,'',None,'   '):
        with pytest.raises(ValueError):parse_call(call('search',{'query':'q','search_intent':intent}))


async def test_oversize_explicit_intent_is_validation_feedback_then_corrected_without_http():
    class QuestionWeb(Web):
        async def search(self,*args):self.args=args;return await super().search(*args)
    web=QuestionWeb()
    rid,main,_=await execute([
        msg(None,call('search',{'query':'q','search_intent':'问'*129})),
        msg(None,call('search',{'query':'q','search_intent':'聚焦问题'})),finish(),msg('Report [1]')],web=web)
    assert web.searches==['q'] and web.args==('q','聚焦问题',10)
    assert '128' in main.payloads[1]['messages'][-1]['content']
    assert not any(m['rolled_back'] for m in store.messages(rid))


async def test_long_original_question_remains_full_in_main_history_with_program_resolved_search_intent():
    from app.agent import research
    class QuestionWeb(Web):
        async def search(self,*args):self.args=args;return await super().search(*args)
    original='完整任务'*252+'研究结束条件完整保留'
    rid=store.new_run(store.new_conversation(),original,config_snapshot=config.snapshot())
    main=Script([msg(None,call('search',{'query':'聚焦搜索词'})),finish(),msg('Report [1]')]);summary=Script([]);web=QuestionWeb()
    await research(rid,main=main.model('main'),summary=summary.model('summary'),web=web)
    assert store.get_run(rid)['question']==original and web.args==('聚焦搜索词','聚焦搜索词',10)
    assert all(p['messages'][1]['content']==original for p in main.payloads)
    recorded=store.search_responses(rid)[0]['arguments']
    assert recorded['ori_question']=='聚焦搜索词' and recorded['ori_question_source']=='query'
    assert not any(e['kind']=='tool_error' for e in store.events(rid))


def test_single_answer_export_contains_only_selected_answer_and_its_citations():
    from app.main import app
    with TestClient(app) as client:
        cid=store.new_conversation()
        first=store.new_run(cid,'First question',config_snapshot={})
        second=store.new_run(cid,'Second question',config_snapshot={})
        answer='## 回答一\n\n结论 [7](<https://example.org/a?x=1#part>).\n\n### 参考来源\n- [7](<https://example.org/a?x=1#part>) 官方原文\n'
        store.update(first,status='completed',answer=answer,sources=[{'id':99,'title':'Not cited','url':'https://example.org/unused'}])
        store.update(second,status='completed',answer='SECOND_ANSWER')
        response=client.get(f'/api/runs/{first}/export')
        assert response.status_code==200
        assert response.text==answer
        assert response.headers['content-type'].startswith('text/markdown')
        assert f'LucentThinker-{first}.md' in response.headers['content-disposition']
        assert 'SECOND_ANSWER' not in response.text and 'First question' not in response.text
        assert 'Not cited' not in response.text and 'Generated by' not in response.text
        whole=client.get(f'/api/conversations/{cid}/export').text
        assert answer in whole and 'SECOND_ANSWER' in whole
        assert client.get('/api/runs/missing/export').status_code==404


def test_answer_export_running_empty_and_partial_states():
    from app.main import app
    with TestClient(app) as client:
        rid=newrun()
        store.update(rid,answer='PARTIAL_OUTPUT')
        assert client.get(f'/api/runs/{rid}/export').status_code==409
        store.update(rid,status='cancelled')
        result=client.get(f'/api/runs/{rid}/export')
        assert result.text=='PARTIAL_OUTPUT' and '-partial.md' in result.headers['content-disposition']
        store.update(rid,answer=' ')
        assert client.get(f'/api/runs/{rid}/export').status_code==409


def test_shared_model_selection_is_atomic_and_preserves_provider_profiles():
    from app.main import app
    with TestClient(app) as client:
        original=settings_store.load()
        frozen=config.model_settings('main')
        pid=client.post('/api/settings/profiles',json={'name':'Shared LLM','base_url':'https://compatible.example/v1',
            'api_key':'SHARED_TEST_SECRET','model':'configured-model','concurrency':9}).json()['id']
        profiles=settings_store.load()['profiles']
        result=client.put('/api/settings/active',json={'main':pid,'summary':pid})
        assert result.status_code==200 and result.json()['active']=={'main':pid,'summary':pid}
        assert settings_store.load()['profiles']==profiles
        assert config.model_settings('main').profile_id==config.model_settings('summary').profile_id==pid
        assert config.model_settings('main').concurrency==9
        assert frozen==settings_store.to_model(original['profiles'][original['active']['main']])
        assert 'SHARED_TEST_SECRET' not in result.text
        rejected=client.put('/api/settings/active',json={'main':original['active']['main'],'summary':'missing'})
        assert rejected.status_code==422
        assert settings_store.load()['active']=={'main':pid,'summary':pid}
        assert client.put('/api/settings/active',json={'main':pid}).status_code==422
        assert client.delete(f'/api/settings/profiles/{pid}').status_code==422
        assert client.put('/api/settings/active',json=original['active']).status_code==200
        assert client.delete(f'/api/settings/profiles/{pid}').status_code==200


def test_search_count_settings_migration_validation_and_run_snapshot(monkeypatch):
    from app import main as api_module
    doc = settings_store.default_document()
    del doc['web']['search_count']
    doc['research'] = {'iteration_tier':'standard','max_iterations':50,'keep_tool_result':-1,
                       'context_compress_limit':0,'memory_mode':'strict','preset':'demo'}
    settings_store.write(doc)
    assert settings_store.load()['web']['search_count'] == 10

    async def fake_research(*args, **kwargs):
        pass
    monkeypatch.setattr(api_module, 'research', fake_research)
    with TestClient(api_module.app) as client:
        for bad in (0, -1, 1.5, True, '20', None):
            assert client.put('/api/settings/web', json={'search_count': bad}).status_code == 422
        assert settings_store.load()['web']['search_count'] == 10
        saved = client.put('/api/settings/web', json={'search_count': 25})
        assert saved.status_code == 200
        assert saved.json()['web']['search_count'] == 25
        # An older client updating credentials must not reset the saved count.
        assert client.put('/api/settings/web', json={}).json()['web']['search_count'] == 25
        cid = client.post('/api/conversations').json()['id']
        run = client.post(f'/api/conversations/{cid}/runs', json={'question': 'test'}).json()
        assert run['config_snapshot']['web']['search_count'] == 25
        search = next(t['function'] for t in run['config_snapshot']['tools'] if t['function']['name'] == 'search')
        assert 'count' not in search['parameters']['properties']
        assert '25 results' in search['description']
        client.put('/api/settings/web', json={'search_count': 30})
        assert store.get_run(run['id'])['config_snapshot']['web']['search_count'] == 25


@pytest.mark.asyncio
async def test_search_count_snapshot_controls_actual_wire_and_audit():
    from app.provider import DeepSeek
    payloads = []
    def handle(request):
        payloads.append(json.loads(request.content))
        return httpx.Response(200, json={'results': [{'url': 'https://example.org/a', 'title': 'Evidence', 'snippet': 'lead'}]})
    web = DeepSeek(api_key='fixture-web', client=httpx.AsyncClient(base_url='https://mock.invalid', transport=httpx.MockTransport(handle)))
    snapshot = config.snapshot(web={'search_count': 25})
    rid = store.new_run(store.new_conversation(), 'test question', config_snapshot=snapshot)
    settings_store.save_web({'search_count': 30})
    main = Script([msg(None, call('search', {'query': 'q', 'count': 3})), finish(), msg('Report [1]')])
    await research(rid, main=main.model('main'), summary=Script([]).model('summary'), web=web)
    assert store.get_run(rid)['status'] == 'completed'
    assert payloads[0]['count'] == 25 and payloads[0]['need_content'] is True
    assert store.search_responses(rid)[0]['arguments']['count'] == 25
    event = next(e for e in store.events(rid) if e['kind'] == 'tool_start')
    assert event['data']['arguments']['count'] == 25
    assert event['data']['model_arguments']['count'] == 3


def test_search_connection_test_uses_form_count(monkeypatch):
    from app import settings_api
    from app.main import app
    counts = []
    class TestWeb(Web):
        def __init__(self, **kwargs): super().__init__()
        async def search(self, query, question, count=10):
            counts.append(count)
            return await super().search(query, question, count)
    monkeypatch.setattr(settings_api, 'DeepSeek', TestWeb)
    with TestClient(app) as client:
        client.put('/api/settings/web', json={'search_count': 25})
        result = client.post('/api/settings/web/test/search', json={'search_count': 15}).json()
        assert result['ok'] and result['requested_count'] == 15 and result['result_count'] == 2
        client.post('/api/settings/web/test/search', json={})
        assert counts == [15, 25]
        assert settings_store.load()['web']['search_count'] == 25

@pytest.mark.asyncio
@pytest.mark.parametrize('locale', ['zh', 'en'])
async def test_selected_language_reaches_actual_main_extraction_and_final_requests(locale):
    from app.prompts import apply_language
    snapshot = config.snapshot()
    apply_language(snapshot, locale)
    outputs = [msg(None, call('search', {'query': 'evidence'})),
               msg(None, call('scrape_and_extract_info', {'source_id': 1, 'info_to_extract': 'date'})),
               msg('Public progress without a tool'), finish(), msg('Final answer [1].')]
    rid, main, summary = await execute(outputs, [msg('Extracted finding')], language=locale,
        prompt_templates=snapshot['prompt_templates'], prompt_sha256=snapshot['prompt_sha256'], tools=snapshot['tools'])
    assert store.get_run(rid)['status'] == 'completed'
    system = main.payloads[0]['messages'][0]['content']
    extraction = summary.payloads[0]['messages']
    final = main.payloads[-1]['messages'][-1]['content']
    assert extraction[0]['content'] == snapshot['prompt_templates']['extraction']
    if locale == 'zh':
        assert '你是 LucentThinker' in system
        assert '提取任务：' in extraction[1]['content']
        assert '使用简体中文' in final
        assert '研究仍在进行' in json.dumps(main.payloads[-2], ensure_ascii=False)
        assert '参考来源' in store.get_run(rid)['answer']
    else:
        assert 'Use English for public progress' in system
        assert 'INFORMATION TO EXTRACT:' in extraction[1]['content']
        assert 'Write the entire response in English' in final
        assert 'Research is still active' in json.dumps(main.payloads[-2])
        assert 'References' in store.get_run(rid)['answer']
