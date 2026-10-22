"""Ask-user behavior through the real SDK runner and application controller."""

import asyncio
import json
from copy import deepcopy

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient

from bumblehive import BumblehiveRuntime
from bumblehive.providers.base import ModelProvider, ModelResponse
from bumblehive.protocols import ToolCall
from bumblehive.session.manager import SessionManager
from bumblehive_server.app import create_app
from bumblehive_server.chat import questions
from bumblehive_server.chat.session import InputError
from bumblehive_server.runtime_service import RuntimeService
from bumblehive_server.schemas import ChatRequest
from bumblehive_server.session_reader import SessionReader


class QuestionProvider(ModelProvider):
    def __init__(self):
        self.requests = []
        self.after_tool = asyncio.Event()
        self.release = asyncio.Event()
        self.release.set()

    async def generate(self, request):
        self.requests.append(deepcopy(request.messages))
        tools = [m for m in request.messages if m["role"] == "tool"]
        if not tools:
            return ModelResponse(None, [ToolCall("ask", "ask_user", {
                "question": "Which database?",
                "options": ["PostgreSQL (recommended): flexible queries", "MySQL"],
            })], "tool_calls")
        self.after_tool.set()
        await self.release.wait()
        return ModelResponse(content="Question handled")

    async def generate_stream(self, request, *, callbacks=None):
        response = await self.generate(request)
        if response.content and callbacks and callbacks.on_content_delta:
            await callbacks.on_content_delta(response.content)
        return response


def make_service(tmp_path):
    reader = SessionReader(tmp_path / "sessions")
    provider = QuestionProvider()

    def factory(config):
        runtime = BumblehiveRuntime(config)
        runtime.sessions = SessionManager(reader.directory)

        async def get_provider(_config):
            return provider

        runtime._get_provider = get_provider
        return runtime

    service = RuntimeService(
        tmp_path / "config.json", session_reader=reader, runtime_factory=factory,
    )
    return service, provider, reader


@pytest_asyncio.fixture
async def asking(tmp_path, monkeypatch):
    monkeypatch.setattr(questions, "ASK_USER_WAIT_SECONDS", 0.05)
    service, provider, reader = make_service(tmp_path)
    await service.startup()
    try:
        session_id = await reader.create(tmp_path)
        controller = service.get_session_controller(session_id)
        queue, _ = controller.subscribe()
        yield service, provider, reader, controller, queue, tmp_path
    finally:
        await service.shutdown()
    assert service._active_runs == 0


async def receive(queue, kind):
    async with asyncio.timeout(3):
        while True:
            item = await queue.get()
            if item["type"] == kind:
                return item


async def start(asking):
    _, _, _, controller, queue, workspace = asking
    await controller.submit(ChatRequest(
        content="Ask me", approval_mode="request",
        config={"runtime": {"workspace": str(workspace)}},
    ))
    return await receive(queue, "question_request")


def tool_results(messages):
    return [json.loads(m["content"]) for m in messages if m["role"] == "tool"]


def background_results(messages):
    return [json.loads(m["content"].split("\n\n", 1)[1]) for m in messages
            if m["role"] == "user" and str(m["content"]).startswith("[Background tool result]\n")]


def late_answers(messages):
    return [result for result in background_results(messages) if result["status"] == "answered"]


