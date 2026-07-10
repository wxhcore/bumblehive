from contextvars import ContextVar, Token
from pathlib import Path

from ..paths import get_workspace_path


_CURRENT_TOOL_WORKSPACE: ContextVar[Path | None] = ContextVar(
    "bumblehive_tool_workspace",
    default=None,
)
_DEFAULT_TOOL_SESSION_ID = "default"
_CURRENT_TOOL_SESSION_ID: ContextVar[str] = ContextVar(
    "bumblehive_tool_session_id",
    default=_DEFAULT_TOOL_SESSION_ID,
)


def bind_tool_workspace(workspace: Path | str | None = None) -> Token[Path | None]:
    return _CURRENT_TOOL_WORKSPACE.set(get_workspace_path(workspace))


def reset_tool_workspace(token: Token[Path | None]) -> None:
    _CURRENT_TOOL_WORKSPACE.reset(token)


def current_tool_workspace() -> Path | None:
    return _CURRENT_TOOL_WORKSPACE.get()


def bind_tool_session(session_id: str | None = None) -> Token[str]:
    return _CURRENT_TOOL_SESSION_ID.set(session_id or _DEFAULT_TOOL_SESSION_ID)


def reset_tool_session(token: Token[str]) -> None:
    _CURRENT_TOOL_SESSION_ID.reset(token)


def current_tool_session_id() -> str:
    return _CURRENT_TOOL_SESSION_ID.get()
