import json

import pytest

from bumblehive.config.loader import load_config
from bumblehive.config.schema import BumblehiveConfig, RuntimeArguments


def test_load_config_normalizes_supported_inputs(tmp_path) -> None:
    path = tmp_path / "bumblehive.json"
    path.write_text(json.dumps({"provider": {"model": "file-model"}}), encoding="utf-8")
    existing = BumblehiveConfig.from_mapping({"provider": {"model": "object-model"}})
    mapping = load_config({"provider": {"model": "mapping-model"}})

    assert load_config().provider.model is None
    assert mapping.generation.max_completion_tokens is None
    assert "max_completion_tokens" not in mapping.to_dict()["generation"]
    assert load_config(existing) is existing
    assert mapping.provider.model == "mapping-model"
    assert load_config(RuntimeArguments(model="arguments-model")).provider.model == "arguments-model"
    assert load_config(path).provider.model == "file-model"


def test_json_config_round_trip_and_file_validation(tmp_path) -> None:
    config = BumblehiveConfig.from_mapping({"provider": {"model": "demo-model"}})
    path = tmp_path / "bumblehive.json"

    config.to_json_file(path)

    assert BumblehiveConfig.from_json_file(path) == config
    assert path.read_text(encoding="utf-8").endswith("\n")

    with pytest.raises(ValueError, match="must be JSON"):
        config.to_json_file(tmp_path / "config.yaml")

    invalid = tmp_path / "invalid.json"
    invalid.write_text("[]", encoding="utf-8")
    with pytest.raises(TypeError, match="must contain an object"):
        load_config(invalid)
