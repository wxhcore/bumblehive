import asyncio
from typing import Any

import pytest

import bumblehive
from bumblehive.observability import (
    FINAL_RESULT,
    MODEL_STREAM_CONTENT_DELTA,
    TOOL_APPROVAL_FINISHED,
    TOOL_APPROVAL_STARTED,
)
from bumblehive.protocols import ToolCall
from bumblehive.providers import (
    ModelProvider,
    ModelRequest,
    ModelResponse,
    ModelStreamCallbacks,
)
from bumblehive.session.manager import SessionManager


class FakeProvider(ModelProvider):
    instances: list["FakeProvider"] = []

    def __init__(self, *, api_key: str | None, base_url: str | None) -> None:
        self.api_key = api_key
        self.base_url = base_url
        self.requests: list[ModelRequest] = []
        self.closed = False
        self.instances.append(self)

    async def generate(self, request: ModelRequest) -> ModelResponse:
        self.requests.append(request)
        return ModelResponse(content=f"reply-{len(self.requests)}")

    async def generate_stream(
        self,
        request: ModelRequest,
        *,
        callbacks: ModelStreamCallbacks | None = None,
    ) -> ModelResponse:
        response = await self.generate(request)
        if callbacks and callbacks.on_content_delta:
            await callbacks.on_content_delta(response.content or "")
        return response

    async def close(self) -> None:
        self.closed = True


class ToolCallingProvider(FakeProvider):
    async def generate(self, request: ModelRequest) -> ModelResponse:
        self.requests.append(request)
        if len(self.requests) % 2 == 1:
            return ModelResponse(
                content="",
                finish_reason="tool_calls",
                tool_calls=[
                    ToolCall(
                        f"call-{len(self.requests)}",
                        "protected_tool",
                        {"value": len(self.requests)},
                    )
                ],
            )
        return ModelResponse(content="done")


def _install_provider(monkeypatch, provider_type=FakeProvider) -> None:
    from bumblehive.providers import manager as manager_module

    provider_type.instances = []
    monkeypatch.setattr(manager_module, "OpenAIChatCompletionsProvider", provider_type)


def _runtime(tmp_path, **overrides) -> bumblehive.BumblehiveRuntime:
    config: dict[str, Any] = {
        "provider": {"model": "base-model", "api_key": "key"},
        "agent": {"tool_names": []},
        "runtime": {"workspace": str(tmp_path / "workspace"), "timezone": "UTC"},
    }
    for section, values in overrides.items():
        config.setdefault(section, {}).update(values)
    return bumblehive.from_config(config)


class RecordingRenderer:
    def __init__(self):
        self.started = None
        self.events = []
        self.finish_count = 0

    def start(self, message):
        self.started = message

    async def on_event(self, event):
        self.events.append(event)

    async def finish(self):
        self.finish_count += 1


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["run", "stream", "run_console"])
@pytest.mark.parametrize("source", ["stateless", "history", "session"])
async def test_runtime_steering_across_history_and_output_modes(
    monkeypatch, tmp_path, mode, source
) -> None:
    _install_provider(monkeypatch)
    runtime = _runtime(tmp_path)
    history = bumblehive.MessageHistory(
        [
            {"role": "user", "content": "previous"},
            {"role": "assistant", "content": "previous answer"},
        ]
    )
    original_history = history.get_history()
    kwargs = (
        {"history": history}
        if source == "history"
        else {"session_id": "review"}
        if source == "session"
        else {}
    )
    events = []

    async def hook(event):
        events.append(event)
        if event.kind == "model.response.finished" and event.iteration == 0:
            run.steer("after answer")
        if event.kind in {"final_result", "run.finished", "turn.finished"}:
            with pytest.raises(RuntimeError):
                run.steer("late")

    renderer = RecordingRenderer()
    if mode == "run_console":
        kwargs["renderer"] = renderer
    run = getattr(runtime, mode)("original", hooks=hook, **kwargs)
    assert renderer.started is None
    assert not runtime._tools_initialized
    assert not FakeProvider.instances
    run.steer("before start")
    try:
        if mode == "stream":
            stream_events = [event async for event in run]
            assert [event.kind for event in stream_events] == [
                event.kind for event in events
            ]
            result = await run.result()
        else:
            result = await asyncio.create_task(run)
        assert result.final_content == "reply-2"
        assert [m["content"] for m in result.messages[-4:]] == [
            "before start",
            "reply-1",
            "after answer",
            "reply-2",
        ]
        provider = FakeProvider.instances[0]
        assert len(provider.requests) == 2
        assert provider.requests[0].messages[-1]["content"].endswith("before start")
        assert provider.requests[1].messages[-1] == {
            "role": "user",
            "content": "after answer",
        }
        assert [e.kind for e in events].count(FINAL_RESULT) == 1
        assert history.get_history() == original_history
        assert run.take_pending() == []
        if mode == "run_console":
            assert renderer.started == "original"
            assert renderer.events == events
            assert renderer.finish_count == 1
        if source == "session":
            persisted = await SessionManager().get("review")
            assert persisted.history.get_history() == [
                {"role": "user", "content": "original"},
                *result.messages[-4:],
            ]
    finally:
        if mode == "stream":
            await run.aclose()
        await runtime.close()


