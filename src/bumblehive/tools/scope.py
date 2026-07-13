from contextvars import ContextVar, Token
from pathlib import Path

from ..paths import get_workspace_path


_CURRENT_TOOL_WORKSPACE: ContextVar[Path | None] = ContextVar(
    "bumblehive_tool_workspace",
    default=None,
)
_CURRENT_TOOL_SESSION_ID: ContextVar[str | None] = ContextVar(
    "bumblehive_tool_session_id",
    default=None,
)


def bind_tool_workspace(workspace: Path | str | None = None) -> Token[Path | None]:
    return _CURRENT_TOOL_WORKSPACE.set(get_workspace_path(workspace))


def reset_tool_workspace(token: Token[Path | None]) -> None:
    _CURRENT_TOOL_WORKSPACE.reset(token)


def current_tool_workspace() -> Path | None:
    return _CURRENT_TOOL_WORKSPACE.get()


def bind_tool_session(session_id: str) -> Token[str | None]:
    return _CURRENT_TOOL_SESSION_ID.set(session_id)


def reset_tool_session(token: Token[str | None]) -> None:
    _CURRENT_TOOL_SESSION_ID.reset(token)


def current_tool_session_id() -> str | None:
    return _CURRENT_TOOL_SESSION_ID.get()
