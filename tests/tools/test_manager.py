import asyncio

import pytest

from bumblehive.protocols import ToolCall
from bumblehive.tools import ToolPathPolicy, ToolManager


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
async def test_manager_applies_workspace_read_and_write_roots_to_builtins(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    read_root = tmp_path / "read"
    write_root = tmp_path / "write"
    for path in (workspace, read_root, write_root):
        path.mkdir()
    (workspace / "workspace.txt").write_text("workspace", encoding="utf-8")
    source = read_root / "source.txt"
    source.write_text("read-only", encoding="utf-8")
    target = write_root / "target.txt"
    manager = ToolManager()
    manager.register_builtin_tools()
    policy = ToolPathPolicy.from_roots(
        extra_read_roots=[read_root],
        extra_write_roots=[write_root],
    )

    results = await manager.execute_many(
        [
            _call("workspace", "read_file", {"path": "workspace.txt"}),
            _call("read", "read_file", {"path": str(source)}),
            _call("blocked", "write_file", {"path": str(read_root / "blocked.txt"), "content": "no"}),
            _call("write", "write_file", {"path": str(target), "content": "yes"}),
            _call("read-write", "read_file", {"path": str(target)}),
        ],
        workspace=workspace,
        path_policy=policy,
    )

    assert "workspace" in results[0].content["content"]
    assert "read-only" in results[1].content["content"]
    assert results[2].content == {"error": "path is outside writable roots"}
    assert target.read_text(encoding="utf-8") == "yes"
    assert "yes" in results[4].content["content"]


@pytest.mark.asyncio
async def test_concurrent_manager_calls_keep_run_scopes_isolated(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    for path in (workspace, first_root, second_root):
        path.mkdir()
    first = first_root / "notes.txt"
    second = second_root / "notes.txt"
    first.write_text("first root", encoding="utf-8")
    second.write_text("second root", encoding="utf-8")
    manager = ToolManager()
    manager.register_builtin_tools()

    first_result, second_result = await asyncio.gather(
        manager.execute_call(
            _call("first", "read_file", {"path": str(first)}),
            workspace=workspace,
            path_policy=ToolPathPolicy.from_roots(extra_read_roots=[first_root]),
        ),
        manager.execute_call(
            _call("second", "read_file", {"path": str(second)}),
            workspace=workspace,
            path_policy=ToolPathPolicy.from_roots(extra_read_roots=[second_root]),
        ),
    )

    assert "first root" in first_result.content["content"]
    assert "second root" in second_result.content["content"]
