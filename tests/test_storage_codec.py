import gzip
import hashlib
import json
import sqlite3
import base64
import random
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from app import config, storage_codec as codec, store
from scripts import compact_storage


@pytest.fixture
def database(tmp_path, monkeypatch):
    path = tmp_path / 'research.sqlite3'
    monkeypatch.setattr(store, 'DB', path)
    monkeypatch.setattr(config, 'API_KEY', '')
    monkeypatch.setattr(config, 'SECRETS', set())
    store.init()
    return path


def sample():
    return {'role': 'assistant', 'content': '完整正文\n  空格\t\x00🙂' * 600,
            'reasoning_content': '原始思考摘要' * 200,
            '_provider_native': {'protocol': 'messages', 'items': [
                {'type': 'thinking', 'thinking': '保留', 'signature': 'Signed+/=\n' * 400},
                {'type': 'redacted_thinking', 'data': 'opaque+/=' * 400}]},
            'tool_calls': [{'id': 'call1', 'function': {'name': 'search', 'arguments': '{ "query": "研究" }'}}]}


def test_lossless_shared_messages_and_native_requests(database):
    message = sample()
    sources = [{'id': 1, 'url': 'https://example.org', 'snippet': '来源正文' * 1000}]
    cid = store.new_conversation()
    rid = store.new_run(cid, '问题', config_snapshot={'version': 1})
    store.record_message(rid, 1, 'research', message)
    payload = {'model': 'native', 'messages': [message, {'role': 'user', 'content': '继续'}],
               'wire_request': {'protocol': 'messages', 'body': {'messages': [message]}},
               'literal': {'data': None, 'refs': [[['x'], 'not-a-reference']]}}
    request = store.begin_request(rid, 'main', 'research', 1, 1, payload)
    store.event(rid, 'tool_done', {'sources': sources, 'result': {'value': False, 'empty': None}})
    store.update(rid, sources=sources)
    assert store.requests(rid, request)[0]['request'] == payload
    assert store.messages(rid)[0]['message'] == message
    assert store.get_run(rid)['sources'] == sources
    assert store.events(rid)[0]['data']['sources'] == sources
    with store.connect() as db:
        root = db.execute('SELECT message FROM research_messages').fetchone()[0]
        digest = root[len(codec.MAGIC):]
        # History, normalized request and wire request refer to the exact same message.
        assert db.execute('SELECT count(*) FROM storage_objects WHERE hash=?', (digest,)).fetchone()[0] == 1
        assert db.execute('SELECT count(*) FROM storage_edges WHERE child=?', (digest,)).fetchone()[0] >= 1
        assert db.execute('SELECT count(*) FROM storage_roots').fetchone()[0] >= 4
    # Mutating a returned object cannot change any shared snapshot.
    restored = store.requests(rid, request)[0]['request']
    restored['messages'][0]['content'] = 'changed'
    assert restored['wire_request']['body']['messages'][0] == message
    assert store.requests(rid, request)[0]['request'] == payload


def test_full_stream_batches_and_partial_usage_preserved(database):
    from app.telemetry import Telemetry
    cid = store.new_conversation()
    rid = store.new_run(cid, '问题', config_snapshot={})
    t = Telemetry(rid)
    req = t.start('main', 'research', 1, 1, {'model': 'test', 'messages': []})
    chunks = [{'id': 'same-stream-id', 'object': 'chat.completion.chunk', 'model': 'test',
               'choices': [{'index': 0, 'delta': {'reasoning_content': '研'}, 'finish_reason': None}]} for _ in range(100)]
    chunks.append({'choices': [], 'usage': {'prompt_tokens': 80, 'completion_tokens': 100, 'total_tokens': 180}})
    t.chunk(req, 'main', 'research', chunks)
    t.end(req, 'main', status='cancelled')
    assert store.chunks(req) == [chunks]
    assert store.requests(rid, req)[0]['response']['usage']['total_tokens'] == 180
    with store.connect() as db:
        reference = db.execute('SELECT payload FROM model_chunks').fetchone()[0]
        compressed = db.execute('SELECT length(data) FROM storage_objects WHERE hash=?', (reference[len(codec.MAGIC):],)).fetchone()[0]
    assert compressed < len(codec.serialized(chunks)) / 10


def test_shared_objects_survive_delete_and_orphans_are_collected(database):
    ids = []
    for _ in range(2):
        cid = store.new_conversation()
        rid = store.new_run(cid, '问题', config_snapshot={})
        mid = store.record_message(rid, 1, 'research', sample())
        ids.append((cid, rid, mid))
    store.rollback_messages([ids[1][2]], '回退但保留原文')
    store.delete(ids[0][0])
    assert store.messages(ids[1][1])[0]['message'] == sample()
    assert store.messages(ids[1][1])[0]['rolled_back'] == '回退但保留原文'
    store.delete(ids[1][0])
    with store.connect() as db:
        for table in ('storage_objects', 'storage_roots', 'storage_edges'):
            assert db.execute(f'SELECT count(*) FROM {table}').fetchone()[0] == 0


