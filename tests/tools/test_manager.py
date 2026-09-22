import asyncio

import pytest

from bumblehive.protocols import ToolCall
from bumblehive.tools import ToolApprovalDecision, ToolManager


BUILTINS = [
    "read_file",
    "write_file",
    "list_dir",
    "find_files",
    "grep",
    "edit_file",
    "apply_patch",
    "exec",
    "write_stdin",
    "list_exec_sessions",
]


def _call(call_id, name, arguments=None):
    return ToolCall(call_id, name, arguments or {})


@pytest.mark.asyncio
async def test_manager_owns_registration_discovery_filtering_and_execution() -> None:
    manager = ToolManager()

    @manager.tool(parallel_safe=True)
    def add(a: int, b: int) -> int:
        """Add two integers."""
        return a + b

    assert manager.register_builtin_tools() == BUILTINS
    assert manager.register_builtin_tools() == []
    assert manager.tool_names == ["add", *sorted(BUILTINS)]
    assert manager.get_tool("add").parallel_safe is True
    assert [tool.name for tool in manager.get_tools(["add", "read_file"])] == [
        "add",
        "read_file",
    ]
    assert [item["function"]["name"] for item in manager.get_openai_tool_definitions(["add"])] == [
        "add"
    ]

    allowed, blocked = await manager.execute_many(
        [_call("add", "add", {"a": "2", "b": 5}), _call("read", "read_file", {"path": "x"})],
        tool_names=["add"],
    )
    assert allowed.content == 7
    assert blocked.error is not None and blocked.error.code == "tool_not_allowed"

    manager.unregister("add")
    assert manager.get_tool("add") is None
    with pytest.raises(ValueError, match="Unknown tools"):
        manager.get_openai_tool_definitions(["add"])


@pytest.mark.asyncio
async def test_manager_does_not_approve_unexposed_tools() -> None:
    manager = ToolManager()
    approvals: list[str] = []

    @manager.tool
    def hidden() -> str:
        """A tool omitted from the model request."""
        return "hidden"

    async def approve(request):
        approvals.append(request.call_id)
        return ToolApprovalDecision.approve()

    result = await manager.execute_call(
        _call("hidden", "hidden"),
        tool_names=[],
        approval_handler=approve,
    )

    assert result.error is not None
    assert result.error.code == "tool_not_allowed"
    assert approvals == []


@pytest.mark.asyncio
async def test_concurrent_manager_calls_keep_workspaces_isolated(tmp_path) -> None:
    from bumblehive.tools.scope import current_tool_workspace

    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    for directory, content in ((first_root, "first"), (second_root, "second")):
        directory.mkdir()
        (directory / "notes.txt").write_text(content, encoding="utf-8")
    manager = ToolManager()
    manager.register_builtin_tools()

    async def approve(request):
        before = current_tool_workspace()
        await asyncio.sleep(0)
        assert current_tool_workspace() == before
        return ToolApprovalDecision.approve()

    results = await asyncio.gather(*(
        manager.execute_call(
            _call(label, "read_file", {"path": "notes.txt"}),
            workspace=directory,
            approval_handler=approve,
        )
        for label, directory in (("first", first_root), ("second", second_root))
    ))

    assert results[0].content["content"] == "1| first"
    assert results[1].content["content"] == "1| second"
    assert current_tool_workspace() is None


@pytest.mark.asyncio
@pytest.mark.parametrize("approved", [True, False])
@pytest.mark.parametrize("relative", [True, False])
async def test_approval_controls_writing_outside_workspace(tmp_path, approved, relative):
    from bumblehive.tools.scope import current_tool_workspace

    workspace = tmp_path / "workspace"
    target = tmp_path / "outside.txt"
    path = "../outside.txt" if relative else str(target)
    manager = ToolManager()
    manager.register_builtin_tools()
    requests = []

    async def decide(request):
        requests.append(request)
        return ToolApprovalDecision.approve() if approved else ToolApprovalDecision.reject()

    result = await manager.execute_call(
        _call("write", "write_file", {"path": path, "content": "approved"}),
        workspace=workspace,
        approval_handler=decide,
    )

    assert len(requests) == 1
    assert requests[0].arguments == {"path": path, "content": "approved"}
    assert current_tool_workspace() is None
    if approved:
        assert result.error is None
        assert result.content["success"] is True
        assert target.read_text(encoding="utf-8") == "approved"
    else:
        assert result.error.code == "tool_approval_denied"
        assert not target.exists()
