import asyncio
import logging
from collections.abc import Awaitable, Callable, Iterator
from contextlib import AbstractAsyncContextManager, contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from time import perf_counter, time
from typing import Protocol

from bumblehive import BumblehiveRuntime
from bumblehive.agent import AgentRunResult
from bumblehive.observability import AgentEvent
from bumblehive.tools.scope import current_tool_session_id, current_tool_workspace

from .session_reader import SessionReader
from .tool_context import current_task_id
from .tool_results import format_background_tool_result


RuntimeLease = Callable[[], AbstractAsyncContextManager[BumblehiveRuntime]]
NotifySession = Callable[[str, str, str], Awaitable[None]]
logger = logging.getLogger("uvicorn.error.bumblehive")

SUBAGENT_INSTRUCTIONS = """You are a read-only sub-agent carrying out the task below for a parent agent.
You share its workspace, but not its conversation. Work from the supplied task
and the files you can inspect using your available tools.

Your final answer is your report to the parent and will be delivered
automatically. The parent will not automatically receive your intermediate
messages or tool outputs. Make the report self-contained: state your conclusion,
include the key evidence or file references needed to use it, and identify any
incomplete work, blockers, or uncertainty. Do not leave essential findings only
in intermediate messages or tool outputs.

Follow the task's requested output language and format. Otherwise, use concise
text or Markdown. If blocked, report the limitation in your final answer.

Task:
"""

READ_ONLY_TOOLS = ("read_file", "list_dir", "find_files", "grep")


class SubagentRunObserver(Protocol):
    async def on_created(
        self,
        *,
        session_id: str,
        workspace: str,
        title: str,
        content: str,
    ) -> None: ...

    async def on_event(self, event: AgentEvent) -> None: ...

    async def on_result(
        self,
        *,
        session_id: str,
        result: AgentRunResult,
        duration_s: float,
    ) -> None: ...

    async def on_error(self, *, session_id: str, message: str) -> None: ...

    async def on_cancelled(self, *, session_id: str) -> None: ...


_CURRENT_OBSERVER: ContextVar[SubagentRunObserver | None] = ContextVar(
    "bumblehive_server_subagent_observer",
    default=None,
)


@contextmanager
def observe_subagents(observer: SubagentRunObserver) -> Iterator[None]:
    """Route nested sub-agent activity to the current server request."""
    token = _CURRENT_OBSERVER.set(observer)
    try:
        yield
    finally:
        _CURRENT_OBSERVER.reset(token)


@dataclass
class BackgroundSubagent:
    task_id: str
    session_id: str
    parent_session_id: str
    title: str
    workspace: str
    content: str
    started_at: float
    running: bool = True
    task: asyncio.Task[None] | None = None


class SubagentTasks:
    """Own live background executions; completed reports live in session history."""

    def __init__(self, lease: RuntimeLease, notify: NotifySession) -> None:
        self._lease = lease
        self._notify = notify
        self._tasks: dict[str, BackgroundSubagent] = {}

    def is_running(self, session_id: str) -> bool:
        entry = self._tasks.get(session_id)
        return entry is not None and entry.running

    def snapshot(self, parent_session_id: str) -> list[dict]:
        return [
            {
                key: getattr(entry, key)
                for key in ("session_id", "title", "workspace", "content", "started_at")
            }
            for entry in self._tasks.values()
            if entry.parent_session_id == parent_session_id and entry.running
        ]

    async def start(
        self,
        *,
        task_id: str,
        session_id: str,
        parent_session_id: str,
        title: str,
        workspace: str,
        content: str,
        observer: SubagentRunObserver | None,
    ) -> None:
        entry = BackgroundSubagent(
            task_id, session_id, parent_session_id, title, workspace, content, time()
        )
        ready: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        self._tasks[session_id] = entry
        entry.task = asyncio.create_task(self._execute(entry, observer, ready))

        def finished(task: asyncio.Task[None]) -> None:
            self._tasks.pop(session_id, None)
            if not ready.done():
                ready.set_exception(
                    RuntimeError("Background sub-agent stopped before startup")
                )
            if not task.cancelled() and (error := task.exception()) is not None:
                logger.error(
                    "Background sub-agent failed | session_id=%s",
                    session_id,
                    exc_info=error,
                )

        entry.task.add_done_callback(finished)
        try:
            await asyncio.shield(ready)
        except BaseException:
            entry.task.cancel()
            await asyncio.gather(entry.task, return_exceptions=True)
            self._tasks.pop(session_id, None)
            if entry.running and observer is not None:
                await observer.on_cancelled(session_id=session_id)
            if ready.done() and not ready.cancelled():
                ready.exception()
            raise

    async def _execute(
        self,
        entry: BackgroundSubagent,
        observer: SubagentRunObserver | None,
        ready: asyncio.Future[None],
    ) -> None:
        try:
            async with self._lease() as runtime:
                ready.set_result(None)
                try:
                    result = await _run_subagent(runtime, entry, observer)
                    report = result.final_content or ""
                except Exception as exc:
                    report = f"Error:\n{exc}"
                content = format_background_tool_result(entry.task_id, report)
                await self._notify(
                    entry.parent_session_id, f"subagent:{entry.task_id}", content
                )
        except Exception as exc:
            if not ready.done():
                entry.running = False
                ready.set_exception(exc)
                if observer is not None:
                    await observer.on_error(
                        session_id=entry.session_id, message=str(exc)
                    )
            else:
                logger.exception(
                    "Failed to deliver sub-agent report | session_id=%s",
                    entry.session_id,
                )

    async def cancel(self, session_id: str | None = None) -> None:
        tasks = [
            entry.task
            for entry in self._tasks.values()
            if session_id is None
            or session_id in (entry.session_id, entry.parent_session_id)
        ]
        for task in tasks:
            if task is not None:
                task.cancel()
        await asyncio.gather(
            *(task for task in tasks if task is not None), return_exceptions=True
        )


