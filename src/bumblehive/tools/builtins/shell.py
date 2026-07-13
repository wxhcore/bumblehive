import asyncio
import os
import re
import shutil
import sys
import time
import uuid
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..adapters.function import CallableTool
from ..registry import ToolRegistry
from ..scope import current_tool_session_id
from .state import BuiltinToolState
from .workspace import WorkspaceAccess, current_workspace_access


_IS_WINDOWS = sys.platform == "win32"
_DEFAULT_YIELD_MS = 1000
_MAX_YIELD_MS = 30_000
_DEFAULT_WAIT_FOR_MS = 10_000
_MAX_WAIT_FOR_MS = 120_000
_DEFAULT_MAX_OUTPUT_CHARS = 10_000
_MAX_OUTPUT_CHARS = 50_000
_OUTPUT_DRAIN_GRACE_S = 0.1
_SESSION_BUFFER_CHAR_LIMIT = 200_000
_EXEC_MANAGER_METADATA_KEY = "_bumblehive_builtin_exec_session_manager"
_BENIGN_DEVICE_PATHS = frozenset(
    {
        "/dev/null",
        "/dev/zero",
        "/dev/full",
        "/dev/random",
        "/dev/urandom",
        "/dev/stdin",
        "/dev/stdout",
        "/dev/stderr",
        "/dev/tty",
    }
)

_EXEC_DESCRIPTION = (
    "Execute a shell command. Use yield_time_ms for long-running commands; "
    "running commands return a session_id that can be polled or controlled with write_stdin."
)

_EXEC_PARAMETERS: dict[str, Any] = {
    "type": "object",
    "properties": {
        "command": {"type": "string", "description": "The shell command to execute."},
        "cmd": {"type": "string", "description": "Alias for command."},
        "working_dir": {
            "type": "string",
            "description": "Optional working directory, relative to the workspace.",
        },
        "workdir": {"type": "string", "description": "Alias for working_dir."},
        "timeout": {
            "type": "integer",
            "description": "Timeout in seconds. Default 60, max 600.",
            "minimum": 1,
            "maximum": 600,
        },
        "shell": {
            "type": "string",
            "description": "Optional shell binary or name. Supported: sh, bash, zsh.",
        },
        "login": {
            "type": "boolean",
            "description": "Run bash/zsh with login shell semantics. Default true.",
        },
        "yield_time_ms": {
            "type": "integer",
            "description": "Milliseconds to wait before returning a running session.",
            "minimum": 0,
            "maximum": _MAX_YIELD_MS,
        },
        "max_output_chars": {
            "type": "integer",
            "description": "Maximum output characters to return. Default 10000, max 50000.",
            "minimum": 1000,
            "maximum": _MAX_OUTPUT_CHARS,
        },
    },
    "additionalProperties": False,
}

_WRITE_STDIN_DESCRIPTION = (
    "Interact with a running exec session. Poll output, write stdin, close stdin, "
    "wait for text, or terminate the process."
)

_WRITE_STDIN_PARAMETERS: dict[str, Any] = {
    "type": "object",
    "properties": {
        "session_id": {"type": "string", "description": "Session id returned by exec."},
        "chars": {
            "type": "string",
            "description": "Text to write to stdin. Omit or pass empty string to only poll.",
        },
        "close_stdin": {
            "type": "boolean",
            "description": "Close stdin after writing chars.",
        },
        "terminate": {
            "type": "boolean",
            "description": "Terminate the running process.",
        },
        "yield_time_ms": {
            "type": "integer",
            "description": "Milliseconds to wait before returning output.",
            "minimum": 0,
            "maximum": _MAX_YIELD_MS,
        },
        "wait_for": {
            "type": "string",
            "description": "Optional text to wait for before returning.",
        },
        "wait_timeout_ms": {
            "type": "integer",
            "description": "Maximum milliseconds to wait for wait_for text.",
            "minimum": 0,
            "maximum": _MAX_WAIT_FOR_MS,
        },
        "max_output_chars": {
            "type": "integer",
            "description": "Maximum output characters to return.",
            "minimum": 1000,
            "maximum": _MAX_OUTPUT_CHARS,
        },
    },
    "required": ["session_id"],
    "additionalProperties": False,
}

