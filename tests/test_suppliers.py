"""Supplier migration and the actual model request/selection boundaries."""
from settings_fixtures import legacy_document
import asyncio
import copy
import json
import stat

import httpx
import pytest
from fastapi.testclient import TestClient

from app import config, settings_store as settings, store
from app.provider import ChatModel


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(config, 'DATA', tmp_path)
    monkeypatch.setattr(config, 'API_KEY', 'fixture-web')
    monkeypatch.setattr(config, 'SECRETS', set())
    monkeypatch.setattr(config, 'env_model_settings', lambda role: config.ModelSettings(
        model='deepseek-flash', base_url='https://api.deepseek.com',
        api_key='fixture-secret', provider='deepseek', concurrency=2 if role == 'main' else 3))
    monkeypatch.setattr(store, 'DB', tmp_path / 'research.sqlite3')
    monkeypatch.setattr(settings, 'SETTINGS_FILE', tmp_path / 'settings.json')
    monkeypatch.setattr(settings, 'DISCOVERED', {})
    store.init()


def added_supplier(name='Custom', key='fixture-custom', models=('model-a', 'model-b')):
    sid = settings.save_supplier({'name': name, 'base_url': 'https://mock.invalid/v1', 'api_key': key})
    probe = settings.supplier_profile(sid)
    settings.cache_supplier_models(sid, probe, [{'id': m} for m in models])
    return sid, settings.add_supplier_models(sid, list(models))


def test_migration_preserves_ids_credentials_and_duplicate_model_limits(tmp_path):
    old = legacy_document()
    old['profiles']['other-key'] = {**old['profiles']['main'], 'id': 'other-key', 'api_key': 'separate-secret'}
    old['profiles']['third-party'] = {**old['profiles']['main'], 'id': 'third-party', 'base_url': 'https://proxy.invalid', 'reasoning_effort': 'max'}
    original = json.dumps(old).encode()
    settings.SETTINGS_FILE.write_bytes(original)
    settings.ensure()
    backups = list((tmp_path / 'backups').glob('settings-v3-*.json'))
    assert len(backups) == 1 and backups[0].read_bytes() == original
    assert stat.S_IMODE(backups[0].stat().st_mode) == 0o600
    assert stat.S_IMODE(settings.SETTINGS_FILE.stat().st_mode) == 0o600
    new = settings.load()
    assert new['version'] == 4 and new['active'] == old['active']
    assert new['profiles'].keys() == old['profiles'].keys()
    assert len({p['supplier_id'] for p in new['profiles'].values()}) == 4
    for pid, p in old['profiles'].items():
        assert new['profiles'][pid]['api_key'] == p['api_key']
        assert new['profiles'][pid]['concurrency'] == p['concurrency']
    assert new['profiles']['third-party']['provider'] == 'openai'
    assert new['profiles']['third-party']['reasoning_effort'] is None
    settings.ensure()
    assert len(list((tmp_path / 'backups').glob('*'))) == 1


def test_credentials_owned_by_supplier_public_redacted_and_models_independent():
    sid, (a, b) = added_supplier()
    settings.update_supplier_model(sid, a, {'concurrency': 17, 'thinking': 'enabled', 'reasoning_effort': 'max'})
    settings.save_supplier({'name': 'Renamed', 'base_url': 'https://mock.invalid/v1', 'api_key': 'new-secret'}, sid)
    disk = json.loads(settings.SETTINGS_FILE.read_text())
    assert all('api_key' not in p and 'base_url' not in p for p in disk['profiles'].values())
    loaded = settings.load()
    assert loaded['profiles'][a]['api_key'] == loaded['profiles'][b]['api_key'] == 'new-secret'
    assert loaded['profiles'][a]['display_name'] == 'Renamed / model-a'
    assert loaded['profiles'][a]['supplier_id'] == sid
    assert loaded['profiles'][a]['concurrency'] == 17
    assert loaded['profiles'][b]['concurrency'] == 1
    assert loaded['profiles'][a]['thinking'] is None
    assert loaded['profiles'][a]['reasoning_effort'] is None
    public = json.dumps(settings.public())
    assert 'new-secret' not in public and 'fixture-secret' not in public
    assert 'api_key' not in public


def test_supplier_names_unique_and_connection_changes_explicit():
    sid, ids = added_supplier()
    with pytest.raises(ValueError, match='已存在'):
        settings.save_supplier({'name': 'custom'})
    with pytest.raises(ValueError, match='重新输入'):
        settings.save_supplier({'name': 'Custom', 'base_url': 'https://other.invalid'}, sid)
    settings.save_supplier({'name': 'Custom', 'base_url': 'https://other.invalid', 'api_key': ''}, sid)
    assert settings.supplier(sid)['catalog'] == []
    assert settings.load()['profiles'][ids[0]]['api_key'] == ''


