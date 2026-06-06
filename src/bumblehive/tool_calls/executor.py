from jsonschema.exceptions import ValidationError

from ..schemas.errors import AgentError
from ..schemas.tool_calls import ToolCall, ToolResult
from ..tools.registry import ToolRegistry


class ToolExecutor:
    """Execute parsed tool calls through a registry."""

    def __init__(self, registry: ToolRegistry) -> None:
        self.registry = registry

    async def execute_call(self, call: ToolCall) -> ToolResult:
        """Execute a parsed tool call and return a structured result."""
        tool = self.registry.get_tool(call.name)
        if tool is None:
            available = ", ".join(self.registry.tool_names) or "(none)"
            return ToolResult(
                call_id=call.id,
                name=call.name,
                error=AgentError(
                    code="tool_not_found",
                    message=f"Tool '{call.name}' not found. Available tools: {available}",
                ),
            )

        try:
            tool.validate_arguments(call.arguments)
            content = await tool.execute(**call.arguments)
        except ValidationError as exc:
            return ToolResult(
                call_id=call.id,
                name=call.name,
                error=AgentError(
                    code="invalid_tool_arguments",
                    message=f"Invalid arguments for tool '{call.name}': {exc}",
                ),
            )

        return ToolResult(call_id=call.id, name=call.name, content=content)
