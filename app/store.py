import json
import fcntl
import logging
import sqlite3
import time
import uuid
from contextlib import contextmanager
from .config import DATA, redact
from . import storage_codec as codec

DB = DATA / 'research.sqlite3'
DEFAULT_PROJECT_ID = 'default'

class ConversationRunningError(RuntimeError):
    pass


@contextmanager
def connect(*, exclusive=False):
    # Every connection participates in the offline migration lock. Open SQLite
    # only after acquiring it, so an atomic replacement cannot leave stale writers.
    with open(str(DB) + '.storage.lock', 'a+b') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
        db = sqlite3.connect(DB, timeout=30)
        db.row_factory = sqlite3.Row
        try:
            db.execute('PRAGMA journal_mode=WAL')
            with db:
                yield db
        finally:
            db.close()


def packed(db, value, *, split=True, force=False):
    return codec.pack(db, redact(value), split=split, force=force)

def init():
    with connect() as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS conversations(id TEXT PRIMARY KEY,title TEXT,created REAL,updated REAL);
        CREATE TABLE IF NOT EXISTS projects(id TEXT PRIMARY KEY,name TEXT NOT NULL,created REAL,updated REAL);
        CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY,conversation_id TEXT,question TEXT,status TEXT,
          answer TEXT DEFAULT '',sources TEXT DEFAULT '[]',usage TEXT DEFAULT '{}',created REAL,mode TEXT,error TEXT DEFAULT '');
        CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY AUTOINCREMENT,run_id TEXT,kind TEXT,payload TEXT);
        CREATE INDEX IF NOT EXISTS events_run ON events(run_id,id);
        CREATE TABLE IF NOT EXISTS research_messages(id INTEGER PRIMARY KEY AUTOINCREMENT,
          run_id TEXT,attempt INTEGER,purpose TEXT,message TEXT,rolled_back TEXT DEFAULT '',created REAL);
        CREATE TABLE IF NOT EXISTS model_requests(id INTEGER PRIMARY KEY AUTOINCREMENT,
          run_id TEXT,role TEXT,purpose TEXT,attempt INTEGER,iteration INTEGER,request TEXT,
          response TEXT DEFAULT '{}',status TEXT DEFAULT 'running',error TEXT DEFAULT '',created REAL,finished REAL);
        CREATE TABLE IF NOT EXISTS model_chunks(id INTEGER PRIMARY KEY AUTOINCREMENT, request_id INTEGER, payload TEXT, created REAL);
        CREATE INDEX IF NOT EXISTS chunks_request ON model_chunks(request_id,id);
        CREATE INDEX IF NOT EXISTS messages_run ON research_messages(run_id,id);
        CREATE INDEX IF NOT EXISTS requests_run ON model_requests(run_id,id);
        CREATE TABLE IF NOT EXISTS search_responses(id INTEGER PRIMARY KEY AUTOINCREMENT,
          run_id TEXT,attempt INTEGER,iteration INTEGER,arguments TEXT,response TEXT,created REAL);
        CREATE INDEX IF NOT EXISTS search_run ON search_responses(run_id,attempt,id);
        ''')
        # Additive and idempotent: legacy titles, answers and timestamps are untouched.
        db.execute('INSERT OR IGNORE INTO projects(id,name,created,updated) VALUES(?,?,?,?)',
                   (DEFAULT_PROJECT_ID, '默认项目', time.time(), time.time()))
        conversation_columns = {r['name'] for r in db.execute('PRAGMA table_info(conversations)')}
        if 'project_id' not in conversation_columns:
            db.execute("ALTER TABLE conversations ADD COLUMN project_id TEXT NOT NULL DEFAULT 'default'")
        db.execute('CREATE INDEX IF NOT EXISTS conversations_project ON conversations(project_id,updated)')
        columns = {r['name'] for r in db.execute('PRAGMA table_info(runs)')}
        for name, default in [('config_snapshot', "'{}'"), ('end_reason', "''"), ('memory_context', "'[]'")]:
            if name not in columns:
                db.execute(f'ALTER TABLE runs ADD COLUMN {name} TEXT DEFAULT {default}')
        for name in ('started_at', 'finished_at'):
            if name not in columns:
                db.execute(f'ALTER TABLE runs ADD COLUMN {name} REAL')
        db.execute('CREATE INDEX IF NOT EXISTS runs_conversation_created ON runs(conversation_id,created)')
        codec.init(db)
        db.execute("UPDATE runs SET status='interrupted',error='服务重启，研究已中断。可继续追问或重新提交。' WHERE status='running'")
        db.execute("UPDATE model_requests SET status='interrupted',error='服务重启',finished=? WHERE status='running'", (time.time(),))

def projects():
    with connect() as db:
        return [dict(row) for row in db.execute('''SELECT p.*, p.id=? AS is_default,
            (SELECT count(*) FROM conversations c WHERE c.project_id=p.id) AS conversation_count
            FROM projects p ORDER BY is_default DESC,p.created,p.id''', (DEFAULT_PROJECT_ID,))]


def new_project(name):
    name = redact(name.strip())
    if not name or len(name) > 120:
        raise ValueError('项目名称须为 1–120 个字符')
    ident, now = uuid.uuid4().hex, time.time()
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        if any(row['name'].casefold() == name.casefold() for row in db.execute('SELECT name FROM projects')):
            raise ValueError('已存在同名项目')
        db.execute('INSERT INTO projects(id,name,created,updated) VALUES(?,?,?,?)', (ident, name, now, now))
    return ident


def new_conversation(project_id=DEFAULT_PROJECT_ID):
    cid = uuid.uuid4().hex
    with connect() as db:
        if db.execute('SELECT 1 FROM projects WHERE id=?', (project_id,)).fetchone() is None:
            raise ValueError('项目不存在，请重新选择')
        db.execute('INSERT INTO conversations(id,title,created,updated,project_id) VALUES(?,?,?,?,?)',
                   (cid, '新的研究', time.time(), time.time(), project_id))
    return cid

def conversations():
    with connect() as db:
        # Only lightweight metadata; sidebar polling must not load full histories.
        return [dict(x) for x in db.execute('''SELECT c.*, r.status AS latest_status,
            r.id AS latest_run_id, COALESCE(r.started_at,r.created) AS started_at, r.finished_at
            FROM conversations c LEFT JOIN runs r ON r.id=(SELECT id FROM runs
            WHERE conversation_id=c.id ORDER BY created DESC,rowid DESC LIMIT 1)
            ORDER BY c.updated DESC''')]


def search_conversations(query='', scope='all', limit=30, offset=0):
    """Search saved titles, user questions and answers without loading audit logs."""
    if scope not in ('all', 'title', 'content'):
        raise ValueError('Unknown search scope')
    query = query.strip()
    needle = query.casefold()
    title_match = 'instr(casefold(c.title), ?) > 0'
    content_match = '''EXISTS (SELECT 1 FROM runs r WHERE r.conversation_id=c.id
        AND (instr(casefold(r.question), ?) > 0 OR instr(casefold(r.answer), ?) > 0))'''
    condition, params = {
        'title': (title_match, [needle]),
        'content': (content_match, [needle, needle]),
        'all': ('(' + title_match + ' OR ' + content_match + ')', [needle] * 3),
    }[scope]
    if not query:
        condition, params = '1=1', []
    with connect() as db:
        db.create_function('casefold', 1, lambda value: (value or '').casefold(), deterministic=True)
        rows = db.execute(f'''SELECT c.*, p.name AS project_name, p.id='default' AS project_is_default
            FROM conversations c LEFT JOIN projects p ON p.id=c.project_id WHERE {condition}
            ORDER BY c.updated DESC,c.id LIMIT ? OFFSET ?''', [*params, limit + 1, offset]).fetchall()
        results = []
        for row in rows[:limit]:
            item = dict(row)
            item.update(match_field='title', snippet='', run_id=None)
            if query and scope != 'title' and (scope == 'content' or needle not in row['title'].casefold()):
                run = db.execute('''SELECT id,question,answer FROM runs WHERE conversation_id=?
                    AND (instr(casefold(question), ?) > 0 OR instr(casefold(answer), ?) > 0)
                    ORDER BY created DESC,id LIMIT 1''', (row['id'], needle, needle)).fetchone()
                if run:
                    field = 'question' if needle in run['question'].casefold() else 'answer'
                    value = run[field]
                    # Keep Unicode case-fold expansions aligned with the original text.
                    import re
                    match = re.search(re.escape(query), value, re.IGNORECASE)
                    at = match.start() if match else 0
                    start, end = max(0, at - 70), min(len(value), at + len(query) + 170)
                    item.update(match_field=field, run_id=run['id'],
                                snippet=('…' if start else '') + value[start:end] + ('…' if end < len(value) else ''))
            results.append(item)
    return {'results': results, 'has_more': len(rows) > limit, 'next_offset': offset + len(results)}

def rename_conversation(cid, title):
    with connect() as db:
        return db.execute('UPDATE conversations SET title=?,updated=? WHERE id=?',
                          (redact(title), time.time(), cid)).rowcount > 0

def get_conversation(cid):
    with connect() as db:
        row = db.execute('SELECT * FROM conversations WHERE id=?', (cid,)).fetchone()
        if not row: return None
        result = dict(row)
        result['runs'] = [decode(x, db) for x in db.execute('SELECT * FROM runs WHERE conversation_id=? ORDER BY created', (cid,))]
        return result

def decode(row, db):
    d = dict(row)
    for key in ('sources', 'usage', 'config_snapshot', 'memory_context'):
        d[key] = codec.unpack(db, d[key])
    if d['status'] == 'completed' and d['answer'] and d['config_snapshot'].get('version', 0) >= 6:
        from .citations import refresh_registered_references
        from .prompts import reference_heading
        heading = reference_heading(d['config_snapshot'], d['question'])
        d['answer'] = refresh_registered_references(d['answer'], d['sources'], heading)
    # Old records have a known creation time, but no reliable end timestamp.
    d['started_at'] = d.get('started_at') or d['created']
    d['duration_seconds'] = max(0, d['finished_at']-d['started_at']) if d.get('finished_at') is not None else None
    return d

def get_run(rid):
    with connect() as db:
        row = db.execute('SELECT * FROM runs WHERE id=?', (rid,)).fetchone()
        return decode(row, db) if row else None

def new_run(cid, question, mode='demo', config_snapshot=None, memory_context=None):
    from .config import snapshot
    config_snapshot = config_snapshot if config_snapshot is not None else snapshot(mode)
    rid = uuid.uuid4().hex
    now = time.time()
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        if db.execute('SELECT 1 FROM conversations WHERE id=?', (cid,)).fetchone() is None:
            raise ValueError('会话已删除，请新建对话')
        db.execute('INSERT INTO runs(id,conversation_id,question,status,created,started_at,mode,config_snapshot,memory_context) VALUES(?,?,?,?,?,?,?,?,?)',
                   (rid, cid, redact(question), 'running', now, now, mode, packed(db, config_snapshot), packed(db, memory_context or [])))
        db.execute("UPDATE conversations SET title=CASE WHEN title='新的研究' THEN ? ELSE title END,updated=? WHERE id=?", (redact(question[:42]), time.time(), cid))
    return rid

def update(rid, **fields):
    allowed = {'status', 'answer', 'sources', 'usage', 'error', 'end_reason'}
    assert fields.keys() <= allowed
    with connect() as db:
        values = [packed(db, v) if isinstance(v, (list, dict)) else redact(v) for v in fields.values()]
        if fields.get('status') in ('completed', 'failed', 'cancelled', 'incomplete'):
            db.execute("UPDATE runs SET finished_at=? WHERE id=? AND status='running' AND finished_at IS NULL", (time.time(), rid))
        db.execute('UPDATE runs SET '+','.join(k+'=?' for k in fields)+' WHERE id=?', [*values, rid])

def event(rid, kind, payload):
    with connect() as db:
        db.execute('INSERT INTO events(run_id,kind,payload) VALUES(?,?,?)', (rid, kind, packed(db, payload)))

def events(rid, after=0):
    with connect() as db:
        return [{'id': r['id'], 'kind': r['kind'], 'data': codec.unpack(db, r['payload'])} for r in db.execute('SELECT * FROM events WHERE run_id=? AND id>? ORDER BY id', (rid, after))]

def reclaim_space(db):
    """Called outside a transaction, with the app's exclusive storage lock held."""
    before = db.execute('PRAGMA page_count').fetchone()[0] * db.execute('PRAGMA page_size').fetchone()[0]
    if db.execute('PRAGMA wal_checkpoint(TRUNCATE)').fetchone()[0]:
        raise sqlite3.OperationalError('数据库仍被外部连接占用')
    db.execute('VACUUM')
    if db.execute('PRAGMA wal_checkpoint(TRUNCATE)').fetchone()[0]:
        raise sqlite3.OperationalError('数据库日志仍被外部连接占用')
    after = db.execute('PRAGMA page_count').fetchone()[0] * db.execute('PRAGMA page_size').fetchone()[0]
    return {'compacted': True, 'reclaimed_bytes': max(0, before - after)}


def selected_conversations(db, identifiers, *, missing_ok=False):
    identifiers = list(dict.fromkeys(identifiers))
    if not identifiers or any(not isinstance(cid, str) or not cid for cid in identifiers):
        raise ValueError('请选择有效的对话')
    # A temporary table supports large selections without SQLite's parameter limit.
    db.execute('CREATE TEMP TABLE selected_conversations(id TEXT PRIMARY KEY)')
    db.executemany('INSERT INTO selected_conversations VALUES(?)', [(cid,) for cid in identifiers])
    count = db.execute('SELECT count(*) FROM conversations WHERE id IN (SELECT id FROM selected_conversations)').fetchone()[0]
    if missing_ok and not count:
        return 0
    if count != len(identifiers):
        raise ValueError('部分对话已不存在，请刷新后重试')
    return count


def move_conversations(identifiers, project_id):
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        if db.execute('SELECT 1 FROM projects WHERE id=?', (project_id,)).fetchone() is None:
            raise ValueError('项目不存在，请重新选择')
        count = selected_conversations(db, identifiers)
        db.execute('UPDATE conversations SET project_id=? WHERE id IN (SELECT id FROM selected_conversations)', (project_id,))
    return count


def delete(cid, *, require_stopped=False):
    return delete_conversations([cid], require_stopped=require_stopped, missing_ok=True)


def delete_conversations(identifiers, *, require_stopped=True, missing_ok=False):
    # Keep the exclusive lock through commit, VACUUM and WAL truncation. Other
    # app readers/writers wait before opening SQLite, including other deletions.
    with connect(exclusive=True) as db:
        db.execute('BEGIN IMMEDIATE')
        count = selected_conversations(db, identifiers, missing_ok=missing_ok)
        if not count:
            return None
        if require_stopped and db.execute("SELECT 1 FROM runs WHERE conversation_id IN (SELECT id FROM selected_conversations) AND status='running'").fetchone():
            raise ConversationRunningError('所选对话中有研究正在进行，请先停止后再删除')
        selected_runs = 'SELECT id FROM runs WHERE conversation_id IN (SELECT id FROM selected_conversations)'
        db.execute(f'DELETE FROM model_chunks WHERE request_id IN (SELECT id FROM model_requests WHERE run_id IN ({selected_runs}))')
        for table in ('research_messages', 'model_requests', 'search_responses'):
            db.execute(f'DELETE FROM {table} WHERE run_id IN ({selected_runs})')
        db.execute(f'DELETE FROM events WHERE run_id IN ({selected_runs})')
        db.execute('DELETE FROM runs WHERE conversation_id IN (SELECT id FROM selected_conversations)')
        db.execute('DELETE FROM conversations WHERE id IN (SELECT id FROM selected_conversations)')
        codec.collect_garbage(db)
        db.commit()  # VACUUM cannot run inside the deletion transaction.
        try:
            return reclaim_space(db)
        except sqlite3.Error:
            # Deletion is already committed. Never tell the caller it failed or
            # hide the removed conversation until a second delete is attempted.
            logging.getLogger(__name__).exception('Conversation deleted; database space reclamation failed')
            return {'compacted': False, 'reclaimed_bytes': 0,
                    'warning': '对话已删除，但磁盘空间整理未完成；下次删除对话时会再次尝试。'}


def dumps(value):
    return json.dumps(redact(value), ensure_ascii=False)


def record_search(rid, attempt, iteration, arguments, response):
    """Transport audit/failure fallback only; never automatically part of model history."""
    with connect() as db:
        cur = db.execute('INSERT INTO search_responses(run_id,attempt,iteration,arguments,response,created) VALUES(?,?,?,?,?,?)',
                         (rid, attempt, iteration, packed(db, arguments), packed(db, response), time.time()))
        return cur.lastrowid


def search_responses(rid):
    with connect() as db:
        rows = [dict(r) for r in db.execute('SELECT * FROM search_responses WHERE run_id=? ORDER BY id', (rid,))]
        for r in rows:
            for key in ('arguments', 'response'): r[key] = codec.unpack(db, r[key])
        return rows


def bound_search_items(rid, attempt, bindings):
    """Dereference program-created row/index pointers. No model URL matching."""
    items = []
    with connect() as db:
        for binding in reversed(bindings):
            row = db.execute('SELECT * FROM search_responses WHERE id=? AND run_id=? AND attempt=?',
                             (binding['search_response_id'], rid, attempt)).fetchone()
            if row is None: continue
            results = codec.unpack(db, row['response']).get('results', [])
            index = binding['result_index']
            if type(index) is not int or not 0 <= index < len(results): continue
            items.append((results[index], row['id'], index, codec.unpack(db, row['arguments'])['query']))
    return items


def search_fallback(rid, attempt, bindings):
    candidates = bound_search_items(rid, attempt, bindings)
    for field in ('content', 'summary'):
        for item, response_id, index, query in candidates:
            if isinstance(item.get(field), str) and item[field].strip():
                return {'text': item[field], 'content_source': 'search_' + field,
                        'title': item.get('title') or item['url'], 'search_response_id': response_id,
                        'result_index': index, 'query': query}
    return None


def record_message(rid, attempt, purpose, message):
    with connect() as db:
        cur = db.execute('INSERT INTO research_messages(run_id,attempt,purpose,message,created) VALUES(?,?,?,?,?)',
                         (rid, attempt, purpose, packed(db, message, force=True), time.time()))
        return cur.lastrowid


def rollback_messages(ids, reason):
    with connect() as db:
        db.executemany('UPDATE research_messages SET rolled_back=? WHERE id=?', [(reason, i) for i in ids])


def messages(rid):
    with connect() as db:
        rows = [dict(r) for r in db.execute('SELECT * FROM research_messages WHERE run_id=? ORDER BY id', (rid,))]
        for row in rows: row['message'] = codec.unpack(db, row['message'])
        return rows


def begin_request(rid, role, purpose, attempt, iteration, payload):
    with connect() as db:
        cur = db.execute('INSERT INTO model_requests(run_id,role,purpose,attempt,iteration,request,created) VALUES(?,?,?,?,?,?,?)',
                         (rid, role, purpose, attempt, iteration, packed(db, payload), time.time()))
        return cur.lastrowid


def finish_request(cid, response=None, error='', status='completed'):
    with connect() as db:
        db.execute('UPDATE model_requests SET response=?,status=?,error=?,finished=? WHERE id=?',
                   (packed(db, response or {}), status, redact(error), time.time(), cid))


def requests(rid, detail_id=None):
    with connect() as db:
        if detail_id is None:
            rows = [dict(r) for r in db.execute('SELECT id,role,purpose,attempt,iteration,status,error,created,finished FROM model_requests WHERE run_id=? ORDER BY id', (rid,))]
        else:
            rows = [dict(r) for r in db.execute('SELECT * FROM model_requests WHERE run_id=? AND id=?', (rid, detail_id))]
        for row in rows:
            for key in ('request', 'response'):
                if key in row: row[key] = codec.unpack(db, row[key])
        return rows


def append_chunks(request_id, chunks):
    with connect() as db:
        db.execute('INSERT INTO model_chunks(request_id,payload,created) VALUES(?,?,?)', (request_id,packed(db, chunks, split=False),time.time()))


def chunks(request_id):
    with connect() as db:
        return [codec.unpack(db, r['payload']) for r in db.execute('SELECT payload FROM model_chunks WHERE request_id=? ORDER BY id',(request_id,))]


def append_answer(rid, text):
    with connect() as db:
        db.execute("UPDATE runs SET answer=answer || ? WHERE id=?",(redact(text),rid))
