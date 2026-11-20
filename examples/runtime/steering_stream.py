import asyncio
import os

import bumblehive
from bumblehive.observability import MODEL_STREAM_CONTENT_DELTA


async def main() -> None:
    config = bumblehive.RuntimeArguments(
        model=os.environ["BUMBLEHIVE_MODEL"],
        api_key=os.environ["BUMBLEHIVE_API_KEY"],
        base_url=os.environ["BUMBLEHIVE_BASE_URL"],
    )

    async with bumblehive.from_config(config) as runtime:
        stream = runtime.stream("用英文解释 Agent Loop。")
        stream.steer("改用中文，只说两句话。")

        async for event in stream:
            if event.kind == MODEL_STREAM_CONTENT_DELTA:
                print(event.payload["delta"], end="", flush=True)
        print()


if __name__ == "__main__":
    asyncio.run(main())
