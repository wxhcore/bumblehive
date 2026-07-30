from collections.abc import Mapping
from typing import Any


DEFAULT_CONFIG_VALUES: dict[str, dict[str, Any]] = {
    "provider": {
        "type": "openai_chat_completions",
    },
    "generation": {
        "max_completion_tokens": 16_384,
    },
    "runtime": {
        "context_window_tokens": 200_000,
        "max_tool_result_chars": 20_000,
        "max_iterations": 300,
    },
}


def apply_config_defaults(config: Mapping[str, Any]) -> dict[str, Any]:
    """Fill effective SDK defaults without changing the SDK configuration API."""
    resolved = dict(config)
    for section_name, defaults in DEFAULT_CONFIG_VALUES.items():
        section = dict(resolved.get(section_name) or {})
        for name, value in defaults.items():
            if section.get(name) is None:
                section[name] = value
        resolved[section_name] = section
    return resolved
