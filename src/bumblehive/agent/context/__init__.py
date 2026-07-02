"""Agent context assembly, history preparation, and window management."""

from .builder import ContextBuilder, DynamicValue
from .governor import ContextGovernanceConfig, ContextGovernor
from .history import (
    MessageHistoryManager,
    backfill_missing_tool_results,
    drop_empty_messages,
    drop_orphan_tool_results,
    merge_consecutive_text_messages,
    prepare_history,
    repair_message_sequence,
    sanitize_messages,
    truncate_tool_results,
)

__all__ = [
    "ContextBuilder",
    "ContextGovernanceConfig",
    "ContextGovernor",
    "DynamicValue",
    "MessageHistoryManager",
    "backfill_missing_tool_results",
    "drop_empty_messages",
    "drop_orphan_tool_results",
    "merge_consecutive_text_messages",
    "prepare_history",
    "repair_message_sequence",
    "sanitize_messages",
    "truncate_tool_results",
]
