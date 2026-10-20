import runpy
import asyncio
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).parents[1]
EXAMPLE_FILES = sorted((ROOT / "examples").glob("*/*.py"))
LOCAL_EXAMPLES = [
    ROOT / "examples/tools/basic.py",
    ROOT / "examples/tools/builtins.py",
    ROOT / "examples/skills/basic.py",
]


@pytest.mark.parametrize("path", EXAMPLE_FILES, ids=lambda path: path.stem)
def test_example_imports(path: Path) -> None:
    runpy.run_path(str(path))


@pytest.mark.parametrize("path", LOCAL_EXAMPLES, ids=lambda path: path.stem)
def test_local_example_runs(path: Path) -> None:
    completed = subprocess.run(
        [sys.executable, str(path)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "answers,options,expected",
    [
        (["1"], ["初学者", "开发者"], {"status": "answered", "answer": "初学者"}),
        (["小学生"], ["初学者"], {"status": "answered", "answer": "小学生"}),
        (["", "技术团队"], None, {"status": "answered", "answer": "技术团队"}),
        (["/skip"], None, {"status": "skipped"}),
    ],
)
async def test_question_example_input(monkeypatch, answers, options, expected):
    from examples.runtime.ask_user import read_answer

    inputs = iter(answers)
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))
    assert await read_answer("面向谁？", options) == expected


@pytest.mark.asyncio
@pytest.mark.parametrize("wait_seconds", [None, 1])
async def test_background_example_returns_fast_result_once(wait_seconds):
    from examples.runtime.background_support import BackgroundTools

    notifications = []
    jobs = BackgroundTools(lambda task_id, value: notifications.append(value))

    async def work():
        return {"answer": 42}

    try:
        assert await jobs.submit(work(), wait_seconds=wait_seconds) == {"answer": 42}
        await jobs.drain()
        assert notifications == []
    finally:
        await jobs.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("wait_seconds", [0, 0.001])
@pytest.mark.parametrize("fails", [False, True])
async def test_background_example_keeps_work_and_delivers_once(wait_seconds, fails):
    from examples.runtime.background_support import BackgroundTools

    release = asyncio.Event()
    notifications = []
    jobs = BackgroundTools(lambda task_id, value: notifications.append((task_id, value)))

    async def work():
        await release.wait()
        if fails:
            raise ValueError("查询失败")
        return {"answer": 42}

    try:
        pending = await jobs.submit(work(), wait_seconds=wait_seconds)
        assert pending["status"] == "pending"
        assert not jobs.tasks[0].done()
        release.set()
        await jobs.drain()
        expected = {"status": "error", "message": "查询失败"} if fails else {"answer": 42}
        assert notifications == [(pending["task_id"], expected)]
        await jobs.drain()
        assert len(notifications) == 1
    finally:
        await jobs.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("delivery", ["during_run", "after_run"])
async def test_background_example_continues_real_runtime(monkeypatch, delivery):
    """Use the actual tool loop and history; only replace the external model."""
    import bumblehive
    from bumblehive.protocols import ToolCall
    from bumblehive.providers import ModelProvider, ModelResponse
    from bumblehive.providers import manager
    from examples.runtime.background_support import BackgroundTools, Conversation

    waiting = asyncio.Event()
    release = asyncio.Event()
    requests = []

    class Provider(ModelProvider):
        def __init__(self, **kwargs):
            pass

        async def generate(self, request):
            requests.append(request)
            if len(requests) == 1:
                return ModelResponse(
                    content="",
                    finish_reason="tool_calls",
                    tool_calls=[ToolCall("example-call", "lookup", {})],
                )
            if len(requests) == 2 and delivery == "during_run":
                release.set()
                await waiting.wait()
            return ModelResponse(content="已收到结果" if len(requests) > 2 else "先做其他工作")

    monkeypatch.setattr(manager, "OpenAIChatCompletionsProvider", Provider)
    conversation = Conversation()

    def notify(task_id, value):
        conversation.notify(task_id, value)
        waiting.set()

    class Jobs(BackgroundTools):
        async def drain(self):
            if delivery == "after_run":
                release.set()
            await super().drain()

    jobs = Jobs(notify)
    config = bumblehive.RuntimeArguments(
        model="offline", api_key="test", tool_names=["lookup"], skill_names=[],
    )
    async with bumblehive.from_config(config) as runtime:
        @runtime.tools.tool(description="测试后台查询")
        async def lookup() -> dict:
            async def work():
                await release.wait()
                return {"answer": "UNIQUE_LATE_ANSWER"}
            return await jobs.submit(work(), wait_seconds=0)

        result = await asyncio.wait_for(
            conversation.run(runtime, "查询数据", jobs), timeout=5,
        )

    assert result.error is None
    assert len(requests) == 3
    messages = requests[-1].messages
    late = [m for m in messages if m["role"] == "user" and "UNIQUE_LATE_ANSWER" in str(m)]
    assert len(late) == 1
    tool_results = [m for m in messages if m["role"] == "tool"]
    assert len(tool_results) == 1
    assert "pending" in tool_results[0]["content"]


