import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from fastapi import APIRouter, Body, Depends, File, HTTPException, UploadFile

from ..dependencies import get_runtime_service
from ..runtime_service import (
    MCPConnectionError,
    ModelListError,
    RuntimeBusyError,
    RuntimeService,
)
from ..schemas import McpServerTestRequest, ModelListRequest
from ..skill_uploads import extract_skill_archives


router = APIRouter(prefix="/api/v1", tags=["settings"])


@router.get("/settings")
async def get_settings(
    service: RuntimeService = Depends(get_runtime_service),
) -> dict[str, Any]:
    return service.public_config()


@router.get("/settings/options")
async def get_settings_options(
    service: RuntimeService = Depends(get_runtime_service),
) -> dict[str, Any]:
    return service.settings_options()


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


@router.post("/mcp/test")
async def test_mcp_server(
    request: McpServerTestRequest,
    service: RuntimeService = Depends(get_runtime_service),
) -> dict[str, Any]:
    try:
        registered = await service.test_mcp_server(
            request.server.model_dump(),
            original_name=request.original_name,
        )
    except MCPConnectionError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "name": request.server.name.strip(),
        "registered_tools": registered,
    }


@router.post("/mcp/refresh")
async def refresh_mcp_servers(
    service: RuntimeService = Depends(get_runtime_service),
) -> dict[str, Any]:
    try:
        await service.reload_mcp_servers()
    except RuntimeBusyError as exc:
        raise HTTPException(status_code=409, detail="runtime is busy") from exc
    except MCPConnectionError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return service.settings_options()


@router.post("/mcp/{server_name}/refresh")
async def refresh_mcp_server(
    server_name: str,
    service: RuntimeService = Depends(get_runtime_service),
) -> dict[str, Any]:
    try:
        await service.reload_mcp_servers(server_name)
    except RuntimeBusyError as exc:
        raise HTTPException(status_code=409, detail="runtime is busy") from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except MCPConnectionError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return service.settings_options()


@router.post("/skills/import")
async def import_skills(
    files: list[UploadFile] = File(...),
    replace: bool = False,
    service: RuntimeService = Depends(get_runtime_service),
) -> dict[str, Any]:
    try:
        with TemporaryDirectory(prefix="bumblehive-skill-upload-") as temp:
            sources = await asyncio.to_thread(
                extract_skill_archives,
                files,
                Path(temp),
            )
            await service.install_skills(sources, replace=replace)
    except RuntimeBusyError as exc:
        raise HTTPException(status_code=409, detail="runtime is busy") from exc
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (OSError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    finally:
        await asyncio.gather(*(file.close() for file in files))
    return service.settings_options()


@router.delete("/skills/{skill_name}")
async def remove_skill(
    skill_name: str,
    service: RuntimeService = Depends(get_runtime_service),
) -> dict[str, Any]:
    try:
        await service.remove_skill(skill_name)
    except RuntimeBusyError as exc:
        raise HTTPException(status_code=409, detail="runtime is busy") from exc
    except (OSError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return service.settings_options()


@router.post("/skills/refresh")
async def refresh_skills(
    service: RuntimeService = Depends(get_runtime_service),
) -> dict[str, Any]:
    try:
        await service.reload_skills()
    except RuntimeBusyError as exc:
        raise HTTPException(status_code=409, detail="runtime is busy") from exc
    return service.settings_options()
