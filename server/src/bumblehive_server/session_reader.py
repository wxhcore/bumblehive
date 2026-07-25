from __future__ import annotations

import asyncio
import json
from hashlib import sha256
from pathlib import Path
from typing import Any

from bumblehive.paths import get_sessions_path

from .schemas import SessionDetail, SessionSummary


class SessionNotFoundError(KeyError):
    """Raised when a persisted session does not exist."""


class SessionReader:
    def __init__(self, directory: str | Path | None = None) -> None:
        self.directory = get_sessions_path(directory)

    async def list(self) -> list[SessionSummary]:
        return await asyncio.to_thread(self._list)

    async def get(self, session_id: str) -> SessionDetail:
        return await asyncio.to_thread(self._get, session_id)

    def _list(self) -> list[SessionSummary]:
        sessions: list[SessionSummary] = []
        for path in self.directory.glob("*.json"):
            try:
                document = self._read_document(path)
                sessions.append(self._summary(document, path.stat().st_mtime))
            except (OSError, TypeError, ValueError):
                continue
        sessions.sort(key=lambda item: item.updated_at, reverse=True)
        return sessions

    def _get(self, session_id: str) -> SessionDetail:
        path = self._path(session_id)
        if not path.is_file():
            raise SessionNotFoundError(session_id)
        try:
            document = self._read_document(path)
            if document["session_id"] != session_id:
                raise SessionNotFoundError(session_id)
            return SessionDetail(
                session_id=session_id,
                messages=document["messages"],
                updated_at=path.stat().st_mtime,
            )
        except SessionNotFoundError:
            raise
        except (OSError, TypeError, ValueError) as exc:
            raise SessionNotFoundError(session_id) from exc

    @staticmethod
    def _read_document(path: Path) -> dict[str, Any]:
        with path.open(encoding="utf-8") as file:
            raw = json.load(file)
        if not isinstance(raw, dict) or not isinstance(raw.get("session_id"), str):
            raise ValueError("invalid session document")
        messages = raw.get("messages")
        if not isinstance(messages, list) or not all(
            isinstance(message, dict) for message in messages
        ):
            raise ValueError("invalid session messages")
        return {
            "session_id": raw["session_id"],
            "messages": [dict(message) for message in messages],
        }

    @staticmethod
    def _summary(document: dict[str, Any], updated_at: float) -> SessionSummary:
        messages = document["messages"]
        title = next(
            (
                _message_text(message)
                for message in messages
                if message.get("role") == "user" and _message_text(message)
            ),
            "",
        )
        last_message = next(
            (
                _message_text(message)
                for message in reversed(messages)
                if _message_text(message)
            ),
            "",
        )
        return SessionSummary(
            session_id=document["session_id"],
            message_count=len(messages),
            title=_truncate(title, 80),
            last_message=_truncate(last_message, 120),
            updated_at=updated_at,
        )

    def _path(self, session_id: str) -> Path:
        digest = sha256(session_id.encode("utf-8")).hexdigest()
        return self.directory / f"{digest}.json"


def _message_text(message: dict[str, Any]) -> str:
    content = message.get("content")
    if isinstance(content, str):
        return " ".join(content.split())
    if content is None:
        return ""
    return json.dumps(content, ensure_ascii=False)


def _truncate(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return f"{value[: limit - 1]}…"
