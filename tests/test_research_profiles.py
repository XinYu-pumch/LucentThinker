from settings_fixtures import legacy_document
import copy
import json
import stat
import os

import pytest
from fastapi.testclient import TestClient
from app import config, main, research_profiles, settings_store as settings, store


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, 'SETTINGS_FILE', tmp_path / 'settings.json')
    monkeypatch.setattr(store, 'DB', tmp_path / 'research.sqlite3')
    monkeypatch.setattr(config, 'API_KEY', '')
    monkeypatch.setattr(config, 'SECRETS', set())
    settings.write(legacy_document())
    async def fake_research(rid, **kwargs):
        store.update(rid, status='completed', answer='fixture')
    monkeypatch.setattr(main, 'research', fake_research)
    with TestClient(main.app) as c:
        yield c


def test_builtin_and_full_profile_lifecycle(client):
    doc = client.get('/api/settings').json()
    assert doc['active_research_profile'] == 'default'
    assert doc['research'] == research_profiles.DEFAULT
    assert doc['web']['search_count'] == 20
    body = {**research_profiles.DEFAULT, 'name': '快速核查', 'iteration_tier': 'quick',
            'max_iterations': 10, 'keep_tool_result': 5, 'context_compress_limit': 0,
            'memory_mode': 'followup', 'search_count': 7}
    created = client.post('/api/settings/research-profiles', json=body)
    assert created.status_code == 200
    pid = created.json()['id']
    path = '/api/settings/research-profiles/' + pid
    doc = settings.load()
    assert doc['active_research_profile'] == pid
    assert doc['research']['search_count'] == doc['web']['search_count'] == 7
    assert client.put(path, json={'search_count': 31}).status_code == 200
    assert client.patch(path, json={'name': ' 日常核查 '}).status_code == 200
    profile = settings.load()['research_profiles'][pid]
    assert profile['name'] == '日常核查' and profile['max_iterations'] == 10 and profile['search_count'] == 31
    assert client.post('/api/settings/research-profiles/default/activate').status_code == 200
    assert settings.load()['research'] == research_profiles.DEFAULT
    assert client.post(path + '/activate').json()['research']['search_count'] == 31
    assert client.delete(path).json()['active_research_profile'] == 'default'
    assert pid not in settings.load()['research_profiles']
    if os.name != 'nt':
        assert stat.S_IMODE(settings.SETTINGS_FILE.stat().st_mode) == 0o600


def test_protected_default_names_invalid_and_missing_profiles(client):
    prefix = '/api/settings/research-profiles'
    for method, body in [('put', {'search_count': 9}), ('patch', {'name': 'Changed'}), ('delete', None)]:
        args = {} if body is None else {'json': body}
        assert getattr(client, method)(prefix + '/default', **args).status_code == 422
    for name in ['', '   ', '默认配置']:
        assert client.post(prefix, json={'name': name}).status_code == 422
    assert client.post(prefix, json={'name': 'Daily'}).status_code == 200
    assert client.post(prefix, json={'name': 'daily'}).status_code == 422
    for value in [0, -1, 1.5, True, '20', None]:
        assert client.post(prefix, json={'name': 'Bad', 'search_count': value}).status_code == 422
    assert client.post(prefix, json={'name': 'Bad', 'iteration_tier': 'deep', 'max_iterations': 10}).status_code == 422
    assert client.post(prefix + '/missing/activate').status_code == 422
    assert client.put(prefix + '/missing', json={'search_count': 5}).status_code == 422
    assert settings.load()['research_profiles']['default']['search_count'] == 20


def test_migration_keeps_old_parameters_and_credentials(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, 'SETTINGS_FILE', tmp_path / 'settings.json')
    old = legacy_document()
    old['research'] = {'iteration_tier': 'custom', 'max_iterations': 357, 'keep_tool_result': 5,
                       'context_compress_limit': 0, 'memory_mode': 'followup', 'preset': 'keep5_max200'}
    old['web']['search_count'] = 17
    original = json.dumps(old)
    settings.SETTINGS_FILE.write_text(original)
    settings.ensure()
    doc = settings.load()
    assert doc['active_research_profile'] == 'legacy'
    assert doc['research'] == {**old['research'], 'search_count': 17}
    assert doc['research_profiles']['legacy']['name'] == '原研究配置'
    assert doc['research_profiles']['default']['max_iterations'] == 200
    assert doc['active'] == old['active']
    assert doc['web']['api_key'] == old['web']['api_key']
    assert [p.read_text() for p in (tmp_path / 'backups').glob('settings-v3-*')] == [original]
    settings.ensure()
    assert len(list((tmp_path / 'backups').glob('*'))) == 1


def test_snapshot_freezes_all_parameters_and_web_test_uses_active_count(client, monkeypatch):
    from app.settings_api import DeepSeek
    seen = []
    async def fake_search(self, query, question, count):
        seen.append(count)
        return {'results': [{'title': 'fixture', 'url': 'https://example.org'}]}
    monkeypatch.setattr(DeepSeek, 'search', fake_search)
    cid = client.post('/api/conversations').json()['id']
    run = client.post(f'/api/conversations/{cid}/runs', json={'question': 'test'}).json()
    snap = run['config_snapshot']
    assert snap['max_iterations'] == 200 and snap['keep_tool_result'] == -1
    assert snap['context_compress_limit'] == 5 and snap['memory_mode'] == 'strict'
    assert snap['web']['search_count'] == 20
    assert snap['research_profile'] == {'id': 'default', 'name': '默认配置'}
    assert client.post('/api/settings/research-profiles', json={'name': 'Other', 'search_count': 27}).status_code == 200
    assert client.put('/api/settings/web', json={}).json()['research']['search_count'] == 27
    assert client.post('/api/settings/web/test/search', json={}).json()['requested_count'] == 27
    assert seen == [27]
    assert store.get_run(run['id'])['config_snapshot'] == snap


def test_mask_metadata_and_independent_key_reveal(client):
    settings.save_web({'api_key': 'saved-independent-key'})
    doc = client.get('/api/settings').json()
    assert doc['web']['independent_configured'] is True
    assert 'saved-independent-key' not in json.dumps(doc)
    assert client.post('/api/settings/web/reveal?independent=true').json()['api_key'] == 'saved-independent-key'
    settings.save_web({'api_key': ''})
    assert client.get('/api/settings').json()['web']['independent_configured'] is False
