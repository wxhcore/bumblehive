import asyncio
import logging
from time import perf_counter
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.encoders import jsonable_encoder
from pydantic import ValidationError

from ..chat.approval import SendFrame, ToolApprovals
from ..chat.streaming import stream_turn
from ..logging_utils import elapsed_since, safe_log_value
from ..runtime_service import RuntimeService
from ..schemas import ApprovalDecisionRequest, CancelRequest, ChatRequest


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

    send_lock = asyncio.Lock()

    async def send(frame: dict[str, Any]) -> None:
        async with send_lock:
            await websocket.send_json(jsonable_encoder(frame))

    approvals = ToolApprovals(session_id, send)

    try:
        await send({"type": "ready", "session_id": session_id})
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
                if not await _report_turn_completion(send, finished_task):
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
                await _send_error(send, "invalid_message", "message must be JSON")
                continue

            if not isinstance(payload, dict):
                await _send_error(send, "invalid_message", "message must be an object")
                continue

            if payload.get("type") == "approval_decision":
                try:
                    decision = ApprovalDecisionRequest.model_validate(payload)
                except ValidationError as exc:
                    await _send_error(send, "invalid_message", str(exc))
                    continue
                await approvals.decide(decision.approval_id, decision.approved)
                continue

            if payload.get("type") == "cancel":
                try:
                    CancelRequest.model_validate(payload)
                except ValidationError as exc:
                    await _send_error(send, "invalid_message", str(exc))
                    continue

                if active_task is None:
                    continue
                if active_task.done():
                    finished_task = active_task
                    active_task = None
                    if not await _report_turn_completion(send, finished_task):
                        return
                    continue

                cancelling_task = active_task
                active_task = None
                cancelling_task.cancel()
                await asyncio.gather(cancelling_task, return_exceptions=True)
                await send({"type": "cancelled", "session_id": session_id})
                continue

            try:
                request = ChatRequest.model_validate(payload)
            except ValidationError as exc:
                await _send_error(send, "invalid_message", str(exc))
                continue

            if active_task is not None:
                await _send_error(
                    send,
                    "run_in_progress",
                    "an agent run is already active for this session",
                )
                continue

            approvals = ToolApprovals(session_id, send, request.approval_mode)
            active_task = asyncio.create_task(
                stream_turn(send, service, session_id, request, approvals)
            )
    finally:
        if receive_task is not None:
            receive_task.cancel()
            await asyncio.gather(receive_task, return_exceptions=True)
        if active_task is not None:
            active_task.cancel()
            await asyncio.gather(active_task, return_exceptions=True)
        approvals.clear()
        logger.info(
            "[websocket] disconnected | session_id=%s | duration=%s",
            session_label,
            elapsed_since(connected_at),
        )


async def _report_turn_completion(
    send: SendFrame,
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
            await _send_error(send, "runtime_error", str(exc))
        except WebSocketDisconnect:
            return False
    return True


async def _send_error(
    send: SendFrame,
    code: str,
    message: str,
) -> None:
    await send(
        {
            "type": "error",
            "code": code,
            "message": message,
        }
    )
