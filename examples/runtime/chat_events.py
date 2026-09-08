"""Map SDK events to small UI updates; print JSON lines as a transport example."""

import asyncio
import json
import os
from typing import Any

import bumblehive
from bumblehive.observability import (
    MODEL_STREAM_CONTENT_DELTA,
    TOOL_CALL_FINISHED,
    TOOL_CALL_STARTED,
)


def to_ui_update(event: bumblehive.AgentEvent) -> dict[str, Any] | None:
    update: dict[str, Any] = {"run_id": event.run_id, "session_id": event.session_id}
    if event.kind == MODEL_STREAM_CONTENT_DELTA:
        return {**update, "type": "text_delta", "text": event.payload["delta"]}
    if event.kind == TOOL_CALL_STARTED:
        call = event.payload["tool_call"]
        return {
            **update,
            "type": "tool_started",
            "call_id": call["call_id"],
            "name": call["name"],
        }
    if event.kind == TOOL_CALL_FINISHED:
        result = event.payload["tool_result"]
        return {
            **update,
            "type": "tool_finished",
            "call_id": result["tool_call_id"],
            "ok": event.payload["ok"],
        }
    return None


def send(update: dict[str, Any]) -> None:
    # A real application sends this update through its WebSocket or SSE layer.
    print(json.dumps(update, ensure_ascii=False), flush=True)


async def main() -> None:
    config = bumblehive.RuntimeArguments(
        model=os.environ["BUMBLEHIVE_MODEL"],
        api_key=os.environ["BUMBLEHIVE_API_KEY"],
        base_url=os.environ["BUMBLEHIVE_BASE_URL"],
        tool_names=["add"],
    )
    async with bumblehive.from_config(config) as runtime:
        @runtime.tools.tool(name="add", description="计算两个整数的和。")
        def add(a: int, b: int) -> int:
            return a + b

        stream = runtime.stream("请调用 add 计算 21 加 34。", session_id="chat-events-demo")
        try:
            async for event in stream:
                update = to_ui_update(event)
                if update is not None:
                    send(update)
            result = await stream.result()
            send({
                "type": "finished",
                "text": result.final_content,
                "usage": result.usage,
                "error": result.error.message if result.error else None,
            })
        finally:
            await stream.aclose()


if __name__ == "__main__":
    asyncio.run(main())
