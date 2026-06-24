from collections.abc import Sequence
from pathlib import Path
from typing import Mapping

from ..providers.base import GenerationConfig, ModelProvider
from ..skills.manager import SkillsManager
from ..tools.manager import ToolManager
from .context import ContextBuilder, DynamicValue
from .runner import AgentRunResult, Message, ToolCallingRunner


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
        current_user_message: str,
        *,
        provider: ModelProvider,
        model: str,
        generation: GenerationConfig | None = None,
        workspace: Path | str | None = None,
        timezone: str | None = None,
        dynamic_context: Mapping[str, DynamicValue] | None = None,
        history: Sequence[Message] | None = None,
        skill_names: list[str] | None = None,
        tool_names: list[str] | None = None,
        context_window_tokens: int | None = None,
        agent_instructions: str | None = None,
    ) -> AgentRunResult:
        """Run one user turn with optional skill and tool filtering.

        ``skill_names`` and ``tool_names`` use the same selection semantics:
        ``None`` exposes everything, ``[]`` exposes nothing, and a non-empty
        list exposes only the named items in the given order.
        """
        available_skills = self.skills.build_skills_summary(
            skill_names,
            workspace=workspace,
        )
        messages = self.context.build(
            current_user_message=current_user_message,
            workspace=workspace,
            timezone=timezone,
            dynamic_context=dynamic_context,
            history=history,
            agent_instructions=agent_instructions,
            available_skills=available_skills,
        )

        return await self.runner.run(
            provider=provider,
            tools=self.tools,
            messages=messages,
            model=model,
            generation=generation,
            workspace=workspace,
            tool_names=tool_names,
            context_window_tokens=context_window_tokens,
        )
