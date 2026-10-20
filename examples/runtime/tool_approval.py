import asyncio
import os
from pathlib import Path

import bumblehive
async def main() -> None:
    workspace = Path(__file__).resolve().parent
    print(f"工作目录：{workspace}")

    async def approve_tool(
        request: bumblehive.ToolApprovalRequest,
    ) -> bumblehive.ToolApprovalDecision:
        print(f"工具：{request.name}\n参数：{dict(request.arguments)}")
        answer = await asyncio.to_thread(input, "允许执行？[y/N] ")
        if answer.strip().lower() in {"y", "yes"}:
            print("已批准")
            return bumblehive.ToolApprovalDecision.approve()
        print("已拒绝")
        return bumblehive.ToolApprovalDecision.reject("用户拒绝写入，请勿重试。")

    config = bumblehive.RuntimeArguments(
        model=os.environ["BUMBLEHIVE_MODEL"],
        api_key=os.environ["BUMBLEHIVE_API_KEY"],
        base_url=os.environ["BUMBLEHIVE_BASE_URL"],
        workspace=workspace,
        skill_names=[],
        tool_names=["write_file"],
    )

    async with bumblehive.from_config(config) as runtime:
        result = await runtime.run(
            "请调用 write_file 创建 approval-demo.txt，内容为 hello。"
            "如果调用被拒绝，不要重试，直接说明文件未创建。",
            approval_handler=approve_tool,
        )
        print(result.error.message if result.error else result.final_content)


if __name__ == "__main__":
    asyncio.run(main())
