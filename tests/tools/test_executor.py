import asyncio
from dataclasses import dataclass, field
from typing import Any

import pytest

from bumblehive.protocols import ToolCall
from bumblehive.tools import Tool, ToolRegistry
from bumblehive.tools.executor import ToolExecutor


def _call(call_id, name, arguments=None):
    return ToolCall(call_id, name, arguments or {})


@pytest.mark.asyncio
async def test_executor_returns_structured_results_for_all_call_outcomes() -> None:
    registry = ToolRegistry()

    @registry.tool
    def add(a: int, b: int) -> int:
        """Add two integers."""
        return a + b

    @registry.tool
    def explode() -> None:
        """Raise an error."""
        raise RuntimeError("boom")

    executor = ToolExecutor(registry)
    success, invalid, missing, failed = [
        await executor.execute_call(call)
        for call in [
            _call("success", "add", {"a": "2", "b": 5}),
            _call("invalid", "add", {"a": "not-an-int", "b": 5}),
            _call("missing", "missing"),
            _call("failed", "explode"),
        ]
    ]

    assert success.content == 7 and success.error is None
    assert invalid.error is not None and invalid.error.code == "invalid_tool_arguments"
    assert missing.error is not None and missing.error.code == "tool_not_found"
    assert failed.error is not None and failed.error.code == "tool_execution_error"
    assert "boom" in failed.error.message


@dataclass(frozen=True)
class RecordingTool(Tool):
    state: dict[str, Any] = field(compare=False)

    async def execute(self, **kwargs: Any) -> str:
        self.state["active"] += 1
        self.state["max_active"] = max(self.state["max_active"], self.state["active"])
        self.state["started"].append(self.name)
        await asyncio.sleep(0.01)
        self.state["active"] -= 1
        self.state["finished"].append(self.name)
        return self.name


@pytest.mark.asyncio
async def test_execute_many_batches_safe_reads_around_sequential_writes() -> None:
    state = {"active": 0, "max_active": 0, "started": [], "finished": []}
    registry = ToolRegistry()
    parameters = {"type": "object", "properties": {}, "additionalProperties": False}
    for name, read_only in (("read-a", True), ("read-b", True), ("write", False)):
        registry.register(
            RecordingTool(
                name=name,
                description=name,
                parameters=parameters,
                read_only=read_only,
                state=state,
            )
        )

    results = await ToolExecutor(registry).execute_many(
        [
            _call("1", "read-a"),
            _call("2", "read-b"),
            _call("3", "write"),
            _call("4", "read-a"),
        ]
    )

    assert [result.content for result in results] == ["read-a", "read-b", "write", "read-a"]
    assert state["max_active"] == 2
    assert state["started"].index("write") > state["finished"].index("read-a")
    assert state["started"][-1] == "read-a"
