from dataclasses import dataclass, field


@dataclass(frozen=True)
class ProviderConfig:
    """Connection settings that determine which provider instance to reuse."""

    api_key: str | None = field(default=None, repr=False)
    base_url: str | None = None
