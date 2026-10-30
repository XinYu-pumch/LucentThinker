"""Open the local application once ready; never use a system proxy for localhost."""
import os
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import ProxyHandler, build_opener


def open_when_ready(port, pid, *, timeout=180, launch=None, alive=None, ready=None):
    url = f'http://127.0.0.1:{int(port)}'
    opener = build_opener(ProxyHandler({}))

    def process_alive():
        try:
            os.kill(int(pid), 0)
            return True
        except ProcessLookupError:
            return False

    def application_ready():
        try:
            with opener.open(url + '/', timeout=1) as response:
                return response.status == 200 and b'LucentThinker' in response.read()
        except (OSError, URLError):
            return False

    launch = launch or (lambda target: subprocess.run(['/usr/bin/open', target], check=True))
    alive, ready = alive or process_alive, ready or application_ready
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not alive():
            print('服务进程已退出，没有自动打开浏览器。', flush=True)
            return False
        if ready():
            try:
                launch(url)
            except (OSError, subprocess.CalledProcessError):
                print(f'无法自动打开浏览器，请手动访问 {url}', flush=True)
                return False
            return True
        time.sleep(0.25)
    print(f'服务未在等待时间内就绪，请检查终端；就绪后可手动访问 {url}', flush=True)
    return False


if __name__ == '__main__':
    sys.exit(0 if open_when_ready(sys.argv[1], sys.argv[2]) else 1)
