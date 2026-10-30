"""Versioned, lossless JSON storage. Public store APIs still return ordinary JSON.

Large documents use compressed content-addressed objects. Message/source objects
and long strings are immutable shared leaves; manifests contain typed paths, never
markers inserted into user data. SQLite roots/edges make deletion safe across runs.
"""
import hashlib
import json
import zlib

MAGIC = b'OMTJSON\x01'
COLUMNS = {
    'runs': ('sources', 'usage', 'config_snapshot', 'memory_context'),
    'events': ('payload',),
    'research_messages': ('message',),
    'model_requests': ('request', 'response'),
    'model_chunks': ('payload',),
    'search_responses': ('arguments', 'response'),
}


class StorageCorruptionError(RuntimeError):
    pass


def serialized(value):
    # Keep dictionary order, scalar types, signed provider strings and all whitespace
    # inside text values. Only the JSON envelope's formatting is compacted.
    return json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode('utf-8')


def is_reference(value):
    return isinstance(value, bytes) and len(value) == len(MAGIC) + 32 and value.startswith(MAGIC)


def init(db):
    db.executescript('''
        CREATE TABLE IF NOT EXISTS storage_objects(
          hash BLOB PRIMARY KEY, codec INTEGER NOT NULL, raw_size INTEGER NOT NULL,
          data BLOB NOT NULL) WITHOUT ROWID;
        CREATE TABLE IF NOT EXISTS storage_edges(
          parent BLOB NOT NULL, child BLOB NOT NULL, PRIMARY KEY(parent, child)) WITHOUT ROWID;
        CREATE TABLE IF NOT EXISTS storage_roots(
          owner_table TEXT NOT NULL, owner_id TEXT NOT NULL, column_name TEXT NOT NULL,
          object_hash BLOB NOT NULL,
          PRIMARY KEY(owner_table, owner_id, column_name)) WITHOUT ROWID;
    ''')
    # Triggers also cover direct SQL deletes/updates and rolled-back transactions.
    # Names come exclusively from the fixed schema above.
    for table, columns in COLUMNS.items():
        for column in columns:
            prefix = f'storage_{table}_{column}'
            condition = (f"typeof(NEW.{column})='blob' AND length(NEW.{column})={len(MAGIC)+32} "
                         f"AND substr(NEW.{column},1,{len(MAGIC)})=X'{MAGIC.hex()}'")
            insert = (f"INSERT OR REPLACE INTO storage_roots SELECT '{table}', NEW.id, '{column}', "
                      f"substr(NEW.{column},{len(MAGIC)+1}) WHERE {condition};")
            delete = (f"DELETE FROM storage_roots WHERE owner_table='{table}' "
                      f"AND owner_id=OLD.id AND column_name='{column}';")
            db.executescript(f'''
                CREATE TRIGGER IF NOT EXISTS {prefix}_insert AFTER INSERT ON {table}
                BEGIN {insert} END;
                CREATE TRIGGER IF NOT EXISTS {prefix}_update AFTER UPDATE OF {column} ON {table}
                BEGIN {delete} {insert} END;
                CREATE TRIGGER IF NOT EXISTS {prefix}_delete AFTER DELETE ON {table}
                BEGIN {delete} END;
            ''')


class Encoder:
    def __init__(self, db):
        self.db = db

    def object(self, value, split=True):
        references = []

        def walk(node, path):
            shared = (isinstance(node, str) and len(node) >= 2048) or (
                isinstance(node, dict) and ('role' in node or 'url' in node))
            if path and shared:
                digest = self.object(node)
                references.append([path, digest.hex()])
                return None
            if isinstance(node, dict):
                return {k: walk(v, path + [k]) for k, v in node.items()}
            if isinstance(node, list):
                return [walk(v, path + [i]) for i, v in enumerate(node)]
            return node

        data = walk(value, []) if split else value
        codec = 2 if references else 1
        raw = serialized({'data': data, 'refs': references} if references else data)
        digest = hashlib.sha256(bytes([codec]) + raw).digest()
        # Compression is done only for objects not already present in this database.
        if self.db.execute('SELECT 1 FROM storage_objects WHERE hash=?', (digest,)).fetchone() is None:
            self.db.execute('INSERT OR IGNORE INTO storage_objects VALUES(?,?,?,?)',
                            (digest, codec, len(raw), zlib.compress(raw, level=6)))
            self.db.executemany('INSERT OR IGNORE INTO storage_edges VALUES(?,?)',
                                [(digest, bytes.fromhex(h)) for _, h in references])
        return digest


def pack(db, value, *, split=True, force=False):
    raw = serialized(value)
    if len(raw) < 512 and not force:
        return raw.decode('utf-8')
    return MAGIC + Encoder(db).object(value, split)


class Decoder:
    def __init__(self, db):
        self.db = db
        self.active = set()

    def object(self, digest):
        if digest in self.active:
            raise StorageCorruptionError('存储引用形成循环')
        row = self.db.execute('SELECT codec,raw_size,data FROM storage_objects WHERE hash=?', (digest,)).fetchone()
        if row is None:
            raise StorageCorruptionError('存储对象缺失：' + digest.hex())
        codec, size, data = row
        if codec not in (1, 2):
            raise StorageCorruptionError('不支持的存储对象版本')
        try:
            raw = zlib.decompress(data)
            if len(raw) != size or hashlib.sha256(bytes([codec]) + raw).digest() != digest:
                raise StorageCorruptionError('存储对象校验失败：' + digest.hex())
            document = json.loads(raw)
            if codec == 1:
                return document
            self.active.add(digest)
            try:
                value = document['data']
                for path, child in document['refs']:
                    target = value
                    for key in path[:-1]:
                        target = target[key]
                    target[path[-1]] = self.object(bytes.fromhex(child))
                return value
            finally:
                self.active.remove(digest)
        except (ValueError, KeyError, IndexError, TypeError, zlib.error) as exc:
            raise StorageCorruptionError('无法还原存储对象：' + digest.hex()) from exc

    def load(self, value):
        if is_reference(value):
            return self.object(value[len(MAGIC):])
        # Legacy TEXT and plain JSON BLOBs remain readable without migration.
        return json.loads(value)


def unpack(db, value):
    return Decoder(db).load(value)


def collect_garbage(db):
    """Run under a write transaction so no concurrent root can be lost."""
    db.execute('CREATE TEMP TABLE IF NOT EXISTS storage_live(hash BLOB PRIMARY KEY) WITHOUT ROWID')
    db.execute('DELETE FROM storage_live')
    db.execute('''WITH RECURSIVE live(hash) AS (
        SELECT object_hash FROM storage_roots
        UNION SELECT child FROM storage_edges JOIN live ON parent=live.hash
    ) INSERT INTO storage_live SELECT hash FROM live''')
    db.execute('DELETE FROM storage_edges WHERE parent NOT IN (SELECT hash FROM storage_live)')
    count = db.execute('DELETE FROM storage_objects WHERE hash NOT IN (SELECT hash FROM storage_live)').rowcount
    db.execute('DROP TABLE storage_live')
    return count