@pytest.mark.asyncio
async def test_console_steer_during_tool_approval(monkeypatch, tmp_path):
    _install_provider(monkeypatch, ToolCallingProvider)
    runtime = _runtime(tmp_path, agent={"tool_names": ["protected_tool"]})
    renderer = RecordingRenderer()

    @runtime.tools.tool
    async def protected_tool(value: int) -> str:
        """Return the supplied test value."""
        return str(value)

    async def approve(request):
        run.steer("correction during approval")
        return bumblehive.ToolApprovalDecision.approve()

    run = runtime.run_console(
        "original", renderer=renderer, approval_handler=approve, max_queue_size=1
    )
    try:
        result = await asyncio.wait_for(asyncio.create_task(run), timeout=2)
        messages = ToolCallingProvider.instances[0].requests[1].messages
        assert [m["role"] for m in messages[-3:]] == ["assistant", "tool", "user"]
        assert messages[-1]["content"] == "correction during approval"
        assert result.final_content == "done"
        assert renderer.finish_count == 1
        assert [e.kind for e in renderer.events].count(FINAL_RESULT) == 1
        with pytest.raises(RuntimeError):
            run.steer("late")
    finally:
        await runtime.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["start", "event", "cancel"])
async def test_console_failure_closes_producer_and_retains_pending(
    monkeypatch, tmp_path, failure
):
    entered, stopped = asyncio.Event(), asyncio.Event()

    class WaitingProvider(FakeProvider):
        async def generate(self, request):
            self.requests.append(request)
            entered.set()
            try:
                await asyncio.Event().wait()
            finally:
                stopped.set()

    _install_provider(monkeypatch, WaitingProvider)
    runtime = _runtime(tmp_path)

    class Renderer(RecordingRenderer):
        def start(self, message):
            super().start(message)
            if failure == "start":
                raise ValueError("renderer start failed")

        async def on_event(self, event):
            if failure == "event":
                await entered.wait()
                run.steer("pending")
                raise ValueError("renderer event failed")
            await super().on_event(event)

    renderer = Renderer()
    run = runtime.run_console("original", renderer=renderer)
    if failure == "start":
        run.steer("pending")
    task = asyncio.create_task(run)
    try:
        if failure == "cancel":
            await asyncio.wait_for(entered.wait(), timeout=2)
            run.steer("pending")
            task.cancel()
        with pytest.raises(asyncio.CancelledError if failure == "cancel" else ValueError):
            await asyncio.wait_for(task, timeout=2)
        assert renderer.finish_count == 1
        assert run.take_pending() == [{"role": "user", "content": "pending"}]
        with pytest.raises(RuntimeError):
            run.steer("late")
        if failure != "start":
            assert stopped.is_set()
        else:
            assert not WaitingProvider.instances
    finally:
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        await runtime.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("cancel", [False, True])
async def test_console_discard_before_start(monkeypatch, tmp_path, cancel):
    _install_provider(monkeypatch)
    runtime = _runtime(tmp_path)
    renderer = RecordingRenderer()
    run = runtime.run_console("original", renderer=renderer)
    run.steer("pending")
    if cancel:
        task = asyncio.create_task(run)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    else:
        run.close()
    assert renderer.started is None
    assert renderer.finish_count == 0
    assert not FakeProvider.instances
    assert run.take_pending() == [{"role": "user", "content": "pending"}]
    with pytest.raises(RuntimeError):
        run.steer("late")
    await runtime.close()