@pytest.mark.asyncio
@pytest.mark.parametrize("late", [False, True])
@pytest.mark.parametrize("skipped", [False, True])
async def test_timeout_question_example(monkeypatch, late, skipped):
    import json
    from bumblehive.protocols import ToolCall
    from bumblehive.providers import ModelProvider, ModelResponse, manager
    from examples.runtime import ask_user_timeout as example

    release = asyncio.Event()
    requests = []

    class Provider(ModelProvider):
        def __init__(self, **kwargs):
            pass

        async def generate(self, request):
            requests.append(request)
            if len(requests) == 1:
                return ModelResponse(
                    content="", finish_reason="tool_calls",
                    tool_calls=[ToolCall("question", "ask_user", {
                        "question": "面向谁？", "options": ["初学者"],
                    })],
                )
            release.set()
            return ModelResponse(content="完成")

    async def answer(question, options):
        if late:
            await release.wait()
        return {"status": "skipped"} if skipped else {
            "status": "answered", "answer": "UNIQUE_READER",
        }

    for name in ("MODEL", "API_KEY", "BASE_URL"):
        monkeypatch.setenv(f"BUMBLEHIVE_{name}", "offline")
    monkeypatch.setattr(manager, "OpenAIChatCompletionsProvider", Provider)
    monkeypatch.setattr(example, "read_answer", answer)
    monkeypatch.setattr(example, "WAIT_SECONDS", 0.001)
    await asyncio.wait_for(example.main(), timeout=5)
    tool_messages = [m for m in requests[1].messages if m["role"] == "tool"]
    assert len(tool_messages) == 1
    tool_result = json.loads(tool_messages[0]["content"])
    assert tool_result["status"] == (
        "pending" if late else "skipped" if skipped else "answered"
    )
    # Late skip closes silently; late answer is delivered exactly once.
    assert len(requests) == (3 if late and not skipped else 2)
    if late and not skipped:
        assert sum(
            m["role"] == "user" and "UNIQUE_READER" in str(m)
            for m in requests[-1].messages
        ) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("allowed", [False, True])
async def test_approval_example_writes_only_after_approval(monkeypatch, tmp_path, allowed):
    import importlib
    import bumblehive
    from bumblehive.protocols import ToolCall
    from bumblehive.providers import ModelProvider, ModelResponse, manager

    example = importlib.import_module("examples.runtime.tool_approval")
    requests = []

    class Provider(ModelProvider):
        def __init__(self, **kwargs):
            pass

        async def generate(self, request):
            requests.append(request)
            if len(requests) == 1:
                return ModelResponse(
                    content="", finish_reason="tool_calls",
                    tool_calls=[ToolCall("write", "write_file", {
                        "path": "approval-demo.txt", "content": "hello",
                    })],
                )
            return ModelResponse(content="完成")

    original = bumblehive.from_config

    def create(config):
        config = config.to_config().to_dict()
        config["runtime"]["workspace"] = str(tmp_path)
        return original(config)

    for name in ("MODEL", "API_KEY", "BASE_URL"):
        monkeypatch.setenv(f"BUMBLEHIVE_{name}", "offline")
    monkeypatch.setattr(manager, "OpenAIChatCompletionsProvider", Provider)
    monkeypatch.setattr(bumblehive, "from_config", create)
    monkeypatch.setattr("builtins.input", lambda _: "y" if allowed else "n")
    await example.main()
    output = tmp_path / "approval-demo.txt"
    assert output.exists() == allowed
    if allowed:
        assert output.read_text() == "hello"
    else:
        assert "tool_approval_denied" in str(requests[-1].messages)
