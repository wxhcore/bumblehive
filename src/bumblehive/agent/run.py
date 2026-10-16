"""Steerable handles for a single non-streaming or streaming run."""

import inspect
from collections.abc import AsyncIterator, Awaitable, Callable, Coroutine, Generator
from typing import Any

from ..observability.events import AgentEvent
from ..observability.streaming import (
    DEFAULT_STREAM_QUEUE_SIZE,
    AsyncEventStream,
    AsyncEventStreamHook,
)
from ..protocols import Message, UserMessage
from .control import _RunControl
from .runner import AgentRunResult


class AgentRun(Coroutine[Any, Any, AgentRunResult]):
    """A single-use coroutine with a queue for supplemental user input.

    Await directly or schedule with ``asyncio.create_task``. Only one await or
    Task may drive the run. Call ``steer`` on the owning event loop; it queues
    input without starting execution. Cancel an active run through its Task.
    """

    def __init__(
        self,
        coroutine: Coroutine[Any, Any, AgentRunResult],
        control: _RunControl,
    ) -> None:
        self._coroutine = coroutine
        self._control = control

    def steer(self, message: UserMessage) -> None:
        """Validate and copy input into this run; raise RuntimeError if closed."""
        self._control.steer(message)

    def take_pending(self) -> list[Message]:
        """Remove unconsumed input after closure; raise RuntimeError while open."""
        return self._control.take_pending()

    def __await__(self) -> Generator[Any, None, AgentRunResult]:
        try:
            return (yield from self._coroutine.__await__())
        finally:
            self._close_if_terminated()

    def send(self, value: Any) -> Any:
        try:
            return self._coroutine.send(value)
        finally:
            self._close_if_terminated()

    def throw(self, *args: Any) -> Any:
        try:
            return self._coroutine.throw(*args)
        finally:
            self._close_if_terminated()

    def close(self) -> None:
        """Discard an unscheduled run; cancel active runs through their Task."""
        self._control._close()
        self._coroutine.close()

    def _close_if_terminated(self) -> None:
        if inspect.getcoroutinestate(self._coroutine) == inspect.CORO_CLOSED:
            self._control._close()


class AgentRunStream(AsyncEventStream[AgentRunResult]):
    """A single-consumer event stream with supplemental input for its run.

    Iteration starts execution. Consume fully before calling ``result`` and
    always call ``aclose`` when abandoning the stream. Input can close before
    buffered events have all been consumed.
    """

    def __init__(
        self,
        run_with_hook: Callable[[AsyncEventStreamHook], Awaitable[AgentRunResult]],
        control: _RunControl,
        *,
        maxsize: int = DEFAULT_STREAM_QUEUE_SIZE,
    ) -> None:
        super().__init__(run_with_hook, maxsize=maxsize)
        self._control = control

    def steer(self, message: UserMessage) -> None:
        """Validate and copy input into this run on its owning event loop."""
        self._control.steer(message)

    def take_pending(self) -> list[Message]:
        """Remove unconsumed input after closure; raise RuntimeError while open."""
        return self._control.take_pending()

    def __aiter__(self) -> AsyncIterator[AgentEvent]:
        if self._closed:
            raise RuntimeError("AgentRunStream is closed")
        return super().__aiter__()

    async def aclose(self) -> None:
        """Close input and cancel/await stream execution, including before start."""
        self._control._close()
        await super().aclose()
