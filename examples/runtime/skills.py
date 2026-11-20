import asyncio
import os
from pathlib import Path

import bumblehive


async def main() -> None:
    skills_dir = Path(__file__).resolve().parents[1] / "skills"
    config = bumblehive.RuntimeArguments(
        model=os.environ["BUMBLEHIVE_MODEL"],
        api_key=os.environ["BUMBLEHIVE_API_KEY"],
        base_url=os.environ["BUMBLEHIVE_BASE_URL"],
        workspace=skills_dir,
        skills_dir=skills_dir,
        skill_names=["course-summary"],
        tool_names=["read_file"],
    )
    async with bumblehive.from_config(config) as runtime:
        result = await runtime.run(
            "请读取并遵循 course-summary Skill，把 notes.md 整理成简短复习提纲。"
        )
        print(result.final_content)


if __name__ == "__main__":
    asyncio.run(main())
