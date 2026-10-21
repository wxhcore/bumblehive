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
    monkeypatch.setattr(questions, "ASK_USER_TIMEOUT_SECONDS", 0.05)
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


def late_answers(messages):
    return [m for m in messages if m["role"] == "user"
            and str(m["content"]).startswith("The user answered an earlier question.")]


@pytest.mark.asyncio
@pytest.mark.parametrize("timed_out", [False, True])
async def test_concurrent_sessions_keep_questions_and_answers_isolated(asking, monkeypatch, timed_out):
    monkeypatch.setattr(questions, "ASK_USER_TIMEOUT_SECONDS", 0.05 if timed_out else 10)
    service, provider, reader, first, first_queue, workspace = asking
    second = service.get_session_controller(await reader.create(workspace))
    second_queue, _ = second.subscribe()
    other = (service, provider, reader, second, second_queue, workspace)
    first_card, second_card = await asyncio.gather(start(asking), start(other))
    assert first_card["question"] == second_card["question"]
    assert first_card["question_id"] != second_card["question_id"]

    if timed_out:
        await asyncio.gather(receive(first_queue, "result"), receive(second_queue, "result"))
        await asyncio.gather(*(c.active_task for c in (first, second) if c.active_task))

    # Neither answering nor skipping can target another session's question.
    with pytest.raises(InputError, match="does not exist"):
        await second.answer_question(first_card["question_id"], "wrong session")
    with pytest.raises(InputError, match="does not exist"):
        await first.answer_question(second_card["question_id"])
    assert [q["question_id"] for q in first.subscribe()[1]["questions"]] == [first_card["question_id"]]
    assert [q["question_id"] for q in second.subscribe()[1]["questions"]] == [second_card["question_id"]]

    await asyncio.gather(
        first.answer_question(first_card["question_id"], "first-session-only"),
        second.answer_question(second_card["question_id"]),
    )
    for controller, queue, card in ((first, first_queue, first_card), (second, second_queue, second_card)):
        assert await receive(queue, "question_closed") == {
            "type": "question_closed", "session_id": controller.session_id,
            "question_id": card["question_id"],
        }
        assert controller.subscribe()[1]["questions"] == []
    await receive(first_queue, "result")
    if not timed_out:
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
    assert tool.parallel_safe is False
    assert tool.parameters["required"] == ["question"]
    await controller.answer_question(card["question_id"], answer)
    with pytest.raises(InputError, match="does not exist"):
        await controller.answer_question(card["question_id"], "duplicate")
    await receive(queue, "result")
    history = (await reader.get(controller.session_id)).messages
    assert tool_results(history) == [{
        "question_id": card["question_id"], "status": "answered", "answer": answer,
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
    item = controller.questions[card["question_id"]]
    assert item.future is None
    results = await asyncio.gather(
        controller.answer_question(card["question_id"], "SQLite"),
        controller.answer_question(card["question_id"], "SQLite"),
        return_exceptions=True,
    )
    assert results[0] is None
    assert isinstance(results[1], InputError)
    assert controller.questions == {}
    provider.release.set()
    async with asyncio.timeout(3):
        while controller.active_task:
            await asyncio.sleep(0.001)
    history = (await reader.get(controller.session_id)).messages
    assert tool_results(history)[0] == {"status": "pending", "task_id": "ask"}
    assert len(late_answers(history)) == 1
    assert "Question: Which database?\nAnswer: SQLite" in late_answers(history)[0]["content"]
    assert controller._last_request.config["runtime"]["workspace"] == str(asking[-1])
    assert controller._last_request.approval_mode == "request"


@pytest.mark.asyncio
async def test_disconnect_snapshot_and_cancel_release_waiter_but_keep_question(asking, monkeypatch):
    monkeypatch.setattr(questions, "ASK_USER_TIMEOUT_SECONDS", 10)
    _, _, reader, controller, queue, _ = asking
    card = await start(asking)
    controller.unsubscribe(queue)
    queue, snapshot = controller.subscribe()
    assert snapshot["questions"] == [{
        "question_id": card["question_id"], "question": card["question"],
        "options": card["options"],
    }]
    assert controller.active_task is not None
    await controller.cancel()
    assert controller.questions[card["question_id"]].future is None
    assert controller.subscribe()[1]["questions"] == snapshot["questions"]
    await controller.answer_question(card["question_id"], "MySQL")
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
        await controller.answer_question(card["question_id"], "  ")
    assert card["question_id"] in controller.questions
    controller._closing = True
    with pytest.raises(InputError, match="closed"):
        await controller.answer_question(card["question_id"], "answer")
    assert card["question_id"] in controller.questions
    controller._closing = False


@pytest.mark.asyncio
async def test_failed_late_answer_keeps_question_for_retry(asking, monkeypatch):
    _, _, reader, controller, queue, _ = asking
    card = await start(asking)
    await receive(queue, "result")
    if controller.active_task:
        await controller.active_task

    async def reject_submission(*args, **kwargs):
        raise InputError("submission_failed", "could not accept answer")

    with monkeypatch.context() as patch:
        patch.setattr(controller, "_submit", reject_submission)
        with pytest.raises(InputError, match="could not accept answer"):
            await controller.answer_question(card["question_id"], "MySQL")
    assert controller.subscribe()[1]["questions"][0]["question_id"] == card["question_id"]

    await controller.answer_question(card["question_id"], "MySQL")
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
    item = controller.questions[card["question_id"]]
    await controller.answer_question(card["question_id"], "MySQL")
    assert card["question_id"] not in controller.questions
    assert not item.future.done()
    assert [p.request.message_id for p in controller.pending] == [card["question_id"]]
    await controller.cancel()
    assert controller.active_task is None
    assert len(controller.pending) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("answer_first", [True, False])
async def test_zero_timeout_and_answer_choose_exactly_one_route(asking, monkeypatch, answer_first):
    monkeypatch.setattr(questions, "ASK_USER_TIMEOUT_SECONDS", 0)
    _, _, reader, controller, queue, _ = asking
    card = await start(asking)
    if not answer_first:
        await receive(queue, "result")
        if controller.active_task:
            await controller.active_task
    await controller.answer_question(card["question_id"], "MySQL")
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
    monkeypatch.setattr(questions, "ASK_USER_TIMEOUT_SECONDS", 10)
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
            qid = frame["question_id"]
            socket.send_json({"type": "question_answer", "question_id": qid, "answer": " "})
            error = socket.receive_json()
            while error["type"] != "error":
                error = socket.receive_json()
            assert error["scope"] == "input"
            assert error["question_id"] == qid
        with client.websocket_connect("/ws/v1/chat/questions-test") as socket:
            ready = socket.receive_json()
            assert ready["questions"][0]["question_id"] == qid
            assert set(ready["questions"][0]) == {"question_id", "question", "options"}
            socket.send_json({"type": "question_answer", "question_id": qid, "answer": "MySQL"})
            answered = socket.receive_json()
            assert answered == {"type": "question_closed", "session_id": "questions-test", "question_id": qid}
            while socket.receive_json()["type"] != "result":
                pass
        with client.websocket_connect("/ws/v1/chat/questions-test") as socket:
            assert socket.receive_json()["questions"] == []


@pytest.mark.asyncio
async def test_skip_ends_wait_immediately_and_rejects_later_answers(asking, monkeypatch):
    monkeypatch.setattr(questions, "ASK_USER_TIMEOUT_SECONDS", 60)
    _, _, reader, controller, queue, _ = asking
    card = await start(asking)
    await controller.answer_question(card["question_id"])
    await receive(queue, "result")  # bounded to 3 seconds, not the 60-second timeout
    with pytest.raises(InputError, match="does not exist"):
        await controller.answer_question(card["question_id"], "late conflicting answer")
    with pytest.raises(InputError, match="does not exist"):
        await controller.answer_question(card["question_id"])
    history = (await reader.get(controller.session_id)).messages
    assert tool_results(history) == [{"question_id": card["question_id"], "status": "skipped"}]
    assert late_answers(history) == []
    assert controller.subscribe()[1]["questions"] == []
    assert controller.questions == {}


@pytest.mark.asyncio
async def test_skip_after_timeout_closes_without_starting_another_run(asking):
    _, provider, reader, controller, queue, _ = asking
    card = await start(asking)
    await receive(queue, "result")
    if controller.active_task:
        await controller.active_task
    before = (await reader.get(controller.session_id)).messages
    requests = len(provider.requests)
    await controller.answer_question(card["question_id"])
    with pytest.raises(InputError, match="does not exist"):
        await controller.answer_question(card["question_id"], "late conflicting answer")
    assert controller.active_task is None
    assert not controller.pending
    assert len(provider.requests) == requests
    assert (await reader.get(controller.session_id)).messages == before
    assert tool_results(before)[0] == {"status": "pending", "task_id": "ask"}
    assert controller.subscribe()[1]["questions"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize("skip_first", [False, True])
async def test_answer_and_skip_first_submission_wins(asking, skip_first):
    _, _, reader, controller, queue, _ = asking
    card = await start(asking)
    answers = [None, "MySQL"] if skip_first else ["MySQL", None]
    results = await asyncio.gather(
        *(controller.answer_question(card["question_id"], a) for a in answers),
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
    monkeypatch.setattr(questions, "ASK_USER_TIMEOUT_SECONDS", 60)
    service, _, reader = make_service(tmp_path)
    with TestClient(create_app(runtime_service=service, session_reader=reader)) as client:
        with client.websocket_connect("/ws/v1/chat/skip-test") as socket:
            socket.receive_json()
            socket.send_json({"type": "question_skip", "question_id": "unknown"})
            assert socket.receive_json()["question_id"] == "unknown"
            socket.send_json({"type": "message", "content": "Ask", "config": {
                "runtime": {"workspace": str(tmp_path)},
            }})
            frame = socket.receive_json()
            while frame["type"] != "question_request":
                frame = socket.receive_json()
            socket.send_json({"type": "question_skip", "question_id": frame["question_id"]})
            frame = socket.receive_json()
            while frame["type"] != "question_closed":
                frame = socket.receive_json()
            while socket.receive_json()["type"] != "result":
                pass
        with client.websocket_connect("/ws/v1/chat/skip-test") as socket:
            assert socket.receive_json()["questions"] == []
