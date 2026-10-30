"""FIFO, cancellable model request slots shared by saved profile in one server.

Concurrency is a live scheduling setting; model/prompt snapshots stay immutable.
Lowering a limit lets active requests finish, then admits queued requests in order.
"""
import asyncio
import threading
import time
import weakref
from collections import deque
from contextlib import asynccontextmanager

_loops = weakref.WeakKeyDictionary()
_lock = threading.RLock()


class Gate:
    def __init__(self, limit):
        self.limit, self.active = limit, 0
        self.waiters = deque()

    def configure(self, limit):
        self.limit = limit
        self.drain()

    def drain(self):
        while self.waiters and self.active < self.limit:
            waiter = self.waiters.popleft()
            if not waiter.done():
                self.active += 1
                waiter.set_result(None)

    async def acquire(self):
        waiter = asyncio.get_running_loop().create_future()
        self.waiters.append(waiter)
        self.drain()
        try:
            await waiter
        except BaseException:
            if waiter.done() and not waiter.cancelled():
                self.release()  # Cancelled after grant but before resuming.
            elif waiter in self.waiters:
                self.waiters.remove(waiter)
            raise

    def release(self):
        self.active -= 1
        self.drain()


def update_profile_limit(profile_id, limit):
    # Settings endpoints run in worker threads; all gate changes run on its loop.
    with _lock:
        for loop, gates in list(_loops.items()):
            gate = gates.get(('profile', profile_id))
            if gate is not None and not loop.is_closed():
                loop.call_soon_threadsafe(gate.configure, limit)


def gate_for(settings):
    from . import settings_store
    key = ('profile', settings.profile_id) if settings.profile_id else ('unsaved', settings.base_url, settings.model)
    # Read current scheduling settings, never replace the research's model/key.
    # Hold settings lock through registration to avoid racing a simultaneous save.
    with settings_store.LOCK, _lock:
        limit = settings.concurrency
        if settings.profile_id:
            saved = settings_store.load()['profiles'].get(settings.profile_id)
            if saved: limit = saved.get('concurrency', 1)
        loop = asyncio.get_running_loop()
        gates = _loops.setdefault(loop, {})
        gate = gates.setdefault(key, Gate(limit))
        gate.configure(limit)
        return gate


@asynccontextmanager
async def model_slot(settings, observer, role, purpose, iteration, attempt):
    gate = gate_for(settings)
    queued = gate.active >= gate.limit or bool(gate.waiters)
    started = time.monotonic()
    def emit(kind, **data):
        if observer and hasattr(observer, 'emit'):
            observer.emit(kind, role=role, purpose=purpose, iteration=iteration,
                          attempt=attempt, profile_id=settings.profile_id, limit=gate.limit, **data)
    if queued: emit('model_queued')
    try:
        await gate.acquire()
    except asyncio.CancelledError:
        if queued: emit('model_queue_cancelled')
        raise
    try:
        if queued: emit('model_dequeued', waited_seconds=time.monotonic()-started)
        emit('model_admitted', waited_seconds=time.monotonic()-started)
        yield
    finally:
        gate.release()