def test_delete_reclaims_physical_space_and_preserves_other_research(database):
    keep = store.new_conversation()
    keep_run = store.new_run(keep, '继续运行', config_snapshot={})
    shared = sample()
    store.record_message(keep_run, 1, 'research', shared)
    remove = store.new_conversation()
    run = store.new_run(remove, '删除', config_snapshot={})
    store.record_message(run, 1, 'research', shared)
    # Incompressible synthetic stream data produces genuinely allocated pages.
    payload = base64.b64encode(random.Random(42).randbytes(2 * 1024 * 1024)).decode()
    req = store.begin_request(run, 'main', 'research', 1, 1, {'messages': []})
    store.append_chunks(req, [{'data': payload}])
    store.record_search(run, 1, 1, {'query': 'test'}, {'results': []})
    store.event(run, 'progress', {'text': 'remove'})
    store.update(run, status='completed')
    before = database.stat().st_size
    result = store.delete(remove, require_stopped=True)
    after = database.stat().st_size
    assert result['compacted'] and result['reclaimed_bytes'] == before - after
    assert before - after > 1024 * 1024
    assert store.get_conversation(remove) is None
    assert store.get_run(keep_run)['status'] == 'running'
    assert store.messages(keep_run)[0]['message'] == shared
    assert store.chunks(req) == [] and store.requests(run) == []
    assert store.events(run) == [] and store.search_responses(run) == []
    with store.connect() as db:
        assert db.execute('PRAGMA freelist_count').fetchone()[0] == 0
        assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
    wal = database.with_name(database.name + '-wal')
    assert not wal.exists() or wal.stat().st_size == 0
    assert not (database.parent / 'storage-backups').exists()
    with pytest.raises(ValueError, match='会话已删除'):
        store.new_run(remove, '不能产生孤立研究', config_snapshot={})


def test_compaction_serializes_other_writers_without_losing_data(database, monkeypatch):
    remove, keep = store.new_conversation(), store.new_conversation()
    run = store.new_run(keep, '其他研究', config_snapshot={})
    compacting, release, writer_started = threading.Event(), threading.Event(), threading.Event()
    original = store.reclaim_space
    def paused(db):
        compacting.set()
        assert release.wait(5)
        return original(db)
    def write():
        writer_started.set()
        store.event(run, 'progress', {'text': '并发流片段'})
    monkeypatch.setattr(store, 'reclaim_space', paused)
    with ThreadPoolExecutor(max_workers=2) as pool:
        deleting = pool.submit(store.delete, remove)
        try:
            assert compacting.wait(5)
            writing = pool.submit(write)
            assert writer_started.wait(5)
            assert not writing.done()
        finally:
            release.set()
        assert deleting.result(timeout=5)['compacted']
        writing.result(timeout=5)
    assert store.events(run)[0]['data'] == {'text': '并发流片段'}


def test_delete_failure_rolls_back_but_compaction_failure_reports_committed_delete(database, monkeypatch):
    cid = store.new_conversation()
    original_gc = codec.collect_garbage
    def fail_gc(db):
        raise sqlite3.OperationalError('fixture failure')
    monkeypatch.setattr(codec, 'collect_garbage', fail_gc)
    with pytest.raises(sqlite3.OperationalError):
        store.delete(cid)
    assert store.get_conversation(cid) is not None
    monkeypatch.setattr(codec, 'collect_garbage', original_gc)
    monkeypatch.setattr(store, 'reclaim_space', fail_gc)
    from app.main import delete_conversation
    result = delete_conversation(cid)
    assert result['ok'] and not result['storage_cleanup']['compacted']
    assert '对话已删除' in result['storage_cleanup']['warning']
    assert store.get_conversation(cid) is None


def test_running_guard_checked_inside_delete_transaction(database):
    from app.main import delete_conversation
    from fastapi import HTTPException
    cid = store.new_conversation()
    run = store.new_run(cid, '运行中', config_snapshot={})
    with pytest.raises(HTTPException) as error:
        delete_conversation(cid)
    assert error.value.status_code == 409
    assert store.get_run(run) is not None
    store.update(run, status='completed')
    assert delete_conversation(cid)['storage_cleanup']['compacted']
    with pytest.raises(HTTPException) as error:
        delete_conversation(cid)
    assert error.value.status_code == 404


def test_legacy_inline_and_corruption_detection(database):
    with store.connect() as db:
        assert codec.unpack(db, '{ "literal": ["OMTJSON", null, false, 1.0] }') == {'literal': ['OMTJSON', None, False, 1.0]}
        packed = codec.pack(db, sample())
        digest = packed[len(codec.MAGIC):]
        db.execute('UPDATE storage_objects SET data=? WHERE hash=?', (b'broken', digest))
        with pytest.raises(codec.StorageCorruptionError):
            codec.unpack(db, packed)
        db.execute('DELETE FROM storage_objects WHERE hash=?', (digest,))
        with pytest.raises(codec.StorageCorruptionError, match='缺失'):
            codec.unpack(db, packed)


