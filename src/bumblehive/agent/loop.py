from pathlib import Path
from typing import Any, Mapping

from ..observability import (
    EventEmitter,
    HookInput,
    TurnEvents,
)
from ..protocols import GenerationConfig
from ..providers.base import ModelProvider
from ..skills.manager import SkillsManager
from ..tools.manager import ToolManager
from ..tools.scope import bind_tool_session, reset_tool_session
from .context import ContextBuilder, DynamicValue, MessageHistory
from .runner import AgentRunResult, CheckpointCallback, ToolCallingRunner


class AgentLoop:
    """Build turn context, then delegate model/tool execution."""

    def __init__(
        self,
        *,
        tools: ToolManager,
        context: ContextBuilder,
        skills: SkillsManager,
        runner: ToolCallingRunner,
        history: MessageHistory | None = None,
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
        history_messages: list[dict[str, Any]] | None = None,
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
        session_id: str | None = None,
        stream: bool = False,
        checkpoint_callback: CheckpointCallback | None = None,
    ) -> AgentRunResult:
        """Run one user turn with optional skill and tool filtering.

        ``skill_names`` and ``tool_names`` use the same selection semantics:
        ``None`` exposes everything, ``[]`` exposes nothing, and a non-empty
        list exposes only the named items in the given order.

        When ``history_messages`` is provided, it is used only for this turn.
        Otherwise, the optional history passed to the constructor is read and
        updated after a successful turn.
        """
        emitter = EventEmitter.from_hooks(
            hooks,
            run_id=run_id,
            session_id=session_id,
        )
        turn_events = TurnEvents(emitter)
        tool_session_id = session_id if session_id is not None else emitter.run_id
        session_token = bind_tool_session(tool_session_id)
        try:
            await turn_events.started(current_user_message)
            try:
                return await self._run_turn(
                    current_user_message,
                    provider=provider,
                    model=model,
                    history_messages=history_messages,
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
                    checkpoint_callback=checkpoint_callback,
                )
            except Exception as exc:
                await turn_events.error(exc)
                raise
        finally:
            reset_tool_session(session_token)

    async def _run_turn(
        self,
        current_user_message: str,
        *,
        provider: ModelProvider,
        model: str,
        history_messages: list[dict[str, Any]] | None,
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
        checkpoint_callback: CheckpointCallback | None,
    ) -> AgentRunResult:
        internal_history = self.history if history_messages is None else None
        if history_messages is None:
            history_messages = (
                internal_history.get_history()
                if internal_history is not None
                else []
            )

        available_skills = self.skills.build_skills_summary(skill_names)
        messages = self.context.build(
            current_user_message=current_user_message,
            workspace=workspace,
            timezone=timezone,
            dynamic_context=dynamic_context,
            history=history_messages,
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
            checkpoint_callback=checkpoint_callback,
        )
        if internal_history is not None:
            internal_history.replace_run_messages(result.messages)
        await turn_events.finished(
            stop_reason=result.stop_reason,
            error=result.error,
        )
        return result
