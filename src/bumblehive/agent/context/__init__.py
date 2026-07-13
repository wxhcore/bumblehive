"""Agent context assembly, history preparation, and window management."""

from .builder import ContextBuilder, DynamicValue
from .governor import ContextGovernanceConfig, ContextGovernor
from .history import (
    MessageHistory,
    backfill_missing_tool_results,
    drop_empty_messages,
    drop_orphan_tool_results,
    merge_consecutive_text_messages,
    prepare_history,
    repair_message_sequence,
    run_messages_to_history,
    sanitize_messages,
    truncate_tool_results,
)

__all__ = [
    "ContextBuilder",
    "ContextGovernanceConfig",
    "ContextGovernor",
    "DynamicValue",
    "MessageHistory",
    "backfill_missing_tool_results",
    "drop_empty_messages",
    "drop_orphan_tool_results",
    "merge_consecutive_text_messages",
    "prepare_history",
    "repair_message_sequence",
    "run_messages_to_history",
    "sanitize_messages",
    "truncate_tool_results",
]
