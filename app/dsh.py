"""DSH-owned loopback engine. Capability URLs and stdin ownership are mandatory."""
import asyncio
import json
import os
import re
import socket
import sys
import threading
from urllib.parse import urlsplit

import uvicorn


class PluginBoundary:
    def __init__(self, app, token, parent_origin='dsh-app://app'):
        if not re.fullmatch(r'[a-f0-9]{64}', token):
            raise ValueError('Invalid engine capability')
        self.app = app
        self.prefix = '/dsh/' + token
        parsed = urlsplit(parent_origin)
        if parent_origin != 'dsh-app://app' and not (
            re.fullmatch(r'https?://(?:127\.0\.0\.1|localhost|\[::1\])(?::[0-9]{1,5})?', parent_origin)
            and (parsed.port is None or 0 < parsed.port < 65536)
            and parsed.scheme in ('http', 'https') and parsed.hostname in ('127.0.0.1', 'localhost', '::1')
            and not parsed.username and not parsed.password and not parsed.path and not parsed.query and not parsed.fragment
        ):
            raise ValueError('Embedding requires a local DSH origin')
        self.ancestors = ('frame-ancestors dsh-app://app' +
                          ('' if parent_origin == 'dsh-app://app' else ' ' + parent_origin)).encode()

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        path = scope['path']
        if not path.startswith(self.prefix + '/'):
            await send({'type': 'http.response.start', 'status': 404, 'headers': []})
            return await send({'type': 'http.response.body', 'body': b'Not found'})
        scope = dict(scope)
        scope['path'] = path[len(self.prefix):]
        scope['raw_path'] = scope['path'].encode()
        # Keep URL generation same-origin; routing uses the stripped path.
        if scope['method'] == 'GET' and scope['path'] == '/':
            # An authenticated capability navigation from the DSH iframe is cross-site.
            scope['headers'] = [(k, v) for k, v in scope['headers'] if k not in (b'sec-fetch-site', b'origin')]

        async def respond(message):
            if message['type'] == 'http.response.start':
                message = dict(message)
                message['headers'] = [
                    (k, v.replace(b"frame-ancestors 'none'", self.ancestors))
                    if k == b'content-security-policy' else (k, v)
                    for k, v in message.get('headers', [])
                ]
            await send(message)
        await self.app(scope, receive, respond)


async def run():
    # The initial private pipe message never appears in a process command line or log.
    line = await asyncio.to_thread(sys.stdin.readline)
    options = json.loads(line)
    token = options['token']
    from .file_lock import acquire
    from pathlib import Path
    data = Path(os.environ['LUCENT_DATA_DIR'])
    data.mkdir(parents=True, exist_ok=True)
    lock = (data / '.engine.lock').open('a+')
    acquire(lock, exclusive=True, blocking=False)
    from . import config
    from .main import app
    boundary = PluginBoundary(app, token, options.get('parentOrigin', 'dsh-app://app'))
    config.URL_PREFIX = boundary.prefix
    config.register_secret(token)
    sock = socket.socket()
    sock.bind(('127.0.0.1', 0))
    sock.listen(128)
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(boundary, host='127.0.0.1', port=port,
        log_level='warning', access_log=False, timeout_graceful_shutdown=3))
    loop = asyncio.get_running_loop()
    def owner_watchdog():
        # Includes a normal unload, a crashed Host and SIGKILL of the Host.
        for _ in sys.stdin:
            pass
        loop.call_soon_threadsafe(setattr, server, 'should_exit', True)
    threading.Thread(target=owner_watchdog, daemon=True).start()
    task = asyncio.create_task(server.serve(sockets=[sock]))
    try:
        while not server.started and not task.done():
            await asyncio.sleep(.02)
        if not server.started:
            await task
            raise RuntimeError('Research engine did not start')
        print(json.dumps({'ready': True, 'port': port, 'pid': os.getpid()}), flush=True)
        await task
    finally:
        sock.close()
        state_file = data / 'engine-state.json'
        try:
            if json.loads(state_file.read_text(encoding='utf-8')).get('enginePid') == os.getpid():
                state_file.unlink()
        except (OSError, ValueError):
            pass
        lock.close()


if __name__ == '__main__':
    if not os.getenv('LUCENT_DATA_DIR'):
        raise SystemExit('DSH engine requires its own data directory')
    asyncio.run(run())
