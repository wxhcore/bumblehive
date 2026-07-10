import difflib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..adapters.function import CallableTool
from ..registry import ToolRegistry
from .state import BuiltinToolState, _session_scoped_file_handler
from .workspace import (
    FileStates,
    WorkspaceAccess,
    current_file_states,
    current_workspace_access,
)


_APPLY_PATCH_DESCRIPTION = (
    "Apply structured text edits to one or more UTF-8 files inside the workspace."
)

_APPLY_PATCH_PARAMETERS: dict[str, Any] = {
    "type": "object",
    "properties": {
        "edits": {
            "type": "array",
            "description": "List of edits to apply.",
            "minItems": 1,
            "maxItems": 20,
            "items": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative file path to edit.",
                    },
                    "action": {
                        "type": "string",
                        "enum": ["add", "replace"],
                        "description": "Use add to create/append; replace for exact text replacement.",
                    },
                    "old_text": {
                        "type": "string",
                        "description": "Exact text to replace. Required for replace.",
                    },
                    "new_text": {
                        "type": "string",
                        "description": "Text to add or replace with.",
                    },
                },
                "required": ["path", "action"],
                "allOf": [
                    {
                        "if": {
                            "properties": {"action": {"const": "add"}},
                            "required": ["action"],
                        },
                        "then": {"required": ["new_text"]},
                    },
                    {
                        "if": {
                            "properties": {"action": {"const": "replace"}},
                            "required": ["action"],
                        },
                        "then": {
                            "required": ["old_text", "new_text"],
                            "properties": {
                                "old_text": {"minLength": 1},
                            },
                        },
                    },
                ],
                "additionalProperties": False,
            },
        },
        "dry_run": {
            "type": "boolean",
            "description": "Validate and summarize edits without writing files. Default false.",
        },
    },
    "required": ["edits"],
    "additionalProperties": False,
}


class PatchError(ValueError):
    """Raised when a structured patch cannot be applied."""


@dataclass(frozen=True)
class PatchSummary:
    action: str
    path: str
    added: int
    deleted: int


class StructuredPatch:
    def __init__(
        self,
        file_states: FileStates | None = None,
    ) -> None:
        self._explicit_file_states = file_states
        self._fallback_file_states = FileStates()

    @property
    def file_states(self) -> FileStates:
        if self._explicit_file_states is not None:
            return self._explicit_file_states
        return current_file_states(self._fallback_file_states)

    def apply_patch(
        self,
        edits: list[dict[str, Any]],
        dry_run: bool = False,
    ) -> dict[str, Any]:
        try:
            writes: dict[Path, str] = {}
            summaries: list[PatchSummary] = []

            for edit in edits:
                summary = self._prepare_edit(edit, writes)
                summaries.append(summary)

            if dry_run:
                return {
                    "success": True,
                    "dry_run": True,
                    "edits": [_summary_dict(summary) for summary in summaries],
                }

            backups: dict[Path, bytes | None] = {}
            for path in writes:
                backups[path] = path.read_bytes() if path.exists() else None

            try:
                for path, content in writes.items():
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(content, encoding="utf-8", newline="")
            except Exception:
                for path, data in backups.items():
                    if data is None:
                        if path.exists():
                            path.unlink()
                    else:
                        path.parent.mkdir(parents=True, exist_ok=True)
                        path.write_bytes(data)
                raise
            for path in writes:
                self.file_states.record_write(path)

            return {
                "success": True,
                "dry_run": False,
                "edits": [_summary_dict(summary) for summary in summaries],
            }
        except PermissionError as exc:
            return {"error": str(exc)}
        except PatchError as exc:
            return {"error": str(exc)}
        except Exception as exc:
            return {"error": str(exc)}

    def _prepare_edit(
        self,
        edit: dict[str, Any],
        writes: dict[Path, str],
    ) -> PatchSummary:
        if not isinstance(edit, dict):
            raise PatchError("each edit must be an object")
        raw_path = edit.get("path")
        if not isinstance(raw_path, str) or not raw_path.strip():
            raise PatchError("path is required for each edit")
        path = _validate_relative_path(raw_path)
        action = edit.get("action")
        if action not in {"add", "replace"}:
            raise PatchError(f"unknown action for {path}: {action}")

        access = self._access()
        resolved = access.resolve(path)
        if isinstance(resolved, str):
            raise PatchError(f"{path}: {resolved}")

        if action == "add":
            return self._prepare_add(path, resolved, edit, writes)
        return self._prepare_replace(path, resolved, edit, writes)

    def _prepare_add(
        self,
        path: str,
        resolved: Path,
        edit: dict[str, Any],
        writes: dict[Path, str],
    ) -> PatchSummary:
        new_text = edit.get("new_text")
        if new_text is None:
            raise PatchError(f"new_text required for add: {path}")

        pending = writes.get(resolved)
        if pending is not None:
            content = pending
            exists = True
        elif resolved.exists():
            content = _read_utf8_file(resolved, path)
            exists = True
        else:
            content = ""
            exists = False

        normalized_new = str(new_text).replace("\r\n", "\n")
        if exists:
            updated = content.replace("\r\n", "\n") + normalized_new
            action_name = "update"
            added, deleted = _line_diff_stats(content, updated)
        else:
            updated = normalized_new
            action_name = "add"
            added, deleted = _text_line_count(updated), 0

        if updated and not updated.endswith("\n"):
            updated += "\n"
        writes[resolved] = _restore_newlines(content, updated)
        return PatchSummary(action=action_name, path=path, added=added, deleted=deleted)

    def _prepare_replace(
        self,
        path: str,
        resolved: Path,
        edit: dict[str, Any],
        writes: dict[Path, str],
    ) -> PatchSummary:
        old_text = edit.get("old_text")
        if not old_text:
            raise PatchError(f"old_text required for replace: {path}")
        new_text = edit.get("new_text")
        if new_text is None:
            raise PatchError(f"new_text required for replace: {path}")

        if resolved in writes:
            content = writes[resolved]
        else:
            if not resolved.exists():
                raise PatchError(f"file to update does not exist: {path}")
            if not resolved.is_file():
                raise PatchError(f"path to update is not a file: {path}")
            content = _read_utf8_file(resolved, path)

        normalized_content = content.replace("\r\n", "\n")
        normalized_old = str(old_text).replace("\r\n", "\n")
        index = normalized_content.find(normalized_old)
        if index < 0:
            raise PatchError(f"old_text not found in {path}")
        if normalized_content.find(normalized_old, index + 1) >= 0:
            raise PatchError(f"old_text appears multiple times in {path}")

        updated = (
            normalized_content[:index]
            + str(new_text).replace("\r\n", "\n")
            + normalized_content[index + len(normalized_old):]
        )
        if updated and not updated.endswith("\n"):
            updated += "\n"
        writes[resolved] = _restore_newlines(content, updated)
        added, deleted = _line_diff_stats(content, updated)
        return PatchSummary(action="update", path=path, added=added, deleted=deleted)

    def _access(self) -> WorkspaceAccess:
        return current_workspace_access()


