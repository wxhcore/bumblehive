import asyncio
from dataclasses import dataclass, field

from ..agent.context import MessageHistoryManager


@dataclass(slots=True)
class SessionState:
    """Mutable state for one conversation lane."""

    session_id: str
    history: MessageHistoryManager = field(default_factory=MessageHistoryManager)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