_LIST_EXEC_SESSIONS_DESCRIPTION = "List active long-running exec sessions."

_LIST_EXEC_SESSIONS_PARAMETERS: dict[str, Any] = {
    "type": "object",
    "properties": {},
    "additionalProperties": False,
}


@dataclass(frozen=True)
class PreparedCommand:
    command: str
    cwd: str
    env: dict[str, str]
    timeout: int | None
    shell_program: str | None
    login: bool


@dataclass(frozen=True)
class SessionPoll:
    output: str
    done: bool
    exit_code: int | None
    elapsed_seconds: float
    timed_out: bool = False
    terminated: bool = False
    stdin_closed: bool = False
    truncated_chars: int = 0


class ExecSession:
    def __init__(
        self,
        *,
        session_id: str,
        process: asyncio.subprocess.Process,
        command: str,
        cwd: str,
        timeout: int | None,
        owner_session_id: str | None,
    ) -> None:
        self.session_id = session_id
        self.process = process
        self.command = command
        self.cwd = cwd
        self.owner_session_id = owner_session_id
        self.started_at = time.monotonic()
        self.last_access = time.monotonic()
        self.deadline = time.monotonic() + timeout if timeout else float("inf")
        self._chunks: list[str] = []
        self._buffer_chars = 0
        self._dropped_chars = 0
        self._timed_out = False
        self._lock = asyncio.Lock()
        self._stdout_task = asyncio.create_task(self._read_stream(process.stdout, ""))
        self._stderr_task = asyncio.create_task(self._read_stream(process.stderr, "STDERR:\n"))

    async def _read_stream(
        self,
        stream: asyncio.StreamReader | None,
        prefix: str,
    ) -> None:
        if stream is None:
            return
        first = True
        while True:
            chunk = await stream.read(4096)
            if not chunk:
                break
            text = chunk.decode("utf-8", errors="replace")
            if prefix and first:
                text = prefix + text
                first = False
            async with self._lock:
                self._chunks.append(text)
                self._buffer_chars += len(text)
                while self._buffer_chars > _SESSION_BUFFER_CHAR_LIMIT and self._chunks:
                    dropped = self._chunks.pop(0)
                    self._buffer_chars -= len(dropped)
                    self._dropped_chars += len(dropped)

    async def write(self, chars: str) -> str | None:
        if self.process.returncode is not None:
            return "session has already exited"
        if self.process.stdin is None:
            return "session stdin is not available"
        try:
            self.process.stdin.write(chars.encode("utf-8"))
            await self.process.stdin.drain()
        except (BrokenPipeError, ConnectionResetError):
            return "session stdin is closed"
        return None

    async def close_stdin(self) -> str | None:
        if self.process.returncode is not None:
            return "session has already exited"
        if self.process.stdin is None:
            return "session stdin is not available"
        self.process.stdin.close()
        with suppress(BrokenPipeError, ConnectionResetError):
            await self.process.stdin.wait_closed()
        return None

    async def poll(
        self,
        yield_time_ms: int,
        max_output_chars: int,
        *,
        terminated: bool = False,
        stdin_closed: bool = False,
    ) -> SessionPoll:
        self.last_access = time.monotonic()
        if yield_time_ms > 0 and self.process.returncode is None:
            await asyncio.sleep(min(yield_time_ms, _MAX_YIELD_MS) / 1000)

        if self.process.returncode is None and time.monotonic() >= self.deadline:
            self._timed_out = True
            await self.kill()

        if self.process.returncode is not None:
            with suppress(asyncio.TimeoutError):
                await asyncio.wait_for(
                    asyncio.gather(self._stdout_task, self._stderr_task),
                    timeout=2.0,
                )
        elif yield_time_ms > 0:
            await self._wait_for_buffered_output()

        async with self._lock:
            output = "".join(self._chunks)
            self._chunks.clear()
            self._buffer_chars = 0
            dropped_chars = self._dropped_chars
            self._dropped_chars = 0

        output, truncated = _truncate_output(output, max_output_chars)
        if dropped_chars:
            output = f"... ({dropped_chars:,} chars dropped before poll) ...\n" + output
        return SessionPoll(
            output=output,
            done=self.process.returncode is not None,
            exit_code=self.process.returncode,
            elapsed_seconds=max(0.0, time.monotonic() - self.started_at),
            timed_out=self._timed_out,
            terminated=terminated,
            stdin_closed=stdin_closed,
            truncated_chars=truncated + dropped_chars,
        )

    async def kill(self) -> None:
        if self.process.returncode is not None:
            return
        self.process.kill()
        with suppress(asyncio.TimeoutError):
            await asyncio.wait_for(self.process.wait(), timeout=5.0)

    async def _wait_for_buffered_output(self) -> None:
        deadline = time.monotonic() + _OUTPUT_DRAIN_GRACE_S
        while time.monotonic() < deadline:
            async with self._lock:
                if self._chunks:
                    return
            await asyncio.sleep(0.01)


