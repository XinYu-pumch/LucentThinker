"""Offline, verified storage migration. No model calls or content truncation.

Usage: .venv/bin/python scripts/compact_storage.py [--database PATH]
The application must be stopped. A verified gzip SQLite backup is retained.
"""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app import storage_codec as codec
from app.file_lock import acquire

TABLES = ('projects', 'conversations', 'runs', 'events', 'research_messages', 'model_requests',
          'model_chunks', 'search_responses', 'sqlite_sequence')


def fingerprint(db, progress=lambda _: None):
    result = {}
    for table in TABLES:
        digest, count = hashlib.sha256(), 0
        columns = [r[1] for r in db.execute(f'PRAGMA table_info({table})')]
        if not columns:  # Older databases do not yet have project metadata.
            continue
        order = 'name' if table == 'sqlite_sequence' else 'id'
        for row in db.execute(f'SELECT * FROM {table} ORDER BY {order}'):
            values = list(row)
            for i, name in enumerate(columns):
                if name in codec.COLUMNS.get(table, ()):
                    values[i] = codec.unpack(db, values[i])
            raw = codec.serialized(values)
            digest.update(len(raw).to_bytes(8, 'big'))
            digest.update(raw)
            count += 1
        result[table] = {'rows': count, 'sha256': digest.hexdigest()}
        progress(f'校验 {table}: {count} 行')
    return result


def convert(db, progress=lambda _: None):
    codec.init(db)
    converted = {}
    for table, columns in codec.COLUMNS.items():
        fields = ','.join(columns)
        cursor = db.execute(f'SELECT id,{fields} FROM {table} ORDER BY id')
        count = 0
        while rows := cursor.fetchmany(100):
            with db:
                for row in rows:
                    new = []
                    for column, value in zip(columns, row[1:]):
                        if codec.is_reference(value):
                            new.append(value)
                        else:
                            new.append(codec.pack(db, json.loads(value), split=table != 'model_chunks',
                                                  force=table == 'research_messages'))
                    if tuple(new) != tuple(row[1:]):
                        db.execute(f'UPDATE {table} SET '+','.join(c+'=?' for c in columns)+' WHERE id=?',
                                   [*new, row[0]])
                        count += 1
        converted[table] = count
        progress(f'迁移 {table}: {count} 行')
    with db:
        # Acquire the writer lock before computing reachability.
        db.execute('BEGIN IMMEDIATE')
        codec.collect_garbage(db)
    return converted


def hash_stream(stream):
    h = hashlib.sha256()
    while data := stream.read(1024 * 1024):
        h.update(data)
    return h.hexdigest()


def compressed_backup(source, destination):
    with source.open('rb') as f:
        expected = hash_stream(f)
    with source.open('rb') as inp, destination.open('xb') as raw:
        os.chmod(destination, 0o600)
        with gzip.GzipFile(fileobj=raw, mode='wb', compresslevel=6, mtime=0) as out:
            shutil.copyfileobj(inp, out, 1024 * 1024)
        raw.flush()
        os.fsync(raw.fileno())
    with gzip.open(destination, 'rb') as check:
        if hash_stream(check) != expected:
            raise RuntimeError('备份解压后校验失败；未替换数据库')
    return expected


def assert_offline(path):
    # Old app versions do not know about the maintenance lock. Refuse their open
    # SQLite handles as well. Absence of lsof is an error, not permission to race.
    if os.name == 'nt':
        # All Windows app versions participate in the exclusive maintenance lock.
        # Windows also refuses replacement while another SQLite handle is open.
        return
    executable = shutil.which('lsof')
    if not executable:
        raise RuntimeError('需要 lsof 确认数据库未被其他进程打开')
    files = [str(p) for p in (path, Path(str(path)+'-wal'), Path(str(path)+'-shm')) if p.exists()]
    check = subprocess.run([executable, '-t', '--', *files], capture_output=True, text=True)
    if check.returncode not in (0, 1):
        raise RuntimeError('无法确认数据库是否处于离线状态')
    if check.stdout.strip():
        raise RuntimeError('请先退出 LucentThinker；数据库仍被进程占用，未进行迁移')


