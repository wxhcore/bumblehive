import asyncio
import os
from pathlib import Path

import bumblehive


async def main() -> None:
    config = bumblehive.RuntimeArguments(
        model=os.environ["BUMBLEHIVE_MODEL"],
        api_key=os.environ["BUMBLEHIVE_API_KEY"],
        base_url=os.environ["BUMBLEHIVE_BASE_URL"],
        skill_names=[],
        workspace=Path(__file__).resolve().parent,
        tool_names=["list_dir", "read_file"],
    )
    async with bumblehive.from_config(config) as runtime:
        result = await runtime.run("读取 basic.py，用中文概括它做了什么。")
        print(result.error.message if result.error else result.final_content)


if __name__ == "__main__":
    asyncio.run(main())
