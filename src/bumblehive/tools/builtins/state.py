from dataclasses import dataclass, field
from typing import Any

from .workspace import FileStates


@dataclass
class BuiltinToolState:
    """Shared runtime objects for one built-in tool registration set."""

    file_states: FileStates = field(default_factory=FileStates)
    workspace_files: Any | None = None
    exec_session_manager: Any | None = None
