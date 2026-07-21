import asyncio
from types import SimpleNamespace
from typing import Any

import pytest

from bumblehive.protocols import GenerationConfig
from bumblehive.providers import (
    ModelRequest,
    ModelStreamCallbacks,
    OpenAIChatCompletionsProvider,
)


class FakeCompletions:
    def __init__(self, response=None, *, error=None, effects=None) -> None:
        self.response = response
        self.error = error
        self.effects = list(effects or [])
        self.payloads: list[dict[str, Any]] = []

    @property
    def payload(self):
        return self.payloads[-1] if self.payloads else None

    async def create(self, **payload):
        self.payloads.append(payload)
        if self.effects:
            effect = self.effects.pop(0)
            if isinstance(effect, Exception):
                raise effect
            return effect
        if self.error is not None:
            raise self.error
        return self.response


class FakeStream:
    def __init__(self, chunks) -> None:
        self.chunks = list(chunks)

    def __aiter__(self):
        self._index = 0
        return self

    async def __anext__(self):
        if self._index >= len(self.chunks):
            raise StopAsyncIteration
        chunk = self.chunks[self._index]
        self._index += 1
        return chunk


class SlowStream:
    def __aiter__(self):
        return self

    async def __anext__(self):
        await asyncio.Event().wait()


class FakeClient:
    def __init__(self, completions) -> None:
        self.chat = SimpleNamespace(completions=completions)
        self.closed = False

    async def close(self) -> None:
        self.closed = True


class FakeResponse:
    def __init__(self, *, status_code=None, headers=None, text="") -> None:
        self.status_code = status_code
        self.headers = headers or {}
        self.text = text


class FakeAPIError(Exception):
    def __init__(self, message, *, status_code=None, body=None, headers=None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.body = body
        self.response = FakeResponse(
            status_code=status_code,
            headers=headers,
            text=str(body) if body is not None else message,
        )


class FakeTimeoutError(Exception):
    pass


def _response(*, content="ok", tool_calls=None, finish_reason="stop", usage=None, reasoning=None):
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content=content,
                    tool_calls=tool_calls,
                    refusal=None,
                    reasoning_content=reasoning,
                ),
                finish_reason=finish_reason,
            )
        ],
        usage=usage
        or SimpleNamespace(prompt_tokens=10, completion_tokens=5, total_tokens=15),
    )


def _tool_call(*, arguments='{"a": 1, "b": 2}'):
    return SimpleNamespace(
        id="call_add",
        function=SimpleNamespace(name="add", arguments=arguments),
    )


def _stream_chunk(
    *,
    content=None,
    refusal=None,
    reasoning_content=None,
    tool_calls=None,
    finish_reason=None,
    usage=None,
):
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                delta=SimpleNamespace(
                    content=content,
                    refusal=refusal,
                    reasoning_content=reasoning_content,
                    tool_calls=tool_calls,
                ),
                finish_reason=finish_reason,
            )
        ],
        usage=usage,
    )


def _tool_delta(*, index=0, call_id=None, name=None, arguments=None):
    return SimpleNamespace(
        index=index,
        id=call_id,
        function=SimpleNamespace(name=name, arguments=arguments),
    )


@pytest.mark.asyncio
async def test_generate_resolves_the_default_completion_token_limit() -> None:
    completions = FakeCompletions(_response())
    provider = OpenAIChatCompletionsProvider(
        client=FakeClient(completions),
    )

    await provider.generate(
        ModelRequest(
            messages=[{"role": "user", "content": "hello"}],
            model="test-model",
        )
    )

    assert completions.payload["max_completion_tokens"] == 16_384


