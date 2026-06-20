"""Agent context assembly primitives."""

from .context import ContextBuilder, ContextBundle
from .history import (
    backfill_missing_tool_results,
    drop_empty_messages,
    drop_orphan_tool_results,
    merge_consecutive_text_messages,
    prepare_history,
    sanitize_messages,
    truncate_tool_results,
)
from .turn import AgentTurnContext, DynamicValue
from .types import AgentError

__all__ = [
    "AgentError",
    "AgentTurnContext",
    "ContextBuilder",
    "ContextBundle",
    "DynamicValue",
    "backfill_missing_tool_results",
    "drop_empty_messages",
    "drop_orphan_tool_results",
    "merge_consecutive_text_messages",
    "prepare_history",
    "sanitize_messages",
    "truncate_tool_results",
]
