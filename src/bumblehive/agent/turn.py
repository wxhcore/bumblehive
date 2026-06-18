from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping


DynamicValue = str | int | float | bool | None | dict[str, Any] | list[Any]


@dataclass
class AgentTurnContext:
    """Per-turn runtime context shared by prompt building and tool execution."""

    workspace: Path | str
    timezone: str | None = None
    dynamic_context: Mapping[str, DynamicValue] | None = None
    session_id: str | None = None
    request_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.workspace = Path(self.workspace).expanduser().resolve(strict=False)
