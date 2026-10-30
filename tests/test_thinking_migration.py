"""Protocol and persistence contracts for the ScholarNoteLM thinking migration."""
import copy
import json
from dataclasses import replace

import httpx
import pytest
from fastapi.testclient import TestClient

from app import config, settings_store, store, llm_thinking, llm_protocols
from app.llm_diagnostics import negative_probe
from app.llm_providers import registry
from app.provider import ChatModel, ProviderError
from test_optional_providers import response


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(config, 'DATA', tmp_path)
    monkeypatch.setattr(config, 'API_KEY', '')
    monkeypatch.setattr(config, 'SECRETS', set())
    monkeypatch.setattr(settings_store, 'SETTINGS_FILE', tmp_path / 'settings.json')
    monkeypatch.setattr(settings_store, 'DISCOVERED', {})
    monkeypatch.setattr(store, 'DB', tmp_path / 'research.sqlite3')
    store.init()


def cfg(preset, level=None, output=None, **kwargs):
    selected = llm_thinking.initial(preset)
    if level is not None: selected['level'] = level
    if output is not None: selected['output'] = output
    return config.ModelSettings(model='fixture-model', base_url='https://relay.invalid/prefix/v1', api_key='secret',
                                thinking_config=selected, request_attempts=1, **kwargs)


@pytest.mark.parametrize('preset,level', [(p['id'], level) for p in llm_thinking.PRESETS.values() for level in p['levels']])
def test_all_preset_choices_build_exclusive_protocol_parameters(preset, level):
    settings = cfg(preset, level, temperature=.7)
    spec = llm_thinking.PRESETS[preset]
    if level == 'budget':
        settings = replace(settings, thinking_config={**settings.thinking_config, 'budget': spec['budget']['min']})
    plan = llm_thinking.prepare(settings, {'messages': [{'role': 'user', 'content': 'hello'}]}, 'session')
    body = plan['body']
    assert 'relay.invalid/prefix/' in plan['url']
    assert 'x-opencode-session' not in plan['headers']
    assert plan['protocol'] == spec['protocol']
    assert 'max_tokens' not in body or spec['protocol'] == 'messages'
    if spec.get('omitTemperature'): assert 'temperature' not in body
    if level == 'budget':
        assert body['thinking_budget'] == 0 and 'reasoning_effort' not in body
    elif spec['protocol'] != 'google':
        for key, value in spec['options'][level].items():
            if key == 'thinking':
                assert all(body[key][k] == v for k, v in value.items())
            else: assert body[key] == value


@pytest.mark.parametrize('value', [False, {}, {'preset': 'removed'}, {'preset': []},
    {'preset': 'qwen_openai', 'level': 'budget', 'budget': True},
    {'preset': 'qwen_openai', 'level': 'budget', 'budget': -1},
    {'preset': 'qwen_openai', 'level': 'budget', 'budget': 262145},
    {'preset': 'gpt6_astra_chat', 'level': 'none'},
    {'preset': 'grok47_responses', 'output': 'summary'}])
def test_invalid_presets_rejected(value):
    with pytest.raises(ValueError): llm_thinking.selection(value)


@pytest.mark.parametrize('preset', ['gemini4_native', 'claude55_messages'])
def test_output_off_does_not_turn_off_thinking(preset):
    plan = llm_thinking.prepare(cfg(preset, output='off'), {'messages': []})
    if preset == 'gemini4_native':
        assert plan['body']['generationConfig']['thinkingConfig'] == {'thinkingLevel': 'medium', 'includeThoughts': False}
    else:
        assert plan['body']['thinking'] == {'type': 'adaptive', 'display': 'omitted'}


