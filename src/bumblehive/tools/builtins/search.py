import fnmatch
import os
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from ..adapters.function import CallableTool
from ..registry import ToolRegistry
from .workspace import (
    _DEFAULT_IGNORE_DIRS,
    WorkspaceAccess,
    current_workspace_access,
    is_binary_bytes,
)


_FIND_FILES_DESCRIPTION = (
    "Locate files by path terms, glob, or file type. Use this before read_file when "
    "the path is uncertain, and prefer it over shell find or ls for ordinary file "
    "discovery. Common dependency, build, cache, and version-control directories "
    "are ignored."
)

_FIND_FILES_PARAMETERS: dict[str, Any] = {
    "type": "object",
    "properties": {
        "path": {
            "type": "string",
            "description": (
                "Directory or file to search. Relative paths resolve from the workspace; "
                "absolute paths must be inside a readable root. Default '.'."
            ),
        },
        "query": {
            "type": "string",
            "description": (
                "Case-insensitive path search. Whitespace-separated terms must all "
                "appear in the path."
            ),
        },
        "glob": {
            "type": "string",
            "description": "Optional file filter, e.g. '*.py' or 'tests/**/*.py'.",
        },
        "type": {
            "type": "string",
            "description": "Optional type shorthand, e.g. py, ts, md, json.",
        },
        "include_dirs": {
            "type": "boolean",
            "description": "Include matching directories. Default false.",
        },
        "sort": {
            "type": "string",
            "enum": ["path", "modified"],
            "description": (
                "Sort alphabetically by path or by most recently modified first. "
                "Default path."
            ),
        },
        "head_limit": {
            "type": "integer",
            "description": "Maximum paths to return. Default 200, 0 for all.",
            "minimum": 0,
            "maximum": 1000,
        },
        "offset": {
            "type": "integer",
            "description": "Skip this many matches before returning results.",
            "minimum": 0,
            "maximum": 100000,
        },
    },
    "additionalProperties": False,
}

_GREP_DESCRIPTION = (
    "Search text files with a regular expression, or set fixed_strings=true for a "
    "literal search. The default output_mode returns matching file paths only; use "
    "content for matching lines and context, or count for per-file totals. Prefer "
    "this over shell grep. Binary files and files larger than 2 MB are skipped, and "
    "content output is capped at 128,000 characters."
)

_GREP_PARAMETERS: dict[str, Any] = {
    "type": "object",
    "properties": {
        "pattern": {
            "type": "string",
            "description": (
                "Regular expression to search for. Set fixed_strings=true to treat it "
                "as literal text."
            ),
            "minLength": 1,
        },
        "path": {
            "type": "string",
            "description": (
                "File or directory to search. Relative paths resolve from the workspace; "
                "absolute paths must be inside a readable root. Default '.'."
            ),
        },
        "glob": {
            "type": "string",
            "description": "Optional file filter, e.g. '*.py' or 'src/**/*.py'.",
        },
        "type": {
            "type": "string",
            "description": "Optional type shorthand, e.g. py, ts, md, json.",
        },
        "case_insensitive": {
            "type": "boolean",
            "description": "Case-insensitive search. Default false.",
        },
        "fixed_strings": {
            "type": "boolean",
            "description": "Treat pattern as plain text instead of regex. Default false.",
        },
        "output_mode": {
            "type": "string",
            "enum": ["content", "files_with_matches", "count"],
            "description": (
                "content returns matching lines with optional context; "
                "files_with_matches returns file paths; count returns matching line "
                "counts per file. Default files_with_matches."
            ),
        },
        "context_before": {
            "type": "integer",
            "description": "Lines of context before each content match.",
            "minimum": 0,
            "maximum": 20,
        },
        "context_after": {
            "type": "integer",
            "description": "Lines of context after each content match.",
            "minimum": 0,
            "maximum": 20,
        },
        "head_limit": {
            "type": "integer",
            "description": "Maximum results to return. Default 250, 0 for all.",
            "minimum": 0,
            "maximum": 1000,
        },
        "offset": {
            "type": "integer",
            "description": "Skip this many results before applying head_limit.",
            "minimum": 0,
            "maximum": 100000,
        },
    },
    "required": ["pattern"],
    "additionalProperties": False,
}

