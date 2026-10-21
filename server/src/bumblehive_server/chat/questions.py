"""Session-owned questions exposed as an ordinary application tool."""

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from bumblehive import BumblehiveRuntime
from bumblehive.tools.scope import current_tool_session_id

from ..tool_context import pending_tool_result

if TYPE_CHECKING:
    from .session import SessionController

ASK_USER_TIMEOUT_SECONDS = 60


@dataclass
class UserQuestion:
    question_id: str
    question: str
    options: list[str]
    future: asyncio.Future[str | None] | None = None

    def snapshot(self) -> dict:
        return {
            "question_id": self.question_id,
            "question": self.question,
            "options": list(self.options),
        }

    async def wait(self) -> dict:
        future = self.future
        assert future is not None
        try:
            # Unlike wait_for, timeout does not cancel the future before we
            # decide which route owns the reply. No await between that decision
            # and detaching the waiter in finally.
            await asyncio.wait({future}, timeout=ASK_USER_TIMEOUT_SECONDS)
            if future.done():
                if future.result() is None:
                    return {"question_id": self.question_id, "status": "skipped"}
                return {
                    "question_id": self.question_id,
                    "status": "answered",
                    "answer": future.result(),
                }
            return pending_tool_result()
        finally:
            self.future = None
            if not future.done():
                future.cancel()


def register_ask_user_tool(
    runtime: BumblehiveRuntime,
    controller_for: Callable[[str], "SessionController | None"],
) -> None:
    @runtime.tools.tool(
        name="ask_user",
        description=(
            "Ask the user one concise, self-contained question when important information "
            "cannot be determined from the available context. Provide options when useful; "
            "put a recommended option first and explain the recommendation in its text. "
            "The user can always enter a free-text answer.\n\n"
            "This tool waits up to 60 seconds. An answered result contains the user's reply. "
            "A skipped result means the user chose not to answer; do not repeat that question. "
            "A pending result contains task_id matching this tool call ID and means no answer "
            "was received during the wait. The question "
            "remains answerable, and a later reply will arrive as a user message identifying "
            "the original question. Continue useful independent work. If all remaining work "
            "depends on the answer, explain the blocker and end the current turn. Do not poll "
            "or repeat the same question while it remains unanswered. A pending result is "
            "neither an answer nor approval. A skipped result is not approval either; "
            "never treat a recommended option as submitted."
        ),
        parameters={
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "minLength": 1,
                    "description": (
                        "One concise, self-contained question about information needed "
                        "for the task. Use terms the user understands."
                    ),
                },
                "options": {
                    "type": "array",
                    "items": {"type": "string", "minLength": 1},
                    "description": (
                        "Optional suggested answers. Put a recommended option first when "
                        "appropriate and briefly explain its tradeoff in the same string. "
                        "Omit or pass an empty list for free-text input only. Do not add an "
                        "'Other' option; free-text input is always available."
                    ),
                },
            },
            "required": ["question"],
            "additionalProperties": False,
        },
    )
    async def ask_user(question: str, options: list[str] | None = None) -> dict:
        session_id = current_tool_session_id()
        controller = controller_for(session_id) if session_id else None
        if controller is None:
            raise RuntimeError("ask_user requires an active server conversation")
        return await controller.ask_user(question, options or [])
