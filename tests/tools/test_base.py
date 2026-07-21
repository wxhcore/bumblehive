import pytest
from jsonschema.exceptions import ValidationError

from bumblehive.tools import CallableTool


def test_tool_prepares_nested_schema_arguments_before_validation() -> None:
    tool = CallableTool(
        name="configure",
        description="Configure a job.",
        parameters={
            "type": "object",
            "properties": {
                "retries": {"type": "integer"},
                "threshold": {"type": "number"},
                "enabled": {"type": "boolean"},
                "label": {"type": ["string", "null"]},
                "steps": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "weight": {"type": "number"},
                            "active": {"type": "boolean"},
                        },
                        "required": ["weight", "active"],
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["retries", "threshold", "enabled", "label", "steps"],
            "additionalProperties": False,
        },
        handler=lambda **kwargs: kwargs,
    )

    prepared = tool.prepare_arguments(
        {
            "retries": "3",
            "threshold": "0.75",
            "enabled": "yes",
            "label": None,
            "steps": [{"weight": "2.5", "active": "false"}],
        }
    )

    assert prepared == {
        "retries": 3,
        "threshold": 0.75,
        "enabled": True,
        "label": None,
        "steps": [{"weight": 2.5, "active": False}],
    }

    with pytest.raises(ValidationError):
        tool.prepare_arguments(
            {
                **prepared,
                "steps": [{"weight": "not-a-number", "active": True}],
            }
        )
