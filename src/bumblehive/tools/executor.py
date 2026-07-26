import asyncio
import time
from collections.abc import Awaitable, Callable

from ..observability.emitter import EventEmitter
from ..observability.emitters import ToolEvents
from ..protocols.errors import AgentError
from ..protocols.tool_calls import ToolCall, ToolResult
from .file_changes import FileChangeTracker
from .registry import PreparedToolCall, ToolRegistry


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
        emitter: EventEmitter | None = None,
    ) -> ToolResult:
        """Execute a parsed tool call and return a structured result."""
        emitter = emitter or EventEmitter.noop()
        tool_events = ToolEvents(emitter)
        await tool_events.call_started(call)

        prepared = self.registry.prepare_call(call.name, call.arguments)
        tracker = (
            FileChangeTracker.prepare(call.name, prepared.arguments)
            if not prepared.is_error
            else FileChangeTracker()
        )
        started_at_ns = time.perf_counter_ns()
        result = await self._execute_call_core(call, prepared=prepared)
        duration_s = (time.perf_counter_ns() - started_at_ns) / 1_000_000_000
        await tool_events.call_finished(
            call=call,
            result=result,
            duration_s=duration_s,
            file_changes=tracker.finish(),
        )
        return result

    async def _execute_call_core(
        self,
        call: ToolCall,
        *,
        prepared: PreparedToolCall,
    ) -> ToolResult:
        if prepared.is_error:
            return ToolResult(
                call_id=call.id,
                name=call.name,
                error=AgentError(
                    code=prepared.error_code or "tool_prepare_error",
                    message=prepared.error_message or "Tool call could not be prepared.",
                ),
            )

        result: ToolResult | None = None
        try:
            assert prepared.tool is not None
            content = await prepared.tool.execute(**prepared.arguments)
        except Exception as exc:
            result = ToolResult(
                call_id=call.id,
                name=call.name,
                error=AgentError(
                    code="tool_execution_error",
                    message=f"Error executing tool '{call.name}': {exc}",
                ),
            )
        if result is None:
            result = ToolResult(call_id=call.id, name=call.name, content=content)
        return result

    async def execute_many(
        self,
        calls: list[ToolCall],
        *,
        call_runner: Callable[[ToolCall], Awaitable[ToolResult]] | None = None,
        emitter: EventEmitter | None = None,
    ) -> list[ToolResult]:
        """Execute calls in batches, optionally through a custom call runner."""
        emitter = emitter or EventEmitter.noop()

        async def default_runner(call: ToolCall) -> ToolResult:
            return await self.execute_call(call, emitter=emitter)

        runner = call_runner if call_runner is not None else default_runner

        results: list[ToolResult] = []
        for batch in self._partition_calls(calls):
            if len(batch) == 1:
                results.append(await runner(batch[0]))
                continue

            results.extend(
                await asyncio.gather(
                    *(runner(call) for call in batch)
                )
            )
        return results

    def _partition_calls(self, calls: list[ToolCall]) -> list[list[ToolCall]]:
        batches: list[list[ToolCall]] = []
        current: list[ToolCall] = []

        for call in calls:
            tool = self.registry.get_tool(call.name)
            can_batch = bool(tool and tool.parallel_safe)
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
