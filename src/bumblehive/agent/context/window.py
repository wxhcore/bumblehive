import json
from contextlib import suppress
from functools import lru_cache
from typing import Any

from ...protocols import Message


_DEFAULT_CONTEXT_WINDOW_TOKENS = 200_000
_SNIP_SAFETY_BUFFER = 1024
_IMAGE_TOKEN_ESTIMATE = 1844


def fit_context_window(
    *,
    provider: Any,
    model: str,
    messages: list[Message],
    tools: list[dict[str, Any]],
    context_window_tokens: int | None,
    max_completion_tokens: int,
) -> list[Message]:
    """Return messages trimmed to fit a rough context-window budget."""
    if not messages:
        return messages

    effective_context_window_tokens = (
        _DEFAULT_CONTEXT_WINDOW_TOKENS
        if context_window_tokens is None
        else context_window_tokens
    )
    if effective_context_window_tokens <= 0:
        return messages

    budget = (
        effective_context_window_tokens
        - max(1, max_completion_tokens)
        - _SNIP_SAFETY_BUFFER
    )
    if budget <= 0:
        return messages

    estimate, _source = estimate_prompt_tokens(
        provider=provider,
        model=model,
        messages=messages,
        tools=tools,
    )
    if estimate <= budget:
        return messages

    system_messages = [
        dict(message)
        for message in messages
        if message.get("role") == "system"
    ]
    non_system = [
        dict(message)
        for message in messages
        if message.get("role") != "system"
    ]
    if not non_system:
        return messages

    system_tokens = sum(estimate_message_tokens(message) for message in system_messages)
    fixed_tokens, _source = estimate_prompt_tokens(
        provider=provider,
        model=model,
        messages=system_messages,
        tools=tools,
    )
    remaining_budget = max(0, budget - max(system_tokens, fixed_tokens))

    kept: list[Message] = []
    kept_tokens = 0
    for message in reversed(non_system):
        message_tokens = estimate_message_tokens(message)
        if kept and kept_tokens + message_tokens > remaining_budget:
            break
        kept.append(message)
        kept_tokens += message_tokens
    kept.reverse()

    return system_messages + _legal_history_tail(kept, non_system)


def estimate_prompt_tokens(
    *,
    provider: Any,
    model: str,
    messages: list[Message],
    tools: list[dict[str, Any]] | None = None,
) -> tuple[int, str]:
    """Estimate prompt tokens using a provider counter when available."""
    provider_counter = getattr(provider, "estimate_prompt_tokens", None)
    if callable(provider_counter):
        with suppress(Exception):
            tokens, source = provider_counter(messages, tools, model)
            if isinstance(tokens, (int, float)) and tokens > 0:
                return int(tokens), str(source or "provider_counter")

    total = sum(estimate_message_tokens(message) for message in messages)
    if tools:
        total += _estimate_text_tokens(json.dumps(tools, ensure_ascii=False))
    return total, _token_estimator_source()


def estimate_message_tokens(message: Message) -> int:
    """Estimate tokens contributed by one chat message."""
    text_parts: list[str] = []
    multimodal_tokens = 0
    content = message.get("content")
    if isinstance(content, str):
        text_parts.append(content)
    elif isinstance(content, list):
        for part in content:
            if not isinstance(part, dict):
                text_parts.append(json.dumps(part, ensure_ascii=False))
                continue

            part_type = part.get("type")
            if part_type == "text":
                text = part.get("text")
                if isinstance(text, str):
                    text_parts.append(text)
            elif part_type in {"image_url", "input_image"}:
                multimodal_tokens += estimate_image_tokens(part)
            else:
                text_parts.append(json.dumps(part, ensure_ascii=False))
    elif content is not None:
        text_parts.append(json.dumps(content, ensure_ascii=False))

    for key in ("name", "tool_call_id", "reasoning_content"):
        value = message.get(key)
        if isinstance(value, str) and value:
            text_parts.append(value)

    tool_calls = message.get("tool_calls")
    if tool_calls:
        text_parts.append(json.dumps(tool_calls, ensure_ascii=False))

    text_tokens = _estimate_text_tokens("\n".join(text_parts))
    return max(4, text_tokens + multimodal_tokens + 4)


def estimate_image_tokens(_part: dict[str, Any]) -> int:
    return _IMAGE_TOKEN_ESTIMATE


def _estimate_text_tokens(text: str) -> int:
    if not text:
        return 0
    encoder = _tiktoken_encoder()
    if encoder is not None:
        with suppress(Exception):
            return max(1, len(encoder.encode(text)))
    return max(1, len(text) // 4)


def _token_estimator_source() -> str:
    return "tiktoken" if _tiktoken_encoder() is not None else "rough"


@lru_cache(maxsize=1)
def _tiktoken_encoder() -> Any | None:
    with suppress(Exception):
        import tiktoken

        return tiktoken.get_encoding("cl100k_base")
    return None


def _legal_history_tail(
    kept: list[Message],
    fallback: list[Message],
) -> list[Message]:
    fallback_tail = kept if kept else fallback[-1:] if fallback else []
    tail = _user_tail(kept) or _user_tail(fallback, last=True) or fallback_tail

    while tail:
        start = _find_legal_message_start(tail)
        if start:
            tail = tail[start:]
            continue

        incomplete_index = _first_incomplete_tool_call_index(tail)
        if incomplete_index is None:
            return tail

        next_user_tail = _user_tail(tail[incomplete_index + 1:])
        if not next_user_tail:
            return tail
        tail = next_user_tail

    return tail


def _user_tail(messages: list[Message], *, last: bool = False) -> list[Message]:
    indexes = range(len(messages) - 1, -1, -1) if last else range(len(messages))
    for index in indexes:
        if messages[index].get("role") == "user":
            return messages[index:]
    return []


def _find_legal_message_start(messages: list[Message]) -> int:
    declared: set[str] = set()
    start = 0
    for index, message in enumerate(messages):
        role = message.get("role")
        if role == "assistant":
            declared.update(_tool_call_ids(message))
        elif role == "tool":
            tool_call_id = message.get("tool_call_id")
            if not isinstance(tool_call_id, str) or tool_call_id not in declared:
                start = index + 1
                declared.clear()
    return start


def _first_incomplete_tool_call_index(messages: list[Message]) -> int | None:
    fulfilled = {
        tool_call_id
        for message in messages
        if message.get("role") == "tool"
        for tool_call_id in [message.get("tool_call_id")]
        if isinstance(tool_call_id, str)
    }
    for index, message in enumerate(messages):
        call_ids = _tool_call_ids(message)
        if call_ids and not call_ids <= fulfilled:
            return index
    return None


def _tool_call_ids(message: Message) -> set[str]:
    if message.get("role") != "assistant":
        return set()
    calls = message.get("tool_calls")
    if not isinstance(calls, list):
        return set()
    return {
        call_id
        for call in calls
        if isinstance(call, dict)
        for call_id in [call.get("id")]
        if isinstance(call_id, str) and call_id
    }
