from bumblehive_server.logging_utils import (
    format_duration,
    format_token_usage,
    safe_log_value,
)


def test_format_duration_uses_readable_units() -> None:
    assert format_duration(0.01234) == "12.3ms"
    assert format_duration(1.234) == "1.23s"
    assert format_duration(62.3) == "1m 02.3s"
    assert format_duration(3723.4) == "1h 02m 03.4s"


def test_format_token_usage_orders_and_shortens_token_names() -> None:
    assert format_token_usage(
        {
            "total_tokens": 156,
            "completion_tokens": 36,
            "prompt_tokens": 120,
        }
    ) == "prompt:120,completion:36,total:156"
    assert format_token_usage({}) == "none"


def test_safe_log_value_prevents_multiline_log_injection() -> None:
    assert safe_log_value("session\r\n\tnext\x1b-line") == (
        "session\\r\\n\\tnext\\x1b-line"
    )
    assert safe_log_value("x" * 200) == "x" * 128
