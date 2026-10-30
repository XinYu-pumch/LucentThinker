import sqlite3

import pytest
from fastapi.testclient import TestClient

from app import config, store, settings_store
from app.main import app
from scripts.compact_storage import fingerprint


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(store, 'DB', tmp_path / 'research.sqlite3')
    monkeypatch.setattr(settings_store, 'SETTINGS_FILE', tmp_path / 'settings.json')
    monkeypatch.setattr(config, 'API_KEY', '')
    monkeypatch.setattr(config, 'SECRETS', set())
    return store.DB


def test_legacy_migration_assigns_default_project_without_changing_titles_or_times(isolated):
    before = [('one', '旧对话 <标题>', 12.0, 34.0), ('two', 'Second', 56.0, 78.0)]
    with sqlite3.connect(isolated) as db:
        db.execute('CREATE TABLE conversations(id TEXT PRIMARY KEY,title TEXT,created REAL,updated REAL)')
        db.executemany('INSERT INTO conversations VALUES(?,?,?,?)', before)
    store.init()
    with store.connect() as db:
        assert [tuple(r) for r in db.execute('SELECT id,title,created,updated FROM conversations ORDER BY id')] == before
        assert {r[0] for r in db.execute('SELECT project_id FROM conversations')} == {'default'}
    assert len(store.projects()) == 1
    assert store.projects()[0]['conversation_count'] == 2
    project = store.new_project('New project')
    cid = store.new_conversation(project)
    rid = store.new_run(cid, 'Original question')
    store.update(rid, answer='Original answer', status='completed')
    store.init()
    assert store.get_conversation(cid)['project_id'] == project
    assert store.get_run(rid)['answer'] == 'Original answer'
    assert len(store.projects()) == 2
    assert store.projects()[0]['id'] == 'default'


def test_projects_api_creation_membership_counts_and_global_search(isolated):
    with TestClient(app) as client:
        default = client.post('/api/conversations').json()['id']
        assert client.get('/api/conversations/' + default).json()['project_id'] == 'default'
        created = client.post('/api/projects', json={'name': '  Battery research  '})
        assert created.status_code == 200
        pid = created.json()['id']
        cid = client.post('/api/conversations', json={'project_id': pid}).json()['id']
        store.rename_conversation(cid, 'Unique title')
        rid = store.new_run(cid, 'Question about batteries')
        store.update(rid, answer='Unique evidence', status='completed')
        assert client.get('/api/conversations/' + cid).json()['project_id'] == pid
        projects = client.get('/api/projects').json()
        assert [p['conversation_count'] for p in projects] == [1, 1]
        assert projects[1]['name'] == 'Battery research'
        hit, = client.get('/api/conversations/search', params={'q': 'Unique evidence', 'scope': 'content'}).json()['results']
        assert hit['project_id'] == pid and hit['project_name'] == 'Battery research'
        assert not hit['project_is_default']
        client.delete('/api/conversations/' + cid)
        assert client.get('/api/projects').json()[1]['conversation_count'] == 0
        assert len(client.get('/api/projects').json()) == 2


def test_invalid_names_and_missing_projects_do_not_create_orphan_conversations(isolated):
    with TestClient(app) as client:
        for name in ('', '   ', 'x' * 121):
            assert client.post('/api/projects', json={'name': name}).status_code == 422
        assert client.post('/api/projects', json={'name': 'Topic'}).status_code == 200
        assert client.post('/api/projects', json={'name': ' topic '}).status_code == 422
        assert client.post('/api/projects', json={'name': '默认项目'}).status_code == 422
        assert client.post('/api/conversations', json={'project_id': 'missing'}).status_code == 422
        assert client.get('/api/conversations').json() == []


def test_storage_maintenance_verifies_project_metadata(isolated):
    store.init()
    store.new_project('Project data survives compaction')
    with store.connect() as db:
        before = fingerprint(db)
        assert before['projects']['rows'] == 2
        db.execute("UPDATE projects SET name='changed' WHERE id!='default'")
        assert fingerprint(db)['projects']['sha256'] != before['projects']['sha256']


