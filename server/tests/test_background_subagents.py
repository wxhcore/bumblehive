"""Exercise background delegation through the real SDK runner and session history."""

import asyncio
from copy import deepcopy

import pytest
import pytest_asyncio

from bumblehive import BumblehiveRuntime
from bumblehive.providers.base import ModelProvider, ModelResponse
from bumblehive.protocols import ToolCall
from bumblehive.session.manager import SessionManager
from bumblehive_server.runtime_service import RuntimeBusyError, RuntimeService
from bumblehive_server.schemas import ChatRequest
from bumblehive_server.session_reader import SessionReader


class DelegationProvider(ModelProvider):
    def __init__(self):
        self.plans = {}
        self.children = {}
        self.parent_release = asyncio.Event()
        self.parent_release.set()
        self.requests = []
        self.child_error = False
        self.parent_error = False
        self.approval_path = None

    async def generate(self, request):
        messages = request.messages
        self.requests.append(deepcopy(messages))
        users = [m["content"] for m in messages if m["role"] == "user"]
        first = users[0]
        if "\nTask:\nCHILD:" in first:
            name = first.rsplit("CHILD:", 1)[1].splitlines()[0]
            if messages[-1]["role"] == "tool":
                return ModelResponse(
                    content=f"REPORT:{name}: {messages[-1]['content']}"
                )
            gate = self.children.setdefault(name, asyncio.Event())
            await gate.wait()
            if self.child_error:
                raise RuntimeError("child execution failed")
            return ModelResponse(
                None,
                [ToolCall("read-child", "read_file", {"path": "data.txt"})],
                "tool_calls",
            )
        root = first.removeprefix("ROOT:").splitlines()[0]
        if len(messages) == len([m for m in messages if m["role"] == "system"]) + 1:
            backgrounds, approval = self.plans[root]
            calls = [
                ToolCall(
                    f"delegate-{i}",
                    "sub_agent",
                    {
                        "title": f"Review {root}-{i}",
                        "task": f"CHILD:{root}-{i}",
                        **({"background": bg} if bg is not None else {}),
                    },
                )
                for i, bg in enumerate(backgrounds)
            ]
            if approval:
                calls.append(
                    ToolCall(
                        "write-parent",
                        "write_file",
                        {"path": str(self.approval_path), "content": "approved"},
                    )
                )
            return ModelResponse(None, calls, "tool_calls")
        await self.parent_release.wait()
        if self.parent_error:
            raise RuntimeError("parent execution failed")
        reports = [text for text in users if text.startswith("[Background sub-agent")]
        return ModelResponse(
            content=f"PARENT:{root}:"
            + ("\n".join(reports) if reports else "initial answer")
        )

    async def generate_stream(self, request, *, callbacks=None):
        response = await self.generate(request)
        if response.content and callbacks and callbacks.on_content_delta:
            await callbacks.on_content_delta(response.content)
        return response


@pytest_asyncio.fixture
async def delegation(tmp_path):
    reader = SessionReader(tmp_path / "sessions")
    provider = DelegationProvider()
    provider.approval_path = tmp_path / "approval.txt"
    runtimes = []

    def factory(config):
        runtime = BumblehiveRuntime(config)
        runtime.sessions = SessionManager(reader.directory)

        async def get_provider(_config):
            return provider

        runtime._get_provider = get_provider
        runtimes.append(runtime)
        return runtime

    service = RuntimeService(
        tmp_path / "config.json", session_reader=reader, runtime_factory=factory
    )
    await service.startup()
    try:
        yield service, provider, reader, tmp_path
    finally:
        await service.shutdown()
    assert service._active_runs == 0
    assert service.subagents._tasks == {}


async def receive(queue, kind, session_id=None, status=None):
    async with asyncio.timeout(4):
        while True:
            value = await queue.get()
            if (
                value["type"] == kind
                and (session_id is None or value.get("session_id") == session_id)
                and (status is None or value.get("status") == status)
            ):
                return value


async def begin(delegation, root, backgrounds, *, approval=False, workspace=None):
    service, provider, reader, tmp_path = delegation
    workspace = workspace or tmp_path / root
    workspace.mkdir(exist_ok=True)
    (workspace / "data.txt").write_text(f"DATA:{root}")
    session_id = await reader.create(workspace)
    controller = service.get_session_controller(session_id)
    queue, _ = controller.subscribe()
    provider.plans[root] = (backgrounds, approval)
    await controller.submit(
        ChatRequest(
            content=f"ROOT:{root}",
            config={"runtime": {"workspace": str(workspace)}},
        )
    )
    children = [await receive(queue, "session_created") for _ in backgrounds]
    return session_id, controller, queue, children


