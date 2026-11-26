import asyncio
import logging
from collections.abc import Awaitable, Callable, Iterator
from contextlib import AbstractAsyncContextManager, contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from time import perf_counter, time
from typing import Protocol
from uuid import uuid4

from bumblehive import BumblehiveRuntime
from bumblehive.agent import AgentRunResult, AgentRunStream
from bumblehive.observability import AgentEvent
from bumblehive.tools.scope import current_tool_session_id, current_tool_workspace

from .session_reader import SessionReader
from .tool_context import current_task_id
from .tool_results import format_background_tool_result
from .tool_results import format_subagent_update


RuntimeLease = Callable[[], AbstractAsyncContextManager[BumblehiveRuntime]]
NotifySession = Callable[[str, str, str], Awaitable[bool]]
logger = logging.getLogger("uvicorn.error.bumblehive")

SUBAGENT_INSTRUCTIONS = """You are a read-only sub-agent carrying out the task below for a parent agent.
You share its workspace, but not its conversation. Work from the supplied task
and the files you can inspect using your available tools.

If a finding or blocker could change the parent's next step, send it now with
send_message(target="parent", message=...). Include the evidence the parent
needs to act, then continue any work you can do independently.

Your final answer goes to the parent automatically. Give a self-contained
report with your conclusion, supporting evidence or file references, and any
remaining blockers or uncertainty. The parent sees only the updates you send
and your final report.

Follow the task's requested output language and format. Otherwise, use concise
text or Markdown. If blocked, report the limitation in your final answer.

Task:
"""

SUBAGENT_TOOLS = ("read_file", "list_dir", "find_files", "grep", "send_message")


class SubagentRunObserver(Protocol):
    async def on_created(
        self,
        *,
        session_id: str,
        workspace: str,
        title: str,
        content: str,
    ) -> None: ...

    async def on_followup(self, *, session_id: str, message_id: str, content: str) -> None: ...

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
    message_id: str
    followup: bool = False
    stream: AgentRunStream | None = None
    changed: asyncio.Event = field(default_factory=asyncio.Event)
    running: bool = True
    task: asyncio.Task[None] | None = None


