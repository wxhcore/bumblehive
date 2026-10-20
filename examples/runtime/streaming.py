import asyncio
import os

import bumblehive
from bumblehive.observability import MODEL_STREAM_CONTENT_DELTA


async def main() -> None:
    config = bumblehive.RuntimeArguments(
        model=os.environ["BUMBLEHIVE_MODEL"],
        api_key=os.environ["BUMBLEHIVE_API_KEY"],
        base_url=os.environ["BUMBLEHIVE_BASE_URL"],
        skill_names=[],
        tool_names=[],
    )
    async with bumblehive.from_config(config) as runtime:
        stream = runtime.stream("用三句话解释 Agent Loop。")
        try:
            async for event in stream:
                if event.kind == MODEL_STREAM_CONTENT_DELTA:
                    print(event.payload["delta"], end="", flush=True)
            result = await stream.result()
        finally:
            await stream.aclose()
        print()
        if result.error:
            print(result.error.message)


if __name__ == "__main__":
    asyncio.run(main())
