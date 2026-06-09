"""Adapters that expose executable backends as tools."""

from .function import CallableTool
from .mcp import MCPToolWrapper

__all__ = ["CallableTool", "MCPToolWrapper"]
