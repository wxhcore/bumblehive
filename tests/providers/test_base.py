from typing import Any

import pytest

from bumblehive.protocols.errors import AgentError
from bumblehive.providers import ModelProvider, ModelRequest, ModelResponse, RetryConfig


class SequenceProvider(ModelProvider):
    def __init__(self, responses: list[ModelResponse]) -> None:
        self.responses = list(responses)
        self.requests: list[ModelRequest] = []

    async def generate(self, request: ModelRequest) -> ModelResponse:
        self.requests.append(request)
        if self.responses:
            return self.responses.pop(0)
        return ModelResponse(content="fallback")


def _error_response(
    *,
    recoverable: bool,
    retry_after: float | None = None,
) -> ModelResponse:
    return ModelResponse(
        content="error",
        finish_reason="error",
        retry_after=retry_after,
        error=AgentError(
            code="model_error",
            message="model failed",
            recoverable=recoverable,
        ),
    )


@pytest.mark.asyncio
async def test_generate_with_retry_returns_success_without_retry() -> None:
    request = ModelRequest(messages=[{"role": "user", "content": "hello"}], model="test-model")
    provider = SequenceProvider([ModelResponse(content="ok")])

    result = await provider.generate_with_retry(
        request,
        retry=RetryConfig(max_retries=3, retry_delays=(0.0,)),
    )

    assert result.content == "ok"
    assert provider.requests == [request]


@pytest.mark.asyncio
async def test_generate_with_retry_retries_recoverable_errors() -> None:
    request = ModelRequest(messages=[{"role": "user", "content": "hello"}], model="test-model")
    provider = SequenceProvider(
        [
            _error_response(recoverable=True),
            ModelResponse(content="ok"),
        ]
    )

    result = await provider.generate_with_retry(
        request,
        retry=RetryConfig(max_retries=3, retry_delays=(0.0,)),
    )

    assert result.content == "ok"
    assert provider.requests == [request, request]


@pytest.mark.asyncio
async def test_generate_with_retry_does_not_retry_non_recoverable_errors() -> None:
    request = ModelRequest(messages=[{"role": "user", "content": "hello"}], model="test-model")
    provider = SequenceProvider(
        [
            _error_response(recoverable=False),
            ModelResponse(content="ok"),
        ]
    )

    result = await provider.generate_with_retry(
        request,
        retry=RetryConfig(max_retries=3, retry_delays=(0.0,)),
    )

    assert result.is_error
    assert provider.requests == [request]


@pytest.mark.asyncio
async def test_generate_with_retry_returns_last_recoverable_error_after_limit() -> None:
    request = ModelRequest(messages=[{"role": "user", "content": "hello"}], model="test-model")
    provider = SequenceProvider(
        [
            _error_response(recoverable=True),
            _error_response(recoverable=True),
            ModelResponse(content="too late"),
        ]
    )

    result = await provider.generate_with_retry(
        request,
        retry=RetryConfig(max_retries=1, retry_delays=(0.0,)),
    )

    assert result.is_error
    assert provider.requests == [request, request]


@pytest.mark.asyncio
async def test_generate_with_retry_uses_retry_after(monkeypatch: Any) -> None:
    sleeps: list[float] = []

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    from bumblehive.providers import base as base_module

    monkeypatch.setattr(base_module.asyncio, "sleep", fake_sleep)

    request = ModelRequest(messages=[{"role": "user", "content": "hello"}], model="test-model")
    provider = SequenceProvider(
        [
            _error_response(recoverable=True, retry_after=5.0),
            ModelResponse(content="ok"),
        ]
    )

    result = await provider.generate_with_retry(
        request,
        retry=RetryConfig(max_retries=1, retry_delays=(1.0,), max_delay=3.0),
    )

    assert result.content == "ok"
    assert sleeps == [3.0]
