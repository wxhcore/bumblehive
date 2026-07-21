from typing import Any

import pytest

from bumblehive.providers import ProviderManager
from bumblehive.providers.base import ModelRequest, ModelResponse


class FakeProvider:
    instances: list["FakeProvider"] = []

    def __init__(
        self,
        *,
        api_key: str | None,
        base_url: str | None,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url
        self.closed = False
        self.instances.append(self)

    async def generate(self, request: ModelRequest) -> ModelResponse:
        return ModelResponse(content="ok")

    async def close(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_provider_manager_reuses_matching_provider(monkeypatch: Any) -> None:
    from bumblehive.providers import manager as manager_module

    FakeProvider.instances = []
    monkeypatch.setattr(
        manager_module,
        "OpenAIChatCompletionsProvider",
        FakeProvider,
    )
    providers = ProviderManager()

    first = await providers.get(
        api_key="key",
        base_url="https://example.test/v1",
    )
    second = await providers.get(
        api_key="key",
        base_url="https://example.test/v1",
    )

    assert first is second
    assert len(FakeProvider.instances) == 1
    assert not FakeProvider.instances[0].closed


@pytest.mark.asyncio
async def test_provider_manager_caches_changed_provider(monkeypatch: Any) -> None:
    from bumblehive.providers import manager as manager_module

    FakeProvider.instances = []
    monkeypatch.setattr(
        manager_module,
        "OpenAIChatCompletionsProvider",
        FakeProvider,
    )
    providers = ProviderManager()

    first = await providers.get(
        api_key="old-key",
        base_url="https://example.test/v1",
    )
    second = await providers.get(
        api_key="new-key",
        base_url="https://example.test/v1",
    )
    first_again = await providers.get(
        api_key="old-key",
        base_url="https://example.test/v1",
    )

    assert first is not second
    assert first_again is first
    assert len(FakeProvider.instances) == 2
    assert not FakeProvider.instances[0].closed
    assert not FakeProvider.instances[1].closed

    await providers.close()

    assert FakeProvider.instances[0].closed
    assert FakeProvider.instances[1].closed
