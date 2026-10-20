"""从仓库根目录运行：python -m examples.runtime.ask_user_timeout"""

import asyncio
import os

import bumblehive
from examples.runtime.ask_user import read_answer
from examples.runtime.background_support import BackgroundTools, Conversation


WAIT_SECONDS = 60


async def main() -> None:
    config = bumblehive.RuntimeArguments(
        model=os.environ["BUMBLEHIVE_MODEL"],
        api_key=os.environ["BUMBLEHIVE_API_KEY"],
        base_url=os.environ["BUMBLEHIVE_BASE_URL"],
        skill_names=[],
        tool_names=["ask_user"],
    )
    conversation = Conversation()

    def on_answer(task_id: str, value: dict) -> None:
        # 超时后跳过只结束等待，不再给 Agent 发送消息。
        if value["status"] != "skipped":
            conversation.notify(task_id, value)

    background = BackgroundTools(on_answer)
    async with bumblehive.from_config(config) as runtime:
        @runtime.tools.tool(description=(
            "缺少关键信息时询问用户，可提供建议选项，也允许自由输入。"
            f"等待 {WAIT_SECONDS} 秒。answered 包含答案；skipped 表示跳过，不要重复问。"
            "pending 表示还未回答，晚到答案会带原问题作为消息送达。"
            "可以继续独立工作；必须依赖答案时说明阻碍并结束本轮。"
            "pending 和 skipped 都不代表同意，不要猜答案或重复提问。"
        ))
        async def ask_user(question: str, options: list[str] | None = None) -> dict:
            async def read() -> dict:
                return {"question": question, **await read_answer(question, options)}

            return await background.submit(read(), wait_seconds=WAIT_SECONDS)

        await conversation.run(
            runtime,
            "帮我写介绍 Python 的开场白，先用 ask_user 询问目标读者。"
            "等待时可以先列出通用提纲；收到答案再写正文。"
            "如果跳过，就只给通用提纲。不要重复提问。",
            background,
        )


if __name__ == "__main__":
    asyncio.run(main())
