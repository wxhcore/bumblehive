from fastapi import Request

from .runtime_service import RuntimeService
from .session_reader import SessionReader


def get_runtime_service(request: Request) -> RuntimeService:
    return request.app.state.runtime_service


def get_session_reader(request: Request) -> SessionReader:
    return request.app.state.session_reader

