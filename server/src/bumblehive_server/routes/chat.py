import asyncio
import json
import logging
from collections.abc import Mapping
from dataclasses import asdict
from time import perf_counter
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.encoders import jsonable_encoder
from pydantic import ValidationError

from bumblehive.observability.events import (
    MODEL_RESPONSE_FINISHED,
    MODEL_STREAM_CONTENT_DELTA,
    MODEL_STREAM_REASONING_DELTA,
    MODEL_STREAM_REFUSAL_DELTA,
    MODEL_STREAM_TOOL_CALL_DELTA,
    TOOL_CALL_FINISHED,
    TOOL_CALL_STARTED,
    AgentEvent,
)

from ..logging_utils import elapsed_since, format_token_usage, safe_log_value
from ..runtime_service import RuntimeService
from ..schemas import CancelRequest, ChatRequest


router = APIRouter(tags=["chat"])
logger = logging.getLogger("uvicorn.error.bumblehive")

_DIRECT_UI_EVENT_KINDS = frozenset(
    {
        MODEL_STREAM_CONTENT_DELTA,
        MODEL_STREAM_REASONING_DELTA,
        MODEL_STREAM_REFUSAL_DELTA,
        MODEL_STREAM_TOOL_CALL_DELTA,
        TOOL_CALL_STARTED,
    }
)
_SHELL_OUTPUT_PREVIEW_CHARS = 16_000
_SHELL_STDERR_PREVIEW_CHARS = 6_000
_MUTATION_DIFF_CHARS = 256_000
_MUTATION_FILE_ITEMS = 20
_MUTATION_TOOLS = frozenset({"write_file", "edit_file", "apply_patch"})
_SHELL_TOOLS = frozenset({"exec", "write_stdin"})
_READ_TOOLS = frozenset({"read_file", "list_dir", "find_files", "grep"})
_READ_DETAIL_ITEMS = 20
_SHELL_SESSION_ITEMS = 20


@router.websocket("/ws/v1/chat/{session_id}")
async def chat(websocket: WebSocket, session_id: str) -> None:
    if not session_id.strip():
        await websocket.close(code=1008)
        return

    connected_at = perf_counter()
    session_label = safe_log_value(session_id)
    await websocket.accept()
    logger.info("[websocket] connected | session_id=%s", session_label)
    service: RuntimeService = websocket.app.state.runtime_service
    active_task: asyncio.Task[None] | None = None
    receive_task: asyncio.Task[Any] | None = None

    try:
        await websocket.send_json({"type": "ready", "session_id": session_id})
        receive_task = asyncio.create_task(websocket.receive_json())
        while True:
            assert receive_task is not None
            waiters: set[asyncio.Task[Any]] = {receive_task}
            if active_task is not None:
                waiters.add(active_task)
            done, _ = await asyncio.wait(
                waiters,
                return_when=asyncio.FIRST_COMPLETED,
            )

            if active_task is not None and active_task in done:
                finished_task = active_task
                active_task = None
                if not await _report_turn_completion(websocket, finished_task):
                    return

            if receive_task not in done:
                continue

            try:
                payload = receive_task.result()
                receive_task = asyncio.create_task(websocket.receive_json())
            except WebSocketDisconnect:
                return
            except ValueError:
                receive_task = asyncio.create_task(websocket.receive_json())
                await _send_error(websocket, "invalid_message", "message must be JSON")
                continue

            if not isinstance(payload, dict):
                await _send_error(websocket, "invalid_message", "message must be an object")
                continue

            if payload.get("type") == "cancel":
                try:
                    CancelRequest.model_validate(payload)
                except ValidationError as exc:
                    await _send_error(websocket, "invalid_message", str(exc))
                    continue

                if active_task is None:
                    continue
                if active_task.done():
                    finished_task = active_task
                    active_task = None
                    if not await _report_turn_completion(websocket, finished_task):
                        return
                    continue

                cancelling_task = active_task
                active_task = None
                cancelling_task.cancel()
                await asyncio.gather(cancelling_task, return_exceptions=True)
                await websocket.send_json(
                    {"type": "cancelled", "session_id": session_id}
                )
                continue

            try:
                request = ChatRequest.model_validate(payload)
            except ValidationError as exc:
                await _send_error(websocket, "invalid_message", str(exc))
                continue

            if active_task is not None:
                await _send_error(
                    websocket,
                    "run_in_progress",
                    "an agent run is already active for this session",
                )
                continue

            active_task = asyncio.create_task(
                _stream_turn(websocket, service, session_id, request)
            )
    finally:
        if receive_task is not None:
            receive_task.cancel()
            await asyncio.gather(receive_task, return_exceptions=True)
        if active_task is not None:
            active_task.cancel()
            await asyncio.gather(active_task, return_exceptions=True)
        logger.info(
            "[websocket] disconnected | session_id=%s | duration=%s",
            session_label,
            elapsed_since(connected_at),
        )


