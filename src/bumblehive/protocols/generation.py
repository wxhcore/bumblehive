from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class GenerationConfig:
    """Provider-agnostic generation settings for one model request."""

    max_completion_tokens: int = 16384
    temperature: float | None = None
    reasoning_effort: str | None = None
    extra_body: dict[str, Any] | None = None