@pytest.mark.asyncio
@pytest.mark.parametrize("timed_out", [False, True])
async def test_concurrent_sessions_keep_questions_and_answers_isolated(asking, monkeypatch, timed_out):
    monkeypatch.setattr(questions, "ASK_USER_WAIT_SECONDS", 0.05 if timed_out else 10)
    service, provider, reader, first, first_queue, workspace = asking
    second = service.get_session_controller(await reader.create(workspace))
    second_queue, _ = second.subscribe()
    other = (service, provider, reader, second, second_queue, workspace)
    first_card, second_card = await asyncio.gather(start(asking), start(other))
    assert first_card["question"] == second_card["question"]
    # Tool call IDs can repeat across sessions; each controller owns its question.
    assert first_card["task_id"] == second_card["task_id"] == "ask"

    if timed_out:
        await asyncio.gather(receive(first_queue, "result"), receive(second_queue, "result"))
        await asyncio.gather(*(c.active_task for c in (first, second) if c.active_task))

    # A session without this task cannot answer or skip either question.
    empty = service.get_session_controller(await reader.create(workspace))
    with pytest.raises(InputError, match="does not exist"):
        await empty.answer_question(first_card["task_id"], "wrong session")
    with pytest.raises(InputError, match="does not exist"):
        await empty.answer_question(second_card["task_id"])
    assert [q["task_id"] for q in first.subscribe()[1]["questions"]] == [first_card["task_id"]]
    assert [q["task_id"] for q in second.subscribe()[1]["questions"]] == [second_card["task_id"]]

    await asyncio.gather(
        first.answer_question(first_card["task_id"], "first-session-only"),
        second.answer_question(second_card["task_id"]),
    )
    for controller, queue, card in ((first, first_queue, first_card), (second, second_queue, second_card)):
        assert await receive(queue, "question_closed") == {
            "type": "question_closed", "session_id": controller.session_id,
            "task_id": card["task_id"],
        }
        assert controller.subscribe()[1]["questions"] == []
    await receive(first_queue, "result")
    await receive(second_queue, "result")
    first_history = (await reader.get(first.session_id)).messages
    second_history = (await reader.get(second.session_id)).messages
    assert "first-session-only" in json.dumps(first_history)
    assert "first-session-only" not in json.dumps(second_history)
    assert "wrong session" not in json.dumps(first_history + second_history)
    assert tool_results(first_history)[0]["status"] == ("pending" if timed_out else "answered")
    assert tool_results(second_history)[0]["status"] == ("pending" if timed_out else "skipped")
    if timed_out:
        # Both model calls use "ask", but questions and answers remain session-owned.
        assert tool_results(first_history)[0] == tool_results(second_history)[0] == {
            "status": "pending", "task_id": "ask",
        }
    assert len(late_answers(first_history)) == int(timed_out)
    assert late_answers(second_history) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("answer", ["MySQL", "Use our existing SQLite database"])
async def test_timely_answer_is_only_a_tool_result(asking, answer):
    service, _, reader, controller, queue, _ = asking
    card = await start(asking)
    tool = service._runtime.tools.get_tool("ask_user")
    assert card["task_id"] == "ask"
    assert tool.parallel_safe is False
    assert tool.parameters["required"] == ["question"]
    await controller.answer_question(card["task_id"], answer)
    with pytest.raises(InputError, match="does not exist"):
        await controller.answer_question(card["task_id"], "duplicate")
    await receive(queue, "result")
    history = (await reader.get(controller.session_id)).messages
    assert tool_results(history) == [{
        "task_id": card["task_id"], "status": "answered", "answer": answer,
    }]
    assert late_answers(history) == []
    assert controller.subscribe()[1]["questions"] == []
    assert controller.questions == {}


@pytest.mark.asyncio
@pytest.mark.parametrize("running", [False, True])
async def test_timeout_late_answer_routes_once_and_keeps_original_result(asking, running):
    _, provider, reader, controller, queue, _ = asking
    if running:
        provider.release.clear()
    card = await start(asking)
    if running:
        await asyncio.wait_for(provider.after_tool.wait(), 3)
    else:
        await receive(queue, "result")
        if controller.active_task:
            await controller.active_task
    item = controller.questions[card["task_id"]]
    assert item.future is not None and not item.future.done()
    background_task = item.background_task
    results = await asyncio.gather(
        controller.answer_question(card["task_id"], "SQLite"),
        controller.answer_question(card["task_id"], "SQLite"),
        return_exceptions=True,
    )
    assert results[0] is None
    assert isinstance(results[1], InputError)
    await background_task
    assert controller.questions == {}
    provider.release.set()
    async with asyncio.timeout(3):
        while controller.active_task:
            await asyncio.sleep(0.001)
    history = (await reader.get(controller.session_id)).messages
    assert tool_results(history)[0] == {"status": "pending", "task_id": "ask"}
    assert card["task_id"] == "ask"
    assert len(late_answers(history)) == 1
    assert background_results(history) == [{"task_id": "ask", "status": "answered", "answer": "SQLite"}]
    assert controller._last_request.config["runtime"]["workspace"] == str(asking[-1])
    assert controller._last_request.approval_mode == "request"


