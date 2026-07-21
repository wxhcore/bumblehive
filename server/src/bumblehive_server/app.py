from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routes import chat, health, sessions, settings
from .runtime_service import RuntimeService
from .session_reader import SessionReader
from .settings import ServerSettings


def create_app(
    *,
    runtime_service: RuntimeService | None = None,
    session_reader: SessionReader | None = None,
) -> FastAPI:
    server_settings = ServerSettings.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        service = runtime_service or RuntimeService(server_settings.config_path)
        reader = session_reader or SessionReader()
        await service.startup()
        app.state.runtime_service = service
        app.state.session_reader = reader
        try:
            yield
        finally:
            await service.shutdown()

    application = FastAPI(
        title="Bumblehive Server",
        version="0.1.0",
        lifespan=lifespan,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(server_settings.allowed_origins),
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Content-Type"],
    )
    application.include_router(health.router)
    application.include_router(settings.router)
    application.include_router(sessions.router)
    application.include_router(chat.router)
    return application


app = create_app()
