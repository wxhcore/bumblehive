import asyncio
import os

import bumblehive
from bumblehive.protocols import MCPServerConfig


async def main() -> None:
    config = bumblehive.RuntimeArguments(
        model=os.environ["BUMBLEHIVE_MODEL"],
        api_key=os.environ["BUMBLEHIVE_API_KEY"],
        base_url=os.environ["BUMBLEHIVE_BASE_URL"],
        skill_names=[],
        mcp_servers=(MCPServerConfig(
            name="courses",
            url="http://127.0.0.1:8000/mcp",
            enabled_tools=["get_course_info"],
        ),),
        tool_names=["mcp_courses_get_course_info"],
    )
    async with bumblehive.from_config(config) as runtime:
        result = await runtime.run("请查询课程“Python 入门”的上课时间和地点。")
        print(result.error.message if result.error else result.final_content)


if __name__ == "__main__":
    asyncio.run(main())