@pytest.mark.parametrize('default', [False, True])
def test_project_rename_preserves_membership_research_and_updates_search(isolated, default):
    with TestClient(app) as client:
        pid = 'default' if default else store.new_project('Original project')
        cid = store.new_conversation(pid)
        rid = store.new_run(cid, 'Research question')
        before = store.get_conversation(cid)
        original = next(p for p in store.projects() if p['id'] == pid)
        assert client.patch('/api/projects/' + pid, json={'name': '  Renamed 项目  '}).status_code == 200
        renamed = next(p for p in store.projects() if p['id'] == pid)
        assert renamed['name'] == 'Renamed 项目'
        assert renamed['created'] == original['created']
        assert bool(renamed['is_default']) == default
        assert store.get_conversation(cid) == before
        assert store.get_run(rid)['status'] == 'running'
        hit, = client.get('/api/conversations/search', params={'q': 'Research', 'scope': 'content'}).json()['results']
        assert hit['project_name'] == 'Renamed 项目' and hit['project_id'] == pid
        if default:
            new_cid = client.post('/api/conversations').json()['id']
            assert store.get_conversation(new_cid)['project_id'] == pid
        store.update(rid, status='completed')
        store.init()
        assert next(p for p in store.projects() if p['id'] == pid)['name'] == 'Renamed 项目'


def test_project_rename_rejects_invalid_duplicates_and_missing_ids(isolated):
    with TestClient(app) as client:
        pid = store.new_project('Topic')
        other = store.new_project('Other')
        before = store.projects()
        for name in ('', '   ', 'x' * 121, ' other ', '默认项目'):
            assert client.patch('/api/projects/' + pid, json={'name': name}).status_code == 422
            assert store.projects() == before
        assert client.patch('/api/projects/missing', json={'name': 'Missing'}).status_code == 422
        assert store.projects() == before
        assert client.patch('/api/projects/' + pid, json={'name': 'TOPIC'}).status_code == 200
        assert next(p for p in store.projects() if p['id'] == other)['name'] == 'Other'


def test_batch_move_preserves_research_and_is_atomic(isolated):
    with TestClient(app) as client:
        target = store.new_project('Destination')
        first, second = store.new_conversation(), store.new_conversation()
        rid = store.new_run(first, 'Original question')
        # Moving an active run only changes its project membership, not its context.
        before = store.get_conversation(first)
        result = client.post('/api/conversations/move', json={'ids': [first, second, first], 'project_id': target})
        assert result.json()['moved'] == 2
        after = store.get_conversation(first)
        assert after['runs'] == before['runs'] and after['updated'] == before['updated']
        assert after['project_id'] == target and store.get_run(rid)['status'] == 'running'
        for payload in ({'ids': [first, 'missing'], 'project_id': 'default'},
                        {'ids': [first], 'project_id': 'missing'}, {'ids': [], 'project_id': target}):
            assert client.post('/api/conversations/move', json=payload).status_code == 422
        assert store.get_conversation(first)['project_id'] == target
        assert store.get_conversation(second)['project_id'] == target


def test_batch_delete_refuses_entire_selection_if_any_run_is_active(isolated):
    with TestClient(app) as client:
        first, second = store.new_conversation(), store.new_conversation()
        rid = store.new_run(second, 'Running question')
        assert client.post('/api/conversations/delete', json={'ids': [first, second]}).status_code == 409
        assert store.get_conversation(first) and store.get_conversation(second)
        assert store.get_run(rid)['status'] == 'running'
        assert client.post('/api/conversations/delete', json={'ids': [first, 'missing']}).status_code == 422
        assert store.get_conversation(first)


def test_batch_delete_cleans_related_records_once_and_preserves_shared_data(isolated, monkeypatch):
    with TestClient(app) as client:
        identifiers, runs = [], []
        message = {'role': 'user', 'content': 'Shared evidence ' * 2000}
        for _ in range(3):
            cid = store.new_conversation()
            rid = store.new_run(cid, 'Question')
            store.record_message(rid, 1, 'research', message)
            store.update(rid, status='completed', answer='Saved answer')
            identifiers.append(cid)
            runs.append(rid)
        calls = []
        original = store.reclaim_space
        def reclaim(db):
            calls.append(True)
            return original(db)
        monkeypatch.setattr(store, 'reclaim_space', reclaim)
        result = client.post('/api/conversations/delete', json={'ids': identifiers[:2] + identifiers[:1]})
        assert result.status_code == 200 and result.json()['deleted'] == 2
        assert len(calls) == 1
        assert all(store.get_conversation(cid) is None for cid in identifiers[:2])
        assert all(store.get_run(rid) is None for rid in runs[:2])
        assert store.get_run(runs[2])['answer'] == 'Saved answer'
        assert store.messages(runs[2])[0]['message'] == message
        assert store.projects()[0]['conversation_count'] == 1
