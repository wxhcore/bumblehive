from dataclasses import dataclass, field


DEFAULT_MCP_TOOL_TIMEOUT = 30


@dataclass(frozen=True)
class MCPServerConfig:
    """Configuration for one FastMCP-connectable server."""

    name: str
    url: str
    headers: dict[str, str] = field(default_factory=dict)
    tool_timeout: int | None = None
    enabled_tools: list[str] = field(default_factory=lambda: ["*"])

    @property
    def effective_tool_timeout(self) -> int:
        """Return the effective positive tool timeout in seconds."""
        if self.tool_timeout is None:
            return DEFAULT_MCP_TOOL_TIMEOUT
        return max(1, self.tool_timeout)