def assert_message_order(messages):
    waiting = set()
    for message in messages:
        role = message["role"]
        if role == "assistant":
            assert not waiting, "assistant interrupted a tool result batch"
            waiting = {call["id"] for call in message.get("tool_calls", [])}
        elif role == "tool":
            assert message["tool_call_id"] in waiting
            waiting.remove(message["tool_call_id"])
        elif role == "user":
            assert not waiting, "notification split an assistant/tool result batch"
    assert not waiting


@pytest.mark.asyncio
async def test_waiting_mode_uses_final_report_without_background_notification(
    delegation,
):
    _, provider, reader, _ = delegation
    parent, controller, queue, children = await begin(delegation, "sync", [False])
    assert "background" not in children[0]
    assert controller.active_task is not None
    provider.children.setdefault("sync-0", asyncio.Event()).set()
    result = await receive(queue, "result", parent)
    assert result["error"] is None
    history = (await reader.get(parent)).messages
    assert "REPORT:sync-0" in str(history)
    assert not any(
        str(m.get("content", "")).startswith("[Background sub-agent") for m in history
    )
    assert_message_order(history)


@pytest.mark.asyncio
@pytest.mark.parametrize("count", [1, 3])
@pytest.mark.parametrize("background", [None, True], ids=["default", "explicit"])
async def test_background_returns_then_wakes_idle_parent_and_preserves_order(
    delegation, count, background
):
    service, provider, reader, _ = delegation
    parent, controller, queue, children = await begin(
        delegation, "idle", [background] * count
    )
    assert all(child["background"] for child in children)
    await receive(queue, "result", parent)
    assert service._active_runs == count
    with pytest.raises(RuntimeBusyError):
        await service.update_config({"provider": {"model": "other"}})
    assert len(service.subagents.snapshot(parent)) == count
    for i in range(count):
        provider.children.setdefault(f"idle-{i}", asyncio.Event()).set()
    unfinished = {child["session_id"] for child in children}
    while unfinished:
        ended = await receive(queue, "result")
        unfinished.discard(ended["session_id"])
    async with asyncio.timeout(4):
        while service.subagents._tasks or controller.active_task:
            await asyncio.sleep(0.001)
    assert service.subagents.snapshot(parent) == []
    history = (await reader.get(parent)).messages
    reports = [
        m
        for m in history
        if str(m.get("content", "")).startswith("[Background sub-agent")
    ]
    assert len(reports) == count
    assert {child["session_id"] for child in children} == {
        m["content"].split("Session ID: ", 1)[1].split("\n", 1)[0] for m in reports
    }
    assert_message_order(history)
    for request in provider.requests:
        assert_message_order(request)


@pytest.mark.asyncio
async def test_two_parent_sessions_keep_results_and_workspaces_separate(delegation):
    service, provider, reader, _ = delegation
    parents = await asyncio.gather(
        begin(delegation, "one", [True, True]), begin(delegation, "two", [True])
    )
    for parent, _, queue, _ in parents:
        await receive(queue, "result", parent)
    for name in ["two-0", "one-1", "one-0"]:
        provider.children.setdefault(name, asyncio.Event()).set()
    async with asyncio.timeout(4):
        while service.subagents._tasks or any(c.active_task for _, c, _, _ in parents):
            await asyncio.sleep(0.001)
    for root, (parent, _, _, children) in zip(["one", "two"], parents):
        history = (await reader.get(parent)).messages
        other = "two" if root == "one" else "one"
        assert f"REPORT:{root}-" in str(history)
        assert f"REPORT:{other}-" not in str(history)
        assert f"DATA:{root}" in str(history)
        assert f"DATA:{other}" not in str(history)
        assert_message_order(history)


@pytest.mark.asyncio
async def test_completion_during_approval_is_steered_then_restored_on_stop(delegation):
    service, provider, reader, tmp_path = delegation
    parent, controller, queue, children = await begin(
        delegation, "stop", [True], approval=True
    )
    await receive(queue, "approval_request", parent)
    provider.children.setdefault("stop-0", asyncio.Event()).set()
    await receive(queue, "message_status", parent, "steered")
    await controller.cancel()
    assert len(controller.pending) == 1
    report_id = controller.pending[0].request.message_id
    _, snapshot = controller.subscribe()
    assert snapshot["pending"][0]["message_id"] == report_id
    assert not snapshot["running"]
    assert not (tmp_path / "approval.txt").exists()
    await controller.steer(report_id)
    await receive(queue, "result", parent)
    history = (await reader.get(parent)).messages
    assert (
        sum(
            str(m.get("content", "")).startswith("[Background sub-agent")
            for m in history
        )
        == 1
    )
    assert_message_order(history)


