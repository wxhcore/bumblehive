import asyncio
import re
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from typing import Any

from .base import Tool
from .registry import ToolRegistry


@dataclass(frozen=True)
class MCPServerConfig:
    """Configuration for one FastMCP-connectable server."""

    name: str
    url: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    tool_timeout: int = 30
    enabled_tools: list[str] = field(default_factory=lambda: ["*"])


def sanitize_mcp_tool_name(name: str) -> str:
    """Return a provider-safe tool name."""
    sanitized = re.sub(r"[^a-zA-Z0-9_-]", "_", name)
    return re.sub(r"_+", "_", sanitized).strip("_")


def mcp_tool_name(server_name: str, tool_name: str) -> str:
    """Build the stable Bumblehive name for an MCP tool."""
    return sanitize_mcp_tool_name(f"mcp_{server_name}_{tool_name}")


def _fastmcp_client_transport(server: MCPServerConfig) -> str | Any:
    """Return the transport argument expected by fastmcp.Client."""
    if not server.headers:
        return server.url

    from fastmcp.client.transports import (
        SSETransport,
        StreamableHttpTransport,
        infer_transport,
    )

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


def _text_from_content_blocks(blocks: Any) -> str:
    parts: list[str] = []
    for block in blocks:
        if getattr(block, "type", None) == "text" and hasattr(block, "text"):
            parts.append(block.text)
        elif hasattr(block, "model_dump_json"):
            parts.append(block.model_dump_json())
        else:
            parts.append(str(block))
    return "\n".join(parts) or "(no output)"


def _mcp_result_payload(result: Any) -> Any:
    is_error = bool(getattr(result, "is_error", False))
    data = getattr(result, "data", None)
    if not is_error and data is not None:
        return data

    output = _text_from_content_blocks(getattr(result, "content", []))
    if is_error:
        return f"Error: {output}"

    structured_content = getattr(result, "structured_content", None)
    if structured_content is not None:
        return structured_content
    return output


@dataclass(frozen=True)
class MCPToolWrapper(Tool):
    """Expose an MCP tool through Bumblehive's Tool interface."""

    client: Any
    original_name: str
    server_name: str
    timeout: int = 30

    async def execute(self, **kwargs: Any) -> Any:
        try:
            result = await self.client.call_tool(
                self.original_name,
                kwargs,
                timeout=self.timeout,
                raise_on_error=False,
            )
        except (asyncio.TimeoutError, TimeoutError):
            return f"Error: MCP tool '{self.name}' timed out after {self.timeout} seconds"

        return _mcp_result_payload(result)


class MCPManager:
    """Connect MCP servers and register their tools."""

    def __init__(
        self,
        registry: ToolRegistry,
        servers: list[MCPServerConfig] | None = None,
    ) -> None:
        self.registry = registry
        self.servers = list(servers or [])
        self._stacks: dict[str, AsyncExitStack] = {}
        self._registered_tools: dict[str, list[str]] = {}

    @property
    def registered_tools(self) -> dict[str, list[str]]:
        """Return registered MCP tool names grouped by server name."""
        return {
            server_name: list(tool_names)
            for server_name, tool_names in self._registered_tools.items()
        }

    async def connect_all(self) -> list[str]:
        """Connect every configured MCP server and register its tools."""
        registered: list[str] = []
        for server in self.servers:
            registered.extend(await self.connect_server(server))
        return registered

    async def connect_server(self, server: MCPServerConfig) -> list[str]:
        """Connect one MCP server and register its enabled tools."""
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
            self._registered_tools[server.name] = registered
            return registered
        except Exception:
            self._unregister_tools(registered)
            await stack.aclose()
            raise

    async def _connect_client(self, stack: AsyncExitStack, server: MCPServerConfig) -> Any:
        from fastmcp import Client

        return await stack.enter_async_context(
            Client(_fastmcp_client_transport(server), name=server.name)
        )

    async def _register_server_tools(self, server: MCPServerConfig, client: Any) -> list[str]:
        registered: list[str] = []
        for tool_def in await client.list_tools():
            tool = self._wrap_tool(server, client, tool_def)
            if tool is None:
                continue
            self.registry.register(tool)
            registered.append(tool.name)
        return registered

    def _wrap_tool(
        self,
        server: MCPServerConfig,
        client: Any,
        tool_def: Any,
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
        self._unregister_tools(self._registered_tools.pop(server_name, []))

        stack = self._stacks.pop(server_name, None)
        if stack is not None:
            await stack.aclose()

    async def close_all(self) -> None:
        """Unregister all MCP tools and close all live MCP connections."""
        for server_name in list(self._stacks):
            await self.close_server(server_name)
