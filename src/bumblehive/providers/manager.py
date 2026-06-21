from .config import ProviderConfig
from .base import ModelProvider
from .openai_chat_completions import OpenAIChatCompletionsProvider


class ProviderManager:
    """Single-runtime cache for one active provider.

    Reuses the provider while connection settings stay unchanged. When the API
    key or base URL changes, the previous provider is closed before a new one is
    created.
    """

    def __init__(self) -> None:
        self._config: ProviderConfig | None = None
        self._provider: ModelProvider | None = None

    async def get(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> ModelProvider:
        config = ProviderConfig(
            api_key=api_key,
            base_url=base_url,
        )

        if self._provider is not None and config == self._config:
            return self._provider

        await self._discard_current_provider()
        self._provider = self._create_provider(config)
        self._config = config
        return self._provider

    async def close(self) -> None:
        """Close and forget the currently cached provider."""
        await self._discard_current_provider()

    async def _discard_current_provider(self) -> None:
        """Remove the cached provider and release its resources."""
        provider = self._provider
        self._provider = None
        self._config = None
        if provider is not None:
            await provider.close()

    @staticmethod
    def _create_provider(config: ProviderConfig) -> ModelProvider:
        return OpenAIChatCompletionsProvider(
            api_key=config.api_key,
            base_url=config.base_url,
        )
