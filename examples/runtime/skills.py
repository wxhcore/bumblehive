import asyncio
import os
from pathlib import Path

import bumblehive


async def main() -> None:
    config = bumblehive.RuntimeArguments(
        model=os.environ["BUMBLEHIVE_MODEL"],
        api_key=os.environ["BUMBLEHIVE_API_KEY"],
        base_url=os.environ["BUMBLEHIVE_BASE_URL"],
        workspace=Path(__file__).resolve().parents[1] / "skills",
        skills_dir=Path(__file__).resolve().parents[1] / "skills",
        skill_names=["course-summary"],
        tool_names=["read_file"],
    )
    async with bumblehive.from_config(config) as runtime:
        result = await runtime.run(
            "请读取并遵循 course-summary Skill，把 notes.md 整理成简短复习提纲。"
        )
        print(result.error.message if result.error else result.final_content)


if __name__ == "__main__":
    asyncio.run(main())
