from typing import Any

import pytest

from bumblehive.protocols.errors import AgentError
from bumblehive.providers import (
    ModelProvider,
    ModelRequest,
    ModelResponse,
    ModelStreamCallbacks,
    RetryConfig,
)
from bumblehive.providers.streaming import resolve_stream_idle_timeout_s


class StreamingProvider(ModelProvider):
    def __init__(
        self,
        responses: list[ModelResponse],
        *,
        delta_kind: str | None = None,
    ) -> None:
        self.responses = list(responses)
        self.delta_kind = delta_kind
        self.attempts = 0

    async def generate(self, request: ModelRequest) -> ModelResponse:
        return await self.generate_stream(request)

    async def generate_stream(
        self,
        request: ModelRequest,
        *,
        callbacks: ModelStreamCallbacks | None = None,
    ) -> ModelResponse:
        self.attempts += 1
        if callbacks is not None:
            if self.delta_kind == "content" and callbacks.on_content_delta:
                await callbacks.on_content_delta("hello")
            elif self.delta_kind == "refusal" and callbacks.on_refusal_delta:
                await callbacks.on_refusal_delta("blocked")
            elif self.delta_kind == "reasoning" and callbacks.on_reasoning_delta:
                await callbacks.on_reasoning_delta("thinking")
            elif self.delta_kind == "tool_call" and callbacks.on_tool_call_delta:
                await callbacks.on_tool_call_delta(
                    {
                        "index": 0,
                        "call_id": "call_1",
                        "name": "read_file",
                        "arguments_delta": '{"path":',
                    }
                )
        if self.responses:
            return self.responses.pop(0)
        return ModelResponse(content="fallback")


class NonStreamingProvider(ModelProvider):
    def __init__(self, responses: list[ModelResponse]) -> None:
        self.responses = list(responses)
        self.attempts = 0

    async def generate(self, request: ModelRequest) -> ModelResponse:
        self.attempts += 1
        if self.responses:
            return self.responses.pop(0)
        return ModelResponse(content="fallback")


def _recoverable_error_response() -> ModelResponse:
    return ModelResponse(
        content="temporary error",
        finish_reason="error",
        error=AgentError(
            code="model_rate_limit",
            message="try again",
            recoverable=True,
        ),
    )


def test_resolve_stream_idle_timeout_bounds_invalid_values() -> None:
    assert resolve_stream_idle_timeout_s(env_value=None, default=12) == 12
    assert resolve_stream_idle_timeout_s(env_value="bad", default=12) == 12
    assert resolve_stream_idle_timeout_s(env_value="-1", default=12) == 12
    assert resolve_stream_idle_timeout_s(
        env_value="9999",
        default=12,
        maximum=30,
    ) == 30


@pytest.mark.asyncio
async def test_streaming_retries_before_any_delta() -> None:
    provider = StreamingProvider(
        [
            _recoverable_error_response(),
            ModelResponse(content="ok"),
        ]
    )

    result = await provider.generate_stream_with_retry(
        ModelRequest(messages=[{"role": "user", "content": "hello"}], model="test-model"),
        callbacks=ModelStreamCallbacks(),
        retry=RetryConfig(max_retries=1, retry_delays=()),
    )

    assert result.content == "ok"
    assert provider.attempts == 2


@pytest.mark.asyncio
async def test_non_streaming_provider_reports_streaming_not_supported() -> None:
    provider = NonStreamingProvider(
        [
            _recoverable_error_response(),
            ModelResponse(content="ok"),
        ]
    )

    with pytest.raises(NotImplementedError, match="does not support streaming"):
        await provider.generate_stream_with_retry(
            ModelRequest(messages=[{"role": "user", "content": "hello"}], model="test-model"),
            callbacks=ModelStreamCallbacks(),
            retry=RetryConfig(max_retries=1, retry_delays=()),
        )

    assert provider.attempts == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("delta_kind", ["content", "refusal", "reasoning", "tool_call"])
async def test_streaming_does_not_retry_after_any_observed_delta(
    delta_kind: str,
) -> None:
    provider = StreamingProvider(
        [
            _recoverable_error_response(),
            ModelResponse(content="should not be used"),
        ],
        delta_kind=delta_kind,
    )
    observed: list[Any] = []

    async def on_content(delta: str) -> None:
        observed.append(("content", delta))

    async def on_refusal(delta: str) -> None:
        observed.append(("refusal", delta))

    async def on_reasoning(delta: str) -> None:
        observed.append(("reasoning", delta))

    async def on_tool_call(delta: dict[str, Any]) -> None:
        observed.append(("tool_call", delta))

    result = await provider.generate_stream_with_retry(
        ModelRequest(messages=[{"role": "user", "content": "hello"}], model="test-model"),
        callbacks=ModelStreamCallbacks(
            on_content_delta=on_content,
            on_refusal_delta=on_refusal,
            on_reasoning_delta=on_reasoning,
            on_tool_call_delta=on_tool_call,
        ),
        retry=RetryConfig(max_retries=1, retry_delays=()),
    )

    assert result.is_error
    assert provider.attempts == 1
    assert observed
