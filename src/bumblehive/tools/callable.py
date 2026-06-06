import asyncio
import inspect
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from jsonschema.validators import validator_for


@dataclass(frozen=True)
class CallableTool:
    """A callable object exposed as an LLM-callable tool."""

    name: str
    description: str
    parameters: dict[str, Any]
    handler: Callable[..., Any]
    _validator: Any = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        validator_cls = validator_for(schema=self.parameters)
        validator_cls.check_schema(schema=self.parameters)
        object.__setattr__(self, "_validator", validator_cls(schema=self.parameters))

    def validate_arguments(self, arguments: dict[str, Any]) -> None:
        """Validate arguments against the tool JSON Schema."""
        self._validator.validate(arguments)

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

    async def execute(self, **kwargs: Any) -> Any:
        """Execute the wrapped function, supporting sync and async functions."""
        if inspect.iscoroutinefunction(self.handler):
            return await self.handler(**kwargs)

        return await asyncio.to_thread(self.handler, **kwargs)
