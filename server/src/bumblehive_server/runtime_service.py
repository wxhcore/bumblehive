import asyncio
import json
import logging
import os
from collections.abc import AsyncIterator, Callable, Mapping
from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path
from time import perf_counter
from typing import Any
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

from bumblehive import (
    BumblehiveConfig,
    BumblehiveRuntime,
    ToolManager,
)
from bumblehive.paths import get_workspace_path
from bumblehive.protocols import MCPServerConfig
from bumblehive.skills import SkillLoadResult
from openai import AsyncOpenAI

from .config_defaults import apply_config_defaults
from .logging_utils import elapsed_since, safe_log_value
from .session_reader import SessionReader
from .subagents import register_subagent_tool


RuntimeFactory = Callable[[BumblehiveConfig], BumblehiveRuntime]
OpenAIClientFactory = Callable[..., AsyncOpenAI]
ToolManagerFactory = Callable[..., ToolManager]
logger = logging.getLogger("uvicorn.error.bumblehive")


class RuntimeBusyError(RuntimeError):
    """Raised when settings are changed while a run is active."""


class ModelListError(RuntimeError):
    """Raised when the provider cannot return a model list."""


class MCPConnectionError(RuntimeError):
    """Raised when an MCP server cannot connect or list its tools."""


class RuntimeNotStartedError(RuntimeError):
    """Raised when the server runtime has not been started."""


