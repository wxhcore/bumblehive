from __future__ import annotations

import asyncio
import json
import os
from contextlib import suppress
from hashlib import sha256
from pathlib import Path
from time import time
from typing import Any
from uuid import uuid4

from bumblehive.paths import get_sessions_path

from .schemas import SessionDetail, SessionSummary


class SessionNotFoundError(KeyError):
    """Raised when a persisted session does not exist."""


class SessionReader:
    def __init__(self, directory: str | Path | None = None) -> None:
        self.directory = get_sessions_path(directory)
        self.metadata_directory = self.directory / ".metadata"
        self.metadata_directory.mkdir(mode=0o700, parents=True, exist_ok=True)

    async def list(self) -> list[SessionSummary]:
        return await asyncio.to_thread(self._list)

    async def get(self, session_id: str) -> SessionDetail:
        return await asyncio.to_thread(self._get, session_id)

    async def create(
        self,
        workspace: str | Path,
    ) -> str:
        return await asyncio.to_thread(self._create, workspace, None, None)

    async def create_child(
        self,
        workspace: str | Path,
        *,
        title: str,
        parent_session_id: str,
    ) -> str:
        return await asyncio.to_thread(
            self._create,
            workspace,
            title,
            parent_session_id,
        )

    async def migrate_missing_workspace(self, workspace: str | Path) -> int:
        return await asyncio.to_thread(self._migrate_missing_workspace, workspace)

    async def delete_metadata(self, session_id: str) -> bool:
        return await asyncio.to_thread(self._delete_metadata, session_id)

    def _list(self) -> list[SessionSummary]:
        sessions: list[SessionSummary] = []
        for path in self.directory.glob("*.json"):
            try:
                document = self._read_document(path)
                workspace, created_at, title = self._read_metadata(
                    document["session_id"]
                )
                sessions.append(
                    self._summary(
                        document,
                        workspace,
                        created_at,
                        path.stat().st_mtime,
                        title,
                    )
                )
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
            workspace, created_at, _ = self._read_metadata(session_id)
            return SessionDetail(
                session_id=session_id,
                workspace=workspace,
                messages=document["messages"],
                created_at=created_at,
                updated_at=path.stat().st_mtime,
            )
        except SessionNotFoundError:
            raise
        except (OSError, TypeError, ValueError) as exc:
            raise SessionNotFoundError(session_id) from exc

    def _create(
        self,
        workspace: str | Path,
        title: str | None,
        parent_session_id: str | None,
    ) -> str:
        session_id = str(uuid4())
        session_path = self._path(session_id)
        metadata_path = self._metadata_path(session_id)
        created_at = time()
        metadata: dict[str, Any] = {
            "session_id": session_id,
            "workspace": _resolved_workspace(workspace),
            "created_at": created_at,
        }
        display_title = _normalized_title(title)
        if display_title:
            metadata["title"] = display_title
        if parent_session_id:
            metadata["parent_session_id"] = parent_session_id
        try:
            self._write_json(
                session_path,
                {"session_id": session_id, "messages": []},
            )
            self._write_json(metadata_path, metadata)
        except (OSError, TypeError, ValueError):
            session_path.unlink(missing_ok=True)
            metadata_path.unlink(missing_ok=True)
            raise
        return session_id

    def _migrate_missing_workspace(self, workspace: str | Path) -> int:
        default_workspace = _resolved_workspace(workspace)
        migrated = 0
        for path in self.directory.glob("*.json"):
            try:
                document = self._read_document(path)
                session_id = document["session_id"]
                try:
                    self._read_metadata(session_id)
                    continue
                except (OSError, TypeError, ValueError):
                    pass
                self._write_json(
                    self._metadata_path(session_id),
                    {
                        "session_id": session_id,
                        "workspace": default_workspace,
                        "created_at": _path_created_at(path),
                    },
                )
            except (OSError, TypeError, ValueError):
                continue
            migrated += 1
        return migrated

    def _delete_metadata(self, session_id: str) -> bool:
        try:
            self._metadata_path(session_id).unlink()
        except FileNotFoundError:
            return False
        return True

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

    def _read_metadata(self, session_id: str) -> tuple[str, float, str]:
        metadata_path = self._metadata_path(session_id)
        with metadata_path.open(encoding="utf-8") as file:
            raw = json.load(file)
        if (
            not isinstance(raw, dict)
            or raw.get("session_id") != session_id
            or not isinstance(raw.get("workspace"), str)
            or not raw["workspace"].strip()
        ):
            raise ValueError("invalid session metadata")
        created_at = raw.get("created_at")
        if isinstance(created_at, bool) or not isinstance(created_at, (int, float)):
            created_at = _path_created_at(metadata_path)
        return (
            raw["workspace"],
            float(created_at),
            _normalized_title(raw.get("title")),
        )

    @staticmethod
    def _write_json(path: Path, document: dict[str, Any]) -> None:
        temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
        try:
            with temporary.open("x", encoding="utf-8") as file:
                with suppress(OSError):
                    os.chmod(temporary, 0o600)
                json.dump(document, file, ensure_ascii=False, indent=2)
                file.write("\n")
            os.replace(temporary, path)
        except (OSError, TypeError, ValueError):
            temporary.unlink(missing_ok=True)
            raise

    @staticmethod
    def _summary(
        document: dict[str, Any],
        workspace: str,
        created_at: float,
        updated_at: float,
        metadata_title: str,
    ) -> SessionSummary:
        messages = document["messages"]
        title = metadata_title or next(
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
            workspace=workspace,
            message_count=len(messages),
            title=_truncate(title, 80),
            last_message=_truncate(last_message, 120),
            created_at=created_at,
            updated_at=updated_at,
        )

    def _path(self, session_id: str) -> Path:
        return self.directory / _session_filename(session_id)

    def _metadata_path(self, session_id: str) -> Path:
        return self.metadata_directory / _session_filename(session_id)


def _session_filename(session_id: str) -> str:
    digest = sha256(session_id.encode("utf-8")).hexdigest()
    return f"{digest}.json"


def _resolved_workspace(workspace: str | Path) -> str:
    return str(Path(workspace).expanduser().resolve(strict=False))


def _path_created_at(path: Path) -> float:
    stat = path.stat()
    return float(getattr(stat, "st_birthtime", stat.st_mtime))


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


def _normalized_title(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return _truncate(" ".join(value.split()), 80)
