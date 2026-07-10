import asyncio

from .base import ModelProvider
from .openai_chat_completions import OpenAIChatCompletionsProvider


ProviderKey = tuple[str | None, str | None]


class ProviderManager:
    """Runtime-scoped cache of providers by connection settings.

    Providers with different API keys or base URLs may be used concurrently.
    Cached providers remain open until the manager is closed.
    """

    def __init__(self) -> None:
        self._providers: dict[ProviderKey, ModelProvider] = {}
        self._lock = asyncio.Lock()

    async def get(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> ModelProvider:
        async with self._lock:
            key = (api_key, base_url)
            provider = self._providers.get(key)
            if provider is not None:
                return provider

            provider = self._create_provider(
                api_key=api_key,
                base_url=base_url,
            )
            self._providers[key] = provider
            return provider

    async def close(self) -> None:
        """Close and forget every cached provider."""
        async with self._lock:
            providers = list(self._providers.values())
            self._providers.clear()
            await asyncio.gather(*(provider.close() for provider in providers))

    @staticmethod
    def _create_provider(
        *,
        api_key: str | None,
        base_url: str | None,
    ) -> ModelProvider:
        return OpenAIChatCompletionsProvider(
            api_key=api_key,
            base_url=base_url,
        )
