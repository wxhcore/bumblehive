from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException

from ..dependencies import get_runtime_service, get_session_reader
from ..runtime_service import RuntimeService
from ..schemas import SessionDetail, SessionSummary
from ..session_reader import SessionNotFoundError, SessionReader


router = APIRouter(prefix="/api/v1/sessions", tags=["sessions"])


@router.post("")
async def create_session() -> dict[str, str]:
    return {"session_id": str(uuid4())}


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
) -> dict[str, bool]:
    return {"deleted": await service.delete_session(session_id)}

