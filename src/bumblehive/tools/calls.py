import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from ..agent.types import AgentError


@dataclass(frozen=True)
class ToolCall:
    """A parsed tool call ready for registry execution."""

    id: str
    name: str
    arguments: dict[str, Any]

    def to_openai_tool_call(self) -> dict[str, Any]:
        """Return this call in Chat Completions assistant-message shape."""
        return {
            "id": self.id,
            "type": "function",
            "function": {
                "name": self.name,
                "arguments": json.dumps(
                    self.arguments,
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
            },
        }


@dataclass(frozen=True)
class ToolResult:
    """Result of executing a tool call."""

    call_id: str
    name: str
    content: Any = None
    error: AgentError | None = None

    @property
    def is_error(self) -> bool:
        return self.error is not None


def parse_tool_call(raw: Any) -> ToolCall:
    """Parse and validate a raw model tool call into a ToolCall."""
    if isinstance(raw, str):
        raw = _loads_object(raw, "tool call")
    elif not isinstance(raw, Mapping):
        raise ValueError("tool call must be a JSON object")

    call_id = raw.get("id")
    if not isinstance(call_id, str):
        raise ValueError("tool call id must be a string")

    payload = raw.get("function")
    if isinstance(payload, Mapping):
        name = payload.get("name")
        arguments = payload.get("arguments", "{}")
    else:
        name = raw.get("name")
        arguments = raw.get("arguments", "{}")

    if not isinstance(name, str):
        raise ValueError("tool call name must be a string")

    if isinstance(arguments, str):
        arguments = _loads_object(arguments or "{}", "tool call arguments")
    elif not isinstance(arguments, Mapping):
        raise ValueError("tool call arguments must be a JSON object")

    return ToolCall(id=call_id, name=name, arguments=dict(arguments))


def _loads_object(value: str, label: str) -> dict[str, Any]:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} must be valid JSON: {exc.msg}") from exc

    if not isinstance(parsed, dict):
        raise ValueError(f"{label} must be a JSON object")

    return parsed
