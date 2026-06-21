"""Built-in tool registrations."""

from typing import Any

from ..policy import ToolPolicy
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
    policy: ToolPolicy | None = None,
) -> list[str]:
    """Register built-in local tools according to the startup policy."""
    return _register_builtin_tools(
        registry,
        config=config,
        state=BuiltinToolState(),
        policy=policy,
    )


def _register_builtin_tools(
    registry: ToolRegistry,
    *,
    config: dict[str, Any] | None = None,
    state: BuiltinToolState,
    policy: ToolPolicy | None = None,
) -> list[str]:
    """Register built-in local tools with caller-owned internal state."""
    policy = policy or ToolPolicy()
    config = config or {}
    registered: list[str] = []

    if policy.allows_tool("read_file"):
        registered.append(register_read_file_tool(registry, state=state).name)
    if policy.allows_tool("write_file"):
        registered.append(register_write_file_tool(registry, state=state).name)
    if policy.allows_tool("list_dir"):
        registered.append(register_list_dir_tool(registry, state=state).name)
    if policy.allows_tool("find_files"):
        registered.append(register_find_files_tool(registry).name)
    if policy.allows_tool("grep"):
        registered.append(register_grep_tool(registry).name)
    if policy.allows_tool("edit_file"):
        registered.append(register_edit_file_tool(registry, state=state).name)
    if policy.allows_tool("apply_patch"):
        registered.append(register_apply_patch_tool(registry, state=state).name)
    if policy.allows_tool("exec"):
        registered.append(register_exec_tool(registry, config=config, state=state).name)
    if policy.allows_tool("write_stdin"):
        registered.append(
            register_write_stdin_tool(registry, config=config, state=state).name
        )
    if policy.allows_tool("list_exec_sessions"):
        registered.append(
            register_list_exec_sessions_tool(registry, config=config, state=state).name
        )

    return registered


__all__ = [
    "register_builtin_tools",
]
