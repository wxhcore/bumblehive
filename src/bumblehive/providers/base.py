import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from ..contracts.errors import AgentError
from ..tools.calls import ToolCall


@dataclass(frozen=True)
class GenerationConfig:
    """Provider-agnostic generation settings for one model request."""
    max_tokens: int = 8192
    temperature: float | None = None
    reasoning_effort: str | None = None


@dataclass(frozen=True)
class RetryConfig:
    """Provider-agnostic retry settings for recoverable model errors."""

    max_retries: int = 3
    retry_delays: tuple[float, ...] = (1.0, 2.0, 4.0)
    max_delay: float = 60.0
    respect_retry_after: bool = True


@dataclass(frozen=True)
class ModelRequest:
    """A single model request after context construction."""

    messages: list[dict[str, Any]]
    tools: list[dict[str, Any]] = field(default_factory=list)
    model: str | None = None
    generation: GenerationConfig | None = None
    tool_choice: str | dict[str, Any] | None = None


@dataclass(frozen=True)
class ModelResponse:
    """Provider-normalized model output."""

    content: str | None
    tool_calls: list[ToolCall] = field(default_factory=list)
    finish_reason: str = "stop"
    usage: dict[str, int] = field(default_factory=dict)
    refusal: str | None = None
    reasoning_content: str | None = None
    error: AgentError | None = None
    retry_after: float | None = None
    error_status_code: int | None = None
    error_kind: str | None = None
    error_type: str | None = None
    error_code: str | None = None

    @property
    def is_error(self) -> bool:
        return self.error is not None

    @property
    def should_execute_tools(self) -> bool:
        return bool(self.tool_calls) and self.finish_reason in {"tool_calls", "stop"}


class ModelProvider(ABC):
    """Base interface for model providers."""

    @abstractmethod
    async def generate(self, request: ModelRequest) -> ModelResponse:
        """Generate one non-streaming model response."""
        ...

    async def generate_with_retry(
        self,
        request: ModelRequest,
        *,
        retry: RetryConfig | None = None,
    ) -> ModelResponse:
        """Return one model response, retrying recoverable provider errors.

        The default implementation is intentionally provider-agnostic: concrete
        providers classify errors on ``ModelResponse.error.recoverable`` and may
        attach ``retry_after``. This wrapper only decides whether and when to
        repeat the same request.
        """
        config = retry or RetryConfig()
        max_retries = max(0, config.max_retries)
        response: ModelResponse | None = None

        for attempt in range(max_retries + 1):
            response = await self.generate(request)
            if not self._should_retry_response(response):
                return response
            if attempt >= max_retries:
                return response

            delay = self._retry_delay(response, attempt + 1, config)
            if delay > 0:
                await asyncio.sleep(delay)

        # Unreachable, but keeps type checkers happy if the loop shape changes.
        assert response is not None
        return response

    @staticmethod
    def _should_retry_response(response: ModelResponse) -> bool:
        return bool(response.error and response.error.recoverable)

    @staticmethod
    def _retry_delay(
        response: ModelResponse,
        retry_index: int,
        config: RetryConfig,
    ) -> float:
        if (
            config.respect_retry_after
            and response.retry_after is not None
            and response.retry_after > 0
        ):
            return min(response.retry_after, max(0.0, config.max_delay))

        if not config.retry_delays:
            return 0.0

        delay = config.retry_delays[
            min(max(0, retry_index - 1), len(config.retry_delays) - 1)
        ]
        return min(max(0.0, delay), max(0.0, config.max_delay))

    async def close(self) -> None:
        """Release provider-owned resources."""
        pass
