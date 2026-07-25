from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

import pytest
from fastmcp import Client, FastMCP

from bumblehive.protocols import MCPServerConfig, ToolCall
from bumblehive.tools import ToolManager, ToolRegistry
from bumblehive.tools.mcp.manager import MCPManager


@dataclass
class Content:
    text: str
    type: str = "text"


@dataclass
class Result:
    content: list[Any]
    data: Any = None
    structured_content: dict[str, Any] | None = None
    is_error: bool = False


@dataclass
class Definition:
    name: str
    description: str
    inputSchema: dict[str, Any]


class FakeClient:
    def __init__(self, tools, responses=None, *, timeout_names=None) -> None:
        self.tools = tools if isinstance(tools, BaseException) else list(tools)
        self.responses = dict(responses or {})
        self.timeout_names = set(timeout_names or ())
        self.calls = []

    async def list_tools(self):
        if isinstance(self.tools, BaseException):
            raise self.tools
        return self.tools

    async def call_tool(self, name, arguments=None, timeout=None, raise_on_error=True):
        self.calls.append((name, arguments or {}))
        if name in self.timeout_names:
            raise TimeoutError("timed out")
        response = self.responses[name]
        if isinstance(response, list):
            response = response.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


class FakeManager(MCPManager):
    def __init__(self, registry, client, **kwargs) -> None:
        super().__init__(registry, **kwargs)
        self.client = client
        self.connection_count = 0

    async def _connect_client(self, stack, server):
        self.connection_count += 1
        return self.client


class LifecycleManager(MCPManager):
    def __init__(self, registry, client=None, *, connect_error=None) -> None:
        super().__init__(registry)
        self.client = client
        self.connect_error = connect_error
        self.closed = False

    async def _connect_client(self, stack, server):
        @asynccontextmanager
        async def connection():
            try:
                yield self.client
            finally:
                self.closed = True

        client = await stack.enter_async_context(connection())
        if self.connect_error is not None:
            raise self.connect_error
        return client


def _definition(name, *, properties=None, required=None):
    schema = {
        "type": "object",
        "properties": properties or {},
        "additionalProperties": False,
    }
    if required:
        schema["required"] = required
    return Definition(name, f"{name} tool.", schema)


def _call(call_id, name, arguments=None):
    return ToolCall(call_id, name, arguments or {})


@pytest.mark.asyncio
async def test_tool_manager_registers_filters_executes_and_closes_mcp_tools() -> None:
    registry = ToolRegistry()
    client = FakeClient(
        [
            _definition("search", properties={"query": {"type": "string"}}, required=["query"]),
            _definition("get_pr", properties={"number": {"type": "integer"}}, required=["number"]),
            _definition("delete_repo"),
        ],
        {
            "search": [ConnectionResetError("reset"), Result([Content("issue")])],
            "get_pr": Result([], data={"number": 12}),
        },
    )
    manager = ToolManager(registry=registry)
    manager.mcp_manager = FakeManager(registry, client)
    server = MCPServerConfig(
        name="github",
        url="https://example.test/mcp",
        enabled_tools=["search", "mcp_github_get_pr"],
    )

    registered = await manager.connect_mcp_server(server)
    search, pr, missing = await manager.execute_many(
        [
            _call("search", "mcp_github_search", {"query": "bug"}),
            _call("pr", "mcp_github_get_pr", {"number": "12"}),
            _call("delete", "mcp_github_delete_repo"),
        ]
    )

    assert registered == ["mcp_github_search", "mcp_github_get_pr"]
    assert manager.registered_mcp_tool_names == {"github": registered}
    assert search.content == "issue"
    assert client.calls[:2] == [("search", {"query": "bug"})] * 2
    assert pr.content == {"number": 12}
    assert missing.error is not None and missing.error.code == "tool_not_found"

    await manager.close_mcp_server("github")
    assert manager.tool_names == []
    assert manager.registered_mcp_tool_names == {}


@pytest.mark.asyncio
async def test_mcp_manager_tracks_config_status_reload_and_removal() -> None:
    registry = ToolRegistry()
    client = FakeClient([_definition("search")])
    manager = FakeManager(registry, client)
    server = MCPServerConfig(name="demo", url="https://example.test/mcp")

    manager.set_server(server)
    assert manager.get_server_status("demo").connected is False
    assert await manager.connect_server("demo") == ["mcp_demo_search"]
    assert manager.get_server_status("demo").connected is True

    client.tools = [_definition("lookup")]
    updated = MCPServerConfig(
        name="demo",
        url="https://example.test/new",
        enabled_tools=["lookup"],
    )
    manager.set_server(updated)
    assert registry.tool_names == ["mcp_demo_search"]
    assert await manager.reload_server("demo") == ["mcp_demo_lookup"]
    assert manager.get_server_status("demo").config == updated

    await manager.remove_server("demo")
    assert manager.list_server_configs() == []
    assert manager.list_server_statuses() == []
    assert registry.tool_names == []
    with pytest.raises(ValueError, match="Unknown MCP server"):
        await manager.reload_server("missing")


