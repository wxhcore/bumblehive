from collections.abc import Callable, Sequence
from pathlib import Path
from types import TracebackType
from typing import Any, Mapping

from ..observability.emitter import EventEmitter
from ..protocols import MCPServerConfig
from ..protocols.errors import AgentError
from ..protocols.tool_calls import ToolCall, ToolResult
from .base import Tool
from .builtins import _register_builtin_tools
from .builtins.state import BuiltinToolState
from .executor import ToolExecutor
from .mcp.manager import MCPManager, MCPServerStatus
from .registry import ToolRegistry
from .scope import ToolPathPolicy, bind_tool_path_scope, reset_tool_path_scope


class ToolManager:
    """Facade that coordinates tool registration, discovery, MCP, and execution."""

    def __init__(
        self,
        *,
        registry: ToolRegistry | None = None,
        builtin_config: Mapping[str, Any] | None = None,
        mcp_servers: list[MCPServerConfig] | None = None,
    ) -> None:
        self.registry = registry or ToolRegistry()
        self.builtin_config = dict(builtin_config or {})
        self._builtin_state = BuiltinToolState()
        self._builtin_tools_registered = False
        self.mcp_manager = MCPManager(
            self.registry,
            servers=mcp_servers,
        )
        self._executor = ToolExecutor(self.registry)

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
        """Register built-in local tools using manager-owned config and state."""
        if self._builtin_tools_registered:
            return []

        registered = _register_builtin_tools(
            self.registry,
            config=self.builtin_config,
            state=self._builtin_state,
        )
        self._builtin_tools_registered = True
        return registered

    async def connect_mcp(self) -> list[str]:
        """Connect configured MCP servers and register their enabled tools."""
        return await self.mcp_manager.connect_all()

    def set_mcp_server(self, server: MCPServerConfig) -> None:
        """Add or replace one MCP server configuration without connecting it."""
        self.mcp_manager.set_server(server)

    async def remove_mcp_server(self, server_name: str) -> None:
        """Close and forget one MCP server configuration."""
        await self.mcp_manager.remove_server(server_name)

    def get_mcp_server_config(self, server_name: str) -> MCPServerConfig | None:
        """Return one configured MCP server by name."""
        return self.mcp_manager.get_server_config(server_name)

    def list_mcp_server_configs(self) -> list[MCPServerConfig]:
        """Return all configured MCP servers."""
        return self.mcp_manager.list_server_configs()

    def get_mcp_server_status(self, server_name: str) -> MCPServerStatus | None:
        """Return one MCP server status by name."""
        return self.mcp_manager.get_server_status(server_name)

    def list_mcp_server_statuses(self) -> list[MCPServerStatus]:
        """Return runtime status for all configured MCP servers."""
        return self.mcp_manager.list_server_statuses()

    async def connect_mcp_server(self, server: MCPServerConfig | str) -> list[str]:
        """Connect one MCP server and register its enabled tools."""
        return await self.mcp_manager.connect_server(server)

    async def reload_mcp(self) -> list[str]:
        """Reconnect configured MCP servers and rebuild their registered tools."""
        return await self.mcp_manager.reload_all()

    async def reload_mcp_server(self, server_name: str) -> list[str]:
        """Reconnect one MCP server and rebuild its registered tools."""
        return await self.mcp_manager.reload_server(server_name)

    async def sync_mcp_servers(
        self,
        servers: Sequence[MCPServerConfig],
    ) -> list[str]:
        """Make configured MCP servers match ``servers``.

        If the configuration is unchanged, connected servers are left alone.
        If the configuration changed, existing MCP connections are closed,
        removed server configs are forgotten, new configs are stored, and the
        current server set is connected.
        """
        next_servers = list(servers)
        if next_servers == self.list_mcp_server_configs():
            return await self._connect_disconnected_mcp_servers()

        await self.close_mcp()
        next_names = {server.name for server in next_servers}
        for server in list(self.list_mcp_server_configs()):
            if server.name not in next_names:
                await self.remove_mcp_server(server.name)

        for server in next_servers:
            self.set_mcp_server(server)

        return await self.connect_mcp()

    async def _connect_disconnected_mcp_servers(self) -> list[str]:
        registered: list[str] = []
        statuses = {
            status.name: status
            for status in self.list_mcp_server_statuses()
        }
        for server in self.list_mcp_server_configs():
            status = statuses.get(server.name)
            if status is None or status.connected:
                continue
            registered.extend(await self.connect_mcp_server(server.name))
        return registered

    def get_tool(self, name: str) -> Tool | None:
        """Return one registered Tool object by name."""
        return self.registry.get_tool(name)

    def get_tools(self, tool_names: list[str]) -> list[Tool]:
        """Return registered Tool objects filtered by name."""
        return self.registry.get_tools(tool_names)

    def list_tools(self) -> list[Tool]:
        """Return all registered Tool objects."""
        return self.registry.list_tools()

    def get_openai_tool_definitions(
        self,
        tool_names: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Return OpenAI-compatible tool definitions for a model request.

        ``tool_names=None`` returns all tools, ``[]`` returns none, and a
        non-empty list returns only the named tools in the given order.
        """
        return self.registry.get_openai_tool_definitions(tool_names)

    async def execute_call(
        self,
        call: ToolCall,
        *,
        tool_names: list[str] | None = None,
        workspace: Path | str | None = None,
        path_policy: ToolPathPolicy = ToolPathPolicy(),
        emitter: EventEmitter | None = None,
    ) -> ToolResult:
        """Execute one tool call with a run-scoped built-in path policy.

        Custom Python and MCP tools are responsible for enforcing their own
        filesystem access rules.
        """
        allowed = None if tool_names is None else frozenset(tool_names)
        return await self._execute_call(
            call,
            allowed=allowed,
            workspace=workspace,
            path_policy=path_policy,
            emitter=emitter,
        )

    async def _execute_call(
        self,
        call: ToolCall,
        *,
        allowed: frozenset[str] | None,
        workspace: Path | str | None,
        path_policy: ToolPathPolicy,
        emitter: EventEmitter | None,
    ) -> ToolResult:
        if allowed is not None and call.name not in allowed:
            return ToolResult(
                call_id=call.id,
                name=call.name,
                error=AgentError(
                    code="tool_not_allowed",
                    message=(
                        f"Tool '{call.name}' was not exposed in this model request."
                    ),
                ),
            )

        try:
            token = bind_tool_path_scope(workspace, path_policy)
        except Exception as exc:
            return ToolResult(
                call_id=call.id,
                name=call.name,
                error=AgentError(
                    code="tool_execution_error",
                    message=f"Error executing tool '{call.name}': {exc}",
                ),
            )

        try:
            return await self._executor.execute_call(call, emitter=emitter)
        finally:
            reset_tool_path_scope(token)

    async def execute_many(
        self,
        calls: list[ToolCall],
        *,
        tool_names: list[str] | None = None,
        workspace: Path | str | None = None,
        path_policy: ToolPathPolicy = ToolPathPolicy(),
        emitter: EventEmitter | None = None,
    ) -> list[ToolResult]:
        """Execute tool calls with one run-scoped built-in path policy.

        Custom Python and MCP tools are responsible for enforcing their own
        filesystem access rules.
        """
        emitter = emitter or EventEmitter.noop()
        allowed = None if tool_names is None else frozenset(tool_names)

        async def run(call: ToolCall) -> ToolResult:
            return await self._execute_call(
                call,
                allowed=allowed,
                workspace=workspace,
                path_policy=path_policy,
                emitter=emitter,
            )

        return await self._executor.execute_many(calls, call_runner=run)

    async def close_mcp_server(self, server_name: str) -> None:
        """Close one MCP server connection and unregister its tools."""
        await self.mcp_manager.close_server(server_name)

    async def close_mcp(self) -> None:
        """Close all MCP server connections and unregister their tools."""
        await self.mcp_manager.close_all()

    async def close(self) -> None:
        """Release all resources owned by this manager."""
        exec_session_manager = self._builtin_state.exec_session_manager
        try:
            if exec_session_manager is not None:
                await exec_session_manager.close()
        finally:
            await self.close_mcp()
