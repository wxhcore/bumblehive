import asyncio
import logging
from collections.abc import Mapping
from time import perf_counter
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect
from fastapi.encoders import jsonable_encoder

from bumblehive.agent import AgentRunResult
from bumblehive.observability import AgentEvent

from ..logging_utils import elapsed_since, format_token_usage, safe_log_value
from ..runtime_service import RuntimeService
from ..schemas import ChatRequest
from ..subagents import SubagentRunObserver, observe_subagents
from .frames import result_frame, ui_event_frame


logger = logging.getLogger("uvicorn.error.bumblehive")


class WebSocketSubagentObserver(SubagentRunObserver):
    def __init__(self, websocket: WebSocket, runtime: Any) -> None:
        self._websocket = websocket
        self._runtime = runtime
        self._send_lock = asyncio.Lock()

    async def on_created(
        self,
        *,
        session_id: str,
        workspace: str,
        title: str,
        content: str,
    ) -> None:
        await self._send(
            {
                "type": "session_created",
                "session_id": session_id,
                "workspace": workspace,
                "title": title,
                "content": content,
            }
        )

    async def on_event(self, event: AgentEvent) -> None:
        frame = ui_event_frame(event)
        if frame is not None:
            await self._send(frame)

    async def on_result(
        self,
        *,
        session_id: str,
        result: AgentRunResult,
        duration_s: float,
    ) -> None:
        await persist_run_duration(self._runtime, session_id, duration_s)
        await self._send(result_frame(session_id, result, duration_s))

    async def on_error(self, *, session_id: str, message: str) -> None:
        await self._send(
            {
                "type": "error",
                "session_id": session_id,
                "code": "runtime_error",
                "message": message,
            }
        )

    async def on_cancelled(self, *, session_id: str) -> None:
        await self._send({"type": "cancelled", "session_id": session_id})

    async def _send(self, frame: dict[str, Any]) -> None:
        async with self._send_lock:
            await self._websocket.send_json(jsonable_encoder(frame))


async def stream_turn(
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
            observer = WebSocketSubagentObserver(websocket, runtime)
            with observe_subagents(observer):
                stream = runtime.stream(
                    request.content,
                    session_id=session_id,
                    config=request.config,
                )
                try:
                    async for event in stream:
                        await observer.on_event(event)
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

    await persist_run_duration(runtime, session_id, duration_s)
    await websocket.send_json(
        jsonable_encoder(result_frame(session_id, result, duration_s))
    )


async def persist_run_duration(
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
