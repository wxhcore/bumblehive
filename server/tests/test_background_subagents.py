"""Exercise background delegation through the real SDK runner and session history."""

import asyncio
import json
from copy import deepcopy
from pathlib import Path

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

    async def generate(self, request):
        messages = request.messages
        self.requests.append(deepcopy(messages))
        users = [m["content"] for m in messages if m["role"] == "user"]
        first = users[0]
        if first.startswith("CHILD:"):
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
            count, question = self.plans[root]
            calls = [
                ToolCall(
                    f"delegate-{i}",
                    "sub_agent",
                    {
                        "title": f"Review {root}-{i}",
                        "task": f"CHILD:{root}-{i}",
                    },
                )
                for i in range(count)
            ]
            if question:
                calls.append(
                    ToolCall(
                        "ask-parent",
                        "ask_user",
                        {"question": "Continue?"},
                    )
                )
            return ModelResponse(None, calls, "tool_calls")
        await self.parent_release.wait()
        if self.parent_error:
            raise RuntimeError("parent execution failed")
        reports = [text for text in users if text.startswith("[Background tool result]")]
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


async def begin(delegation, root, count, *, question=False, workspace=None, approval_mode="request"):
    service, provider, reader, tmp_path = delegation
    workspace = workspace or tmp_path / root
    workspace.mkdir(exist_ok=True)
    (workspace / "data.txt").write_text(f"DATA:{root}")
    session_id = await reader.create(workspace)
    await service.set_super_mode(reader, session_id, True)
    controller = service.get_session_controller(session_id)
    queue, _ = controller.subscribe()
    provider.plans[root] = (count, question)
    await controller.submit(
        ChatRequest(
            content=f"ROOT:{root}",
            approval_mode=approval_mode,
            config={"runtime": {"workspace": str(workspace)}},
        )
    )
    children = [await receive(queue, "session_created") for _ in range(count)]
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
@pytest.mark.parametrize("count", [1, 3])
async def test_background_returns_then_wakes_idle_parent_and_preserves_order(
    delegation, count
):
    service, provider, reader, _ = delegation
    parent, controller, queue, children = await begin(
        delegation, "idle", count
    )
    assert all("background" not in child for child in children)
    await receive(queue, "result", parent)
    history = (await reader.get(parent)).messages
    assert [json.loads(m["content"]) for m in history if m["role"] == "tool"] == [
        {"status": "pending", "task_id": f"delegate-{i}"} for i in range(count)
    ]
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
        if str(m.get("content", "")).startswith("[Background tool result]")
    ]
    assert len(reports) == count
    assert {f"delegate-{i}" for i in range(count)} == {
        m["content"].split("Task ID: ", 1)[1].split("\n", 1)[0] for m in reports
    }
    assert all(m["role"] == "user" for m in reports)
    assert all(m["content"].split("\n\n", 1)[1].startswith("REPORT:idle-") for m in reports)
    for child in children:
        assert (await reader.get(child["session_id"])).messages
    assert_message_order(history)
    for request in provider.requests:
        assert_message_order(request)


