from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .schema import BumblehiveConfig


ConfigInput = str | Path | Mapping[str, Any] | BumblehiveConfig | None


def load_config(config: ConfigInput = None) -> BumblehiveConfig:
    """Normalize supported config inputs into a BumblehiveConfig."""
    if config is None:
        return BumblehiveConfig()

    if isinstance(config, BumblehiveConfig):
        return config

    if isinstance(config, Mapping):
        return BumblehiveConfig.from_mapping(config)

    return load_json_config(config)


def load_json_config(path: str | Path) -> BumblehiveConfig:
    """Load a BumblehiveConfig from a JSON file."""
    return BumblehiveConfig.from_json_file(path)
