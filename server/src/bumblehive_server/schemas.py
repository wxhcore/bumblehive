from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class ChatRequest(BaseModel):
    type: Literal["message"] = "message"
    content: str = Field(min_length=1)
    config: dict[str, Any] | None = None

    @field_validator("content")
    @classmethod
    def content_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("content must not be blank")
        return value


class CancelRequest(BaseModel):
    type: Literal["cancel"]


class CreateSessionRequest(BaseModel):
    workspace: str | None = None

    @field_validator("workspace")
    @classmethod
    def workspace_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        workspace = value.strip()
        if not workspace:
            raise ValueError("workspace must not be blank")
        return workspace


class ModelListRequest(BaseModel):
    base_url: str
    api_key: str | None = None


class SessionSummary(BaseModel):
    session_id: str
    workspace: str
    message_count: int
    title: str
    last_message: str
    created_at: float
    updated_at: float


class SessionDetail(BaseModel):
    session_id: str
    workspace: str
    messages: list[dict[str, Any]]
    created_at: float
    updated_at: float
