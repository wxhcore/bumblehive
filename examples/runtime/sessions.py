import asyncio
import os
from uuid import uuid4

import bumblehive


async def main() -> None:
    config = bumblehive.RuntimeArguments(
        model=os.environ["BUMBLEHIVE_MODEL"],
        api_key=os.environ["BUMBLEHIVE_API_KEY"],
        base_url=os.getenv("BUMBLEHIVE_BASE_URL"),
    )
    session_id = f"example:{uuid4()}"

    async with bumblehive.from_config(config) as runtime:
        await runtime.run(
            "Remember that the release color is amber.",
            session_id=session_id,
        )
        result = await runtime.run(
            "What is the release color?",
            session_id=session_id,
        )
        await runtime.delete_session(session_id)

    print(result.final_content)


if __name__ == "__main__":
    asyncio.run(main())
