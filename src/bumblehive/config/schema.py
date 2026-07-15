import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..protocols import GenerationConfig, MCPServerConfig


@dataclass(frozen=True)
class ProviderConfig:
    """Provider settings used to build the default runtime provider."""

    type: str = "openai_chat_completions"
    model: str = "gpt-5.4"
    api_key: str | None = None
    base_url: str | None = None


@dataclass(frozen=True)
class AgentConfig:
    """Agent defaults applied to each runtime turn."""

    instructions: str | None = None
    dynamic_context: dict[str, Any] = field(default_factory=dict)
    skill_names: tuple[str, ...] | None = None
    tool_names: tuple[str, ...] | None = None


@dataclass(frozen=True)
class RuntimeConfig:
    """Per-runtime defaults applied to each turn."""

    workspace: str | None = None
    timezone: str | None = None
    context_window_tokens: int | None = None
    max_tool_result_chars: int | None = None
    max_iterations: int | None = None
    extra_read_roots: tuple[str, ...] = ()
    extra_write_roots: tuple[str, ...] = ()


@dataclass(frozen=True)
class RuntimeArguments:
    """Convenient flat arguments for constructing a Bumblehive runtime."""

    provider_type: str = "openai_chat_completions"
    model: str = "gpt-5.4"
    api_key: str | None = None
    base_url: str | None = None
    max_completion_tokens: int = 16384
    temperature: float | None = None
    reasoning_effort: str | None = None
    extra_body: dict[str, Any] | None = None
    workspace: str | Path | None = None
    timezone: str | None = None
    context_window_tokens: int | None = None
    max_tool_result_chars: int | None = None
    max_iterations: int | None = None
    extra_read_roots: Sequence[str | Path] = ()
    extra_write_roots: Sequence[str | Path] = ()
    agent_instructions: str | None = None
    dynamic_context: dict[str, Any] = field(default_factory=dict)
    skill_names: tuple[str, ...] | None = None
    tool_names: tuple[str, ...] | None = None
    mcp_servers: tuple[MCPServerConfig, ...] = ()

    def to_config(self) -> "BumblehiveConfig":
        """Convert flat runtime arguments into structured config."""
        return BumblehiveConfig(
            provider=ProviderConfig(
                type=self.provider_type,
                model=self.model,
                api_key=self.api_key,
                base_url=self.base_url,
            ),
            generation=GenerationConfig(
                max_completion_tokens=self.max_completion_tokens,
                temperature=self.temperature,
                reasoning_effort=self.reasoning_effort,
                extra_body=self.extra_body,
            ),
            agent=AgentConfig(
                instructions=self.agent_instructions,
                dynamic_context=dict(self.dynamic_context),
                skill_names=self.skill_names,
                tool_names=self.tool_names,
            ),
            runtime=RuntimeConfig(
                workspace=(
                    str(self.workspace)
                    if self.workspace is not None
                    else None
                ),
                timezone=self.timezone,
                context_window_tokens=self.context_window_tokens,
                max_tool_result_chars=self.max_tool_result_chars,
                max_iterations=self.max_iterations,
                extra_read_roots=tuple(str(path) for path in self.extra_read_roots),
                extra_write_roots=tuple(str(path) for path in self.extra_write_roots),
            ),
            mcp_servers=self.mcp_servers,
        )


