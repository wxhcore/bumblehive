"""Tool registration primitives."""

from .base import Tool
from .adapters.function import CallableTool
from .adapters.mcp import MCPToolWrapper
from .builtins import (
    register_builtin_tools,
    register_apply_patch_tool,
    register_edit_file_tool,
    register_exec_tool,
    register_find_files_tool,
    register_grep_tool,
    register_list_exec_sessions_tool,
    register_list_dir_tool,
    register_read_file_tool,
    register_write_stdin_tool,
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
    "register_apply_patch_tool",
    "register_builtin_tools",
    "register_edit_file_tool",
    "register_exec_tool",
    "register_find_files_tool",
    "register_grep_tool",
    "register_list_exec_sessions_tool",
    "register_list_dir_tool",
    "register_read_file_tool",
    "register_write_stdin_tool",
    "register_write_file_tool",
]
