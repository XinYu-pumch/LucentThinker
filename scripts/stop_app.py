"""Stop the project-owned application and wait until it exits."""
import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.launch import ROOT, stop_existing, owned_process

pid = stop_existing()
if pid is None:
    print('LucentThinker 没有在运行。')
    sys.exit(0)
for _ in range(80):
    if not (owned_process(pid, str(ROOT / 'scripts/launch.py')) or
            owned_process(pid, str(ROOT / '.venv/bin/python') + ' -m uvicorn app.main:app ')):
        print('LucentThinker 已退出。')
        break
    time.sleep(.2)
else:
    print('已请求退出，服务仍在停止；请检查 data/server.log。')
    sys.exit(1)