_ABSOLUTE_WINDOWS_RE = re.compile(r"^[A-Za-z]:[\\/]")


def _validate_relative_path(path: str) -> str:
    normalized = path.strip()
    if not normalized:
        raise PatchError("patch path cannot be empty")
    if "\0" in normalized:
        raise PatchError(f"patch path contains a null byte: {path!r}")
    if normalized.startswith(("~", "/", "\\")) or _ABSOLUTE_WINDOWS_RE.match(normalized):
        raise PatchError(f"patch path must be relative: {path}")
    if any(part in ("", ".", "..") for part in re.split(r"[\\/]+", normalized)):
        raise PatchError(f"patch path must not contain empty or parent segments: {path}")
    return normalized


def _read_utf8_file(path: Path, display_path: str) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise PatchError(f"file is not UTF-8 text: {display_path}") from exc


def _restore_newlines(original: str, updated_lf: str) -> str:
    if "\r\n" in original:
        return updated_lf.replace("\n", "\r\n")
    return updated_lf


def _text_line_count(text: str) -> int:
    return len(text.splitlines()) if text else 0


def _line_diff_stats(old: str, new: str) -> tuple[int, int]:
    added = 0
    deleted = 0
    matcher = difflib.SequenceMatcher(
        None,
        old.replace("\r\n", "\n").splitlines(),
        new.replace("\r\n", "\n").splitlines(),
    )
    for tag, old_start, old_end, new_start, new_end in matcher.get_opcodes():
        if tag in ("replace", "delete"):
            deleted += old_end - old_start
        if tag in ("replace", "insert"):
            added += new_end - new_start
    return added, deleted


def _summary_dict(summary: PatchSummary) -> dict[str, Any]:
    return {
        "action": summary.action,
        "path": summary.path,
        "added": summary.added,
        "deleted": summary.deleted,
    }


def register_apply_patch_tool(
    registry: ToolRegistry,
    *,
    state: BuiltinToolState,
) -> CallableTool:
    """Register the apply_patch tool on a registry."""
    patch = StructuredPatch()
    return registry.register(
        CallableTool(
            name="apply_patch",
            description=_APPLY_PATCH_DESCRIPTION,
            parameters=_APPLY_PATCH_PARAMETERS,
            handler=_session_scoped_file_handler(state, patch.apply_patch),
            exclusive=True,
        )
    )
