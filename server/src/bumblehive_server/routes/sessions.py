from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from ..dependencies import get_runtime_service, get_session_reader
from ..runtime_service import RuntimeService
from ..schemas import CreateSessionRequest, SessionDetail, SessionSummary
from ..session_reader import SessionNotFoundError, SessionReader


router = APIRouter(prefix="/api/v1/sessions", tags=["sessions"])


@router.post("")
async def create_session(
    request: CreateSessionRequest | None = None,
    service: RuntimeService = Depends(get_runtime_service),
    reader: SessionReader = Depends(get_session_reader),
) -> dict[str, str]:
    workspace = (
        Path(request.workspace).expanduser().resolve(strict=False)
        if request is not None and request.workspace is not None
        else service.workspace
    )
    session_id = await reader.create(workspace)
    return {"session_id": session_id, "workspace": str(workspace)}


@router.get("")
async def list_sessions(
    reader: SessionReader = Depends(get_session_reader),
) -> dict[str, list[SessionSummary]]:
    return {"sessions": await reader.list()}


@router.get("/{session_id}", response_model=SessionDetail)
async def get_session(
    session_id: str,
    reader: SessionReader = Depends(get_session_reader),
) -> SessionDetail:
    try:
        return await reader.get(session_id)
    except SessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail="session not found") from exc


@router.delete("/{session_id}")
async def delete_session(
    session_id: str,
    service: RuntimeService = Depends(get_runtime_service),
    reader: SessionReader = Depends(get_session_reader),
) -> dict[str, bool | list[str]]:
    descendant_ids = await reader.descendant_ids(session_id)
    deleted_session_ids: list[str] = []
    for target_session_id in [*reversed(descendant_ids), session_id]:
        session_deleted = await service.delete_session(target_session_id)
        metadata_deleted = await reader.delete_metadata(target_session_id)
        if session_deleted or metadata_deleted:
            deleted_session_ids.append(target_session_id)
    return {
        "deleted": bool(deleted_session_ids),
        "deleted_session_ids": deleted_session_ids,
    }