async def _report_turn_completion(
    websocket: WebSocket,
    task: asyncio.Task[None],
) -> bool:
    try:
        await task
    except asyncio.CancelledError:
        return True
    except WebSocketDisconnect:
        return False
    except Exception as exc:
        try:
            await _send_error(websocket, "runtime_error", str(exc))
        except WebSocketDisconnect:
            return False
    return True


async def _stream_turn(
    websocket: WebSocket,
    service: RuntimeService,
    session_id: str,
    request: ChatRequest,
) -> None:
    started_at = perf_counter()
    session_label = safe_log_value(session_id)
    logger.info("[agent] started | session_id=%s", session_label)
    try:
        async with service.lease() as runtime:
            stream = runtime.stream(
                request.content,
                session_id=session_id,
                config=request.config,
            )
            try:
                async for event in stream:
                    frame = _ui_event_frame(event)
                    if frame is not None:
                        await websocket.send_json(jsonable_encoder(frame))
                result = await stream.result()
            finally:
                await stream.aclose()
    except asyncio.CancelledError:
        logger.info(
            "[agent] cancelled | session_id=%s | duration=%s",
            session_label,
            elapsed_since(started_at),
        )
        raise
    except WebSocketDisconnect:
        logger.info(
            "[agent] cancelled | session_id=%s | reason=websocket_disconnect | "
            "duration=%s",
            session_label,
            elapsed_since(started_at),
        )
        raise
    except Exception:
        logger.exception(
            "[agent] failed | session_id=%s | duration=%s",
            session_label,
            elapsed_since(started_at),
        )
        raise

    duration_s = max(0.0, perf_counter() - started_at)
    if result.error is None:
        logger.info(
            "[agent] completed | session_id=%s | duration=%s | "
            "stop_reason=%s | tokens=%s",
            session_label,
            elapsed_since(started_at),
            safe_log_value(result.stop_reason),
            format_token_usage(result.usage),
        )
    else:
        logger.warning(
            "[agent] failed | session_id=%s | duration=%s | stop_reason=%s | "
            "error_code=%s | tokens=%s",
            session_label,
            elapsed_since(started_at),
            safe_log_value(result.stop_reason),
            safe_log_value(result.error.code),
            format_token_usage(result.usage),
        )

    await _persist_run_duration(runtime, session_id, duration_s)
    error = asdict(result.error) if result.error is not None else None
    await websocket.send_json(
        jsonable_encoder(
            {
                "type": "result",
                "final_content": result.final_content,
                "tools_used": result.tools_used,
                "usage": result.usage,
                "stop_reason": result.stop_reason,
                "duration_s": round(duration_s, 3),
                "error": error,
            }
        )
    )


