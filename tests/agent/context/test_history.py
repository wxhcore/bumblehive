from copy import deepcopy

import pytest

from bumblehive.agent.context import MessageHistory, prepare_history


def _assistant_call(call_id: str, name: str = "read_file") -> dict:
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": call_id,
                "type": "function",
                "function": {"name": name, "arguments": "{}"},
            }
        ],
    }


def test_message_history_supports_the_full_library_lifecycle() -> None:
    history = MessageHistory([{"role": "user", "content": "hello"}])
    history.add_assistant("hi")
    history.add_tool("call_1", {"ok": True}, name="read_file")

    snapshot = history.get_history()
    snapshot[0]["role"] = "assistant"
    snapshot[0]["content"] = "changed"
    assert history.get_history()[0] == {"role": "user", "content": "hello"}

    history.replace_run_messages(
        [
            {"role": "system", "content": "runtime prompt"},
            {
                "role": "user",
                "content": (
                    "next question\n\n<runtime_context>\n"
                    "  <environment_context>old</environment_context>\n"
                    "</runtime_context>"
                ),
            },
            {"role": "assistant", "content": "answer"},
        ]
    )
    assert history.get_history() == [
        {"role": "user", "content": "next question"},
        {"role": "assistant", "content": "answer"},
    ]

    history.clear()
    assert history.get_history() == []


def test_prepare_history_repairs_and_limits_a_complete_provider_history() -> None:
    messages = [
        {"role": "developer", "content": "unsupported"},
        {"role": "user", "content": "first", "metadata": "drop"},
        {"role": "user", "content": "second"},
        {"role": "tool", "tool_call_id": "orphan", "content": "drop"},
        _assistant_call("missing"),
        _assistant_call("done", "grep"),
        {"role": "tool", "tool_call_id": "done", "content": {"value": "abcdef"}},
    ]
    original = deepcopy(messages)

    prepared = prepare_history(
        messages,
        max_tool_result_chars=8,
        missing_tool_result_content="lost",
    )

    assert prepared == [
        {"role": "user", "content": "first\n\nsecond"},
        _assistant_call("missing"),
        {
            "role": "tool",
            "tool_call_id": "missing",
            "name": "read_file",
            "content": "lost",
        },
        _assistant_call("done", "grep"),
        {
            "role": "tool",
            "tool_call_id": "done",
            "content": '{"value"\n[truncated 11 chars]',
        },
    ]
    assert messages == original


@pytest.mark.parametrize("max_chars", [-1, -20])
def test_prepare_history_rejects_negative_tool_result_budgets(max_chars) -> None:
    with pytest.raises(ValueError, match="non-negative"):
        prepare_history([], max_tool_result_chars=max_chars)
