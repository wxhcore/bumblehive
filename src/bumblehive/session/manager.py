import asyncio
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from ..agent.context import (
    MessageHistory,
    repair_message_sequence,
    run_messages_to_history,
)
from ..agent.runner import CheckpointCallback
from ..protocols import Message, UserMessage, normalize_user_message
from .models import SessionState
from .stores import JsonSessionStore


_INTERRUPTED_BEFORE_RESPONSE = (
    "[Previous turn was interrupted before a response was generated.]"
)
_INTERRUPTED_AFTER_TOOL = (
    "[Previous turn was interrupted after tool execution.]"
)


class SessionManager:
    """Load, cache, repair, and persist runtime conversation sessions."""

    def __init__(
        self,
        directory: str | Path | None = None,
    ) -> None:
        self._store = JsonSessionStore(directory)
        self._sessions: dict[str, SessionState] = {}
        self._load_lock = asyncio.Lock()

    async def get(self, session_id: str) -> SessionState:
        """Load a session on first access, then return its cached state."""
        session_id = _normalize_session_id(session_id)
        cached = self._sessions.get(session_id)
        if cached is not None:
            return cached

        async with self._load_lock:
            cached = self._sessions.get(session_id)
            if cached is not None:
                return cached

            messages = await self._store.load(session_id)
            session = SessionState(
                session_id=session_id,
                history=MessageHistory(messages),
            )
            self._sessions[session_id] = session
            return session

    def get_history(self, session: SessionState) -> list[Message]:
        """Return a copy of the session history."""
        return session.history.get_history()

    async def append_user(
        self,
        session: SessionState,
        current_user_message: UserMessage,
    ) -> None:
        """Persist a triggering user message before model execution starts."""
        messages = self.get_history(session)
        messages.extend(normalize_user_message(current_user_message))
        await self.replace_and_save(session, messages)

    async def save_run_messages(
        self,
        session: SessionState,
        run_messages: list[Message],
    ) -> None:
        """Convert run messages to history and persist them."""
        await self.replace_and_save(
            session,
            run_messages_to_history(run_messages),
        )

    def create_checkpoint_callback(
        self,
        session: SessionState,
    ) -> CheckpointCallback:
        """Create a checkpoint callback bound to one session."""

        async def checkpoint(run_messages: list[Message]) -> None:
            await self.save_run_messages(session, run_messages)

        return checkpoint

    async def replace_and_save(
        self,
        session: SessionState,
        messages: Sequence[Mapping[str, Any]],
    ) -> None:
        """Atomically save messages, then publish them to the in-memory state."""
        stored_messages = [dict(message) for message in messages]
        # A file save may continue in a worker thread after cancellation.
        # Wait for it before publishing the matching in-memory snapshot.
        save_task = asyncio.create_task(
            self._store.save(session.session_id, stored_messages)
        )
        cancellation: asyncio.CancelledError | None = None
        try:
            await asyncio.shield(save_task)
        except asyncio.CancelledError as exc:
            cancellation = exc
            await save_task

        session.history.replace(stored_messages)
        if cancellation is not None:
            raise cancellation

    async def recover(self, session: SessionState) -> bool:
        """Close an interrupted message sequence before accepting a new turn."""
        original = self.get_history(session)
        recovered = repair_message_sequence(original)

        if recovered:
            last_role = recovered[-1].get("role")
            if last_role == "user":
                recovered.append(
                    {"role": "assistant", "content": _INTERRUPTED_BEFORE_RESPONSE}
                )
            elif last_role == "tool":
                recovered.append(
                    {"role": "assistant", "content": _INTERRUPTED_AFTER_TOOL}
                )

        if recovered == original:
            return False
        await self.replace_and_save(session, recovered)
        return True

    async def clear(self, session_id: str) -> None:
        """Remove all messages while keeping the session itself."""
        session = await self.get(session_id)
        async with session.lock:
            await self.replace_and_save(session, [])

    async def delete(self, session_id: str) -> bool:
        """Delete one persisted session and evict its cached state."""
        session_id = _normalize_session_id(session_id)
        session = self._sessions.get(session_id)
        if session is None:
            return await self._store.delete(session_id)

        async with session.lock:
            persisted = await self._store.delete(session_id)
            cached = self._sessions.pop(session_id, None) is not None
            return persisted or cached


def _normalize_session_id(session_id: str) -> str:
    if not isinstance(session_id, str):
        raise TypeError("session_id must be a string")
    if not session_id.strip():
        raise ValueError("session_id must not be empty")
    return session_id