@dataclass(frozen=True)
class BumblehiveConfig:
    """Top-level runtime configuration."""

    provider: ProviderConfig = field(default_factory=ProviderConfig)
    generation: GenerationConfig = field(default_factory=GenerationConfig)
    agent: AgentConfig = field(default_factory=AgentConfig)
    runtime: RuntimeConfig = field(default_factory=RuntimeConfig)
    mcp_servers: tuple[MCPServerConfig, ...] = ()

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> "BumblehiveConfig":
        """Build a config object from JSON-like dictionary data."""
        return cls.from_mapping(data)

    @classmethod
    def from_json_file(cls, path: str | Path) -> "BumblehiveConfig":
        """Load a config object from a JSON file."""
        path = Path(path).expanduser()
        if path.suffix.lower() != ".json":
            raise ValueError("Bumblehive config files must be JSON files")

        with path.open(encoding="utf-8") as file:
            data = json.load(file)

        if not isinstance(data, Mapping):
            raise TypeError("Bumblehive JSON config must contain an object")

        return cls.from_mapping(data)

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any] | None) -> "BumblehiveConfig":
        """Build a config object from JSON-like mapping data."""
        raw = dict(data or {})
        return cls(
            provider=_provider_config(raw.get("provider")),
            generation=_generation_config(raw.get("generation")),
            agent=_agent_config(raw.get("agent")),
            runtime=_runtime_config(raw.get("runtime")),
            mcp_servers=_mcp_servers(raw.get("mcp_servers")),
        )

    def to_dict(self) -> dict[str, Any]:
        """Return this config as JSON-like dictionary data."""
        data: dict[str, Any] = {
            "provider": _provider_to_dict(self.provider),
            "generation": _generation_to_dict(self.generation),
        }

        agent = _agent_to_dict(self.agent)
        if agent:
            data["agent"] = agent

        runtime = _runtime_to_dict(self.runtime)
        if runtime:
            data["runtime"] = runtime

        if self.mcp_servers:
            data["mcp_servers"] = [
                _mcp_server_to_dict(server)
                for server in self.mcp_servers
            ]

        return data

    def to_json_file(self, path: str | Path) -> None:
        """Write this config to a JSON file."""
        path = Path(path).expanduser()
        if path.suffix.lower() != ".json":
            raise ValueError("Bumblehive config files must be JSON files")

        with path.open("w", encoding="utf-8") as file:
            json.dump(self.to_dict(), file, ensure_ascii=False, indent=2)
            file.write("\n")


