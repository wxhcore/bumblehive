import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from bumblehive.observability.events import make_event
from bumblehive.agent.control import _RunControl
from bumblehive_server.chat.session import InputError, SessionController
from bumblehive_server.schemas import ChatRequest


class Stream:
    def __init__(self, content, session_id):
        self.content = content
        self.session_id = session_id
        self.release = asyncio.Event()
        self.inputs = []
        self.control = _RunControl()
        self.closed = False
        self.error = None
        self.failure = None

    def steer(self, text):
        if self.closed:
            raise RuntimeError("closed")
        self.inputs.append(text)
        self.control.steer(text)

    def consume_inputs(self):
        return self.control._drain_all()

    def take_pending(self):
        return self.control.take_pending()

    def __aiter__(self):
        return self.iterate()

    async def iterate(self):
        yield make_event(
            "model.stream.content_delta",
            run_id="run",
            session_id=self.session_id,
            delta=self.content,
        )
        await self.release.wait()
        if self.failure:
            raise self.failure
        if self.error is None:
            self.consume_inputs()
        self.closed = True

    async def result(self):
        return SimpleNamespace(
            final_content=self.content,
            tools_used=[],
            usage={},
            stop_reason="model_error" if self.error else "completed",
            error=self.error,
        )

    async def aclose(self):
        self.closed = True
        self.control._close()


class Service:
    def __init__(self):
        self.streams = []
        self.lease_gate = asyncio.Event()
        self.lease_gate.set()

    @asynccontextmanager
    async def lease(self):
        await self.lease_gate.wait()
        yield self

    def stream(self, content, *, session_id, **kwargs):
        stream = Stream(content, session_id)
        self.streams.append(stream)
        return stream


def message(text):
    return ChatRequest(message_id=text, content=text)


async def frame(queue, kind, *, status=None, message_id=None):
    async with asyncio.timeout(2):
        while True:
            item = await queue.get()
            if (
                item["type"] == kind
                and (status is None or item.get("status") == status)
                and (message_id is None or item.get("message_id") == message_id)
            ):
                return item


@pytest.mark.asyncio
async def test_followups_are_fifo_and_result_precedes_next_started():
    service = Service()
    controller = SessionController(service.lease, "one")
    queue, _ = controller.subscribe()
    try:
        await controller.submit(message("A"))
        await frame(queue, "message_status", status="started")
        await controller.submit(message("B"))
        await controller.submit(message("C"))
        assert [s.content for s in service.streams] == ["A"]
        for current, following in [("A", "B"), ("B", "C")]:
            service.streams[-1].release.set()
            assert (await frame(queue, "result"))["final_content"] == current
            await frame(queue, "message_status", status="started", message_id=following)
            assert service.streams[-1].content == following
        last_task = controller.active_task
        service.streams[-1].release.set()
        await frame(queue, "result")
        await last_task
        assert controller.active_task is None
        assert [s.content for s in service.streams] == ["A", "B", "C"]
    finally:
        await controller.close()


@pytest.mark.asyncio
async def test_multiple_steers_non_head_delete_and_direct_input():
    service = Service()
    controller = SessionController(service.lease, "one")
    queue, _ = controller.subscribe()
    try:
        await controller.submit(message("A"))
        await frame(queue, "message_status", status="started")
        for text in ("B", "C", "D", "E"):
            await controller.submit(message(text))
        await controller.steer("C")
        await controller.steer("B")
        await controller.submit(message("backend input"), steer=True)
        await controller.remove_pending("D")
        assert service.streams[0].inputs == ["C", "B", "backend input"]
        assert [item.request.content for item in controller.pending] == ["E"]
        for method in (controller.steer, controller.remove_pending):
            with pytest.raises(InputError, match="no longer pending"):
                await method("C")
        service.streams[0].release.set()
        await frame(queue, "message_status", status="started", message_id="E")
        assert [s.content for s in service.streams] == ["A", "E"]
    finally:
        await controller.close()


@pytest.mark.asyncio
async def test_steer_before_stream_and_after_input_closed():
    service = Service()
    service.lease_gate.clear()
    controller = SessionController(service.lease, "one")
    queue, _ = controller.subscribe()
    try:
        await controller.submit(message("A"))
        await controller.submit(message("B"))
        await controller.steer("B")
        service.lease_gate.set()
        await frame(queue, "message_status", status="steered", message_id="B")
        assert service.streams[0].inputs == ["B"]
        service.streams[0].closed = True
        await controller.submit(message("C"))
        await controller.steer("C")
        assert [item.request.content for item in controller.pending] == ["C"]
        service.streams[0].release.set()
        await frame(queue, "message_status", status="started", message_id="C")
    finally:
        await controller.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("before_start", [True, False])
