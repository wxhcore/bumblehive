import asyncio
import subprocess
import sys

import pytest

from bumblehive.protocols import ToolCall
from bumblehive.tools import PathAllowlist, ToolManager
from bumblehive.tools.builtins.shell import ExecSession, _build_env, _resolve_shell
from bumblehive.tools.scope import bind_tool_session, reset_tool_session


def _manager(*, timeout=30):
    manager = ToolManager(builtin_config={"exec": {"timeout": timeout}})
    manager.register_builtin_tools()
    return manager


def _long_command(seconds):
    if sys.platform == "win32":
        return (
            "powershell -NoProfile -Command "
            f'"Write-Output ready; Start-Sleep -Seconds {seconds}"'
        )
    return f"printf 'ready\\n'; sleep {seconds}"


def _delayed_command():
    if sys.platform == "win32":
        code = (
            "import time; "
            "print('ready', flush=True); "
            "time.sleep(0.2); "
            "print('done', flush=True)"
        )
        return subprocess.list2cmdline(["python", "-u", "-c", code])
    return "printf 'ready\n'; sleep 0.2; printf 'done\n'"


def _interactive_command():
    return (
        "printf 'ready\\n'; "
        "IFS= read line; printf 'got:%s\\n' \"$line\"; "
        "cat >/dev/null; printf 'eof\\n'"
    )


async def _execute(
    manager,
    workspace,
    name,
    arguments=None,
    *,
    session_id=None,
    allowlist=PathAllowlist(),
):
    token = bind_tool_session(session_id)
    try:
        return await manager.execute_call(
            ToolCall(f"call-{name}", name, arguments or {}),
            workspace=workspace,
            path_allowlist=allowlist,
        )
    finally:
        reset_tool_session(token)


@pytest.mark.parametrize(
    "arguments",
    [{}, {"command": "echo hello", "unexpected": True}],
)
def test_exec_schema_requires_the_current_explicit_interface(arguments) -> None:
    prepared = _manager().registry.prepare_call("exec", arguments)
    assert prepared.error_code == "invalid_tool_arguments"


@pytest.mark.asyncio
async def test_session_poll_waits_for_early_process_completion() -> None:
    class CompletingProcess:
        returncode = None
        stdin = None
        stdout = None
        stderr = None

        def __init__(self) -> None:
            self.wait_calls = 0

        async def wait(self) -> int:
            self.wait_calls += 1
            self.returncode = 0
            return 0

    process = CompletingProcess()
    session = ExecSession(
        session_id="test-session",
        process=process,
        command="complete",
        cwd=".",
        timeout=None,
        owner_session_id=None,
    )
    try:
        poll = await session.poll(yield_time_ms=50, max_output_chars=1_000)

        assert process.wait_calls == 1
        assert poll.done is True
        assert poll.exit_code == 0
    finally:
        await asyncio.gather(
            session._stdout_task,
            session._stderr_task,
            return_exceptions=True,
        )


