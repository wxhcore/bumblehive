import re
from contextlib import AsyncExitStack
from dataclasses import dataclass

from fastmcp import Client
from fastmcp.client.transports import SSETransport, StreamableHttpTransport, infer_transport
from mcp.types import Tool as MCPToolDefinition

from ...protocols.mcp import MCPServerConfig
from ..adapters.mcp import MCPToolWrapper
from ..registry import ToolRegistry


@dataclass(frozen=True)
class MCPServerStatus:
    """Runtime status for one configured MCP server."""

    name: str
    connected: bool
    registered_tools: list[str]
    config: MCPServerConfig


def sanitize_mcp_tool_name(name: str) -> str:
    """Return a provider-safe tool name."""
    sanitized = re.sub(r"[^a-zA-Z0-9_-]", "_", name)
    return re.sub(r"_+", "_", sanitized).strip("_")


def mcp_tool_name(server_name: str, tool_name: str) -> str:
    """Build the stable Bumblehive name for an MCP tool."""
    return sanitize_mcp_tool_name(f"mcp_{server_name}_{tool_name}")


def _fastmcp_client_transport(
    server: MCPServerConfig,
) -> str | SSETransport | StreamableHttpTransport:
    """Return the transport argument expected by fastmcp.Client."""
    if not server.headers:
        return server.url

    transport = infer_transport(server.url)
    if not isinstance(transport, (SSETransport, StreamableHttpTransport)):
        raise ValueError(
            "MCP server headers are only supported for HTTP or SSE transports"
        )
    transport.headers = server.headers
    return transport


def _is_enabled_tool(server: MCPServerConfig, original_name: str, wrapped_name: str) -> bool:
    enabled_tools = set(server.enabled_tools)
    return (
        "*" in enabled_tools
        or original_name in enabled_tools
        or wrapped_name in enabled_tools
    )


class MCPManager:
    """Connect MCP servers and register their tools."""

    def __init__(
        self,
        registry: ToolRegistry,
        servers: list[MCPServerConfig] | None = None,
    ) -> None:
        self.registry = registry
        self._server_configs: dict[str, MCPServerConfig] = {
            server.name: server for server in servers or []
        }
        self._stacks: dict[str, AsyncExitStack] = {}
        self._registered_mcp_tool_names: dict[str, list[str]] = {}

    @property
    def registered_mcp_tool_names(self) -> dict[str, list[str]]:
        """Return locally registered MCP tool names grouped by server name."""
        return {
            server_name: list(tool_names)
            for server_name, tool_names in self._registered_mcp_tool_names.items()
        }

    async def connect_all(self) -> list[str]:
        """Connect every configured MCP server and register its tools."""
        registered: list[str] = []
        for server in self.list_server_configs():
            registered.extend(await self.connect_server(server))
        return registered

    def set_server(self, server: MCPServerConfig) -> None:
        """Add or replace one MCP server configuration without connecting it."""
        self._server_configs[server.name] = server

    async def remove_server(self, server_name: str) -> None:
        """Close and forget one MCP server configuration."""
        await self.close_server(server_name)
        self._server_configs.pop(server_name, None)

    def get_server_config(self, server_name: str) -> MCPServerConfig | None:
        """Return one configured MCP server by name."""
        return self._server_configs.get(server_name)

    def list_server_configs(self) -> list[MCPServerConfig]:
        """Return all configured MCP servers."""
        return list(self._server_configs.values())

    def get_server_status(self, server_name: str) -> MCPServerStatus | None:
        """Return one MCP server status by name."""
        config = self.get_server_config(server_name)
        if config is None:
            return None
        return MCPServerStatus(
            name=server_name,
            connected=server_name in self._stacks,
            registered_tools=list(self._registered_mcp_tool_names.get(server_name, [])),
            config=config,
        )

    def list_server_statuses(self) -> list[MCPServerStatus]:
        """Return runtime status for all configured MCP servers."""
        return [
            status
            for server_name in self._server_configs
            if (status := self.get_server_status(server_name)) is not None
        ]

    async def connect_server(self, server: MCPServerConfig | str) -> list[str]:
        """Connect one MCP server and register its enabled tools."""
        if isinstance(server, str):
            server_config = self.get_server_config(server)
            if server_config is None:
                raise ValueError(f"Unknown MCP server: {server}")
            server = server_config

        if server.name in self._stacks:
            raise RuntimeError(f"MCP server already connected: {server.name}")
        if not server.url:
            raise ValueError("MCP server requires url")

        stack = AsyncExitStack()
        await stack.__aenter__()
        registered: list[str] = []

        try:
            client = await self._connect_client(stack, server)
            registered = await self._register_server_tools(server, client)

            self._stacks[server.name] = stack
            self._registered_mcp_tool_names[server.name] = registered
            self.set_server(server)
            return registered
        except Exception:
            self._unregister_tools(registered)
            await stack.aclose()
            raise

    async def reload_server(self, server_name: str) -> list[str]:
        """Reconnect one MCP server and rebuild its registered tools."""
        server = self._server_configs.get(server_name)
        if server is None:
            raise ValueError(f"Unknown MCP server: {server_name}")

        await self.close_server(server_name)
        return await self.connect_server(server)

    async def reload_all(self) -> list[str]:
        """Reconnect configured MCP servers and rebuild their registered tools."""
        await self.close_all()
        return await self.connect_all()

    async def _connect_client(self, stack: AsyncExitStack, server: MCPServerConfig) -> Client:
        return await stack.enter_async_context(
            Client(_fastmcp_client_transport(server), name=server.name)
        )

    async def _register_server_tools(self, server: MCPServerConfig, client: Client) -> list[str]:
        registered: list[str] = []
        try:
            for tool_def in await client.list_tools():
                tool = self._wrap_tool(server, client, tool_def)
                if tool is None:
                    continue
                self.registry.register(tool)
                registered.append(tool.name)
        except Exception:
            self._unregister_tools(registered)
            raise
        return registered

    def _wrap_tool(
        self,
        server: MCPServerConfig,
        client: Client,
        tool_def: MCPToolDefinition,
    ) -> MCPToolWrapper | None:
        wrapped_name = mcp_tool_name(server.name, tool_def.name)
        if not _is_enabled_tool(server, tool_def.name, wrapped_name):
            return None

        return MCPToolWrapper(
            name=wrapped_name,
            description=tool_def.description or tool_def.name,
            parameters=tool_def.inputSchema,
            source="mcp",
            client=client,
            original_name=tool_def.name,
            server_name=server.name,
            timeout=server.tool_timeout,
        )

    def _unregister_tools(self, tool_names: list[str]) -> None:
        for tool_name in tool_names:
            self.registry.unregister(tool_name)

    async def close_server(self, server_name: str) -> None:
        """Unregister one server's tools and close its connection."""
        self._unregister_tools(self._registered_mcp_tool_names.pop(server_name, []))

        stack = self._stacks.pop(server_name, None)
        if stack is not None:
            await stack.aclose()

    async def close_all(self) -> None:
        """Unregister all MCP tools and close all live MCP connections."""
        for server_name in list(self._stacks):
            await self.close_server(server_name)
