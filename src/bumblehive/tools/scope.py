from collections.abc import Sequence
from contextvars import ContextVar, Token
from dataclasses import dataclass
from pathlib import Path

from ..paths import get_workspace_path


def _normalize_roots(roots: Sequence[str | Path]) -> tuple[Path, ...]:
    if not isinstance(roots, Sequence) or isinstance(roots, (str, bytes)):
        raise TypeError("roots must be a sequence of paths")

    normalized: list[Path] = []
    seen: set[Path] = set()
    for root in roots:
        path = Path(root).expanduser().resolve(strict=False)
        if path in seen:
            continue
        seen.add(path)
        normalized.append(path)
    return tuple(normalized)


@dataclass(frozen=True, slots=True)
class ToolPathPolicy:
    """Run-scoped path policy for path-aware built-in tools.

    This is an application-level policy, not an OS sandbox. It does not
    automatically restrict arbitrary Python tools, MCP servers, or filesystem
    access performed by subprocesses.
    """

    extra_read_roots: tuple[Path, ...] = ()
    extra_write_roots: tuple[Path, ...] = ()
    restrict_exec_paths: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.restrict_exec_paths, bool):
            raise TypeError("restrict_exec_paths must be a bool")
        for roots in (self.extra_read_roots, self.extra_write_roots):
            if not isinstance(roots, tuple):
                raise TypeError("policy roots must be tuples of Path instances")
            for root in roots:
                if not isinstance(root, Path):
                    raise TypeError("policy roots must be tuples of Path instances")
                if not root.is_absolute():
                    raise ValueError("policy roots must be absolute paths")

    @classmethod
    def from_roots(
        cls,
        *,
        extra_read_roots: Sequence[str | Path] = (),
        extra_write_roots: Sequence[str | Path] = (),
        restrict_exec_paths: bool = False,
    ) -> "ToolPathPolicy":
        """Build a policy from normalized, deduplicated filesystem roots."""
        return cls(
            extra_read_roots=_normalize_roots(extra_read_roots),
            extra_write_roots=_normalize_roots(extra_write_roots),
            restrict_exec_paths=restrict_exec_paths,
        )


@dataclass(frozen=True, slots=True)
class _ToolPathScope:
    workspace: Path
    policy: ToolPathPolicy


_CURRENT_TOOL_PATH_SCOPE: ContextVar[_ToolPathScope | None] = ContextVar(
    "bumblehive_tool_path_scope",
    default=None,
)
_CURRENT_TOOL_SESSION_ID: ContextVar[str | None] = ContextVar(
    "bumblehive_tool_session_id",
    default=None,
)


def bind_tool_path_scope(
    workspace: Path | str | None,
    policy: ToolPathPolicy,
) -> Token[_ToolPathScope | None]:
    return _CURRENT_TOOL_PATH_SCOPE.set(
        _ToolPathScope(
            workspace=get_workspace_path(workspace),
            policy=policy,
        )
    )


def reset_tool_path_scope(token: Token[_ToolPathScope | None]) -> None:
    _CURRENT_TOOL_PATH_SCOPE.reset(token)


def current_tool_path_scope() -> _ToolPathScope | None:
    return _CURRENT_TOOL_PATH_SCOPE.get()


def bind_tool_session(session_id: str) -> Token[str | None]:
    return _CURRENT_TOOL_SESSION_ID.set(session_id)


def reset_tool_session(token: Token[str | None]) -> None:
    _CURRENT_TOOL_SESSION_ID.reset(token)


def current_tool_session_id() -> str | None:
    return _CURRENT_TOOL_SESSION_ID.get()