def test_discovery_race_and_unknown_models_do_not_mutate_selection():
    sid, ids = added_supplier()
    assert settings.add_supplier_models(sid, ['model-a', 'model-a']) == []
    with pytest.raises(ValueError, match='已拉取列表'):
        settings.add_supplier_models(sid, ['unavailable'])
    probe = settings.supplier_profile(sid)
    settings.save_supplier({'name': 'Custom', 'base_url': probe['base_url'], 'api_key': 'changed'}, sid)
    with pytest.raises(ValueError, match='已变化'):
        settings.cache_supplier_models(sid, probe, [{'id': 'stale'}])
    assert settings.supplier(sid)['catalog'] == []
    assert set(ids).issubset(settings.load()['profiles'])


def test_delete_selected_supplier_clears_roles_and_preserves_web_key():
    sid, (a, b) = added_supplier()
    settings.select_models(a, b)
    settings.save_web({'credential_profile': a})
    settings.delete_supplier(sid)
    doc = settings.load()
    assert doc['active'] == {'main': '', 'summary': ''}
    assert settings.web_key(doc) == 'fixture-custom'
    assert doc['web']['credential_profile'] is None
    from app.main import app
    with TestClient(app) as client:
        assert client.get('/api/config').status_code == 200
        cid = client.post('/api/conversations').json()['id']
        assert client.post(f'/api/conversations/{cid}/runs', json={'question': 'hello'}).status_code == 422


def test_delete_model_is_scoped_to_supplier_and_keeps_other_models():
    sid, (a, b) = added_supplier()
    settings.select_models(a, b)
    with pytest.raises(ValueError, match='不属于'):
        settings.delete_supplier_model('builtin_deepseek', a)
    settings.delete_supplier_model(sid, a)
    assert settings.load()['active'] == {'main': '', 'summary': b}
    assert b in settings.load()['profiles']


def test_builtin_fixed_address_and_model_specific_thinking():
    settings.ensure()
    with pytest.raises(ValueError, match='固定'):
        settings.save_supplier({'name': 'DeepSeek', 'base_url': 'https://other.invalid'}, 'builtin_deepseek')
    with pytest.raises(ValueError, match='内置'):
        settings.delete_supplier('builtin_deepseek')
    pid, = settings.add_supplier_models('builtin_deepseek', ['deepseek-flash'], manual=True)
    settings.update_supplier_model('builtin_deepseek', pid, {'reasoning_effort': 'max'})
    assert settings.to_model(settings.load()['profiles'][pid]).generation()['reasoning_effort'] == 'max'
    from app.llm_providers import registry
    if 'fourrouter_argon' in registry.catalog():
        sid = 'builtin_fourrouter_argon'
        pid, = settings.add_supplier_models(sid, ['gemini-4-argon'])
        settings.update_supplier_model(sid, pid, {'reasoning_effort': 'low', 'concurrency': 7})
        model = settings.to_model(settings.load()['profiles'][pid])
        assert model.reasoning_effort == 'low' and model.concurrency == 7
        assert 'thinking' not in model.generation()
        with pytest.raises(ValueError):
            settings.update_supplier_model(sid, pid, {'reasoning_effort': 'max'})
        with pytest.raises(ValueError):
            settings.add_supplier_models(sid, ['other'])


async def test_empty_key_and_ordinary_provider_actual_wire_request():
    sid, (pid,) = added_supplier(key='', models=('model-a',))
    settings.update_supplier_model(sid, pid, {'thinking': 'enabled', 'reasoning_effort': 'max'})
    model = settings.to_model(settings.load()['profiles'][pid])
    observed = []
    def handler(request):
        assert 'authorization' not in request.headers
        if request.method == 'GET': return httpx.Response(200, json={'data': [{'id': 'model-a'}]})
        payload = json.loads(request.content)
        observed.append(payload)
        return httpx.Response(200, json={'choices': [{'message': {'role': 'assistant', 'content': 'hello'}, 'finish_reason': 'stop'}]})
    client = ChatModel(model, 'main')
    assert 'authorization' not in client.client.headers
    await client.client.aclose()
    client.client = httpx.AsyncClient(base_url=model.base_url+'/', transport=httpx.MockTransport(handler))
    try:
        assert (await client.models())['data'][0]['id'] == 'model-a'
        reply = await client.complete([{'role': 'user', 'content': 'hellow'}])
        assert reply.message['content'] == 'hello'
        assert not {'thinking', 'reasoning_effort', 'max_tokens', 'concurrency'} & observed[0].keys()
    finally:
        await client.close()


