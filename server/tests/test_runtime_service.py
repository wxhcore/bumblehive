import json
import logging
from typing import Any

import pytest

from bumblehive import BumblehiveConfig, ProviderConfig
from bumblehive_server.runtime_service import RuntimeBusyError, RuntimeService


class FakeRuntime:
    def __init__(self, config: BumblehiveConfig) -> None:
        self.config = config
        self.closed = False
        self.deleted_sessions: list[str] = []
        self.model_list_requests: list[dict[str, str | None]] = []

    async def close(self) -> None:
        self.closed = True

    async def delete_session(self, session_id: str) -> bool:
        self.deleted_sessions.append(session_id)
        return True

    async def list_models(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> list[str]:
        self.model_list_requests.append(
            {"api_key": api_key, "base_url": base_url}
        )
        return ["listed-model", "other-model"]


@pytest.mark.asyncio
async def test_runtime_service_starts_without_a_config_file(
    tmp_path,
    caplog,
) -> None:
    runtimes: list[FakeRuntime] = []

    def factory(config: BumblehiveConfig) -> Any:
        runtime = FakeRuntime(config)
        runtimes.append(runtime)
        return runtime

    service = RuntimeService(tmp_path / "missing.json", runtime_factory=factory)

    with caplog.at_level(logging.INFO, logger="uvicorn.error.bumblehive"):
        await service.startup()
        deleted = await service.delete_session("session-1")

    assert service.ready is True
    assert deleted is True
    assert service.config.provider.model is None
    assert service.public_config()["provider"] == {
        "type": "openai_chat_completions",
        "api_key_configured": False,
    }
    assert "[config] loaded | source=defaults | duration=" in caplog.text
    assert (
        "[session] delete completed | session_id=session-1 | deleted=true"
        in caplog.text
    )

    await service.shutdown()
    assert runtimes[0].closed is True


@pytest.mark.asyncio
async def test_runtime_service_updates_config_without_exposing_api_key(
    tmp_path,
    caplog,
) -> None:
    config_path = tmp_path / "config.json"
    BumblehiveConfig(
        provider=ProviderConfig(model="old-model", api_key="secret")
    ).to_json_file(config_path)
    runtimes: list[FakeRuntime] = []

    def factory(config: BumblehiveConfig) -> Any:
        runtime = FakeRuntime(config)
        runtimes.append(runtime)
        return runtime

    service = RuntimeService(config_path, runtime_factory=factory)
    with caplog.at_level(logging.INFO, logger="uvicorn.error.bumblehive"):
        await service.startup()

        public = service.public_config()
        assert "api_key" not in public["provider"]
        assert public["provider"]["api_key_configured"] is True

        await service.update_config({"provider": {"model": "new-model"}})
    saved = json.loads(config_path.read_text(encoding="utf-8"))
    assert saved == {
        "provider": {
            "type": "openai_chat_completions",
            "model": "new-model",
            "api_key": "secret",
            "base_url": None,
        },
        "generation": {
            "max_completion_tokens": None,
            "temperature": None,
            "reasoning_effort": None,
            "extra_body": None,
        },
        "agent": {
            "instructions": None,
            "dynamic_context": {},
            "skill_names": None,
            "tool_names": None,
        },
        "runtime": {
            "workspace": None,
            "timezone": None,
            "context_window_tokens": None,
            "max_tool_result_chars": None,
            "max_iterations": None,
            "extra_read_roots": [],
            "extra_write_roots": [],
        },
        "mcp_servers": [],
    }
    assert runtimes[0].closed is True

    with caplog.at_level(logging.INFO, logger="uvicorn.error.bumblehive"):
        async with service.lease():
            with pytest.raises(RuntimeBusyError):
                await service.update_config({"provider": {"model": "busy"}})

    assert "[config] loaded | source=file | duration=" in caplog.text
    assert "[config] update completed | duration=" in caplog.text
    assert "[config] update rejected | reason=active_run" in caplog.text
    assert "secret" not in caplog.text

    await service.shutdown()
    assert runtimes[-1].closed is True


@pytest.mark.asyncio
async def test_runtime_service_lists_models_with_unsaved_provider_settings(
    tmp_path,
) -> None:
    config_path = tmp_path / "config.json"
    BumblehiveConfig(
        provider=ProviderConfig(
            model="saved-model",
            api_key="saved-secret",
            base_url="https://saved.example/v1",
        )
    ).to_json_file(config_path)
    runtimes: list[FakeRuntime] = []

    def factory(config: BumblehiveConfig) -> Any:
        runtime = FakeRuntime(config)
        runtimes.append(runtime)
        return runtime

    service = RuntimeService(config_path, runtime_factory=factory)
    await service.startup()

    models = await service.list_models(
        {
            "api_key": "temporary-secret",
            "base_url": " https://draft.example/v1 ",
        }
    )

    assert models == ["listed-model", "other-model"]
    assert runtimes[0].model_list_requests == [
        {
            "api_key": "temporary-secret",
            "base_url": "https://draft.example/v1",
        }
    ]
    assert service.config.provider.api_key == "saved-secret"
    saved = json.loads(config_path.read_text(encoding="utf-8"))
    assert saved["provider"]["api_key"] == "saved-secret"
    assert saved["provider"]["base_url"] == "https://saved.example/v1"

    await service.shutdown()


@pytest.mark.asyncio
async def test_runtime_service_logs_config_load_failure(
    tmp_path,
    caplog,
) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text("{", encoding="utf-8")
    service = RuntimeService(config_path)

    with caplog.at_level(logging.INFO, logger="uvicorn.error.bumblehive"):
        with pytest.raises(json.JSONDecodeError):
            await service.startup()

    failure_records = [
        record
        for record in caplog.records
        if record.getMessage().startswith("[config] load failed")
    ]
    assert len(failure_records) == 1
    assert failure_records[0].exc_info is not None
