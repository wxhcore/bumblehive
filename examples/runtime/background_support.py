"""教学示例共用的等待与结果投递逻辑；不属于 SDK 公共 API。"""

import asyncio
import json
from collections.abc import Awaitable, Callable
from typing import Any
from uuid import uuid4

import bumblehive


class BackgroundTools:
    """共用等待逻辑；调用方决定怎样投递晚到结果。"""

    def __init__(self, notify: Callable[[str, Any], None]) -> None:
        self.notify = notify
        self.tasks: list[asyncio.Task] = []
        self.deliveries: list[asyncio.Task] = []

    async def submit(self, work: Awaitable, *, wait_seconds: float | None) -> Any:
        task = asyncio.ensure_future(work)
        self.tasks.append(task)
        if wait_seconds is None:
            return await task
        if wait_seconds > 0:
            # 只结束等待，不取消仍在执行的工作。
            done, _ = await asyncio.wait({task}, timeout=wait_seconds)
            if done:
                return task.result()
        task_id = uuid4().hex
        self.deliveries.append(asyncio.create_task(self._deliver(task_id, task)))
        return {"status": "pending", "task_id": task_id}

    async def _deliver(self, task_id: str, task: asyncio.Future) -> None:
        try:
            value = await task
        except Exception as exc:
            value = {"status": "error", "message": str(exc)}
        self.notify(task_id, value)

    async def drain(self) -> None:
        await asyncio.gather(*self.deliveries)

    async def close(self) -> None:
        for task in self.tasks + self.deliveries:
            if not task.done():
                task.cancel()
        await asyncio.gather(*self.tasks, *self.deliveries, return_exceptions=True)


class Conversation:
    """运行中用 steer 投递；运行结束后用同一份历史继续。"""

    def __init__(self) -> None:
        self.current: bumblehive.AgentRun | None = None
        self.inbox: list[str] = []

    def notify(self, task_id: str, value: Any) -> None:
        message = f"后台任务 {task_id} 的结果：{json.dumps(value, ensure_ascii=False)}"
        if self.current is not None:
            try:
                self.current.steer(message)
                return
            except RuntimeError:
                pass  # 当前运行已结束，交给下一轮。
        self.inbox.append(message)

    async def run(self, runtime, prompt: str, background: BackgroundTools):
        history = bumblehive.MessageHistory()
        try:
            while True:
                self.current = runtime.run(prompt, history=history)
                result = await self.current
                history.replace_run_messages(result.messages)
                self.inbox.extend(
                    message["content"] for message in self.current.take_pending()
                )
                print(result.error.message if result.error else result.final_content)
                if result.error:
                    return result
                # 保持应用存活，等待后台结果；Agent 的这一轮已经结束。
                await background.drain()
                if not self.inbox:
                    return result
                prompt = "\n\n".join(self.inbox)
                self.inbox.clear()
        finally:
            await background.close()
