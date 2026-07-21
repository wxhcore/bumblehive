from bumblehive.agent.context import ContextGovernanceConfig, ContextGovernor


def _call(call_id, name):
    return {
        "id": call_id,
        "type": "function",
        "function": {"name": name, "arguments": "{}"},
    }


def test_governor_builds_a_valid_bounded_model_copy() -> None:
    original = [
        {"role": "user", "content": "first"},
        {
            "role": "assistant",
            "content": "keep this text",
            "tool_calls": [_call(None, "grep"), _call("", "read_file")],
        },
        {"role": "tool", "tool_call_id": "invalid", "content": "orphan"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [_call("valid", "grep")],
        },
        {"role": "tool", "tool_call_id": "valid", "content": "abcdef"},
    ]

    prepared = ContextGovernor.prepare_for_model(
        original,
        config=ContextGovernanceConfig(
            provider=object(),
            model="test-model",
            tools=[],
            context_window_tokens=None,
            max_completion_tokens=32,
            max_tool_result_chars=3,
        ),
    )

    assert prepared == [
        {"role": "user", "content": "first"},
        {"role": "assistant", "content": "keep this text"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [_call("valid", "grep")],
        },
        {
            "role": "tool",
            "tool_call_id": "valid",
            "content": "abc\n[truncated 3 chars]",
        },
    ]
    assert original[1]["tool_calls"][0]["id"] is None
