from contextvars import ContextVar, Token
from dataclasses import dataclass
from pathlib import Path

from ..config import get_workspace_path


@dataclass(frozen=True)
class ToolScope:
    """Per-execution scope used to bound workspace-aware tool calls."""

    workspace: Path | str | None = None
    restrict_to_workspace: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "workspace", get_workspace_path(self.workspace))


_CURRENT_TOOL_SCOPE: ContextVar[ToolScope | None] = ContextVar(
    "bumblehive_tool_scope",
    default=None,
)


def bind_tool_scope(scope: ToolScope) -> Token[ToolScope | None]:
    return _CURRENT_TOOL_SCOPE.set(scope)


def reset_tool_scope(token: Token[ToolScope | None]) -> None:
    _CURRENT_TOOL_SCOPE.reset(token)


def current_tool_scope() -> ToolScope | None:
    return _CURRENT_TOOL_SCOPE.get()
