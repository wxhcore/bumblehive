import asyncio
from pathlib import Path
from typing import Any

import pytest

from bumblehive.agent import ToolCallingRunner
from bumblehive.protocols import GenerationConfig, ToolCall
from bumblehive.protocols.errors import AgentError
from bumblehive.providers import ModelProvider, ModelRequest, ModelResponse
from bumblehive.tools import CallableTool, ToolManager


class SequenceProvider(ModelProvider):
    def __init__(self, responses: list[ModelResponse]) -> None:
        self.responses = list(responses)
        self.requests: list[ModelRequest] = []

    async def generate(self, request: ModelRequest) -> ModelResponse:
        self.requests.append(request)
        return self.responses.pop(0)


def _call(name: str, arguments: dict[str, Any] | None = None) -> ToolCall:
    return ToolCall(id=f"call_{name}", name=name, arguments=arguments or {})


def _tools() -> ToolManager:
    tools = ToolManager()

    @tools.tool
    def add(a: int, b: int) -> int:
        """Add two integers."""
        return a + b

    @tools.tool
    def explode() -> None:
        """Raise an execution error."""
        raise RuntimeError("boom")

    return tools


@pytest.mark.asyncio
async def test_run_returns_a_final_response_and_checkpoints(tmp_path) -> None:
    provider = SequenceProvider(
        [ModelResponse(content="hello", usage={"prompt_tokens": 3, "completion_tokens": 2})]
    )
    generation = GenerationConfig(max_completion_tokens=123, temperature=0.1)
    checkpoints: list[list[dict[str, Any]]] = []

    async def checkpoint(messages):
        checkpoints.append(messages)

    original = [{"role": "user", "content": "say hello"}]
    result = await ToolCallingRunner().run(
        provider=provider,
        tools=_tools(),
        messages=original,
        model="test-model",
        generation=generation,
        tool_names=[],
        workspace=tmp_path,
        checkpoint_callback=checkpoint,
    )

    assert result.final_content == "hello"
    assert result.stop_reason == "completed"
    assert result.usage == {"prompt_tokens": 3, "completion_tokens": 2}
    assert result.messages[-1] == {"role": "assistant", "content": "hello"}
    assert provider.requests[0].generation == generation
    assert provider.requests[0].tools == []
    assert checkpoints == [result.messages]
    assert original == [{"role": "user", "content": "say hello"}]


@pytest.mark.asyncio
async def test_run_executes_multiple_tool_iterations_and_returns_errors_to_model(tmp_path) -> None:
    provider = SequenceProvider(
        [
            ModelResponse(
                content="",
                finish_reason="tool_calls",
                tool_calls=[_call("add", {"a": "2", "b": 5})],
                usage={"prompt_tokens": 10},
            ),
            ModelResponse(
                content="",
                finish_reason="tool_calls",
                tool_calls=[_call("explode")],
                usage={"prompt_tokens": 4},
            ),
            ModelResponse(content="handled", usage={"completion_tokens": 8}),
        ]
    )

    result = await ToolCallingRunner().run(
        provider=provider,
        tools=_tools(),
        messages=[{"role": "user", "content": "run both"}],
        model="test-model",
        workspace=tmp_path,
    )

    tool_messages = [message for message in result.messages if message["role"] == "tool"]
    assert tool_messages[0]["content"] == "7"
    assert '"code": "tool_execution_error"' in tool_messages[1]["content"]
    assert "boom" in tool_messages[1]["content"]
    assert result.final_content == "handled"
    assert result.tools_used == ["add"]
    assert result.usage == {"prompt_tokens": 14, "completion_tokens": 8}
    assert provider.requests[-1].messages[-1] == tool_messages[-1]