@pytest.mark.asyncio
async def test_disconnect_snapshot_and_cancel_release_waiter_but_keep_question(asking, monkeypatch):
    monkeypatch.setattr(questions, "ASK_USER_WAIT_SECONDS", 10)
    _, _, reader, controller, queue, _ = asking
    card = await start(asking)
    controller.unsubscribe(queue)
    queue, snapshot = controller.subscribe()
    assert snapshot["questions"] == [{
        "task_id": card["task_id"], "question": card["question"],
        "options": card["options"],
    }]
    assert controller.active_task is not None
    await controller.cancel()
    assert controller.questions[card["task_id"]].future is None
    assert controller.subscribe()[1]["questions"] == snapshot["questions"]
    await controller.answer_question(card["task_id"], "MySQL")
    await receive(queue, "result")
    history = (await reader.get(controller.session_id)).messages
    assert len(late_answers(history)) == 1
    assert controller.subscribe()[1]["questions"] == []
    await controller.close()
    assert controller.questions == {}


@pytest.mark.asyncio
async def test_unknown_blank_and_closed_answers_do_not_lock_card(asking):
    _, _, _, controller, _, _ = asking
    card = await start(asking)
    with pytest.raises(InputError, match="does not exist"):
        await controller.answer_question("other-session-question", "answer")
    with pytest.raises(InputError, match="blank"):
        await controller.answer_question(card["task_id"], "  ")
    assert card["task_id"] in controller.questions
    controller._closing = True
    with pytest.raises(InputError, match="closed"):
        await controller.answer_question(card["task_id"], "answer")
    assert card["task_id"] in controller.questions
    controller._closing = False


@pytest.mark.asyncio
async def test_failed_answer_after_foreground_stop_keeps_question_for_retry(asking, monkeypatch):
    monkeypatch.setattr(questions, "ASK_USER_WAIT_SECONDS", 10)
    _, _, reader, controller, queue, _ = asking
    card = await start(asking)
    await controller.cancel()

    async def reject_submission(*args, **kwargs):
        raise InputError("submission_failed", "could not accept answer")

    with monkeypatch.context() as patch:
        patch.setattr(controller, "_submit", reject_submission)
        with pytest.raises(InputError, match="could not accept answer"):
            await controller.answer_question(card["task_id"], "MySQL")
    assert controller.subscribe()[1]["questions"][0]["task_id"] == card["task_id"]

    await controller.answer_question(card["task_id"], "MySQL")
    await receive(queue, "result")
    assert controller.subscribe()[1]["questions"] == []
    history = (await reader.get(controller.session_id)).messages
    assert len(late_answers(history)) == 1


@pytest.mark.asyncio
async def test_answer_during_stop_is_queued_without_starting_or_resolving_waiter(asking):
    _, _, _, controller, _, _ = asking
    card = await start(asking)
    # The cancel path sets this flag before waiting for the run to unwind.
    controller._stopping = True
    item = controller.questions[card["task_id"]]
    await controller.answer_question(card["task_id"], "MySQL")
    assert card["task_id"] not in controller.questions
    assert not item.future.done()
    assert [p.request.message_id for p in controller.pending] == [card["task_id"]]
    await controller.cancel()
    assert controller.active_task is None
    assert len(controller.pending) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("answer_first", [True, False])
async def test_zero_timeout_and_answer_choose_exactly_one_route(asking, monkeypatch, answer_first):
    monkeypatch.setattr(questions, "ASK_USER_WAIT_SECONDS", 0)
    _, _, reader, controller, queue, _ = asking
    card = await start(asking)
    if not answer_first:
        await receive(queue, "result")
        if controller.active_task:
            await controller.active_task
    await controller.answer_question(card["task_id"], "MySQL")
    await receive(queue, "question_closed")
    async with asyncio.timeout(3):
        while controller.active_task:
            await asyncio.sleep(0.001)
    history = (await reader.get(controller.session_id)).messages
    result = tool_results(history)[0]
    assert (result["status"] == "answered") + len(late_answers(history)) == 1


@pytest.mark.asyncio
async def test_tool_rejects_missing_session_without_creating_controller(asking):
    service, _, _, _, _, _ = asking
    before = set(service._session_controllers)
    with pytest.raises(RuntimeError, match="active server conversation"):
        await service._runtime.tools.get_tool("ask_user").execute(question="Which database?")
    assert set(service._session_controllers) == before


