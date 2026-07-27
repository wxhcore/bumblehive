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

from bumblehive import BumblehiveConfig, BumblehiveRuntime
from bumblehive.paths import get_workspace_path
from openai import AsyncOpenAI

from .logging_utils import elapsed_since, safe_log_value
from .session_reader import SessionReader
from .subagents import register_subagent_tool


RuntimeFactory = Callable[[BumblehiveConfig], BumblehiveRuntime]
OpenAIClientFactory = Callable[..., AsyncOpenAI]
logger = logging.getLogger("uvicorn.error.bumblehive")


class RuntimeBusyError(RuntimeError):
    """Raised when settings are changed while a run is active."""


class ModelListError(RuntimeError):
    """Raised when the provider cannot return a model list."""


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
    ) -> None:
        self.config_path = Path(config_path).expanduser()
        self._session_reader = session_reader
        self._runtime_factory = runtime_factory
        self._openai_client_factory = openai_client_factory or AsyncOpenAI
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

                merged = _deep_merge(current.config.to_dict(), patch)
                config = BumblehiveConfig.from_mapping(merged)
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

    def public_config(self) -> dict[str, Any]:
        data = self.config.to_dict()
        provider = data["provider"]
        api_key = provider.pop("api_key", None)
        provider["api_key_configured"] = bool(api_key)
        runtime = data.setdefault("runtime", {})
        runtime["workspace"] = str(self.workspace)
        return data

    def _load_config(self) -> BumblehiveConfig:
        if not self.config_path.exists():
            return BumblehiveConfig()
        return BumblehiveConfig.from_json_file(self.config_path)

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
