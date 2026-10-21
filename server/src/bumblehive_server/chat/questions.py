"""State and waiting lifecycle of a session-owned question."""

import asyncio
from dataclasses import dataclass

from ..tool_context import pending_tool_result

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
