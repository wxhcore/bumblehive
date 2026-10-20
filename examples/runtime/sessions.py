import asyncio
import os

import bumblehive


async def main() -> None:
    config = bumblehive.RuntimeArguments(
        model=os.environ["BUMBLEHIVE_MODEL"],
        api_key=os.environ["BUMBLEHIVE_API_KEY"],
        base_url=os.environ["BUMBLEHIVE_BASE_URL"],
        skill_names=[],
        tool_names=[],
    )
    async with bumblehive.from_config(config) as runtime:
        first = await runtime.run("记住：我的项目叫 BumbleHive。", session_id="hello-agent")
        print(first.error.message if first.error else first.final_content)
        second = await runtime.run("我的项目叫什么？", session_id="hello-agent")
        print(second.error.message if second.error else second.final_content)


if __name__ == "__main__":
    asyncio.run(main())