class ExecSessionManager:
    def __init__(self, *, max_sessions: int = 8, idle_timeout: int = 1800) -> None:
        self.max_sessions = max_sessions
        self.idle_timeout = idle_timeout
        self._sessions: dict[str, ExecSession] = {}
        self._lock = asyncio.Lock()

    async def start(
        self,
        *,
        prepared: PreparedCommand,
        yield_time_ms: int,
        max_output_chars: int,
        owner_session_id: str | None,
    ) -> tuple[str, SessionPoll]:
        async with self._lock:
            await self._cleanup_locked()
            if len(self._sessions) >= self.max_sessions:
                raise RuntimeError(f"maximum exec sessions reached ({self.max_sessions})")
            process = await _spawn(
                prepared.command,
                prepared.cwd,
                prepared.env,
                prepared.shell_program,
                prepared.login,
                stdin=asyncio.subprocess.PIPE,
            )
            session_id = uuid.uuid4().hex[:12]
            session = ExecSession(
                session_id=session_id,
                process=process,
                command=prepared.command,
                cwd=prepared.cwd,
                timeout=prepared.timeout,
                owner_session_id=owner_session_id,
            )
            self._sessions[session_id] = session

        poll = await session.poll(yield_time_ms, max_output_chars)
        if poll.done:
            async with self._lock:
                self._sessions.pop(session_id, None)
        return session_id, poll

    async def write(
        self,
        *,
        session_id: str,
        chars: str | None,
        close_stdin: bool,
        terminate: bool,
        yield_time_ms: int,
        max_output_chars: int,
        owner_session_id: str | None,
    ) -> SessionPoll:
        async with self._lock:
            await self._cleanup_locked()
            session = self._sessions.get(session_id)
        if session is None:
            raise KeyError(session_id)
        if session.owner_session_id != owner_session_id:
            raise KeyError(session_id)

        if chars:
            error = await session.write(chars)
            if error:
                raise RuntimeError(error)
        stdin_closed = False
        if close_stdin:
            error = await session.close_stdin()
            if error:
                raise RuntimeError(error)
            stdin_closed = True
        if terminate:
            await session.kill()

        poll = await session.poll(
            yield_time_ms,
            max_output_chars,
            terminated=terminate,
            stdin_closed=stdin_closed,
        )
        if poll.done:
            async with self._lock:
                self._sessions.pop(session_id, None)
        return poll

    async def list(self, *, owner_session_id: str | None) -> list[dict[str, Any]]:
        async with self._lock:
            await self._cleanup_locked()
            now = time.monotonic()
            return [
                {
                    "session_id": session_id,
                    "command": session.command,
                    "working_dir": session.cwd,
                    "running": session.process.returncode is None,
                    "exit_code": session.process.returncode,
                    "elapsed_seconds": round(max(0.0, now - session.started_at), 3),
                    "idle_seconds": round(max(0.0, now - session.last_access), 3),
                    "remaining_seconds": (
                        None
                        if session.deadline == float("inf")
                        else round(max(0.0, session.deadline - now), 3)
                    ),
                }
                for session_id, session in sorted(self._sessions.items())
                if session.owner_session_id == owner_session_id
            ]

    async def _cleanup_locked(self) -> None:
        now = time.monotonic()
        stale = [
            session_id
            for session_id, session in self._sessions.items()
            if now - session.last_access > self.idle_timeout
        ]
        for session_id in stale:
            session = self._sessions.pop(session_id)
            await session.kill()


