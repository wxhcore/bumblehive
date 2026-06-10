from pathlib import Path
from typing import Any

from ..adapters.function import CallableTool
from ..runtime import ToolRuntimeContext
from ..registry import ToolRegistry


READ_FILE_DESCRIPTION = (
    "Read a UTF-8 text file inside the project workspace, optionally by line range."
)

READ_FILE_PARAMETERS: dict[str, Any] = {
    "type": "object",
    "properties": {
        "path": {
            "type": "string",
            "description": "File path to read, relative to the workspace.",
        },
        "start_line": {
            "type": "integer",
            "description": "Optional 1-based line number to start reading from.",
        },
        "max_lines": {
            "type": "integer",
            "description": "Optional maximum number of lines to return.",
        },
    },
    "required": ["path"],
    "additionalProperties": False,
}

WRITE_FILE_DESCRIPTION = "Create or overwrite a UTF-8 text file inside the project workspace."

WRITE_FILE_PARAMETERS: dict[str, Any] = {
    "type": "object",
    "properties": {
        "path": {
            "type": "string",
            "description": "File path to write, relative to the workspace.",
        },
        "content": {
            "type": "string",
            "description": "Full text content to write to the file.",
        },
    },
    "required": ["path", "content"],
    "additionalProperties": False,
}


class WorkspaceFiles:
    _MAX_READ_CHARS = 12_000
    _MAX_WRITE_CHARS = 200_000

    def __init__(self, workspace: str | Path) -> None:
        self.workspace = Path(workspace).expanduser().resolve()

    def read_file(
        self,
        path: str,
        start_line: int | None = None,
        max_lines: int | None = None,
    ) -> dict[str, Any]:
        resolved = self._resolve_path(path)
        if isinstance(resolved, str):
            return {"error": resolved}
        if not resolved.exists() or not resolved.is_file():
            return {"error": "path does not exist or is not a file", "path": str(resolved)}

        try:
            lines = resolved.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError:
            return {"error": "file is not valid UTF-8 text", "path": str(resolved)}

        total_lines = len(lines)
        start = max((start_line or 1) - 1, 0)
        end = total_lines if max_lines is None else min(start + max_lines, total_lines)
        selected = lines[start:end]
        content = "\n".join(selected)

        truncated = False
        if len(content) > self._MAX_READ_CHARS:
            content = content[: self._MAX_READ_CHARS]
            truncated = True

        return {
            "path": str(resolved),
            "start_line": start + 1,
            "end_line": end,
            "total_lines": total_lines,
            "content": content,
            "truncated": truncated,
        }

    def write_file(self, path: str, content: str) -> dict[str, Any]:
        resolved = self._resolve_path(path)
        if isinstance(resolved, str):
            return {"error": resolved}
        if len(content) > self._MAX_WRITE_CHARS:
            return {"error": f"content is too large; max {self._MAX_WRITE_CHARS} chars"}

        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(content, encoding="utf-8")
        return {
            "path": str(resolved),
            "bytes_written": len(content.encode("utf-8")),
            "success": True,
        }

    def _resolve_path(self, path: str) -> Path | str:
        raw = Path(path).expanduser()
        resolved = raw.resolve() if raw.is_absolute() else (self.workspace / raw).resolve()

        if resolved != self.workspace and self.workspace not in resolved.parents:
            return "path is outside workspace"
        return resolved


def _workspace_from_context(workspace_or_context: str | Path | ToolRuntimeContext) -> Path:
    if isinstance(workspace_or_context, ToolRuntimeContext):
        return workspace_or_context.workspace
    return Path(workspace_or_context)


def register_read_file_tool(
    registry: ToolRegistry,
    workspace: str | Path | ToolRuntimeContext,
) -> CallableTool:
    """Register the read_file tool on a registry."""
    files = WorkspaceFiles(_workspace_from_context(workspace))
    return registry.register(
        CallableTool(
            name="read_file",
            description=READ_FILE_DESCRIPTION,
            parameters=READ_FILE_PARAMETERS,
            handler=files.read_file,
            read_only=True,
        )
    )


def register_write_file_tool(
    registry: ToolRegistry,
    workspace: str | Path | ToolRuntimeContext,
) -> CallableTool:
    """Register the write_file tool on a registry."""
    files = WorkspaceFiles(_workspace_from_context(workspace))
    return registry.register(
        CallableTool(
            name="write_file",
            description=WRITE_FILE_DESCRIPTION,
            parameters=WRITE_FILE_PARAMETERS,
            handler=files.write_file,
            exclusive=True,
        )
    )
