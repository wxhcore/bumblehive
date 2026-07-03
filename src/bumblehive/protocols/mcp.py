from dataclasses import dataclass, field


@dataclass(frozen=True)
class MCPServerConfig:
    """Configuration for one FastMCP-connectable server."""

    name: str
    url: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    tool_timeout: int = 30
    enabled_tools: list[str] = field(default_factory=lambda: ["*"])