class ExecRunner:
    _MAX_TIMEOUT = 600

    def __init__(
        self,
        *,
        timeout: int = 60,
        manager: ExecSessionManager | None = None,
    ) -> None:
        self.timeout = timeout
        self.manager = manager or ExecSessionManager()
        self.deny_patterns = [
            r"\brm\s+-[rf]{1,2}\b",
            r"\bdel\s+/[fq]\b",
            r"\brmdir\s+/s\b",
            r"(?:^|[;&|]\s*)format(?!=)\b",
            r"\b(mkfs|diskpart)\b",
            r"\bdd\s+if=",
            r">\s*/dev/sd",
            r"\b(shutdown|reboot|poweroff)\b",
            r":\(\)\s*\{.*\};\s*:",
            r"\b(curl|wget)\b[^|;&]*\|\s*(sh|bash)\b",
            r"\bsudo\b",
        ]

    async def exec(
        self,
        command: str | None = None,
        cmd: str | None = None,
        working_dir: str | None = None,
        workdir: str | None = None,
        timeout: int | None = None,
        shell: str | None = None,
        login: bool | None = None,
        yield_time_ms: int | None = None,
        max_output_chars: int | None = None,
    ) -> dict[str, Any]:
        command = command or cmd
        working_dir = working_dir or workdir
        if not command:
            return {"error": "missing command"}
        output_limit = _clamp_int(
            max_output_chars,
            _DEFAULT_MAX_OUTPUT_CHARS,
            1000,
            _MAX_OUTPUT_CHARS,
        )

        prepared = self._prepare_command(command, working_dir, timeout, shell, login)
        if isinstance(prepared, dict):
            return prepared

        if yield_time_ms is not None:
            try:
                session_id, poll = await self.manager.start(
                    prepared=prepared,
                    yield_time_ms=_clamp_int(yield_time_ms, _DEFAULT_YIELD_MS, 0, _MAX_YIELD_MS),
                    max_output_chars=output_limit,
                    owner_session_id=current_tool_session_id(),
                )
            except Exception as exc:
                return {"error": str(exc)}
            return _poll_dict(session_id, poll, command=prepared.command, cwd=prepared.cwd)

        try:
            process = await _spawn(
                prepared.command,
                prepared.cwd,
                prepared.env,
                prepared.shell_program,
                prepared.login,
            )
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=prepared.timeout,
                )
            except asyncio.TimeoutError:
                await _kill_process(process)
                return {
                    "command": prepared.command,
                    "working_dir": prepared.cwd,
                    "exit_code": None,
                    "stdout": "",
                    "stderr": "",
                    "timed_out": True,
                    "error": f"Command timed out after {prepared.timeout} seconds",
                }
            except asyncio.CancelledError:
                await _kill_process(process)
                raise

            stdout_text = stdout.decode("utf-8", errors="replace")
            stderr_text = stderr.decode("utf-8", errors="replace")
            stdout_text, stdout_truncated = _truncate_output(stdout_text, output_limit)
            stderr_text, stderr_truncated = _truncate_output(stderr_text, output_limit)
            return {
                "command": prepared.command,
                "working_dir": prepared.cwd,
                "exit_code": process.returncode,
                "stdout": stdout_text,
                "stderr": stderr_text,
                "timed_out": False,
                "stdout_truncated_chars": stdout_truncated,
                "stderr_truncated_chars": stderr_truncated,
            }
        except Exception as exc:
            return {"error": str(exc)}

    async def write_stdin(
        self,
        session_id: str,
        chars: str | None = None,
        close_stdin: bool = False,
        terminate: bool = False,
        yield_time_ms: int | None = None,
        wait_for: str | None = None,
        wait_timeout_ms: int | None = None,
        max_output_chars: int | None = None,
    ) -> dict[str, Any]:
        output_limit = _clamp_int(
            max_output_chars,
            _DEFAULT_MAX_OUTPUT_CHARS,
            1000,
            _MAX_OUTPUT_CHARS,
        )
        try:
            if wait_for:
                return await self._wait_for_output(
                    session_id=session_id,
                    chars=chars,
                    close_stdin=close_stdin,
                    terminate=terminate,
                    wait_for=wait_for,
                    wait_timeout_ms=_clamp_int(
                        wait_timeout_ms,
                        _DEFAULT_WAIT_FOR_MS,
                        0,
                        _MAX_WAIT_FOR_MS,
                    ),
                    max_output_chars=output_limit,
                )
            poll = await self.manager.write(
                session_id=session_id,
                chars=chars,
                close_stdin=close_stdin,
                terminate=terminate,
                yield_time_ms=_clamp_int(yield_time_ms, _DEFAULT_YIELD_MS, 0, _MAX_YIELD_MS),
                max_output_chars=output_limit,
                owner_session_id=current_tool_session_id(),
            )
            return _poll_dict(session_id, poll)
        except KeyError:
            return {"error": f"exec session not found: {session_id}"}
        except Exception as exc:
            return {"error": str(exc)}

    async def list_exec_sessions(self) -> dict[str, Any]:
        return {
            "sessions": await self.manager.list(
                owner_session_id=current_tool_session_id(),
            )
        }

    async def _wait_for_output(
        self,
        *,
        session_id: str,
        chars: str | None,
        close_stdin: bool,
        terminate: bool,
        wait_for: str,
        wait_timeout_ms: int,
        max_output_chars: int,
    ) -> dict[str, Any]:
        deadline = time.monotonic() + wait_timeout_ms / 1000
        aggregate: list[str] = []
        first = True
        last: SessionPoll | None = None
        while True:
            remaining_ms = max(0, int((deadline - time.monotonic()) * 1000))
            step_ms = min(500, remaining_ms)
            last = await self.manager.write(
                session_id=session_id,
                chars=chars if first else None,
                close_stdin=close_stdin if first else False,
                terminate=terminate if first else False,
                yield_time_ms=step_ms,
                max_output_chars=max_output_chars,
                owner_session_id=current_tool_session_id(),
            )
            first = False
            if last.output:
                aggregate.append(last.output)
                joined = "".join(aggregate)
                if wait_for in joined:
                    return _poll_dict(session_id, last, output=joined)
            if last.done or remaining_ms <= 0:
                joined = "".join(aggregate)
                result = _poll_dict(session_id, last, output=joined)
                if wait_for not in joined:
                    result["wait_observed"] = False
                    result["wait_for"] = wait_for
                return result

    def _prepare_command(
        self,
        command: str,
        working_dir: str | None,
        timeout: int | None,
        shell: str | None,
        login: bool | None,
    ) -> PreparedCommand | dict[str, Any]:
        access = self._access()
        cwd = self._resolve_working_dir(working_dir, access)
        if isinstance(cwd, str):
            return {"error": cwd}
        guard_error = self._guard_command(
            command,
            cwd,
        )
        if guard_error:
            return {"error": guard_error}
        shell_program, shell_error = _resolve_shell(shell)
        if shell_error:
            return {"error": shell_error}
        return PreparedCommand(
            command=command,
            cwd=str(cwd),
            env=_build_env(),
            timeout=self._resolve_timeout(timeout),
            shell_program=shell_program,
            login=True if login is None else login,
        )

    def _resolve_timeout(self, timeout: int | None) -> int | None:
        if timeout:
            return min(timeout, self._MAX_TIMEOUT)
        if self.timeout and self.timeout > 0:
            return self.timeout
        return None

    def _resolve_working_dir(
        self,
        working_dir: str | None,
        access: WorkspaceAccess,
    ) -> Path | str:
        if working_dir:
            resolved = access.resolve(working_dir)
        else:
            resolved = access.workspace
        if isinstance(resolved, str):
            return "working_dir is outside workspace"
        if not resolved.exists() or not resolved.is_dir():
            return "working_dir does not exist or is not a directory"
        return resolved

    def _guard_command(
        self,
        command: str,
        cwd: Path,
    ) -> str | None:
        lower = command.strip().lower()
        for pattern in self.deny_patterns:
            if re.search(pattern, lower):
                return "command blocked by safety policy"
        if "../" in command or "..\\" in command:
            return "command blocked by safety policy: path traversal"
        for raw_path in _extract_absolute_paths(command):
            expanded = os.path.expandvars(raw_path.strip())
            if _is_benign_device_path(expanded):
                continue
            try:
                path = Path(expanded).expanduser().resolve()
            except OSError:
                continue
            if _is_benign_device_path(str(path)):
                continue
            if path != cwd and cwd not in path.parents:
                return "command blocked by safety policy: path outside working_dir"
        return None

    def _access(self) -> WorkspaceAccess:
        return current_workspace_access()


