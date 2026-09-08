"""Tool registration primitives."""

from ..protocols import (
    ToolApprovalDecision,
    ToolApprovalHandler,
    ToolApprovalRequest,
)
from .adapters.function import CallableTool
from .base import Tool
from .manager import ToolManager
from .mcp.manager import MCPServerStatus
from .registry import ToolRegistry
from .scope import ToolPathPolicy

__all__ = [
    "CallableTool",
    "MCPServerStatus",
    "ToolApprovalDecision",
    "ToolApprovalHandler",
    "ToolApprovalRequest",
    "ToolPathPolicy",
    "Tool",
    "ToolManager",
    "ToolRegistry",
]
