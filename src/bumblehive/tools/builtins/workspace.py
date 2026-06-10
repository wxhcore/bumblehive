from pathlib import Path


DEFAULT_IGNORE_DIRS = frozenset(
    {
        ".git",
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


class WorkspaceAccess:
    """Shared workspace path handling for built-in local tools."""

    def __init__(self, workspace: str | Path) -> None:
        self.workspace = Path(workspace).expanduser().resolve()

    def resolve(self, path: str | Path) -> Path | str:
        raw = Path(path).expanduser()
        resolved = raw.resolve() if raw.is_absolute() else (self.workspace / raw).resolve()

        if resolved != self.workspace and self.workspace not in resolved.parents:
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
    def is_ignored(path: Path, ignore_dirs: frozenset[str] = DEFAULT_IGNORE_DIRS) -> bool:
        return any(part in ignore_dirs for part in path.parts)


def is_binary_bytes(raw: bytes) -> bool:
    """Return whether a byte sample looks binary."""
    if b"\x00" in raw:
        return True
    sample = raw[:4096]
    if not sample:
        return False
    non_text = sum(byte < 9 or 13 < byte < 32 for byte in sample)
    return (non_text / len(sample)) > 0.2