_TYPE_GLOB_MAP = {
    "css": ("*.css", "*.scss", "*.sass"),
    "go": ("*.go",),
    "html": ("*.html", "*.htm"),
    "java": ("*.java",),
    "js": ("*.js", "*.jsx", "*.mjs", "*.cjs"),
    "json": ("*.json",),
    "jsx": ("*.jsx",),
    "md": ("*.md", "*.mdx"),
    "py": ("*.py", "*.pyi"),
    "python": ("*.py", "*.pyi"),
    "rs": ("*.rs",),
    "rust": ("*.rs",),
    "sh": ("*.sh", "*.bash"),
    "sql": ("*.sql",),
    "toml": ("*.toml",),
    "ts": ("*.ts", "*.tsx", "*.mts", "*.cts"),
    "tsx": ("*.tsx",),
    "yaml": ("*.yaml", "*.yml"),
    "yml": ("*.yaml", "*.yml"),
}


@dataclass(frozen=True)
class ReadTextResult:
    lines: list[str] | None
    skipped_reason: str | None = None


class WorkspaceSearch:
    _DEFAULT_FIND_LIMIT = 200
    _DEFAULT_GREP_LIMIT = 250
    _MAX_FILE_BYTES = 2_000_000
    _MAX_RESULT_CHARS = 128_000

    def find_files(
        self,
        path: str = ".",
        query: str | None = None,
        glob: str | None = None,
        type: str | None = None,
        include_dirs: bool = False,
        sort: str = "path",
        head_limit: int | None = None,
        offset: int = 0,
    ) -> dict[str, Any]:
        access = self._access()
        resolved = access.resolve_read(path or ".")
        if isinstance(resolved, str):
            return {"error": resolved}
        if not resolved.exists():
            return {"error": "path does not exist", "path": str(resolved)}
        if not resolved.is_dir() and not resolved.is_file():
            return {"error": "path is not searchable", "path": str(resolved)}
        if sort not in {"path", "modified"}:
            return {"error": "sort must be 'path' or 'modified'"}

        root = resolved if resolved.is_dir() else resolved.parent
        matches: list[tuple[str, float]] = []
        for candidate in self._iter_paths(resolved, include_dirs=include_dirs):
            checked = access.resolve_read(candidate)
            if isinstance(checked, str):
                continue
            is_dir = checked.is_dir()
            is_file = checked.is_file()
            if is_dir and not include_dirs:
                continue
            if WorkspaceAccess.is_ignored(candidate.relative_to(root)):
                continue
            if is_dir and type:
                continue

            rel_path = candidate.relative_to(root).as_posix()
            display_path = access.relative_display_path(candidate, root=root)
            if glob and not _matches_glob(rel_path, candidate.name, glob):
                continue
            if is_file and not _matches_type(candidate.name, type):
                continue
            if not _matches_query(display_path, query):
                continue

            try:
                mtime = checked.stat().st_mtime
            except OSError:
                mtime = 0.0
            matches.append((display_path + ("/" if is_dir else ""), mtime))

        if sort == "modified":
            matches.sort(key=lambda item: (-item[1], item[0]))
        else:
            matches.sort(key=lambda item: item[0])

        paths = [match[0] for match in matches]
        paged, truncated = _paginate(paths, head_limit, offset, self._DEFAULT_FIND_LIMIT)
        return {
            "matches": paged,
            "total_matches": len(paths),
            "offset": offset,
            "truncated": truncated,
        }

    def grep(
        self,
        pattern: str,
        path: str = ".",
        glob: str | None = None,
        type: str | None = None,
        case_insensitive: bool = False,
        fixed_strings: bool = False,
        output_mode: str = "files_with_matches",
        context_before: int = 0,
        context_after: int = 0,
        head_limit: int | None = None,
        offset: int = 0,
    ) -> dict[str, Any]:
        if output_mode not in {"content", "files_with_matches", "count"}:
            return {"error": "output_mode must be content, files_with_matches, or count"}
        access = self._access()
        resolved = access.resolve_read(path or ".")
        if isinstance(resolved, str):
            return {"error": resolved}
        if not resolved.exists():
            return {"error": "path does not exist", "path": str(resolved)}

        flags = re.IGNORECASE if case_insensitive else 0
        try:
            regex = re.compile(re.escape(pattern) if fixed_strings else pattern, flags)
        except re.error as exc:
            return {"error": f"invalid regex pattern: {exc}"}

        files = [resolved] if resolved.is_file() else list(self._iter_files(resolved))
        limit = None if head_limit == 0 else head_limit or self._DEFAULT_GREP_LIMIT
        returned = 0
        files_with_matches: list[str] = []
        counts: list[dict[str, Any]] = []
        file_mtimes: dict[str, float] = {}
        content_matches: list[dict[str, Any]] = []
        total_matches = 0
        seen_content_matches = 0
        truncated = False
        truncated_reason: str | None = None
        content_chars = 0
        skipped_binary = 0
        skipped_large = 0
        skipped_unreadable = 0

        root = resolved if resolved.is_dir() else resolved.parent
        for candidate in files:
            checked = access.resolve_read(candidate)
            if isinstance(checked, str):
                skipped_unreadable += 1
                continue
            if WorkspaceAccess.is_ignored(candidate.relative_to(root)):
                continue
            rel_path = candidate.relative_to(root).as_posix()
            if glob and not _matches_glob(rel_path, candidate.name, glob):
                continue
            if not _matches_type(candidate.name, type):
                continue

            read_result = self._read_text_lines(checked)
            if read_result.lines is None:
                if read_result.skipped_reason == "binary":
                    skipped_binary += 1
                elif read_result.skipped_reason == "large":
                    skipped_large += 1
                else:
                    skipped_unreadable += 1
                continue
            lines = read_result.lines

            display_path = access.relative_display_path(candidate, root=root)
            file_match_count = 0
            for index, line in enumerate(lines):
                if not regex.search(line):
                    continue
                total_matches += 1
                file_match_count += 1
                if output_mode != "content":
                    continue
                seen_content_matches += 1
                if seen_content_matches <= offset:
                    continue
                if limit is not None and returned >= limit:
                    truncated = True
                    truncated_reason = "head_limit"
                    break
                start = max(0, index - context_before)
                end = min(len(lines), index + context_after + 1)
                result_match = {
                    "path": display_path,
                    "line": index + 1,
                    "text": line,
                    "context": [
                        {"line": ctx_index + 1, "text": lines[ctx_index]}
                        for ctx_index in range(start, end)
                    ],
                }
                match_chars = _content_match_chars(result_match)
                if content_chars + match_chars > self._MAX_RESULT_CHARS:
                    truncated = True
                    truncated_reason = "output_size"
                    break
                content_matches.append(result_match)
                content_chars += match_chars
                returned += 1
            if output_mode == "content" and truncated:
                break
            if file_match_count == 0:
                continue

            try:
                file_mtimes[display_path] = checked.stat().st_mtime
            except OSError:
                file_mtimes[display_path] = 0.0

            if output_mode == "files_with_matches":
                files_with_matches.append(display_path)
            elif output_mode == "count":
                counts.append({"path": display_path, "count": file_match_count})

        result: dict[str, Any] = {
            "total_matches": total_matches,
            "truncated": truncated,
            "skipped_binary": skipped_binary,
            "skipped_large": skipped_large,
            "skipped_unreadable": skipped_unreadable,
        }
        if truncated_reason:
            result["truncated_reason"] = truncated_reason
        if output_mode == "files_with_matches":
            files_with_matches.sort(key=lambda path: (-file_mtimes.get(path, 0.0), path))
            paged, truncated = _slice_items(files_with_matches, limit, offset)
            result["files"] = paged
            result["truncated"] = truncated
            if truncated:
                result["truncated_reason"] = "head_limit"
        elif output_mode == "count":
            counts.sort(
                key=lambda item: (-file_mtimes.get(item["path"], 0.0), item["path"])
            )
            paged_counts, truncated = _slice_items(counts, limit, offset)
            result["counts"] = paged_counts
            result["truncated"] = truncated
            if truncated:
                result["truncated_reason"] = "head_limit"
        else:
            result["matches"] = content_matches
        return result

    def _iter_paths(self, root: Path, *, include_dirs: bool) -> list[Path]:
        if root.is_file():
            return [root]

        paths: list[Path] = []
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = sorted(name for name in dirnames if name not in _DEFAULT_IGNORE_DIRS)
            current = Path(dirpath)
            if include_dirs and current != root:
                paths.append(current)
            paths.extend(current / filename for filename in sorted(filenames))
        return paths

    def _iter_files(self, root: Path) -> list[Path]:
        return [path for path in self._iter_paths(root, include_dirs=False) if path.is_file()]

    def _read_text_lines(self, path: Path) -> ReadTextResult:
        try:
            if path.stat().st_size > self._MAX_FILE_BYTES:
                return ReadTextResult(None, "large")
            raw = path.read_bytes()
        except OSError:
            return ReadTextResult(None, "unreadable")
        if is_binary_bytes(raw):
            return ReadTextResult(None, "binary")
        try:
            return ReadTextResult(raw.decode("utf-8").splitlines())
        except UnicodeDecodeError:
            return ReadTextResult(None, "binary")

    def _access(self) -> WorkspaceAccess:
        return current_workspace_access()