def _poll_dict(
    session_id: str,
    poll: SessionPoll,
    *,
    command: str | None = None,
    cwd: str | None = None,
    output: str | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "session_id": session_id,
        "running": not poll.done,
        "done": poll.done,
        "exit_code": poll.exit_code,
        "output": poll.output if output is None else output,
        "elapsed_seconds": round(poll.elapsed_seconds, 3),
        "timed_out": poll.timed_out,
        "terminated": poll.terminated,
        "stdin_closed": poll.stdin_closed,
        "truncated_chars": poll.truncated_chars,
    }
    if command is not None:
        result["command"] = command
    if cwd is not None:
        result["working_dir"] = cwd
    return result


async def _spawn(
    command: str,
    cwd: str,
    env: dict[str, str],
    shell_program: str | None = None,
    login: bool = True,
    *,
    stdin: int = asyncio.subprocess.DEVNULL,
) -> asyncio.subprocess.Process:
    if _IS_WINDOWS:
        if "\n" in command:
            return await asyncio.create_subprocess_exec(
                "powershell",
                "-NoProfile",
                "-Command",
                command,
                stdin=stdin,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
                env=env,
            )
        return await asyncio.create_subprocess_shell(
            command,
            stdin=stdin,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
            env=env,
        )
    shell_program = shell_program or shutil.which("bash") or "/bin/bash"
    shell_name = Path(shell_program).name.lower()
    args = [shell_program]
    if login and shell_name in {"bash", "bash.exe", "zsh", "zsh.exe"}:
        args.append("-l")
    args.extend(["-c", command])
    return await asyncio.create_subprocess_exec(
        *args,
        stdin=stdin,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd,
        env=env,
    )


