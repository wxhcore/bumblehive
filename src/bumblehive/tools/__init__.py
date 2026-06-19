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
from .calls import ToolCall, ToolResult, parse_tool_call
from .scope import ToolScope
from .registration import ToolRegistrationContext
from .executor import ToolExecutor
from .manager import ToolManager
from .mcp import MCPManager, MCPServerConfig, MCPServerStatus
from .policy import ToolPolicy
from .registry import ToolRegistry

__all__ = [
    "CallableTool",
    "MCPManager",
    "MCPServerConfig",
    "MCPServerStatus",
    "MCPToolWrapper",
    "Tool",
    "ToolCall",
    "ToolExecutor",
    "ToolResult",
    "ToolScope",
    "ToolRegistrationContext",
    "ToolManager",
    "ToolPolicy",
    "ToolRegistry",
    "parse_tool_call",
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