@pytest.mark.asyncio
async def test_two_parent_sessions_keep_results_and_workspaces_separate(delegation):
    service, provider, reader, _ = delegation
    parents = await asyncio.gather(
        begin(delegation, "one", 2), begin(delegation, "two", 1)
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
async def test_completion_during_question_is_steered_then_restored_on_stop(delegation):
    service, provider, reader, tmp_path = delegation
    parent, controller, queue, children = await begin(
        delegation, "stop", 1, question=True
    )
    await receive(queue, "question_request", parent)
    provider.children.setdefault("stop-0", asyncio.Event()).set()
    await receive(queue, "message_status", parent, "steered")
    await controller.cancel()
    assert len(controller.pending) == 1
    report_id = controller.pending[0].request.message_id
    assert report_id == "subagent:delegate-0"
    _, snapshot = controller.subscribe()
    assert snapshot["pending"][0]["message_id"] == report_id
    assert not snapshot["running"]
    await controller.steer(report_id)
    await receive(queue, "result", parent)
    history = (await reader.get(parent)).messages
    assert (
        sum(
            str(m.get("content", "")).startswith("[Background tool result]")
            for m in history
        )
        == 1
    )
    assert_message_order(history)


@pytest.mark.asyncio
async def test_late_report_after_stop_stays_queued_until_manual_resume(delegation):
    service, provider, reader, _ = delegation
    provider.parent_release.clear()
    parent, controller, queue, children = await begin(delegation, "late", 1)
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
    parent, controller, queue, children = await begin(delegation, "reconnect", 1)
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
    parent, controller, queue, children = await begin(delegation, "error", 1)
    await receive(queue, "result", parent)
    provider.children.setdefault("error-0", asyncio.Event()).set()
    await receive(queue, "message_status", parent, "started")
    await receive(queue, "result", parent)
    reports = [
        m
        for m in (await reader.get(parent)).messages
        if str(m.get("content", "")).startswith("[Background tool result]")
    ]
    assert len(reports) == 1
    assert reports[0]["content"] == (
        "[Background tool result]\nTask ID: delegate-0\n\n"
        "Error:\nchild execution failed"
    )
    provider.child_error = False
    parent2, controller2, queue2, children2 = await begin(delegation, "delete", 1)
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
    parent, controller, queue, _ = await begin(delegation, "final", 1)
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
        if str(m.get("content", "")).startswith("[Background tool result]")
    )
    assert history[index - 1]["role"] == "assistant"
    assert not history[index - 1].get("tool_calls")
    assert_message_order(history)
    await controller.cancel()
    assert not controller.pending, "a consumed report must not be restored"


@pytest.mark.asyncio
async def test_report_during_question_is_consumed_after_complete_tool_batch(delegation):
    _, provider, reader, _ = delegation
    parent, controller, queue, _ = await begin(
        delegation, "approve", 1, question=True
    )
    question = await receive(queue, "question_request", parent)
    provider.children.setdefault("approve-0", asyncio.Event()).set()
    await receive(queue, "message_status", parent, "steered")
    assert not controller.pending
    await controller.answer_question(question["task_id"], "Continue")
    await receive(queue, "result", parent)
    history = (await reader.get(parent)).messages
    index = next(
        i
        for i, m in enumerate(history)
        if str(m.get("content", "")).startswith("[Background tool result]")
    )
    assert history[index - 1]["role"] == "tool"
    assert_message_order(history)


