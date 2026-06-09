import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from ..adapters.function import CallableTool
from ..context import ToolContext
from ..registry import ToolRegistry


_IS_WINDOWS = sys.platform == "win32"

SHELL_EXEC_DESCRIPTION = (
    "Run a non-interactive shell command inside the project workspace. "
    "Use this for tests, scripts, builds, and quick environment checks."
)

SHELL_EXEC_PARAMETERS: dict[str, Any] = {
    "type": "object",
    "properties": {
        "command": {
            "type": "string",
            "description": "The shell command to run. It must be non-interactive.",
        },
        "working_dir": {
            "type": "string",
            "description": "Optional working directory, relative to the workspace.",
        },
        "timeout": {
            "type": "integer",
            "description": "Timeout in seconds. Default 30, max 300.",
        },
    },
    "required": ["command"],
    "additionalProperties": False,
}


class ShellExec:
    _MAX_TIMEOUT = 300
    _MAX_OUTPUT = 8_000

    def __init__(self, workspace: str | Path, *, timeout: int = 30) -> None:
        self.workspace = Path(workspace).expanduser().resolve()
        self.timeout = timeout
        self.deny_patterns = [
            r"\brm\s+-[rf]{1,2}\b",
            r"\bdel\s+/[fq]\b",
            r"\brmdir\s+/s\b",
            r"(?:^|[;&|]\s*)format\b",
            r"\b(mkfs|diskpart)\b",
            r"\bdd\s+if=",
            r">\s*/dev/sd",
            r"\b(shutdown|reboot|poweroff)\b",
            r":\(\)\s*\{.*\};\s*:",
            r"\b(curl|wget)\b[^|;&]*\|\s*(sh|bash)\b",
            r"\bsudo\b",
        ]

    def __call__(
        self,
        command: str,
        working_dir: str | None = None,
        timeout: int | None = None,
    ) -> dict[str, Any]:
        cwd = self._resolve_working_dir(working_dir)
        if isinstance(cwd, str):
            return {"error": cwd}

        guard_error = self._guard_command(command, cwd)
        if guard_error:
            return {"error": guard_error}

        effective_timeout = min(timeout or self.timeout, self._MAX_TIMEOUT)

        try:
            result = subprocess.run(
                self._shell_args(command),
                cwd=str(cwd),
                env=self._build_env(),
                text=True,
                capture_output=True,
                timeout=effective_timeout,
            )
            return {
                "command": command,
                "working_dir": str(cwd),
                "exit_code": result.returncode,
                "stdout": self._truncate(result.stdout),
                "stderr": self._truncate(result.stderr),
                "timed_out": False,
            }
        except subprocess.TimeoutExpired as exc:
            return {
                "command": command,
                "working_dir": str(cwd),
                "exit_code": None,
                "stdout": self._truncate(exc.stdout or ""),
                "stderr": self._truncate(exc.stderr or ""),
                "timed_out": True,
                "error": f"Command timed out after {effective_timeout} seconds",
            }

    def _resolve_working_dir(self, working_dir: str | None) -> Path | str:
        if working_dir:
            raw = Path(working_dir).expanduser()
            cwd = raw.resolve() if raw.is_absolute() else (self.workspace / raw).resolve()
        else:
            cwd = self.workspace

        if cwd != self.workspace and self.workspace not in cwd.parents:
            return "working_dir is outside workspace"
        if not cwd.exists() or not cwd.is_dir():
            return "working_dir does not exist or is not a directory"
        return cwd

    def _guard_command(self, command: str, cwd: Path) -> str | None:
        lower = command.strip().lower()
        for pattern in self.deny_patterns:
            if re.search(pattern, lower):
                return "command blocked by safety policy"

        if "../" in command or "..\\" in command:
            return "command blocked by safety policy: path traversal"

        for raw_path in self._extract_absolute_paths(command):
            try:
                path = Path(os.path.expandvars(raw_path)).expanduser().resolve()
            except OSError:
                continue
            if path != cwd and cwd not in path.parents:
                return "command blocked by safety policy: path outside working_dir"
        return None

    @staticmethod
    def _extract_absolute_paths(command: str) -> list[str]:
        win_paths = re.findall(r"[A-Za-z]:\\[^\s\"'|><;]*", command)
        posix_paths = re.findall(r"(?:^|[\s|>'\"])(/[^\s\"'>;|<]+)", command)
        home_paths = re.findall(r"(?:^|[\s|>'\"])(~[^\s\"'>;|<]*)", command)
        return win_paths + posix_paths + home_paths

    @staticmethod
    def _shell_args(command: str) -> list[str]:
        if _IS_WINDOWS:
            return [os.environ.get("COMSPEC", "cmd.exe"), "/c", command]
        bash = shutil.which("bash") or "/bin/bash"
        return [bash, "-lc", command]

    @staticmethod
    def _build_env() -> dict[str, str]:
        allowed = ("HOME", "LANG", "TERM", "PATH")
        return {key: value for key in allowed if (value := os.environ.get(key))}

    def _truncate(self, value: str | bytes) -> str:
        if isinstance(value, bytes):
            value = value.decode("utf-8", errors="replace")
        if len(value) <= self._MAX_OUTPUT:
            return value
        half = self._MAX_OUTPUT // 2
        omitted = len(value) - self._MAX_OUTPUT
        return value[:half] + f"\n... ({omitted} chars truncated) ...\n" + value[-half:]


def register_shell_exec_tool(
    registry: ToolRegistry,
    workspace: str | Path | ToolContext,
    *,
    timeout: int | None = None,
) -> CallableTool:
    """Register the shell_exec tool on a registry."""
    if isinstance(workspace, ToolContext):
        ctx = workspace
        workspace = ctx.workspace
        shell_config = ctx.config.get("shell", {})
        config_timeout = (
            shell_config.get("timeout")
            if isinstance(shell_config, dict)
            else None
        )
        if config_timeout is None:
            config_timeout = ctx.config.get("shell_timeout")
        timeout = timeout if timeout is not None else config_timeout

    return registry.register(
        CallableTool(
            name="shell_exec",
            description=SHELL_EXEC_DESCRIPTION,
            parameters=SHELL_EXEC_PARAMETERS,
            handler=ShellExec(workspace, timeout=timeout or 30),
            exclusive=True,
        )
    )
