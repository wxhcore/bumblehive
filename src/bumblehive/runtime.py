import asyncio
from collections.abc import Iterable, Mapping
from types import TracebackType
from typing import Any

from .agent import (
    AgentLoop,
    AgentRunResult,
    CheckpointCallback,
    ContextBuilder,
    ToolCallingRunner,
)
from .config.loader import ConfigInput, load_config
from .config.schema import BumblehiveConfig, ProviderConfig
from .observability import (
    DEFAULT_STREAM_QUEUE_SIZE,
    AgentHook,
    AsyncEventStream,
    AsyncEventStreamHook,
    HookInput,
)
from .providers import ModelProvider, ProviderManager
from .session import SessionManager
from .skills import SkillsManager
from .tools import PathAllowlist, ToolManager


class BumblehiveRuntime:
    """High-level agent runtime built from BumblehiveConfig."""

    def __init__(
        self,
        config: ConfigInput = None,
    ) -> None:
        self.config = load_config(config)
        self.providers = ProviderManager()
        self.tools = ToolManager()
        self.context = ContextBuilder()
        self.skills = SkillsManager()
        self.runner = ToolCallingRunner()
        self.sessions = SessionManager()

        self._tools_initialized = False
        self._tools_init_lock = asyncio.Lock()

    @classmethod
    def from_config(
        cls,
        config: ConfigInput = None,
    ) -> "BumblehiveRuntime":
        """Create a runtime from a JSON file, mapping, config object, or defaults."""
        return cls(config)

    async def __aenter__(self) -> "BumblehiveRuntime":
        await self.initialize_tools()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.close()

    async def initialize_tools(self) -> None:
        """Register built-ins and connect the runtime-scoped MCP servers once."""
        if self._tools_initialized:
            return

        async with self._tools_init_lock:
            if self._tools_initialized:
                return

            self.tools.register_builtin_tools()
            await self.tools.sync_mcp_servers(self.config.mcp_servers)
            self._tools_initialized = True

    async def run(
        self,
        message: str,
        *,
        config: Mapping[str, Any] | None = None,
        hooks: HookInput = None,
        session_id: str | None = None,
    ) -> AgentRunResult:
        """Run one stateless turn, or persist it when session_id is provided."""
        return await self._run(
            message,
            config=config,
            hooks=hooks,
            session_id=session_id,
            stream=False,
        )

    def stream(
        self,
        message: str,
        *,
        config: Mapping[str, Any] | None = None,
        hooks: HookInput = None,
        session_id: str | None = None,
        max_queue_size: int = DEFAULT_STREAM_QUEUE_SIZE,
    ) -> AsyncEventStream[AgentRunResult]:
        """Stream one stateless or explicitly session-backed turn."""

        async def _run_with_stream_hook(
            stream_hook: AsyncEventStreamHook,
        ) -> AgentRunResult:
            return await self._run(
                message,
                config=config,
                hooks=_append_hook(hooks, stream_hook),
                session_id=session_id,
                stream=True,
            )

        return AsyncEventStream(_run_with_stream_hook, maxsize=max_queue_size)

    async def run_console(
        self,
        message: str,
        *,
        config: Mapping[str, Any] | None = None,
        hooks: HookInput = None,
        session_id: str | None = None,
        renderer: Any | None = None,
        max_queue_size: int = DEFAULT_STREAM_QUEUE_SIZE,
    ) -> AgentRunResult:
        """Run and render one stateless or explicitly session-backed turn."""

        if renderer is None:
            from .console import ConsoleStreamRenderer

            renderer = ConsoleStreamRenderer()

        stream = self.stream(
            message,
            config=config,
            hooks=hooks,
            session_id=session_id,
            max_queue_size=max_queue_size,
        )
        renderer.start(message)
        try:
            async for event in stream:
                await renderer.on_event(event)
            return await stream.result()
        finally:
            await stream.aclose()
            await renderer.finish()

    async def delete_session(self, session_id: str) -> bool:
        """Delete a persisted session and evict its cached state."""
        return await self.sessions.delete(session_id)

    async def _run(
        self,
        message: str,
        *,
        config: Mapping[str, Any] | None = None,
        hooks: HookInput = None,
        session_id: str | None = None,
        stream: bool = False,
    ) -> AgentRunResult:
        """Run one stateless turn, or persist it when session_id is provided."""
        run_config = self._resolve_run_config(config)
        if session_id is None:
            return await self._run_agent(
                message,
                run_config=run_config,
                hooks=hooks,
                session_id=None,
                stream=stream,
            )

        session = await self.sessions.get(session_id)
        async with session.lock:
            await self.sessions.recover(session)
            history_messages = self.sessions.get_history(session)
            await self.sessions.append_user(session, message)
            checkpoint = self.sessions.create_checkpoint_callback(session)

            try:
                return await self._run_agent(
                    message,
                    run_config=run_config,
                    history_messages=history_messages,
                    hooks=hooks,
                    session_id=session.session_id,
                    stream=stream,
                    checkpoint_callback=checkpoint,
                )
            except Exception as exc:
                try:
                    await self.sessions.recover(session)
                except Exception as recovery_exc:
                    exc.add_note(
                        "Failed to persist the interrupted turn: "
                        f"{type(recovery_exc).__name__}: {recovery_exc}"
                    )
                raise

    async def _run_agent(
        self,
        message: str,
        *,
        run_config: BumblehiveConfig,
        hooks: HookInput,
        session_id: str | None,
        stream: bool,
        history_messages: list[dict[str, Any]] | None = None,
        checkpoint_callback: CheckpointCallback | None = None,
    ) -> AgentRunResult:
        await self.initialize_tools()
        provider = await self._get_provider(run_config.provider)
        loop = self._build_loop()
        path_allowlist = PathAllowlist.from_roots(
            extra_read_roots=run_config.runtime.extra_read_roots,
            extra_write_roots=(
                *run_config.runtime.extra_write_roots,
                self.skills.skills_dir,
            ),
        )
        return await loop.run_turn(
            message,
            provider=provider,
            model=run_config.provider.model,
            history_messages=history_messages,
            generation=run_config.generation,
            workspace=run_config.runtime.workspace,
            path_allowlist=path_allowlist,
            timezone=run_config.runtime.timezone,
            dynamic_context=run_config.agent.dynamic_context,
            skill_names=_list_or_none(run_config.agent.skill_names),
            tool_names=_list_or_none(run_config.agent.tool_names),
            context_window_tokens=run_config.runtime.context_window_tokens,
            max_tool_result_chars=run_config.runtime.max_tool_result_chars,
            max_iterations=run_config.runtime.max_iterations,
            agent_instructions=run_config.agent.instructions,
            hooks=hooks,
            session_id=session_id,
            stream=stream,
            checkpoint_callback=checkpoint_callback,
        )

    async def close(self) -> None:
        """Release resources owned by this runtime."""
        try:
            await self.tools.close()
        finally:
            await self.providers.close()

    def _resolve_run_config(
        self,
        config: Mapping[str, Any] | None = None,
    ) -> BumblehiveConfig:
        if config is not None and "mcp_servers" in config:
            raise ValueError("mcp_servers cannot be changed per run")
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

    def _build_loop(self) -> AgentLoop:
        return AgentLoop(
            tools=self.tools,
            context=self.context,
            skills=self.skills,
            runner=self.runner,
        )


def from_config(
    config: ConfigInput = None,
) -> BumblehiveRuntime:
    """Create a runtime from a JSON file, mapping, or config object."""
    return BumblehiveRuntime.from_config(config)


def _list_or_none(values: tuple[str, ...] | None) -> list[str] | None:
    if values is None:
        return None
    return list(values)


def _append_hook(hooks: HookInput, hook: AgentHook) -> HookInput:
    if hooks is None:
        return hook
    if isinstance(hooks, AgentHook) or callable(hooks):
        return [hook, hooks]
    if isinstance(hooks, Iterable):
        return [hook, *hooks]
    return [hook, hooks]


def _deep_merge(base: Mapping[str, Any], overlay: Mapping[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in overlay.items():
        base_value = merged.get(key)
        if isinstance(base_value, Mapping) and isinstance(value, Mapping):
            merged[key] = _deep_merge(base_value, value)
        else:
            merged[key] = value
    return merged
