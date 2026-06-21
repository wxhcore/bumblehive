"""Tool registration primitives."""

from .base import Tool
from .adapters.function import CallableTool
from .adapters.mcp import MCPToolWrapper
from .builtins import register_builtin_tools
from .calls import ToolCall, ToolResult, parse_tool_call
from .scope import ToolScope
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
    "ToolManager",
    "ToolPolicy",
    "ToolRegistry",
    "parse_tool_call",
    "register_builtin_tools",
]
