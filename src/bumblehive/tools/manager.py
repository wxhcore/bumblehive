from collections.abc import Callable, Iterable
from types import TracebackType
from typing import Any

from ..schemas.tool_calls import ToolCall, ToolResult
from ..tool_calls.executor import ToolExecutor
from .base import Tool
from .builtins import register_builtin_tools
from .runtime import ToolRuntimeContext
from .mcp import MCPManager, MCPServerConfig
from .policy import ToolPolicy
from .registry import ToolRegistry


class ToolManager:
    """Facade that coordinates tool registration, discovery, MCP, and execution."""

    def __init__(
        self,
        *,
        registry: ToolRegistry | None = None,
        context: ToolRuntimeContext | None = None,
        builtin_policy: ToolPolicy | None = None,
        mcp_servers: list[MCPServerConfig] | None = None,
        mcp_policy: ToolPolicy | None = None,
    ) -> None:
        self.registry = registry or ToolRegistry()
        self.context = context
        self.builtin_policy = builtin_policy or ToolPolicy()
        self.mcp_manager = MCPManager(
            self.registry,
            servers=mcp_servers,
            policy=mcp_policy,
        )

    async def __aenter__(self) -> "ToolManager":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.close()

    @property
    def tool(self) -> Callable[..., Any]:
        """Return the registry decorator for local Python function tools."""
        return self.registry.tool

    @property
    def tool_names(self) -> list[str]:
        return self.registry.tool_names

    @property
    def registered_mcp_tool_names(self) -> dict[str, list[str]]:
        return self.mcp_manager.registered_mcp_tool_names

    def register(self, tool: Tool) -> Tool:
        """Register an already constructed Tool object."""
        return self.registry.register(tool)

    def unregister(self, name: str) -> None:
        self.registry.unregister(name)

    def register_builtin_tools(self) -> list[str]:
        """Register built-in local tools using the configured context and policy."""
        if self.context is None:
            raise ValueError("ToolRuntimeContext is required to register built-in tools")
        return register_builtin_tools(
            self.registry,
            self.context,
            policy=self.builtin_policy,
        )

    async def connect_mcp(self) -> list[str]:
        """Connect configured MCP servers and register their enabled tools."""
        return await self.mcp_manager.connect_all()

    async def connect_mcp_server(self, server: MCPServerConfig) -> list[str]:
        """Connect one MCP server and register its enabled tools."""
        return await self.mcp_manager.connect_server(server)

    def list_tools(self, tool_names: Iterable[str] | None = None) -> list[Tool]:
        """Return registered Tool objects, optionally filtered by name."""
        return self.registry.list_tools(tool_names)

    def get_openai_tool_definitions(
        self,
        tool_names: Iterable[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Return OpenAI-compatible tool definitions for a model request."""
        return self.registry.get_openai_tool_definitions(tool_names)

    async def execute_call(
        self,
        call: ToolCall,
        *,
        allowed_tool_names: Iterable[str] | None = None,
    ) -> ToolResult:
        executor = ToolExecutor(self.registry, allowed_tool_names=allowed_tool_names)
        return await executor.execute_call(call)

    async def execute_many(
        self,
        calls: list[ToolCall],
        *,
        allowed_tool_names: Iterable[str] | None = None,
    ) -> list[ToolResult]:
        executor = ToolExecutor(self.registry, allowed_tool_names=allowed_tool_names)
        return await executor.execute_many(calls)

    async def close_mcp_server(self, server_name: str) -> None:
        """Close one MCP server connection and unregister its tools."""
        await self.mcp_manager.close_server(server_name)

    async def close_mcp(self) -> None:
        """Close all MCP server connections and unregister their tools."""
        await self.mcp_manager.close_all()

    async def close(self) -> None:
        """Release all resources owned by this manager."""
        await self.close_mcp()
