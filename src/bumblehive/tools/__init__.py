"""Tool registration primitives."""

from .base import Tool
from .adapters.function import CallableTool
from .adapters.mcp import MCPToolWrapper
from .builtins import register_builtin_tools
from .executor import ToolExecutor
from .manager import ToolManager
from .mcp import MCPManager, MCPServerStatus
from .registry import ToolRegistry
from .scope import PathAllowlist

__all__ = [
    "CallableTool",
    "MCPManager",
    "MCPServerStatus",
    "MCPToolWrapper",
    "PathAllowlist",
    "Tool",
    "ToolExecutor",
    "ToolManager",
    "ToolRegistry",
    "register_builtin_tools",
]
