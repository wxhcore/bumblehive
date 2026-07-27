from collections.abc import Mapping
from typing import Any


_SHELL_OUTPUT_PREVIEW_CHARS = 16_000
_SHELL_STDERR_PREVIEW_CHARS = 6_000
_MUTATION_DIFF_CHARS = 256_000
_MUTATION_FILE_ITEMS = 20
_MUTATION_TOOLS = frozenset({"write_file", "edit_file", "apply_patch"})
_SHELL_TOOLS = frozenset({"exec", "write_stdin"})
_READ_TOOLS = frozenset({"read_file", "list_dir", "find_files", "grep"})
_READ_DETAIL_ITEMS = 20
_SHELL_SESSION_ITEMS = 20


def tool_detail(
    name: str,
    document: Mapping[str, Any],
    *,
    file_changes: Any = None,
) -> dict[str, Any] | None:
    if name == "list_exec_sessions":
        return _exec_sessions_tool_detail(document)
    if name in _SHELL_TOOLS:
        return _shell_tool_detail(document)
    if name in _MUTATION_TOOLS:
        detail = _mutation_tool_detail(document)
        changes = _mutation_file_changes(file_changes)
        if changes:
            detail["fileChanges"] = changes
        return detail
    if name in _READ_TOOLS:
        return _read_tool_detail(name, document)
    return None


def _exec_sessions_tool_detail(
    document: Mapping[str, Any],
) -> dict[str, Any]:
    detail: dict[str, Any] = {"kind": "shellSessions", "sessions": []}
    sessions = document.get("sessions")
    if not isinstance(sessions, list):
        return detail

    bounded_sessions: list[dict[str, Any]] = []
    for value in sessions[:_SHELL_SESSION_ITEMS]:
        if not isinstance(value, Mapping):
            continue
        session_id = value.get("session_id")
        if not isinstance(session_id, str) or not session_id:
            continue
        session: dict[str, Any] = {
            "sessionId": session_id[:300],
            "command": (
                value.get("command", "")[:4_000]
                if isinstance(value.get("command"), str)
                else ""
            ),
            "running": (
                value.get("running")
                if isinstance(value.get("running"), bool)
                else False
            ),
        }
        _copy_text(
            session,
            "workingDirectory",
            value,
            "working_dir",
            1_000,
        )
        exit_code = value.get("exit_code")
        if exit_code is None or (
            isinstance(exit_code, int) and not isinstance(exit_code, bool)
        ):
            session["exitCode"] = exit_code
        for target_key, source_key in (
            ("elapsedSeconds", "elapsed_seconds"),
            ("idleSeconds", "idle_seconds"),
        ):
            duration = value.get(source_key)
            if isinstance(duration, (int, float)) and not isinstance(
                duration,
                bool,
            ):
                session[target_key] = float(duration)
        remaining_seconds = value.get("remaining_seconds")
        if remaining_seconds is None:
            session["remainingSeconds"] = None
        elif isinstance(remaining_seconds, (int, float)) and not isinstance(
            remaining_seconds,
            bool,
        ):
            session["remainingSeconds"] = float(remaining_seconds)
        bounded_sessions.append(session)

    detail["sessions"] = bounded_sessions
    return detail


def _read_tool_detail(
    name: str,
    document: Mapping[str, Any],
) -> dict[str, Any]:
    detail: dict[str, Any] = {"kind": "read"}
    _copy_text(detail, "path", document, "path", 1_000)
    _copy_if_number(detail, "startLine", document, "start_line")
    _copy_if_number(detail, "endLine", document, "end_line")
    _copy_if_number(detail, "totalLines", document, "total_lines")
    _copy_text(detail, "pages", document, "pages", 100)
    _copy_if_number(detail, "totalPages", document, "total_pages")
    _copy_if_number(detail, "totalEntries", document, "total_entries")
    _copy_if_number(detail, "totalMatches", document, "total_matches")
    _copy_if_type(detail, "truncated", document, "truncated", bool)
    _copy_if_type(detail, "deduplicated", document, "deduplicated", bool)

    items: list[str] = []
    if name == "list_dir":
        entries = document.get("entries")
        if isinstance(entries, list):
            for entry in entries[:_READ_DETAIL_ITEMS]:
                if not isinstance(entry, Mapping):
                    continue
                path = entry.get("path")
                if isinstance(path, str):
                    items.append(path[:1_000])
    elif name == "find_files":
        matches = document.get("matches")
        if isinstance(matches, list):
            items.extend(
                item[:1_000]
                for item in matches[:_READ_DETAIL_ITEMS]
                if isinstance(item, str)
            )
    elif name == "grep":
        items.extend(_grep_result_paths(document))

    if items:
        detail["items"] = list(dict.fromkeys(items))[:_READ_DETAIL_ITEMS]
    return detail


