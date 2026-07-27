import asyncio
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from time import perf_counter
from typing import Protocol

from bumblehive import BumblehiveRuntime
from bumblehive.agent import AgentRunResult
from bumblehive.observability import AgentEvent
from bumblehive.tools.scope import current_tool_path_scope, current_tool_session_id

from .session_reader import SessionReader


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


def register_subagent_tool(
    runtime: BumblehiveRuntime,
    session_reader: SessionReader | None,
) -> None:
    if session_reader is None:
        return

    @runtime.tools.tool(
        name="sub_agent",
        description=(
            "Delegate a self-contained task to an independent read-only "
            "sub-agent and wait for its result. The sub-agent starts a separate "
            "conversation in the same workspace and can inspect and search "
            "files to summarize, analyze, compare, review, or plan, but it "
            "cannot modify files or execute commands. Use it for work that can "
            "be investigated independently, for a useful second perspective, "
            "or for multiple independent read-only tasks that can run in "
            "parallel. Do not use it for simple work you can do directly or for "
            "tasks that require writes, execution, or unstated context. The "
            "sub-agent cannot see the current conversation, so include all "
            "necessary context in the task."
        ),
        parameters={
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": 80,
                    "description": (
                        "A short, specific, action-oriented label for the "
                        "delegated work, shown in the UI. Summarize the objective "
                        "in at most 8 words; do not put detailed instructions here."
                    ),
                },
                "task": {
                    "type": "string",
                    "minLength": 1,
                    "description": (
                        "Complete, self-contained instructions for the sub-agent. "
                        "Include the objective, relevant context or paths, scope "
                        "and constraints, and the expected output. Do not refer to "
                        "the current conversation or omit context the sub-agent "
                        "needs. Request only read-only investigation such as "
                        "summarization, analysis, comparison, review, or planning."
                    ),
                },
            },
            "required": ["title", "task"],
            "additionalProperties": False,
        },
        parallel_safe=True,
    )
    async def sub_agent(title: str, task: str) -> str:
        title = title.strip()
        task = task.strip()
        if not title:
            raise ValueError("title must not be blank")
        if not task:
            raise ValueError("task must not be blank")

        parent_session_id = current_tool_session_id()
        path_scope = current_tool_path_scope()
        if parent_session_id is None or path_scope is None:
            raise RuntimeError("sub_agent requires an active server conversation")

        workspace_path = path_scope.workspace
        workspace = str(workspace_path)
        child_session_id = await session_reader.create(
            workspace_path,
            title=title,
        )
        observer = _CURRENT_OBSERVER.get()
        started_at = perf_counter()
        try:
            if observer is not None:
                await observer.on_created(
                    session_id=child_session_id,
                    workspace=workspace,
                    title=title,
                    content=task,
                )

            stream = runtime.stream(
                task,
                session_id=child_session_id,
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
        except asyncio.CancelledError:
            if observer is not None:
                await observer.on_cancelled(session_id=child_session_id)
            raise
        except Exception as exc:
            if observer is not None:
                await observer.on_error(
                    session_id=child_session_id,
                    message=str(exc),
                )
            raise

        if observer is not None:
            await observer.on_result(
                session_id=child_session_id,
                result=result,
                duration_s=max(0.0, perf_counter() - started_at),
            )
        if result.error is not None:
            raise RuntimeError(result.error.message)
        return result.final_content or ""
