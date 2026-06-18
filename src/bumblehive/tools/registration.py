from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ToolRegistrationContext:
    """Context used when registering workspace-bound tools."""

    workspace: Path
    config: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "workspace", Path(self.workspace).expanduser().resolve())


@dataclass(frozen=True)
class ToolExecutionContext:
    """Per-execution context used to scope workspace-bound tool calls."""

    workspace: Path
    restrict_to_workspace: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "workspace", Path(self.workspace).expanduser().resolve())


_CURRENT_TOOL_EXECUTION_CONTEXT: ContextVar[ToolExecutionContext | None] = ContextVar(
    "bumblehive_tool_execution_context",
    default=None,
)


def bind_tool_execution_context(
    context: ToolExecutionContext,
) -> Token[ToolExecutionContext | None]:
    return _CURRENT_TOOL_EXECUTION_CONTEXT.set(context)


def reset_tool_execution_context(token: Token[ToolExecutionContext | None]) -> None:
    _CURRENT_TOOL_EXECUTION_CONTEXT.reset(token)


def current_tool_execution_context() -> ToolExecutionContext | None:
    return _CURRENT_TOOL_EXECUTION_CONTEXT.get()
