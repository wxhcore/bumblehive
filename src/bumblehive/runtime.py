from collections.abc import Mapping
from pathlib import Path
from types import TracebackType

from .agent import (
    AgentLoop,
    AgentRunResult,
    ContextBuilder,
    MessageHistoryManager,
    ToolCallingRunner,
)
from .agent.context import DynamicValue
from .config.loader import ConfigInput, load_config
from .config.schema import BumblehiveConfig
from .providers import GenerationConfig, ModelProvider, ProviderManager
from .skills import SkillsManager
from .tools import ToolManager


class BumblehiveRuntime:
    """High-level in-memory runtime built from BumblehiveConfig."""

    def __init__(self, config: ConfigInput = None) -> None:
        self._config_input = config
        self.config = load_config(self._config_input)
        self.providers = ProviderManager()
        self.tools = ToolManager()
        self.context = ContextBuilder()
        self.skills = SkillsManager()
        self.runner = ToolCallingRunner()
        self.history = MessageHistoryManager()
        self.loop = AgentLoop(
            tools=self.tools,
            context=self.context,
            skills=self.skills,
            runner=self.runner,
            history=self.history,
        )

    @classmethod
    def from_config(cls, config: ConfigInput = None) -> "BumblehiveRuntime":
        """Create a runtime from a JSON file, mapping, config object, or defaults."""
        return cls(config)

    def reload_config(self) -> BumblehiveConfig:
        """Reload the current config source and replace runtime defaults."""
        self.config = load_config(self._config_input)
        return self.config

    def update_config(self, config: ConfigInput = None) -> BumblehiveConfig:
        """Replace the config source and reload runtime defaults."""
        self._config_input = config
        return self.reload_config()

    async def __aenter__(self) -> "BumblehiveRuntime":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.close()

    async def run(
        self,
        message: str,
        *,
        model: str | None = None,
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
    ) -> AgentRunResult:
        """Run one turn using runtime defaults, with optional per-turn overrides."""
        self.reload_config()
        self.tools.register_builtin_tools()
        await self.tools.sync_mcp_servers(self.config.mcp_servers)
        provider = await self._get_provider()
        return await self.loop.run_turn(
            message,
            provider=provider,
            model=model if model is not None else self.config.provider.model,
            generation=(
                generation if generation is not None else self.config.generation
            ),
            workspace=(
                workspace if workspace is not None else self.config.runtime.workspace
            ),
            timezone=(
                timezone if timezone is not None else self.config.runtime.timezone
            ),
            dynamic_context=(
                dynamic_context
                if dynamic_context is not None
                else self.config.agent.dynamic_context
            ),
            skill_names=(
                skill_names
                if skill_names is not None
                else _list_or_none(self.config.agent.skill_names)
            ),
            tool_names=(
                tool_names
                if tool_names is not None
                else _list_or_none(self.config.agent.tool_names)
            ),
            context_window_tokens=(
                context_window_tokens
                if context_window_tokens is not None
                else self.config.runtime.context_window_tokens
            ),
            max_tool_result_chars=(
                max_tool_result_chars
                if max_tool_result_chars is not None
                else self.config.runtime.max_tool_result_chars
            ),
            max_iterations=(
                max_iterations
                if max_iterations is not None
                else self.config.runtime.max_iterations
            ),
            agent_instructions=(
                agent_instructions
                if agent_instructions is not None
                else self.config.agent.instructions
            ),
        )

    async def close(self) -> None:
        """Release resources owned by this runtime."""
        await self.tools.close()
        await self.providers.close()

    async def _get_provider(self) -> ModelProvider:
        config = self.config.provider
        if config.type != "openai_chat_completions":
            raise ValueError(f"Unsupported provider type: {config.type}")
        return await self.providers.get(
            api_key=config.api_key,
            base_url=config.base_url,
        )


def from_config(config: ConfigInput = None) -> BumblehiveRuntime:
    """Create an in-memory runtime from a JSON file, mapping, or config object."""
    return BumblehiveRuntime.from_config(config)


def _list_or_none(values: tuple[str, ...] | None) -> list[str] | None:
    if values is None:
        return None
    return list(values)