def _matches_query(path: str, query: str | None) -> bool:
    if not query:
        return True
    haystack = path.lower()
    terms = [part for part in query.lower().split() if part]
    return all(term in haystack for term in terms)


def _matches_glob(rel_path: str, name: str, pattern: str) -> bool:
    normalized = pattern.strip().replace("\\", "/")
    if not normalized:
        return True
    if "/" in normalized or normalized.startswith("**"):
        return PurePosixPath(rel_path).match(normalized)
    return fnmatch.fnmatch(name, normalized)


def _matches_type(name: str, file_type: str | None) -> bool:
    if not file_type:
        return True
    lowered = file_type.strip().lower()
    patterns = _TYPE_GLOB_MAP.get(lowered, (f"*.{lowered}",))
    return any(fnmatch.fnmatch(name.lower(), pattern.lower()) for pattern in patterns)


def _paginate(
    items: list[str],
    head_limit: int | None,
    offset: int,
    default_limit: int,
) -> tuple[list[str], bool]:
    limit = None if head_limit == 0 else head_limit or default_limit
    if limit is None:
        return items[offset:], False
    return items[offset:offset + limit], len(items) > offset + limit


def _slice_items(
    items: list[Any],
    limit: int | None,
    offset: int,
) -> tuple[list[Any], bool]:
    if limit is None:
        return items[offset:], False
    return items[offset:offset + limit], len(items) > offset + limit


def _content_match_chars(match: dict[str, Any]) -> int:
    chars = len(str(match.get("path", ""))) + len(str(match.get("text", ""))) + 32
    for context in match.get("context", []):
        if isinstance(context, dict):
            chars += len(str(context.get("text", ""))) + 16
    return chars


def register_find_files_tool(
    registry: ToolRegistry,
) -> CallableTool:
    """Register the find_files tool on a registry."""
    search = WorkspaceSearch()
    return registry.register(
        CallableTool(
            name="find_files",
            description=_FIND_FILES_DESCRIPTION,
            parameters=_FIND_FILES_PARAMETERS,
            handler=search.find_files,
            parallel_safe=True,
        )
    )


def register_grep_tool(
    registry: ToolRegistry,
) -> CallableTool:
    """Register the grep tool on a registry."""
    search = WorkspaceSearch()
    return registry.register(
        CallableTool(
            name="grep",
            description=_GREP_DESCRIPTION,
            parameters=_GREP_PARAMETERS,
            handler=search.grep,
            parallel_safe=True,
        )
    )