async def test_cancel_retains_queue_and_manual_send_resumes(before_start):
    service = Service()
    controller = SessionController(service.lease, "one")
    queue, _ = controller.subscribe()
    try:
        await controller.submit(message("A"))
        if not before_start:
            await frame(queue, "message_status", status="started")
        await controller.submit(message("B"))
        await controller.cancel()
        assert controller.active_task is None
        assert not service.streams or service.streams[0].closed
        await controller.steer("B")
        await frame(queue, "message_status", status="started", message_id="B")
        assert service.streams[-1].content == "B"
    finally:
        await controller.close()


@pytest.mark.asyncio
async def test_two_sessions_reconnect_multiple_subscribers_and_steers_are_isolated():
    service = Service()
    one = SessionController(service.lease, "one")
    two = SessionController(service.lease, "two")
    first_queue, _ = one.subscribe()
    second_queue, _ = two.subscribe()
    try:
        await asyncio.gather(one.submit(message("A")), two.submit(message("X")))
        await frame(first_queue, "message_status", status="started")
        await frame(second_queue, "message_status", status="started")
        await asyncio.gather(one.submit(message("B")), two.submit(message("Y")))
        one.unsubscribe(first_queue)
        assert not service.streams[0].closed
        reconnected, snapshot = one.subscribe()
        assert snapshot["running"] is True
        assert [m["message_id"] for m in snapshot["pending"]] == ["B"]
        extra, _ = one.subscribe()
        await one.steer("B")
        await two.steer("Y")
        assert [(s.session_id, s.inputs) for s in service.streams] == [
            ("one", ["B"]),
            ("two", ["Y"]),
        ]
        await frame(reconnected, "message_status", status="steered", message_id="B")
        await frame(extra, "message_status", status="steered", message_id="B")
        with pytest.raises(InputError):
            await one.steer("Y")
        one.unsubscribe(reconnected)
        one.unsubscribe(extra)
        for stream in service.streams:
            stream.release.set()
        await asyncio.gather(one.active_task, two.active_task)
        assert one.active_task is two.active_task is None
        _, completed = one.subscribe()
        assert completed["running"] is False and completed["pending"] == []
    finally:
        await asyncio.gather(one.close(), two.close())


@pytest.mark.asyncio
async def test_model_error_pauses_pending_and_close_does_not_restart():
    from bumblehive.protocols.errors import AgentError

    service = Service()
    controller = SessionController(service.lease, "one")
    queue, _ = controller.subscribe()
    await controller.submit(message("A"))
    await frame(queue, "message_status", status="started")
    await controller.submit(message("B"))
    service.streams[0].error = AgentError(code="model_error", message="failed")
    service.streams[0].release.set()
    await asyncio.gather(controller.active_task)
    assert [s.content for s in service.streams] == ["A"]
    await controller.submit(message("C"))
    assert controller.active_task is None
    assert [i.request.content for i in controller.pending] == ["B", "C"]
    await controller.close()
    assert controller.pending == []
    with pytest.raises(InputError):
        await controller.submit(message("D"))


@pytest.mark.asyncio
async def test_service_delete_and_shutdown_close_only_the_owned_runs(tmp_path):
    from bumblehive_server.runtime_service import RuntimeService

    streams = Service()
    deleted = []
    closed = []

    async def delete(session_id):
        deleted.append(session_id)
        return True

    async def close():
        closed.append(True)

    service = RuntimeService(tmp_path / "unused.json")
    service._runtime = SimpleNamespace(
        stream=streams.stream, delete_session=delete, close=close
    )
    one = service.get_session_controller("one")
    two = service.get_session_controller("two")
    first, _ = one.subscribe()
    second, _ = two.subscribe()
    try:
        await asyncio.gather(one.submit(message("A")), two.submit(message("B")))
        await frame(first, "message_status", status="started")
        await frame(second, "message_status", status="started")
        await two.submit(message("B follow-up"))
        assert service._active_runs == 2
        assert await service.delete_session("one") is True
        assert deleted == ["one"]
        assert one.active_task is None
        assert streams.streams[0].closed
        assert not streams.streams[1].closed
        assert two.active_task is not None
        assert service._active_runs == 1
    finally:
        await service.shutdown()
    assert two.active_task is None and two.pending == []
    assert streams.streams[1].closed and closed == [True]
    assert service._active_runs == 0
    assert service._session_controllers == {}


