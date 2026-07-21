from bumblehive.protocols.mcp import (
    DEFAULT_MCP_TOOL_TIMEOUT,
    MCPServerConfig,
)


def test_tool_timeout_resolves_default_and_explicit_values() -> None:
    default = MCPServerConfig(name="docs", url="https://example.test/mcp")

    assert default.tool_timeout is None
    assert default.effective_tool_timeout == DEFAULT_MCP_TOOL_TIMEOUT
    assert (
        MCPServerConfig(
            name="docs",
            url="https://example.test/mcp",
            tool_timeout=5,
        ).effective_tool_timeout
        == 5
    )
    assert (
        MCPServerConfig(
            name="docs",
            url="https://example.test/mcp",
            tool_timeout=0,
        ).effective_tool_timeout
        == 1
    )
