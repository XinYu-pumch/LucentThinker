"""Terminal-owned service supervisor. Closing any attached launch window stops the app."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from scripts.open_when_ready import open_when_ready


def owned_process(pid, needle):
    if type(pid) is not int or pid <= 1:
        return False
    try:
        command = subprocess.run(['ps', '-p', str(pid), '-o', 'command='], capture_output=True,
                                 text=True, check=False).stdout.strip()
        return needle in command
    except OSError:
        return False


def stop_existing(state_dir=ROOT / 'data'):
    """Stop only this project's supervisor (or its legacy uvicorn process)."""
    try:
        pid = int((state_dir / 'launcher.pid').read_text())
        if owned_process(pid, str(ROOT / 'scripts/launch.py')):
            os.kill(pid, signal.SIGTERM)
            return pid
    except (OSError, ValueError):
        pass
    try:
        pid = int((state_dir / 'server.pid').read_text())
        if owned_process(pid, str(ROOT / '.venv/bin/python') + ' -m uvicorn app.main:app '):
            os.kill(pid, signal.SIGTERM)
            return pid
    except (OSError, ValueError):
        pass
    return None


def run(port, state_dir, open_browser=False):
    state_dir.mkdir(parents=True, exist_ok=True)
    stopped = threading.Event()
    for sig in (signal.SIGHUP, signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stopped.set())
    lock = (state_dir / 'launcher.lock').open('a+')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        # A second .command window attaches instead of orphaning or duplicating the server.
        owner = None
        for _ in range(40):
            try:
                candidate = int((state_dir / 'launcher.pid').read_text())
                if owned_process(candidate, str(ROOT / 'scripts/launch.py')):
                    owner = candidate
                    break
            except (OSError, ValueError):
                pass
            if stopped.wait(.1): break
        if owner is None:
            print('另一个启动进程尚未就绪，请稍后重试。', flush=True)
            return 1
        actual_port = json.loads((state_dir / 'launcher.json').read_text())['port']
        print(f'已连接运行中的 LucentThinker：http://127.0.0.1:{actual_port}\n关闭本窗口或按 Ctrl+C 也会退出整个应用。', flush=True)
        if open_browser:
            threading.Thread(target=open_when_ready, args=(actual_port, owner), daemon=True).start()
        while not stopped.wait(.3):
            if not owned_process(owner, str(ROOT / 'scripts/launch.py')): return 0
        if owned_process(owner, str(ROOT / 'scripts/launch.py')):
            os.kill(owner, signal.SIGTERM)
        return 0
    child = None
    try:
        # Publish metadata before PID so attached windows see a consistent record.
        (state_dir / 'launcher.json').write_text(json.dumps({'port':port,'root':str(ROOT)}))
        (state_dir / 'launcher.pid').write_text(str(os.getpid()))
        with (state_dir / 'server.log').open('a') as log:
            child = subprocess.Popen([str(ROOT / '.venv/bin/python'), '-m', 'uvicorn', 'app.main:app',
                '--host', '127.0.0.1', '--port', str(port), '--timeout-graceful-shutdown', '3'],
                cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        (state_dir / 'server.pid').write_text(str(child.pid))
        print(f'LucentThinker → http://127.0.0.1:{port}\n关闭此终端窗口或按 Ctrl+C 即退出应用。\n服务日志：{state_dir / "server.log"}', flush=True)
        if open_browser:
            threading.Thread(target=open_when_ready, args=(port, child.pid), daemon=True).start()
        while child.poll() is None and not stopped.wait(.2):
            pass
        return 0 if stopped.is_set() else child.returncode
    finally:
        if child and child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait()
        for name in ('launcher.pid', 'launcher.json', 'server.pid'):
            (state_dir / name).unlink(missing_ok=True)
        lock.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, required=True)
    parser.add_argument('--open', action='store_true')
    parser.add_argument('--state-dir', type=Path, default=ROOT / 'data')
    args = parser.parse_args()
    sys.exit(run(args.port, args.state_dir, args.open))
