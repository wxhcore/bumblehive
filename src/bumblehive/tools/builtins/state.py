from collections.abc import Callable
from dataclasses import dataclass, field
from functools import wraps
from typing import Any

from ..scope import current_tool_session_id
from .workspace import FileStateStore, bind_file_states, reset_file_states


@dataclass
class BuiltinToolState:
    """Shared runtime objects for one built-in tool registration set."""

    file_state_store: FileStateStore = field(default_factory=FileStateStore)
    workspace_files: Any | None = None
    exec_session_manager: Any | None = None


def _session_scoped_file_handler(
    state: BuiltinToolState,
    handler: Callable[..., Any],
) -> Callable[..., Any]:
    """Bind one stable per-session FileStates object for a tool call."""

    @wraps(handler)
    def wrapped(**kwargs: Any) -> Any:
        file_states = state.file_state_store.for_session(current_tool_session_id())
        token = bind_file_states(file_states)
        try:
            return handler(**kwargs)
        finally:
            reset_file_states(token)

    return wrapped