async def _run_subagent(
    runtime: BumblehiveRuntime,
    entry: BackgroundSubagent,
    observer: SubagentRunObserver | None,
) -> AgentRunResult:
    session_id, workspace, task = entry.session_id, entry.workspace, entry.content
    started_at = perf_counter()
    try:
        try:
            stream = runtime.stream(
                [
                    {
                        "role": "user",
                        "content": SUBAGENT_INSTRUCTIONS + task,
                        "_bumblehive_ui": {"content": task},
                    }
                ],
                session_id=session_id,
                config={
                    "runtime": {"workspace": workspace},
                    "agent": {"tool_names": READ_ONLY_TOOLS},
                },
            )
            try:
                async for event in stream:
                    if observer is not None:
                        await observer.on_event(event)
                result = await stream.result()
            finally:
                await stream.aclose()
        finally:
            entry.running = False
    except asyncio.CancelledError:
        if observer is not None:
            await observer.on_cancelled(session_id=session_id)
        raise
    except Exception as exc:
        if observer is not None:
            await observer.on_error(session_id=session_id, message=str(exc))
        raise
    if observer is not None:
        await observer.on_result(
            session_id=session_id,
            result=result,
            duration_s=max(0.0, perf_counter() - started_at),
        )
    if result.error is not None:
        raise RuntimeError(result.error.message)
    return result


def register_subagent_tool(
    runtime: BumblehiveRuntime,
    session_reader: SessionReader | None,
    background_tasks: SubagentTasks,
) -> None:
    if session_reader is None:
        return

    @runtime.tools.tool(
        name="sub_agent",
        description=(
            "Delegate a self-contained task to an independent read-only sub-agent in the same "
            "workspace. It can inspect and search files, but cannot modify files or execute "
            "commands. Use it for independent investigation, review, comparison, or planning. "
            "The sub-agent cannot see this conversation.\n\n"
            "Runs in the background and returns status=pending with task_id matching this "
            "tool call ID. Its final answer or execution error arrives automatically with "
            "the same task_id. Continue work that does not depend on the result; if all "
            "remaining work depends on it, end the current turn and await the notification. "
            "Do not poll, duplicate delegated work, or claim results you have not received. "
            "Independent tasks may run concurrently."
        ),
        parameters={
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": 80,
                    "description": "A short, specific label for the delegated task, shown in the UI.",
                },
                "task": {
                    "type": "string",
                    "minLength": 1,
                    "description": (
                        "Self-contained instructions with the objective, relevant context or paths, "
                        "scope, constraints, and expected deliverable, including the desired output "
                        "language or format when relevant. Specify the conclusion and supporting "
                        "details needed in the final report."
                    ),
                },
            },
            "required": ["title", "task"],
            "additionalProperties": False,
        },
        parallel_safe=True,
    )
    async def sub_agent(title: str, task: str) -> dict:
        title, task = title.strip(), task.strip()
        if not title:
            raise ValueError("title must not be blank")
        if not task:
            raise ValueError("task must not be blank")
        parent_session_id = current_tool_session_id()
        workspace_path = current_tool_workspace()
        if parent_session_id is None or workspace_path is None:
            raise RuntimeError("sub_agent requires an active server conversation")
        task_id = current_task_id()
        workspace = str(workspace_path)
        child_session_id = await session_reader.create_child(
            workspace_path,
            title=title,
            parent_session_id=parent_session_id,
        )
        observer = _CURRENT_OBSERVER.get()
        if observer is not None:
            await observer.on_created(
                session_id=child_session_id,
                workspace=workspace,
                title=title,
                content=task,
            )
        await background_tasks.start(
            task_id=task_id,
            session_id=child_session_id,
            parent_session_id=parent_session_id,
            title=title,
            workspace=workspace,
            content=task,
            observer=observer,
        )
        return {"status": "pending", "task_id": task_id}
