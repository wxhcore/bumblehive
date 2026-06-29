import asyncio
from pathlib import Path

from ..contracts.errors import AgentError
from .calls import ToolCall, ToolResult
from .scope import (
    bind_tool_workspace,
    reset_tool_workspace,
)
from .registry import ToolRegistry


class ToolExecutor:
    """Execute parsed tool calls through a registry."""

    def __init__(
        self,
        registry: ToolRegistry,
    ) -> None:
        self.registry = registry

    async def execute_call(
        self,
        call: ToolCall,
        *,
        allowed_tool_names: list[str] | None = None,
        workspace: Path | str | None = None,
    ) -> ToolResult:
        """Execute a parsed tool call and return a structured result."""
        allowed = None if allowed_tool_names is None else frozenset(allowed_tool_names)
        if (
            allowed is not None
            and call.name not in allowed
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
            token = bind_tool_workspace(workspace)
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
                reset_tool_workspace(token)

        return ToolResult(call_id=call.id, name=call.name, content=content)

    async def execute_many(
        self,
        calls: list[ToolCall],
        *,
        allowed_tool_names: list[str] | None = None,
        workspace: Path | str | None = None,
    ) -> list[ToolResult]:
        """Execute tool calls, parallelizing adjacent concurrency-safe tools."""
        results: list[ToolResult] = []
        for batch in self._partition_calls(calls):
            if len(batch) == 1:
                results.append(
                    await self.execute_call(
                        batch[0],
                        allowed_tool_names=allowed_tool_names,
                        workspace=workspace,
                    )
                )
                continue

            results.extend(
                await asyncio.gather(
                    *(
                        self.execute_call(
                            call,
                            allowed_tool_names=allowed_tool_names,
                            workspace=workspace,
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
