"""Observe built-in file mutations without changing their tool results."""

from __future__ import annotations

import difflib
from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any

from .builtins.workspace import (
    WorkspaceAccess,
    current_workspace_access,
    is_binary_bytes,
)


_MUTATION_TOOLS = frozenset({"write_file", "edit_file", "apply_patch"})
_MAX_TRACKED_FILES = 20
_MAX_SNAPSHOT_BYTES = 2 * 1024 * 1024
_MAX_DIFF_LINES = 500
_MAX_DIFF_LINE_CHARACTERS = 1_200
_MAX_TOTAL_DIFF_CHARACTERS = 256_000
_DIFF_CONTEXT_LINES = 3


@dataclass(frozen=True, slots=True)
class _FileSnapshot:
    exists: bool
    text: str | None
    fingerprint: tuple[int, int, bytes | None]


@dataclass(frozen=True, slots=True)
class _TrackedFile:
    path: Path
    display_path: str
    before: _FileSnapshot


@dataclass(frozen=True, slots=True)
class FileChangeTracker:
    """Capture target files before a mutation and diff their final contents."""

    files: tuple[_TrackedFile, ...] = ()

    @classmethod
    def prepare(
        cls,
        tool_name: str,
        arguments: Mapping[str, Any],
    ) -> FileChangeTracker:
        if tool_name not in _MUTATION_TOOLS:
            return cls()

        try:
            access = current_workspace_access()
            paths = _resolve_target_paths(tool_name, arguments, access)
        except (OSError, RuntimeError, TypeError, ValueError):
            return cls()

        tracked = tuple(
            _TrackedFile(
                path=path,
                display_path=access.relative_display_path(path),
                before=_read_snapshot(path),
            )
            for path in paths
        )
        return cls(tracked)

    def finish(self) -> list[dict[str, Any]]:
        changes: list[dict[str, Any]] = []
        remaining_characters = _MAX_TOTAL_DIFF_CHARACTERS

        for tracked in self.files:
            change = _build_change(
                tracked.display_path,
                tracked.before,
                _read_snapshot(tracked.path),
            )
            if change is None:
                continue

            unified_diff = change.get("unified_diff")
            if isinstance(unified_diff, str):
                if len(unified_diff) > remaining_characters:
                    change.pop("unified_diff")
                    change["truncated"] = True
                else:
                    remaining_characters -= len(unified_diff)
            changes.append(change)

        return changes


def _resolve_target_paths(
    tool_name: str,
    arguments: Mapping[str, Any],
    access: WorkspaceAccess,
) -> tuple[Path, ...]:
    raw_paths: list[Any]
    if tool_name == "apply_patch":
        if arguments.get("dry_run") is True:
            return ()
        edits = arguments.get("edits")
        if not isinstance(edits, list):
            return ()
        raw_paths = [
            edit.get("path")
            for edit in edits
            if isinstance(edit, Mapping)
        ]
    else:
        raw_paths = [arguments.get("path")]

    paths: list[Path] = []
    seen: set[Path] = set()
    for raw_path in raw_paths:
        if not isinstance(raw_path, str) or not raw_path.strip():
            continue
        resolved = access.resolve_write(raw_path)
        if isinstance(resolved, str) or resolved in seen:
            continue
        seen.add(resolved)
        paths.append(resolved)
        if len(paths) == _MAX_TRACKED_FILES:
            break
    return tuple(paths)


def _read_snapshot(path: Path) -> _FileSnapshot:
    try:
        if not path.is_file():
            return _FileSnapshot(
                exists=False,
                text="",
                fingerprint=(0, 0, None),
            )

        stat = path.stat()
        size = stat.st_size
        modified_ns = stat.st_mtime_ns
        if size > _MAX_SNAPSHOT_BYTES:
            return _FileSnapshot(
                exists=True,
                text=None,
                fingerprint=(size, modified_ns, None),
            )

        raw = path.read_bytes()
        digest = sha256(raw).digest()
        if is_binary_bytes(raw):
            text = None
        else:
            try:
                text = raw.decode("utf-8").replace("\r\n", "\n")
            except UnicodeDecodeError:
                text = None
        return _FileSnapshot(
            exists=True,
            text=text,
            fingerprint=(len(raw), modified_ns, digest),
        )
    except OSError:
        return _FileSnapshot(
            exists=False,
            text=None,
            fingerprint=(0, 0, None),
        )


def _build_change(
    display_path: str,
    before: _FileSnapshot,
    after: _FileSnapshot,
) -> dict[str, Any] | None:
    if not _snapshot_changed(before, after):
        return None

    change: dict[str, Any] = {
        "path": display_path,
        "added": 0,
        "deleted": 0,
    }
    if before.text is None or after.text is None:
        return change

    added, deleted = _line_diff_stats(before.text, after.text)
    change["added"] = added
    change["deleted"] = deleted
    unified_diff, truncated = _unified_diff(
        before.text,
        after.text,
        path=display_path,
    )
    if unified_diff:
        change["unified_diff"] = unified_diff
    if truncated:
        change["truncated"] = True
    return change


def _snapshot_changed(
    before: _FileSnapshot,
    after: _FileSnapshot,
) -> bool:
    if before.exists != after.exists:
        return True
    if before.text is not None and after.text is not None:
        return before.text != after.text
    return before.fingerprint != after.fingerprint


def _line_diff_stats(before: str, after: str) -> tuple[int, int]:
    before_lines = before.splitlines()
    after_lines = after.splitlines()
    added = 0
    deleted = 0
    matcher = difflib.SequenceMatcher(
        a=before_lines,
        b=after_lines,
        autojunk=False,
    )
    for tag, old_start, old_end, new_start, new_end in matcher.get_opcodes():
        if tag in ("replace", "delete"):
            deleted += old_end - old_start
        if tag in ("replace", "insert"):
            added += new_end - new_start
    return added, deleted


def _unified_diff(
    before: str,
    after: str,
    *,
    path: str,
) -> tuple[str | None, bool]:
    lines = list(
        difflib.unified_diff(
            before.splitlines(),
            after.splitlines(),
            fromfile=path,
            tofile=path,
            n=_DIFF_CONTEXT_LINES,
            lineterm="",
        )
    )
    if not lines:
        return None, False
    if len(lines) > _MAX_DIFF_LINES:
        return None, True

    truncated = False
    bounded: list[str] = []
    for line in lines:
        if len(line) > _MAX_DIFF_LINE_CHARACTERS:
            bounded.append(line[:_MAX_DIFF_LINE_CHARACTERS])
            truncated = True
        else:
            bounded.append(line)
    return "\n".join(bounded), truncated
