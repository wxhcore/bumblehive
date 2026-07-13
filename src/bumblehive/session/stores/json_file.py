import asyncio
import json
import os
from contextlib import suppress
from hashlib import sha256
from pathlib import Path
from typing import Any
from uuid import uuid4

from ...paths import get_sessions_path


class SessionFileError(RuntimeError):
    """Raised when session JSON cannot be read or written."""


class JsonSessionStore:
    """Store each session as one atomically replaced JSON document."""

    def __init__(self, directory: str | Path | None = None) -> None:
        self.directory = get_sessions_path(directory)

    async def load(self, session_id: str) -> list[dict[str, Any]] | None:
        return await asyncio.to_thread(self._load, session_id)

    async def save(
        self,
        session_id: str,
        messages: list[dict[str, Any]],
    ) -> None:
        await asyncio.to_thread(self._save, session_id, messages)

    async def delete(self, session_id: str) -> bool:
        return await asyncio.to_thread(self._delete, session_id)

    def _load(self, session_id: str) -> list[dict[str, Any]] | None:
        path = self._path(session_id)
        if not path.exists():
            return None

        try:
            with path.open(encoding="utf-8") as file:
                raw = json.load(file)
            if not isinstance(raw, dict):
                raise ValueError("Session document must contain a JSON object")
            if raw.get("session_id") != session_id:
                raise ValueError("Session id does not match its storage file")

            raw_messages = raw.get("messages")
            if not isinstance(raw_messages, list):
                raise ValueError("Session document messages must be a list")

            messages: list[dict[str, Any]] = []
            for index, message in enumerate(raw_messages):
                if not isinstance(message, dict):
                    raise ValueError(
                        f"Session message at index {index} must be an object"
                    )
                messages.append(dict(message))
            return messages
        except (OSError, TypeError, ValueError) as exc:
            raise SessionFileError(f"Failed to load session {session_id!r}") from exc

    def _save(
        self,
        session_id: str,
        messages: list[dict[str, Any]],
    ) -> None:
        path = self._path(session_id)
        temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")

        try:
            with temporary.open("x", encoding="utf-8") as file:
                with suppress(OSError):
                    os.chmod(temporary, 0o600)
                json.dump(
                    {"session_id": session_id, "messages": messages},
                    file,
                    ensure_ascii=False,
                    indent=2,
                )
                file.write("\n")

            os.replace(temporary, path)
        except (OSError, TypeError, ValueError) as exc:
            temporary.unlink(missing_ok=True)
            raise SessionFileError(f"Failed to save session {session_id!r}") from exc

    def _delete(self, session_id: str) -> bool:
        path = self._path(session_id)
        try:
            path.unlink()
        except FileNotFoundError:
            return False
        except OSError as exc:
            raise SessionFileError(f"Failed to delete session {session_id!r}") from exc
        return True

    def _path(self, session_id: str) -> Path:
        digest = sha256(session_id.encode("utf-8")).hexdigest()
        return self.directory / f"{digest}.json"
