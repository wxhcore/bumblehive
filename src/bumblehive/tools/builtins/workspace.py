import hashlib
import os
from dataclasses import dataclass
from pathlib import Path

from ..scope import current_tool_workspace
from ...config import get_workspace_path


_DEFAULT_IGNORE_DIRS = frozenset(
    {
        ".git",
        ".coverage",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".tox",
        ".venv",
        "__pycache__",
        "build",
        "dist",
        "htmlcov",
        "node_modules",
        "venv",
    }
)


@dataclass(slots=True)
class ReadState:
    mtime: float
    size: int
    content_hash: str | None
    offset: int
    limit: int | None
    can_dedup: bool


def _hash_file(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


class FileStates:
    """Track per-session file reads/writes for edit warnings and deduplication."""

    def __init__(self) -> None:
        self._state: dict[str, ReadState] = {}

    def record_read(self, path: str | Path, offset: int = 1, limit: int | None = None) -> None:
        resolved = Path(path).resolve()
        try:
            stat = resolved.stat()
        except OSError:
            return
        self._state[str(resolved)] = ReadState(
            mtime=stat.st_mtime,
            size=stat.st_size,
            content_hash=_hash_file(resolved),
            offset=offset,
            limit=limit,
            can_dedup=True,
        )

    def record_write(self, path: str | Path) -> None:
        resolved = Path(path).resolve()
        try:
            stat = resolved.stat()
        except OSError:
            self._state.pop(str(resolved), None)
            return
        self._state[str(resolved)] = ReadState(
            mtime=stat.st_mtime,
            size=stat.st_size,
            content_hash=_hash_file(resolved),
            offset=1,
            limit=None,
            can_dedup=False,
        )

    def check_read(self, path: str | Path) -> str | None:
        resolved = Path(path).resolve()
        entry = self._state.get(str(resolved))
        if entry is None:
            return "file has not been read yet; read it first to verify content before editing"

        try:
            stat = resolved.stat()
        except OSError:
            return None

        current_hash = _hash_file(resolved)
        if (
            stat.st_mtime != entry.mtime
            or stat.st_size != entry.size
            or (entry.content_hash and current_hash != entry.content_hash)
        ):
            if entry.content_hash and current_hash == entry.content_hash:
                entry.mtime = stat.st_mtime
                entry.size = stat.st_size
                return None
            return "file has been modified since last read; re-read to verify content before editing"
        return None

    def is_unchanged(self, path: str | Path, offset: int = 1, limit: int | None = None) -> bool:
        resolved = Path(path).resolve()
        entry = self._state.get(str(resolved))
        if entry is None or not entry.can_dedup:
            return False
        if entry.offset != offset or entry.limit != limit:
            return False
        try:
            current_mtime = os.path.getmtime(resolved)
        except OSError:
            return False
        if current_mtime != entry.mtime:
            current_hash = _hash_file(resolved)
            if current_hash != entry.content_hash:
                entry.can_dedup = False
                return False
            entry.can_dedup = False
            return True
        return True


class WorkspaceAccess:
    """Shared workspace path handling for built-in local tools."""

    def __init__(self, workspace: str | Path) -> None:
        self.workspace = Path(workspace).expanduser().resolve()

    def resolve(self, path: str | Path) -> Path | str:
        raw = Path(path).expanduser()
        resolved = raw.resolve() if raw.is_absolute() else (self.workspace / raw).resolve()

        if (
            resolved != self.workspace
            and self.workspace not in resolved.parents
        ):
            return "path is outside workspace"
        return resolved

    def relative_display_path(self, path: Path, *, root: Path | None = None) -> str:
        try:
            return path.relative_to(self.workspace).as_posix()
        except ValueError:
            if root is not None:
                return path.relative_to(root).as_posix()
            return path.as_posix()

    @staticmethod
    def is_ignored(path: Path, ignore_dirs: frozenset[str] = _DEFAULT_IGNORE_DIRS) -> bool:
        return any(part in ignore_dirs for part in path.parts)


def current_workspace_access() -> WorkspaceAccess:
    workspace = current_tool_workspace()
    return WorkspaceAccess(workspace or get_workspace_path())


def is_binary_bytes(raw: bytes) -> bool:
    """Return whether a byte sample looks binary."""
    if b"\x00" in raw:
        return True
    sample = raw[:4096]
    if not sample:
        return False
    non_text = sum(byte < 9 or 13 < byte < 32 for byte in sample)
    return (non_text / len(sample)) > 0.2