@pytest.mark.asyncio
async def test_console_finish_failure_leaves_input_closed(monkeypatch, tmp_path):
    _install_provider(monkeypatch)
    runtime = _runtime(tmp_path)

    class Renderer(RecordingRenderer):
        async def finish(self):
            await super().finish()
            raise ValueError("renderer finish failed")

    renderer = Renderer()
    run = runtime.run_console("original", renderer=renderer)
    try:
        with pytest.raises(ValueError, match="renderer finish failed"):
            await run
        assert renderer.finish_count == 1
        with pytest.raises(RuntimeError):
            run.steer("late")
        assert run.take_pending() == []
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_steering_isolated_while_waiting_for_session_and_mixed_concurrency(
    monkeypatch, tmp_path
) -> None:
    entered = asyncio.Queue()
    release = asyncio.Event()

    class BlockingProvider(FakeProvider):
        async def generate(self, request):
            self.requests.append(request)
            entered.put_nowait(request)
            await release.wait()
            return ModelResponse(content="done")

    _install_provider(monkeypatch, BlockingProvider)
    runtime = _runtime(tmp_path)
    waiting = asyncio.Event()
    original_get = runtime.sessions.get
    same_calls = 0

    async def get_session(session_id):
        nonlocal same_calls
        session = await original_get(session_id)
        if session_id == "same":
            same_calls += 1
            if same_calls == 2:
                waiting.set()
        return session

    monkeypatch.setattr(runtime.sessions, "get", get_session)
    first = runtime.run("first", session_id="same")
    second = runtime.run("second", session_id="same")
    other = runtime.stream("other", session_id="other")

    async def consume():
        async for _event in other:
            pass
        return await other.result()

    tasks = []
    try:
        tasks.append(asyncio.create_task(first))
        await asyncio.wait_for(entered.get(), timeout=1)
        tasks.append(asyncio.create_task(second))
        await asyncio.wait_for(waiting.wait(), timeout=1)
        second.steer("second only")
        first.steer("first only")
        tasks.append(asyncio.create_task(consume()))
        other_request = await asyncio.wait_for(entered.get(), timeout=1)
        assert "other" in other_request.messages[-1]["content"]
        other.steer("other only")
        release.set()
        first_result, second_result, other_result = await asyncio.wait_for(
            asyncio.gather(*tasks), timeout=2
        )
        first_contents = [m["content"] for m in first_result.messages]
        second_contents = [m["content"] for m in second_result.messages]
        other_contents = [m["content"] for m in other_result.messages]
        assert "first only" in first_contents
        assert "second only" not in first_contents
        assert "other only" not in first_contents
        assert (
            "first only" in second_contents
        )  # Latest committed history after acquiring the lock.
        assert "second only" in second_contents
        assert "other only" not in second_contents
        assert "other only" in other_contents
        assert "first only" not in other_contents
        assert "second only" not in other_contents
        persisted = await SessionManager().get("same")
        assert [m["content"] for m in persisted.history.get_history()] == [
            "first",
            "done",
            "first only",
            "done",
            "second",
            "second only",
            "done",
        ]
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await other.aclose()
        await runtime.close()


@pytest.mark.asyncio
async def test_steering_waiting_session_cancellation_retains_pending(
    monkeypatch, tmp_path
) -> None:
    _install_provider(monkeypatch)
    runtime = _runtime(tmp_path)
    session = await runtime.sessions.get("locked")
    waiting = asyncio.Event()

    async def get_session(_session_id):
        waiting.set()
        return session

    monkeypatch.setattr(runtime.sessions, "get", get_session)
    run = runtime.run("original", session_id="locked")
    async with session.lock:
        task = asyncio.create_task(run)
        await asyncio.wait_for(waiting.wait(), timeout=1)
        run.steer("pending")
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        with pytest.raises(RuntimeError):
            run.steer("late")
        assert run.take_pending() == [{"role": "user", "content": "pending"}]
        assert not FakeProvider.instances
    assert not session.lock.locked()
    await runtime.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("streaming", [False, True])
