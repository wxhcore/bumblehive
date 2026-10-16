import asyncio

import pytest

from bumblehive.observability import AsyncEventStream
from bumblehive.observability.events import make_event
from bumblehive.observability.streaming import AsyncEventStreamHook


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


@pytest.mark.asyncio
@pytest.mark.parametrize("before_start", [False, True])
async def test_external_close_unblocks_waiting_consumer(before_start) -> None:
    started = asyncio.Event()

    async def run(hook):
        started.set()
        await asyncio.Event().wait()

    stream = AsyncEventStream(run, maxsize=1)
    iterator = aiter(stream)
    consumer = asyncio.create_task(anext(iterator))
    try:
        if not before_start:
            await started.wait()
        await stream.aclose()
        with pytest.raises(asyncio.CancelledError):
            async with asyncio.timeout(1):
                await consumer
    finally:
        consumer.cancel()
        await asyncio.gather(consumer, return_exceptions=True)
        await iterator.aclose()


@pytest.mark.asyncio
async def test_close_full_queue_discards_buffer_and_wakes_reader() -> None:
    full = asyncio.Event()

    async def run(hook):
        await hook.on_event(make_event("buffered", run_id="run"))
        full.set()
        await hook.on_event(make_event("blocked", run_id="run"))

    stream = AsyncEventStream(run, maxsize=1)
    iterator = aiter(stream)
    await full.wait()
    async with asyncio.timeout(1):
        await stream.aclose()
        with pytest.raises(asyncio.CancelledError):
            await anext(iterator)
    with pytest.raises(RuntimeError, match="closed before producing a result"):
        await stream.result()
