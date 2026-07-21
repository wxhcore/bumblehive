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
from uuid import uuid4

from bumblehive import BumblehiveConfig, BumblehiveRuntime

from .logging_utils import elapsed_since, safe_log_value


RuntimeFactory = Callable[[BumblehiveConfig], BumblehiveRuntime]
logger = logging.getLogger("uvicorn.error.bumblehive")


class RuntimeBusyError(RuntimeError):
    """Raised when settings are changed while a run is active."""


class RuntimeNotStartedError(RuntimeError):
    """Raised when the server runtime has not been started."""


class RuntimeService:
    def __init__(
        self,
        config_path: str | Path,
        *,
        runtime_factory: RuntimeFactory = BumblehiveRuntime.from_config,
    ) -> None:
        self.config_path = Path(config_path).expanduser()
        self._runtime_factory = runtime_factory
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
            self._runtime = self._runtime_factory(config)

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
            "[session] delete completed | session_id=%s | deleted=%s | "
            "duration=%s",
            safe_log_value(session_id),
            str(deleted).lower(),
            elapsed_since(started_at),
        )
        return deleted

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
                replacement = self._runtime_factory(config)
                self._write_config(config)
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
        return data

    def _load_config(self) -> BumblehiveConfig:
        if not self.config_path.exists():
            return BumblehiveConfig()
        return BumblehiveConfig.from_json_file(self.config_path)

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