@pytest.mark.parametrize("failure", ["config", "initialize", "provider"])
async def test_steering_closes_when_runtime_setup_fails(
    monkeypatch, tmp_path, streaming, failure
) -> None:
    runtime = _runtime(tmp_path)

    async def fail(*args, **kwargs):
        raise ValueError("setup failed")

    kwargs = {}
    if failure == "config":
        kwargs["config"] = {"mcp_servers": {}}
    elif failure == "initialize":
        monkeypatch.setattr(runtime, "initialize_tools", fail)
    else:
        monkeypatch.setattr(runtime, "_get_provider", fail)
    run = (runtime.stream if streaming else runtime.run)("original", **kwargs)
    run.steer("pending")
    try:
        with pytest.raises(ValueError):
            if streaming:
                async for _event in run:
                    pass
            else:
                await run
        with pytest.raises(RuntimeError):
            run.steer("late")
        assert run.take_pending() == [{"role": "user", "content": "pending"}]
    finally:
        if streaming:
            await run.aclose()
        await runtime.close()


def test_runtime_applies_skills_directory_without_creating_it(tmp_path) -> None:
    skills_dir = tmp_path / "custom-skills"

    runtime = bumblehive.from_config(
        bumblehive.RuntimeArguments(skills_dir=skills_dir)
    )

    assert runtime.config.skills_dir == str(skills_dir)
    assert runtime.skills.skills_dir == skills_dir.resolve()
    assert not skills_dir.exists()
    assert not (tmp_path / "skills").exists()


@pytest.mark.asyncio
async def test_runtime_runs_stateless_turns_with_per_run_overlays_and_closes(monkeypatch, tmp_path) -> None:
    _install_provider(monkeypatch)
    runtime = _runtime(
        tmp_path,
        provider={"base_url": "https://example.test/v1"},
        agent={"dynamic_context": {"project": "bumblehive"}},
    )

    first = await runtime.run("first")
    second = await runtime.run("second", config={"provider": {"model": "overlay-model"}})

    provider = FakeProvider.instances[0]
    assert first.final_content == "reply-1"
    assert second.final_content == "reply-2"
    assert [request.model for request in provider.requests] == ["base-model", "overlay-model"]
    assert all(
        [message["role"] for message in request.messages] == ["system", "user"]
        for request in provider.requests
    )
    assert "<project>bumblehive</project>" in provider.requests[0].messages[-1]["content"]
    assert (provider.api_key, provider.base_url) == ("key", "https://example.test/v1")

    await runtime.close()
    assert provider.closed


@pytest.mark.asyncio
async def test_runtime_string_and_message_list_inputs_are_equivalent(
    monkeypatch,
    tmp_path,
) -> None:
    _install_provider(monkeypatch)
    runtime = _runtime(tmp_path)
    current_messages = [{"role": "user", "content": "hello"}]

    await runtime.run("hello")
    await runtime.run(current_messages)

    provider = FakeProvider.instances[0]
    assert [
        message["role"] for message in provider.requests[0].messages
    ] == ["system", "user"]
    assert [
        message["role"] for message in provider.requests[1].messages
    ] == ["system", "user"]
    assert provider.requests[0].messages[-1] == provider.requests[1].messages[-1]
    assert current_messages == [{"role": "user", "content": "hello"}]


@pytest.mark.asyncio
async def test_runtime_reads_history_without_updating_it(monkeypatch, tmp_path) -> None:
    _install_provider(monkeypatch)
    runtime = _runtime(
        tmp_path,
        agent={"dynamic_context": {"project": "bumblehive"}},
    )
    history = bumblehive.MessageHistory()

    first = await runtime.run("first", history=history)
    assert history.get_history() == []

    history.replace_run_messages(first.messages)
    second = await runtime.run("second", history=history)

    provider = FakeProvider.instances[0]
    assert [message["role"] for message in provider.requests[1].messages] == [
        "system",
        "user",
        "assistant",
        "user",
    ]
    assert provider.requests[1].messages[1]["content"] == "first"
    assert history.get_history() == [
        {"role": "user", "content": "first"},
        {"role": "assistant", "content": "reply-1"},
    ]

    history.replace_run_messages(second.messages)
    assert history.get_history() == [
        {"role": "user", "content": "first"},
        {"role": "assistant", "content": "reply-1"},
        {"role": "user", "content": "second"},
        {"role": "assistant", "content": "reply-2"},
    ]