def test_websocket_answers_errors_and_reconnect(tmp_path, monkeypatch):
    monkeypatch.setattr(questions, "ASK_USER_WAIT_SECONDS", 10)
    service, _, reader = make_service(tmp_path)
    app = create_app(runtime_service=service, session_reader=reader)
    with TestClient(app) as client:
        with client.websocket_connect("/ws/v1/chat/questions-test") as socket:
            assert socket.receive_json()["questions"] == []
            socket.send_json({"type": "message", "content": "Ask", "config": {
                "runtime": {"workspace": str(tmp_path)},
            }})
            while True:
                frame = socket.receive_json()
                if frame["type"] == "question_request":
                    break
            task_id = frame["task_id"]
            socket.send_json({"type": "question_answer", "task_id": task_id, "answer": " "})
            error = socket.receive_json()
            while error["type"] != "error":
                error = socket.receive_json()
            assert error["scope"] == "input"
            assert error["task_id"] == task_id
        with client.websocket_connect("/ws/v1/chat/questions-test") as socket:
            ready = socket.receive_json()
            assert ready["questions"][0]["task_id"] == task_id
            assert set(ready["questions"][0]) == {"task_id", "question", "options"}
            socket.send_json({"type": "question_answer", "task_id": task_id, "answer": "MySQL"})
            answered = socket.receive_json()
            assert answered == {"type": "question_closed", "session_id": "questions-test", "task_id": task_id}
            while socket.receive_json()["type"] != "result":
                pass
        with client.websocket_connect("/ws/v1/chat/questions-test") as socket:
            assert socket.receive_json()["questions"] == []


@pytest.mark.asyncio
async def test_skip_ends_wait_immediately_and_rejects_later_answers(asking, monkeypatch):
    monkeypatch.setattr(questions, "ASK_USER_WAIT_SECONDS", 60)
    _, _, reader, controller, queue, _ = asking
    card = await start(asking)
    await controller.answer_question(card["task_id"])
    await receive(queue, "result")  # bounded to 3 seconds, not the 60-second timeout
    with pytest.raises(InputError, match="does not exist"):
        await controller.answer_question(card["task_id"], "late conflicting answer")
    with pytest.raises(InputError, match="does not exist"):
        await controller.answer_question(card["task_id"])
    history = (await reader.get(controller.session_id)).messages
    assert tool_results(history) == [{"task_id": card["task_id"], "status": "skipped"}]
    assert late_answers(history) == []
    assert controller.subscribe()[1]["questions"] == []
    assert controller.questions == {}


@pytest.mark.asyncio
async def test_skip_after_timeout_delivers_one_result(asking):
    _, _, reader, controller, queue, _ = asking
    card = await start(asking)
    await receive(queue, "result")
    if controller.active_task:
        await controller.active_task
    item = controller.questions[card["task_id"]]
    background_task = item.background_task
    await controller.answer_question(card["task_id"])
    with pytest.raises(InputError, match="does not exist"):
        await controller.answer_question(card["task_id"], "late conflicting answer")
    await background_task
    await receive(queue, "question_closed")
    await receive(queue, "result")
    history = (await reader.get(controller.session_id)).messages
    assert tool_results(history) == [{"status": "pending", "task_id": "ask"}]
    assert background_results(history) == [{"task_id": "ask", "status": "skipped"}]
    assert controller.subscribe()[1]["questions"] == []
    assert item.future is None and item.background_task is None


@pytest.mark.asyncio
@pytest.mark.parametrize("skip_first", [False, True])
async def test_answer_and_skip_first_submission_wins(asking, skip_first):
    _, _, reader, controller, queue, _ = asking
    card = await start(asking)
    answers = [None, "MySQL"] if skip_first else ["MySQL", None]
    results = await asyncio.gather(
        *(controller.answer_question(card["task_id"], a) for a in answers),
        return_exceptions=True,
    )
    assert results[0] is None
    assert isinstance(results[1], InputError)
    assert controller.questions == {}
    await receive(queue, "result")
    history = (await reader.get(controller.session_id)).messages
    assert len(tool_results(history)) == 1
    assert tool_results(history)[0]["status"] == ("skipped" if skip_first else "answered")
    assert late_answers(history) == []


