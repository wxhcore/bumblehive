"""Shared protocols used across Bumblehive subsystems."""

from .errors import AgentError
from .generation import GenerationConfig
from .mcp import MCPServerConfig
from .tool_calls import ToolCall, ToolResult, parse_tool_call

__all__ = [
    "AgentError",
    "GenerationConfig",
    "MCPServerConfig",
    "ToolCall",
    "ToolResult",
    "parse_tool_call",
]