def migrate(path, progress=print):
    path = Path(path).resolve()
    if not path.is_file():
        raise FileNotFoundError(path)
    stamp = time.strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:8]
    backups = path.parent / 'storage-backups'
    backups.mkdir(mode=0o700, exist_ok=True)
    plain = backups / (stamp + '.sqlite3')
    backup = Path(str(plain) + '.gz')
    work = path.with_name(path.name + '.migrating-' + stamp)
    report_path = backups / (stamp + '.json')
    with open(str(path)+'.storage.lock', 'a+b') as lock:
        acquire(lock, exclusive=True, blocking=False)
        assert_offline(path)
        # Guard against writers that do not yet participate in our advisory lock.
        guard = sqlite3.connect(path, timeout=1)
        original = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)
        try:
            guard.execute('BEGIN IMMEDIATE')
            with plain.open('xb'):
                pass
            os.chmod(plain, 0o600)
            dest = sqlite3.connect(plain)
            try:
                original.backup(dest)
                dest.execute('PRAGMA journal_mode=DELETE')
            finally:
                dest.close()
            progress('一致性备份已创建，正在压缩并验证备份')
            backup_hash = compressed_backup(plain, backup)
            before_bytes = plain.stat().st_size
            shutil.copyfile(plain, work)
            os.chmod(work, 0o600)
            before = sqlite3.connect(plain.as_uri() + '?mode=ro', uri=True)
            target = sqlite3.connect(work)
            try:
                expected = fingerprint(before, progress)
                changed = convert(target, progress)
                progress('正在逐条还原迁移后的内容并校验')
                actual = fingerprint(target, progress)
                if actual != expected:
                    raise RuntimeError('内容校验不一致；未替换数据库')
                if target.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
                    raise RuntimeError('SQLite 完整性检查失败；未替换数据库')
                progress('内容校验通过，正在回收副本中的空闲页')
                target.execute('VACUUM')
                if fingerprint(target) != expected:
                    raise RuntimeError('紧凑化后内容校验失败；未替换数据库')
                objects = target.execute('SELECT count(*),sum(length(data)) FROM storage_objects').fetchone()
            finally:
                before.close()
                target.close()
            report = {'version': 1, 'database': str(path), 'backup': str(backup),
                      'backup_uncompressed_sha256': backup_hash, 'backup_bytes': backup.stat().st_size,
                      'before_bytes': before_bytes, 'after_bytes': work.stat().st_size,
                      'converted_rows': changed, 'verified_tables': actual,
                      'integrity_check': 'ok', 'objects': objects[0], 'compressed_object_bytes': objects[1]}
            # Close all source handles before replacing; clear any pre-existing WAL
            # so it can never be replayed onto the new main file.
            original.close()
            guard.rollback()
            checkpoint = guard.execute('PRAGMA wal_checkpoint(TRUNCATE)').fetchone()
            if checkpoint[0] != 0:
                raise RuntimeError('数据库仍被使用，无法安全替换')
            guard.close()
            for suffix in ('-wal', '-shm'):
                Path(str(path)+suffix).unlink(missing_ok=True)
            with work.open('rb') as f:
                os.fsync(f.fileno())
            os.replace(work, path)
            if os.name != 'nt':
                fd = os.open(path.parent, os.O_RDONLY)
                try:
                    os.fsync(fd)
                finally:
                    os.close(fd)
            report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
            os.chmod(report_path, 0o600)
            # The gzip backup was verified byte-for-byte before this temporary
            # uncompressed copy is removed. The original data remains recoverable.
            plain.unlink()
            progress(f'迁移完成：{before_bytes:,} → {report["after_bytes"]:,} bytes')
            progress(f'校验报告：{report_path}')
            return report
        finally:
            original.close()
            guard.close()
            work.unlink(missing_ok=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', type=Path, default=ROOT/'data/research.sqlite3')
    args = parser.parse_args()
    migrate(args.database, progress=lambda message: print(message, flush=True))