def legacy_fixture():
    cid = store.new_conversation()
    rid = store.new_run(cid, '迁移样例', config_snapshot={'version': 1})
    source = {'id': 1, 'url': 'https://example.org', 'content': '网页原文' * 500}
    mid = store.record_message(rid, 1, 'research', sample())
    req = store.begin_request(rid, 'main', 'research', 1, 1, {'model': 'test', 'messages': [sample()]})
    chunks = [{'id': 'response', 'choices': [{'delta': {'content': '文字', 'reasoning_content': '摘要'}}]}] * 500
    store.append_chunks(req, chunks)
    store.finish_request(req, {'choices': [{'message': sample()}]}, status='failed', error='断流')
    store.record_search(rid, 1, 1, {'query': '研究'}, {'results': [source]})
    store.event(rid, 'tool_done', {'sources': [source]})
    store.update(rid, sources=[source], answer='最终回答\n\n保留所有段落。', status='completed')
    with store.connect() as db:
        for table, columns in codec.COLUMNS.items():
            rows = db.execute('SELECT id,'+','.join(columns)+' FROM '+table).fetchall()
            for row in rows:
                values = [json.dumps(codec.unpack(db, x), ensure_ascii=False) for x in row[1:]]
                db.execute('UPDATE '+table+' SET '+','.join(c+'=?' for c in columns)+' WHERE id=?', [*values, row[0]])
        codec.collect_garbage(db)
    return cid, rid, req, mid, chunks


def test_offline_migration_backup_and_all_store_apis(database, monkeypatch, tmp_path):
    cid, rid, req, mid, chunks = legacy_fixture()
    with sqlite3.connect(database) as db:
        before = compact_storage.fingerprint(db)
    # OS occupancy protection is independently exercised below; avoid requiring
    # an lsof binary on test runners for this data migration test.
    monkeypatch.setattr(compact_storage, 'assert_offline', lambda _: None)
    report = compact_storage.migrate(database, progress=lambda _: None)
    assert report['verified_tables'] == before
    assert report['after_bytes'] < report['before_bytes']
    backup = tmp_path / 'restored.sqlite3'
    with gzip.open(report['backup'], 'rb') as f:
        raw = f.read()
    assert hashlib.sha256(raw).hexdigest() == report['backup_uncompressed_sha256']
    backup.write_bytes(raw)
    with sqlite3.connect(backup) as db:
        assert compact_storage.fingerprint(db) == before
    assert store.messages(rid)[0]['message'] == sample()
    assert store.requests(rid, req)[0]['request']['messages'][0] == sample()
    assert store.chunks(req) == [chunks]
    source = store.events(rid)[0]['data']['sources'][0]
    search = store.search_responses(rid)[0]
    assert store.get_conversation(cid)['runs'][0]['sources'] == [source]
    assert store.bound_search_items(rid, 1, [{'search_response_id': search['id'], 'result_index': 0}])[0][0] == source
    assert store.search_fallback(rid, 1, [{'search_response_id': search['id'], 'result_index': 0}])['text'] == source['content']
    # A second conversion preserves identifiers, order and sqlite_sequence.
    with sqlite3.connect(database) as db:
        compact_storage.convert(db)
        assert compact_storage.fingerprint(db) == before
    store.record_message(rid, 2, 'research', {'role': 'user', 'content': '新写入'})
    assert len(store.messages(rid)) == 2


def test_migration_failure_never_replaces_original(database, monkeypatch):
    legacy_fixture()
    original = database.read_bytes()
    monkeypatch.setattr(compact_storage, 'assert_offline', lambda _: None)
    def fail(db, progress):
        db.execute("UPDATE runs SET answer='wrong'")
        db.commit()
        raise RuntimeError('injected failure')
    monkeypatch.setattr(compact_storage, 'convert', fail)
    with pytest.raises(RuntimeError, match='injected'):
        compact_storage.migrate(database, progress=lambda _: None)
    assert database.read_bytes() == original
    assert list((database.parent / 'storage-backups').glob('*.gz'))


def test_migration_refuses_shared_app_lock(database, monkeypatch):
    import fcntl
    with open(str(database)+'.storage.lock', 'a+b') as lock:
        fcntl.flock(lock, fcntl.LOCK_SH)
        with pytest.raises(BlockingIOError):
            compact_storage.migrate(database, progress=lambda _: None)


def test_object_insert_and_roots_rollback_together(database):
    before = None
    with store.connect() as db:
        before = db.execute('SELECT count(*) FROM storage_objects').fetchone()[0]
    with pytest.raises(RuntimeError):
        with store.connect() as db:
            value = codec.pack(db, sample())
            db.execute('INSERT INTO events(run_id,kind,payload) VALUES(?,?,?)', ('x', 'test', value))
            raise RuntimeError('rollback')
    with store.connect() as db:
        assert db.execute('SELECT count(*) FROM storage_objects').fetchone()[0] == before
        assert db.execute('SELECT count(*) FROM storage_roots').fetchone()[0] == 0
