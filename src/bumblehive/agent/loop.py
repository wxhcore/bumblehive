from pathlib import Path
from typing import Mapping

from ..observability import (
    EventEmitter,
    HookInput,
    TurnEvents,
)
from ..protocols import GenerationConfig
from ..providers.base import ModelProvider
from ..skills.manager import SkillsManager
from ..tools.manager import ToolManager
from .context import ContextBuilder, DynamicValue, MessageHistoryManager
from .runner import AgentRunResult, ToolCallingRunner


class AgentLoop:
    """Build turn context, then delegate model/tool execution."""

    def __init__(
        self,
        *,
        tools: ToolManager,
        context: ContextBuilder,
        skills: SkillsManager,
        runner: ToolCallingRunner,
        history: MessageHistoryManager,
    ) -> None:
        self.tools = tools
        self.context = context
        self.skills = skills
        self.runner = runner
        self.history = history

    async def run_turn(
        self,
        current_user_message: str,
        *,
        provider: ModelProvider,
        model: str,
        generation: GenerationConfig | None = None,
        workspace: Path | str | None = None,
        timezone: str | None = None,
        dynamic_context: Mapping[str, DynamicValue] | None = None,
        skill_names: list[str] | None = None,
        tool_names: list[str] | None = None,
        context_window_tokens: int | None = None,
        max_tool_result_chars: int | None = None,
        max_iterations: int | None = None,
        agent_instructions: str | None = None,
        hooks: HookInput = None,
        run_id: str | None = None,
        stream: bool = False,
    ) -> AgentRunResult:
        """Run one user turn with optional skill and tool filtering.

        ``skill_names`` and ``tool_names`` use the same selection semantics:
        ``None`` exposes everything, ``[]`` exposes nothing, and a non-empty
        list exposes only the named items in the given order.
        """
        emitter = EventEmitter.from_hooks(hooks, run_id=run_id)
        turn_events = TurnEvents(emitter)
        await turn_events.started(current_user_message)

        try:
            return await self._run_turn(
                current_user_message,
                provider=provider,
                model=model,
                generation=generation,
                workspace=workspace,
                timezone=timezone,
                dynamic_context=dynamic_context,
                skill_names=skill_names,
                tool_names=tool_names,
                context_window_tokens=context_window_tokens,
                max_tool_result_chars=max_tool_result_chars,
                max_iterations=max_iterations,
                agent_instructions=agent_instructions,
                emitter=emitter,
                stream=stream,
            )
        except Exception as exc:
            await turn_events.error(exc)
            raise

    async def _run_turn(
        self,
        current_user_message: str,
        *,
        provider: ModelProvider,
        model: str,
        generation: GenerationConfig | None,
        workspace: Path | str | None,
        timezone: str | None,
        dynamic_context: Mapping[str, DynamicValue] | None,
        skill_names: list[str] | None,
        tool_names: list[str] | None,
        context_window_tokens: int | None,
        max_tool_result_chars: int | None,
        max_iterations: int | None,
        agent_instructions: str | None,
        emitter: EventEmitter,
        stream: bool,
    ) -> AgentRunResult:
        available_skills = self.skills.build_skills_summary(
            skill_names,
            workspace=workspace,
        )
        messages = self.context.build(
            current_user_message=current_user_message,
            workspace=workspace,
            timezone=timezone,
            dynamic_context=dynamic_context,
            history=self.history.history(),
            agent_instructions=agent_instructions,
            available_skills=available_skills,
        )
        turn_events = TurnEvents(emitter)
        await turn_events.context_built(message_count=len(messages))

        result = await self.runner.run(
            provider=provider,
            tools=self.tools,
            messages=messages,
            model=model,
            generation=generation,
            workspace=workspace,
            tool_names=tool_names,
            context_window_tokens=context_window_tokens,
            max_tool_result_chars=max_tool_result_chars,
            max_iterations=max_iterations,
            emitter=emitter,
            stream=stream,
        )
        self.history.replace_run_messages(result.messages)
        await turn_events.finished(
            stop_reason=result.stop_reason,
            error=result.error,
        )
        return result
