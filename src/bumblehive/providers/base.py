from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from ..agent.types import AgentError
from ..tools.calls import ToolCall


@dataclass(frozen=True)
class GenerationConfig:
    """Provider-agnostic generation settings for one model request."""
    max_tokens: int = 8192
    temperature: float | None = None
    reasoning_effort: str | None = None


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
        return bool(self.tool_calls) and self.finish_reason == "tool_calls"


class ModelProvider(ABC):
    """Base interface for model providers."""

    @abstractmethod
    async def complete(self, request: ModelRequest) -> ModelResponse:
        """Return one non-streaming model response."""
        ...
