import asyncio
import json
import os
from pathlib import Path

import bumblehive
from bumblehive.console import ConsoleStreamRenderer


async def main() -> None:
    workspace = Path(__file__).resolve().parent
    print(f"工作目录：{workspace}")
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
            approved = answer.strip().lower() in {"y", "yes"}
            print("已批准工具调用：" if approved else "已拒绝工具调用：", request.name)
        if approved:
            return bumblehive.ToolApprovalDecision.approve()
        return bumblehive.ToolApprovalDecision.reject("用户拒绝了这次文件写入。")

    config = bumblehive.RuntimeArguments(
        model=os.environ["BUMBLEHIVE_MODEL"],
        api_key=os.environ["BUMBLEHIVE_API_KEY"],
        base_url=os.environ["BUMBLEHIVE_BASE_URL"],
        workspace=workspace,
        tool_names=["write_file"],
    )

    async with bumblehive.from_config(config) as runtime:
        await runtime.run_console(
            "请调用 write_file 创建 approval-demo.txt，内容为 hello。"
            "如果调用被拒绝，不要重试，直接说明文件未创建。",
            approval_handler=approve_tool,
            renderer=renderer,
        )


if __name__ == "__main__":
    asyncio.run(main())
