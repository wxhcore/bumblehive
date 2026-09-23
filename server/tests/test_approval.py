import asyncio
from pathlib import Path

import pytest

from bumblehive.protocols import ToolCall
from bumblehive.protocols.tool_approval import ToolApprovalRequest
from bumblehive.tools import ToolManager
from bumblehive_server.chat.approval import ToolApprovals, approval_details


def request(workspace, name, **arguments):
    return ToolApprovalRequest("call-1", name, arguments, workspace.resolve())


@pytest.mark.parametrize(
    "name",
    ["read_file", "list_dir", "find_files", "grep", "list_exec_sessions", "sub_agent"],
)
def test_reads_and_readonly_subagent_are_automatic(tmp_path, name):
    assert approval_details(request(tmp_path, name, path="/outside")) is None


@pytest.mark.parametrize("name", ["write_file", "edit_file"])
def test_file_scope_matches_resolved_paths(tmp_path, name):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    assert approval_details(request(workspace, name, path="inside.txt")) is None
    assert (
        approval_details(request(workspace, name, path=str(workspace / "inside.txt")))
        is None
    )
    outside = tmp_path / "outside.txt"
    (workspace / "link").symlink_to(outside)
    for path in ["../outside.txt", str(outside), "link"]:
        details = approval_details(request(workspace, name, path=path))
        assert details["outside_paths"] == [str(outside)]
    # Keep whitespace and follow the platform's path resolution semantics.
    raw_path = " ../outside.txt "
    resolved = (workspace / raw_path).resolve()
    details = approval_details(request(workspace, name, path=raw_path))
    if resolved.is_relative_to(workspace.resolve()):
        assert details is None
    else:
        assert details["outside_paths"] == [str(resolved)]


def test_patch_strips_paths_and_approves_dry_run(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    edits = [{"path": "inside.txt"}, {"path": "  ../outside.txt  "}]
    details = approval_details(request(workspace, "apply_patch", edits=edits))
    assert details["paths"] == [
        str(workspace / "inside.txt"),
        str(tmp_path / "outside.txt"),
    ]
    assert details["outside_paths"] == [str(tmp_path / "outside.txt")]
    assert (
        approval_details(request(workspace, "apply_patch", edits=edits, dry_run=True))
        is None
    )


@pytest.mark.parametrize("working_dir", [None, "", ".", ".."])
def test_shell_always_asks_and_displays_effective_directory(tmp_path, working_dir):
    details = approval_details(
        request(tmp_path, "exec", command="pwd", working_dir=working_dir)
    )
    assert details["command"] == "pwd"
    assert Path(details["working_dir"]) == (tmp_path / (working_dir or ".")).resolve()


@pytest.mark.parametrize(
    "arguments,asks",
    [
        ({}, False),
        ({"chars": ""}, False),
        ({"wait_for": "done"}, False),
        ({"terminate": True}, False),
        ({"chars": "\n"}, True),
        ({"close_stdin": True}, True),
        ({"terminate": True, "chars": "exit\n"}, True),
        ({"terminate": True, "close_stdin": True}, True),
    ],
)
def test_stdin_rules(tmp_path, arguments, asks):
    details = approval_details(
        request(tmp_path, "write_stdin", session_id="exec-1", **arguments)
    )
    assert (details is not None) == asks


def test_unknown_tools_ask(tmp_path):
    assert approval_details(request(tmp_path, "mcp_update")) == {"reason": "tool"}


@pytest.mark.asyncio
@pytest.mark.parametrize("approved", [False, True])
@pytest.mark.parametrize("patch", [False, True])
async def test_real_write_waits_for_decision(tmp_path, approved, patch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "outside.txt"
    frames = asyncio.Queue()
    approvals = ToolApprovals("session-1", frames.put)
    call = (
        ToolCall(
            "call-1",
            "apply_patch",
            {
                "edits": [
                    {"path": "inside.txt", "action": "add", "new_text": "hello"},
                    {"path": " ../outside.txt ", "action": "add", "new_text": "hello"},
                ]
            },
        )
        if patch
        else ToolCall(
            "call-1", "write_file", {"path": "../outside.txt", "content": "hello"}
        )
    )
    async with ToolManager() as tools:
        tools.register_builtin_tools()
        task = asyncio.create_task(
            tools.execute_call(call, workspace=workspace, approval_handler=approvals)
        )
        frame = await asyncio.wait_for(frames.get(), 2)
        assert frame["type"] == "approval_request"
        assert frame["workspace"] == str(workspace)
        assert not task.done() and not outside.exists()
        assert not (workspace / "inside.txt").exists()
        await approvals.decide(frame["approval_id"], approved)
        assert (await frames.get())["type"] == "approval_resolved"
        result = await asyncio.wait_for(task, 2)
        assert outside.exists() is approved
        if patch:
            assert (workspace / "inside.txt").exists() is approved
        if approved:
            assert result.error is None
            assert outside.read_text() == ("hello\n" if patch else "hello")
        else:
            assert result.error.code == "tool_approval_denied"
            assert result.error.message == "The user rejected this tool call."
        await approvals.decide(frame["approval_id"], not approved)
        assert frames.empty() and not approvals.pending


@pytest.mark.asyncio
async def test_parallel_approvals_are_isolated_and_cleared(tmp_path):
    frames = asyncio.Queue()
    first = ToolApprovals("first", frames.put)
    second = ToolApprovals("second", frames.put)
    tasks = [
        asyncio.create_task(manager(request(tmp_path, "exec", command="pwd")))
        for manager in (first, first, second)
    ]
    requests = [await asyncio.wait_for(frames.get(), 2) for _ in tasks]
    own = [frame for frame in requests if frame["session_id"] == "first"]
    foreign = next(frame for frame in requests if frame["session_id"] == "second")
    await first.decide(foreign["approval_id"], True)
    assert all(not task.done() for task in tasks)
    await first.decide(own[1]["approval_id"], False)
    assert not (await tasks[1]).approved
    first.clear()
    second.clear()
    results = await asyncio.gather(*tasks, return_exceptions=True)
    assert isinstance(results[0], asyncio.CancelledError)
    assert isinstance(results[2], asyncio.CancelledError)
    assert not first.pending and not second.pending


@pytest.mark.asyncio
async def test_full_access_skips_confirmation(tmp_path):
    frames = asyncio.Queue()
    approvals = ToolApprovals("session-1", frames.put, "full_access")
    for name, arguments in [
        ("write_file", {"path": "../outside.txt"}),
        ("exec", {"command": "pwd"}),
        ("write_stdin", {"chars": "exit\n"}),
        ("custom_tool", {}),
    ]:
        assert (await approvals(request(tmp_path, name, **arguments))).approved
    assert frames.empty() and not approvals.pending


def test_chat_approval_mode_defaults_and_validation():
    from pydantic import ValidationError
    from bumblehive_server.schemas import ChatRequest

    assert ChatRequest(content="hello").approval_mode == "request"
    assert ChatRequest(content="hello", approval_mode="full_access").approval_mode == "full_access"
    with pytest.raises(ValidationError):
        ChatRequest(content="hello", approval_mode="unknown")
