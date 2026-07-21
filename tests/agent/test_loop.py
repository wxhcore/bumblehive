from typing import Any

import pytest

from bumblehive.agent import (
    AgentLoop,
    ContextBuilder,
    MessageHistory,
    ToolCallingRunner,
)
from bumblehive.protocols import GenerationConfig, ToolCall
from bumblehive.protocols.errors import AgentError
from bumblehive.providers import ModelProvider, ModelRequest, ModelResponse
from bumblehive.skills import SkillsManager
from bumblehive.tools import PathAllowlist, ToolManager
from bumblehive.tools.scope import current_tool_path_scope, current_tool_session_id


class SequenceProvider(ModelProvider):
    def __init__(self, responses: list[ModelResponse]) -> None:
        self.responses = list(responses)
        self.requests: list[ModelRequest] = []

    async def generate(self, request: ModelRequest) -> ModelResponse:
        self.requests.append(request)
        return self.responses.pop(0)


def _call(name: str, arguments: dict[str, Any] | None = None) -> ToolCall:
    return ToolCall(id=f"call_{name}", name=name, arguments=arguments or {})


def _write_skill(root, name: str) -> None:
    directory = root / name
    directory.mkdir(parents=True)
    (directory / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {name} skill.\n---\n",
        encoding="utf-8",
    )


def _loop(tmp_path, tools, skills) -> AgentLoop:
    return AgentLoop(
        tools=tools,
        context=ContextBuilder(tmp_path, timezone="UTC"),
        skills=skills,
        runner=ToolCallingRunner(),
    )


@pytest.mark.asyncio
async def test_run_turn_composes_context_capabilities_and_execution_scope(
    tmp_path,
) -> None:
    skills_dir = tmp_path / "skills"
    _write_skill(skills_dir, "audit")
    _write_skill(skills_dir, "unused")
    skills = SkillsManager(skills_dir)
    tools = ToolManager()
    observed: dict[str, Any] = {}

    @tools.tool
    def scope_info() -> dict[str, Any]:
        """Return the current execution scope."""
        scope = current_tool_path_scope()
        assert scope is not None
        observed.update(
            workspace=scope.workspace,
            allowlist=scope.path_allowlist,
            session_id=current_tool_session_id(),
        )
        return {"workspace": scope.workspace.as_posix()}

    @tools.tool
    def hidden() -> str:
        """A tool that is not selected."""
        return "hidden"

    provider = SequenceProvider(
        [
            ModelResponse(
                content="",
                finish_reason="tool_calls",
                tool_calls=[_call("scope_info")],
            ),
            ModelResponse(content="done"),
        ]
    )
    generation = GenerationConfig(max_completion_tokens=123, temperature=0.2)
    allowlist = PathAllowlist.from_roots(extra_write_roots=[skills_dir])

    result = await _loop(tmp_path, tools, skills).run_turn(
        "inspect",
        provider=provider,
        model="test-model",
        generation=generation,
        workspace=tmp_path,
        path_allowlist=allowlist,
        timezone="Asia/Shanghai",
        dynamic_context={"active_file": "src/bumblehive/agent/loop.py"},
        skill_names=["audit"],
        tool_names=["scope_info"],
        session_id="session-a",
    )

    request = provider.requests[0]
    assert request.model == "test-model"
    assert request.generation == generation
    assert [tool["function"]["name"] for tool in request.tools] == ["scope_info"]
    assert "<name>audit</name>" in request.messages[0]["content"]
    assert "<name>unused</name>" not in request.messages[0]["content"]
    assert "(Asia/Shanghai, UTC+08:00)" in request.messages[-1]["content"]
    assert (
        "<active_file>src/bumblehive/agent/loop.py</active_file>"
        in request.messages[-1]["content"]
    )
    assert observed == {
        "workspace": tmp_path.resolve(),
        "allowlist": allowlist,
        "session_id": "session-a",
    }
    assert current_tool_session_id() is None
    assert result.final_content == "done"
    assert result.tools_used == ["scope_info"]


@pytest.mark.asyncio
async def test_run_turn_updates_caller_history_without_retaining_it(tmp_path) -> None:
    history = MessageHistory(
        [
            {"role": "user", "content": "earlier question"},
            {"role": "assistant", "content": "earlier answer"},
        ]
    )
    provider = SequenceProvider(
        [ModelResponse(content="first answer"), ModelResponse(content="second answer")]
    )
    loop = _loop(tmp_path, ToolManager(), SkillsManager(tmp_path / "skills"))

    await loop.run_turn(
        "first question",
        provider=provider,
        model="test-model",
        history=history,
        workspace=tmp_path,
        dynamic_context={"turn": 1},
    )
    await loop.run_turn(
        "second question",
        provider=provider,
        model="test-model",
        workspace=tmp_path,
        dynamic_context={"turn": 2},
    )

    assert [message["role"] for message in provider.requests[0].messages] == [
        "system",
        "user",
        "assistant",
        "user",
    ]
    assert [message["role"] for message in provider.requests[1].messages] == [
        "system",
        "user",
    ]
    assert history.get_history() == [
        {"role": "user", "content": "earlier question"},
        {"role": "assistant", "content": "earlier answer"},
        {"role": "user", "content": "first question"},
        {"role": "assistant", "content": "first answer"},
    ]