@pytest.mark.asyncio
@pytest.mark.parametrize("consume_first", [False, True])
async def test_cancel_restores_only_unconsumed_steers_with_original_ids_config_and_order(
    consume_first,
):
    service = Service()
    controller = SessionController(service.lease, "one")
    queue, _ = controller.subscribe()
    left, tail = message("left"), message("tail")
    first = ChatRequest(
        message_id="B",
        content="same text",
        config={"generation": {"temperature": 0.2}},
        approval_mode="full_access",
    )
    second = ChatRequest(
        message_id="C", content="same text", config={"generation": {"temperature": 0.8}}
    )
    try:
        await controller.submit(message("A"))
        await frame(queue, "message_status", status="started")
        for request in (left, first, second, tail):
            await controller.submit(request)
        await controller.steer("C")
        if consume_first:
            assert service.streams[0].consume_inputs() == [
                {"role": "user", "content": "same text"}
            ]
        await controller.steer("B")
        while not queue.empty():
            queue.get_nowait()
        await controller.cancel()
        expected = [left, first, tail] if consume_first else [left, first, second, tail]
        assert [item.request for item in controller.pending] == expected
        assert controller.pending[1].request is first
        assert controller.active_task is None
        assert len(service.streams) == 1  # Cancellation must leave the queue paused.
        receipts = []
        while not queue.empty():
            receipts.append(queue.get_nowait())
        assert [
            (item["message_id"], item["position"])
            for item in receipts
            if item["type"] == "message_status"
        ] == ([("B", 1)] if consume_first else [("B", 1), ("C", 2)])
        assert receipts[-1]["type"] == "cancelled"
        _, snapshot = controller.subscribe()
        assert [item["message_id"] for item in snapshot["pending"]] == [
            item.message_id for item in expected
        ]
        await controller.steer("B")
        await frame(queue, "message_status", status="started", message_id="B")
        assert controller.active_request is first
        assert controller.approvals.mode == "full_access"
        assert service.streams[-1].inputs == []
    finally:
        await controller.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("failure_kind", ["exception", "result_error"])
async def test_failed_run_restores_unconsumed_steers_and_keeps_followups_paused(
    failure_kind,
):
    from bumblehive.protocols.errors import AgentError

    service = Service()
    controller = SessionController(service.lease, "one")
    queue, _ = controller.subscribe()
    try:
        await controller.submit(message("A"))
        await frame(queue, "message_status", status="started")
        await controller.submit(message("B"), steer=True)
        await controller.submit(message("C"))
        stream = service.streams[0]
        if failure_kind == "exception":
            stream.failure = RuntimeError("request failed")
        else:
            stream.error = AgentError(code="model_error", message="request failed")
        task = controller.active_task
        stream.release.set()
        await task
        assert controller.active_task is None
        assert [item.request.message_id for item in controller.pending] == ["B", "C"]
        assert len(service.streams) == 1
        assert controller._steered == []
    finally:
        await controller.close()


@pytest.mark.asyncio
async def test_cancel_one_session_does_not_restore_or_consume_another_sessions_steer():
    service = Service()
    one = SessionController(service.lease, "one")
    two = SessionController(service.lease, "two")
    first, _ = one.subscribe()
    second, _ = two.subscribe()
    try:
        await asyncio.gather(one.submit(message("A")), two.submit(message("X")))
        await frame(first, "message_status", status="started")
        await frame(second, "message_status", status="started")
        await one.submit(message("same"), steer=True)
        await two.submit(message("same"), steer=True)
        await one.cancel()
        assert [item.request.message_id for item in one.pending] == ["same"]
        assert two.pending == [] and two.active_task is not None
        assert two.active_stream.inputs == ["same"]
        task = two.active_task
        two.active_stream.release.set()
        await task
        assert two.pending == [] and two._steered == []
    finally:
        await asyncio.gather(one.close(), two.close())


@pytest.mark.asyncio
async def test_cancel_during_startup_clears_deferred_steering_intent():
    service = Service()
    service.lease_gate.clear()
    controller = SessionController(service.lease, "one")
    queue, _ = controller.subscribe()
    try:
        await controller.submit(message("A"))
        await controller.submit(message("B"), steer=True)
        await controller.submit(message("C"))
        await controller.cancel()
        assert all(not item.steer_requested for item in controller.pending)
        service.lease_gate.set()
        await controller.steer("C")
        await frame(queue, "message_status", status="started", message_id="C")
        assert service.streams[-1].inputs == []
    finally:
        await controller.close()
