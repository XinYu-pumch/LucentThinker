"""Standalone server owned by the launcher's stdin pipe, including host crashes."""
import asyncio
import sys
import threading

import uvicorn


async def run(port):
    server = uvicorn.Server(uvicorn.Config('app.main:app', host='127.0.0.1', port=port,
                                          timeout_graceful_shutdown=3))
    loop = asyncio.get_running_loop()

    def watch_owner():
        for _ in sys.stdin:
            pass
        loop.call_soon_threadsafe(setattr, server, 'should_exit', True)

    threading.Thread(target=watch_owner, daemon=True).start()
    await server.serve()


if __name__ == '__main__':
    asyncio.run(run(int(sys.argv[1])))