@pytest.mark.asyncio
async def test_generate_builds_payload_and_normalizes_a_tool_response() -> None:
    completions = FakeCompletions(
        _response(
            content=None,
            tool_calls=[_tool_call()],
            finish_reason="tool_calls",
            reasoning="reasoning",
        )
    )
    provider = OpenAIChatCompletionsProvider(
        default_generation=GenerationConfig(
            temperature=0.2,
            max_completion_tokens=128,
            extra_body={"enable_thinking": True},
        ),
        client=FakeClient(completions),
    )

    result = await provider.generate(
        ModelRequest(
            model="gpt-test",
            messages=[
                {"role": "system", "content": "system", "ignored": True},
                {
                    "role": "tool",
                    "tool_call_id": "previous",
                    "name": "read_file",
                    "content": "contents",
                },
                {"role": "user", "content": ""},
            ],
            tools=[
                {
                    "type": "function",
                    "function": {
                        "name": "add",
                        "description": "Add numbers",
                        "parameters": {"type": "object"},
                    },
                }
            ],
        )
    )

    assert result.should_execute_tools
    assert result.tool_calls[0].arguments == {"a": 1, "b": 2}
    assert result.reasoning_content == "reasoning"
    assert result.usage == {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
    assert completions.payload["model"] == "gpt-test"
    assert completions.payload["temperature"] == 0.2
    assert completions.payload["max_completion_tokens"] == 128
    assert completions.payload["extra_body"] == {"enable_thinking": True}
    assert completions.payload["tool_choice"] == "auto"
    assert completions.payload["messages"] == [
        {"role": "system", "content": "system"},
        {
            "role": "tool",
            "tool_call_id": "previous",
            "name": "read_file",
            "content": "contents",
        },
        {"role": "user", "content": "(empty)"},
    ]


@pytest.mark.asyncio
async def test_generate_reports_invalid_tool_arguments_as_a_parse_error() -> None:
    provider = OpenAIChatCompletionsProvider(
        client=FakeClient(
            FakeCompletions(
                _response(
                    content=None,
                    tool_calls=[_tool_call(arguments="{bad json")],
                    finish_reason="tool_calls",
                )
            )
        )
    )

    result = await provider.generate(
        ModelRequest(messages=[{"role": "user", "content": "add"}], model="test-model")
    )

    assert result.error is not None
    assert result.error.code == "model_response_parse_error"
    assert "valid JSON" in result.error.message


@pytest.mark.asyncio
async def test_stream_aggregates_content_reasoning_tools_and_usage() -> None:
    usage = SimpleNamespace(prompt_tokens=10, completion_tokens=5, total_tokens=15)
    completions = FakeCompletions(
        FakeStream(
            [
                _stream_chunk(
                    content="hel",
                    reasoning_content="think ",
                    tool_calls=[
                        _tool_delta(call_id="call_add", name="add", arguments='{"a"')
                    ],
                ),
                _stream_chunk(
                    content="lo",
                    reasoning_content="more",
                    tool_calls=[_tool_delta(arguments=": 1}")],
                    finish_reason="tool_calls",
                    usage=usage,
                ),
            ]
        )
    )
    observed: dict[str, list[Any]] = {"content": [], "reasoning": [], "tools": []}

    async def content(delta):
        observed["content"].append(delta)

    async def reasoning(delta):
        observed["reasoning"].append(delta)

    async def tools(delta):
        observed["tools"].append(delta)

    result = await OpenAIChatCompletionsProvider(
        client=FakeClient(completions)
    ).generate_stream(
        ModelRequest(messages=[{"role": "user", "content": "hello"}], model="test-model"),
        callbacks=ModelStreamCallbacks(
            on_content_delta=content,
            on_reasoning_delta=reasoning,
            on_tool_call_delta=tools,
        ),
    )

    assert completions.payload["stream"] is True
    assert completions.payload["stream_options"] == {"include_usage": True}
    assert observed["content"] == ["hel", "lo"]
    assert observed["reasoning"] == ["think ", "more"]
    assert len(observed["tools"]) == 2
    assert result.content == "hello"
    assert result.reasoning_content == "think more"
    assert result.tool_calls[0].arguments == {"a": 1}
    assert result.usage["total_tokens"] == 15


@pytest.mark.asyncio
async def test_stream_supports_mapping_chunks_and_refusal_deltas() -> None:
    completions = FakeCompletions(
        FakeStream(
            [
                {"choices": [{"delta": {"content": "Hello"}, "finish_reason": None}], "usage": None},
                _stream_chunk(refusal="blocked", finish_reason="stop"),
                SimpleNamespace(choices=[], usage={"prompt_tokens": 2, "completion_tokens": 1, "total_tokens": 3}),
            ]
        )
    )
    refusals = []

    async def on_refusal(delta):
        refusals.append(delta)

    result = await OpenAIChatCompletionsProvider(
        client=FakeClient(completions)
    ).generate_stream(
        ModelRequest(messages=[{"role": "user", "content": "hello"}], model="test-model"),
        callbacks=ModelStreamCallbacks(on_refusal_delta=on_refusal),
    )

    assert result.content == "Hello"
    assert result.refusal == "blocked"
    assert refusals == ["blocked"]
    assert result.usage == {"prompt_tokens": 2, "completion_tokens": 1, "total_tokens": 3}


@pytest.mark.asyncio
async def test_stream_reports_an_incomplete_response() -> None:
    provider = OpenAIChatCompletionsProvider(
        client=FakeClient(FakeCompletions(FakeStream([_stream_chunk(content="partial")])))
    )

    result = await provider.generate_stream(
        ModelRequest(messages=[{"role": "user", "content": "hello"}], model="test-model")
    )

    assert result.content == "partial"
    assert result.error is not None
    assert result.error.code == "model_stream_incomplete"
    assert result.error.recoverable
    assert result.error_kind == "stream_incomplete"


@pytest.mark.asyncio
async def test_stream_retries_only_the_unsupported_stream_options_shape() -> None:
    unsupported = FakeAPIError(
        "unknown parameter: stream_options",
        status_code=400,
        body={"error": {"message": "unknown parameter: stream_options"}},
    )
    completions = FakeCompletions(
        effects=[
            unsupported,
            FakeStream([_stream_chunk(content="ok", finish_reason="stop")]),
        ]
    )

    result = await OpenAIChatCompletionsProvider(
        client=FakeClient(completions)
    ).generate_stream(
        ModelRequest(messages=[{"role": "user", "content": "hello"}], model="test-model")
    )

    assert result.content == "ok"
    assert completions.payloads[0]["stream_options"] == {"include_usage": True}
    assert "stream_options" not in completions.payloads[1]

    unrelated = FakeCompletions(
        error=FakeAPIError("invalid model", status_code=400, body={"error": {"message": "invalid model"}})
    )
    result = await OpenAIChatCompletionsProvider(
        client=FakeClient(unrelated)
    ).generate_stream(
        ModelRequest(messages=[{"role": "user", "content": "hello"}], model="test-model")
    )
    assert result.is_error
    assert len(unrelated.payloads) == 1


@pytest.mark.asyncio
async def test_stream_timeout_is_a_recoverable_model_error(monkeypatch) -> None:
    monkeypatch.setenv("BUMBLEHIVE_STREAM_IDLE_TIMEOUT_S", "0.001")
    provider = OpenAIChatCompletionsProvider(
        client=FakeClient(FakeCompletions(SlowStream()))
    )

    result = await provider.generate_stream(
        ModelRequest(messages=[{"role": "user", "content": "hello"}], model="test-model")
    )

    assert result.error is not None
    assert result.error.code == "model_timeout"
    assert result.error.recoverable
    assert result.error_kind == "timeout"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "code", "recoverable", "retry_after"),
    [
        (
            FakeAPIError(
                "quota",
                status_code=429,
                body={"error": {"type": "insufficient_quota", "code": "insufficient_quota"}},
            ),
            "model_quota_error",
            False,
            None,
        ),
        (
            FakeAPIError(
                "rate",
                status_code=429,
                body={"error": {"type": "rate_limit_error", "code": "rate_limit_exceeded"}},
                headers={"retry-after": "3"},
            ),
            "model_rate_limit",
            True,
            3.0,
        ),
        (
            FakeAPIError("server", status_code=500, headers={"x-should-retry": "false"}),
            "model_server_error",
            False,
            None,
        ),
        (FakeTimeoutError("timed out"), "model_timeout", True, None),
        (RuntimeError("network down"), "model_request_error", False, None),
    ],
)
async def test_generate_classifies_sdk_failures(error, code, recoverable, retry_after) -> None:
    provider = OpenAIChatCompletionsProvider(
        client=FakeClient(FakeCompletions(error=error))
    )

    result = await provider.generate(
        ModelRequest(messages=[{"role": "user", "content": "hello"}], model="test-model")
    )

    assert result.error is not None
    assert result.error.code == code
    assert result.error.recoverable is recoverable
    assert result.retry_after == retry_after


@pytest.mark.asyncio
async def test_close_releases_the_supplied_client() -> None:
    client = FakeClient(FakeCompletions(_response()))
    provider = OpenAIChatCompletionsProvider(client=client)

    await provider.close()

    assert client.closed
