import hashlib
from collections import OrderedDict
from contextvars import ContextVar, Token
from dataclasses import dataclass
from pathlib import Path
from threading import Lock

from ...paths import get_workspace_path
from ..scope import current_tool_path_scope


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
_MAX_TOOL_STATE_SESSIONS = 256


@dataclass(slots=True)
class ReadState:
    mtime: float
    size: int
    content_hash: str | None


def _hash_file(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


class FileStates:
    """Track per-session file reads/writes for edit warnings and deduplication."""

    def __init__(self) -> None:
        self._state: dict[str, ReadState] = {}
        self._read_cache: dict[
            tuple[str, int, int | None],
            tuple[float, int, str | None],
        ] = {}

    def record_read(self, path: str | Path, offset: int = 1, limit: int | None = None) -> None:
        resolved = Path(path).resolve()
        try:
            stat = resolved.stat()
        except OSError:
            return
        path_key = str(resolved)
        content_hash = _hash_file(resolved)
        self._state[path_key] = ReadState(
            mtime=stat.st_mtime,
            size=stat.st_size,
            content_hash=content_hash,
        )
        self._read_cache[(path_key, offset, limit)] = (
            stat.st_mtime,
            stat.st_size,
            content_hash,
        )

    def record_write(self, path: str | Path) -> None:
        resolved = Path(path).resolve()
        path_key = str(resolved)
        try:
            stat = resolved.stat()
        except OSError:
            self._state.pop(path_key, None)
            self._invalidate_read_cache(path_key)
            return
        self._state[path_key] = ReadState(
            mtime=stat.st_mtime,
            size=stat.st_size,
            content_hash=_hash_file(resolved),
        )
        self._invalidate_read_cache(path_key)

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
        path_key = str(resolved)
        cached = self._read_cache.get((path_key, offset, limit))
        if cached is None:
            return False
        try:
            stat = resolved.stat()
        except OSError:
            return False
        current_hash = _hash_file(resolved)
        current = (stat.st_mtime, stat.st_size, current_hash)
        if current != cached:
            self._invalidate_read_cache(path_key)
            return False
        return True

    def _invalidate_read_cache(self, path_key: str) -> None:
        stale_keys = [key for key in self._read_cache if key[0] == path_key]
        for key in stale_keys:
            self._read_cache.pop(key, None)


class FileStateStore:
    """Bounded LRU store for per-session file tool state."""

    def __init__(self, max_entries: int = _MAX_TOOL_STATE_SESSIONS) -> None:
        if max_entries <= 0:
            raise ValueError("max_entries must be positive")
        self.max_entries = max_entries
        self._states: OrderedDict[str | None, FileStates] = OrderedDict()
        self._lock = Lock()

    def for_session(self, session_id: str | None) -> FileStates:
        with self._lock:
            state = self._states.pop(session_id, None)
            if state is None:
                state = FileStates()
            self._states[session_id] = state
            while len(self._states) > self.max_entries:
                self._states.popitem(last=False)
            return state

    def clear(self) -> None:
        with self._lock:
            self._states.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._states)


_CURRENT_FILE_STATES: ContextVar[FileStates | None] = ContextVar(
    "bumblehive_file_states",
    default=None,
)


def bind_file_states(file_states: FileStates) -> Token[FileStates | None]:
    return _CURRENT_FILE_STATES.set(file_states)


def reset_file_states(token: Token[FileStates | None]) -> None:
    _CURRENT_FILE_STATES.reset(token)


def current_file_states(default: FileStates) -> FileStates:
    return _CURRENT_FILE_STATES.get() or default


class WorkspaceAccess:
    """Shared workspace path handling for built-in local tools."""

    def __init__(
        self,
        workspace: str | Path,
        *,
        extra_read_roots: tuple[Path, ...] = (),
        extra_write_roots: tuple[Path, ...] = (),
    ) -> None:
        self.workspace = Path(workspace).expanduser().resolve()
        self.write_roots = self._merge_roots(
            self.workspace,
            *extra_write_roots,
        )
        self.read_roots = self._merge_roots(
            self.workspace,
            *extra_read_roots,
            *extra_write_roots,
        )

    def resolve_read(self, path: str | Path) -> Path | str:
        resolved = self._resolve(path)
        if not any(self._is_within(resolved, root) for root in self.read_roots):
            return "path is outside readable roots"
        return resolved

    def resolve_write(self, path: str | Path) -> Path | str:
        resolved = self._resolve(path)
        if not any(
            self._is_within(resolved, root)
            for root in self.write_roots
        ):
            return "path is outside writable roots"
        return resolved

    def _resolve(self, path: str | Path) -> Path:
        raw = Path(path).expanduser()
        return raw.resolve() if raw.is_absolute() else (self.workspace / raw).resolve()

    @staticmethod
    def _is_within(path: Path, root: Path) -> bool:
        return path == root or root in path.parents

    @staticmethod
    def _merge_roots(*roots: Path) -> tuple[Path, ...]:
        return tuple(dict.fromkeys(roots))

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
    scope = current_tool_path_scope()
    workspace = scope.workspace if scope is not None else get_workspace_path()
    allowlist = scope.path_allowlist if scope is not None else None
    extra_read_roots = allowlist.extra_read_roots if allowlist is not None else ()
    extra_write_roots = allowlist.extra_write_roots if allowlist is not None else ()
    return WorkspaceAccess(
        workspace,
        extra_read_roots=extra_read_roots,
        extra_write_roots=extra_write_roots,
    )


def is_binary_bytes(raw: bytes) -> bool:
    """Return whether a byte sample looks binary."""
    if b"\x00" in raw:
        return True
    sample = raw[:4096]
    if not sample:
        return False
    non_text = sum(byte < 9 or 13 < byte < 32 for byte in sample)
    return (non_text / len(sample)) > 0.2