@pytest.mark.asyncio
async def test_runtime_does_not_update_caller_history_when_run_fails(
    monkeypatch,
    tmp_path,
) -> None:
    runtime = _runtime(tmp_path)
    history = bumblehive.MessageHistory(
        [{"role": "user", "content": "existing"}]
    )

    async def fail_run(*args, **kwargs):
        raise RuntimeError("failed")

    monkeypatch.setattr(runtime, "_run_agent", fail_run)
    with pytest.raises(RuntimeError, match="failed"):
        await runtime.run("new", history=history)

    assert history.get_history() == [{"role": "user", "content": "existing"}]


@pytest.mark.asyncio
async def test_runtime_reads_and_writes_external_files_and_skills(
    monkeypatch,
    tmp_path,
) -> None:
    read_root = tmp_path / "read"
    read_root.mkdir()
    source = read_root / "notes.txt"
    source.write_text("external content", encoding="utf-8")

    class PathProvider(FakeProvider):
        async def generate(self, request: ModelRequest) -> ModelResponse:
            self.requests.append(request)
            index = len(self.requests)
            if index == 1:
                return ModelResponse(
                    content="",
                    finish_reason="tool_calls",
                    tool_calls=[
                        ToolCall("read", "read_file", {"path": str(source)}),
                        ToolCall(
                            "read-skill",
                            "read_file",
                            {"path": str(skill_source)},
                        ),
                        ToolCall(
                            "write",
                            "write_file",
                            {"path": str(skill_target), "content": "generated"},
                        ),
                    ],
                )
            if index == 3:
                return ModelResponse(
                    content="",
                    finish_reason="tool_calls",
                    tool_calls=[ToolCall("read-again", "read_file", {"path": str(source)})],
                )
            return ModelResponse(content="done")

    _install_provider(monkeypatch, PathProvider)
    runtime = _runtime(tmp_path, agent={"tool_names": ["read_file", "write_file"]})
    runtime.skills.skills_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    skill_source = runtime.skills.skills_dir / "reference.txt"
    skill_source.write_text("skill content", encoding="utf-8")
    skill_target = runtime.skills.skills_dir / "generated.txt"

    first = await runtime.run("first")
    second = await runtime.run("second")

    provider = PathProvider.instances[0]
    first_tool_messages = [
        message for message in provider.requests[1].messages if message["role"] == "tool"
    ]
    second_tool_messages = [
        message for message in provider.requests[3].messages if message["role"] == "tool"
    ]
    assert first.tools_used == ["read_file", "read_file", "write_file"]
    assert [message["tool_call_id"] for message in first_tool_messages] == [
        "read",
        "read-skill",
        "write",
    ]
    assert [message["role"] for message in provider.requests[1].messages[-4:]] == [
        "assistant",
        "tool",
        "tool",
        "tool",
    ]
    assert any("external content" in message["content"] for message in first_tool_messages)
    assert any("skill content" in message["content"] for message in first_tool_messages)
    assert skill_target.read_text(encoding="utf-8") == "generated"
    assert second.tools_used == ["read_file"]
    assert "external content" in second_tool_messages[0]["content"]


@pytest.mark.asyncio
async def test_runtime_sessions_persist_and_remain_isolated(monkeypatch, tmp_path) -> None:
    _install_provider(monkeypatch)
    runtime = _runtime(tmp_path)

    await runtime.run("first a", session_id="a")
    await runtime.run("first b", session_id="b")
    await runtime.run("second a", session_id="a")

    provider = FakeProvider.instances[0]
    assert [message["role"] for message in provider.requests[2].messages] == [
        "system",
        "user",
        "assistant",
        "user",
    ]
    history_text = str(provider.requests[2].messages)
    assert "first a" in history_text
    assert "first b" not in history_text

    await runtime.close()
    reloaded_runtime = _runtime(tmp_path)
    await reloaded_runtime.run("third a", session_id="a")
    reloaded_request = FakeProvider.instances[1].requests[0]
    reloaded_text = str(reloaded_request.messages)
    assert [message["role"] for message in reloaded_request.messages] == [
        "system",
        "user",
        "assistant",
        "user",
        "assistant",
        "user",
    ]
    assert "first a" in reloaded_text and "second a" in reloaded_text
    assert "first b" not in reloaded_text
    assert await reloaded_runtime.delete_session("a") is True
    assert await reloaded_runtime.delete_session("a") is False


