from collections.abc import Mapping
from time import perf_counter


_TOKEN_ORDER = {
    "input_tokens": 0,
    "prompt_tokens": 1,
    "output_tokens": 2,
    "completion_tokens": 3,
    "reasoning_tokens": 4,
    "cached_tokens": 5,
    "total_tokens": 100,
}


def elapsed_since(started_at: float) -> str:
    return format_duration(perf_counter() - started_at)


def format_duration(elapsed_seconds: float) -> str:
    elapsed_seconds = max(elapsed_seconds, 0.0)
    if elapsed_seconds < 1:
        return f"{elapsed_seconds * 1000:.1f}ms"
    if elapsed_seconds < 60:
        return f"{elapsed_seconds:.2f}s"

    minutes, seconds = divmod(elapsed_seconds, 60)
    if minutes < 60:
        return f"{int(minutes)}m {seconds:04.1f}s"

    hours, minutes = divmod(minutes, 60)
    return f"{int(hours)}h {int(minutes):02d}m {seconds:04.1f}s"


def format_token_usage(usage: Mapping[str, int]) -> str:
    if not usage:
        return "none"

    keys = sorted(
        usage,
        key=lambda key: (_TOKEN_ORDER.get(key, 50), key),
    )
    return ",".join(
        f"{key.removesuffix('_tokens')}:{usage[key]}" for key in keys
    )


def safe_log_value(value: object, *, limit: int = 128) -> str:
    parts: list[str] = []
    for character in str(value):
        codepoint = ord(character)
        if character == "\r":
            parts.append("\\r")
        elif character == "\n":
            parts.append("\\n")
        elif character == "\t":
            parts.append("\\t")
        elif codepoint < 32 or codepoint == 127:
            parts.append(f"\\x{codepoint:02x}")
        else:
            parts.append(character)
    sanitized = "".join(parts)
    return sanitized[:limit]
