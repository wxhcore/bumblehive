import asyncio
import os

import bumblehive


async def main() -> None:
    config = bumblehive.RuntimeArguments(
        model=os.environ["BUMBLEHIVE_MODEL"],
        api_key=os.environ["BUMBLEHIVE_API_KEY"],
        base_url=os.environ["BUMBLEHIVE_BASE_URL"],
    )
    async with bumblehive.from_config(config) as runtime:
        result = await runtime.run("请用一句话解释什么是 Agent Runtime。")

    print(result.final_content)


if __name__ == "__main__":
    asyncio.run(main())
