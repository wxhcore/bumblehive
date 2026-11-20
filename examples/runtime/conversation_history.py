import asyncio
import os

import bumblehive


async def main() -> None:
    config = bumblehive.RuntimeArguments(
        model=os.environ["BUMBLEHIVE_MODEL"],
        api_key=os.environ["BUMBLEHIVE_API_KEY"],
        base_url=os.environ["BUMBLEHIVE_BASE_URL"],
    )
    history = bumblehive.MessageHistory()

    async with bumblehive.from_config(config) as runtime:
        first = await runtime.run(
            "Remember that my project is named Bumblehive.",
            history=history,
        )
        history.replace_run_messages(first.messages)
        second = await runtime.run(
            "What is my project named?",
            history=history,
        )

    print(second.final_content)


if __name__ == "__main__":
    asyncio.run(main())
