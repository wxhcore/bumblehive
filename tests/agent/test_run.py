import asyncio
import inspect

import pytest

from bumblehive.agent import AgentRun, AgentRunResult
from bumblehive.agent.control import _RunControl


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "schedule", ["await", "task", "gather", "wait_for", "task_group"]
)
async def test_run_is_lazy_and_supports_asyncio_scheduling(schedule) -> None:
    control = _RunControl()
    calls = []

    async def execute():
        calls.append("executed")
        return AgentRunResult("done", control._drain_all())

    run = AgentRun(execute(), control)
    run.steer("extra")
    assert not calls
    assert asyncio.iscoroutine(run)
    assert not inspect.iscoroutine(run)
    if schedule == "await":
        result = await run
    elif schedule == "task":
        result = await asyncio.create_task(run)
    elif schedule == "gather":
        (result,) = await asyncio.gather(run)
    elif schedule == "wait_for":
        result = await asyncio.wait_for(run, timeout=1)
    else:
        async with asyncio.TaskGroup() as group:
            task = group.create_task(run)
        result = task.result()
    assert result == AgentRunResult("done", [{"role": "user", "content": "extra"}])
    assert calls == ["executed"]
    with pytest.raises(RuntimeError):
        run.steer("late")
    with pytest.raises(RuntimeError, match="reuse"):
        await run
    assert calls == ["executed"]


@pytest.mark.asyncio
@pytest.mark.parametrize("scheduled", [False, True])
async def test_run_preserves_exceptions_and_closes_input(scheduled) -> None:
    error = ValueError("original")

    async def execute():
        raise error

    run = AgentRun(execute(), _RunControl())
    run.steer("unused")
    with pytest.raises(ValueError) as caught:
        await (asyncio.create_task(run) if scheduled else run)
    assert caught.value is error
    assert run.take_pending() == [{"role": "user", "content": "unused"}]
    with pytest.raises(RuntimeError):
        run.steer("late")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "termination", ["close", "cancel_before_start", "cancel", "timeout"]
)
async def test_run_cancellation_closes_input_and_runs_cleanup(termination) -> None:
    started = asyncio.Event()
    cleaned = asyncio.Event()
    lock = asyncio.Lock()

    async def execute():
        async with lock:
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                cleaned.set()

    run = AgentRun(execute(), _RunControl())
    run.steer("unused")
    if termination == "close":
        run.close()
        assert not started.is_set()
    elif termination == "cancel_before_start":
        task = asyncio.create_task(run)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert not started.is_set()
    else:
        if termination == "cancel":
            task = asyncio.create_task(run)
        else:
            task = asyncio.create_task(asyncio.wait_for(run, timeout=0.05))
        await asyncio.wait_for(started.wait(), timeout=1)
        # A suspended coroutine must still accept input.
        run.steer("while running")
        if termination == "cancel":
            task.cancel()
        with pytest.raises(
            asyncio.CancelledError if termination == "cancel" else TimeoutError
        ):
            await task
        assert cleaned.is_set()
    assert not lock.locked()
    with pytest.raises(RuntimeError):
        run.steer("late")
    assert run.take_pending()[0]["content"] == "unused"
