import asyncio
import os

import bumblehive


async def main() -> None:
    config = bumblehive.RuntimeArguments(
        model=os.environ["BUMBLEHIVE_MODEL"],
        api_key=os.environ["BUMBLEHIVE_API_KEY"],
        base_url=os.environ["BUMBLEHIVE_BASE_URL"],
        agent_instructions="你是项目助手。回答简洁，只依据给定的项目事实。",
        dynamic_context={"project": "BumbleHive", "stage": "文档整理"},
        skill_names=[],
        tool_names=[],
    )
    async with bumblehive.from_config(config) as runtime:
        result = await runtime.run("我们正在做什么？建议下一步工作。")
        print(result.error.message if result.error else result.final_content)


if __name__ == "__main__":
    asyncio.run(main())
