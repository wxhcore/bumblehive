import asyncio
import inspect
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from jsonschema import validate


@dataclass(frozen=True)
class FunctionTool:
    """A Python function exposed as an LLM-callable tool."""

    name: str
    description: str
    parameters: dict[str, Any]
    handler: Callable[..., Any]

    def validate_arguments(self, arguments: dict[str, Any]) -> None:
        """Validate arguments against the tool JSON Schema."""
        validate(instance=arguments, schema=self.parameters)

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
