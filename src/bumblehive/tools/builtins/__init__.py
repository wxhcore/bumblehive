"""Built-in tool registrations."""

from ..runtime import ToolRuntimeContext
from ..policy import ToolPolicy
from ..registry import ToolRegistry
from .file import (
    register_read_file_tool,
    register_write_file_tool,
)
from .shell import register_shell_exec_tool


def register_builtin_tools(
    registry: ToolRegistry,
    context: ToolRuntimeContext,
    *,
    policy: ToolPolicy | None = None,
) -> list[str]:
    """Register built-in local tools according to the startup policy."""
    policy = policy or ToolPolicy()
    registered: list[str] = []

    if policy.allows_tool("read_file"):
        registered.append(register_read_file_tool(registry, context).name)
    if policy.allows_tool("write_file"):
        registered.append(register_write_file_tool(registry, context).name)
    if policy.allows_tool("shell_exec"):
        registered.append(register_shell_exec_tool(registry, context).name)

    return registered


__all__ = [
    "register_builtin_tools",
    "register_read_file_tool",
    "register_shell_exec_tool",
    "register_write_file_tool",
]