@pytest.mark.asyncio
async def test_mcp_execution_surfaces_validation_remote_and_transport_errors() -> None:
    registry = ToolRegistry()
    client = FakeClient(
        [
            _definition("validate", properties={"count": {"type": "integer"}}, required=["count"]),
            _definition("remote_error"),
            _definition("timeout"),
        ],
        {
            "validate": Result([Content("ok")]),
            "remote_error": Result([Content("bad input")], is_error=True),
            "timeout": Result([Content("late")]),
        },
        timeout_names={"timeout"},
    )
    manager = ToolManager(registry=registry)
    manager.mcp_manager = FakeManager(registry, client)
    await manager.connect_mcp_server(
        MCPServerConfig(
            name="demo",
            url="https://example.test/mcp",
            enabled_tools=["*"],
            tool_timeout=1,
        )
    )

    invalid, remote, timeout = await manager.execute_many(
        [
            _call("invalid", "mcp_demo_validate", {"count": "bad"}),
            _call("remote", "mcp_demo_remote_error"),
            _call("timeout", "mcp_demo_timeout"),
        ]
    )

    assert invalid.error is not None and invalid.error.code == "invalid_tool_arguments"
    assert remote.content == "Error: bad input"
    assert "timed out after 1 seconds" in timeout.content


@pytest.mark.asyncio
async def test_mcp_failure_paths_close_connections_and_roll_back_partial_registration() -> None:
    server = MCPServerConfig(name="demo", url="https://example.test/mcp")

    for client, connect_error, expected_error in (
        (FakeClient([]), ConnectionError("connect failed"), ConnectionError),
        (FakeClient(RuntimeError("list failed")), None, RuntimeError),
    ):
        registry = ToolRegistry()
        manager = LifecycleManager(
            registry,
            client,
            connect_error=connect_error,
        )

        with pytest.raises(expected_error):
            await manager.connect_server(server)

        assert manager.closed is True
        assert manager.get_server_status("demo") is None
        assert registry.tool_names == []

    registry = ToolRegistry()
    registry.tool("mcp_demo_duplicate")(lambda: "existing")
    manager = LifecycleManager(
        registry,
        FakeClient([_definition("first"), _definition("duplicate")]),
    )

    with pytest.raises(ValueError, match="already registered"):
        await manager.connect_server(server)

    assert manager.closed is True
    assert registry.tool_names == ["mcp_demo_duplicate"]
    assert manager.registered_mcp_tool_names == {}


@pytest.mark.asyncio
async def test_mcp_result_fallbacks_and_second_transient_failure_are_stable() -> None:
    class JsonBlock:
        type = "image"

        def model_dump_json(self) -> str:
            return '{"type":"image","data":"abc"}'

    registry = ToolRegistry()
    client = FakeClient(
        [_definition("structured"), _definition("blocks"), _definition("unstable")],
        {
            "structured": Result([], structured_content={"items": [1, 2]}),
            "blocks": Result([Content("ready"), JsonBlock()]),
            "unstable": [ConnectionResetError("first"), BrokenPipeError("second")],
        },
    )
    manager = ToolManager(registry=registry)
    manager.mcp_manager = FakeManager(registry, client)
    await manager.connect_mcp_server(
        MCPServerConfig(name="demo", url="https://example.test/mcp")
    )

    structured, blocks, unstable = await manager.execute_many(
        [
            _call("1", "mcp_demo_structured"),
            _call("2", "mcp_demo_blocks"),
            _call("3", "mcp_demo_unstable"),
        ]
    )

    assert structured.content == {"items": [1, 2]}
    assert blocks.content == 'ready\n{"type":"image","data":"abc"}'
    assert "failed after retry: BrokenPipeError: second" in unstable.content
    assert client.calls[-2:] == [("unstable", {})] * 2


@pytest.mark.asyncio
async def test_mcp_manager_integrates_with_a_real_in_process_fastmcp_server() -> None:
    server = FastMCP("calculator")

    @server.tool
    def multiply(left: int, right: int) -> dict[str, int]:
        """Multiply two integers."""
        return {"product": left * right}

    class InProcessManager(MCPManager):
        async def _connect_client(self, stack, config):
            return await stack.enter_async_context(Client(server, name=config.name))

    registry = ToolRegistry()
    manager = ToolManager(registry=registry)
    manager.mcp_manager = InProcessManager(registry)

    assert await manager.connect_mcp_server(
        MCPServerConfig(name="local", url="in-process")
    ) == ["mcp_local_multiply"]
    result = await manager.execute_call(
        _call("multiply", "mcp_local_multiply", {"left": "6", "right": 7})
    )

    assert result.error is None
    assert result.content == {"product": 42}
    await manager.close()


@pytest.mark.asyncio
async def test_tool_manager_sync_preserves_matching_connections_and_replaces_changes() -> None:
    registry = ToolRegistry()
    client = FakeClient([_definition("search")])
    old = MCPServerConfig(name="old", url="https://example.test/old")
    manager = ToolManager(registry=registry)
    fake = FakeManager(registry, client, servers=[old])
    manager.mcp_manager = fake

    assert await manager.connect_mcp() == ["mcp_old_search"]
    assert await manager.sync_mcp_servers([old]) == []
    assert fake.connection_count == 1

    new = MCPServerConfig(name="new", url="https://example.test/new")
    assert await manager.sync_mcp_servers([new]) == ["mcp_new_search"]
    assert manager.list_mcp_server_configs() == [new]
    assert manager.tool_names == ["mcp_new_search"]
