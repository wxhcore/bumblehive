import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..contracts.errors import AgentError
from ..providers.base import GenerationConfig, ModelProvider, ModelRequest
from ..tools.calls import ToolCall, ToolResult
from ..tools.manager import ToolManager
from .context_governor import ContextGovernanceConfig, ContextGovernor


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
    ) -> AgentRunResult:
        """Run model/tool iterations until a final model response is produced."""

        tool_definitions = tools.get_openai_tool_definitions(tool_names)
        run_messages = [dict(message) for message in messages]
        tools_used: list[str] = []
        usage: dict[str, int] = {}

        effective_max_iterations = (
            _MAX_ITERATIONS if max_iterations is None else max_iterations
        )

        for _iteration in range(effective_max_iterations):
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
            response = await provider.generate_with_retry(request)
            self._accumulate_usage(usage, response.usage)

            if response.is_error:
                return AgentRunResult(
                    final_content=response.content,
                    messages=run_messages,
                    tools_used=tools_used,
                    usage=usage,
                    stop_reason="model_error",
                    error=response.error,
                )

            if response.should_execute_tools:
                run_messages.append(self._assistant_tool_call_message(response))
                tool_results = await tools.execute_many(
                    response.tool_calls,
                    allowed_tool_names=tool_names,
                    workspace=workspace,
                )
                for tool_call, tool_result in zip(response.tool_calls, tool_results):
                    if tool_result.error is None:
                        tools_used.append(tool_call.name)
                    run_messages.append(self._tool_result_message(tool_call, tool_result))
                continue

            final_content = response.content or response.refusal or ""
            run_messages.append(
                self._assistant_message(
                    final_content,
                    reasoning_content=response.reasoning_content,
                )
            )
            return AgentRunResult(
                final_content=final_content,
                messages=run_messages,
                tools_used=tools_used,
                usage=usage,
                stop_reason="completed",
            )

        final_content = _MAX_ITERATIONS_MESSAGE
        run_messages.append(self._assistant_message(final_content))
        return AgentRunResult(
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
    def _tool_result_message(
        cls,
        tool_call: ToolCall,
        result: ToolResult,
    ) -> Message:
        return {
            "role": "tool",
            "tool_call_id": result.call_id or tool_call.id,
            "name": result.name or tool_call.name,
            "content": cls._tool_result_content(result),
        }

    @classmethod
    def _tool_result_content(cls, result: ToolResult) -> str:
        if result.error is not None:
            return cls._stringify(
                {
                    "error": {
                        "code": result.error.code,
                        "message": result.error.message,
                        "recoverable": result.error.recoverable,
                    }
                }
            )
        return cls._stringify(result.content)

    @staticmethod
    def _stringify(value: Any) -> str:
        if isinstance(value, str):
            return value
        if value is None:
            return ""
        try:
            return json.dumps(value, ensure_ascii=False)
        except (TypeError, ValueError):
            return str(value)

    @staticmethod
    def _accumulate_usage(
        usage: dict[str, int],
        update: dict[str, int],
    ) -> None:
        for key, value in update.items():
            if isinstance(value, int):
                usage[key] = usage.get(key, 0) + value
