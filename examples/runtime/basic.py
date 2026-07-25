import asyncio
import os

import bumblehive


async def main() -> None:
    config = bumblehive.RuntimeArguments(
        model=os.environ["BUMBLEHIVE_MODEL"],
        api_key=os.environ["BUMBLEHIVE_API_KEY"],
        base_url=os.getenv("BUMBLEHIVE_BASE_URL"),
        workspace=".",
        tool_names=[],  # Expose no tools, including built-ins.
    )

    runtime = bumblehive.from_config(config)
    result = await runtime.run("Explain the purpose of an agent runtime in one sentence.")
    await runtime.close()

    print("Answer:", result.final_content)
    print("Usage:", result.usage)


if __name__ == "__main__":
    asyncio.run(main())
