"""Built-in tool registrations."""

from typing import Any

from ..registry import ToolRegistry
from .state import BuiltinToolState
from .file import (
    register_edit_file_tool,
    register_list_dir_tool,
    register_read_file_tool,
    register_write_file_tool,
)
from .patch import register_apply_patch_tool
from .search import register_find_files_tool, register_grep_tool
from .shell import (
    register_exec_tool,
    register_list_exec_sessions_tool,
    register_write_stdin_tool,
)


def register_builtin_tools(
    registry: ToolRegistry,
    *,
    config: dict[str, Any] | None = None,
) -> list[str]:
    """Register all built-in local tools."""
    return _register_builtin_tools(
        registry,
        config=config,
        state=BuiltinToolState(),
    )


def _register_builtin_tools(
    registry: ToolRegistry,
    *,
    config: dict[str, Any] | None = None,
    state: BuiltinToolState,
) -> list[str]:
    """Register built-in local tools with caller-owned internal state."""
    config = config or {}
    return [
        register_read_file_tool(registry, state=state).name,
        register_write_file_tool(registry, state=state).name,
        register_list_dir_tool(registry, state=state).name,
        register_find_files_tool(registry).name,
        register_grep_tool(registry).name,
        register_edit_file_tool(registry, state=state).name,
        register_apply_patch_tool(registry, state=state).name,
        register_exec_tool(registry, config=config, state=state).name,
        register_write_stdin_tool(registry, config=config, state=state).name,
        register_list_exec_sessions_tool(registry, config=config, state=state).name,
    ]


__all__ = [
    "register_builtin_tools",
]
