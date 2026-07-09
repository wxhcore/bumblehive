import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from .events import AgentEvent


_STREAM_END = object()
DEFAULT_STREAM_QUEUE_SIZE = 256


class AsyncEventStreamHook:
    """Hook that forwards agent events into an async queue."""

    def __init__(self, queue: asyncio.Queue[AgentEvent | object]) -> None:
        self._queue = queue

    async def on_event(self, event: AgentEvent) -> None:
        await self._queue.put(event)


@dataclass(slots=True)
class AsyncEventStream:
    """Async iterator over events produced by one background agent run."""

    run_with_hook: Callable[[AsyncEventStreamHook], Awaitable[Any]]
    maxsize: int = DEFAULT_STREAM_QUEUE_SIZE
    _queue: asyncio.Queue[AgentEvent | object] = field(init=False)
    _task: asyncio.Task[Any] | None = field(default=None, init=False)
    _error: BaseException | None = field(default=None, init=False)
    _started: bool = field(default=False, init=False)
    _closed: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        self._queue = asyncio.Queue(maxsize=max(0, self.maxsize))

    def __aiter__(self) -> AsyncIterator[AgentEvent]:
        if self._started:
            raise RuntimeError("AsyncEventStream can only be consumed once")
        self._started = True
        hook = AsyncEventStreamHook(self._queue)
        self._task = asyncio.create_task(self._run_background(hook))
        return self._iterate()

    async def _run_background(self, hook: AsyncEventStreamHook) -> None:
        try:
            await self.run_with_hook(hook)
        except asyncio.CancelledError:
            raise
        except BaseException as exc:
            self._error = exc
        finally:
            await self._put_end()

    async def _iterate(self) -> AsyncIterator[AgentEvent]:
        try:
            while True:
                item = await self._queue.get()
                if item is _STREAM_END:
                    if self._error is not None:
                        raise self._error
                    break
                yield item
        finally:
            await self.aclose()

    async def aclose(self) -> None:
        if self._closed:
            return
        self._closed = True
        task = self._task
        if task is None or task.done():
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    async def _put_end(self) -> None:
        if self._closed:
            return
        await self._queue.put(_STREAM_END)