def test_supplier_api_discovery_multiselect_and_connection_test(monkeypatch):
    from app.main import app
    from app import settings_api
    seen = []
    async def models(self):
        seen.append(self.settings)
        return {'data': [{'id': 'a'}, {'id': 'b'}, {'id': 'a'}, {'bad': 'no-id'}]}
    async def run(profile, tools=False):
        seen.append(profile)
        return {'ok': True}
    monkeypatch.setattr(ChatModel, 'models', models)
    monkeypatch.setattr(settings_api, 'run_profile_test', run)
    with TestClient(app) as client:
        created = client.post('/api/settings/suppliers', json={'name': 'Anonymous', 'base_url': 'http://localhost:9999/v1', 'api_key': ''})
        assert created.status_code == 200
        sid = created.json()['id']; path = '/api/settings/suppliers/' + sid
        assert client.post(path + '/discover').json()['models'] == [{'id': 'a'}, {'id': 'b'}]
        added = client.post(path + '/models', json={'models': ['a', 'b', 'a']}).json()['added']
        assert len(added) == 2
        assert client.put(path + '/models/' + added[0], json={'concurrency': 4}).status_code == 200
        assert client.post(path + '/models/' + added[0] + '/test', json={}).json()['ok']
        assert seen[-1]['concurrency'] == 4 and seen[-1]['supplier_id'] == sid
        assert seen[0].api_key == ''
        for invalid in (0, True, '4', 2.3):
            assert client.put(path + '/models/' + added[0], json={'concurrency': invalid}).status_code == 422
        assert client.put(path + '/models/' + added[0], json={'base_url': 'https://evil.invalid'}).status_code == 422


def test_per_run_selection_snapshot_is_explicit_and_immutable(monkeypatch):
    from app import main
    sid, (a, b) = added_supplier()
    captured = {}
    async def research(rid, models, web_api_key):
        captured[rid] = models
        await asyncio.Event().wait()
    monkeypatch.setattr(main, 'research', research)
    with TestClient(main.app) as client:
        defaults = copy.deepcopy(settings.load()['active'])
        cids = [client.post('/api/conversations').json()['id'] for _ in range(2)]
        results = []
        for cid, pair in zip(cids, [(a, b), (b, a)]):
            result = client.post(f'/api/conversations/{cid}/runs', json={'question': 'test', 'main_profile': pair[0], 'summary_profile': pair[1]})
            assert result.status_code == 200
            results.append(result.json())
        assert settings.load()['active'] == defaults
        snapshot = results[0]['config_snapshot']['main_model']
        assert snapshot['supplier_id'] == sid and snapshot['profile_id'] == a
        assert snapshot['profile_name'] == 'Custom / model-a'
        assert 'fixture-custom' not in json.dumps(results)
        settings.save_supplier({'name': 'Renamed', 'base_url': 'https://mock.invalid/v1', 'api_key': 'changed-key'}, sid)
        for result, pair in zip(results, [(a, b), (b, a)]):
            rid = result['id']
            assert captured[rid]['main'].profile_id == pair[0]
            assert captured[rid]['main'].supplier_name == 'Custom'
            assert captured[rid]['summary'].profile_id == pair[1]
            assert captured[rid]['main'].api_key == 'fixture-custom'
            assert store.get_run(rid)['config_snapshot'] == result['config_snapshot']
            client.post('/api/runs/' + rid + '/cancel')


def test_fresh_install_requires_explicit_model_configuration(monkeypatch):
    from app import main

    def unexpected_environment_model(role):
        pytest.fail('Fresh settings must not import environment model profiles')

    async def fake_research(rid, **kwargs):
        store.update(rid, status='completed', answer='fixture')

    monkeypatch.setattr(config, 'env_model_settings', unexpected_environment_model)
    monkeypatch.setattr(main, 'research', fake_research)
    with TestClient(main.app) as client:
        doc = client.get('/api/config').json()['settings']
        assert doc['profiles'] == {}
        assert doc['active'] == {'main': '', 'summary': ''}
        assert 'supplier_summary' not in doc['suppliers']
        assert client.post('/api/check').status_code == 422
        cid = client.post('/api/conversations').json()['id']
        assert client.post(f'/api/conversations/{cid}/runs', json={'question': 'test'}).status_code == 422
        result = client.post('/api/settings/suppliers/builtin_deepseek/models',
                             json={'models': ['deepseek-flash'], 'manual': True})
        assert result.status_code == 200
        pid, = result.json()['added']
        settings.ensure()
        assert settings.load()['active'] == {'main': '', 'summary': ''}
        assert client.post(f'/api/conversations/{cid}/runs', json={'question': 'test'}).status_code == 422
        assert client.put('/api/settings/active', json={'main': pid, 'summary': pid}).status_code == 200
        assert client.post(f'/api/conversations/{cid}/runs', json={'question': 'test'}).status_code == 200
    with TestClient(main.app):
        assert settings.load()['active'] == {'main': pid, 'summary': pid}
        settings.delete_supplier_model('builtin_deepseek', pid)
        settings.ensure()
        assert settings.load()['profiles'] == {}
        assert settings.load()['active'] == {'main': '', 'summary': ''}
