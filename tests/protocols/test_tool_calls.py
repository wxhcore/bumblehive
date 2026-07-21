import json

import pytest

from bumblehive.protocols import AgentError, ToolCall, ToolResult, parse_tool_call


def test_tool_call_and_result_round_trip_through_openai_shapes() -> None:
    call = parse_tool_call(
        {
            "id": "call-1",
            "type": "function",
            "function": {"name": "add", "arguments": '{"a": 1, "b": 2}'},
        }
    )

    assert call == ToolCall("call-1", "add", {"a": 1, "b": 2})
    assert call.to_openai_tool_call()["function"]["arguments"] == '{"a":1,"b":2}'
    assert ToolResult("call-1", "add", {"value": 3}).to_openai_tool_message() == {
        "role": "tool",
        "tool_call_id": "call-1",
        "name": "add",
        "content": '{"value": 3}',
    }

    error_message = ToolResult(
        "call-1",
        "add",
        error=AgentError("tool_failed", "boom", recoverable=True),
    ).to_openai_tool_message()
    assert json.loads(error_message["content"]) == {
        "error": {"code": "tool_failed", "message": "boom", "recoverable": True}
    }


@pytest.mark.parametrize(
    "raw",
    [
        [],
        {"id": 1, "function": {"name": "add", "arguments": "{}"}},
        {"id": "1", "function": {"name": 2, "arguments": "{}"}},
        {"id": "1", "function": {"name": "add", "arguments": "[]"}},
        {"id": "1", "function": {"name": "add", "arguments": "{bad"}},
    ],
)
def test_parse_tool_call_rejects_malformed_model_payloads(raw) -> None:
    with pytest.raises(ValueError):
        parse_tool_call(raw)
