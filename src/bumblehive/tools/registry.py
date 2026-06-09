from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

from fastmcp.tools.function_parsing import ParsedFunction
from jsonschema.exceptions import ValidationError

from .base import Tool
from .adapters.function import CallableTool


def _resolve_tool_definition(
    func: Callable[..., Any],
    *,
    name: str | None,
    description: str | None,
    parameters: dict[str, Any] | None,
) -> tuple[str, str, dict[str, Any]]:
    if name is None or description is None or parameters is None:
        parsed = ParsedFunction.from_function(func)
        return (
            name if name is not None else parsed.name,
            description if description is not None else parsed.description or "",
            parameters if parameters is not None else parsed.input_schema,
        )

    return name, description, parameters


@dataclass(frozen=True)
class PreparedToolCall:
    """A resolved tool call with arguments ready for execution."""

    tool: Tool | None
    arguments: dict[str, Any]
    error_code: str | None = None
    error_message: str | None = None

    @property
    def is_error(self) -> bool:
        return self.error_code is not None


class ToolRegistry:
    """Registry used by the agent loop to expose and execute tools."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> Tool:
        if tool.name in self._tools:
            raise ValueError(f"Tool already registered: {tool.name}")
        self._tools[tool.name] = tool
        return tool

    def unregister(self, name: str) -> None:
        """Remove a registered tool by name if it exists."""
        self._tools.pop(name, None)

    def prepare_call(self, name: str, arguments: dict[str, Any]) -> PreparedToolCall:
        """Resolve a tool call and prepare its arguments for execution."""
        tool = self.get_tool(name)
        if tool is None:
            available = ", ".join(self.tool_names) or "(none)"
            return PreparedToolCall(
                tool=None,
                arguments=arguments,
                error_code="tool_not_found",
                error_message=f"Tool '{name}' not found. Available tools: {available}",
            )

        try:
            prepared_arguments = tool.prepare_arguments(arguments)
        except ValidationError as exc:
            return PreparedToolCall(
                tool=tool,
                arguments=arguments,
                error_code="invalid_tool_arguments",
                error_message=f"Invalid arguments for tool '{name}': {exc}",
            )
        except Exception as exc:
            return PreparedToolCall(
                tool=tool,
                arguments=arguments,
                error_code="tool_prepare_error",
                error_message=f"Error preparing tool '{name}': {exc}",
            )

        return PreparedToolCall(tool=tool, arguments=prepared_arguments)

    def tool(
        self,
        fn_or_name: Callable[..., Any] | str | None = None,
        *,
        name: str | None = None,
        description: str | None = None,
        parameters: dict[str, Any] | None = None,
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]] | Callable[..., Any]:
        """Register a function as a tool."""
        func: Callable[..., Any] | None
        if isinstance(fn_or_name, str):
            name = name or fn_or_name
            func = None
        elif callable(fn_or_name):
            func = fn_or_name
        else:
            func = None

        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            tool_name, tool_description, tool_parameters = _resolve_tool_definition(
                func,
                name=name,
                description=description,
                parameters=parameters,
            )
            self.register(
                CallableTool(
                    name=tool_name,
                    description=tool_description,
                    parameters=tool_parameters,
                    handler=func,
                )
            )
            return func

        if func is not None:
            return decorator(func)
        return decorator

    def get_tool(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def list_tools(self, tool_names: Iterable[str] | None = None) -> list[Tool]:
        """Return registered tools, optionally filtered by name."""
        names = self.tool_names if tool_names is None else sorted(set(tool_names))
        missing = [name for name in names if name not in self._tools]
        if missing:
            raise ValueError(f"Unknown tools: {', '.join(missing)}")

        return [self._tools[name] for name in names]

    @property
    def tool_names(self) -> list[str]:
        return sorted(self._tools)

    def get_openai_tool_definitions(
        self,
        tool_names: Iterable[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Return OpenAI-compatible tool definitions for the model request."""
        return [tool.to_openai_tool_schema() for tool in self.list_tools(tool_names)]
