import json
from collections.abc import Mapping, Sequence
from typing import Any


Message = dict[str, Any]

_ALLOWED_ROLES = frozenset({"system", "user", "assistant", "tool"})
_BASE_MESSAGE_KEYS = frozenset(
    {
        "role",
        "content",
        "tool_calls",
        "tool_call_id",
        "name",
    }
)
_MISSING_TOOL_RESULT_CONTENT = (
    "[Tool result unavailable - call was interrupted or lost]"
)
_DEFAULT_MAX_TOOL_RESULT_CHARS = 20_000


def prepare_history(
    messages: Sequence[Mapping[str, Any]],
    *,
    max_tool_result_chars: int | None = _DEFAULT_MAX_TOOL_RESULT_CHARS,
    missing_tool_result_content: str = _MISSING_TOOL_RESULT_CONTENT,
) -> list[Message]:
    """Return provider-ready history without mutating caller-owned messages."""
    prepared = sanitize_messages(messages)
    prepared = drop_empty_messages(prepared)
    prepared = merge_consecutive_text_messages(prepared)
    prepared = drop_orphan_tool_results(prepared)
    prepared = backfill_missing_tool_results(
        prepared,
        missing_tool_result_content=missing_tool_result_content,
    )
    if max_tool_result_chars is not None:
        prepared = truncate_tool_results(
            prepared,
            max_chars=max_tool_result_chars,
        )
    return prepared


def sanitize_messages(messages: Sequence[Mapping[str, Any]]) -> list[Message]:
    """Clone messages and keep only provider-relevant fields with valid roles."""
    sanitized: list[Message] = []
    for message in messages:
        role = message.get("role")
        if role not in _ALLOWED_ROLES:
            continue
        sanitized.append(
            {
                key: value
                for key, value in message.items()
                if key in _BASE_MESSAGE_KEYS
            }
        )
    return sanitized


def drop_empty_messages(messages: Sequence[Mapping[str, Any]]) -> list[Message]:
    """Drop messages with no model-relevant content."""
    result: list[Message] = []
    for message in messages:
        role = message.get("role")
        if role == "assistant" and message.get("tool_calls"):
            result.append(dict(message))
            continue
        if role == "tool" and message.get("tool_call_id"):
            result.append(dict(message))
            continue
        if _has_content(message.get("content")):
            result.append(dict(message))
    return result


def merge_consecutive_text_messages(
    messages: Sequence[Mapping[str, Any]],
) -> list[Message]:
    """Merge adjacent plain user/assistant text messages of the same role."""
    merged: list[Message] = []
    for message in messages:
        current = dict(message)
        role = current.get("role")
        if (
            role in {"user", "assistant"}
            and merged
            and merged[-1].get("role") == role
            and _is_plain_text_message(merged[-1])
            and _is_plain_text_message(current)
        ):
            previous = dict(merged[-1])
            previous["content"] = _merge_content(
                previous.get("content"),
                current.get("content"),
            )
            merged[-1] = previous
            continue
        merged.append(current)
    return merged


def drop_orphan_tool_results(
    messages: Sequence[Mapping[str, Any]],
) -> list[Message]:
    """Drop tool results that have no matching assistant tool call earlier."""
    declared: set[str] = set()
    result: list[Message] = []
    for message in messages:
        role = message.get("role")
        if role == "assistant":
            declared.update(_tool_call_ids(message))
        if role == "tool":
            tool_call_id = message.get("tool_call_id")
            if not isinstance(tool_call_id, str) or tool_call_id not in declared:
                continue
        result.append(dict(message))
    return result


def backfill_missing_tool_results(
    messages: Sequence[Mapping[str, Any]],
    *,
    missing_tool_result_content: str = _MISSING_TOOL_RESULT_CONTENT,
) -> list[Message]:
    """Insert synthetic tool results for assistant tool calls without results."""
    declared: list[tuple[int, str, str]] = []
    fulfilled: set[str] = set()

    for index, message in enumerate(messages):
        role = message.get("role")
        if role == "assistant":
            for call_id, name in _tool_call_refs(message):
                declared.append((index, call_id, name))
        elif role == "tool":
            tool_call_id = message.get("tool_call_id")
            if isinstance(tool_call_id, str):
                fulfilled.add(tool_call_id)

    missing = [
        (assistant_index, call_id, name)
        for assistant_index, call_id, name in declared
        if call_id not in fulfilled
    ]
    if not missing:
        return [dict(message) for message in messages]

    result = [dict(message) for message in messages]
    offset = 0
    for assistant_index, call_id, name in missing:
        insert_at = assistant_index + 1 + offset
        while insert_at < len(result) and result[insert_at].get("role") == "tool":
            insert_at += 1
        result.insert(
            insert_at,
            {
                "role": "tool",
                "tool_call_id": call_id,
                "name": name,
                "content": missing_tool_result_content,
            },
        )
        offset += 1
    return result


def truncate_tool_results(
    messages: Sequence[Mapping[str, Any]],
    *,
    max_chars: int,
) -> list[Message]:
    """Truncate oversized tool result content while preserving structure."""
    if max_chars < 0:
        raise ValueError("max_chars must be non-negative")

    result: list[Message] = []
    for message in messages:
        current = dict(message)
        if current.get("role") == "tool":
            text = _stringify_tool_content(current.get("content"))
            if len(text) > max_chars:
                omitted = len(text) - max_chars
                current["content"] = (
                    f"{text[:max_chars]}\n"
                    f"[truncated {omitted} chars]"
                )
            elif not isinstance(current.get("content"), str):
                current["content"] = text
        result.append(current)
    return result


def _has_content(content: Any) -> bool:
    if content is None:
        return False
    if isinstance(content, str):
        return bool(content.strip())
    if isinstance(content, list):
        return bool(content)
    return True


def _is_plain_text_message(message: Mapping[str, Any]) -> bool:
    if message.get("tool_calls"):
        return False
    content = message.get("content")
    return content is None or isinstance(content, str)


def _merge_content(left: Any, right: Any) -> str:
    left_text = "" if left is None else str(left)
    right_text = "" if right is None else str(right)
    if left_text and right_text:
        return f"{left_text}\n\n{right_text}"
    return left_text or right_text


def _tool_call_ids(message: Mapping[str, Any]) -> set[str]:
    return {call_id for call_id, _ in _tool_call_refs(message)}


def _tool_call_refs(message: Mapping[str, Any]) -> list[tuple[str, str]]:
    refs: list[tuple[str, str]] = []
    raw_tool_calls = message.get("tool_calls")
    if not isinstance(raw_tool_calls, list):
        return refs
    for raw_call in raw_tool_calls:
        if not isinstance(raw_call, Mapping):
            continue
        call_id = raw_call.get("id")
        if not isinstance(call_id, str) or not call_id:
            continue
        refs.append((call_id, _tool_call_name(raw_call)))
    return refs


def _tool_call_name(raw_call: Mapping[str, Any]) -> str:
    function = raw_call.get("function")
    if isinstance(function, Mapping):
        name = function.get("name")
        return name if isinstance(name, str) else ""
    name = raw_call.get("name")
    return name if isinstance(name, str) else ""


def _stringify_tool_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if content is None:
        return ""
    try:
        return json.dumps(content, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(content)
