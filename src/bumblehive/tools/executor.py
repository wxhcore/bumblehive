import asyncio
import time
from pathlib import Path

from ..protocols.errors import AgentError
from ..protocols.tool_calls import ToolCall, ToolResult
from ..observability import (
    TOOL_CALL_FINISHED,
    TOOL_CALL_STARTED,
    EventEmitter,
    tool_call_payload,
    tool_result_payload,
)
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
        emitter: EventEmitter | None = None,
    ) -> ToolResult:
        """Execute a parsed tool call and return a structured result."""
        emitter = emitter or EventEmitter.noop()
        await self._emit_tool_call_started(
            emitter,
            call=call,
        )

        started_at_ns = time.perf_counter_ns()
        result = await self._execute_call_core(
            call,
            allowed_tool_names=allowed_tool_names,
            workspace=workspace,
        )
        duration_s = (time.perf_counter_ns() - started_at_ns) / 1_000_000_000
        await self._emit_tool_call_finished(
            emitter,
            call=call,
            result=result,
            duration_s=duration_s,
        )
        return result

    async def _execute_call_core(
        self,
        call: ToolCall,
        *,
        allowed_tool_names: list[str] | None = None,
        workspace: Path | str | None = None,
    ) -> ToolResult:
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

        result: ToolResult | None = None
        token = None
        try:
            assert prepared.tool is not None
            token = bind_tool_workspace(workspace)
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
        finally:
            if token is not None:
                reset_tool_workspace(token)
        if result is None:
            result = ToolResult(call_id=call.id, name=call.name, content=content)
        return result

    async def execute_many(
        self,
        calls: list[ToolCall],
        *,
        allowed_tool_names: list[str] | None = None,
        workspace: Path | str | None = None,
        emitter: EventEmitter | None = None,
    ) -> list[ToolResult]:
        """Execute tool calls, parallelizing adjacent concurrency-safe tools."""
        emitter = emitter or EventEmitter.noop()
        results: list[ToolResult] = []
        for batch in self._partition_calls(calls):
            if len(batch) == 1:
                results.append(
                    await self.execute_call(
                        batch[0],
                        allowed_tool_names=allowed_tool_names,
                        workspace=workspace,
                        emitter=emitter,
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
                            emitter=emitter,
                        )
                        for call in batch
                    )
                )
            )
        return results

    @classmethod
    async def _emit_tool_call_started(
        cls,
        emitter: EventEmitter,
        *,
        call: ToolCall,
    ) -> None:
        await emitter.emit(
            TOOL_CALL_STARTED,
            **tool_call_payload(call),
        )

    @classmethod
    async def _emit_tool_call_finished(
        cls,
        emitter: EventEmitter,
        *,
        call: ToolCall,
        result: ToolResult,
        duration_s: float,
    ) -> None:
        await emitter.emit(
            TOOL_CALL_FINISHED,
            **tool_result_payload(result, call=call),
            duration_s=round(duration_s, 4),
        )

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