@pytest.mark.asyncio
async def test_late_report_after_stop_stays_queued_until_manual_resume(delegation):
    service, provider, reader, _ = delegation
    provider.parent_release.clear()
    parent, controller, queue, children = await begin(delegation, "late", [True])
    while (await receive(queue, "event"))["kind"] != "tool.call.finished":
        pass
    await controller.cancel()
    provider.children.setdefault("late-0", asyncio.Event()).set()
    await receive(queue, "message_status", parent, "queued")
    async with asyncio.timeout(4):
        while service.subagents._tasks:
            await asyncio.sleep(0.001)
    assert controller.active_task is None
    assert len(controller.pending) == 1
    assert controller.pending[0].request.config["runtime"]["workspace"].endswith("late")
    provider.parent_release.set()
    await controller.steer(controller.pending[0].request.message_id)
    await receive(queue, "result", parent)
    assert "REPORT:late-0" in str((await reader.get(parent)).messages)


@pytest.mark.asyncio
async def test_disconnect_does_not_cancel_background_and_snapshot_is_authoritative(
    delegation,
):
    service, provider, reader, _ = delegation
    parent, controller, queue, children = await begin(delegation, "reconnect", [True])
    await receive(queue, "result", parent)
    controller.unsubscribe(queue)
    again, snapshot = controller.subscribe()
    assert not snapshot["running"]
    assert (
        service.subagents.snapshot(parent)[0]["session_id"] == children[0]["session_id"]
    )
    controller.unsubscribe(again)
    provider.children.setdefault("reconnect-0", asyncio.Event()).set()
    async with asyncio.timeout(4):
        while service.subagents._tasks or controller.active_task:
            await asyncio.sleep(0.001)
    _, final = controller.subscribe()
    assert not final["running"]
    assert service.subagents.snapshot(parent) == []
    assert "REPORT:reconnect-0" in str((await reader.get(parent)).messages)


@pytest.mark.asyncio
async def test_failure_reports_once_and_delete_cancels_without_waking_parent(
    delegation,
):
    service, provider, reader, _ = delegation
    provider.child_error = True
    parent, controller, queue, children = await begin(delegation, "error", [True])
    await receive(queue, "result", parent)
    provider.children.setdefault("error-0", asyncio.Event()).set()
    await receive(queue, "message_status", parent, "started")
    await receive(queue, "result", parent)
    reports = [
        m
        for m in (await reader.get(parent)).messages
        if str(m.get("content", "")).startswith("[Background sub-agent")
    ]
    assert len(reports) == 1
    assert "failed" in reports[0]["content"]
    assert "child execution failed" in reports[0]["content"]
    provider.child_error = False
    parent2, controller2, queue2, children2 = await begin(delegation, "delete", [True])
    await receive(queue2, "result", parent2)
    await service.delete_session(children2[0]["session_id"])
    assert controller2.active_task is None and not controller2.pending
    assert not service.subagents.snapshot(parent2)


@pytest.mark.asyncio
async def test_report_arriving_during_final_model_response_follows_assistant(
    delegation,
):
    service, provider, reader, _ = delegation
    provider.parent_release.clear()
    parent, controller, queue, _ = await begin(delegation, "final", [True])
    # Wait until the parent has requested its answer with the delegation result.
    async with asyncio.timeout(4):
        while not any(
            messages[-1]["role"] == "tool"
            and str(messages[1].get("content", "")).startswith("ROOT:final")
            for messages in provider.requests
        ):
            await asyncio.sleep(0.001)
    provider.children.setdefault("final-0", asyncio.Event()).set()
    await receive(queue, "message_status", parent, "steered")
    provider.parent_release.set()
    await receive(queue, "result", parent)
    history = (await reader.get(parent)).messages
    index = next(
        i
        for i, m in enumerate(history)
        if str(m.get("content", "")).startswith("[Background sub-agent")
    )
    assert history[index - 1]["role"] == "assistant"
    assert not history[index - 1].get("tool_calls")
    assert_message_order(history)
    await controller.cancel()
    assert not controller.pending, "a consumed report must not be restored"


