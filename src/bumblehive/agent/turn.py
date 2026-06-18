from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


DynamicValue = str | int | float | bool | None | dict[str, Any] | list[Any]


@dataclass
class AgentTurnContext:
    """Per-turn context used when building model request messages."""

    workspace: Path | str
    timezone: str | None = None
    dynamic_context: Mapping[str, DynamicValue] | None = None

    def __post_init__(self) -> None:
        self.workspace = Path(self.workspace).expanduser().resolve(strict=False)
