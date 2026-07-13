import asyncio
from dataclasses import dataclass, field

from ..agent.context import MessageHistory


@dataclass(slots=True)
class SessionState:
    """Mutable state for one conversation lane."""

    session_id: str
    history: MessageHistory = field(default_factory=MessageHistory)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
