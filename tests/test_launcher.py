import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from urllib.request import ProxyHandler, build_opener

from scripts.launch import ROOT, running, stop_existing


def wait_until(check, timeout=20):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if check():
                return
        except (OSError, ValueError):
            pass
        time.sleep(.1)
    raise AssertionError('Launcher did not reach the expected state')


def test_source_launcher_start_stop_and_restart(tmp_path):
    state = tmp_path / '中文 standalone'
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    opener = build_opener(ProxyHandler({}))
    for _ in range(2):
        command = [sys.executable, str(ROOT / 'scripts/launch.py')]
        if os.name == 'nt':
            command = ['cmd.exe', '/d', '/c', 'start.cmd', '--no-open']
        child = subprocess.Popen([*command, '--port', str(port), '--state-dir', str(state)],
                                  cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                  env={**os.environ, 'PYTHONUTF8': '1'}, text=True, encoding='utf-8')
        try:
            def ready():
                with opener.open(f'http://127.0.0.1:{port}/api/projects', timeout=1) as response:
                    return response.status == 200
            wait_until(ready)
            assert running(state)
            # Windows venv python.exe redirects to a child interpreter PID.
            owner = json.loads((state / 'launcher.json').read_text(encoding='utf-8'))['pid']
            assert stop_existing(state) == owner
            child.wait(timeout=15)
            assert child.returncode == 0, child.stdout.read()
            assert not running(state)
            assert not (state / 'server.pid').exists()
            assert (state / 'research.sqlite3').is_file()
            with socket.socket() as sock:
                assert sock.connect_ex(('127.0.0.1', port)) != 0
        finally:
            if child.poll() is None:
                stop_existing(state)
                try:
                    child.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait(timeout=5)
            child.stdout.close()
