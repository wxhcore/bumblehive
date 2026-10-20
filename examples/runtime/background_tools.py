"""从仓库根目录运行：python -m examples.runtime.background_tools"""

import asyncio
import os

import bumblehive
from examples.runtime.background_support import BackgroundTools, Conversation


async def main() -> None:
    config = bumblehive.RuntimeArguments(
        model=os.environ["BUMBLEHIVE_MODEL"],
        api_key=os.environ["BUMBLEHIVE_API_KEY"],
        base_url=os.environ["BUMBLEHIVE_BASE_URL"],
        skill_names=[],
        tool_names=["make_report"],
    )
    conversation = Conversation()
    jobs = BackgroundTools(conversation.notify)
    async with bumblehive.from_config(config) as runtime:
        @runtime.tools.tool(description=(
            "生成统计报告。background=true 立即后台执行；false 等待完成。"
            "pending 只是处理中，结果随后会作为消息送达；不要重复发起。"
        ))
        async def make_report(background: bool = True) -> dict:
            async def work() -> dict:
                await asyncio.sleep(3)  # 模拟耗时计算。
                return {"orders": 12, "total_yuan": 360}

            return await jobs.submit(
                work(), wait_seconds=0 if background else None,
            )

        await conversation.run(
            runtime,
            "请调用 make_report 后台生成报告，先说明报告可用于什么，"
            "收到实际结果后再总结数字。不要重复调用。",
            jobs,
        )


if __name__ == "__main__":
    asyncio.run(main())
