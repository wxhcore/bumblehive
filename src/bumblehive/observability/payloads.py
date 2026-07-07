from typing import Any

from ..protocols import AgentError, ToolCall, ToolResult


def error_payload(error: AgentError | None) -> dict[str, Any] | None:
    """Return the standard event payload for an agent error."""

    if error is None:
        return None
    return {
        "code": error.code,
        "message": error.message,
        "recoverable": error.recoverable,
    }


def tool_call_payload(call: ToolCall) -> dict[str, Any]:
    """Return the standard event payload for a tool call."""

    return {
        "tool_call": {
            "call_id": call.id,
            "name": call.name,
            "arguments": dict(call.arguments),
        },
    }


def tool_result_payload(
    result: ToolResult,
    *,
    call: ToolCall | None = None,
) -> dict[str, Any]:
    """Return the standard event payload for a tool result."""

    payload: dict[str, Any] = {
        "ok": result.error is None,
        "tool_result": result.to_openai_tool_message(call=call),
    }
    error = error_payload(result.error)
    if error is not None:
        payload["error"] = error
    return payload