def _ui_event_frame(event: AgentEvent) -> dict[str, Any] | None:
    payload: Mapping[str, Any]
    if event.kind in _DIRECT_UI_EVENT_KINDS:
        payload = event.payload
    elif event.kind == TOOL_CALL_FINISHED:
        tool_result = event.payload.get("tool_result")
        if not isinstance(tool_result, Mapping):
            return None
        name = tool_result.get("name")
        result_document = _tool_result_document(tool_result.get("content"))
        payload = {
            "ok": event.payload.get("ok"),
            "tool_result": {
                key: tool_result[key]
                for key in ("tool_call_id", "name")
                if key in tool_result
            },
        }
        if isinstance(name, str):
            detail = _ui_tool_detail(name, result_document)
            if detail is not None:
                if name in _MUTATION_TOOLS:
                    file_changes = _mutation_file_changes(
                        event.payload.get("file_changes")
                    )
                    if file_changes:
                        detail["fileChanges"] = file_changes
                payload["tool_result"]["detail"] = detail
        result_error = _tool_result_error(result_document)
        if result_error is not None:
            payload["ok"] = False
            payload["error"] = {
                "code": "tool_result_error",
                "message": result_error,
                "recoverable": True,
            }
        for key in ("duration_s", "error"):
            if key in event.payload:
                payload[key] = event.payload[key]
    elif event.kind == MODEL_RESPONSE_FINISHED:
        message = event.payload.get("message")
        if not isinstance(message, Mapping):
            return None
        reasoning = message.get("reasoning_content")
        if not isinstance(reasoning, str) or not reasoning:
            return None
        payload = {"message": {"reasoning_content": reasoning}}
    else:
        return None

    return {
        "type": "event",
        "kind": event.kind,
        "run_id": event.run_id,
        "payload": dict(payload),
        "iteration": event.iteration,
        "session_id": event.session_id,
        "timestamp": event.timestamp,
    }


def _tool_result_document(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    if not isinstance(value, str) or not value:
        return {}
    try:
        parsed = json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return {}
    return parsed if isinstance(parsed, Mapping) else {}


def _tool_result_error(document: Mapping[str, Any]) -> str | None:
    error = document.get("error")
    if isinstance(error, str) and error:
        return error
    if isinstance(error, Mapping):
        message = error.get("message")
        if isinstance(message, str) and message:
            return message
    return None


def _ui_tool_detail(
    name: str,
    document: Mapping[str, Any],
) -> dict[str, Any] | None:
    if name == "list_exec_sessions":
        return _exec_sessions_tool_detail(document)
    if name in _SHELL_TOOLS:
        return _shell_tool_detail(document)
    if name in _MUTATION_TOOLS:
        return _mutation_tool_detail(document)
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


async def _persist_run_duration(
    runtime: Any,
    session_id: str,
    duration_s: float,
) -> None:
    """Store UI-only timing without exposing it to model providers."""
    if not hasattr(runtime, "sessions"):
        return
    try:
        session = await runtime.sessions.get(session_id)
        async with session.lock:
            messages = runtime.sessions.get_history(session)
            for index in range(len(messages) - 1, -1, -1):
                message = messages[index]
                if message.get("role") != "assistant":
                    continue
                updated = dict(message)
                metadata = updated.get("_bumblehive_ui")
                ui_metadata = dict(metadata) if isinstance(metadata, Mapping) else {}
                ui_metadata["duration_s"] = round(duration_s, 3)
                updated["_bumblehive_ui"] = ui_metadata
                messages[index] = updated
                await runtime.sessions.replace_and_save(session, messages)
                return
    except Exception:
        logger.warning(
            "[session] failed to persist run duration | session_id=%s",
            safe_log_value(session_id),
            exc_info=True,
        )


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
            item[:1_000]
            for item in files[:_READ_DETAIL_ITEMS]
            if isinstance(item, str)
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
            upstream_truncated
            + output_omitted
            + stdout_omitted
            + stderr_omitted
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


async def _send_error(
    websocket: WebSocket,
    code: str,
    message: str,
) -> None:
    await websocket.send_json(
        {
            "type": "error",
            "code": code,
            "message": message,
        }
    )
