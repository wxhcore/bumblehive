import asyncio
import logging
from time import perf_counter
from typing import Any

import anyio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.encoders import jsonable_encoder
from pydantic import ValidationError

from ..chat.session import InputError
from ..logging_utils import elapsed_since, safe_log_value
from ..runtime_service import RuntimeService
from ..schemas import (
    ApprovalDecisionRequest,
    CancelRequest,
    ChatRequest,
    QuestionAnswerRequest,
    QuestionSkipRequest,
    RemovePendingRequest,
    SteerRequest,
)


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
    controller = service.get_session_controller(session_id)
    queue, snapshot = controller.subscribe()
    snapshot["running_subagents"] = service.subagents.snapshot(session_id)

    async def send_frames() -> None:
        while True:
            frame = await queue.get()
            await websocket.send_json(jsonable_encoder(frame))

    sender: asyncio.Task | None = None
    receiver: asyncio.Task | None = None
    try:
        await websocket.send_json(jsonable_encoder(snapshot))
        sender = asyncio.create_task(send_frames())
        while True:
            receiver = asyncio.create_task(websocket.receive_json())
            done, _ = await asyncio.wait(
                {receiver, sender}, return_when=asyncio.FIRST_COMPLETED
            )
            if sender in done:
                await sender
                return
            try:
                payload = receiver.result()
            except ValueError:
                queue.put_nowait(_error("invalid_message", "message must be JSON"))
                continue
            try:
                if not isinstance(payload, dict):
                    raise InputError("invalid_message", "message must be an object")
                kind = payload.get("type", "message")
                if service.subagents.is_running(session_id):
                    raise InputError(
                        "subagent_running",
                        "This background sub-agent is view-only while running",
                    )
                if kind == "message":
                    await controller.submit(ChatRequest.model_validate(payload))
                elif kind == "steer":
                    request = SteerRequest.model_validate(payload)
                    await controller.steer(request.message_id)
                elif kind == "remove_pending":
                    request = RemovePendingRequest.model_validate(payload)
                    await controller.remove_pending(request.message_id)
                elif kind == "cancel":
                    CancelRequest.model_validate(payload)
                    await controller.cancel()
                elif kind == "approval_decision":
                    request = ApprovalDecisionRequest.model_validate(payload)
                    await controller.decide_approval(
                        request.approval_id, request.approved
                    )
                elif kind == "question_answer":
                    request = QuestionAnswerRequest.model_validate(payload)
                    await controller.answer_question(request.task_id, request.answer)
                elif kind == "question_skip":
                    request = QuestionSkipRequest.model_validate(payload)
                    await controller.answer_question(request.task_id)
                else:
                    raise InputError("invalid_message", "unknown message type")
            except (ValidationError, InputError) as exc:
                queue.put_nowait(
                    _error(
                        exc.code if isinstance(exc, InputError) else "invalid_message",
                        str(exc),
                        payload.get("message_id")
                        if isinstance(payload, dict)
                        else None,
                        task_id=payload.get("task_id")
                        if isinstance(payload, dict) and payload.get("type") in {"question_answer", "question_skip"}
                        else None,
                    )
                )
    except (WebSocketDisconnect, asyncio.CancelledError):
        pass
    finally:
        controller.unsubscribe(queue)
        tasks = [task for task in (sender, receiver) if task is not None]
        for task in tasks:
            task.cancel()
        with anyio.CancelScope(shield=True):
            await asyncio.gather(*tasks, return_exceptions=True)
        logger.info(
            "[websocket] disconnected | session_id=%s | duration=%s",
            session_label,
            elapsed_since(connected_at),
        )


def _error(
    code: str, message: str, message_id: str | None = None,
    *, task_id: str | None = None,
) -> dict[str, Any]:
    return {
        "type": "error",
        "scope": "input",
        "code": code,
        "message": message,
        "message_id": message_id,
        **({"task_id": task_id} if task_id is not None else {}),
    }
