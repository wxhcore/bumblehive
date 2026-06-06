from dataclasses import dataclass
from typing import Any

from .errors import AgentError


@dataclass(frozen=True)
class ToolCall:
    """A parsed tool call ready for registry execution."""

    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class ToolResult:
    """Result of executing a tool call."""

    call_id: str
    name: str
    content: Any = None
    error: AgentError | None = None

    @property
    def is_error(self) -> bool:
        return self.error is not None
