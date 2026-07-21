import asyncio

import pytest

from bumblehive.observability import AsyncEventStream, AsyncEventStreamHook
from bumblehive.observability.events import make_event


@pytest.mark.asyncio
async def test_stream_delivers_events_then_exposes_the_background_result() -> None:
    async def run(hook: AsyncEventStreamHook) -> str:
        await hook.on_event(make_event("one", run_id="run"))
        await hook.on_event(make_event("two", run_id="run"))
        return "done"

    stream = AsyncEventStream(run)

    with pytest.raises(RuntimeError, match="must be consumed"):
        await stream.result()
    assert [event.kind async for event in stream] == ["one", "two"]
    assert await stream.result() == "done"
    assert await stream.result() == "done"


@pytest.mark.asyncio
async def test_stream_propagates_background_failures_to_iteration_and_result() -> None:
    async def run(hook: AsyncEventStreamHook) -> None:
        raise RuntimeError("boom")

    stream = AsyncEventStream(run)
    with pytest.raises(RuntimeError, match="boom"):
        async for _ in stream:
            pass
    with pytest.raises(RuntimeError, match="boom"):
        await stream.result()


@pytest.mark.asyncio
async def test_closing_a_stream_cancels_its_background_run() -> None:
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def run(hook: AsyncEventStreamHook) -> None:
        started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled.set()
            raise

    stream = AsyncEventStream(run)
    stream.__aiter__()
    await started.wait()
    await stream.aclose()

    assert cancelled.is_set()
    with pytest.raises(RuntimeError, match="closed before producing a result"):
        await stream.result()
