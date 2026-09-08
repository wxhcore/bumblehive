import asyncio
from dataclasses import dataclass, field
from typing import Any

import pytest

from bumblehive.protocols import ToolCall
from bumblehive.tools import CallableTool, Tool, ToolApprovalDecision, ToolRegistry
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


@pytest.mark.asyncio
async def test_executor_approves_prepared_arguments_without_sharing_mutations() -> None:
    registry = ToolRegistry()
    executed: list[dict[str, Any]] = []
    parameters = {
        "type": "object",
        "properties": {
            "value": {"type": "integer"},
            "nested": {
                "type": "object",
                "properties": {
                    "items": {
                        "type": "array",
                        "items": {"type": "string"},
                    }
                },
                "required": ["items"],
                "additionalProperties": False,
            },
        },
        "required": ["value", "nested"],
        "additionalProperties": False,
    }

    async def capture(*, value: int, nested: dict[str, Any]) -> str:
        executed.append({"value": value, "nested": nested})
        return "done"

    registry.register(
        CallableTool(
            name="capture",
            description="capture",
            parameters=parameters,
            handler=capture,
        )
    )

    async def approve(request):
        assert request.arguments["value"] == 2
        nested = request.arguments["nested"]
        assert isinstance(nested, dict)
        nested["items"].append("changed-in-handler")
        return ToolApprovalDecision.approve()

    result = await ToolExecutor(registry).execute_call(
        _call(
            "capture",
            "capture",
            {"value": "2", "nested": {"items": ["original"]}},
        ),
        approval_handler=approve,
    )

    assert result.content == "done"
    assert executed == [
        {"value": 2, "nested": {"items": ["original"]}}
    ]


@pytest.mark.asyncio
async def test_executor_returns_structured_approval_denial_and_error() -> None:
    registry = ToolRegistry()
    executions = 0

    @registry.tool
    def run() -> str:
        """Record one execution."""
        nonlocal executions
        executions += 1
        return "ran"

    async def reject(_request):
        return ToolApprovalDecision.reject("user rejected it")

    async def fail(_request):
        raise RuntimeError("approval service unavailable")

    executor = ToolExecutor(registry)
    denied = await executor.execute_call(
        _call("denied", "run"),
        approval_handler=reject,
    )
    failed = await executor.execute_call(
        _call("failed", "run"),
        approval_handler=fail,
    )

    assert executions == 0
    assert denied.error is not None
    assert denied.error.code == "tool_approval_denied"
    assert denied.error.message == "user rejected it"
    assert denied.error.recoverable is False
    assert failed.error is not None
    assert failed.error.code == "tool_approval_error"
    assert "approval service unavailable" in failed.error.message
    assert failed.error.recoverable is False


@pytest.mark.asyncio
async def test_executor_skips_approval_for_unprepared_calls() -> None:
    registry = ToolRegistry()
    approvals: list[str] = []

    @registry.tool
    def add(a: int, b: int) -> int:
        """Add two integers."""
        return a + b

    async def approve(request):
        approvals.append(request.call_id)
        return ToolApprovalDecision.approve()

    executor = ToolExecutor(registry)
    invalid = await executor.execute_call(
        _call("invalid", "add", {"a": "bad", "b": 1}),
        approval_handler=approve,
    )
    missing = await executor.execute_call(
        _call("missing", "missing"),
        approval_handler=approve,
    )

    assert invalid.error is not None
    assert invalid.error.code == "invalid_tool_arguments"
    assert missing.error is not None
    assert missing.error.code == "tool_not_found"
    assert approvals == []


@pytest.mark.asyncio
async def test_executor_propagates_cancellation_from_approval_handler() -> None:
    registry = ToolRegistry()
    executed = False

    @registry.tool
    def run() -> str:
        """Return a value."""
        nonlocal executed
        executed = True
        return "ran"

    async def cancel(_request):
        raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await ToolExecutor(registry).execute_call(
            _call("cancelled", "run"),
            approval_handler=cancel,
        )

    assert executed is False


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
async def test_execute_many_runs_calls_sequentially_by_default() -> None:
    state = {"active": 0, "max_active": 0, "started": [], "finished": []}
    registry = ToolRegistry()
    parameters = {"type": "object", "properties": {}, "additionalProperties": False}
    for name in ("first", "second"):
        registry.register(
            RecordingTool(
                name=name,
                description=name,
                parameters=parameters,
                state=state,
            )
        )

    await ToolExecutor(registry).execute_many(
        [_call("1", "first"), _call("2", "second")]
    )

    assert state["max_active"] == 1


@pytest.mark.asyncio
async def test_execute_many_batches_parallel_safe_calls_around_sequential_calls() -> None:
    state = {"active": 0, "max_active": 0, "started": [], "finished": []}
    registry = ToolRegistry()
    parameters = {"type": "object", "properties": {}, "additionalProperties": False}
    for name, parallel_safe in (
        ("read-a", True),
        ("read-b", True),
        ("write", False),
    ):
        registry.register(
            RecordingTool(
                name=name,
                description=name,
                parameters=parameters,
                parallel_safe=parallel_safe,
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


@pytest.mark.asyncio
async def test_parallel_approvals_execute_immediately_before_next_batch() -> None:
    registry = ToolRegistry()
    parameters = {
        "type": "object",
        "properties": {"value": {"type": "string"}},
        "required": ["value"],
        "additionalProperties": False,
    }
    approval_entered = {name: asyncio.Event() for name in ("A", "B", "C")}
    approval_released = {name: asyncio.Event() for name in ("A", "B", "C")}
    body_started = {name: asyncio.Event() for name in ("A", "B", "C")}
    body_released = {name: asyncio.Event() for name in ("A", "B", "C")}

    async def gated_tool(*, value: str) -> str:
        body_started[value].set()
        await body_released[value].wait()
        return value

    for name, parallel_safe in (("tool_a", True), ("tool_b", True), ("tool_c", False)):
        registry.register(
            CallableTool(
                name=name,
                description=name,
                parameters=parameters,
                handler=gated_tool,
                parallel_safe=parallel_safe,
            )
        )

    async def approve(request):
        value = request.arguments["value"]
        approval_entered[value].set()
        await approval_released[value].wait()
        return ToolApprovalDecision.approve()

    task = asyncio.create_task(
        ToolExecutor(registry).execute_many(
            [
                _call("a", "tool_a", {"value": "A"}),
                _call("b", "tool_b", {"value": "B"}),
                _call("c", "tool_c", {"value": "C"}),
            ],
            approval_handler=approve,
        )
    )

    await asyncio.wait_for(
        asyncio.gather(
            approval_entered["A"].wait(),
            approval_entered["B"].wait(),
        ),
        timeout=1,
    )
    assert approval_entered["C"].is_set() is False

    approval_released["A"].set()
    await asyncio.wait_for(body_started["A"].wait(), timeout=1)
    assert body_started["B"].is_set() is False

    approval_released["B"].set()
    await asyncio.wait_for(body_started["B"].wait(), timeout=1)
    assert approval_entered["C"].is_set() is False

    body_released["A"].set()
    body_released["B"].set()
    await asyncio.wait_for(approval_entered["C"].wait(), timeout=1)

    body_released["C"].set()
    approval_released["C"].set()
    results = await asyncio.wait_for(task, timeout=1)

    assert [result.content for result in results] == ["A", "B", "C"]