@pytest.mark.asyncio
async def test_exec_runs_commands_and_enforces_working_directory_safety(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    extra = tmp_path / "skills"
    read_only = tmp_path / "reference"
    workspace.mkdir()
    extra.mkdir()
    read_only.mkdir()
    if sys.platform == "win32":
        script = extra / "run.cmd"
        script.write_text("@echo from skills\r\n", encoding="utf-8")
    else:
        script = extra / "run.sh"
        script.write_text("#!/bin/sh\nprintf 'from skills\\n'\n", encoding="utf-8")
        script.chmod(0o700)
    manager = _manager(timeout=2)
    allowlist = PathAllowlist.from_roots(extra_write_roots=[extra])

    normal = await _execute(manager, workspace, "exec", {"command": "echo hello"})
    skill_script = await _execute(
        manager,
        workspace,
        "exec",
        {"command": str(script), "working_dir": str(extra)},
        allowlist=allowlist,
    )
    outside = await _execute(
        manager,
        workspace,
        "exec",
        {"command": "pwd", "working_dir": str(tmp_path)},
    )
    read_only_cwd = await _execute(
        manager,
        workspace,
        "exec",
        {"command": "pwd", "working_dir": str(read_only)},
        allowlist=PathAllowlist.from_roots(extra_read_roots=[read_only]),
    )
    blocked = await _execute(manager, workspace, "exec", {"command": "sudo ls"})

    assert normal.content["exit_code"] == 0
    assert normal.content["stdout"].strip() == "hello"
    assert skill_script.content["exit_code"] == 0
    assert skill_script.content["stdout"].strip() == "from skills"
    assert outside.content == {"error": "working_dir is outside writable roots"}
    assert read_only_cwd.content == {"error": "working_dir is outside writable roots"}
    assert blocked.content == {"error": "command blocked by safety policy"}


@pytest.mark.skipif(sys.platform == "win32", reason="uses POSIX stdin commands")
@pytest.mark.asyncio
async def test_concurrent_sessions_support_input_wait_timeout_and_eof(tmp_path) -> None:
    manager = _manager(timeout=0)
    try:
        first, second = await asyncio.gather(
            *(
                _execute(
                    manager,
                    tmp_path,
                    "exec",
                    {"command": _interactive_command(), "yield_time_ms": 50},
                )
                for _ in range(2)
            )
        )
        session_ids = [first.content["session_id"], second.content["session_id"]]
        assert len(set(session_ids)) == 2
        assert first.content["running"] is second.content["running"] is True

        received = await asyncio.gather(
            *(
                _execute(
                    manager,
                    tmp_path,
                    "write_stdin",
                    {
                        "session_id": session_id,
                        "chars": f"{label}\n",
                        "wait_for": f"got:{label}",
                        "wait_timeout_ms": 1_000,
                    },
                )
                for session_id, label in zip(session_ids, ("first", "second"))
            )
        )
        assert "got:first" in received[0].content["output"]
        assert "got:second" in received[1].content["output"]

        timed_out = await _execute(
            manager,
            tmp_path,
            "write_stdin",
            {
                "session_id": session_ids[0],
                "wait_for": "never-produced",
                "wait_timeout_ms": 20,
            },
        )
        assert timed_out.content["running"] is True
        assert timed_out.content["wait_observed"] is False

        completed = await asyncio.gather(
            *(
                _execute(
                    manager,
                    tmp_path,
                    "write_stdin",
                    {
                        "session_id": session_id,
                        "close_stdin": True,
                        "wait_for": "eof",
                        "wait_timeout_ms": 1_000,
                    },
                )
                for session_id in session_ids
            )
        )
        assert all(result.content["done"] for result in completed)
        assert all(result.content["stdin_closed"] for result in completed)
        assert all("eof" in result.content["output"] for result in completed)
    finally:
        await manager.close()


@pytest.mark.asyncio
async def test_background_session_can_be_listed_and_polled_after_completion(tmp_path) -> None:
    manager = _manager(timeout=0)
    try:
        started = await _execute(
            manager,
            tmp_path,
            "exec",
            {"command": _delayed_command(), "yield_time_ms": 50},
        )
        session_id = started.content["session_id"]
        listed = await _execute(manager, tmp_path, "list_exec_sessions")

        assert started.content["running"] is True
        assert listed.content["sessions"][0]["session_id"] == session_id
        assert listed.content["sessions"][0]["remaining_seconds"] is None

        completed = await _execute(
            manager,
            tmp_path,
            "write_stdin",
            {"session_id": session_id, "yield_time_ms": 5_000},
        )
        assert completed.content["done"] is True
        assert "done" in completed.content["output"]
    finally:
        await manager.close()


@pytest.mark.asyncio
async def test_exec_sessions_are_isolated_by_manager_and_conversation(tmp_path) -> None:
    first = _manager(timeout=0)
    second = _manager(timeout=0)
    started = await _execute(
        first,
        tmp_path,
        "exec",
        {"command": _long_command(30), "yield_time_ms": 50},
        session_id="conversation-a",
    )
    session_id = started.content["session_id"]
    try:
        other_manager = await _execute(second, tmp_path, "list_exec_sessions", session_id="conversation-a")
        other_conversation = await _execute(first, tmp_path, "list_exec_sessions", session_id="conversation-b")
        wrong_terminate = await _execute(
            first,
            tmp_path,
            "write_stdin",
            {"session_id": session_id, "terminate": True},
            session_id="conversation-b",
        )
        owner = await _execute(first, tmp_path, "list_exec_sessions", session_id="conversation-a")

        assert other_manager.content == {"sessions": []}
        assert other_conversation.content == {"sessions": []}
        assert wrong_terminate.content == {"error": f"exec session not found: {session_id}"}
        assert owner.content["sessions"][0]["session_id"] == session_id
    finally:
        await _execute(
            first,
            tmp_path,
            "write_stdin",
            {"session_id": session_id, "terminate": True},
            session_id="conversation-a",
        )
        await first.close()
        await second.close()


@pytest.mark.asyncio
async def test_background_timeout_finishes_without_being_polled(tmp_path) -> None:
    manager = _manager(timeout=1)
    try:
        started = await _execute(
            manager,
            tmp_path,
            "exec",
            {"command": _long_command(30), "yield_time_ms": 50},
        )
        await asyncio.sleep(1.3)
        completed = await _execute(
            manager,
            tmp_path,
            "write_stdin",
            {"session_id": started.content["session_id"]},
        )

        assert completed.content["done"] is True
        assert completed.content["timed_out"] is True
    finally:
        await manager.close()


@pytest.mark.asyncio
async def test_manager_close_is_idempotent_and_terminates_background_processes(tmp_path) -> None:
    manager = _manager(timeout=0)
    started = await _execute(
        manager,
        tmp_path,
        "exec",
        {"command": _long_command(30), "yield_time_ms": 50},
    )
    session_id = started.content["session_id"]
    exec_manager = manager._builtin_state.exec_session_manager
    session = exec_manager._sessions[session_id]

    await manager.close()
    await manager.close()

    assert session.process.returncode is not None
    assert session._stdout_task.done() and session._stderr_task.done()
    assert exec_manager._sessions == {}


@pytest.mark.asyncio
async def test_cancelling_initial_yield_cleans_up_the_spawned_process(tmp_path) -> None:
    manager = _manager(timeout=0)
    task = asyncio.create_task(
        _execute(
            manager,
            tmp_path,
            "exec",
            {"command": _long_command(30), "yield_time_ms": 30_000},
        )
    )
    try:
        exec_manager = None
        for _ in range(100):
            exec_manager = manager._builtin_state.exec_session_manager
            if exec_manager is not None and exec_manager._sessions:
                break
            await asyncio.sleep(0.01)
        assert exec_manager is not None and exec_manager._sessions
        session = next(iter(exec_manager._sessions.values()))

        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        assert session.process.returncode is not None
        assert exec_manager._sessions == {}
    finally:
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        await manager.close()


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX process-group behavior")
@pytest.mark.asyncio
async def test_close_terminates_process_descendants(tmp_path) -> None:
    marker = tmp_path / "child-survived"
    manager = _manager(timeout=0)
    try:
        started = await _execute(
            manager,
            tmp_path,
            "exec",
            {
                "command": "(sleep 1; touch child-survived) & printf 'ready\\n'; sleep 30",
                "yield_time_ms": 50,
            },
        )
        assert started.content["running"] is True
        await manager.close()
        await asyncio.sleep(1.2)
        assert not marker.exists()
    finally:
        await manager.close()


def test_windows_shell_environment_is_preserved(monkeypatch) -> None:
    monkeypatch.setattr("bumblehive.tools.builtins.shell._IS_WINDOWS", True)
    monkeypatch.setenv("COMSPEC", r"C:\Windows\System32\cmd.exe")
    monkeypatch.setenv("SYSTEMROOT", r"C:\Windows")
    monkeypatch.setenv("USERPROFILE", r"C:\Users\demo")

    env = _build_env()

    assert env["COMSPEC"] == r"C:\Windows\System32\cmd.exe"
    assert env["SYSTEMROOT"] == r"C:\Windows"
    assert env["USERPROFILE"] == r"C:\Users\demo"
    assert _resolve_shell("bash")[1] == "shell parameter is not supported on Windows"