@pytest.mark.asyncio
async def test_history_provides_a_stable_tool_session_id(tmp_path) -> None:
    tools = ToolManager()
    observed: list[str | None] = []

    @tools.tool
    def observe_scope() -> str:
        """Return the current tool session id."""
        current = current_tool_session_id()
        observed.append(current)
        return current or ""

    provider = SequenceProvider(
        [
            ModelResponse(
                content="",
                finish_reason="tool_calls",
                tool_calls=[ToolCall("scope-1", "observe_scope", {})],
            ),
            ModelResponse(content="first answer"),
            ModelResponse(
                content="",
                finish_reason="tool_calls",
                tool_calls=[ToolCall("scope-2", "observe_scope", {})],
            ),
            ModelResponse(content="second answer"),
        ]
    )
    loop = _loop(tmp_path, tools, SkillsManager(tmp_path / "skills"))
    history = MessageHistory(conversation_id="conversation-a")

    await loop.run_turn(
        "first",
        provider=provider,
        model="test-model",
        history=history,
        workspace=tmp_path,
        tool_names=["observe_scope"],
    )
    await loop.run_turn(
        "second",
        provider=provider,
        model="test-model",
        history=history,
        workspace=tmp_path,
        tool_names=["observe_scope"],
    )

    assert observed == ["conversation-a", "conversation-a"]


@pytest.mark.asyncio
async def test_history_preserves_tool_message_order_across_turns(tmp_path) -> None:
    tools = ToolManager()

    @tools.tool
    def echo(value: str) -> str:
        """Return the provided value."""
        return value

    provider = SequenceProvider(
        [
            ModelResponse(
                content="",
                finish_reason="tool_calls",
                tool_calls=[_call("echo", {"value": "tool output"})],
            ),
            ModelResponse(content="first answer"),
            ModelResponse(content="second answer"),
        ]
    )
    loop = _loop(tmp_path, tools, SkillsManager(tmp_path / "skills"))
    history = MessageHistory()

    await loop.run_turn(
        "first question",
        provider=provider,
        model="test-model",
        history=history,
        workspace=tmp_path,
        dynamic_context={"turn": 1},
        tool_names=["echo"],
    )
    assert [message["role"] for message in history.get_history()] == [
        "user",
        "assistant",
        "tool",
        "assistant",
    ]

    await loop.run_turn(
        "second question",
        provider=provider,
        model="test-model",
        history=history,
        workspace=tmp_path,
        dynamic_context={"turn": 2},
        tool_names=["echo"],
    )

    second_turn_messages = provider.requests[2].messages
    assert [message["role"] for message in second_turn_messages] == [
        "system",
        "user",
        "assistant",
        "tool",
        "assistant",
        "user",
    ]
    assert second_turn_messages[1]["content"] == "first question"
    assert second_turn_messages[-1]["content"].startswith("second question")
    assert (
        second_turn_messages[2]["tool_calls"][0]["id"]
        == second_turn_messages[3]["tool_call_id"]
    )

    stored_messages = history.get_history()
    assert [message["role"] for message in stored_messages] == [
        "user",
        "assistant",
        "tool",
        "assistant",
        "user",
        "assistant",
    ]
    assert [
        message["content"]
        for message in stored_messages
        if message["role"] == "user"
    ] == ["first question", "second question"]


@pytest.mark.asyncio
async def test_run_turn_rejects_ambiguous_history_sources(tmp_path) -> None:
    loop = _loop(tmp_path, ToolManager(), SkillsManager(tmp_path / "skills"))
    provider = SequenceProvider([])
    history = MessageHistory()

    with pytest.raises(ValueError, match="history and history_messages"):
        await loop.run_turn(
            "both histories",
            provider=provider,
            model="test-model",
            history=history,
            history_messages=[],
        )
    with pytest.raises(ValueError, match="history and session_id"):
        await loop.run_turn(
            "local and managed",
            provider=provider,
            model="test-model",
            history=history,
            session_id="managed",
        )
    with pytest.raises(ValueError, match="history_messages requires session_id"):
        await loop.run_turn(
            "unscoped snapshot",
            provider=provider,
            model="test-model",
            history_messages=[],
        )


@pytest.mark.asyncio
async def test_run_turn_enforces_tool_selection_and_preserves_error_boundary(
    tmp_path,
) -> None:
    tools = ToolManager()

    @tools.tool
    def allowed() -> str:
        """Allowed tool."""
        return "ok"

    @tools.tool
    def blocked() -> str:
        """Blocked tool."""
        return "not reached"

    provider = SequenceProvider(
        [
            ModelResponse(
                content="",
                finish_reason="tool_calls",
                tool_calls=[_call("blocked")],
            ),
            ModelResponse(content="handled"),
        ]
    )

    result = await _loop(
        tmp_path,
        tools,
        SkillsManager(tmp_path / "skills"),
    ).run_turn(
        "run it",
        provider=provider,
        model="test-model",
        workspace=tmp_path,
        tool_names=["allowed"],
    )

    assert [tool["function"]["name"] for tool in provider.requests[0].tools] == [
        "allowed"
    ]
    assert result.final_content == "handled"
    assert result.tools_used == []
    tool_message = next(
        message for message in result.messages if message["role"] == "tool"
    )
    assert '"code": "tool_not_allowed"' in tool_message["content"]


@pytest.mark.asyncio
async def test_model_error_closes_the_turn_for_following_history(tmp_path) -> None:
    provider = SequenceProvider(
        [
            ModelResponse(
                content="failed",
                finish_reason="error",
                error=AgentError(code="model_error", message="failed"),
            ),
            ModelResponse(content="recovered"),
        ]
    )
    loop = _loop(tmp_path, ToolManager(), SkillsManager(tmp_path / "skills"))
    history = MessageHistory()

    await loop.run_turn(
        "first",
        provider=provider,
        model="test-model",
        history=history,
        workspace=tmp_path,
    )
    await loop.run_turn(
        "second",
        provider=provider,
        model="test-model",
        history=history,
        workspace=tmp_path,
    )

    assert provider.requests[1].messages[2]["role"] == "assistant"
    assert "model error" in provider.requests[1].messages[2]["content"].lower()