@pytest.mark.asyncio
async def test_extremely_fast_children_still_report_after_the_tool_batch(delegation):
    service, provider, reader, _ = delegation
    for i in range(3):
        provider.children.setdefault(f"fast-{i}", asyncio.Event()).set()
    parent, controller, queue, _ = await begin(delegation, "fast", 3)
    async with asyncio.timeout(4):
        while service.subagents._tasks or controller.active_task:
            await asyncio.sleep(0.001)
    history = (await reader.get(parent)).messages
    assert (
        len(
            notices := [
                m
                for m in history
                if str(m.get("content", "")).startswith("[Background tool result]")
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
    tasks = SubagentTasks(blocked_lease, notify, lambda _: pytest.fail("lease blocked"))
    startup = asyncio.create_task(
        tasks.start(
            task_id="delegate-blocked",
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
    tasks = SubagentTasks(failed_lease, notify, lambda _: pytest.fail("lease failed"))
    with pytest.raises(RuntimeError, match="runtime unavailable"):
        await tasks.start(
            task_id="delegate-failed",
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
    parent, controller, queue, _ = await begin(delegation, "parent-error", 1)
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


@pytest.mark.asyncio
async def test_message_existing_bee_while_running_and_after_restart(delegation, monkeypatch):
    service, provider, reader, _ = delegation
    generate = provider.generate

    async def send_or_answer(request):
        last = request.messages[-1]
        if last["role"] == "user" and last["content"].startswith("Send: "):
            message = last["content"].splitlines()[0].removeprefix("Send: ")
            return ModelResponse(None, [
                ToolCall("send-" + message, "send_message", {
                    "target": "delegate-0", "message": message,
                })
            ], "tool_calls")
        if last["role"] == "user" and last["content"].splitlines()[0] == "Explain the evidence":
            assert any("DATA:message" in m["content"] for m in request.messages if m["role"] == "tool")
            return ModelResponse(content="Evidence from the first turn.")
        return await generate(request)

    monkeypatch.setattr(provider, "generate", send_or_answer)
    parent, controller, queue, children = await begin(delegation, "message", 2)
    await receive(queue, "result", parent)
    child = await reader.find_child(parent, "delegate-0")
    assert child.session_id in {c["session_id"] for c in children}
    await controller.submit(ChatRequest(content="Send: Check the file"))
    await receive(queue, "result", parent)
    history = (await reader.get(parent)).messages
    expected_receipt = {"status": "sent", "task_id": "delegate-0"}
    assert [json.loads(m["content"]) for m in history if m.get("name") == "send_message"] == [expected_receipt]

    provider.children.setdefault("message-1", asyncio.Event()).set()
    await receive(queue, "result", parent)
    provider.children.setdefault("message-0", asyncio.Event()).set()
    await receive(queue, "result", parent)
    child_history = (await reader.get(child.session_id)).messages
    assert [m["content"] for m in child_history if m["role"] == "user"].count("Check the file") == 1

    await service.shutdown()
    await service.startup()
    controller = service.get_session_controller(parent)
    queue, _ = controller.subscribe()
    await controller.submit(ChatRequest(content="Send: Explain the evidence"))
    frame = await receive(queue, "message_status", child.session_id, "started")
    assert frame["content"] == "Explain the evidence"
    async with asyncio.timeout(4):
        while service.subagents._tasks or controller.active_task:
            await asyncio.sleep(0.001)
    history = (await reader.get(parent)).messages
    reports = [m["content"] for m in history if m["role"] == "user"
               and m["content"].startswith("[Background tool result]")]
    assert [r.splitlines()[1] for r in reports] == [
        "Task ID: delegate-1", "Task ID: delegate-0", "Task ID: delegate-0",
    ]
    assert reports[-1].endswith("Evidence from the first turn.")
    receipts = [json.loads(m["content"]) for m in history if m.get("name") == "send_message"]
    assert receipts == [expected_receipt, expected_receipt]
    assert len(await reader.descendant_ids(parent)) == 2


@pytest.mark.asyncio
async def test_worker_updates_wake_parent_and_queue_after_stop(delegation, monkeypatch):
    service, provider, reader, _ = delegation
    generate = provider.generate
    first_update, second_update, finish = (asyncio.Event() for _ in range(3))
    updates = ["Only on reconnect", "Confirmed after sleep"]

    async def coordinate(request):
        first_user = next(m["content"] for m in request.messages if m["role"] == "user")
        last = request.messages[-1]
        tools = {tool["function"]["name"]: tool["function"] for tool in request.tools}
        assert "send_message" in tools
        if first_user.startswith("CHILD:progress-0"):
            assert "sub_agent" not in tools
            assert "Your final report is delivered automatically" in request.messages[0]["content"]
            receipts = [m for m in request.messages if m.get("name") == "send_message"]
            for receipt in receipts:
                assert json.loads(receipt["content"]) == {"status": "sent", "task_id": "delegate-0"}
            index = len(receipts)
            if index == len(updates):
                await finish.wait()
                return ModelResponse(content="Investigation complete")
            await (first_update, second_update)[index].wait()
            return ModelResponse(None, [ToolCall(f"update-{index}", "send_message", {
                "target": "parent", "message": updates[index],
            })], "tool_calls")
        if last["role"] == "user" and last["content"].startswith(
            "[Sub-agent progress update]\nTask ID: delegate-0\n\nOnly on reconnect"
        ):
            assert "[Sub-agent progress update]" in tools["sub_agent"]["description"]
            assert "[Background tool result]" in tools["sub_agent"]["description"]
            return ModelResponse(None, [ToolCall("redirect", "send_message", {
                "target": "delegate-1", "message": "Check reconnect",
            })], "tool_calls")
        return await generate(request)

    monkeypatch.setattr(provider, "generate", coordinate)
    parent, controller, queue, _ = await begin(delegation, "progress", 2)
    await receive(queue, "result", parent)
    first_update.set()
    first = await receive(queue, "message_status", parent, "queued")
    await receive(queue, "result", parent)
    assert len(service.subagents.snapshot(parent)) == 2
    child_b = await reader.find_child(parent, "delegate-1")
    provider.children["progress-1"].set()
    await receive(queue, "result", parent)
    assert any(m["content"] == "Check reconnect" for m in (await reader.get(child_b.session_id)).messages)

    await controller.cancel()
    second_update.set()
    second = await receive(queue, "message_status", parent, "queued")
    assert first["message_id"] != second["message_id"]
    assert second["content"].endswith(updates[1])
    assert controller.active_task is None
    assert len(service.subagents.snapshot(parent)) == 1

    finish.set()
    await receive(queue, "message_status", parent, "queued")
    assert controller.active_task is None
    assert [item.request.content for item in controller.pending] == [
        second["content"], "[Background tool result]\nTask ID: delegate-0\n\nInvestigation complete",
    ]
    with pytest.raises(ValueError, match="Only a running sub-agent"):
        await service.subagents.send_update(parent, "Wrong direction")


@pytest.mark.asyncio
async def test_sending_at_child_close_does_not_lose_message(delegation, monkeypatch):
    service, provider, reader, _ = delegation
    closing = asyncio.Event()
    release = asyncio.Event()
    notify = service.subagents._notify

    async def hold_first_report(*args):
        closing.set()
        await release.wait()
        await notify(*args)

    monkeypatch.setattr(service.subagents, "_notify", hold_first_report)
    parent, _, _, children = await begin(delegation, "closing", 1)
    provider.children.setdefault("closing-0", asyncio.Event()).set()
    await asyncio.wait_for(closing.wait(), 4)
    with pytest.raises(ValueError, match="No sub-agent"):
        await service.subagents.send(reader, "another-parent", "delegate-0", "Wrong owner")
    with pytest.raises(ValueError, match="No sub-agent"):
        await service.subagents.send(reader, parent, "unknown-task", "Unknown")
    looked_up = asyncio.Event()
    find_child = reader.find_child

    async def observe_lookup(*args):
        child = await find_child(*args)
        looked_up.set()
        return child

    monkeypatch.setattr(reader, "find_child", observe_lookup)
    send = asyncio.create_task(service.subagents.send(reader, parent, "delegate-0", "One more question"))
    await asyncio.wait_for(looked_up.wait(), 4)
    assert not send.done()
    release.set()
    await asyncio.wait_for(send, 4)
    async with asyncio.timeout(4):
        while service.subagents._tasks:
            await asyncio.sleep(0.001)
    child = children[0]["session_id"]
    history = (await reader.get(child)).messages
    assert sum(m["content"] == "One more question" for m in history if m["role"] == "user") == 1
    await service.delete_session(child)
    with pytest.raises(ValueError, match="No sub-agent"):
        await service.subagents.send(reader, parent, "delegate-0", "Deleted")


@pytest.mark.asyncio
@pytest.mark.parametrize(("approval_mode", "decision"), [
    ("request", True), ("request", False), ("full_access", None),
])
async def test_worker_write_after_router_finishes(delegation, monkeypatch, approval_mode, decision):
    from bumblehive_server.chat.session import InputError

    service, provider, reader, tmp_path = delegation
    target = tmp_path / "outside-workspace.txt"
    generate = provider.generate
    release = asyncio.Event()

    async def do_work(request):
        user = next(m["content"] for m in request.messages if m["role"] == "user")
        names = {tool["function"]["name"] for tool in request.tools}
        if not user.startswith("CHILD:"):
            assert names == {"sub_agent", "send_message", "ask_user", "read_file", "grep", "list_dir", "find_files"}
            return await generate(request)
        assert {"exec", "write_file", "send_message"} <= names
        assert not {"sub_agent", "ask_user"} & names
        if request.messages[-1]["role"] == "tool":
            return ModelResponse(content="Worker finished")
        await release.wait()
        return ModelResponse(None, [ToolCall("write", "write_file", {
            "path": str(target), "content": "worker output",
        })], "tool_calls")

    monkeypatch.setattr(provider, "generate", do_work)
    root, controller, queue, children = await begin(delegation, "write", 1, approval_mode=approval_mode)
    await receive(queue, "result", root)
    with pytest.raises(InputError, match="Worker"):
        await service.set_super_mode(reader, root, False)
    release.set()
    if decision is not None:
        approval = await receive(queue, "approval_request", root)
        assert approval["worker_session_id"] == children[0]["session_id"]
        assert approval["worker_title"] == children[0]["title"]
        assert not target.exists()
        controller.unsubscribe(queue)
        queue, ready = controller.subscribe()
        assert not ready["running"] and ready["approvals"] == [approval]
        await controller.decide_approval(approval["approval_id"], decision)
        resolved = await receive(queue, "approval_resolved", root)
        assert resolved["approved"] is decision
    await receive(queue, "result", root)
    assert controller.subscribe()[1]["approvals"] == []
    if decision is False:
        assert not target.exists()
    else:
        assert target.read_text() == "worker output"


@pytest.mark.asyncio
async def test_two_worker_approvals_remain_independent_after_reconnect(delegation, monkeypatch):
    _, provider, _, tmp_path = delegation
    generate = provider.generate
    release = asyncio.Event()

    async def request_write(request):
        first = next(m["content"] for m in request.messages if m["role"] == "user")
        if not first.startswith("CHILD:"):
            return await generate(request)
        if request.messages[-1]["role"] == "tool":
            return ModelResponse(content="Finished")
        await release.wait()
        name = first.splitlines()[0].removeprefix("CHILD:")
        return ModelResponse(None, [ToolCall("write", "write_file", {
            "path": str(tmp_path / name), "content": name,
        })], "tool_calls")

    monkeypatch.setattr(provider, "generate", request_write)
    root, controller, queue, children = await begin(delegation, "parallel", 2)
    await receive(queue, "result", root)
    release.set()
    approvals = [await receive(queue, "approval_request", root) for _ in children]
    assert {a["worker_session_id"] for a in approvals} == {c["session_id"] for c in children}
    assert len({a["approval_id"] for a in approvals}) == 2
    controller.unsubscribe(queue)
    queue, ready = controller.subscribe()
    assert {a["approval_id"] for a in ready["approvals"]} == {a["approval_id"] for a in approvals}

    first, second = approvals
    await controller.decide_approval(second["approval_id"], False)
    await receive(queue, "result", root)
    assert not (tmp_path / "parallel-0").exists() and not (tmp_path / "parallel-1").exists()
    await controller.decide_approval(first["approval_id"], True)
    await receive(queue, "result", root)
    approved_path = Path(first["arguments"]["path"])
    assert approved_path.read_text() == approved_path.name
    assert not Path(second["arguments"]["path"]).exists()


@pytest.mark.asyncio
async def test_role_change_on_same_session_controls_discovery_and_dispatch(delegation, monkeypatch):
    service, provider, reader, tmp_path = delegation
    root = await reader.create(tmp_path)
    controller = service.get_session_controller(root)
    queue, _ = controller.subscribe()
    offered = []

    async def request_tool(request):
        if request.messages[-1]["role"] == "tool":
            return ModelResponse(content=request.messages[-1]["content"])
        is_single = request.messages[-1]["content"].startswith("single")
        offered.append({tool["function"]["name"] for tool in request.tools})
        call = (ToolCall("delegate", "sub_agent", {"title": "test", "task": "test"}) if is_single
                else ToolCall("write", "write_file", {"path": str(tmp_path / "forbidden.txt"), "content": "test"}))
        return ModelResponse(None, [call], "tool_calls")

    monkeypatch.setattr(provider, "generate", request_tool)
    for turn in ("single", "router", "single again"):
        if turn != "single":
            await service.set_super_mode(reader, root, turn == "router")
        await controller.submit(ChatRequest(content=turn))
        await receive(queue, "result", root)
    assert "ask_user" in offered[0] and "write_file" in offered[0]
    assert not {"sub_agent", "send_message"} & offered[0]
    assert "sub_agent" in offered[1] and "write_file" not in offered[1]
    assert offered[0] == offered[2]
    assert not (tmp_path / "forbidden.txt").exists()
    assert not await reader.descendant_ids(root)
    results = [m["content"] for m in (await reader.get(root)).messages if m["role"] == "tool"]
    assert len(results) == 3 and all("not exposed" in result for result in results)
