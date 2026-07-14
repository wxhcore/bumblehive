from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from ..protocols import AgentError, ToolCall, ToolResult
from .emitter import EventEmitter
from .events import (
    FINAL_RESULT,
    ITERATION_FINISHED,
    ITERATION_STARTED,
    MODEL_REQUEST_STARTED,
    MODEL_RESPONSE_FINISHED,
    MODEL_STREAM_CONTENT_DELTA,
    MODEL_STREAM_REFUSAL_DELTA,
    MODEL_STREAM_REASONING_DELTA,
    MODEL_STREAM_TOOL_CALL_DELTA,
    RUN_ERROR,
    RUN_FINISHED,
    RUN_STARTED,
    TOOL_CALL_FINISHED,
    TOOL_CALL_STARTED,
    TOOL_CALLS_FINISHED,
    TOOL_CALLS_STARTED,
    TURN_CONTEXT_BUILT,
    TURN_ERROR,
    TURN_FINISHED,
    TURN_STARTED,
)
from .payloads import error_payload, tool_call_payload, tool_result_payload


@dataclass(frozen=True, slots=True)
class TurnEvents:
    """Typed helpers for turn lifecycle events."""

    emitter: EventEmitter

    async def started(self, current_user_message: str) -> None:
        await self.emitter.emit(
            TURN_STARTED,
            message={
                "role": "user",
                "content": current_user_message,
            },
        )

    async def context_built(self, *, message_count: int) -> None:
        await self.emitter.emit(
            TURN_CONTEXT_BUILT,
            message_count=message_count,
        )

    async def error(self, exc: Exception) -> None:
        await self.emitter.emit(
            TURN_ERROR,
            error_type=type(exc).__name__,
            error_message=str(exc),
        )

    async def finished(
        self,
        *,
        stop_reason: str,
        error: AgentError | None = None,
    ) -> None:
        await self.emitter.emit(
            TURN_FINISHED,
            stop_reason=stop_reason,
            error=error_payload(error),
        )


@dataclass(frozen=True, slots=True)
class RunEvents:
    """Typed helpers for run and iteration lifecycle events."""

    emitter: EventEmitter

    async def started(self, *, message_count: int) -> None:
        await self.emitter.emit(
            RUN_STARTED,
            message_count=message_count,
        )

    async def error(self, exc: Exception) -> None:
        await self.emitter.emit(
            RUN_ERROR,
            error_type=type(exc).__name__,
            error_message=str(exc),
        )

    async def iteration_started(self, *, message_count: int) -> None:
        await self.emitter.emit(
            ITERATION_STARTED,
            message_count=message_count,
        )

    async def iteration_finished(
        self,
        *,
        finish_reason: str,
        message_count: int,
        tools_used: list[str],
        usage: dict[str, int],
        error: AgentError | None = None,
    ) -> None:
        await self.emitter.emit(
            ITERATION_FINISHED,
            finish_reason=finish_reason,
            message_count=message_count,
            tools_used=list(tools_used),
            usage=dict(usage),
            error=error_payload(error),
        )

    async def final_result(
        self,
        *,
        final_content: str | None,
        stop_reason: str,
        error: AgentError | None = None,
    ) -> None:
        await self.emitter.emit(
            FINAL_RESULT,
            final_content=final_content,
            stop_reason=stop_reason,
            error=error_payload(error),
        )

    async def finished(
        self,
        *,
        stop_reason: str,
        error: AgentError | None = None,
    ) -> None:
        await self.emitter.emit(
            RUN_FINISHED,
            stop_reason=stop_reason,
            error=error_payload(error),
        )


@dataclass(frozen=True, slots=True)
class ModelEvents:
    """Typed helpers for model request, response, and stream events."""

    emitter: EventEmitter

    async def request_started(self, *, request: dict[str, Any]) -> None:
        await self.emitter.emit(
            MODEL_REQUEST_STARTED,
            request=request,
        )

    async def content_delta(self, delta: str) -> None:
        if not delta:
            return
        await self.emitter.emit(
            MODEL_STREAM_CONTENT_DELTA,
            delta=delta,
        )

    async def refusal_delta(self, delta: str) -> None:
        if not delta:
            return
        await self.emitter.emit(
            MODEL_STREAM_REFUSAL_DELTA,
            delta=delta,
        )

    async def reasoning_delta(self, delta: str) -> None:
        if not delta:
            return
        await self.emitter.emit(
            MODEL_STREAM_REASONING_DELTA,
            delta=delta,
        )

    async def tool_call_delta(self, delta: dict[str, Any]) -> None:
        if not delta:
            return
        await self.emitter.emit(
            MODEL_STREAM_TOOL_CALL_DELTA,
            **delta,
        )

    async def response_finished(
        self,
        *,
        finish_reason: str,
        is_error: bool,
        usage: Mapping[str, int],
        refusal: str | None = None,
        error: AgentError | None = None,
        message: Mapping[str, Any] | None = None,
    ) -> None:
        await self.emitter.emit(
            MODEL_RESPONSE_FINISHED,
            finish_reason=finish_reason,
            is_error=is_error,
            usage=dict(usage),
            refusal=refusal,
            error=error_payload(error),
            message=dict(message) if message is not None else None,
        )


@dataclass(frozen=True, slots=True)
class ToolEvents:
    """Typed helpers for tool call lifecycle events."""

    emitter: EventEmitter

    async def calls_started(self, tool_calls: list[ToolCall]) -> None:
        await self.emitter.emit(
            TOOL_CALLS_STARTED,
            tool_call_count=len(tool_calls),
        )

    async def calls_finished(self, tool_results: list[ToolResult]) -> None:
        await self.emitter.emit(
            TOOL_CALLS_FINISHED,
            error_count=sum(1 for result in tool_results if result.error),
        )

    async def call_started(self, call: ToolCall) -> None:
        await self.emitter.emit(
            TOOL_CALL_STARTED,
            **tool_call_payload(call),
        )

    async def call_finished(
        self,
        *,
        call: ToolCall,
        result: ToolResult,
        duration_s: float,
    ) -> None:
        await self.emitter.emit(
            TOOL_CALL_FINISHED,
            **tool_result_payload(result, call=call),
            duration_s=round(duration_s, 4),
        )
