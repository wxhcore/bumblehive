"""State and waiting lifecycle of a session-owned question."""

import asyncio
from dataclasses import dataclass


ASK_USER_TIMEOUT_SECONDS = 60


@dataclass
class UserQuestion:
    task_id: str
    question: str
    options: list[str]
    future: asyncio.Future[str | None] | None = None

    def snapshot(self) -> dict:
        return {
            "task_id": self.task_id,
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
                    return {"task_id": self.task_id, "status": "skipped"}
                return {
                    "task_id": self.task_id,
                    "status": "answered",
                    "answer": future.result(),
                }
            return {"status": "pending", "task_id": self.task_id}
        finally:
            self.future = None
            if not future.done():
                future.cancel()