def test_websocket_skip_errors_and_reconnect(tmp_path, monkeypatch):
    monkeypatch.setattr(questions, "ASK_USER_WAIT_SECONDS", 60)
    service, _, reader = make_service(tmp_path)
    with TestClient(create_app(runtime_service=service, session_reader=reader)) as client:
        with client.websocket_connect("/ws/v1/chat/skip-test") as socket:
            socket.receive_json()
            socket.send_json({"type": "question_skip", "task_id": "unknown"})
            assert socket.receive_json()["task_id"] == "unknown"
            socket.send_json({"type": "message", "content": "Ask", "config": {
                "runtime": {"workspace": str(tmp_path)},
            }})
            frame = socket.receive_json()
            while frame["type"] != "question_request":
                frame = socket.receive_json()
            socket.send_json({"type": "question_skip", "task_id": frame["task_id"]})
            frame = socket.receive_json()
            while frame["type"] != "question_closed":
                frame = socket.receive_json()
            while socket.receive_json()["type"] != "result":
                pass
        with client.websocket_connect("/ws/v1/chat/skip-test") as socket:
            assert socket.receive_json()["questions"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize("running", [False, True])
async def test_background_deadline_delivers_skip_and_closes_card(asking, monkeypatch, running):
    monkeypatch.setattr(questions, "ASK_USER_BACKGROUND_WAIT_SECONDS", 0.1)
    _, provider, reader, controller, queue, _ = asking
    if running:
        provider.release.clear()
    card = await start(asking)
    await asyncio.wait_for(provider.after_tool.wait(), 3)
    item = controller.questions[card["task_id"]]
    background_task = item.background_task
    assert background_task is not None and item.future is not None
    assert not item.future.done()
    assert controller.subscribe()[1]["questions"]  # pending is not skipped
    await asyncio.wait_for(background_task, 3)
    assert await receive(queue, "question_closed") == {
        "type": "question_closed", "session_id": controller.session_id, "task_id": "ask",
    }
    assert not controller.questions
    provider.release.set()
    async with asyncio.timeout(3):
        while controller.active_task:
            await asyncio.sleep(0.001)
    history = (await reader.get(controller.session_id)).messages
    assert tool_results(history) == [{"status": "pending", "task_id": "ask"}]
    assert background_results(history) == [{"task_id": "ask", "status": "skipped"}]
    assert item.future is None and item.background_task is None
    with pytest.raises(InputError, match="does not exist"):
        await controller.answer_question("ask", "too late")


@pytest.mark.asyncio
async def test_background_expiration_after_stop_is_queued_until_resume(asking, monkeypatch):
    monkeypatch.setattr(questions, "ASK_USER_BACKGROUND_WAIT_SECONDS", 0.1)
    _, provider, reader, controller, queue, _ = asking
    provider.release.clear()
    card = await start(asking)
    await asyncio.wait_for(provider.after_tool.wait(), 3)
    background_task = controller.questions[card["task_id"]].background_task
    await controller.cancel()
    await asyncio.wait_for(background_task, 3)
    assert controller.active_task is None and controller._paused
    assert not controller.questions
    assert len(controller.pending) == 1
    assert controller.pending[0].request.message_id == "ask_user:ask"
    assert '"status": "skipped"' in controller.pending[0].request.content
    provider.release.set()
    await controller.steer(controller.pending[0].request.message_id)
    await receive(queue, "result")
    assert background_results((await reader.get(controller.session_id)).messages) == [
        {"task_id": "ask", "status": "skipped"},
    ]


@pytest.mark.asyncio
async def test_disconnect_does_not_reset_background_deadline(asking, monkeypatch):
    monkeypatch.setattr(questions, "ASK_USER_BACKGROUND_WAIT_SECONDS", 0.1)
    _, provider, _, controller, queue, _ = asking
    card = await start(asking)
    await asyncio.wait_for(provider.after_tool.wait(), 3)
    background_task = controller.questions[card["task_id"]].background_task
    controller.unsubscribe(queue)
    new_queue, snapshot = controller.subscribe()
    assert snapshot["questions"][0]["task_id"] == card["task_id"]
    controller.unsubscribe(new_queue)
    await asyncio.wait_for(background_task, 3)
    assert controller.subscribe()[1]["questions"] == []


@pytest.mark.asyncio
async def test_close_cancels_background_wait_without_delivering_skip(asking, monkeypatch):
    monkeypatch.setattr(questions, "ASK_USER_BACKGROUND_WAIT_SECONDS", 0.1)
    _, provider, reader, controller, queue, _ = asking
    card = await start(asking)
    await asyncio.wait_for(provider.after_tool.wait(), 3)
    item = controller.questions[card["task_id"]]
    background_task = item.background_task
    future = item.future
    await controller.close()
    assert background_task.cancelled()
    assert future.cancelled()
    assert not controller.questions and not controller.pending
    assert background_results((await reader.get(controller.session_id)).messages) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("answer_first", [True, False])
async def test_background_answer_and_deadline_deliver_only_one_result(asking, monkeypatch, answer_first):
    monkeypatch.setattr(questions, "ASK_USER_BACKGROUND_WAIT_SECONDS", 0)
    _, provider, reader, controller, queue, _ = asking
    card = await start(asking)
    item = controller.questions[card["task_id"]]
    # Hold the completion callback at the deadline; submission must not overwrite
    # a Future that has already completed, even while its card still exists.
    entered = asyncio.Event()
    release = asyncio.Event()
    original_finish = controller._finish_question

    async def finish(question):
        entered.set()
        await release.wait()
        await original_finish(question)

    # wait() has captured the original callback, so exercise the same waiter
    # directly with a controlled boundary and the real submission handler.
    await controller.cancel()
    item.future = asyncio.get_running_loop().create_future()
    item.background_task = asyncio.create_task(item._wait_background(finish, asyncio.get_running_loop().time()))
    background_task = item.background_task
    if answer_first:
        await controller.answer_question(card["task_id"], "boundary answer")
    await asyncio.wait_for(entered.wait(), 3)
    with pytest.raises(InputError, match="does not exist"):
        await controller.answer_question(card["task_id"], "duplicate")
    release.set()
    await asyncio.wait_for(background_task, 3)
    assert len(controller.pending) == 1  # paused by Stop, no automatic restart
    result = json.loads(controller.pending[0].request.content.split("\n\n", 1)[1])
    assert result == ({"task_id": "ask", "status": "answered", "answer": "boundary answer"}
                      if answer_first else {"task_id": "ask", "status": "skipped"})
    assert not controller.questions


@pytest.mark.parametrize("action", ["answer", "skip", "expire"])
def test_websocket_background_completion_and_reconnect(tmp_path, monkeypatch, action):
    monkeypatch.setattr(questions, "ASK_USER_WAIT_SECONDS", 0.02)
    monkeypatch.setattr(questions, "ASK_USER_BACKGROUND_WAIT_SECONDS", 0.15)
    service, provider, reader = make_service(tmp_path)
    app = create_app(runtime_service=service, session_reader=reader)
    with TestClient(app) as client:
        session_id = client.portal.call(reader.create, tmp_path)
        with client.websocket_connect(f"/ws/v1/chat/{session_id}") as socket:
            socket.receive_json()
            socket.send_json({"type": "message", "content": "Ask", "config": {
                "runtime": {"workspace": str(tmp_path)},
            }})
            while socket.receive_json()["type"] != "question_request":
                pass
            while socket.receive_json()["type"] != "result":
                pass
            if action != "expire":
                socket.send_json({
                    "type": "question_answer" if action == "answer" else "question_skip",
                    "task_id": "ask",
                    **({"answer": "MySQL"} if action == "answer" else {}),
                })
            closed = socket.receive_json()
            while closed["type"] != "question_closed":
                closed = socket.receive_json()
            assert closed["task_id"] == "ask"
            while socket.receive_json()["type"] != "result":
                pass
        with client.websocket_connect(f"/ws/v1/chat/{session_id}") as socket:
            assert socket.receive_json()["questions"] == []
        history = client.portal.call(reader.get, session_id).messages
    assert background_results(history) == [
        {"task_id": "ask", "status": "answered", "answer": "MySQL"}
        if action == "answer" else {"task_id": "ask", "status": "skipped"},
    ]


@pytest.mark.asyncio
async def test_answer_and_expiration_in_different_sessions_are_isolated(asking, monkeypatch):
    monkeypatch.setattr(questions, "ASK_USER_BACKGROUND_WAIT_SECONDS", 0.15)
    service, provider, reader, first, first_queue, workspace = asking
    second = service.get_session_controller(await reader.create(workspace))
    second_queue, _ = second.subscribe()
    await asyncio.gather(start(asking), start((service, provider, reader, second, second_queue, workspace)))
    await asyncio.gather(receive(first_queue, "result"), receive(second_queue, "result"))
    first_wait = first.questions["ask"].background_task
    second_wait = second.questions["ask"].background_task
    await first.answer_question("ask", "only first session")
    await asyncio.wait_for(asyncio.gather(first_wait, second_wait), 3)
    await asyncio.gather(receive(first_queue, "result"), receive(second_queue, "result"))
    assert background_results((await reader.get(first.session_id)).messages) == [
        {"task_id": "ask", "status": "answered", "answer": "only first session"},
    ]
    assert background_results((await reader.get(second.session_id)).messages) == [
        {"task_id": "ask", "status": "skipped"},
    ]
    assert not first.questions and not second.questions
