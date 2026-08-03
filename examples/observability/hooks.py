import asyncio
import os

import bumblehive
from bumblehive.observability import (
    FINAL_RESULT,
    MODEL_RESPONSE_FINISHED,
    AgentEvent,
    EventRecorder,
)


def print_event(event: AgentEvent) -> None:
    if event.kind in {MODEL_RESPONSE_FINISHED, FINAL_RESULT}:
        print(event.kind, event.payload)


async def main() -> None:
    config = bumblehive.RuntimeArguments(
        model=os.environ["BUMBLEHIVE_MODEL"],
        api_key=os.environ["BUMBLEHIVE_API_KEY"],
        base_url=os.environ["BUMBLEHIVE_BASE_URL"],
        tool_names=[],
    )
    recorder = EventRecorder()

    async with bumblehive.from_config(config) as runtime:
        result = await runtime.run(
            "Reply with a short greeting.",
            hooks=[print_event, recorder],
        )

    print("Answer:", result.final_content)
    print("Recorded events:", len(recorder.events))
    print("Final events:", len(recorder.by_kind(FINAL_RESULT)))


if __name__ == "__main__":
    asyncio.run(main())
