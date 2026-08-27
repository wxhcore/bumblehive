from pathlib import Path
from typing import Mapping

from ..observability.emitter import EventEmitter
from ..observability.emitters import TurnEvents
from ..observability.hooks import HookInput
from ..protocols import (
    GenerationConfig,
    Message,
    UserMessage,
    normalize_user_message,
)
from ..providers.base import ModelProvider
from ..skills.manager import SkillsManager
from ..tools.manager import ToolManager
from ..tools.scope import ToolPathPolicy, bind_tool_session, reset_tool_session
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
    ) -> None:
        self.tools = tools
        self.context = context
        self.skills = skills
        self.runner = runner

    async def run_turn(
        self,
        current_user_message: UserMessage,
        *,
        provider: ModelProvider,
        model: str,
        history: MessageHistory | None = None,
        history_messages: list[Message] | None = None,
        generation: GenerationConfig | None = None,
        workspace: Path | str | None = None,
        path_policy: ToolPathPolicy = ToolPathPolicy(),
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

        ``history`` is caller-owned local memory that is read without being
        updated or retained by the loop. ``history_messages`` is a
        managed-session snapshot and therefore requires ``session_id``.
        """
        resolved_history_messages = self._resolve_history_messages(
            history,
            history_messages,
            session_id,
        )
        current_messages = normalize_user_message(current_user_message)
        emitter = EventEmitter.from_hooks(
            hooks,
            run_id=run_id,
            session_id=session_id,
        )
        turn_events = TurnEvents(emitter)
        tool_session_id = self._resolve_tool_session_id(
            session_id,
            history,
            emitter.run_id,
        )
        session_token = bind_tool_session(tool_session_id)
        try:
            await turn_events.started(current_messages)
            try:
                available_skills = self.skills.build_skills_summary(skill_names)
                messages = self.context.build(
                    current_messages=current_messages,
                    workspace=workspace,
                    timezone=timezone,
                    dynamic_context=dynamic_context,
                    history=resolved_history_messages or [],
                    agent_instructions=agent_instructions,
                    available_skills=available_skills,
                )
                await turn_events.context_built(message_count=len(messages))

                result = await self.runner.run(
                    provider=provider,
                    tools=self.tools,
                    messages=messages,
                    model=model,
                    generation=generation,
                    workspace=workspace,
                    path_policy=path_policy,
                    tool_names=tool_names,
                    context_window_tokens=context_window_tokens,
                    max_tool_result_chars=max_tool_result_chars,
                    max_iterations=max_iterations,
                    emitter=emitter,
                    stream=stream,
                    checkpoint_callback=checkpoint_callback,
                )
                await turn_events.finished(
                    stop_reason=result.stop_reason,
                    error=result.error,
                )
                return result
            except Exception as exc:
                await turn_events.error(exc)
                raise
        finally:
            reset_tool_session(session_token)

    @staticmethod
    def _resolve_history_messages(
        history: MessageHistory | None,
        history_messages: list[Message] | None,
        session_id: str | None,
    ) -> list[Message] | None:
        if history is not None and not isinstance(history, MessageHistory):
            raise TypeError("history must be a MessageHistory")
        if history is not None and history_messages is not None:
            raise ValueError("history and history_messages cannot be used together")
        if history is not None and session_id is not None:
            raise ValueError("history and session_id cannot be used together")
        if history_messages is not None and session_id is None:
            raise ValueError(
                "history_messages requires session_id; use MessageHistory for "
                "caller-managed history"
            )
        return history.get_history() if history is not None else history_messages

    @staticmethod
    def _resolve_tool_session_id(
        session_id: str | None,
        history: MessageHistory | None,
        run_id: str,
    ) -> str:
        if session_id is not None:
            return session_id
        if history is not None:
            return history.conversation_id
        return run_id