@pytest.mark.parametrize('preset', ['gemini4_native', 'claude55_messages', 'grok47_responses', 'qwen_openai'])
@pytest.mark.parametrize('stream', [True, False])
@pytest.mark.parametrize('role', ['main', 'summary'])
async def test_ordinary_presets_roundtrip_tools_and_signed_state(preset, stream, role):
    settings = cfg(preset)
    protocol = llm_thinking.PRESETS[preset]['protocol']
    seen = []
    def handler(req):
        seen.append(req)
        return response(protocol, 'first' if len(seen) == 1 else 'done',
                        [('search', {'query': 'x'})] if len(seen) == 1 else [], stream=stream)
    client = ChatModel(settings, role, client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    messages = [{'role': 'system', 'content': 'system'}, {'role': 'user', 'content': 'question'}]
    tools = [{'type': 'function', 'function': {'name': 'search', 'parameters': {'type': 'object', 'properties': {}}}}]
    try:
        first = await client.complete(messages, tools)
        assert first.finish_reason == 'tool_calls'
        follow = await client.complete([*messages, first.message, {'role': 'tool', 'tool_call_id': first.message['tool_calls'][0]['id'], 'content': 'RESULT'}])
        assert follow.message['content'] == 'done'
        wire = seen[1].content.decode()
        assert 'RESULT' in wire
        if protocol != 'chat': assert 'SIGNED_' in wire
        assert all('x-opencode-session' not in req.headers for req in seen)
        if protocol == 'messages': assert seen[0].headers['x-api-key'] == 'secret'
    finally: await client.close()


def test_responses_summary_delta_done_final_dedup_and_null_usage():
    decoder = llm_protocols.Decoder('responses', 'x')
    parts = [decoder.decode({'type': 'response.reasoning_summary_text.delta', 'output_index': 0, 'summary_index': 0, 'delta': 'abc'}),
             decoder.decode({'type': 'response.reasoning_summary_text.done', 'output_index': 0, 'summary_index': 0, 'text': 'abcdef'}),
             decoder.decode({'object': 'response', 'status': 'completed', 'output': [
                 {'type': 'reasoning', 'summary': [{'type': 'summary_text', 'text': 'abcdef'}, {'type': 'summary_text', 'text': 'second'}], 'content': None, 'encrypted_content': 'HIDDEN'},
                 {'type': 'message', 'content': [{'type': 'output_text', 'text': 'answer'}]}],
                 'usage': {'input_tokens_details': None, 'output_tokens_details': {'reasoning_tokens': 12}}})]
    assert ''.join(p['choices'][0]['delta']['reasoning_content'] for p in parts) == 'abcdefsecond'
    result = decoder.result()
    assert result['choices'][0]['message']['reasoning_content'] == 'abcdefsecond'
    assert result['usage']['completion_tokens_details']['reasoning_tokens'] == 12
    assert 'HIDDEN' not in result['choices'][0]['message']['content']


def test_responses_reasoning_text_repeated_as_final_summary_is_not_duplicated():
    d = llm_protocols.Decoder('responses', 'x')
    d.decode({'type': 'response.reasoning_text.delta', 'output_index': 0, 'delta': 'abc'})
    d.decode({'object': 'response', 'status': 'completed', 'output': [
        {'type': 'reasoning', 'summary': [{'type': 'summary_text', 'text': 'abc'}], 'content': None}]})
    assert d.result()['choices'][0]['message']['reasoning_content'] == 'abc'


def test_chat_reasoning_aliases_and_encrypted_details():
    raw = {'choices': [{'delta': {'reasoning_details': [
        {'type': 'reasoning.encrypted', 'text': 'HIDDEN'}, {'type': 'reasoning.text', 'text': 'shown'}], 'content': 'answer'}}]}
    normalized = llm_protocols.normalize_chat(raw)
    assert normalized['choices'][0]['delta']['reasoning_content'] == 'shown'
    assert 'reasoning_content' not in raw['choices'][0]['delta']


def test_google_signed_empty_chunks_are_preserved_without_invalid_parts():
    d = llm_protocols.Decoder('google', 'x')
    d.decode({'candidates': [{'content': {'parts': [{'text': 'summary', 'thought': True}]}}]})
    d.decode({'candidates': [{'content': {'parts': [{'thoughtSignature': 'SIGN'}, {'text': ''}]}, 'finishReason': 'STOP'}]})
    m = d.result()['choices'][0]['message']
    assert m['reasoning_content'] == 'summary'
    assert m['_provider_native']['items'] == [{'text': 'summary', 'thought': True, 'thoughtSignature': 'SIGN'}]


GO = registry.get('opencode_go')


@pytest.mark.parametrize('model,level', [(model, level) for model, spec in GO.MANIFEST['models'].items()
                                       for level in ['', *spec.get('reasoning', {}).get('options', {})]])
def test_go_reviewed_choices_and_output_policy(model, level):
    settings = config.ModelSettings(model=model, provider='opencode_go', base_url=GO.BASE, api_key='',
                                    go_reasoning=level, reasoning_budget=1024 if level == 'budget' else None)
    spec = GO.route(model)
    plan = GO.prepare(settings, {'messages': []}, 'fixture-session')
    body = plan['body']
    assert plan['headers']['x-opencode-session'] == 'fixture-session'
    if level == 'budget':
        assert body['thinking']['budget_tokens'] == 1024 and 'output_config' not in body
    if model == 'glm-5.3-flash': assert 'thinking' not in body
    if level == 'disabled' and model == 'claude-haiku-5-5': assert body['thinking'] == {'type': 'disabled'}
    if model.startswith(('gpt-', 'muse-')): assert body['reasoning']['summary'] == 'auto'
    if spec['protocol'] == 'google': assert body['generationConfig']['thinkingConfig']['includeThoughts'] is True
    if spec['protocol'] != 'messages': assert 'max_tokens' not in body


def test_go_budget_ranges_differ_from_ordinary_qwen():
    with pytest.raises(ValueError): GO.validate_choice('qwen3.8-max', 'budget', 0)
    with pytest.raises(ValueError): GO.validate_choice('qwen3.8-max', 'budget', 262145)
    GO.validate_choice('qwen3.8-flash', 'budget', 999999)
    with pytest.raises(ValueError): GO.validate_choice('mimo-v2.6-flash', 'disabled', None)


def test_settings_roundtrip_defaults_explicit_reset_and_backup(tmp_path):
    settings_store.ensure()
    sid = 'builtin_qwen'
    pid, = settings_store.add_supplier_models(sid, ['qwen3.8-flash'], manual=True)
    p = settings_store.load()['profiles'][pid]
    assert p['thinking_config'] == llm_thinking.initial('qwen_openai')
    settings_store.update_supplier_model(sid, pid, {'thinking_config': None})
    settings_store.update_supplier_model(sid, pid, {'concurrency': 5})
    assert settings_store.load()['profiles'][pid]['thinking_config'] is None
    selected = {'preset': 'qwen_openai', 'level': 'budget', 'budget': 0}
    settings_store.update_supplier_model(sid, pid, {'thinking_config': selected})
    settings_store.select_models(pid, pid)
    for role in ('main', 'summary'):
        assert config.model_settings(role).thinking_config['budget'] == 0
    disk = json.loads(settings_store.SETTINGS_FILE.read_text())
    assert 'api_key' not in disk['profiles'][pid]
    disk.pop('thinking_schema')
    settings_store.SETTINGS_FILE.write_text(json.dumps(disk))
    before = settings_store.SETTINGS_FILE.read_bytes()
    settings_store.ensure()
    assert list((tmp_path / 'backups').glob('*.json'))[0].read_bytes() == before
    assert settings_store.load()['active'] == {'main': pid, 'summary': pid}


def test_official_hosts_and_cross_provider_config_rejected():
    settings_store.save_supplier({'base_url': 'https://api.z.ai/api/paas/v4', 'api_key': 'secret'}, 'builtin_z_ai')
    with pytest.raises(ValueError): settings_store.save_supplier({'base_url': 'https://evil.invalid', 'api_key': ''}, 'builtin_z_ai')
    p = {'name': 'x', 'provider': 'deepseek', 'base_url': 'https://api.deepseek.com', 'model': 'deepseek-flash',
         'thinking_config': llm_thinking.initial('qwen_openai')}
    with pytest.raises(ValueError): settings_store.validated_profile(p)


@pytest.mark.parametrize('status,detail,expected', [(200, '', 'possibly_ignored'), (422, 'reasoning_effort invalid', 'validated'),
    (400, 'unrelated schema error', 'inconclusive'), (401, 'reasoning_effort invalid', 'inconclusive')])
async def test_negative_probe_never_mutates_settings(status, detail, expected):
    settings = cfg('gpt6_astra_chat')
    saved = copy.deepcopy(settings.thinking_config)
    seen = []
    def handler(request):
        seen.append(json.loads(request.content))
        return response('chat', 'ok') if status == 200 else httpx.Response(status, json={'error': {'message': detail}})
    client = ChatModel(settings, 'main', client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    try:
        result = await negative_probe(client, {'reasoning_effort': 'high'}, [{'role': 'user', 'content': 'hello'}])
        assert result['status'] == expected
        assert seen[0]['reasoning_effort'] == '__invalid_probe__'
        assert settings.thinking_config == saved
    finally: await client.close()


def test_snapshot_and_audit_redact_native_auth():
    settings = cfg('claude55_messages')
    config.register_secret(settings.api_key)
    wire = llm_thinking.prepare(settings, {'messages': []})
    redacted = config.redact(wire)
    assert 'x-api-key' not in redacted['headers']
    assert 'secret' not in json.dumps(redacted)


@pytest.mark.parametrize('selected,provider', [({}, 'openai'), (llm_thinking.initial('qwen_openai'), 'opencode_go')])
async def test_direct_model_cannot_bypass_thinking_validation(selected, provider):
    sent = []
    settings = config.ModelSettings(model='deepseek-v4.1-flash', provider=provider,
        base_url=GO.BASE, api_key='', thinking_config=selected)
    client = ChatModel(settings, 'main', client=httpx.AsyncClient(transport=httpx.MockTransport(lambda r: sent.append(r))))
    try:
        with pytest.raises(ProviderError): await client.complete([{'role': 'user', 'content': 'hi'}])
        assert not sent
    finally: await client.close()


def test_public_snapshot_describes_actual_protocol_and_omitted_temperature():
    public = cfg('claude55_messages', output='off', temperature=.8).public()
    assert public['protocol'] == 'messages'
    assert public['generation_parameters']['thinking']['display'] == 'omitted'
    assert 'temperature' not in public['generation_parameters']
    assert 'secret' not in json.dumps(public)
