"""State and waiting lifecycle of a session-owned question."""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

ASK_USER_WAIT_SECONDS = 60
ASK_USER_BACKGROUND_WAIT_SECONDS = 120

logger = logging.getLogger("uvicorn.error")


@dataclass
class UserQuestion:
    task_id: str
    question: str
    options: list[str]
    future: asyncio.Future[str | None] | None = None
    background_task: asyncio.Task[None] | None = None

    def snapshot(self) -> dict:
        return {
            "task_id": self.task_id,
            "question": self.question,
            "options": list(self.options),
        }

    def result(self) -> dict:
        assert self.future is not None
        answer = self.future.result()
        return {
            "task_id": self.task_id,
            "status": "skipped" if answer is None else "answered",
            **({"answer": answer} if answer is not None else {}),
        }

    async def wait(self, finish: Callable[["UserQuestion"], Awaitable[None]]) -> dict:
        assert self.future is not None
        try:
            await asyncio.wait({self.future}, timeout=ASK_USER_WAIT_SECONDS)
            if self.future.done():
                return self.result()
            deadline = asyncio.get_running_loop().time() + ASK_USER_BACKGROUND_WAIT_SECONDS
            self.background_task = asyncio.create_task(self._wait_background(finish, deadline))
            return {"status": "pending", "task_id": self.task_id}
        finally:
            # Once pending is returned, the background waiter owns the Future.
            if self.background_task is None:
                self._release_waiter()

    async def _wait_background(
        self, finish: Callable[["UserQuestion"], Awaitable[None]], deadline: float,
    ) -> None:
        assert self.future is not None
        try:
            remaining = max(0.0, deadline - asyncio.get_running_loop().time())
            await asyncio.wait({self.future}, timeout=remaining)
            if not self.future.done():
                self.future.set_result(None)
            await finish(self)
        except Exception:
            logger.exception("Failed to deliver ask_user result | task_id=%s", self.task_id)
        finally:
            self._release_waiter()
            self.background_task = None

    def _release_waiter(self) -> None:
        if self.future is not None:
            if not self.future.done():
                self.future.cancel()
            self.future = None
