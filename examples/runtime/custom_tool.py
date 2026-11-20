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
        tool_names=["get_course_info"],
    )
    async with bumblehive.from_config(config) as runtime:
        @runtime.tools.tool(
            description="查询课程的上课时间和地点。可查询的课程名：Python 入门。",
        )
        def get_course_info(course: str) -> str:
            return COURSES.get(course, f"没有找到课程：{course}")

        result = await runtime.run("请调用 get_course_info 查询课程“Python 入门”的上课时间和地点。")

    print("工具：", result.tools_used)
    print(result.final_content)


if __name__ == "__main__":
    asyncio.run(main())
