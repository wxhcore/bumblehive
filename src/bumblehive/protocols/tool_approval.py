from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class ToolApprovalRequest:
    """One validated tool call awaiting an execution decision."""

    call_id: str
    name: str
    arguments: Mapping[str, Any]
    workspace: Path


@dataclass(frozen=True, slots=True)
class ToolApprovalDecision:
    """Decision returned by a tool approval handler."""

    approved: bool
    reason: str | None = None

    @classmethod
    def approve(cls) -> "ToolApprovalDecision":
        return cls(approved=True)

    @classmethod
    def reject(cls, reason: str | None = None) -> "ToolApprovalDecision":
        return cls(approved=False, reason=reason)


ToolApprovalHandler = Callable[
    [ToolApprovalRequest],
    Awaitable[ToolApprovalDecision],
]
