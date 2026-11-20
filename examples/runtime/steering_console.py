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
        run = runtime.run_console("用英文解释 Agent Loop。")
        run.steer("改用中文，只说两句话。")
        await run


if __name__ == "__main__":
    asyncio.run(main())
