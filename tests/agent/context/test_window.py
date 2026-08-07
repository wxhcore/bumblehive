import pytest

from bumblehive.agent.context.window import (
    estimate_message_tokens,
    estimate_prompt_tokens,
    fit_context_window,
)


def _assistant_call(call_id: str) -> dict:
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": call_id,
                "type": "function",
                "function": {"name": "grep", "arguments": "{}"},
            }
        ],
    }


def test_fit_context_window_keeps_system_and_latest_legal_turn() -> None:
    messages = [
        {"role": "system", "content": "system"},
        {"role": "user", "content": "old question " + "x" * 800},
        _assistant_call("unfinished"),
        {"role": "user", "content": "latest question"},
    ]

    fitted = fit_context_window(
        provider=object(),
        model="test-model",
        messages=messages,
        tools=[],
        context_window_tokens=1_100,
        max_completion_tokens=1,
    )

    assert fitted == [
        {"role": "system", "content": "system"},
        {"role": "user", "content": "latest question"},
    ]
    assert messages[1]["content"].startswith("old question")


def test_fit_context_window_preserves_complete_tool_turn_when_it_fits() -> None:
    messages = [
        {"role": "system", "content": "system"},
        {"role": "user", "content": "old " + "x" * 1_000},
        {"role": "user", "content": "use the tool"},
        _assistant_call("done"),
        {"role": "tool", "tool_call_id": "done", "content": "result"},
        {"role": "user", "content": "continue"},
    ]

    fitted = fit_context_window(
        provider=object(),
        model="test-model",
        messages=messages,
        tools=[],
        context_window_tokens=1_180,
        max_completion_tokens=1,
    )

    assert fitted[0]["role"] == "system"
    assert fitted[1:] == messages[2:]


def test_fit_context_window_rejects_no_input_budget() -> None:
    with pytest.raises(ValueError, match="No input token budget remains"):
        fit_context_window(
            provider=object(),
            model="test-model",
            messages=[{"role": "user", "content": "hello"}],
            tools=[],
            context_window_tokens=1_024,
            max_completion_tokens=1,
        )


def test_fit_context_window_rejects_oversized_current_turn() -> None:
    messages = [
        {"role": "system", "content": "system"},
        {"role": "user", "content": "inspect the result"},
        _assistant_call("large"),
        {
            "role": "tool",
            "tool_call_id": "large",
            "content": "x" * 20_000,
        },
    ]

    with pytest.raises(ValueError, match="after trimming"):
        fit_context_window(
            provider=object(),
            model="test-model",
            messages=messages,
            tools=[],
            context_window_tokens=4_000,
            max_completion_tokens=1_000,
        )


def test_fit_context_window_rejects_fixed_context_without_message_budget() -> None:
    messages = [
        {"role": "system", "content": "x" * 20_000},
        {"role": "user", "content": "hello"},
    ]

    with pytest.raises(ValueError, match="leave no input budget"):
        fit_context_window(
            provider=object(),
            model="test-model",
            messages=messages,
            tools=[],
            context_window_tokens=4_000,
            max_completion_tokens=1_000,
        )


def test_prompt_estimation_prefers_a_provider_counter() -> None:
    class Provider:
        def estimate_prompt_tokens(self, messages, tools, model):
            assert model == "test-model"
            return 42, "provider"

    assert estimate_prompt_tokens(
        provider=Provider(),
        model="test-model",
        messages=[{"role": "user", "content": "hello"}],
        tools=[],
    ) == (42, "provider")


def test_message_estimation_charges_fixed_cost_per_image() -> None:
    text_part = {"type": "text", "text": "inspect"}
    text_only = {"role": "user", "content": [text_part]}
    with_images = {
        "role": "user",
        "content": [
            {
                "type": "image_url",
                "image_url": {"url": "data:image/png;base64,AAAA"},
            },
            {"type": "input_image", "image_url": "data:image/png;base64,BBBB"},
            text_part,
        ],
    }

    assert estimate_message_tokens(with_images) == (
        estimate_message_tokens(text_only) + 2 * 1844
    )


def test_message_estimation_ignores_image_base64_length() -> None:
    def message(payload: str) -> dict:
        return {
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/png;base64,{payload}",
                    },
                }
            ],
        }

    assert estimate_message_tokens(message("A")) == estimate_message_tokens(
        message("A" * 100_000)
    )
