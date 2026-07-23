"""Console rendering helpers for Bumblehive native stream events."""

import json
import re
import sys
from collections.abc import Mapping
from contextlib import contextmanager, nullcontext
from typing import Any

from rich.console import Console, ConsoleOptions, RenderResult
from rich.live import Live
from rich.markdown import Markdown
from rich.segment import Segment
from rich.style import Style
from rich.text import Text

from .observability import AgentEvent
from .protocols import UserMessage, normalize_user_message


PHASE_LINE_PREFIX = "  │ "
TOOL_PROGRESS_FRAMES = ("⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏")


def compact_json(data: Any, *, max_chars: int = 120) -> str:
    text = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    if len(text) <= max_chars:
        return text
    return f"{text[: max_chars - 3]}..."


def _prompt_text(prompt: UserMessage) -> str:
    content = normalize_user_message(prompt)[0]["content"]
    if isinstance(content, str):
        return content

    parts: list[str] = []
    for part in content:
        if not isinstance(part, Mapping):
            continue

        part_type = part.get("type")
        if part_type == "text":
            text = part.get("text")
            if isinstance(text, str) and text:
                parts.append(text)
        elif isinstance(part_type, str):
            parts.append(f"[{part_type}]")

    return "\n".join(parts)


def format_tool_hint(name: str, arguments: Any) -> str:
    if not isinstance(arguments, dict) or not arguments:
        return name

    if "path" in arguments:
        return f"{name} {arguments['path']}"
    if "command" in arguments:
        return f"{name} {arguments['command']}"
    return f"{name} {compact_json(arguments)}"


_STREAMED_HINT_RE = re.compile(
    r'"(?P<key>path|command)"\s*:\s*"(?P<value>(?:\\.|[^"\\])*)"'
)


def _streamed_tool_hint(arguments: str, *, max_chars: int = 120) -> str:
    """Extract a stable path/command hint from incomplete JSON arguments."""
    match = _STREAMED_HINT_RE.search(arguments)
    if match is None or max_chars <= 0:
        return ""
    try:
        value = json.loads(f'"{match.group("value")}"')
    except (json.JSONDecodeError, TypeError):
        value = match.group("value")
    hint = str(value).replace("\r", "\\r").replace("\n", "\\n")
    if len(hint) <= max_chars:
        return hint
    if max_chars == 1:
        return "…"
    return f"{hint[:max_chars - 1]}…"


_STREAMED_TEXT_RE = re.compile(r'"(?:content|new_text)"\s*:\s*"')


def _streamed_text_line_count(arguments: str) -> int | None:
    """Count lines in complete or partial streamed JSON text arguments."""
    total_lines = 0
    search_from = 0
    while True:
        match = _STREAMED_TEXT_RE.search(arguments, search_from)
        if match is None:
            break

        total_lines += 1
        index = match.end()
        while index < len(arguments):
            char = arguments[index]
            if char == "\\" and index + 1 < len(arguments):
                escaped = arguments[index + 1]
                if escaped == "n":
                    total_lines += 1
                    index += 2
                    continue
                if (
                    escaped == "u"
                    and index + 5 < len(arguments)
                    and arguments[index + 2:index + 6].lower() == "000a"
                ):
                    total_lines += 1
                    index += 6
                    continue
                index += 2
                continue
            if char == '"':
                search_from = index + 1
                break
            if char == "\n":
                total_lines += 1
            index += 1
        else:
            search_from = len(arguments)

        if search_from >= len(arguments):
            break

    return total_lines or None


def tool_result_summary(payload: dict[str, Any]) -> str:
    tool_result = payload.get("tool_result") or {}
    content = str(tool_result.get("content") or "")
    if not content:
        return ""

    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        return content.strip()[:160]

    if isinstance(parsed, dict):
        if "path" in parsed:
            return f"path={parsed['path']}"
        if "stdout" in parsed:
            return str(parsed["stdout"]).strip()[:160]
        if "entries" in parsed and isinstance(parsed["entries"], list):
            return f"{len(parsed['entries'])} entries"
    return compact_json(parsed, max_chars=160)


