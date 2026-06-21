import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..providers.base import ModelProvider, ModelRequest
from ..tools.calls import ToolCall, ToolResult
from ..tools.manager import ToolManager
from .config import AgentRunConfig
from .history import prepare_history
from .types import AgentError


Message = dict[str, Any]


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
        config: AgentRunConfig,
        workspace: Path | str | None = None,
        tool_names: list[str] | None = None,
    ) -> AgentRunResult:
        """Run model/tool iterations until a final model response is produced."""
        if config.max_iterations < 1:
            raise ValueError("max_iterations must be at least 1")

        tool_definitions = tools.get_openai_tool_definitions(tool_names)
        run_messages = [dict(message) for message in messages]
        tools_used: list[str] = []
        usage: dict[str, int] = {}

        for _iteration in range(config.max_iterations):
            request = ModelRequest(
                messages=prepare_history(
                    run_messages,
                    max_tool_result_chars=config.max_tool_result_chars,
                ),
                tools=tool_definitions,
                model=config.model,
                generation=config.generation,
                tool_choice=config.tool_choice,
            )
            response = await provider.generate_with_retry(
                request,
                retry=config.retry,
            )
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

            final_content = response.content or ""
            run_messages.append(self._assistant_message(final_content))
            return AgentRunResult(
                final_content=final_content,
                messages=run_messages,
                tools_used=tools_used,
                usage=usage,
                stop_reason="completed",
            )

        final_content = config.max_iterations_message
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
    def _assistant_message(content: str | None) -> Message:
        return {
            "role": "assistant",
            "content": content or "",
        }

    @classmethod
    def _assistant_tool_call_message(cls, response: Any) -> Message:
        message = cls._assistant_message(response.content)
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
