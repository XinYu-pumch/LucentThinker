"""Terminal-owned supervisor with portable locking and graceful pipe shutdown."""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import uuid

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app.file_lock import acquire
from scripts.open_when_ready import open_when_ready


def owned_process(pid, needle):
    """Recognize older POSIX supervisors for upgrade-time shutdown only."""
    if os.name == 'nt' or type(pid) is not int or pid <= 1:
        return False
    try:
        command = subprocess.run(['ps', '-p', str(pid), '-o', 'command='], capture_output=True,
                                 text=True, check=False).stdout.strip()
        return needle in command
    except OSError:
        return False


def running(state_dir):
    try:
        with (state_dir / 'launcher.lock').open('a+b') as lock:
            acquire(lock, exclusive=True, blocking=False)
        return False
    except BlockingIOError:
        return True
    except FileNotFoundError:
        return False


def stop_existing(state_dir=ROOT / 'data'):
    """Request shutdown using this activation's nonce, without signalling a reused PID."""
    try:
        state = json.loads((state_dir / 'launcher.json').read_text(encoding='utf-8'))
        token = str(uuid.UUID(state['token']))
        if running(state_dir):
            (state_dir / ('stop-' + token)).touch()
            return state['pid']
    except (OSError, ValueError, KeyError):
        pass
    for file, needle in [('launcher.pid', str(ROOT / 'scripts/launch.py')),
                         ('server.pid', str(ROOT / '.venv/bin/python') + ' -m uvicorn app.main:app ')]:
        try:
            pid = int((state_dir / file).read_text(encoding='utf-8'))
            if owned_process(pid, needle):
                os.kill(pid, signal.SIGTERM)
                return pid
        except (OSError, ValueError):
            pass
    return None


def run(port, state_dir, open_browser=False):
    state_dir = state_dir.resolve()
    state_dir.mkdir(parents=True, exist_ok=True)
    stopped = threading.Event()
    for name in ('SIGHUP', 'SIGINT', 'SIGTERM', 'SIGBREAK'):
        sig = getattr(signal, name, None)
        if sig is not None:
            signal.signal(sig, lambda *_: stopped.set())
    with (state_dir / 'launcher.lock').open('a+b') as lock:
        try:
            acquire(lock, exclusive=True, blocking=False)
        except BlockingIOError:
            for _ in range(40):
                try:
                    state = json.loads((state_dir / 'launcher.json').read_text(encoding='utf-8'))
                    break
                except (OSError, ValueError):
                    if stopped.wait(.1):
                        return 0
            else:
                print('Another launcher is still starting. Please retry.', flush=True)
                return 1
            print(f"Attached to LucentThinker at http://127.0.0.1:{state['port']}", flush=True)
            if open_browser:
                threading.Thread(target=open_when_ready, args=(state['port'], state['pid']), daemon=True).start()
            while running(state_dir) and not stopped.wait(.3):
                try:
                    current = json.loads((state_dir / 'launcher.json').read_text(encoding='utf-8'))
                except (OSError, ValueError):
                    return 0
                if current.get('token') != state.get('token'):
                    return 0
            if stopped.is_set():
                # This window can stop only the activation it attached to.
                token = str(uuid.UUID(state['token']))
                (state_dir / ('stop-' + token)).touch()
            return 0
        token = str(uuid.uuid4())
        request = state_dir / ('stop-' + token)
        child = None
        try:
            state = {'port': port, 'root': str(ROOT), 'pid': os.getpid(), 'token': token}
            (state_dir / 'launcher.json').write_text(json.dumps(state), encoding='utf-8')
            (state_dir / 'launcher.pid').write_text(str(os.getpid()), encoding='utf-8')
            if state_dir == ROOT / 'data':
                from dotenv import load_dotenv
                load_dotenv(ROOT / '.env')
            env = {**os.environ, 'LUCENT_DATA_DIR': str(state_dir), 'PYTHONUTF8': '1'}
            with (state_dir / 'server.log').open('a', encoding='utf-8') as log:
                child = subprocess.Popen([sys.executable, '-m', 'scripts.serve', str(port)],
                    cwd=ROOT, env=env, stdin=subprocess.PIPE, stdout=log, stderr=subprocess.STDOUT,
                    start_new_session=os.name != 'nt',
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            (state_dir / 'server.pid').write_text(str(child.pid), encoding='utf-8')
            print(f'LucentThinker → http://127.0.0.1:{port}\nClose this terminal or press Ctrl+C to exit.\nLog: {state_dir / "server.log"}', flush=True)
            if open_browser:
                threading.Thread(target=open_when_ready, args=(port, child.pid), daemon=True).start()
            while child.poll() is None and not stopped.wait(.2) and not request.exists():
                pass
            return 0 if child.poll() is None else child.returncode
        finally:
            if child:
                child.stdin.close()
                try:
                    child.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    if os.name == 'nt':
                        child.kill()
                    else:
                        os.killpg(child.pid, signal.SIGKILL)
                    child.wait()
            for name in ('launcher.pid', 'launcher.json', 'server.pid', request.name):
                (state_dir / name).unlink(missing_ok=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, required=True)
    parser.add_argument('--open', action='store_true')
    parser.add_argument('--state-dir', type=Path, default=ROOT / 'data')
    args = parser.parse_args()
    sys.exit(run(args.port, args.state_dir, args.open))
