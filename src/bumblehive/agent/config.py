from dataclasses import dataclass
from typing import Any

from ..providers.base import GenerationConfig, RetryConfig


@dataclass(frozen=True)
class AgentRunConfig:
    """Stable settings for agent runner and loop execution."""

    model: str
    generation: GenerationConfig | None = None
    retry: RetryConfig | None = None
    max_iterations: int = 300
    max_tool_result_chars: int | None = 20_000
    tool_choice: str | dict[str, Any] | None = "auto"
    max_iterations_message: str = (
        "I reached the maximum number of tool iterations before producing "
        "a final response."
    )
