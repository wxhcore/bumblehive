from dataclasses import dataclass
from typing import Any

from .history import prepare_history, repair_message_sequence
from .window import fit_context_window


Message = dict[str, Any]


@dataclass(frozen=True)
class ContextGovernanceConfig:
    """Settings for preparing a model-facing copy of run messages."""

    provider: Any
    model: str
    tools: list[dict[str, Any]]
    context_window_tokens: int | None
    max_completion_tokens: int
    max_tool_result_chars: int | None = None


class ContextGovernor:
    """Prepare model-facing messages without mutating run history."""

    @staticmethod
    def prepare_for_model(
        messages: list[Message],
        *,
        config: ContextGovernanceConfig,
    ) -> list[Message]:
        repaired = _strip_malformed_tool_calls(messages)
        prepared = prepare_history(
            repaired,
            max_tool_result_chars=config.max_tool_result_chars,
        )
        fitted = fit_context_window(
            provider=config.provider,
            model=config.model,
            messages=prepared,
            tools=config.tools,
            context_window_tokens=config.context_window_tokens,
            max_completion_tokens=config.max_completion_tokens,
        )
        return repair_message_sequence(fitted)


def _strip_malformed_tool_calls(
    messages: list[Message],
) -> list[Message]:
    """Drop invalid assistant tool calls from a model-facing history copy."""
    repaired: list[Message] = []
    for message in messages:
        current = dict(message)
        if current.get("role") != "assistant" or not current.get("tool_calls"):
            repaired.append(current)
            continue

        calls = current.get("tool_calls")
        if not isinstance(calls, list):
            current.pop("tool_calls", None)
            if _has_assistant_payload(current):
                repaired.append(current)
            continue

        kept = [call for call in calls if _is_valid_tool_call(call)]
        if kept:
            current["tool_calls"] = kept
            repaired.append(current)
            continue

        current.pop("tool_calls", None)
        if _has_assistant_payload(current):
            repaired.append(current)

    return repaired


def _is_valid_tool_call(call: Any) -> bool:
    if not isinstance(call, dict):
        return False

    call_id = call.get("id")
    if not isinstance(call_id, str) or not call_id:
        return False

    function = call.get("function")
    if isinstance(function, dict):
        name = function.get("name")
    else:
        name = call.get("name")

    return isinstance(name, str) and bool(name)


def _has_assistant_payload(message: Message) -> bool:
    if _has_content(message.get("content")):
        return True
    return _has_content(message.get("reasoning_content"))


def _has_content(content: Any) -> bool:
    if content is None:
        return False
    if isinstance(content, str):
        return bool(content.strip())
    if isinstance(content, list):
        return bool(content)
    return True
