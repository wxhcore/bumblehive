"""从仓库根目录运行：python -m examples.runtime.multi_agent_background"""

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
        tool_names=["sub_agent"],
    )
    conversation = Conversation()
    jobs = BackgroundTools(conversation.notify)
    async with bumblehive.from_config(config) as runtime:
        @runtime.tools.tool(description=(
            "把独立任务交给子 Agent。background 默认 true，立即返回 pending，"
            "完成结果随后作为消息送达，不要重复委派。"
            "下一步必须依赖结果时传 false，等待结果再继续。"
        ))
        async def sub_agent(task: str, background: bool = True) -> dict:
            async def work() -> dict:
                result = await runtime.run(
                    task, config={"agent": {
                        "instructions": "你是写作助手。直接给出简短答案，不使用工具。",
                        "tool_names": [],
                        "skill_names": [],
                    }},
                )
                if result.error:
                    raise RuntimeError(result.error.message)
                return {"answer": result.final_content}

            return await jobs.submit(work(), wait_seconds=0 if background else None)

        await conversation.run(
            runtime,
            "准备一篇 Python 入门文章。把“用 100 字以内设计一道列表练习题，不写参考答案”"
            "交给子 Agent 后台完成。你先列三个提纲要点，收到练习题后简短整合。只委派一次。",
            jobs,
        )


if __name__ == "__main__":
    asyncio.run(main())
