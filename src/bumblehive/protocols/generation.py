from dataclasses import dataclass
from typing import Any


DEFAULT_MAX_COMPLETION_TOKENS = 16_384


@dataclass(frozen=True)
class GenerationConfig:
    """Provider-agnostic generation settings for one model request."""

    max_completion_tokens: int | None = None
    temperature: float | None = None
    reasoning_effort: str | None = None
    extra_body: dict[str, Any] | None = None

    @property
    def effective_max_completion_tokens(self) -> int:
        """Return the effective positive completion-token limit."""
        if self.max_completion_tokens is None:
            return DEFAULT_MAX_COMPLETION_TOKENS
        return max(1, self.max_completion_tokens)
