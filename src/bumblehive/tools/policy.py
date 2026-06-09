from collections.abc import Iterable
from dataclasses import dataclass, field


@dataclass(frozen=True)
class ToolPolicy:
    """Startup-time selection for which candidate tools are registered."""

    enabled_tools: frozenset[str] | None = None
    disabled_tools: frozenset[str] = field(default_factory=frozenset)

    def __init__(
        self,
        *,
        enabled_tools: Iterable[str] | None = None,
        disabled_tools: Iterable[str] = (),
    ) -> None:
        object.__setattr__(
            self,
            "enabled_tools",
            None if enabled_tools is None else frozenset(enabled_tools),
        )
        object.__setattr__(self, "disabled_tools", frozenset(disabled_tools))

    def allows_tool(self, name: str, *aliases: str) -> bool:
        """Return whether a candidate tool name should be registered."""
        names = frozenset((name, *aliases))
        if names & self.disabled_tools:
            return False
        if self.enabled_tools is None:
            return True
        return bool(names & self.enabled_tools)
