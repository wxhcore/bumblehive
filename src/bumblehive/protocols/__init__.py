"""Shared protocols used across Bumblehive subsystems."""

from .errors import AgentError
from .generation import GenerationConfig
from .mcp import MCPServerConfig
from .messages import Message, UserMessage, normalize_user_message
from .tool_approval import (
    ToolApprovalDecision,
    ToolApprovalHandler,
    ToolApprovalRequest,
)
from .tool_calls import ToolCall, ToolResult, parse_tool_call

__all__ = [
    "AgentError",
    "GenerationConfig",
    "MCPServerConfig",
    "Message",
    "ToolApprovalDecision",
    "ToolApprovalHandler",
    "ToolApprovalRequest",
    "ToolCall",
    "ToolResult",
    "UserMessage",
    "normalize_user_message",
    "parse_tool_call",
]
