import asyncio
import os

import bumblehive


COURSES = {
    "Python 入门": "周一 10:00，教学楼 A101",
}


async def main() -> None:
    config = bumblehive.RuntimeArguments(
        model=os.environ["BUMBLEHIVE_MODEL"],
        api_key=os.environ["BUMBLEHIVE_API_KEY"],
        base_url=os.environ["BUMBLEHIVE_BASE_URL"],
        skill_names=[],
        agent_instructions=("回答课程问题前，必须先调用 get_course_info 工具。"),
        tool_names=["get_course_info"],
    )
    async with bumblehive.from_config(config) as runtime:
        @runtime.tools.tool(
            name="get_course_info",
            description="查询课程的上课时间和地点。可查询的课程名：Python 入门。",
        )
        def get_course_info(course: str) -> str:
            return COURSES.get(course, f"没有找到课程：{course}")

        result = await runtime.run("请查询课程“Python 入门”的上课时间和地点。")

    if result.error is not None:
        print(f"运行失败 [{result.error.code}]：{result.error.message}")
        return

    print(f"工具：{', '.join(result.tools_used) or '未调用工具'}")
    print(f"回答：{result.final_content}")


if __name__ == "__main__":
    asyncio.run(main())
