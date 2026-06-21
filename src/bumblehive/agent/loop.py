from collections.abc import Sequence
from pathlib import Path
from typing import Mapping

from ..providers.config import ProviderConfig
from ..providers.manager import ProviderManager
from ..skills.manager import SkillsManager
from ..tools.manager import ToolManager
from .config import AgentRunConfig
from .context import ContextBuilder, DynamicValue
from .runner import AgentRunResult, Message, ToolCallingRunner


class AgentLoop:
    """Build turn context, then delegate model/tool execution."""

    def __init__(
        self,
        *,
        providers: ProviderManager,
        tools: ToolManager,
        context: ContextBuilder,
        skills: SkillsManager,
        runner: ToolCallingRunner,
    ) -> None:
        self.providers = providers
        self.tools = tools
        self.context = context
        self.skills = skills
        self.runner = runner

    async def run_turn(
        self,
        current_user_message: str,
        *,
        provider_config: ProviderConfig,
        run_config: AgentRunConfig,
        workspace: Path | str | None = None,
        timezone: str | None = None,
        dynamic_context: Mapping[str, DynamicValue] | None = None,
        history: Sequence[Message] | None = None,
        skill_names: list[str] | None = None,
        tool_names: list[str] | None = None,
        agent_instructions: str | None = None,
    ) -> AgentRunResult:
        """Run one user turn with optional skill and tool filtering.

        ``skill_names`` and ``tool_names`` use the same selection semantics:
        ``None`` exposes everything, ``[]`` exposes nothing, and a non-empty
        list exposes only the named items in the given order.
        """
        provider = await self.providers.get(
            api_key=provider_config.api_key,
            base_url=provider_config.base_url,
        )

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
            tool_names=tool_names,
            workspace=workspace,
            config=run_config,
        )
