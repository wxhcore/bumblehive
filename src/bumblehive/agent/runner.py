from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..protocols.errors import AgentError
from ..protocols.tool_calls import ToolCall
from ..observability import (
    FINAL_RESULT,
    ITERATION_FINISHED,
    ITERATION_STARTED,
    MODEL_REQUEST_STARTED,
    MODEL_RESPONSE_FINISHED,
    RUN_ERROR,
    RUN_FINISHED,
    RUN_STARTED,
    TOOL_CALLS_FINISHED,
    TOOL_CALLS_STARTED,
    EventEmitter,
    error_payload,
)
from ..protocols import GenerationConfig
from ..providers.base import ModelProvider, ModelRequest
from ..tools.manager import ToolManager
from .context import ContextGovernanceConfig, ContextGovernor


Message = dict[str, Any]

_MAX_ITERATIONS = 300
_MAX_ITERATIONS_MESSAGE = (
    "I reached the maximum number of tool iterations before producing "
    "a final response."
)


@dataclass(frozen=True)
class AgentRunResult:
    """Outcome of one tool-capable model run."""

    final_content: str | None
    messages: list[Message]
    tools_used: list[str] = field(default_factory=list)
    usage: dict[str, int] = field(default_factory=dict)
    stop_reason: str = "completed"
    error: AgentError | None = None