@pytest.mark.asyncio
async def test_report_during_approval_is_consumed_after_complete_tool_batch(delegation):
    _, provider, reader, _ = delegation
    parent, controller, queue, _ = await begin(
        delegation, "approve", [True], approval=True
    )
    approval = await receive(queue, "approval_request", parent)
    provider.children.setdefault("approve-0", asyncio.Event()).set()
    await receive(queue, "message_status", parent, "steered")
    assert not controller.pending
    await controller.decide_approval(approval["approval_id"], False)
    await receive(queue, "result", parent)
    history = (await reader.get(parent)).messages
    index = next(
        i
        for i, m in enumerate(history)
        if str(m.get("content", "")).startswith("[Background sub-agent")
    )
    assert history[index - 1]["role"] == "tool"
    assert_message_order(history)


@pytest.mark.asyncio
async def test_extremely_fast_children_still_report_after_the_tool_batch(delegation):
    service, provider, reader, _ = delegation
    for i in range(3):
        provider.children.setdefault(f"fast-{i}", asyncio.Event()).set()
    parent, controller, queue, _ = await begin(delegation, "fast", [True] * 3)
    async with asyncio.timeout(4):
        while service.subagents._tasks or controller.active_task:
            await asyncio.sleep(0.001)
    history = (await reader.get(parent)).messages
    assert (
        len(
            notices := [
                m
                for m in history
                if str(m.get("content", "")).startswith("[Background sub-agent")
            ]
        )
        == 3
    )
    assert all("REPORT:fast-" in m["content"] for m in notices)
    assert_message_order(history)


@pytest.mark.asyncio
async def test_background_cancel_before_lease_does_not_leave_startup_waiting():
    from contextlib import asynccontextmanager
    from bumblehive_server.subagents import SubagentTasks
    from test_runtime_service import RecordingSubagentObserver

    @asynccontextmanager
    async def blocked_lease():
        await asyncio.Event().wait()
        yield None

    reports = []

    async def notify(*args):
        reports.append(args)

    observer = RecordingSubagentObserver()
    tasks = SubagentTasks(blocked_lease, notify)
    startup = asyncio.create_task(
        tasks.start(
            session_id="child",
            parent_session_id="parent",
            title="Waiting",
            workspace="/tmp",
            content="Inspect",
            observer=observer,
        )
    )
    await asyncio.sleep(0)  # Cancel before the worker can acquire its lease.
    await tasks.cancel("child")
    with pytest.raises(RuntimeError, match="stopped before startup"):
        await asyncio.wait_for(startup, 1)
    assert observer.cancelled == ["child"]
    assert reports == [] and tasks._tasks == {}


@pytest.mark.asyncio
async def test_lease_startup_failure_is_one_tool_error_without_completion_notice():
    from contextlib import asynccontextmanager
    from bumblehive_server.subagents import SubagentTasks
    from test_runtime_service import RecordingSubagentObserver

    @asynccontextmanager
    async def failed_lease():
        raise RuntimeError("runtime unavailable")
        yield None

    reports = []

    async def notify(*args):
        reports.append(args)

    observer = RecordingSubagentObserver()
    tasks = SubagentTasks(failed_lease, notify)
    with pytest.raises(RuntimeError, match="runtime unavailable"):
        await tasks.start(
            session_id="child",
            parent_session_id="parent",
            title="Start",
            workspace="/tmp",
            content="Inspect",
            observer=observer,
        )
    assert observer.errors == [
        {"session_id": "child", "message": "runtime unavailable"}
    ]
    assert observer.cancelled == [] and reports == [] and tasks._tasks == {}


@pytest.mark.asyncio
async def test_parent_failure_does_not_auto_resume_for_late_report(delegation):
    service, provider, reader, _ = delegation
    provider.parent_error = True
    parent, controller, queue, _ = await begin(delegation, "parent-error", [True])
    await receive(queue, "error", parent)
    provider.children.setdefault("parent-error-0", asyncio.Event()).set()
    await receive(queue, "message_status", parent, "queued")
    async with asyncio.timeout(4):
        while service.subagents._tasks:
            await asyncio.sleep(0.001)
    assert controller.active_task is None and controller._paused
    assert len(controller.pending) == 1
    provider.parent_error = False
    await controller.steer(controller.pending[0].request.message_id)
    await receive(queue, "result", parent)
    assert "REPORT:parent-error-0" in str((await reader.get(parent)).messages)
