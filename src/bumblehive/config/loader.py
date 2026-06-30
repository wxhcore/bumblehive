from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .schema import BumblehiveConfig, RuntimeArguments


ConfigInput = (
    str
    | Path
    | Mapping[str, Any]
    | BumblehiveConfig
    | RuntimeArguments
    | None
)


def load_config(config: ConfigInput = None) -> BumblehiveConfig:
    """Normalize supported config inputs into a BumblehiveConfig."""
    if config is None:
        return BumblehiveConfig()

    if isinstance(config, BumblehiveConfig):
        return config

    if isinstance(config, RuntimeArguments):
        return config.to_config()

    if isinstance(config, Mapping):
        return BumblehiveConfig.from_mapping(config)

    return load_json_config(config)


def load_json_config(path: str | Path) -> BumblehiveConfig:
    """Load a BumblehiveConfig from a JSON file."""
    return BumblehiveConfig.from_json_file(path)