class RuntimeService:
    def __init__(
        self,
        config_path: str | Path,
        *,
        session_reader: SessionReader | None = None,
        runtime_factory: RuntimeFactory = BumblehiveRuntime.from_config,
        openai_client_factory: OpenAIClientFactory | None = None,
        tool_manager_factory: ToolManagerFactory = ToolManager,
    ) -> None:
        self.config_path = Path(config_path).expanduser()
        self._session_reader = session_reader
        self._runtime_factory = runtime_factory
        self._openai_client_factory = openai_client_factory or AsyncOpenAI
        self._tool_manager_factory = tool_manager_factory
        self._runtime: BumblehiveRuntime | None = None
        self._active_runs = 0
        self._lock = asyncio.Lock()

    @property
    def ready(self) -> bool:
        return self._runtime is not None

    @property
    def config(self) -> BumblehiveConfig:
        runtime = self._runtime
        if runtime is None:
            raise RuntimeNotStartedError("runtime is not started")
        return runtime.config

    @property
    def workspace(self) -> Path:
        return get_workspace_path(self.config.runtime.workspace)

    async def startup(self) -> None:
        async with self._lock:
            if self._runtime is not None:
                return
            source = "file" if self.config_path.exists() else "defaults"
            load_started_at = perf_counter()
            try:
                config = self._load_config()
            except Exception:
                logger.exception(
                    "[config] load failed | source=%s | duration=%s",
                    source,
                    elapsed_since(load_started_at),
                )
                raise
            logger.info(
                "[config] loaded | source=%s | duration=%s",
                source,
                elapsed_since(load_started_at),
            )
            runtime = await self._create_ready_runtime(config)
            self._runtime = runtime

    async def shutdown(self) -> None:
        async with self._lock:
            runtime = self._runtime
            self._runtime = None
        if runtime is not None:
            await runtime.close()

    @asynccontextmanager
    async def lease(self) -> AsyncIterator[BumblehiveRuntime]:
        async with self._lock:
            runtime = self._runtime
            if runtime is None:
                raise RuntimeNotStartedError("runtime is not started")
            self._active_runs += 1
        try:
            yield runtime
        finally:
            async with self._lock:
                self._active_runs -= 1

    async def delete_session(self, session_id: str) -> bool:
        started_at = perf_counter()
        try:
            async with self.lease() as runtime:
                deleted = await runtime.delete_session(session_id)
        except Exception:
            logger.exception(
                "[session] delete failed | session_id=%s | duration=%s",
                safe_log_value(session_id),
                elapsed_since(started_at),
            )
            raise
        logger.info(
            "[session] delete completed | session_id=%s | deleted=%s | duration=%s",
            safe_log_value(session_id),
            str(deleted).lower(),
            elapsed_since(started_at),
        )
        return deleted

    async def list_models(
        self,
        *,
        base_url: str,
        api_key: str | None = None,
    ) -> list[str]:
        cleaned_base_url = _normalize_base_url(base_url)
        async with self._lock:
            runtime = self._runtime
            if runtime is None:
                raise RuntimeNotStartedError("runtime is not started")
            provider_config = runtime.config.provider

        resolved_api_key = _text_or_none(api_key)
        if resolved_api_key is None:
            saved_base_url = (
                _normalize_base_url(provider_config.base_url)
                if provider_config.base_url
                else None
            )
            if saved_base_url != cleaned_base_url:
                raise ValueError(
                    "API Key is required when querying a different Base URL"
                )
            resolved_api_key = _text_or_none(provider_config.api_key)
        if resolved_api_key is None:
            raise ValueError("API Key is required")

        client: AsyncOpenAI | None = None
        try:
            client = self._openai_client_factory(
                api_key=resolved_api_key,
                base_url=cleaned_base_url,
            )
            response = await client.models.list()
            return _model_ids(response)
        except Exception as exc:
            logger.warning(
                "[models] provider request failed | base_url=%s | error_type=%s",
                safe_log_value(cleaned_base_url),
                type(exc).__name__,
            )
            raise ModelListError("third-party model query failed") from exc
        finally:
            if client is not None:
                await client.close()

    async def update_config(
        self,
        patch: Mapping[str, Any],
    ) -> BumblehiveConfig:
        started_at = perf_counter()
        logger.info("[config] update started")
        try:
            async with self._lock:
                current = self._runtime
                if current is None:
                    raise RuntimeNotStartedError("runtime is not started")
                if self._active_runs:
                    raise RuntimeBusyError("runtime has active runs")

                resolved_patch = _restore_masked_mcp_headers(
                    current.config.to_dict(),
                    patch,
                )
                merged = _deep_merge(current.config.to_dict(), resolved_patch)
                config = BumblehiveConfig.from_mapping(
                    apply_config_defaults(merged)
                )
                replacement = await self._create_ready_runtime(config)
                try:
                    self._write_config(config)
                except BaseException:
                    await replacement.close()
                    raise
                self._runtime = replacement

            await current.close()
        except RuntimeBusyError:
            logger.warning(
                "[config] update rejected | reason=active_run | duration=%s",
                elapsed_since(started_at),
            )
            raise
        except Exception:
            logger.exception(
                "[config] update failed | duration=%s",
                elapsed_since(started_at),
            )
            raise
        logger.info(
            "[config] update completed | duration=%s",
            elapsed_since(started_at),
        )
        return config

    async def test_mcp_server(
        self,
        server: Mapping[str, Any],
        *,
        original_name: str | None = None,
    ) -> list[str]:
        """Test one draft MCP config without changing the active runtime."""
        async with self._lock:
            runtime = self._runtime
            if runtime is None:
                raise RuntimeNotStartedError("runtime is not started")
            current_config = runtime.config.to_dict()

        resolved = _mcp_test_config(
            current_config,
            server,
            original_name=original_name,
        )
        manager = self._tool_manager_factory(mcp_servers=[resolved])
        try:
            return await manager.connect_mcp_server(resolved.name)
        except Exception as exc:
            logger.warning(
                "[mcp] test failed | server=%s | error_type=%s",
                safe_log_value(resolved.name),
                type(exc).__name__,
            )
            raise MCPConnectionError(
                "无法连接 MCP 服务或读取工具，请检查 URL、鉴权信息和服务状态"
            ) from exc
        finally:
            await manager.close()

    async def reload_mcp_servers(
        self,
        server_name: str | None = None,
    ) -> list[str]:
        """Reload one or all configured MCP servers in the active runtime."""
        started_at = perf_counter()
        target = server_name or "all"
        try:
            async with self._lock:
                runtime = self._runtime
                if runtime is None:
                    raise RuntimeNotStartedError("runtime is not started")
                if self._active_runs:
                    raise RuntimeBusyError("runtime has active runs")
                if server_name is None:
                    registered = await runtime.tools.reload_mcp()
                else:
                    registered = await runtime.tools.reload_mcp_server(
                        server_name
                    )
        except (RuntimeBusyError, ValueError):
            raise
        except Exception as exc:
            logger.warning(
                "[mcp] reload failed | server=%s | error_type=%s | duration=%s",
                safe_log_value(target),
                type(exc).__name__,
                elapsed_since(started_at),
            )
            raise MCPConnectionError(
                "刷新 MCP 服务失败，请检查服务状态后重试"
            ) from exc
        logger.info(
            "[mcp] reload completed | server=%s | tools=%d | duration=%s",
            safe_log_value(target),
            len(registered),
            elapsed_since(started_at),
        )
        return registered

    async def install_skills(
        self,
        sources: list[Path],
        *,
        replace: bool = False,
    ) -> SkillLoadResult:
        """Install uploaded skills when the runtime is idle."""
        async with self._lock:
            runtime = self._runtime
            if runtime is None:
                raise RuntimeNotStartedError("runtime is not started")
            if self._active_runs:
                raise RuntimeBusyError("runtime has active runs")
            return await asyncio.to_thread(
                runtime.skills.install_skills,
                sources,
                replace=replace,
            )

    async def remove_skill(self, name: str) -> SkillLoadResult:
        """Remove one installed skill when the runtime is idle."""
        async with self._lock:
            runtime = self._runtime
            if runtime is None:
                raise RuntimeNotStartedError("runtime is not started")
            if self._active_runs:
                raise RuntimeBusyError("runtime has active runs")
            return await asyncio.to_thread(runtime.skills.remove_skill, name)

    async def reload_skills(self) -> SkillLoadResult:
        """Rescan installed skills when the runtime is idle."""
        async with self._lock:
            runtime = self._runtime
            if runtime is None:
                raise RuntimeNotStartedError("runtime is not started")
            if self._active_runs:
                raise RuntimeBusyError("runtime has active runs")
            return await asyncio.to_thread(runtime.skills.reload)

    def public_config(self) -> dict[str, Any]:
        data = self.config.to_dict()
        provider = data["provider"]
        api_key = provider.pop("api_key", None)
        provider["api_key_configured"] = bool(api_key)
        data["mcp_servers"] = [
            {
                "name": server.name,
                "url": server.url,
                "headers": {str(name): "" for name in server.headers},
            }
            for server in self.config.mcp_servers
        ]
        data.setdefault("agent", {})
        runtime = data.setdefault("runtime", {})
        runtime["workspace"] = str(self.workspace)
        return data

    def settings_options(self) -> dict[str, Any]:
        """Return runtime-discovered choices used by the settings UI."""
        runtime = self._runtime
        if runtime is None:
            raise RuntimeNotStartedError("runtime is not started")

        result = runtime.skills.list_skills()
        skills = [
            {
                "name": skill.name,
                "description": skill.description,
            }
            for skill in result.skills
        ]
        skill_errors = [
            {
                "path": str(error.path),
                "message": error.message,
            }
            for error in result.errors
        ]
        tools = [
            {
                "name": tool.name,
                "description": tool.description,
                "source": tool.source,
                "parallel_safe": tool.parallel_safe,
            }
            for tool in runtime.tools.list_tools()
        ]
        mcp_statuses = [
            {
                "name": status.name,
                "connected": status.connected,
                "registered_tools": status.registered_tools,
            }
            for status in runtime.tools.list_mcp_server_statuses()
        ]

        return {
            "skills": skills,
            "skill_errors": skill_errors,
            "tools": tools,
            "mcp_statuses": mcp_statuses,
        }

    def _load_config(self) -> BumblehiveConfig:
        if not self.config_path.exists():
            return BumblehiveConfig.from_mapping(apply_config_defaults({}))
        loaded = BumblehiveConfig.from_json_file(self.config_path)
        return BumblehiveConfig.from_mapping(
            apply_config_defaults(loaded.to_dict())
        )

    async def _create_ready_runtime(
        self,
        config: BumblehiveConfig,
    ) -> BumblehiveRuntime:
        runtime = self._runtime_factory(config)
        try:
            await runtime.initialize_tools()
            register_subagent_tool(runtime, self._session_reader)
        except BaseException:
            await runtime.close()
            raise
        return runtime

    def _write_config(self, config: BumblehiveConfig) -> None:
        self.config_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        temporary = self.config_path.with_name(
            f".{self.config_path.name}.{uuid4().hex}.tmp"
        )
        try:
            with temporary.open("x", encoding="utf-8") as file:
                try:
                    os.chmod(temporary, 0o600)
                except OSError:
                    pass
                json.dump(asdict(config), file, ensure_ascii=False, indent=2)
                file.write("\n")
            os.replace(temporary, self.config_path)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise


