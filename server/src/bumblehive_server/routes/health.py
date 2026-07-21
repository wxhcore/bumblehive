from fastapi import APIRouter, Depends

from ..dependencies import get_runtime_service
from ..runtime_service import RuntimeService


router = APIRouter(prefix="/api/v1", tags=["health"])


@router.get("/health")
async def health(
    service: RuntimeService = Depends(get_runtime_service),
) -> dict[str, str]:
    return {
        "status": "ok",
        "runtime": "ready" if service.ready else "unavailable",
    }

