import asyncio

import pytest

from bumblehive.agent import AgentRunResult, AgentRunStream
from bumblehive.agent.control import _RunControl
from bumblehive.observability import AgentEvent


@pytest.mark.asyncio
async def test_stream_is_lazy_and_closes_before_buffer_is_consumed() -> None:
    control = _RunControl()
    executed = asyncio.Event()

    async def execute(hook):
        try:
            executed.set()
            await hook.on_event(AgentEvent("test", "run"))
            return AgentRunResult("done", control._drain_all())
        finally:
            control._close()

    stream = AgentRunStream(execute, control)
    stream.steer("extra")
    assert not executed.is_set()
    with pytest.raises(RuntimeError):
        await stream.result()
    iterator = aiter(stream)
    with pytest.raises(RuntimeError):
        aiter(stream)
    await asyncio.wait_for(executed.wait(), timeout=1)
    # The event is buffered, but execution has already closed input.
    with pytest.raises(RuntimeError):
        stream.steer("late")
    assert [event.kind async for event in iterator] == ["test"]
    assert (await stream.result()).messages == [{"role": "user", "content": "extra"}]
    await stream.aclose()
    assert stream.take_pending() == []


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ["unstarted", "scheduled", "backpressure"])
async def test_stream_close_covers_every_start_phase(phase) -> None:
    control = _RunControl()
    blocked = asyncio.Event()
    cleaned = asyncio.Event()

    async def execute(hook):
        try:
            await hook.on_event(AgentEvent("first", "run"))
            blocked.set()
            await hook.on_event(AgentEvent("second", "run"))
            pytest.fail("The second put should be blocked")
        finally:
            control._close()
            cleaned.set()

    stream = AgentRunStream(execute, control, maxsize=1)
    stream.steer("before")
    if phase != "unstarted":
        iterator = aiter(stream)
    if phase == "backpressure":
        await asyncio.wait_for(blocked.wait(), timeout=1)
        # Input is independent of the full output queue.
        stream.steer("during")
    # Direct await closes input before the scheduled producer can first run.
    async with asyncio.timeout(1):
        await stream.aclose()
    if phase == "backpressure":
        assert cleaned.is_set()
    else:
        assert not blocked.is_set()
    if phase != "unstarted":
        await iterator.aclose()
    with pytest.raises(RuntimeError):
        aiter(stream)
    with pytest.raises(RuntimeError):
        stream.steer("late")
    with pytest.raises(RuntimeError):
        await stream.result()
    assert [m["content"] for m in stream.take_pending()] == (
        ["before", "during"] if phase == "backpressure" else ["before"]
    )