def _deep_merge(
    base: Mapping[str, Any],
    overlay: Mapping[str, Any],
) -> dict[str, Any]:
    merged = dict(base)
    for key, value in overlay.items():
        current = merged.get(key)
        if isinstance(current, Mapping) and isinstance(value, Mapping):
            merged[key] = _deep_merge(current, value)
        else:
            merged[key] = value
    return merged


def _restore_masked_mcp_headers(
    current: Mapping[str, Any],
    patch: Mapping[str, Any],
) -> dict[str, Any]:
    """Preserve unchanged MCP header secrets represented by empty UI values."""
    incoming_servers = patch.get("mcp_servers")
    if not isinstance(incoming_servers, list):
        return dict(patch)

    current_servers = current.get("mcp_servers")
    current_by_name = {
        str(server.get("name")): server
        for server in (
            current_servers
            if isinstance(current_servers, list)
            else []
        )
        if isinstance(server, Mapping) and server.get("name")
    }

    current_server_list = (
        current_servers
        if isinstance(current_servers, list)
        else []
    )
    resolved_servers: list[Any] = []
    for index, incoming in enumerate(incoming_servers):
        if not isinstance(incoming, Mapping):
            resolved_servers.append(incoming)
            continue

        server = dict(incoming)
        headers = server.get("headers")
        current_server = current_by_name.get(str(server.get("name")))
        if (
            current_server is None
            and index < len(current_server_list)
            and isinstance(current_server_list[index], Mapping)
        ):
            current_server = current_server_list[index]
        current_headers = (
            current_server.get("headers", {})
            if isinstance(current_server, Mapping)
            else {}
        )
        if isinstance(headers, Mapping) and isinstance(current_headers, Mapping):
            server["headers"] = {
                str(name): (
                    current_headers[name]
                    if value == "" and name in current_headers
                    else value
                )
                for name, value in headers.items()
            }
        resolved_servers.append(server)

    resolved = dict(patch)
    resolved["mcp_servers"] = resolved_servers
    return resolved