class PhaseBlock:
    """Render another Rich renderable with a phase guide prefix on every line."""

    def __init__(
        self,
        renderable: Any,
        *,
        prefix: str = PHASE_LINE_PREFIX,
        prefix_style: str = "white dim",
    ) -> None:
        self.renderable = renderable
        self.prefix = prefix
        self.prefix_style = Style.parse(prefix_style)

    def __rich_console__(
        self,
        console: Console,
        options: ConsoleOptions,
    ) -> RenderResult:
        inner_width = max(1, options.max_width - len(self.prefix))
        inner_options = options.update(width=inner_width, max_width=inner_width)
        lines = console.render_lines(self.renderable, inner_options, pad=False)
        if not lines:
            lines = [[]]

        for line in lines:
            yield Segment(self.prefix, self.prefix_style)
            yield from self._rstrip_line(line)
            yield Segment.line()

    @staticmethod
    def _rstrip_line(line: list[Segment]) -> list[Segment]:
        trimmed = list(line)
        while trimmed:
            last = trimmed[-1]
            if last.control:
                break
            text = last.text.rstrip()
            if text:
                trimmed[-1] = last._replace(text=text)
                break
            trimmed.pop()
        return trimmed


class ConsoleStreamRenderer:
    """Nanobot-style console renderer for Bumblehive native stream events."""

    def __init__(
        self,
        *,
        bot_name: str = "bumblehive",
        render_markdown: bool = True,
        verbose_tools: bool = False,
    ) -> None:
        self.console = Console(file=sys.stdout, force_terminal=sys.stdout.isatty())
        self.bot_name = bot_name
        self.render_markdown = render_markdown
        self.verbose_tools = verbose_tools
        self._header_printed = False
        self._current_iteration: int | None = None
        self._phase: str | None = None
        self._phase_body_started = False
        self._usage_totals: dict[str, int] = {}
        self._finished = False
        self._answer = ""
        self._live: Live | None = None
        self._tool_progress_live: Live | None = None
        self._status = None
        self._reasoning_line_open = False
        self._tool_args: dict[tuple[int | None, int], str] = {}
        self._tool_names: dict[tuple[int | None, int], str] = {}
        self._started_tool_counts: dict[int | None, int] = {}
        self._tool_progress_frames: dict[tuple[int | None, int], int] = {}

    def start(self, prompt: UserMessage) -> None:
        self.console.print("[bold blue]You:[/bold blue]")
        self.console.print(Text(_prompt_text(prompt)))
        self.console.print()
        self._start_spinner()

    async def on_event(self, event: AgentEvent) -> None:
        kind = event.kind
        payload = event.payload
        await self._ensure_iteration(event.iteration)

        if kind == "model.stream.reasoning_delta":
            await self.on_reasoning_delta(str(payload.get("delta") or ""))
        elif kind == "model.stream.content_delta":
            await self.on_content_delta(str(payload.get("delta") or ""))
        elif kind == "model.stream.refusal_delta":
            await self.on_content_delta(str(payload.get("delta") or ""))
        elif kind == "model.stream.tool_call_delta":
            await self.on_tool_call_delta(payload, iteration=event.iteration)
        elif kind == "tool.call.started":
            await self.on_tool_started(payload, iteration=event.iteration)
        elif kind == "tool.call.finished":
            await self.on_tool_finished(payload)
        elif kind == "model.response.finished":
            self._add_usage(payload.get("usage"))
            await self.end_response_segment()
            self.end_tool_call_segment()
        elif kind == "final_result":
            await self.finish()
            error = payload.get("error")
            if error:
                self.console.print(f"[red]{compact_json(error, max_chars=300)}[/red]")

    async def on_reasoning_delta(self, delta: str) -> None:
        if not delta:
            return
        self.end_tool_call_segment()
        self._print_reasoning_delta(delta)

    async def on_content_delta(self, delta: str) -> None:
        if not delta:
            return
        self.end_tool_call_segment()
        self._close_reasoning_line()
        self._answer += delta
        if not self._answer.strip():
            return
        self._ensure_header()
        self._ensure_phase("content", style="white dim")
        if self._live is None:
            self._live = Live(
                self._answer_renderable(),
                console=self.console,
                auto_refresh=False,
                transient=True,
            )
            self._live.start()
        else:
            self._live.update(self._answer_renderable())
        self._live.refresh()

    async def on_tool_call_delta(
        self,
        payload: dict[str, Any],
        *,
        iteration: int | None,
    ) -> None:
        index = payload.get("index")
        tool_index = index if isinstance(index, int) else 0
        tool_key = (iteration, tool_index)

        name = str(payload.get("name") or "")
        name_started = bool(name and not self._tool_names.get(tool_key))
        if name:
            self._tool_names[tool_key] = name

        arguments_delta = str(payload.get("arguments_delta") or "")
        if arguments_delta:
            self._tool_args[tool_key] = self._tool_args.get(tool_key, "") + arguments_delta
            self._tool_progress_frames[tool_key] = (
                self._tool_progress_frames.get(tool_key, -1) + 1
            ) % len(TOOL_PROGRESS_FRAMES)

        if not name_started and not arguments_delta:
            return

        self._close_reasoning_line()
        await self.end_response_segment()
        self._stop_spinner()
        self._ensure_header()
        self._ensure_phase("tool_call", style="yellow dim")

        if self._tool_progress_live is None:
            self._tool_progress_live = Live(
                self._tool_call_renderable(iteration),
                console=self.console,
                transient=self.console.is_terminal,
            )
            self._tool_progress_live.start()
        else:
            self._tool_progress_live.update(self._tool_call_renderable(iteration))

    async def on_tool_started(
        self,
        payload: dict[str, Any],
        *,
        iteration: int | None,
    ) -> None:
        self._close_reasoning_line()
        self.end_tool_call_segment()
        await self.end_response_segment()

        tool = payload.get("tool_call") or {}
        name = str(tool.get("name") or "tool")
        arguments = tool.get("arguments") or {}

        started_index = self._started_tool_counts.get(iteration, 0)
        self._started_tool_counts[iteration] = started_index + 1
        self._tool_names[(iteration, started_index)] = name

        self._print_progress(
            f"-> {format_tool_hint(name, arguments)}",
            phase="tool_call",
            style="yellow dim",
        )
        if self.verbose_tools and arguments:
            self._print_progress(
                f"args {compact_json(arguments, max_chars=500)}",
                phase="tool_call",
                style="yellow dim",
            )

    async def on_tool_finished(self, payload: dict[str, Any]) -> None:
        self._close_reasoning_line()
        self.end_tool_call_segment()
        await self.end_response_segment()

        tool_call = payload.get("tool_call") or {}
        name = str(tool_call.get("name") or "tool")
        ok = bool(payload.get("ok"))
        duration = payload.get("duration_s")
        status = "ok" if ok else "failed"
        duration_text = f" in {duration:.4f}s" if isinstance(duration, (int, float)) else ""
        self._print_progress(
            f"<- {name} {status}{duration_text}",
            phase="tool_result",
            style="green dim" if ok else "red dim",
        )

        summary = tool_result_summary(payload)
        if self.verbose_tools and summary:
            self._print_progress(
                f"result {summary}",
                phase="tool_result",
                style="green dim" if ok else "red dim",
            )

        self._start_spinner()

    async def end_response_segment(self) -> None:
        if self._live is not None:
            self._live.refresh()
            self._live.update(self._answer_renderable())
            self._live.refresh()
            self._live.stop()
            self._live = None

        if self._answer.strip():
            with self.console.capture() as capture:
                self.console.print(self._answer_renderable())
            sys.stdout.write(capture.get())
            sys.stdout.flush()
            self._answer = ""

    async def finish(self) -> None:
        if self._finished:
            return
        self._finished = True
        self._close_reasoning_line()
        self.end_tool_call_segment()
        await self.end_response_segment()
        self._stop_spinner()
        self._print_usage()

    def _answer_renderable(self) -> PhaseBlock:
        answer = self._answer.rstrip()
        renderable = Markdown(answer) if self.render_markdown else Text(answer, style="white")
        return PhaseBlock(renderable)

    def _tool_call_renderable(self, iteration: int | None) -> PhaseBlock:
        lines: list[str] = []
        keys = sorted(
            {
                key
                for key in (*self._tool_names, *self._tool_args)
                if key[0] == iteration
            },
            key=lambda key: key[1],
        )
        for key in keys:
            lines.extend(self._tool_call_progress_lines(key))
        return PhaseBlock(Text("\n".join(lines), style="yellow dim"))

    def _tool_call_progress_lines(self, tool_key: tuple[int | None, int]) -> list[str]:
        name = self._tool_names.get(tool_key) or "tool"
        arguments = self._tool_args.get(tool_key, "")
        hint = _streamed_tool_hint(arguments)
        label = f"{name} {hint}" if hint else name
        frame_index = self._tool_progress_frames.get(tool_key, 0)
        frame = TOOL_PROGRESS_FRAMES[frame_index]
        line_count = _streamed_text_line_count(arguments)
        lines = [f"preparing {label}"]
        if line_count is None:
            lines.append(f"generating arguments {frame}")
        else:
            noun = "line" if line_count == 1 else "lines"
            lines.append(f"generating... {frame}  {line_count} {noun}")
        return lines

    def end_tool_call_segment(self) -> None:
        if self._tool_progress_live is None:
            return
        self._tool_progress_live.update(self._tool_call_renderable(self._current_iteration))
        self._tool_progress_live.refresh()
        self._tool_progress_live.stop()
        self._tool_progress_live = None

    def _ensure_header(self) -> None:
        self._stop_spinner()
        if self._header_printed:
            return
        self.console.print(f"[cyan]{self.bot_name}[/cyan]")
        self._header_printed = True

    async def _ensure_iteration(self, iteration: int | None) -> None:
        if iteration is None or iteration == self._current_iteration:
            return
        self._close_reasoning_line()
        self.end_tool_call_segment()
        await self.end_response_segment()
        self._current_iteration = iteration
        self._phase = None
        self._phase_body_started = False

    def _ensure_phase(self, phase: str, *, style: str) -> None:
        if self._phase == phase:
            return
        self.console.print(f"[{style}]{phase}...[/{style}]")
        self._phase = phase
        self._phase_body_started = False

    def _print_reasoning_delta(self, delta: str) -> None:
        with self._pause_transient_output():
            self._ensure_header()
            self._ensure_phase("reasoning", style="cyan dim italic")
            self.console.print(Text(delta, style="cyan dim italic"), end="")
            self.console.file.flush()
            self._reasoning_line_open = not delta.endswith("\n")
            self._phase_body_started = True

    def _print_progress(self, text: str, *, phase: str, style: str) -> None:
        if not text.strip():
            return
        with self._pause_transient_output():
            self._ensure_header()
            self._ensure_phase(phase, style=style)
            self.console.print(Text(self._phase_text(text), style=style))
            self._phase_body_started = True

    def _phase_text(self, text: str) -> str:
        lines = text.rstrip().split("\n")
        return "\n".join(f"{PHASE_LINE_PREFIX}{line}" for line in lines)

    def _add_usage(self, usage: Any) -> None:
        if not isinstance(usage, dict):
            return
        for key, value in usage.items():
            if isinstance(value, int):
                self._usage_totals[key] = self._usage_totals.get(key, 0) + value

    def _print_usage(self) -> None:
        if not self._usage_totals:
            return
        self._phase = None
        self._ensure_phase("usage", style="magenta dim")
        preferred = ("prompt_tokens", "completion_tokens", "total_tokens")
        for key in preferred:
            if key in self._usage_totals:
                self.console.print(
                    Text(
                        self._phase_text(f"{key}: {self._usage_totals[key]}"),
                        style="magenta dim",
                    )
                )
        for key in sorted(k for k in self._usage_totals if k not in preferred):
            self.console.print(
                Text(
                    self._phase_text(f"{key}: {self._usage_totals[key]}"),
                    style="magenta dim",
                )
            )

    def _close_reasoning_line(self) -> None:
        if self._phase == "reasoning" and self._reasoning_line_open:
            self.console.print()
        self._reasoning_line_open = False

    def _start_spinner(self) -> None:
        if self._status is not None or not self.console.is_terminal:
            return
        self._status = self.console.status(
            f"[dim]{self.bot_name} is thinking...[/dim]",
            spinner="dots",
        )
        self._status.start()

    def _stop_spinner(self) -> None:
        if self._status is None:
            return
        self._status.stop()
        self._status = None
        self._clear_current_line()

    def _clear_current_line(self) -> None:
        file = self.console.file
        isatty = getattr(file, "isatty", lambda: False)
        if not isatty():
            return
        file.write("\r\x1b[2K")
        file.flush()

    @contextmanager
    def _pause_transient_output(self):
        live = self._live
        if live is not None:
            live.stop()
            self._live = None

        tool_progress_live = self._tool_progress_live
        if tool_progress_live is not None:
            tool_progress_live.stop()
            self._tool_progress_live = None

        spinner = self._status
        if spinner is not None:
            spinner.stop()
            self._clear_current_line()

        try:
            yield
        finally:
            if spinner is not None and self._status is spinner:
                spinner.start()
            if live is not None and self._answer.strip():
                self._live = Live(
                    self._answer_renderable(),
                    console=self.console,
                    auto_refresh=False,
                    transient=True,
                )
                self._live.start()
                self._live.refresh()
            if tool_progress_live is not None:
                self._tool_progress_live = Live(
                    self._tool_call_renderable(self._current_iteration),
                    console=self.console,
                    transient=self.console.is_terminal,
                )
                self._tool_progress_live.start()
                self._tool_progress_live.refresh()

    def pause(self):
        return (
            self._pause_transient_output()
            if self._status or self._live or self._tool_progress_live
            else nullcontext()
        )


__all__ = ["ConsoleStreamRenderer", "PhaseBlock"]
