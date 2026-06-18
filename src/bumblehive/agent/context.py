import os
import platform
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from html import escape
from importlib.resources import files
from pathlib import Path, PureWindowsPath
from typing import Any, Mapping, Sequence
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .turn import AgentTurnContext, DynamicValue


Message = dict[str, Any]
ToolSchema = dict[str, Any]


@lru_cache(maxsize=None)
def load_prompt(name: str) -> str:
    return (
        files(f"{__package__}.prompts")
        .joinpath(name)
        .read_text(encoding="utf-8")
        .strip()
    )


DEFAULT_AGENT_INSTRUCTIONS = load_prompt("agent_instructions.md")
TOOL_USE_INSTRUCTIONS = load_prompt("tool_use_instructions.md")


@dataclass(frozen=True)
class ContextBundle:
    messages: list[Message]
    tools: list[ToolSchema]


class ContextBuilder:
    """Build model request context from caller-provided capabilities."""

    def __init__(
        self,
        workspace: Path | str | None = None,
        *,
        timezone: str | None = None,
    ) -> None:
        self.workspace = (
            Path(workspace).expanduser().resolve(strict=False)
            if workspace is not None
            else None
        )
        self.timezone = timezone

    def build(
        self,
        *,
        current_user_message: str,
        turn_context: AgentTurnContext | None = None,
        history: Sequence[Message] | None = None,
        agent_instructions: str | None = None,
        available_skills: str = "",
        tools: Sequence[ToolSchema] | None = None,
    ) -> ContextBundle:
        """Build the messages and tool schemas for one model request.

        ``turn_context`` carries per-turn runtime values shared with tool
        execution. When omitted, the builder defaults provide the workspace and
        timezone.
        """
        active_turn_context = self._resolve_turn_context(turn_context)
        system_content = self._build_system_content(
            workspace=active_turn_context.workspace,
            agent_instructions=agent_instructions or DEFAULT_AGENT_INSTRUCTIONS,
            available_skills=available_skills,
        )
        runtime_context = self._build_runtime_context(
            active_turn_context.dynamic_context,
            timezone=active_turn_context.timezone,
        )
        current_user_content = "\n\n".join(
            part for part in (current_user_message, runtime_context) if part
        )

        messages: list[Message] = [
            {"role": "system", "content": system_content},
            *list(history or []),
            {"role": "user", "content": current_user_content},
        ]

        return ContextBundle(messages=messages, tools=list(tools or []))

    def _resolve_turn_context(
        self,
        turn_context: AgentTurnContext | None,
    ) -> AgentTurnContext:
        if turn_context is not None:
            if turn_context.timezone is not None or self.timezone is None:
                return turn_context
            return AgentTurnContext(
                workspace=turn_context.workspace,
                timezone=self.timezone,
                dynamic_context=turn_context.dynamic_context,
                session_id=turn_context.session_id,
                request_id=turn_context.request_id,
                metadata=turn_context.metadata,
            )

        if self.workspace is None:
            raise ValueError("workspace must be provided to ContextBuilder or AgentTurnContext")

        return AgentTurnContext(
            workspace=self.workspace,
            timezone=self.timezone,
        )

    def _build_system_content(
        self,
        *,
        workspace: Path,
        agent_instructions: str,
        available_skills: str,
    ) -> str:
        return "\n\n---\n\n".join(
            part
            for part in (
                self._render_agent_instructions(agent_instructions),
                self._build_capability_context(available_skills),
                self._build_workspace_context(workspace),
            )
            if part
        )

    def _render_agent_instructions(self, text: str) -> str:
        return self._wrap_text("agent_instructions", text)

    def _build_capability_context(self, available_skills: str) -> str:
        parts = [self._build_tool_use()]
        if available_skills.strip():
            parts.append(available_skills.strip())

        body = "\n\n".join(self._indent(part, 2) for part in parts)
        return f"<capability_context>\n{body}\n</capability_context>"

    def _build_tool_use(self) -> str:
        instructions = self._wrap_text("instructions", TOOL_USE_INSTRUCTIONS)
        return (
            "<tool_use>\n"
            f"{self._indent(instructions, 2)}\n"
            "</tool_use>"
        )

    def _build_workspace_context(self, workspace: Path) -> str:
        return "\n".join(
            [
                "<workspace_context>",
                "  <workspace>",
                f"    <cwd>{escape(workspace.as_posix())}</cwd>",
                f"    <os>{escape(self._format_os_name())}</os>",
                f"    <architecture>{escape(platform.machine())}</architecture>",
                f"    <python_version>{escape(platform.python_version())}</python_version>",
                f"    <shell>{escape(self._detect_shell())}</shell>",
                "  </workspace>",
                "</workspace_context>",
            ]
        )

    def _build_runtime_context(
        self,
        dynamic_context: Mapping[str, DynamicValue] | None,
        *,
        timezone: str | None,
    ) -> str:
        parts = [self._build_environment_context(timezone)]
        if dynamic_context:
            rendered_dynamic = self._render_dynamic_context(dynamic_context)
            if rendered_dynamic:
                parts.append(rendered_dynamic)

        body = "\n\n".join(self._indent(part, 2) for part in parts)
        return f"<runtime_context>\n{body}\n</runtime_context>"

    def _build_environment_context(self, timezone: str | None) -> str:
        timezone_info, timezone_name = self._effective_timezone(timezone)
        now = (
            datetime.now(timezone_info)
            if timezone_info is not None
            else datetime.now().astimezone()
        )
        offset = now.strftime("%z")
        utc_offset = f"{offset[:3]}:{offset[3:]}" if len(offset) == 5 else offset
        current_time = (
            f"{now.strftime('%Y-%m-%d %H:%M (%A)')} "
            f"({timezone_name}, UTC{utc_offset})"
        )
        return "\n".join(
            [
                "<environment_context>",
                f"  <current_time>{escape(current_time)}</current_time>",
                "</environment_context>",
            ]
        )

    @staticmethod
    def _effective_timezone(timezone: str | None) -> tuple[ZoneInfo | None, str]:
        timezone_info = ContextBuilder._resolve_timezone(timezone)
        if timezone_info is not None and timezone is not None:
            return timezone_info, timezone

        detected = ContextBuilder._detect_timezone()
        return ContextBuilder._resolve_timezone(detected), detected

    def _render_dynamic_context(self, data: Mapping[str, DynamicValue]) -> str:
        lines = ["<dynamic_context>"]
        for key, value in data.items():
            self._render_dynamic_value(lines, key, value, indent=2)
        lines.append("</dynamic_context>")

        if len(lines) == 2:
            return ""
        return "\n".join(lines)

    def _render_dynamic_value(
        self,
        lines: list[str],
        key: str,
        value: DynamicValue,
        *,
        indent: int,
    ) -> None:
        if value is None:
            return

        tag = self._safe_tag_name(key)
        space = " " * indent

        if isinstance(value, dict):
            lines.append(f"{space}<{tag}>")
            for child_key, child_value in value.items():
                self._render_dynamic_value(
                    lines,
                    child_key,
                    child_value,
                    indent=indent + 2,
                )
            lines.append(f"{space}</{tag}>")
            return

        if isinstance(value, list):
            lines.append(f"{space}<{tag}>")
            for item in value:
                self._render_dynamic_value(lines, "item", item, indent=indent + 2)
            lines.append(f"{space}</{tag}>")
            return

        lines.append(f"{space}<{tag}>{escape(str(value))}</{tag}>")

    @staticmethod
    def _wrap_text(tag: str, text: str) -> str:
        return f"<{tag}>\n{escape(text.strip())}\n</{tag}>"

    @staticmethod
    def _safe_tag_name(key: str) -> str:
        tag = re.sub(r"[^a-zA-Z0-9_-]", "_", key.strip())
        if not tag or tag[0].isdigit():
            tag = f"field_{tag}"
        return tag

    @staticmethod
    def _indent(text: str, spaces: int) -> str:
        prefix = " " * spaces
        return "\n".join(prefix + line if line else line for line in text.splitlines())

    @staticmethod
    def _format_os_name() -> str:
        system = platform.system()
        if system == "Darwin":
            return "macOS"
        return system or sys.platform

    @staticmethod
    def _detect_shell() -> str:
        for variable in ("SHELL", "COMSPEC"):
            value = os.environ.get(variable)
            if value:
                return ContextBuilder._shell_name(value)

        return "unknown"

    @staticmethod
    def _shell_name(value: str) -> str:
        if "\\" in value or re.match(r"^[a-zA-Z]:", value):
            return PureWindowsPath(value).name
        return Path(value).name

    @staticmethod
    def _resolve_timezone(timezone: str | None) -> ZoneInfo | None:
        if timezone is None:
            return None
        try:
            return ZoneInfo(timezone)
        except (ZoneInfoNotFoundError, ValueError):
            return None

    @staticmethod
    def _detect_timezone() -> str:
        env_tz = os.environ.get("TZ")
        if env_tz and ContextBuilder._is_valid_timezone(env_tz):
            return env_tz

        localtime_tz = ContextBuilder._detect_timezone_from_localtime()
        if localtime_tz:
            return localtime_tz

        tzinfo = datetime.now().astimezone().tzinfo
        key = getattr(tzinfo, "key", None)
        if isinstance(key, str) and key:
            return key
        name = datetime.now().astimezone().tzname()
        return name or "local"

    @staticmethod
    def _detect_timezone_from_localtime() -> str | None:
        try:
            target = Path("/etc/localtime").resolve()
        except OSError:
            return None
        return ContextBuilder._timezone_from_zoneinfo_path(target.as_posix())

    @staticmethod
    def _timezone_from_zoneinfo_path(path: str) -> str | None:
        marker = "/zoneinfo/"
        if marker not in path:
            return None

        timezone = path.split(marker, 1)[1]
        return timezone if ContextBuilder._is_valid_timezone(timezone) else None

    @staticmethod
    def _is_valid_timezone(timezone: str) -> bool:
        try:
            ZoneInfo(timezone)
        except (ZoneInfoNotFoundError, ValueError):
            return False
        return True