@pytest.mark.asyncio
async def test_cancelled_session_stream_releases_lock_and_recovers_on_next_turn(
    monkeypatch,
    tmp_path,
) -> None:
    class BlockingStreamProvider(FakeProvider):
        stream_started = asyncio.Event()

        async def generate_stream(
            self,
            request: ModelRequest,
            *,
            callbacks: ModelStreamCallbacks | None = None,
        ) -> ModelResponse:
            self.requests.append(request)
            self.stream_started.set()
            await asyncio.Event().wait()
            raise AssertionError("unreachable")

    _install_provider(monkeypatch, BlockingStreamProvider)
    runtime = _runtime(tmp_path)
    stream = runtime.stream("interrupted", session_id="recoverable")
    iterator = stream.__aiter__()
    await anext(iterator)
    await asyncio.wait_for(BlockingStreamProvider.stream_started.wait(), timeout=1)

    await stream.aclose()
    session = await runtime.sessions.get("recoverable")
    assert not session.lock.locked()
    persisted_after_cancel = await SessionManager().get("recoverable")
    assert [
        message["role"] for message in persisted_after_cancel.history.get_history()
    ] == ["user"]

    result = await asyncio.wait_for(
        runtime.run("continue", session_id="recoverable"),
        timeout=1,
    )
    assert result.final_content == "reply-2"
    request = BlockingStreamProvider.instances[0].requests[-1]
    assert [message["role"] for message in request.messages] == [
        "system",
        "user",
        "assistant",
        "user",
    ]
    assert "interrupted before a response" in request.messages[-2]["content"].lower()

    persisted = await SessionManager().get("recoverable")
    assert persisted.history.get_history() == runtime.sessions.get_history(session)


@pytest.mark.asyncio
async def test_runtime_serializes_one_session_but_allows_distinct_sessions(monkeypatch, tmp_path) -> None:
    class BlockingProvider(FakeProvider):
        entered: asyncio.Queue[ModelRequest]
        release: asyncio.Event

        async def generate(self, request: ModelRequest) -> ModelResponse:
            self.requests.append(request)
            await self.entered.put(request)
            await self.release.wait()
            return ModelResponse(content=f"reply-{len(self.requests)}")

    BlockingProvider.entered = asyncio.Queue()
    BlockingProvider.release = asyncio.Event()
    _install_provider(monkeypatch, BlockingProvider)
    runtime = _runtime(tmp_path)

    first = asyncio.create_task(runtime.run("first", session_id="same"))
    await asyncio.wait_for(BlockingProvider.entered.get(), timeout=1)
    second = asyncio.create_task(runtime.run("second", session_id="same"))
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(BlockingProvider.entered.get(), timeout=0.05)
    BlockingProvider.release.set()
    await asyncio.gather(first, second)

    BlockingProvider.entered = asyncio.Queue()
    BlockingProvider.release = asyncio.Event()
    one = asyncio.create_task(runtime.run("one", session_id="one"))
    two = asyncio.create_task(runtime.run("two", session_id="two"))
    await asyncio.wait_for(BlockingProvider.entered.get(), timeout=1)
    await asyncio.wait_for(BlockingProvider.entered.get(), timeout=1)
    BlockingProvider.release.set()
    await asyncio.gather(one, two)


@pytest.mark.asyncio
async def test_runtime_stream_does_not_update_caller_owned_history(
    monkeypatch,
    tmp_path,
) -> None:
    _install_provider(monkeypatch)
    runtime = _runtime(tmp_path)
    history = bumblehive.MessageHistory()
    stream = runtime.stream("stream", history=history)

    _events = [event async for event in stream]
    streamed_result = await stream.result()

    assert streamed_result.final_content == "reply-1"
    assert history.get_history() == []

    history.replace_run_messages(streamed_result.messages)
    assert history.get_history() == [
        {"role": "user", "content": "stream"},
        {"role": "assistant", "content": "reply-1"},
    ]