@pytest.mark.asyncio
async def test_one_model_turn_runs_safe_tools_concurrently_and_checkpoints_ordered_results(
    tmp_path,
) -> None:
    tools = ToolManager()
    both_started = asyncio.Event()
    started: list[str] = []

    async def concurrent_read(*, value: str) -> str:
        started.append(value)
        if len(started) == 2:
            both_started.set()
        await asyncio.wait_for(both_started.wait(), timeout=1)
        return value

    parameters = {
        "type": "object",
        "properties": {"value": {"type": "string"}},
        "required": ["value"],
        "additionalProperties": False,
    }
    for name in ("read_first", "read_second"):
        tools.register(
            CallableTool(
                name=name,
                description=name,
                parameters=parameters,
                handler=concurrent_read,
                read_only=True,
            )
        )

    @tools.tool
    def fail_after_reads() -> None:
        """Fail after the concurrent read batch."""
        raise RuntimeError("expected failure")

    calls = [
        ToolCall("call-1", "read_first", {"value": "first"}),
        ToolCall("call-2", "read_second", {"value": "second"}),
        ToolCall("call-3", "fail_after_reads", {}),
    ]
    provider = SequenceProvider(
        [
            ModelResponse(content="", finish_reason="tool_calls", tool_calls=calls),
            ModelResponse(content="done"),
        ]
    )
    checkpoints: list[list[dict[str, Any]]] = []

    async def checkpoint(messages):
        checkpoints.append(messages)

    result = await ToolCallingRunner().run(
        provider=provider,
        tools=tools,
        messages=[{"role": "user", "content": "run all"}],
        model="test-model",
        workspace=tmp_path,
        checkpoint_callback=checkpoint,
    )

    tool_messages = [
        message for message in provider.requests[1].messages
        if message["role"] == "tool"
    ]
    assert started == ["first", "second"]
    assert [message["tool_call_id"] for message in tool_messages] == [
        "call-1",
        "call-2",
        "call-3",
    ]
    assert [message["content"] for message in tool_messages[:2]] == [
        "first",
        "second",
    ]
    assert '"code": "tool_execution_error"' in tool_messages[2]["content"]
    assert [message["role"] for message in checkpoints[0]] == ["user", "assistant"]
    assert [message["role"] for message in checkpoints[1][-3:]] == ["tool"] * 3
    assert checkpoints[-1] == result.messages
    assert result.tools_used == ["read_first", "read_second"]


@pytest.mark.asyncio
async def test_run_uses_tool_names_for_discovery_and_execution(tmp_path) -> None:
    provider = SequenceProvider(
        [
            ModelResponse(
                content="",
                finish_reason="tool_calls",
                tool_calls=[_call("explode")],
            ),
            ModelResponse(content="done"),
        ]
    )

    result = await ToolCallingRunner().run(
        provider=provider,
        tools=_tools(),
        messages=[{"role": "user", "content": "run it"}],
        model="test-model",
        tool_names=["add"],
        workspace=tmp_path,
    )

    assert [tool["function"]["name"] for tool in provider.requests[0].tools] == ["add"]
    tool_message = next(message for message in result.messages if message["role"] == "tool")
    assert '"code": "tool_not_allowed"' in tool_message["content"]


@pytest.mark.asyncio
async def test_run_returns_a_structured_model_error(tmp_path) -> None:
    error = AgentError(code="model_error", message="provider failed", recoverable=False)
    provider = SequenceProvider(
        [ModelResponse(content="provider failed", finish_reason="error", error=error)]
    )

    result = await ToolCallingRunner().run(
        provider=provider,
        tools=_tools(),
        messages=[{"role": "user", "content": "hello"}],
        model="test-model",
        tool_names=[],
        workspace=tmp_path,
    )

    assert result.final_content == "provider failed"
    assert result.stop_reason == "model_error"
    assert result.error == error
    assert result.messages[-1]["role"] == "assistant"
    assert "model error" in result.messages[-1]["content"].lower()


@pytest.mark.asyncio
async def test_run_stops_at_the_configured_iteration_limit(tmp_path) -> None:
    provider = SequenceProvider(
        [
            ModelResponse(
                content="",
                finish_reason="tool_calls",
                tool_calls=[_call("add", {"a": 1, "b": 1})],
            )
            for _ in range(2)
        ]
    )

    result = await ToolCallingRunner().run(
        provider=provider,
        tools=_tools(),
        messages=[{"role": "user", "content": "keep going"}],
        model="test-model",
        workspace=Path(tmp_path),
        max_iterations=2,
    )

    assert result.stop_reason == "max_iterations"
    assert result.error is not None and result.error.code == "max_iterations"
    assert len(provider.requests) == 2
    assert result.messages[-1] == {"role": "assistant", "content": result.final_content}
