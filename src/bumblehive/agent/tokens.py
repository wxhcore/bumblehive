import json
from contextlib import suppress
from functools import lru_cache
from typing import Any


Message = dict[str, Any]

SNIP_SAFETY_BUFFER = 1024


def fit_context_window(
    *,
    provider: Any,
    model: str | None,
    messages: list[Message],
    tools: list[dict[str, Any]],
    context_window_tokens: int | None,
    max_output_tokens: int,
) -> list[Message]:
    """Return messages trimmed to fit a rough context-window budget."""
    if not messages or not context_window_tokens:
        return messages

    budget = context_window_tokens - max(1, max_output_tokens) - SNIP_SAFETY_BUFFER
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

    kept = _start_at_user_message(kept, non_system)
    if not kept:
        kept = _start_at_user_message(non_system[-min(len(non_system), 4):], non_system)

    return system_messages + kept


def estimate_prompt_tokens(
    *,
    provider: Any,
    model: str | None,
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
    parts: list[str] = []
    content = message.get("content")
    if isinstance(content, str):
        parts.append(content)
    elif isinstance(content, list):
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
            else:
                parts.append(json.dumps(item, ensure_ascii=False))
    elif content is not None:
        parts.append(json.dumps(content, ensure_ascii=False))

    for key in ("name", "tool_call_id", "reasoning_content"):
        value = message.get(key)
        if isinstance(value, str) and value:
            parts.append(value)

    tool_calls = message.get("tool_calls")
    if tool_calls:
        parts.append(json.dumps(tool_calls, ensure_ascii=False))

    payload = "\n".join(parts)
    return max(4, _estimate_text_tokens(payload) + 4)


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


def _start_at_user_message(
    kept: list[Message],
    fallback: list[Message],
) -> list[Message]:
    for index, message in enumerate(kept):
        if message.get("role") == "user":
            return kept[index:]

    for index in range(len(fallback) - 1, -1, -1):
        if fallback[index].get("role") == "user":
            return fallback[index:]

    return kept
