import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from typing import Generic, TypeVar

from .events import AgentEvent


_STREAM_END = object()
DEFAULT_STREAM_QUEUE_SIZE = 256
ResultT = TypeVar("ResultT")


class AsyncEventStreamHook:
    """Hook that forwards agent events into an async queue."""

    def __init__(self, queue: asyncio.Queue[AgentEvent | object]) -> None:
        self._queue = queue

    async def on_event(self, event: AgentEvent) -> None:
        await self._queue.put(event)


@dataclass(slots=True)
class AsyncEventStream(Generic[ResultT]):
    """Async iterator over events produced by one background agent run."""

    run_with_hook: Callable[[AsyncEventStreamHook], Awaitable[ResultT]]
    maxsize: int = DEFAULT_STREAM_QUEUE_SIZE
    _queue: asyncio.Queue[AgentEvent | object] = field(init=False)
    _task: asyncio.Task[ResultT] | None = field(default=None, init=False)
    _started: bool = field(default=False, init=False)
    _closed: bool = field(default=False, init=False)
    _exhausted: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        self._queue = asyncio.Queue(maxsize=max(0, self.maxsize))

    def __aiter__(self) -> AsyncIterator[AgentEvent]:
        if self._started:
            raise RuntimeError("AsyncEventStream can only be consumed once")
        self._started = True
        hook = AsyncEventStreamHook(self._queue)
        self._task = asyncio.create_task(self._run_background(hook))
        return self._iterate()

    async def _run_background(self, hook: AsyncEventStreamHook) -> ResultT:
        try:
            return await self.run_with_hook(hook)
        finally:
            await self._put_end()

    async def _iterate(self) -> AsyncIterator[AgentEvent]:
        try:
            while True:
                item = await self._queue.get()
                if item is _STREAM_END:
                    self._exhausted = True
                    task = self._task
                    if task is None:
                        raise RuntimeError("AsyncEventStream has not started")
                    await task
                    break
                yield item
        finally:
            await self.aclose()

    async def result(self) -> ResultT:
        """Return the completed background run result."""
        task = self._task
        if task is None:
            raise RuntimeError(
                "AsyncEventStream must be consumed before requesting its result"
            )
        if task.cancelled():
            raise RuntimeError("AsyncEventStream was closed before producing a result")
        if not self._exhausted:
            raise RuntimeError(
                "AsyncEventStream must be consumed to completion before "
                "requesting its result"
            )
        if not task.done():
            raise RuntimeError("AsyncEventStream background run is still finishing")
        return task.result()

    async def aclose(self) -> None:
        """Stop production and wake a consumer, discarding unread events."""
        if self._closed:
            return
        self._closed = True
        task = self._task
        if task is None:
            return
        try:
            if task.done():
                if not task.cancelled():
                    task.exception()
            else:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
        finally:
            if not self._exhausted:
                # The producer skips _put_end() after closure and may not even
                # have started. Wake a reader blocked in queue.get(), including
                # when the bounded output queue was full at cancellation.
                while not self._queue.empty():
                    self._queue.get_nowait()
                self._queue.put_nowait(_STREAM_END)

    async def _put_end(self) -> None:
        if self._closed:
            return
        await self._queue.put(_STREAM_END)