def _resolve_shell(shell: str | None) -> tuple[str | None, str | None]:
    if not shell:
        return None, None
    if _IS_WINDOWS:
        return None, "shell parameter is not supported on Windows"
    if "\0" in shell or "\n" in shell or "\r" in shell:
        return None, "shell contains invalid characters"
    allowed = {"sh", "bash", "zsh"}
    path = Path(shell).expanduser()
    if path.is_absolute():
        if path.name not in allowed:
            return None, f"unsupported shell {shell!r}. Allowed: bash, sh, zsh"
        if not path.is_file() or not os.access(path, os.X_OK):
            return None, f"shell is not executable: {shell}"
        return str(path), None
    if "/" in shell or "\\" in shell:
        return None, "shell must be a shell name or absolute path"
    if shell not in allowed:
        return None, f"unsupported shell {shell!r}. Allowed: bash, sh, zsh"
    resolved = shutil.which(shell)
    if not resolved:
        return None, f"shell not found: {shell}"
    return resolved, None


async def _kill_process(process: asyncio.subprocess.Process) -> None:
    if process.returncode is not None:
        return
    process.kill()
    with suppress(asyncio.TimeoutError):
        await asyncio.wait_for(process.wait(), timeout=5.0)


def _build_env() -> dict[str, str]:
    if _IS_WINDOWS:
        system_root = os.environ.get("SYSTEMROOT", r"C:\Windows")
        return {
            "SYSTEMROOT": system_root,
            "COMSPEC": os.environ.get("COMSPEC", f"{system_root}\\system32\\cmd.exe"),
            "USERPROFILE": os.environ.get("USERPROFILE", ""),
            "HOMEDRIVE": os.environ.get("HOMEDRIVE", "C:"),
            "HOMEPATH": os.environ.get("HOMEPATH", "\\"),
            "TEMP": os.environ.get("TEMP", f"{system_root}\\Temp"),
            "TMP": os.environ.get("TMP", f"{system_root}\\Temp"),
            "PATHEXT": os.environ.get("PATHEXT", ".COM;.EXE;.BAT;.CMD"),
            "PATH": os.environ.get("PATH", f"{system_root}\\system32;{system_root}"),
            "PYTHONUNBUFFERED": "1",
            "APPDATA": os.environ.get("APPDATA", ""),
            "LOCALAPPDATA": os.environ.get("LOCALAPPDATA", ""),
            "ProgramData": os.environ.get("ProgramData", ""),
            "ProgramFiles": os.environ.get("ProgramFiles", ""),
            "ProgramFiles(x86)": os.environ.get("ProgramFiles(x86)", ""),
            "ProgramW6432": os.environ.get("ProgramW6432", ""),
        }
    return {
        "HOME": os.environ.get("HOME", "/tmp"),
        "LANG": os.environ.get("LANG", "C.UTF-8"),
        "TERM": os.environ.get("TERM", "dumb"),
        "PYTHONUNBUFFERED": "1",
    }


