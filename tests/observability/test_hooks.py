import pytest

from bumblehive.observability import CallbackHook, EventRecorder
from bumblehive.observability.emitter import EventEmitter


@pytest.mark.asyncio
async def test_composite_hooks_preserve_order_and_isolate_default_failures() -> None:
    calls = []

    def first(event):
        calls.append(("first", event.kind))

    async def failing(event):
        calls.append(("failing", event.kind))
        raise RuntimeError("ignored")

    recorder = EventRecorder()
    emitter = EventEmitter.from_hooks([first, failing, recorder], run_id="run")

    await emitter.emit("demo", value=1)

    assert calls == [("first", "demo"), ("failing", "demo")]
    assert recorder.events[0].payload == {"value": 1}
    assert recorder.events[0].run_id == "run"


@pytest.mark.asyncio
async def test_reraising_hook_stops_event_delivery() -> None:
    recorder = EventRecorder()

    def fail(event):
        raise RuntimeError("stop")

    emitter = EventEmitter.from_hooks([CallbackHook(fail, reraise=True), recorder])
    with pytest.raises(RuntimeError, match="stop"):
        await emitter.emit("demo")

    assert recorder.events == []
