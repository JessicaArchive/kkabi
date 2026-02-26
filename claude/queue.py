import asyncio
import logging

logger = logging.getLogger(__name__)


class ExecutionQueue:
    def __init__(self, max_concurrent: int = 1, max_size: int = 10):
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=max_size)
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._worker_task: asyncio.Task | None = None

    def start(self):
        self._worker_task = asyncio.create_task(self._worker())

    async def stop(self):
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass

    @property
    def pending_count(self) -> int:
        return self._queue.qsize()

    async def submit(self, coro_func, *args, **kwargs) -> asyncio.Future:
        future = asyncio.get_event_loop().create_future()
        await self._queue.put((coro_func, args, kwargs, future))
        return future

    async def _worker(self):
        while True:
            coro_func, args, kwargs, future = await self._queue.get()
            try:
                async with self._semaphore:
                    result = await coro_func(*args, **kwargs)
                    if not future.done():
                        future.set_result(result)
            except Exception as e:
                if not future.done():
                    future.set_exception(e)
            finally:
                self._queue.task_done()


execution_queue = ExecutionQueue()
