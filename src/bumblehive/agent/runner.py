from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from ..protocols.errors import AgentError
from ..observability import (
    EventEmitter,
    ModelEvents,
    RunEvents,
    ToolEvents,
)
from ..protocols import GenerationConfig
from ..providers.base import (
    ModelProvider,
    ModelRequest,
    ModelResponse,
    ModelStreamCallbacks,
)
from ..tools.manager import ToolManager
from ..tools.scope import PathAllowlist
from .context import ContextGovernanceConfig, ContextGovernor


Message = dict[str, Any]
CheckpointCallback = Callable[[list[Message]], Awaitable[None]]

_MAX_ITERATIONS = 300
_MAX_ITERATIONS_MESSAGE = (
    "I reached the maximum number of tool iterations before producing "
    "a final response."
)
_MODEL_ERROR_PLACEHOLDER = "[Assistant reply unavailable due to model error.]"


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
        path_allowlist: PathAllowlist = PathAllowlist(),
        tool_names: list[str] | None = None,
        context_window_tokens: int | None = None,
        max_tool_result_chars: int | None = None,
        max_iterations: int | None = None,
        emitter: EventEmitter | None = None,
        stream: bool = False,
        checkpoint_callback: CheckpointCallback | None = None,
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

        run_events = RunEvents(emitter)
        await run_events.started(message_count=len(run_messages))

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
                path_allowlist=path_allowlist,
                tool_names=tool_names,
                context_window_tokens=context_window_tokens,
                max_tool_result_chars=max_tool_result_chars,
                max_iterations=effective_max_iterations,
                emitter=emitter,
                stream=stream,
                checkpoint_callback=checkpoint_callback,
            )
        except Exception as exc:
            await run_events.error(exc)
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
        path_allowlist: PathAllowlist,
        tool_names: list[str] | None,
        context_window_tokens: int | None,
        max_tool_result_chars: int | None,
        max_iterations: int,
        emitter: EventEmitter,
        stream: bool,
        checkpoint_callback: CheckpointCallback | None,
    ) -> AgentRunResult:
        for iteration in range(max_iterations):
            iteration_emitter = emitter.with_iteration(iteration)
            run_events = RunEvents(iteration_emitter)
            model_events = ModelEvents(iteration_emitter)
            tool_events = ToolEvents(iteration_emitter)
            await run_events.iteration_started(message_count=len(run_messages))
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
                    max_completion_tokens=(
                        request_generation.effective_max_completion_tokens
                    ),
                    max_tool_result_chars=max_tool_result_chars,
                ),
            )
            request = ModelRequest(
                messages=request_messages,
                tools=tool_definitions,
                model=model,
                generation=request_generation,
            )
            await model_events.request_started(request=asdict(request))
            response = await self._request_model(
                provider,
                request,
                emitter=iteration_emitter,
                stream=stream,
            )
            self._accumulate_usage(usage, response.usage)

            if response.is_error:
                assistant_message = self._append_model_error_placeholder(run_messages)
                await self._checkpoint(checkpoint_callback, run_messages)
                await model_events.response_finished(
                    finish_reason=response.finish_reason,
                    is_error=response.is_error,
                    usage=response.usage,
                    refusal=response.refusal,
                    error=response.error,
                    message=assistant_message,
                )
                result = AgentRunResult(
                    final_content=response.content or response.refusal,
                    messages=run_messages,
                    tools_used=tools_used,
                    usage=usage,
                    stop_reason="model_error",
                    error=response.error,
                )
                await run_events.final_result(
                    final_content=result.final_content,
                    stop_reason=result.stop_reason,
                    error=result.error,
                )
                await run_events.iteration_finished(
                    finish_reason=response.finish_reason,
                    message_count=len(result.messages),
                    tools_used=result.tools_used,
                    usage=result.usage,
                    error=result.error,
                )
                await RunEvents(emitter).finished(
                    stop_reason=result.stop_reason,
                    error=result.error,
                )
                return result

            if response.should_execute_tools:
                assistant_message = self._assistant_tool_call_message(response)
                run_messages.append(assistant_message)
                await self._checkpoint(checkpoint_callback, run_messages)
                await model_events.response_finished(
                    finish_reason=response.finish_reason,
                    is_error=response.is_error,
                    usage=response.usage,
                    refusal=response.refusal,
                    error=response.error,
                    message=assistant_message,
                )
                await tool_events.calls_started(response.tool_calls)
                tool_results = await tools.execute_many(
                    response.tool_calls,
                    tool_names=tool_names,
                    workspace=workspace,
                    path_allowlist=path_allowlist,
                    emitter=iteration_emitter,
                )
                for tool_call, tool_result in zip(response.tool_calls, tool_results):
                    if tool_result.error is None:
                        tools_used.append(tool_call.name)
                    tool_message = tool_result.to_openai_tool_message(call=tool_call)
                    run_messages.append(tool_message)
                await self._checkpoint(checkpoint_callback, run_messages)
                await tool_events.calls_finished(tool_results)
                await run_events.iteration_finished(
                    finish_reason=response.finish_reason,
                    message_count=len(run_messages),
                    tools_used=tools_used,
                    usage=usage,
                )
                continue

            final_content = response.content or response.refusal or ""
            assistant_message = self._assistant_message(
                final_content,
                reasoning_content=response.reasoning_content,
            )
            run_messages.append(assistant_message)
            await self._checkpoint(checkpoint_callback, run_messages)
            await model_events.response_finished(
                finish_reason=response.finish_reason,
                is_error=response.is_error,
                usage=response.usage,
                refusal=response.refusal,
                error=response.error,
                message=assistant_message,
            )
            result = AgentRunResult(
                final_content=final_content,
                messages=run_messages,
                tools_used=tools_used,
                usage=usage,
                stop_reason="completed",
            )
            await run_events.final_result(
                final_content=result.final_content,
                stop_reason=result.stop_reason,
                error=result.error,
            )
            await run_events.iteration_finished(
                finish_reason=response.finish_reason,
                message_count=len(result.messages),
                tools_used=result.tools_used,
                usage=result.usage,
                error=result.error,
            )
            await RunEvents(emitter).finished(
                stop_reason=result.stop_reason,
                error=result.error,
            )
            return result

        final_content = _MAX_ITERATIONS_MESSAGE
        assistant_message = self._assistant_message(final_content)
        run_messages.append(assistant_message)
        await self._checkpoint(checkpoint_callback, run_messages)
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
        run_events = RunEvents(emitter)
        await run_events.final_result(
            final_content=result.final_content,
            stop_reason=result.stop_reason,
            error=result.error,
        )
        await run_events.finished(
            stop_reason=result.stop_reason,
            error=result.error,
        )
        return result

    @staticmethod
    async def _checkpoint(
        callback: CheckpointCallback | None,
        messages: list[Message],
    ) -> None:
        if callback is None:
            return
        await callback([dict(message) for message in messages])

    @classmethod
    async def _request_model(
        cls,
        provider: ModelProvider,
        request: ModelRequest,
        *,
        emitter: EventEmitter,
        stream: bool,
    ) -> ModelResponse:
        if not stream:
            return await provider.generate_with_retry(request)

        model_events = ModelEvents(emitter)

        async def _content_delta(delta: str) -> None:
            await model_events.content_delta(delta)

        async def _refusal_delta(delta: str) -> None:
            await model_events.refusal_delta(delta)

        async def _reasoning_delta(delta: str) -> None:
            await model_events.reasoning_delta(delta)

        async def _tool_call_delta(delta: dict[str, Any]) -> None:
            await model_events.tool_call_delta(delta)

        return await provider.generate_stream_with_retry(
            request,
            callbacks=ModelStreamCallbacks(
                on_content_delta=_content_delta,
                on_refusal_delta=_refusal_delta,
                on_reasoning_delta=_reasoning_delta,
                on_tool_call_delta=_tool_call_delta,
            ),
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

    @classmethod
    def _append_model_error_placeholder(
        cls,
        messages: list[Message],
    ) -> Message | None:
        if (
            messages
            and messages[-1].get("role") == "assistant"
            and not messages[-1].get("tool_calls")
        ):
            return None
        message = cls._assistant_message(_MODEL_ERROR_PLACEHOLDER)
        messages.append(message)
        return message

    @staticmethod
    def _accumulate_usage(
        usage: dict[str, int],
        update: dict[str, int],
    ) -> None:
        for key, value in update.items():
            if isinstance(value, int):
                usage[key] = usage.get(key, 0) + value
