import copy
import hashlib
import json

import pytest
from fastapi.testclient import TestClient

from app import config, store, settings_store
from app.main import app
from app.prompts import apply_language, final_prompt, reference_heading


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(store, 'DB', tmp_path / 'research.sqlite3')
    monkeypatch.setattr(settings_store, 'SETTINGS_FILE', tmp_path / 'settings.json')
    monkeypatch.setattr(config, 'API_KEY', '')
    monkeypatch.setattr(config, 'SECRETS', set())
    with TestClient(app) as c:
        yield c


def saved(title, question, answer):
    cid = store.new_conversation()
    store.rename_conversation(cid, title)
    rid = store.new_run(cid, question)
    store.update(rid, answer=answer, status='completed')
    return cid, rid


def test_search_scopes_all_turns_snippets_and_no_audit_leak(client):
    cid, first = saved('Battery decision', 'solar installation', 'Long intro ' * 100 + 'Bristol 35%_ [x] <script> facts')
    second = store.new_run(cid, '后续提问：郑和', config_snapshot=config.snapshot())
    store.update(second, answer='下西洋的历史资料', status='completed')
    other, _ = saved('BRISTOL city', 'unrelated', 'another answer')
    store.record_message(first, 1, 'research', {'role': 'user', 'content': 'audit-only-needle'})
    def find(q, scope='all'):
        response = client.get('/api/conversations/search', params={'q': q, 'scope': scope})
        assert response.status_code == 200
        return response.json()['results']
    assert {v['id'] for v in find('bristol')} == {cid, other}
    assert [v['id'] for v in find('bristol', 'title')] == [other]
    hit, = find('BRISTOL', 'content')
    assert hit['id'] == cid and hit['run_id'] == first and hit['match_field'] == 'answer'
    assert 'Bristol' in hit['snippet'] and len(hit['snippet']) < 260
    assert find('solar')[0]['match_field'] == 'question'
    assert find('郑和', 'content')[0]['run_id'] == second
    assert find('35%_')[0]['id'] == cid
    assert find('[x]')[0]['id'] == cid
    assert find("' OR 1=1 --") == []
    assert find('audit-only-needle') == []
    assert find('<script>')[0]['snippet'].count('<script>') == 1
    assert client.get('/api/conversations/search', params={'scope': 'logs'}).status_code == 422
    assert client.get('/api/conversations/search', params={'q': 'x' * 201}).status_code == 422


def test_search_pagination_renaming_deletion_and_unicode(client):
    ids = [saved(f'记录 {i}', 'Needle', 'Straße 中文')[0] for i in range(5)]
    pages = [client.get('/api/conversations/search', params={'q': 'needle', 'limit': 2, 'offset': offset}).json()
             for offset in (0, 2, 4)]
    assert [p['has_more'] for p in pages] == [True, True, False]
    assert {r['id'] for p in pages for r in p['results']} == set(ids)
    assert len(client.get('/api/conversations/search', params={'q': 'STRASSE'}).json()['results']) == 5
    client.patch('/api/conversations/' + ids[0], json={'title': 'renamed unique'})
    assert len(client.get('/api/conversations/search', params={'q': 'renamed unique', 'scope': 'title'}).json()['results']) == 1
    client.delete('/api/conversations/' + ids[0])
    assert client.get('/api/conversations/search', params={'q': 'renamed unique'}).json()['results'] == []


def test_prompts_follow_selected_language_and_remain_frozen(client):
    legacy = config.snapshot()
    original = copy.deepcopy(legacy)
    zh, en = copy.deepcopy(legacy), copy.deepcopy(legacy)
    apply_language(zh, 'zh')
    apply_language(en, 'en')
    assert legacy == original
    assert '你是 LucentThinker' in zh['prompt_templates']['main']
    assert '简体中文' in zh['prompt_templates']['extraction']
    assert 'English' in en['prompt_templates']['main']
    assert 'in English' in en['prompt_templates']['extraction']
    assert 'Write the entire response in English' in final_prompt(en['prompt_templates'], '一个中文问题')
    assert '使用简体中文' in final_prompt(zh['prompt_templates'], 'An English question')
    assert reference_heading(en, '一个中文问题') == 'References'
    assert reference_heading(zh, 'An English question') == '参考来源'
    for snap in (zh, en):
        for name, value in snap['prompt_templates'].items():
            assert hashlib.sha256(value.encode()).hexdigest() == snap['prompt_sha256'][name]
        assert set(json.loads(snap['prompt_templates']['control'])) >= {'iteration_limit', 'model_blocked'}
    cid = store.new_conversation()
    rid = store.new_run(cid, '中文问题', config_snapshot=en)
    en['prompt_templates']['main'] = 'later changes'
    assert store.get_run(rid)['config_snapshot']['prompt_templates']['main'] != 'later changes'


@pytest.mark.parametrize('locale', ['zh', 'en'])
def test_api_language_reaches_run_snapshot(client, monkeypatch, locale):
    import app.main as server
    async def no_network(rid, **kwargs):
        store.update(rid, status='completed', answer='fixture answer')
    monkeypatch.setattr(server, 'research', no_network)
    # Use the actual settings workflow; all credentials and data are isolated fixtures.
    result = client.post('/api/settings/profiles', json={'name': 'Fixture', 'model': 'fixture-model',
        'provider': 'openai', 'base_url': 'https://fixture.invalid/v1', 'api_key': 'fixture-key'}).json()
    cid = client.post('/api/conversations').json()['id']
    response = client.post(f'/api/conversations/{cid}/runs', json={
        'question': '我的问题', 'main_profile': result['id'], 'summary_profile': result['id'], 'language': locale})
    assert response.status_code == 200, response.text
    snap = response.json()['config_snapshot']
    assert snap['language'] == locale
    assert snap['prompt_templates']['response_language'] == ('English' if locale == 'en' else '简体中文')
    assert client.post(f'/api/conversations/{cid}/runs', json={'question': 'x', 'language': 'xx'}).status_code == 422
