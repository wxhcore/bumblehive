import json
from collections.abc import Mapping
from dataclasses import asdict
from typing import Any

from bumblehive.agent import AgentRunResult
from bumblehive.observability.events import (
    MODEL_RESPONSE_FINISHED,
    MODEL_STREAM_CONTENT_DELTA,
    MODEL_STREAM_REASONING_DELTA,
    MODEL_STREAM_REFUSAL_DELTA,
    MODEL_STREAM_TOOL_CALL_DELTA,
    TOOL_CALL_FINISHED,
    TOOL_CALL_STARTED,
    AgentEvent,
)

from .tool_details import tool_detail


_DIRECT_UI_EVENT_KINDS = frozenset(
    {
        MODEL_STREAM_CONTENT_DELTA,
        MODEL_STREAM_REASONING_DELTA,
        MODEL_STREAM_REFUSAL_DELTA,
        MODEL_STREAM_TOOL_CALL_DELTA,
        TOOL_CALL_STARTED,
    }
)


def result_frame(
    session_id: str,
    result: AgentRunResult,
    duration_s: float,
) -> dict[str, Any]:
    error = asdict(result.error) if result.error is not None else None
    return {
        "type": "result",
        "session_id": session_id,
        "final_content": result.final_content,
        "tools_used": result.tools_used,
        "usage": result.usage,
        "stop_reason": result.stop_reason,
        "duration_s": round(duration_s, 3),
        "error": error,
    }


def ui_event_frame(event: AgentEvent) -> dict[str, Any] | None:
    payload: Mapping[str, Any]
    if event.kind in _DIRECT_UI_EVENT_KINDS:
        payload = event.payload
    elif event.kind == TOOL_CALL_FINISHED:
        tool_result = event.payload.get("tool_result")
        if not isinstance(tool_result, Mapping):
            return None
        name = tool_result.get("name")
        result_document = _tool_result_document(tool_result.get("content"))
        payload = {
            "ok": event.payload.get("ok"),
            "tool_result": {
                key: tool_result[key]
                for key in ("tool_call_id", "name")
                if key in tool_result
            },
        }
        if isinstance(name, str):
            detail = tool_detail(
                name,
                result_document,
                file_changes=event.payload.get("file_changes"),
            )
            if detail is not None:
                payload["tool_result"]["detail"] = detail
        result_error = _tool_result_error(result_document)
        if result_error is not None:
            payload["ok"] = False
            payload["error"] = {
                "code": "tool_result_error",
                "message": result_error,
                "recoverable": True,
            }
        for key in ("duration_s", "error"):
            if key in event.payload:
                payload[key] = event.payload[key]
    elif event.kind == MODEL_RESPONSE_FINISHED:
        message = event.payload.get("message")
        if not isinstance(message, Mapping):
            return None
        reasoning = message.get("reasoning_content")
        if not isinstance(reasoning, str) or not reasoning:
            return None
        payload = {"message": {"reasoning_content": reasoning}}
    else:
        return None

    return {
        "type": "event",
        "kind": event.kind,
        "run_id": event.run_id,
        "payload": dict(payload),
        "iteration": event.iteration,
        "session_id": event.session_id,
        "timestamp": event.timestamp,
    }


def _tool_result_document(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    if not isinstance(value, str) or not value:
        return {}
    try:
        parsed = json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return {}
    return parsed if isinstance(parsed, Mapping) else {}


def _tool_result_error(document: Mapping[str, Any]) -> str | None:
    error = document.get("error")
    if isinstance(error, str) and error:
        return error
    if isinstance(error, Mapping):
        message = error.get("message")
        if isinstance(message, str) and message:
            return message
    return None
