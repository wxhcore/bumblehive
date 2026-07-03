from collections.abc import Mapping
from types import TracebackType
from typing import Any

from .agent import (
    AgentLoop,
    AgentRunResult,
    ContextBuilder,
    MessageHistoryManager,
    ToolCallingRunner,
)
from .config.loader import ConfigInput, load_config
from .config.schema import BumblehiveConfig, ProviderConfig
from .observability import HookInput
from .providers import ModelProvider, ProviderManager
from .skills import SkillsManager
from .tools import ToolManager


class BumblehiveRuntime:
    """High-level in-memory runtime built from BumblehiveConfig."""

    def __init__(self, config: ConfigInput = None) -> None:
        self.config = load_config(config)
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
        config: Mapping[str, Any] | None = None,
        hooks: HookInput = None,
    ) -> AgentRunResult:
        """Run one turn using runtime defaults plus optional per-turn config."""
        run_config = self._resolve_run_config(config)
        self.tools.register_builtin_tools()
        await self.tools.sync_mcp_servers(run_config.mcp_servers)
        provider = await self._get_provider(run_config.provider)
        return await self.loop.run_turn(
            message,
            provider=provider,
            model=run_config.provider.model,
            generation=run_config.generation,
            workspace=run_config.runtime.workspace,
            timezone=run_config.runtime.timezone,
            dynamic_context=run_config.agent.dynamic_context,
            skill_names=_list_or_none(run_config.agent.skill_names),
            tool_names=_list_or_none(run_config.agent.tool_names),
            context_window_tokens=run_config.runtime.context_window_tokens,
            max_tool_result_chars=run_config.runtime.max_tool_result_chars,
            max_iterations=run_config.runtime.max_iterations,
            agent_instructions=run_config.agent.instructions,
            hooks=hooks,
        )

    async def close(self) -> None:
        """Release resources owned by this runtime."""
        await self.tools.close()
        await self.providers.close()

    def _resolve_run_config(
        self,
        config: Mapping[str, Any] | None = None,
    ) -> BumblehiveConfig:
        if config is None:
            return self.config

        base = self.config.to_dict()
        return BumblehiveConfig.from_mapping(_deep_merge(base, config))

    async def _get_provider(self, config: ProviderConfig) -> ModelProvider:
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


def _deep_merge(base: Mapping[str, Any], overlay: Mapping[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in overlay.items():
        base_value = merged.get(key)
        if isinstance(base_value, Mapping) and isinstance(value, Mapping):
            merged[key] = _deep_merge(base_value, value)
        else:
            merged[key] = value
    return merged
