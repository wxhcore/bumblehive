from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Literal

from jsonschema.validators import validator_for

_JSON_SCHEMA_TYPE_MAP: dict[str, type | tuple[type, ...]] = {
    "string": str,
    "integer": int,
    "number": (int, float),
    "boolean": bool,
    "array": list,
    "object": dict,
}


@dataclass(frozen=True)
class Tool(ABC):
    """Base class for LLM-callable tools.

    Tools execute independently by default. Set ``parallel_safe=True`` only
    when the handler can safely overlap with other parallel-safe tool calls.
    """

    name: str
    description: str
    parameters: dict[str, Any]
    source: Literal["local", "mcp"] = field(default="local", kw_only=True)
    parallel_safe: bool = field(default=False, kw_only=True)
    _validator: Any = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self.source not in ("local", "mcp"):
            raise ValueError("Tool source must be 'local' or 'mcp'")
        validator_cls = validator_for(schema=self.parameters)
        validator_cls.check_schema(schema=self.parameters)
        object.__setattr__(self, "_validator", validator_cls(schema=self.parameters))

    @staticmethod
    def _resolve_type(schema_type: Any) -> str | None:
        """Pick the first non-null type from JSON Schema type unions."""
        if isinstance(schema_type, list):
            return next((item for item in schema_type if item != "null"), None)
        return schema_type

    def _cast_object(self, obj: Any, schema: dict[str, Any]) -> Any:
        if not isinstance(obj, dict):
            return obj

        properties = schema.get("properties", {})
        return {
            key: self._cast_value(value, properties[key]) if key in properties else value
            for key, value in obj.items()
        }

    def _cast_value(self, value: Any, schema: dict[str, Any]) -> Any:
        schema_type = self._resolve_type(schema.get("type"))

        if schema_type == "boolean" and isinstance(value, bool):
            return value
        if schema_type == "integer" and isinstance(value, int) and not isinstance(value, bool):
            return value
        if schema_type in _JSON_SCHEMA_TYPE_MAP and schema_type not in (
            "boolean",
            "integer",
            "array",
            "object",
        ):
            expected = _JSON_SCHEMA_TYPE_MAP[schema_type]
            if isinstance(value, expected):
                return value

        if isinstance(value, str) and schema_type in ("integer", "number"):
            try:
                return int(value) if schema_type == "integer" else float(value)
            except ValueError:
                return value

        if schema_type == "string":
            return value if value is None else str(value)

        if schema_type == "boolean" and isinstance(value, str):
            lowered = value.lower()
            if lowered in ("true", "1", "yes"):
                return True
            if lowered in ("false", "0", "no"):
                return False
            return value

        if schema_type == "array" and isinstance(value, list):
            items = schema.get("items")
            if isinstance(items, dict):
                return [self._cast_value(item, items) for item in value]
            return value

        if schema_type == "object" and isinstance(value, dict):
            return self._cast_object(value, schema)

        return value

    def cast_arguments(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Apply safe schema-driven casts before validation."""
        if self.parameters.get("type", "object") != "object":
            return arguments
        return self._cast_object(arguments, self.parameters)

    def validate_arguments(self, arguments: dict[str, Any]) -> None:
        """Validate arguments against the tool JSON Schema."""
        self._validator.validate(arguments)

    def prepare_arguments(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Cast and validate arguments before tool execution."""
        cast_arguments = self.cast_arguments(arguments)
        self.validate_arguments(cast_arguments)
        return cast_arguments

    def to_openai_tool_schema(self) -> dict[str, Any]:
        """Return the OpenAI-compatible tool schema."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    @abstractmethod
    async def execute(self, **kwargs: Any) -> Any:
        """Execute the tool."""
        ...
