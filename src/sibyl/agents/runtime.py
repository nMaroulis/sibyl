"""Bridge blocking model inference to asynchronous application-owned agent transports."""

import asyncio
import threading
from collections.abc import Callable


class RuntimeBridge:
    """Keep provider calls off the API loop while tools use its registry and clients.

    ProtoLink's synchronous provider adapters can block even inside ``invoke``.
    The reasoning loop therefore runs in a worker. Its async consultation tools
    return to the application loop, avoiding cross-loop transport semaphore use.
    Closing the bridge prevents late tool dispatch after timeout/cancellation.
    """

    def __init__(self):
        self.loop = asyncio.get_running_loop()
        self._lock = threading.Lock()
        self._closed = False
        self._pending = set()

    async def call(self, operation: Callable, *args):
        """Run one async tool on the owning loop and propagate cancellation both ways."""
        with self._lock:
            if self._closed:
                raise asyncio.CancelledError
            future = asyncio.run_coroutine_threadsafe(operation(*args), self.loop)
            self._pending.add(future)
        try:
            return await asyncio.wrap_future(future)
        finally:
            with self._lock:
                self._pending.discard(future)

    def close(self) -> None:
        """Stop accepting tools and cancel any outstanding main-loop consultations."""
        with self._lock:
            self._closed = True
            pending = tuple(self._pending)
        for future in pending:
            future.cancel()
