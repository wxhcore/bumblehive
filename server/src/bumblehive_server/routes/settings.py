from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException

from ..dependencies import get_runtime_service
from ..runtime_service import RuntimeBusyError, RuntimeService


router = APIRouter(prefix="/api/v1", tags=["settings"])


@router.get("/settings")
async def get_settings(
    service: RuntimeService = Depends(get_runtime_service),
) -> dict[str, Any]:
    return service.public_config()


@router.put("/settings")
async def update_settings(
    update: dict[str, Any] = Body(...),
    service: RuntimeService = Depends(get_runtime_service),
) -> dict[str, Any]:
    try:
        await service.update_config(update)
    except RuntimeBusyError as exc:
        raise HTTPException(status_code=409, detail="runtime is busy") from exc
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return service.public_config()