def _mcp_test_config(
    current: Mapping[str, Any],
    incoming: Mapping[str, Any],
    *,
    original_name: str | None,
) -> MCPServerConfig:
    name = _text_or_none(incoming.get("name"))
    if name is None:
        raise ValueError("MCP 服务名称不能为空")
    url = _text_or_none(incoming.get("url"))
    if url is None:
        raise ValueError("MCP 服务 URL 不能为空")

    raw_headers = incoming.get("headers") or {}
    if not isinstance(raw_headers, Mapping):
        raise TypeError("MCP Headers 必须是对象")

    current_servers = current.get("mcp_servers")
    saved_servers = (
        current_servers
        if isinstance(current_servers, list)
        else []
    )
    saved_name = _text_or_none(original_name) or name
    saved_server = next(
        (
            item
            for item in saved_servers
            if isinstance(item, Mapping)
            and str(item.get("name")) == saved_name
        ),
        None,
    )
    saved_headers = (
        saved_server.get("headers", {})
        if isinstance(saved_server, Mapping)
        else {}
    )
    resolved_headers: dict[str, str] = {}
    for raw_name, raw_value in raw_headers.items():
        header_name = str(raw_name).strip()
        if not header_name:
            raise ValueError("Header 名称不能为空")
        value = str(raw_value)
        if value == "" and isinstance(saved_headers, Mapping):
            if header_name in saved_headers:
                value = str(saved_headers[header_name])
            else:
                raise ValueError(f"Header“{header_name}”缺少值")
        resolved_headers[header_name] = value

    return MCPServerConfig(
        name=name,
        url=url,
        headers=resolved_headers,
    )


def _text_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_base_url(value: str) -> str:
    text = _text_or_none(value)
    if text is None:
        raise ValueError("Base URL is required")
    parsed = urlsplit(text)
    if (
        parsed.scheme.lower() not in {"http", "https"}
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("Base URL must be a valid HTTP(S) URL")
    path = parsed.path.rstrip("/")
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), path, "", ""))


def _model_ids(response: Any) -> list[str]:
    raw_models = getattr(response, "data", response)
    models: list[str] = []
    seen: set[str] = set()
    for raw_model in raw_models:
        model_id = (
            raw_model.get("id")
            if isinstance(raw_model, Mapping)
            else getattr(raw_model, "id", None)
        )
        cleaned = _text_or_none(model_id)
        if cleaned is None or cleaned in seen:
            continue
        seen.add(cleaned)
        models.append(cleaned)
    return models
