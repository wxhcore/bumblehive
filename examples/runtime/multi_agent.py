import asyncio
import os

import bumblehive


READ_ONLY_TOOLS = ("read_file", "list_dir", "find_files", "grep")


async def main() -> None:
    config = bumblehive.RuntimeArguments(
        model=os.environ["BUMBLEHIVE_MODEL"],
        api_key=os.environ["BUMBLEHIVE_API_KEY"],
        base_url=os.environ["BUMBLEHIVE_BASE_URL"],
        skill_names=[],
        workspace=".",
        tool_names=["sub_agent"],
    )

    async with bumblehive.from_config(config) as runtime:
        @runtime.tools.tool(
            name="sub_agent",
            description="把独立的文件阅读任务交给子 Agent，等待并返回它的回答。",
        )
        async def sub_agent(task: str) -> str:
            response = await runtime.run(
                task,
                config={"agent": {"tool_names": READ_ONLY_TOOLS}},
            )
            if response.error:
                raise RuntimeError(response.error.message)
            return response.final_content or ""

        result = await runtime.run(
            "请让子 Agent 阅读 README_zh.md，用三句话概括这个项目的用途。"
        )

    print(result.final_content)


if __name__ == "__main__":
    asyncio.run(main())