class ToolCallingRunner:
    """Run the provider/tool-calling loop without product-layer concerns."""

    async def run(
        self,
        *,
        provider: ModelProvider,
        tools: ToolManager,
        messages: list[Message],
        model: str,
        generation: GenerationConfig | None = None,
        workspace: Path | str | None = None,
        tool_names: list[str] | None = None,
        context_window_tokens: int | None = None,
        max_tool_result_chars: int | None = None,
        max_iterations: int | None = None,
        emitter: EventEmitter | None = None,
    ) -> AgentRunResult:
        """Run model/tool iterations until a final model response is produced."""

        emitter = emitter or EventEmitter.noop()
        tool_definitions = tools.get_openai_tool_definitions(tool_names)
        run_messages = [dict(message) for message in messages]
        tools_used: list[str] = []
        usage: dict[str, int] = {}

        effective_max_iterations = (
            _MAX_ITERATIONS if max_iterations is None else max_iterations
        )

        await emitter.emit(
            RUN_STARTED,
            model=model,
            tool_count=len(tool_definitions),
            message_count=len(run_messages),
            max_iterations=effective_max_iterations,
        )

        try:
            return await self._run_iterations(
                provider=provider,
                tools=tools,
                tool_definitions=tool_definitions,
                run_messages=run_messages,
                tools_used=tools_used,
                usage=usage,
                model=model,
                generation=generation,
                workspace=workspace,
                tool_names=tool_names,
                context_window_tokens=context_window_tokens,
                max_tool_result_chars=max_tool_result_chars,
                max_iterations=effective_max_iterations,
                emitter=emitter,
            )
        except Exception as exc:
            await emitter.emit(
                RUN_ERROR,
                error_type=type(exc).__name__,
                error_message=str(exc),
            )
            raise

    async def _run_iterations(
        self,
        *,
        provider: ModelProvider,
        tools: ToolManager,
        tool_definitions: list[dict[str, Any]],
        run_messages: list[Message],
        tools_used: list[str],
        usage: dict[str, int],
        model: str,
        generation: GenerationConfig | None,
        workspace: Path | str | None,
        tool_names: list[str] | None,
        context_window_tokens: int | None,
        max_tool_result_chars: int | None,
        max_iterations: int,
        emitter: EventEmitter,
    ) -> AgentRunResult:
        for iteration in range(max_iterations):
            iteration_emitter = emitter.with_iteration(iteration)
            await iteration_emitter.emit(
                ITERATION_STARTED,
                message_count=len(run_messages),
            )
            request_generation = (
                generation if generation is not None else GenerationConfig()
            )
            request_messages = ContextGovernor.prepare_for_model(
                run_messages,
                config=ContextGovernanceConfig(
                    provider=provider,
                    model=model,
                    tools=tool_definitions,
                    context_window_tokens=context_window_tokens,
                    max_output_tokens=request_generation.max_tokens,
                    max_tool_result_chars=max_tool_result_chars,
                ),
            )
            request = ModelRequest(
                messages=request_messages,
                tools=tool_definitions,
                model=model,
                generation=request_generation,
            )
            await iteration_emitter.emit(
                MODEL_REQUEST_STARTED,
                model=model,
                message_count=len(request_messages),
                tool_count=len(tool_definitions),
            )
            response = await provider.generate_with_retry(request)
            self._accumulate_usage(usage, response.usage)

            if response.is_error:
                await self._emit_model_response_finished(
                    iteration_emitter,
                    response=response,
                )
                result = AgentRunResult(
                    final_content=response.content,
                    messages=run_messages,
                    tools_used=tools_used,
                    usage=usage,
                    stop_reason="model_error",
                    error=response.error,
                )
                await iteration_emitter.emit(
                    FINAL_RESULT,
                    final_content=result.final_content,
                    stop_reason=result.stop_reason,
                    error=error_payload(result.error),
                )
                await self._emit_iteration_finished(
                    iteration_emitter,
                    result=result,
                    finish_reason=response.finish_reason,
                )
                await self._emit_run_finished(emitter, result=result)
                return result

            if response.should_execute_tools:
                assistant_message = self._assistant_tool_call_message(response)
                run_messages.append(assistant_message)
                await self._emit_model_response_finished(
                    iteration_emitter,
                    response=response,
                    message=assistant_message,
                )
                await self._emit_tool_calls_started(
                    iteration_emitter,
                    tool_calls=response.tool_calls,
                )
                tool_results = await tools.execute_many(
                    response.tool_calls,
                    allowed_tool_names=tool_names,
                    workspace=workspace,
                    emitter=iteration_emitter,
                )
                for tool_call, tool_result in zip(response.tool_calls, tool_results):
                    if tool_result.error is None:
                        tools_used.append(tool_call.name)
                    tool_message = tool_result.to_openai_tool_message(call=tool_call)
                    run_messages.append(tool_message)
                await iteration_emitter.emit(
                    TOOL_CALLS_FINISHED,
                    tool_count=len(response.tool_calls),
                    error_count=sum(1 for result in tool_results if result.error),
                )
                await iteration_emitter.emit(
                    ITERATION_FINISHED,
                    finish_reason=response.finish_reason,
                    message_count=len(run_messages),
                    tools_used=list(tools_used),
                    usage=dict(usage),
                )
                continue

            final_content = response.content or response.refusal or ""
            assistant_message = self._assistant_message(
                final_content,
                reasoning_content=response.reasoning_content,
            )
            run_messages.append(assistant_message)
            await self._emit_model_response_finished(
                iteration_emitter,
                response=response,
                message=assistant_message,
            )
            result = AgentRunResult(
                final_content=final_content,
                messages=run_messages,
                tools_used=tools_used,
                usage=usage,
                stop_reason="completed",
            )
            await iteration_emitter.emit(
                FINAL_RESULT,
                final_content=final_content,
                stop_reason=result.stop_reason,
            )
            await self._emit_iteration_finished(
                iteration_emitter,
                result=result,
                finish_reason=response.finish_reason,
            )
            await self._emit_run_finished(emitter, result=result)
            return result

        final_content = _MAX_ITERATIONS_MESSAGE
        assistant_message = self._assistant_message(final_content)
        run_messages.append(assistant_message)
        result = AgentRunResult(
            final_content=final_content,
            messages=run_messages,
            tools_used=tools_used,
            usage=usage,
            stop_reason="max_iterations",
            error=AgentError(
                code="max_iterations",
                message=final_content,
                recoverable=True,
            ),
        )
        await emitter.emit(
            FINAL_RESULT,
            final_content=final_content,
            stop_reason=result.stop_reason,
            error=error_payload(result.error),
        )
        await self._emit_run_finished(emitter, result=result)
        return result

    @classmethod
    async def _emit_tool_calls_started(
        cls,
        emitter: EventEmitter,
        *,
        tool_calls: list[ToolCall],
    ) -> None:
        await emitter.emit(
            TOOL_CALLS_STARTED,
            tool_count=len(tool_calls),
        )

    @classmethod
    async def _emit_model_response_finished(
        cls,
        emitter: EventEmitter,
        *,
        response: Any,
        message: Message | None = None,
    ) -> None:
        await emitter.emit(
            MODEL_RESPONSE_FINISHED,
            finish_reason=response.finish_reason,
            is_error=response.is_error,
            tool_call_count=len(response.tool_calls),
            usage=dict(response.usage),
            refusal=response.refusal,
            error=error_payload(response.error),
            message=dict(message) if message is not None else None,
        )

    @classmethod
    async def _emit_iteration_finished(
        cls,
        emitter: EventEmitter,
        *,
        result: AgentRunResult,
        finish_reason: str,
    ) -> None:
        await emitter.emit(
            ITERATION_FINISHED,
            finish_reason=finish_reason,
            message_count=len(result.messages),
            tools_used=list(result.tools_used),
            usage=dict(result.usage),
            error=error_payload(result.error),
        )

    @classmethod
    async def _emit_run_finished(
        cls,
        emitter: EventEmitter,
        *,
        result: AgentRunResult,
    ) -> None:
        await emitter.emit(
            RUN_FINISHED,
            stop_reason=result.stop_reason,
            message_count=len(result.messages),
            tools_used=list(result.tools_used),
            usage=dict(result.usage),
            error=error_payload(result.error),
        )

    @staticmethod
    def _assistant_message(
        content: str | None,
        *,
        reasoning_content: str | None = None,
    ) -> Message:
        message: Message = {
            "role": "assistant",
            "content": content or "",
        }
        if reasoning_content is not None:
            message["reasoning_content"] = reasoning_content
        return message

    @classmethod
    def _assistant_tool_call_message(cls, response: Any) -> Message:
        message = cls._assistant_message(
            response.content,
            reasoning_content=response.reasoning_content,
        )
        message["tool_calls"] = [
            tool_call.to_openai_tool_call()
            for tool_call in response.tool_calls
        ]
        return message

    @staticmethod
    def _accumulate_usage(
        usage: dict[str, int],
        update: dict[str, int],
    ) -> None:
        for key, value in update.items():
            if isinstance(value, int):
                usage[key] = usage.get(key, 0) + value
