from pathlib import Path


_BUMBLEHIVE_HOME = Path.home() / ".bumblehive"
DEFAULT_SKILLS = _BUMBLEHIVE_HOME / "skills"
DEFAULT_WORKSPACE = _BUMBLEHIVE_HOME / "workspace"
DEFAULT_SESSIONS = _BUMBLEHIVE_HOME / "sessions"


def _resolve_path(value: str | Path | None, default: Path) -> Path:
    path = Path(value).expanduser() if value is not None else default
    return path.resolve(strict=False)


def get_skills_path(directory: str | Path | None = None) -> Path:
    """Resolve the Bumblehive skills directory without creating it."""
    return _resolve_path(directory, DEFAULT_SKILLS)


def get_workspace_path(workspace: str | Path | None = None) -> Path:
    """Resolve and create the default agent workspace path."""
    path = _resolve_path(workspace, DEFAULT_WORKSPACE)
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    return path


def get_sessions_path(directory: str | Path | None = None) -> Path:
    """Resolve the session storage path without creating it."""
    return _resolve_path(directory, DEFAULT_SESSIONS)
