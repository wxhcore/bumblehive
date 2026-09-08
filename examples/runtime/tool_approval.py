import asyncio
import json
import os

import bumblehive
from bumblehive.console import ConsoleStreamRenderer


async def main() -> None:
    renderer = ConsoleStreamRenderer()

    async def approve_tool(
        request: bumblehive.ToolApprovalRequest,
    ) -> bumblehive.ToolApprovalDecision:
        arguments = json.dumps(dict(request.arguments), ensure_ascii=False)
        with renderer.pause():
            answer = await asyncio.to_thread(
                input,
                f"允许调用 {request.name}({arguments})？[y/N] ",
            )
        if answer.strip().lower() in {"y", "yes"}:
            return bumblehive.ToolApprovalDecision.approve()
        return bumblehive.ToolApprovalDecision.reject("Rejected by user.")

    config = bumblehive.RuntimeArguments(
        model=os.environ["BUMBLEHIVE_MODEL"],
        api_key=os.environ["BUMBLEHIVE_API_KEY"],
        base_url=os.environ["BUMBLEHIVE_BASE_URL"],
        agent_instructions=(
            "需要发送通知时，调用 send_notification 一次。"
            "如果调用被拒绝，不要重试，直接说明通知未发送。"
        ),
        tool_names=["send_notification"],
    )

    async with bumblehive.from_config(config) as runtime:
        @runtime.tools.tool(
            name="send_notification",
            description="向项目成员发送一条通知。",
        )
        def send_notification(message: str) -> str:
            print(f"通知已发送：{message}")
            return "Notification sent."

        await runtime.run_console(
            "通知项目成员：今天下午三点开会。",
            approval_handler=approve_tool,
            renderer=renderer,
        )


if __name__ == "__main__":
    asyncio.run(main())
