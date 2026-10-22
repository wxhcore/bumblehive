from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


class ChatRequest(BaseModel):
    type: Literal["message"] = "message"
    message_id: str = Field(default_factory=lambda: uuid4().hex, min_length=1)
    content: str = Field(min_length=1)
    approval_mode: Literal["request", "full_access"] = "request"
    config: dict[str, Any] | None = None

    @field_validator("content")
    @classmethod
    def content_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("content must not be blank")
        return value


class CancelRequest(BaseModel):
    type: Literal["cancel"]


class QuestionAnswerRequest(BaseModel):
    type: Literal["question_answer"]
    task_id: str = Field(min_length=1)
    answer: str = Field(min_length=1)

    @field_validator("answer")
    @classmethod
    def answer_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("answer must not be blank")
        return value


class QuestionSkipRequest(BaseModel):
    type: Literal["question_skip"]
    task_id: str = Field(min_length=1)


class SteerRequest(BaseModel):
    type: Literal["steer"]
    message_id: str = Field(min_length=1)


class RemovePendingRequest(BaseModel):
    type: Literal["remove_pending"]
    message_id: str = Field(min_length=1)


class ApprovalDecisionRequest(BaseModel):
    type: Literal["approval_decision"]
    approval_id: str = Field(min_length=1)
    approved: bool = Field(strict=True)


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


class McpServerInput(BaseModel):
    name: str
    url: str
    headers: dict[str, str] = Field(default_factory=dict)


class McpServerTestRequest(BaseModel):
    server: McpServerInput
    original_name: str | None = None


class SessionSummary(BaseModel):
    session_id: str
    parent_session_id: str | None = None
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
