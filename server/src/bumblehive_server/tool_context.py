"""Desktop tool-call identity, supplied through the SDK's existing hooks."""

from contextvars import ContextVar

from bumblehive.observability.events import (
    RUN_STARTED,
    TOOL_CALL_FINISHED,
    TOOL_CALL_STARTED,
    AgentEvent,
)

_CALL_ID: ContextVar[str | None] = ContextVar("desktop_tool_call_id", default=None)


def capture_tool_call(event: AgentEvent) -> None:
    # Hooks run in the executing task, unlike the WebSocket stream consumer.
    # Parallel tool calls therefore each get their own context.
    if event.kind == TOOL_CALL_STARTED:
        _CALL_ID.set(event.payload["tool_call"]["call_id"])
    elif event.kind in (TOOL_CALL_FINISHED, RUN_STARTED):
        _CALL_ID.set(None)


def pending_tool_result() -> dict[str, str]:
    call_id = _CALL_ID.get()
    if call_id is None:
        raise RuntimeError("A desktop background tool requires an active tool call")
    return {"status": "pending", "task_id": call_id}
