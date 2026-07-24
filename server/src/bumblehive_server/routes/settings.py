from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException

from ..dependencies import get_runtime_service
from ..runtime_service import ModelListError, RuntimeBusyError, RuntimeService
from ..schemas import ModelListRequest


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


@router.post("/models")
async def list_models(
    request: ModelListRequest,
    service: RuntimeService = Depends(get_runtime_service),
) -> dict[str, Any]:
    try:
        models = await service.list_models(
            base_url=request.base_url,
            api_key=request.api_key,
        )
    except ModelListError as exc:
        detail = str(exc) or "provider did not return a model list"
        raise HTTPException(
            status_code=502,
            detail=f"无法获取模型列表：{detail}",
        ) from exc
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"models": models}