def _mapping(value: Any, section: str) -> Mapping[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise TypeError(f"{section} config must be a mapping")
    return value


def _provider_config(value: Any) -> ProviderConfig:
    data = _mapping(value, "provider")
    return ProviderConfig(
        type=str(data.get("type", ProviderConfig.type)),
        model=str(data.get("model", ProviderConfig.model)),
        api_key=_optional_str(data.get("api_key")),
        base_url=_optional_str(data.get("base_url")),
    )


def _generation_config(value: Any) -> GenerationConfig:
    data = _mapping(value, "generation")
    return GenerationConfig(
        max_completion_tokens=int(
            data.get(
                "max_completion_tokens",
                GenerationConfig.max_completion_tokens,
            )
        ),
        temperature=_optional_float(data.get("temperature")),
        reasoning_effort=_optional_str(data.get("reasoning_effort")),
        extra_body=_optional_dict(data.get("extra_body"), "generation.extra_body"),
    )


def _agent_config(value: Any) -> AgentConfig:
    data = _mapping(value, "agent")
    return AgentConfig(
        instructions=_optional_str(data.get("instructions")),
        dynamic_context=_dynamic_context(data.get("dynamic_context")),
        skill_names=_optional_str_tuple(data.get("skill_names"), "agent.skill_names"),
        tool_names=_optional_str_tuple(data.get("tool_names"), "agent.tool_names"),
    )


def _runtime_config(value: Any) -> RuntimeConfig:
    data = _mapping(value, "runtime")
    return RuntimeConfig(
        workspace=_optional_str(data.get("workspace")),
        timezone=_optional_str(data.get("timezone")),
        context_window_tokens=_optional_int(data.get("context_window_tokens")),
        max_tool_result_chars=_optional_int(data.get("max_tool_result_chars")),
        max_iterations=_optional_int(data.get("max_iterations")),
        extra_read_roots=_runtime_roots(data, "extra_read_roots"),
        extra_write_roots=_runtime_roots(data, "extra_write_roots"),
    )


def _runtime_roots(data: Mapping[str, Any], key: str) -> tuple[str, ...]:
    value = data.get(key, ())
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise TypeError(f"runtime.{key} must be a sequence")
    return tuple(str(item) for item in value)


def _mcp_servers(value: Any) -> tuple[MCPServerConfig, ...]:
    if value is None:
        return ()
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise TypeError("mcp_servers must be a sequence")

    servers: list[MCPServerConfig] = []
    for index, item in enumerate(value):
        data = _mapping(item, f"mcp_servers[{index}]")
        name = data.get("name")
        if not name:
            raise ValueError(f"mcp_servers[{index}].name is required")
        headers = data.get("headers") or {}
        if not isinstance(headers, Mapping):
            raise TypeError(f"mcp_servers[{index}].headers must be a mapping")
        enabled_tool_names = data.get("enabled_tools", ["*"])
        if not isinstance(enabled_tool_names, Sequence) or isinstance(
            enabled_tool_names,
            (str, bytes),
        ):
            raise TypeError(
                f"mcp_servers[{index}].enabled_tools must be a sequence"
            )
        servers.append(
            MCPServerConfig(
                name=str(name),
                url=str(data.get("url", "")),
                headers={str(key): str(value) for key, value in headers.items()},
                tool_timeout=int(data.get("tool_timeout", 30)),
                enabled_tools=[str(name) for name in enabled_tool_names],
            )
        )
    return tuple(servers)


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _dynamic_context(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise TypeError("agent.dynamic_context must be a mapping")
    return {str(key): context_value for key, context_value in value.items()}


def _optional_dict(value: Any, section: str) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise TypeError(f"{section} must be a mapping")
    return value


def _optional_str_tuple(value: Any, section: str) -> tuple[str, ...] | None:
    if value is None:
        return None
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise TypeError(f"{section} must be a sequence")
    return tuple(str(item) for item in value)


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)


def _provider_to_dict(config: ProviderConfig) -> dict[str, Any]:
    data: dict[str, Any] = {
        "type": config.type,
        "model": config.model,
    }
    _set_if_not_none(data, "api_key", config.api_key)
    _set_if_not_none(data, "base_url", config.base_url)
    return data


def _generation_to_dict(config: GenerationConfig) -> dict[str, Any]:
    data: dict[str, Any] = {
        "max_completion_tokens": config.max_completion_tokens,
    }
    _set_if_not_none(data, "temperature", config.temperature)
    _set_if_not_none(data, "reasoning_effort", config.reasoning_effort)
    _set_if_not_none(data, "extra_body", config.extra_body)
    return data


def _agent_to_dict(config: AgentConfig) -> dict[str, Any]:
    data: dict[str, Any] = {}
    _set_if_not_none(data, "instructions", config.instructions)
    if config.dynamic_context:
        data["dynamic_context"] = dict(config.dynamic_context)
    if config.skill_names is not None:
        data["skill_names"] = list(config.skill_names)
    if config.tool_names is not None:
        data["tool_names"] = list(config.tool_names)
    return data


def _runtime_to_dict(config: RuntimeConfig) -> dict[str, Any]:
    data: dict[str, Any] = {}
    _set_if_not_none(data, "workspace", config.workspace)
    _set_if_not_none(data, "timezone", config.timezone)
    _set_if_not_none(data, "context_window_tokens", config.context_window_tokens)
    _set_if_not_none(data, "max_tool_result_chars", config.max_tool_result_chars)
    _set_if_not_none(data, "max_iterations", config.max_iterations)
    _set_if_not_empty(data, "extra_read_roots", list(config.extra_read_roots))
    _set_if_not_empty(data, "extra_write_roots", list(config.extra_write_roots))
    return data


def _mcp_server_to_dict(config: MCPServerConfig) -> dict[str, Any]:
    return {
        "name": config.name,
        "url": config.url,
        "headers": dict(config.headers),
        "tool_timeout": config.tool_timeout,
        "enabled_tools": list(config.enabled_tools),
    }


def _set_if_not_none(data: dict[str, Any], key: str, value: Any) -> None:
    if value is not None:
        data[key] = value


def _set_if_not_empty(data: dict[str, Any], key: str, value: Any) -> None:
    if value:
        data[key] = value