def _extract_absolute_paths(command: str) -> list[str]:
    win_paths = re.findall(
        r"(?<![A-Za-z])(?:[A-Za-z]:[^\s\"'|><;]*|\\\\[^\s\"'|><;]+(?:\\[^\s\"'|><;]+)*)",
        command,
    )
    posix_paths = re.findall(r"(?:^|[\s|>'\"])(/[^\s\"'>;|<]+)", command)
    home_paths = re.findall(r"(?:^|[\s>'\"])(~[^\s\"'>;|<]*)", command)
    return win_paths + posix_paths + home_paths


def _is_benign_device_path(path: str) -> bool:
    return path in _BENIGN_DEVICE_PATHS or path.startswith("/dev/fd/")


def _truncate_output(output: str, max_output_chars: int) -> tuple[str, int]:
    if len(output) <= max_output_chars:
        return output, 0
    half = max_output_chars // 2
    omitted = len(output) - max_output_chars
    return (
        output[:half]
        + f"\n\n... ({omitted:,} chars truncated) ...\n\n"
        + output[-half:],
        omitted,
    )


def _clamp_int(value: int | None, default: int, minimum: int, maximum: int) -> int:
    if value is None:
        return default
    return min(max(value, minimum), maximum)


def _timeout_from_config(
    config: dict[str, Any],
    timeout: int | None,
) -> int | None:
    shell_config = config.get("exec", {})
    config_timeout = shell_config.get("timeout") if isinstance(shell_config, dict) else None
    return timeout if timeout is not None else config_timeout


def _runner_from_state(
    state: BuiltinToolState,
    *,
    config: dict[str, Any],
    timeout: int | None = None,
) -> ExecRunner:
    resolved_timeout = _timeout_from_config(config, timeout)
    manager = _manager_from_state(state)
    return ExecRunner(
        timeout=60 if resolved_timeout is None else resolved_timeout,
        manager=manager,
    )


def _manager_from_state(state: BuiltinToolState) -> ExecSessionManager:
    manager = state.exec_session_manager
    if not isinstance(manager, ExecSessionManager):
        manager = ExecSessionManager()
        state.exec_session_manager = manager
    return manager


def register_exec_tool(
    registry: ToolRegistry,
    *,
    config: dict[str, Any],
    state: BuiltinToolState,
    timeout: int | None = None,
) -> CallableTool:
    runner = _runner_from_state(state, config=config, timeout=timeout)
    return registry.register(
        CallableTool(
            name="exec",
            description=_EXEC_DESCRIPTION,
            parameters=_EXEC_PARAMETERS,
            handler=runner.exec,
            exclusive=True,
        )
    )


def register_write_stdin_tool(
    registry: ToolRegistry,
    *,
    config: dict[str, Any],
    state: BuiltinToolState,
    timeout: int | None = None,
) -> CallableTool:
    runner = _runner_from_state(state, config=config, timeout=timeout)
    return registry.register(
        CallableTool(
            name="write_stdin",
            description=_WRITE_STDIN_DESCRIPTION,
            parameters=_WRITE_STDIN_PARAMETERS,
            handler=runner.write_stdin,
            exclusive=True,
        )
    )


def register_list_exec_sessions_tool(
    registry: ToolRegistry,
    *,
    config: dict[str, Any],
    state: BuiltinToolState,
    timeout: int | None = None,
) -> CallableTool:
    runner = _runner_from_state(state, config=config, timeout=timeout)
    return registry.register(
        CallableTool(
            name="list_exec_sessions",
            description=_LIST_EXEC_SESSIONS_DESCRIPTION,
            parameters=_LIST_EXEC_SESSIONS_PARAMETERS,
            handler=runner.list_exec_sessions,
            read_only=True,
        )
    )
