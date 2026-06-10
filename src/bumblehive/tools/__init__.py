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
from .runtime import ToolRuntimeContext
from .manager import ToolManager
from .mcp import MCPManager, MCPServerConfig
from .policy import ToolPolicy
from .registry import ToolRegistry

__all__ = [
    "CallableTool",
    "MCPManager",
    "MCPServerConfig",
    "MCPToolWrapper",
    "Tool",
    "ToolRuntimeContext",
    "ToolManager",
    "ToolPolicy",
    "ToolRegistry",
    "register_builtin_tools",
    "register_read_file_tool",
    "register_shell_exec_tool",
    "register_write_file_tool",
]
