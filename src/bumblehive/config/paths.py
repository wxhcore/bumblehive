from pathlib import Path


DEFAULT_WORKSPACE = Path.home() / ".bumblehive" / "workspace"


def get_workspace_path(workspace: str | Path | None = None) -> Path:
    """Resolve and create the default agent workspace path."""
    path = Path(workspace).expanduser() if workspace is not None else DEFAULT_WORKSPACE
    path.mkdir(parents=True, exist_ok=True)
    return path.resolve(strict=False)
