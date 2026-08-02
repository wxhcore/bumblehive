import inspect
import logging
from collections.abc import Awaitable, Callable, Iterable
from typing import Protocol, runtime_checkable

from .events import AgentEvent

logger = logging.getLogger(__name__)

EventCallback = Callable[[AgentEvent], Awaitable[None] | None]


@runtime_checkable
class AgentHook(Protocol):
    """Consumer of agent lifecycle events."""

    async def on_event(self, event: AgentEvent) -> None:
        """Handle one lifecycle event."""


class NoopHook:
    """Hook used when callers do not observe events."""

    async def on_event(self, event: AgentEvent) -> None:
        pass


class CallbackHook:
    """Adapt a sync or async callable into an AgentHook."""

    def __init__(
        self,
        callback: EventCallback,
        *,
        reraise: bool = False,
    ) -> None:
        self.callback = callback
        self.reraise = reraise

    async def on_event(self, event: AgentEvent) -> None:
        result = self.callback(event)
        if inspect.isawaitable(result):
            await result


class CompositeHook:
    """Fan out events to an ordered list of hooks."""

    def __init__(self, hooks: Iterable[AgentHook | EventCallback]) -> None:
        self._hooks = [as_hook(hook) for hook in hooks]

    async def on_event(self, event: AgentEvent) -> None:
        for hook in self._hooks:
            if getattr(hook, "reraise", False):
                await hook.on_event(event)
                continue

            try:
                await hook.on_event(event)
            except Exception:
                logger.exception(
                    "Agent hook %s failed while handling %s",
                    type(hook).__name__,
                    event.kind,
                )


HookInput = (
    AgentHook
    | EventCallback
    | Iterable[AgentHook | EventCallback]
    | None
)


def as_hook(hook: AgentHook | EventCallback | None) -> AgentHook:
    """Normalize one hook-like value."""

    if hook is None:
        return NoopHook()
    if isinstance(hook, AgentHook):
        return hook
    if callable(hook):
        return CallbackHook(hook)
    raise TypeError(f"Unsupported hook type: {type(hook).__name__}")


def normalize_hooks(hooks: HookInput = None) -> AgentHook:
    """Normalize a hook, callback, hook list, or None into one hook."""

    if hooks is None:
        return NoopHook()
    if isinstance(hooks, CompositeHook):
        return hooks
    if isinstance(hooks, AgentHook) or callable(hooks):
        return CompositeHook([hooks])
    return CompositeHook(hooks)
