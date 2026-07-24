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


class ModelListRequest(BaseModel):
    base_url: str
    api_key: str | None = None


class SessionSummary(BaseModel):
    session_id: str
    message_count: int
    title: str
    last_message: str
    updated_at: float


class SessionDetail(BaseModel):
    session_id: str
    messages: list[dict[str, Any]]
    updated_at: float
