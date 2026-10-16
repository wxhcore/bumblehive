import asyncio
import os

import bumblehive
from bumblehive.observability import TOOL_CALL_STARTED, AgentEvent


async def main() -> None:
    config = bumblehive.RuntimeArguments(
        model=os.environ["BUMBLEHIVE_MODEL"],
        api_key=os.environ["BUMBLEHIVE_API_KEY"],
        base_url=os.environ["BUMBLEHIVE_BASE_URL"],
        agent_instructions="回答课程问题前，先调用 get_course_info 查询，不要猜测。",
        skill_names=[],
        tool_names=["get_course_info"],
    )

    async with bumblehive.from_config(config) as runtime:

        @runtime.tools.tool(description="查询 Python 入门课的时间和地点。")
        def get_course_info() -> str:
            info = "Python 入门：周一 10:00，教学楼 A101。"
            print("工具结果：", info)
            return info

        steered = False

        def on_event(event: AgentEvent) -> None:
            nonlocal steered
            if event.kind == TOOL_CALL_STARTED and not steered:
                steered = True
                print("模型开始调用工具，追加引导。")
                # 工具继续执行；引导会追加在工具结果之后。
                run.steer("改用中文，只说两句话。")

        run = runtime.run(
            "查询 Python 入门课的时间和地点，用英文回答。", hooks=on_event
        )
        result = await run

    if result.error is not None:
        print(f"运行失败：{result.error.message}")
    else:
        print("最终回答：", result.final_content)


if __name__ == "__main__":
    asyncio.run(main())