class SubagentTasks:
    """Own live background executions; completed reports live in session history."""

    def __init__(self, lease: RuntimeLease, notify: NotifySession) -> None:
        self._lease = lease
        self._notify = notify
        self._tasks: dict[str, BackgroundSubagent] = {}
        # Coordinate persisted lookup and startup with deletion of the same sessions.
        self.dispatch_lock = asyncio.Lock()

    def is_running(self, session_id: str) -> bool:
        entry = self._tasks.get(session_id)
        return entry is not None and entry.running

    async def send_update(self, session_id: str, message: str) -> str:
        entry = self._tasks.get(session_id)
        if entry is None or not entry.running:
            raise ValueError("Only a running sub-agent can send a message to its parent")
        delivered = await self._notify(
            entry.parent_session_id,
            f"subagent-update:{uuid4().hex}",
            format_subagent_update(entry.task_id, message),
        )
        if not delivered:
            raise RuntimeError("Parent session could not accept the update")
        return entry.task_id

    def snapshot(self, parent_session_id: str) -> list[dict]:
        return [
            {
                key: getattr(entry, key)
                for key in ("session_id", "title", "workspace", "content", "started_at", "message_id")
            }
            for entry in self._tasks.values()
            if entry.parent_session_id == parent_session_id and entry.running
        ]

    async def send(
        self, reader: SessionReader, parent_session_id: str, task_id: str, message: str,
    ) -> None:
        while True:
            async with self.dispatch_lock:
                child = await reader.find_child(parent_session_id, task_id)
                entry = self._tasks.get(child.session_id)
                if entry is None:
                    await self.start(
                        task_id=task_id,
                        session_id=child.session_id,
                        parent_session_id=parent_session_id,
                        title=child.title,
                        workspace=child.workspace,
                        content=message,
                        observer=_CURRENT_OBSERVER.get(),
                        followup=True,
                    )
                    return
                if entry.stream is not None:
                    try:
                        entry.stream.steer(message)
                        return
                    except RuntimeError:
                        pass  # The stream closed before its terminal events were delivered.
                changed = entry.changed
            await changed.wait()

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
        followup: bool = False,
    ) -> None:
        entry = BackgroundSubagent(
            task_id, session_id, parent_session_id, title, workspace, content, time(),
            message_id=uuid4().hex if followup else session_id, followup=followup,
        )
        ready: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        self._tasks[session_id] = entry
        entry.task = asyncio.create_task(self._execute(entry, observer, ready))

        def finished(task: asyncio.Task[None]) -> None:
            self._tasks.pop(session_id, None)
            entry.changed.set()
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
                remaining: list[str] = []
                while True:
                    if entry.followup and observer is not None:
                        await observer.on_followup(
                            session_id=entry.session_id,
                            message_id=entry.message_id,
                            content=entry.content,
                        )
                    try:
                        result, remaining = await _run_subagent(runtime, entry, observer, remaining, ready)
                        report = result.final_content or ""
                    except Exception as exc:
                        if not ready.done():
                            raise
                        report = f"Error:\n{exc}"
                        remaining = []
                    content = format_background_tool_result(entry.task_id, report)
                    notification_id = entry.message_id if entry.followup else entry.task_id
                    await self._notify(entry.parent_session_id, f"subagent:{notification_id}", content)
                    if not remaining:
                        break
                    entry.followup = True
                    entry.content = remaining.pop(0)
                    entry.message_id = uuid4().hex
                    entry.started_at = time()
                    entry.running = True
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
    remaining: list[str],
    ready: asyncio.Future[None],
) -> tuple[AgentRunResult, list[str]]:
    session_id, workspace, task = entry.session_id, entry.workspace, entry.content
    started_at = perf_counter()
    try:
        try:
            stream = runtime.stream(
                [
                    {
                        "role": "user",
                        "content": task if entry.followup else SUBAGENT_INSTRUCTIONS + task,
                        "_bumblehive_ui": {"content": task, "message_id": entry.message_id},
                    }
                ],
                session_id=session_id,
                config={
                    "runtime": {"workspace": workspace},
                    "agent": {"tool_names": SUBAGENT_TOOLS},
                },
            )
            try:
                for message in remaining:
                    stream.steer(message)
                entry.stream = stream
                if not ready.done():
                    ready.set_result(None)
                entry.changed.set()
                entry.changed = asyncio.Event()
                async for event in stream:
                    if observer is not None:
                        await observer.on_event(event)
                result = await stream.result()
            finally:
                entry.stream = None
                await stream.aclose()
        finally:
            entry.running = False
    except asyncio.CancelledError:
        if observer is not None:
            await observer.on_cancelled(session_id=session_id)
        raise
    except Exception as exc:
        if ready.done() and observer is not None:
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
    return result, [message["content"] for message in stream.take_pending()]


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
            "Returns status=pending and a task_id matching the tool call ID. Continue independent "
            "work and leave the delegated investigation to the child. A child may send "
            "a [Sub-agent progress update] while it is still working. Use that finding to "
            "adjust your plan or send_message to the relevant child by task_id. Its final "
            "answer or error arrives automatically as a [Background tool result] with the same "
            "task_id. If all remaining work depends on that result, end the turn and wait for "
            "delivery. Use the child's evidence when preparing your answer to the user."
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
            task_id=task_id,
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

    @runtime.tools.tool(
        name="send_message",
        description=(
            "Address a child by its original task_id. A running child receives the message at "
            "its next model step. An idle child starts a turn with its existing history. "
            "From a running child, target 'parent' to send an interim update. This can wake an "
            "idle parent. A stopped or paused parent keeps the update queued. "
            "A status=sent receipt means the message was accepted for delivery."
        ),
        parameters={
            "type": "object",
            "properties": {
                "target": {"type": "string", "description": "A task_id returned by sub_agent, or 'parent'."},
                "message": {"type": "string", "description": "The message to deliver."},
            },
            "required": ["target", "message"],
            "additionalProperties": False,
        },
    )
    async def send_message(target: str, message: str) -> dict[str, str]:
        target, message = target.strip(), message.strip()
        if not target or not message:
            raise ValueError("target and message must not be blank")
        session_id = current_tool_session_id()
        if session_id is None:
            raise RuntimeError("send_message requires an active server conversation")
        if target == "parent":
            task_id = await background_tasks.send_update(session_id, message)
        else:
            task_id = target
            await background_tasks.send(session_reader, session_id, task_id, message)
        return {"status": "sent", "task_id": task_id}
