from pathlib import Path


_BUMBLEHIVE_HOME = Path.home() / ".bumblehive"
DEFAULT_WORKSPACE = _BUMBLEHIVE_HOME / "workspace"
DEFAULT_SESSIONS = _BUMBLEHIVE_HOME / "sessions"


def get_workspace_path(workspace: str | Path | None = None) -> Path:
    """Resolve and create the default agent workspace path."""
    path = Path(workspace).expanduser() if workspace is not None else DEFAULT_WORKSPACE
    path.mkdir(parents=True, exist_ok=True)
    return path.resolve(strict=False)


def get_sessions_path(directory: str | Path | None = None) -> Path:
    """Resolve and create the session storage path."""
    path = Path(directory).expanduser() if directory is not None else DEFAULT_SESSIONS
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    return path.resolve(strict=False)
