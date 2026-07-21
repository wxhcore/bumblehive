from typing import Any

import pytest

from bumblehive.agent import AgentLoop, ContextBuilder, ToolCallingRunner
from bumblehive.observability import (
    FINAL_RESULT,
    ITERATION_FINISHED,
    ITERATION_STARTED,
    MODEL_REQUEST_STARTED,
    MODEL_RESPONSE_FINISHED,
    MODEL_STREAM_CONTENT_DELTA,
    RUN_ERROR,
    RUN_FINISHED,
    RUN_STARTED,
    TOOL_CALL_FINISHED,
    TOOL_CALL_STARTED,
    TOOL_CALLS_FINISHED,
    TOOL_CALLS_STARTED,
    TURN_CONTEXT_BUILT,
    TURN_FINISHED,
    TURN_STARTED,
    EventEmitter,
    EventRecorder,
)
from bumblehive.protocols import ToolCall
from bumblehive.providers import (
    ModelProvider,
    ModelRequest,
    ModelResponse,
    ModelStreamCallbacks,
)
from bumblehive.skills import SkillsManager
from bumblehive.tools import ToolManager


class SequenceProvider(ModelProvider):
    def __init__(self, responses: list[ModelResponse]) -> None:
        self.responses = list(responses)

    async def generate(self, request: ModelRequest) -> ModelResponse:
        return self.responses.pop(0)

    async def generate_stream(
        self,
        request: ModelRequest,
        *,
        callbacks: ModelStreamCallbacks | None = None,
    ) -> ModelResponse:
        response = await self.generate(request)
        if callbacks and callbacks.on_content_delta and response.content:
            await callbacks.on_content_delta(response.content)
        return response


def _tools() -> ToolManager:
    tools = ToolManager()

    @tools.tool
    def add(a: int, b: int) -> int:
        """Add two integers."""
        return a + b

    return tools


@pytest.mark.asyncio
async def test_runner_emits_one_complete_model_and_tool_timeline(tmp_path) -> None:
    provider = SequenceProvider(
        [
            ModelResponse(
                content="",
                finish_reason="tool_calls",
                tool_calls=[ToolCall("call_add", "add", {"a": 2, "b": 5})],
            ),
            ModelResponse(content="done", reasoning_content="thinking"),
        ]
    )
    recorder = EventRecorder()

    result = await ToolCallingRunner().run(
        provider=provider,
        tools=_tools(),
        messages=[{"role": "user", "content": "add"}],
        model="test-model",
        workspace=tmp_path,
        emitter=EventEmitter.from_hooks(
            recorder,
            run_id="run-1",
            session_id="session-1",
        ),
    )

    assert result.final_content == "done"
    kinds = [event.kind for event in recorder.events]
    assert kinds == [
        RUN_STARTED,
        ITERATION_STARTED,
        MODEL_REQUEST_STARTED,
        MODEL_RESPONSE_FINISHED,
        TOOL_CALLS_STARTED,
        TOOL_CALL_STARTED,
        TOOL_CALL_FINISHED,
        TOOL_CALLS_FINISHED,
        ITERATION_FINISHED,
        ITERATION_STARTED,
        MODEL_REQUEST_STARTED,
        MODEL_RESPONSE_FINISHED,
        FINAL_RESULT,
        ITERATION_FINISHED,
        RUN_FINISHED,
    ]
    assert {event.run_id for event in recorder.events} == {"run-1"}
    assert {event.session_id for event in recorder.events} == {"session-1"}
    assert recorder.by_kind(TOOL_CALL_FINISHED)[0].payload["tool_result"]["content"] == "7"
    assert recorder.by_kind(TOOL_CALL_FINISHED)[0].payload["duration_s"] >= 0
    assert recorder.by_kind(FINAL_RESULT)[0].payload == {
        "final_content": "done",
        "stop_reason": "completed",
    }


@pytest.mark.asyncio
async def test_streaming_deltas_are_emitted_inside_the_normal_timeline(tmp_path) -> None:
    recorder = EventRecorder()

    await ToolCallingRunner().run(
        provider=SequenceProvider([ModelResponse(content="hello")]),
        tools=_tools(),
        messages=[{"role": "user", "content": "hello"}],
        model="test-model",
        tool_names=[],
        workspace=tmp_path,
        stream=True,
        emitter=EventEmitter.from_hooks(recorder),
    )

    deltas = recorder.by_kind(MODEL_STREAM_CONTENT_DELTA)
    assert [event.payload for event in deltas] == [{"delta": "hello"}]
    assert recorder.events.index(deltas[0]) < recorder.events.index(
        recorder.by_kind(MODEL_RESPONSE_FINISHED)[0]
    )


@pytest.mark.asyncio
async def test_loop_wraps_runner_events_with_turn_metadata(tmp_path) -> None:
    recorder = EventRecorder()
    loop = AgentLoop(
        tools=_tools(),
        context=ContextBuilder(tmp_path, timezone="UTC"),
        skills=SkillsManager(tmp_path / "skills"),
        runner=ToolCallingRunner(),
    )

    result = await loop.run_turn(
        "hello",
        provider=SequenceProvider([ModelResponse(content="done")]),
        model="test-model",
        workspace=tmp_path,
        tool_names=[],
        hooks=recorder,
        run_id="turn-run",
        session_id="turn-session",
    )

    assert result.final_content == "done"
    assert recorder.events[0].kind == TURN_STARTED
    assert recorder.events[0].payload["message"] == {"role": "user", "content": "hello"}
    assert TURN_CONTEXT_BUILT in [event.kind for event in recorder.events]
    assert recorder.events[-1].kind == TURN_FINISHED
    assert recorder.events[-1].payload == {"stop_reason": "completed"}
    assert {event.run_id for event in recorder.events} == {"turn-run"}
    assert {event.session_id for event in recorder.events} == {"turn-session"}


@pytest.mark.asyncio
async def test_runner_emits_a_terminal_error_before_reraising(tmp_path) -> None:
    class BrokenProvider(ModelProvider):
        async def generate(self, request: ModelRequest) -> ModelResponse:
            raise RuntimeError("provider broke")

    recorder = EventRecorder()
    with pytest.raises(RuntimeError, match="provider broke"):
        await ToolCallingRunner().run(
            provider=BrokenProvider(),
            tools=_tools(),
            messages=[{"role": "user", "content": "hello"}],
            model="test-model",
            tool_names=[],
            workspace=tmp_path,
            emitter=EventEmitter.from_hooks(recorder),
        )

    assert recorder.by_kind(RUN_ERROR)[0].payload == {
        "error_type": "RuntimeError",
        "error_message": "provider broke",
    }
