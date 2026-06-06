from collections.abc import Callable
from typing import Any

from fastmcp.tools.function_parsing import ParsedFunction

from .function import FunctionTool


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


class ToolRegistry:
    """Registry used by the agent loop to expose and execute tools."""

    def __init__(self) -> None:
        self._tools: dict[str, FunctionTool] = {}

    def register(self, tool: FunctionTool) -> FunctionTool:
        if tool.name in self._tools:
            raise ValueError(f"Tool already registered: {tool.name}")
        self._tools[tool.name] = tool
        return tool

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
                FunctionTool(
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

    def get_tool(self, name: str) -> FunctionTool | None:
        return self._tools.get(name)

    @property
    def tool_names(self) -> list[str]:
        return sorted(self._tools)

    def get_openai_tool_definitions(self) -> list[dict[str, Any]]:
        """Return OpenAI-compatible tool definitions for the model request."""
        return [self._tools[name].to_openai_tool_schema() for name in self.tool_names]
