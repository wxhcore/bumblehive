"""Tool registration primitives."""

from .base import Tool
from .adapters.function import CallableTool
from .adapters.mcp import MCPToolWrapper
from .builtins import (
    register_builtin_tools,
    register_read_file_tool,
    register_shell_exec_tool,
    register_write_file_tool,
)
from .context import ToolContext
from .mcp import MCPManager, MCPServerConfig
from .policy import ToolPolicy
from .registry import ToolRegistry

__all__ = [
    "CallableTool",
    "MCPManager",
    "MCPServerConfig",
    "MCPToolWrapper",
    "Tool",
    "ToolContext",
    "ToolPolicy",
    "ToolRegistry",
    "register_builtin_tools",
    "register_read_file_tool",
    "register_shell_exec_tool",
    "register_write_file_tool",
]