def _grep_result_paths(document: Mapping[str, Any]) -> list[str]:
    paths: list[str] = []
    files = document.get("files")
    if isinstance(files, list):
        paths.extend(
            item[:1_000] for item in files[:_READ_DETAIL_ITEMS] if isinstance(item, str)
        )

    for key in ("counts", "matches"):
        values = document.get(key)
        if not isinstance(values, list):
            continue
        for item in values[:_READ_DETAIL_ITEMS]:
            if not isinstance(item, Mapping):
                continue
            path = item.get("path")
            if isinstance(path, str):
                paths.append(path[:1_000])
    return list(dict.fromkeys(paths))[:_READ_DETAIL_ITEMS]


def _shell_tool_detail(document: Mapping[str, Any]) -> dict[str, Any]:
    output, output_omitted = _bounded_text(
        document.get("output"),
        _SHELL_OUTPUT_PREVIEW_CHARS,
    )
    stdout, stdout_omitted = _bounded_text(
        document.get("stdout"),
        _SHELL_OUTPUT_PREVIEW_CHARS,
    )
    stderr, stderr_omitted = _bounded_text(
        document.get("stderr"),
        _SHELL_STDERR_PREVIEW_CHARS,
    )
    upstream_truncated = sum(
        _nonnegative_int(document.get(key))
        for key in (
            "truncated_chars",
            "stdout_truncated_chars",
            "stderr_truncated_chars",
        )
    )
    detail: dict[str, Any] = {
        "kind": "shell",
        "output": output,
        "stdout": stdout,
        "stderr": stderr,
        "truncatedCharacters": (
            upstream_truncated + output_omitted + stdout_omitted + stderr_omitted
        ),
    }
    _copy_text(detail, "sessionId", document, "session_id", 300)
    _copy_text(detail, "command", document, "command", 4_000)
    _copy_text(detail, "workingDirectory", document, "working_dir", 1_000)
    _copy_if_type(detail, "running", document, "running", bool)
    _copy_if_type(detail, "done", document, "done", bool)
    _copy_if_type(detail, "timedOut", document, "timed_out", bool)
    _copy_if_type(detail, "terminated", document, "terminated", bool)
    exit_code = document.get("exit_code")
    if exit_code is None or (
        isinstance(exit_code, int) and not isinstance(exit_code, bool)
    ):
        detail["exitCode"] = exit_code
    elapsed = document.get("elapsed_seconds")
    if isinstance(elapsed, (int, float)) and not isinstance(elapsed, bool):
        detail["elapsedSeconds"] = float(elapsed)
    return detail


def _mutation_tool_detail(document: Mapping[str, Any]) -> dict[str, Any]:
    detail: dict[str, Any] = {"kind": "mutation"}
    _copy_text(detail, "path", document, "path", 1_000)
    _copy_if_type(detail, "created", document, "created", bool)
    _copy_if_type(detail, "dryRun", document, "dry_run", bool)
    _copy_if_number(detail, "bytesWritten", document, "bytes_written")
    _copy_if_number(detail, "replacements", document, "replacements")
    warning = document.get("warning")
    if isinstance(warning, str):
        detail["warning"] = warning[:1_000]
    return detail


def _mutation_file_changes(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []

    changes: list[dict[str, Any]] = []
    remaining_diff_chars = _MUTATION_DIFF_CHARS
    for item in value[:_MUTATION_FILE_ITEMS]:
        if not isinstance(item, Mapping):
            continue
        path = item.get("path")
        if not isinstance(path, str) or not path:
            continue

        change: dict[str, Any] = {
            "path": path[:1_000],
            "added": _nonnegative_int(item.get("added")),
            "deleted": _nonnegative_int(item.get("deleted")),
        }
        unified_diff = item.get("unified_diff")
        if (
            isinstance(unified_diff, str)
            and unified_diff
            and len(unified_diff) <= remaining_diff_chars
        ):
            change["unifiedDiff"] = unified_diff
            remaining_diff_chars -= len(unified_diff)
        elif isinstance(unified_diff, str) and unified_diff:
            change["truncated"] = True

        if item.get("truncated") is True:
            change["truncated"] = True
        changes.append(change)
    return changes


def _bounded_text(value: Any, limit: int) -> tuple[str, int]:
    if not isinstance(value, str) or not value:
        return "", 0
    if len(value) <= limit:
        return value, 0
    tail_chars = min(limit // 3, 4_000)
    head_chars = limit - tail_chars
    omitted = len(value) - limit
    marker = f"\n… 已省略 {omitted} 个字符 …\n"
    return value[:head_chars] + marker + value[-tail_chars:], omitted


def _nonnegative_int(value: Any) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        return max(0, value)
    return 0


def _copy_if_type(
    target: dict[str, Any],
    target_key: str,
    source: Mapping[str, Any],
    source_key: str,
    expected_type: type[Any],
) -> None:
    value = source.get(source_key)
    if isinstance(value, expected_type):
        target[target_key] = value


def _copy_text(
    target: dict[str, Any],
    target_key: str,
    source: Mapping[str, Any],
    source_key: str,
    limit: int,
) -> None:
    value = source.get(source_key)
    if isinstance(value, str):
        target[target_key] = value[:limit]


def _copy_if_number(
    target: dict[str, Any],
    target_key: str,
    source: Mapping[str, Any],
    source_key: str,
) -> None:
    value = source.get(source_key)
    if isinstance(value, int) and not isinstance(value, bool):
        target[target_key] = value
