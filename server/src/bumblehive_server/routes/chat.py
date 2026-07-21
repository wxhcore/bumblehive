import asyncio
import logging
from dataclasses import asdict
from time import perf_counter
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.encoders import jsonable_encoder
from pydantic import ValidationError

from ..logging_utils import elapsed_since, format_token_usage, safe_log_value
from ..runtime_service import RuntimeService
from ..schemas import CancelRequest, ChatRequest


router = APIRouter(tags=["chat"])
logger = logging.getLogger("uvicorn.error.bumblehive")


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
                    await websocket.send_json(
                        jsonable_encoder({"type": "event", **asdict(event)})
                    )
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

    error = asdict(result.error) if result.error is not None else None
    await websocket.send_json(
        jsonable_encoder(
            {
                "type": "result",
                "final_content": result.final_content,
                "tools_used": result.tools_used,
                "usage": result.usage,
                "stop_reason": result.stop_reason,
                "error": error,
            }
        )
    )


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
