"""Cross-process lock semantics must match on Windows and POSIX."""
import subprocess
import sys

import pytest
from app.file_lock import acquire


@pytest.mark.parametrize('exclusive', [False, True])
def test_shared_exclusive_and_crash_release(tmp_path, exclusive):
    path = tmp_path / '中文 lock'
    code = '''
import sys
from app.file_lock import acquire
with open(sys.argv[1], 'a+b') as lock:
    acquire(lock, exclusive=sys.argv[2] == 'True')
    print('locked', flush=True)
    sys.stdin.read()
'''
    child = subprocess.Popen([sys.executable, '-c', code, str(path), str(exclusive)],
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    try:
        assert child.stdout.readline().strip() == 'locked'
        with path.open('a+b') as lock:
            if exclusive:
                with pytest.raises(BlockingIOError):
                    acquire(lock, blocking=False)
            else:
                acquire(lock, blocking=False)
        with path.open('a+b') as lock:
            with pytest.raises(BlockingIOError):
                acquire(lock, exclusive=True, blocking=False)
        child.kill()
        child.wait(timeout=10)
        with path.open('a+b') as lock:
            acquire(lock, exclusive=True, blocking=False)
    finally:
        if child.poll() is None:
            child.kill()
        child.communicate(timeout=10)