@pytest.mark.asyncio
async def test_runtime_run_and_stream_propagate_approval_handler(
    monkeypatch,
    tmp_path,
) -> None:
    _install_provider(monkeypatch, ToolCallingProvider)
    runtime = _runtime(tmp_path, agent={"tool_names": ["protected_tool"]})
    approvals = []
    executions = []

    @runtime.tools.tool
    def protected_tool(value: int) -> int:
        """Execute only after approval."""
        executions.append(value)
        return value

    async def approve(request):
        approvals.append(request)
        return bumblehive.ToolApprovalDecision.approve()

    result = await runtime.run("run", approval_handler=approve)
    stream_workspace = tmp_path / "stream-workspace"
    stream = runtime.stream(
        "stream",
        config={"runtime": {"workspace": str(stream_workspace)}},
        approval_handler=approve,
    )
    events = [event async for event in stream]
    streamed_result = await stream.result()

    assert result.final_content == "done"
    assert streamed_result.final_content == "done"
    assert [request.name for request in approvals] == [
        "protected_tool",
        "protected_tool",
    ]
    assert [request.workspace for request in approvals] == [
        (tmp_path / "workspace").resolve(),
        stream_workspace.resolve(),
    ]
    assert executions == [1, 3]
    assert [
        event.kind
        for event in events
        if event.kind in {TOOL_APPROVAL_STARTED, TOOL_APPROVAL_FINISHED}
    ] == [TOOL_APPROVAL_STARTED, TOOL_APPROVAL_FINISHED]


@pytest.mark.asyncio
async def test_runtime_stream_and_console_expose_the_same_agent_result(monkeypatch, tmp_path) -> None:
    _install_provider(monkeypatch)
    runtime = _runtime(tmp_path)
    stream = runtime.stream("stream", session_id="observable")

    events = [event async for event in stream]
    streamed_result = await stream.result()

    assert [event.kind for event in events if event.kind in {MODEL_STREAM_CONTENT_DELTA, FINAL_RESULT}] == [
        MODEL_STREAM_CONTENT_DELTA,
        FINAL_RESULT,
    ]
    assert {event.session_id for event in events} == {"observable"}
    assert streamed_result.final_content == "reply-1"

    class Renderer:
        def __init__(self) -> None:
            self.started = None
            self.events = []
            self.finished = False

        def start(self, message):
            self.started = message

        async def on_event(self, event):
            self.events.append(event)

        async def finish(self):
            self.finished = True

    renderer = Renderer()
    console_history = bumblehive.MessageHistory()
    console_result = await runtime.run_console(
        "console",
        history=console_history,
        renderer=renderer,
    )

    assert console_result.final_content == "reply-2"
    assert renderer.started == "console"
    assert renderer.events and renderer.finished
    assert console_history.get_history() == []


@pytest.mark.asyncio
async def test_runtime_rejects_unsupported_run_configuration(tmp_path) -> None:
    runtime = bumblehive.from_config(
        {"provider": {"type": "unsupported", "model": "test-model"}}
    )
    with pytest.raises(ValueError, match="Unsupported provider type"):
        await runtime.run("hello")

    runtime = _runtime(tmp_path)
    with pytest.raises(ValueError, match="cannot be changed per run"):
        await runtime.run("hello", config={"mcp_servers": []})
    with pytest.raises(ValueError, match="cannot be changed per run"):
        await runtime.run("hello", config={"skills_dir": str(tmp_path / "skills")})


@pytest.mark.asyncio
async def test_runtime_rejects_multiple_conversation_sources(tmp_path) -> None:
    runtime = _runtime(tmp_path)
    history = bumblehive.MessageHistory()

    with pytest.raises(ValueError, match="history and session_id"):
        await runtime.run("hello", history=history, session_id="demo")
    stream = runtime.stream("hello", history=history, session_id="demo")
    with pytest.raises(ValueError, match="history and session_id"):
        async for _event in stream:
            pass
    with pytest.raises(TypeError, match="MessageHistory"):
        await runtime.run("hello", history=[])
