import json
from typing import Any

import pytest

from bumblehive import BumblehiveConfig, ProviderConfig
from bumblehive_server.runtime_service import RuntimeBusyError, RuntimeService


class FakeRuntime:
    def __init__(self, config: BumblehiveConfig) -> None:
        self.config = config
        self.closed = False

    async def close(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_runtime_service_starts_without_a_config_file(tmp_path) -> None:
    runtimes: list[FakeRuntime] = []

    def factory(config: BumblehiveConfig) -> Any:
        runtime = FakeRuntime(config)
        runtimes.append(runtime)
        return runtime

    service = RuntimeService(tmp_path / "missing.json", runtime_factory=factory)

    await service.startup()

    assert service.ready is True
    assert service.config.provider.model is None
    assert service.public_config()["provider"] == {
        "type": "openai_chat_completions",
        "api_key_configured": False,
    }

    await service.shutdown()
    assert runtimes[0].closed is True


@pytest.mark.asyncio
async def test_runtime_service_updates_config_without_exposing_api_key(tmp_path) -> None:
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

    async with service.lease():
        with pytest.raises(RuntimeBusyError):
            await service.update_config({"provider": {"model": "busy"}})

    await service.shutdown()
    assert runtimes[-1].closed is True
