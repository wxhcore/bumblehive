import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from time import perf_counter

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routes import chat, health, sessions, settings
from .logging_utils import elapsed_since
from .runtime_service import RuntimeService
from .session_reader import SessionReader
from .settings import ServerSettings


logger = logging.getLogger("uvicorn.error.bumblehive")


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
        startup_started_at = perf_counter()
        logger.info("[lifecycle] startup started")
        try:
            await service.startup()
            migrated_sessions = await reader.migrate_missing_workspace(
                service.workspace
            )
        except Exception:
            logger.exception(
                "[lifecycle] startup failed | duration=%s",
                elapsed_since(startup_started_at),
            )
            raise
        app.state.runtime_service = service
        app.state.session_reader = reader
        if migrated_sessions:
            logger.info(
                "[session] migrated legacy documents | count=%d",
                migrated_sessions,
            )
        logger.info(
            "[lifecycle] startup completed | duration=%s",
            elapsed_since(startup_started_at),
        )
        try:
            yield
        finally:
            shutdown_started_at = perf_counter()
            logger.info("[lifecycle] shutdown started")
            try:
                await service.shutdown()
            except Exception:
                logger.exception(
                    "[lifecycle] shutdown failed | duration=%s",
                    elapsed_since(shutdown_started_at),
                )
                raise
            else:
                logger.info(
                    "[lifecycle] shutdown completed | duration=%s",
                    elapsed_since(shutdown_started_at),
                )

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
