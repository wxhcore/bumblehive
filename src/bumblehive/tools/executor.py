import asyncio
from collections.abc import Iterable

from ..agent.types import AgentError
from .calls import ToolCall, ToolResult
from .scope import (
    ToolScope,
    bind_tool_scope,
    reset_tool_scope,
)
from .registry import ToolRegistry


class ToolExecutor:
    """Execute parsed tool calls through a registry."""

    def __init__(
        self,
        registry: ToolRegistry,
        *,
        allowed_tool_names: Iterable[str] | None = None,
    ) -> None:
        self.registry = registry
        self.allowed_tool_names = (
            None if allowed_tool_names is None else frozenset(allowed_tool_names)
        )

    async def execute_call(
        self,
        call: ToolCall,
        *,
        scope: ToolScope | None = None,
    ) -> ToolResult:
        """Execute a parsed tool call and return a structured result."""
        if (
            self.allowed_tool_names is not None
            and call.name not in self.allowed_tool_names
        ):
            return ToolResult(
                call_id=call.id,
                name=call.name,
                error=AgentError(
                    code="tool_not_allowed",
                    message=f"Tool '{call.name}' was not exposed in this model request.",
                ),
            )

        prepared = self.registry.prepare_call(call.name, call.arguments)
        if prepared.is_error:
            return ToolResult(
                call_id=call.id,
                name=call.name,
                error=AgentError(
                    code=prepared.error_code or "tool_prepare_error",
                    message=prepared.error_message or "Tool call could not be prepared.",
                ),
            )

        token = None
        try:
            assert prepared.tool is not None
            if scope is not None:
                token = bind_tool_scope(scope)
            content = await prepared.tool.execute(**prepared.arguments)
        except Exception as exc:
            return ToolResult(
                call_id=call.id,
                name=call.name,
                error=AgentError(
                    code="tool_execution_error",
                    message=f"Error executing tool '{call.name}': {exc}",
                ),
            )
        finally:
            if token is not None:
                reset_tool_scope(token)

        return ToolResult(call_id=call.id, name=call.name, content=content)

    async def execute_many(
        self,
        calls: list[ToolCall],
        *,
        scope: ToolScope | None = None,
    ) -> list[ToolResult]:
        """Execute tool calls, parallelizing adjacent concurrency-safe tools."""
        results: list[ToolResult] = []
        for batch in self._partition_calls(calls):
            if len(batch) == 1:
                results.append(
                    await self.execute_call(
                        batch[0],
                        scope=scope,
                    )
                )
                continue

            results.extend(
                await asyncio.gather(
                    *(
                        self.execute_call(
                            call,
                            scope=scope,
                        )
                        for call in batch
                    )
                )
            )
        return results

    def _partition_calls(self, calls: list[ToolCall]) -> list[list[ToolCall]]:
        batches: list[list[ToolCall]] = []
        current: list[ToolCall] = []

        for call in calls:
            tool = self.registry.get_tool(call.name)
            can_batch = bool(tool and tool.concurrency_safe)
            if can_batch:
                current.append(call)
                continue

            if current:
                batches.append(current)
                current = []
            batches.append([call])

        if current:
            batches.append(current)
        return batches
