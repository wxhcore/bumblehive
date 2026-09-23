import asyncio
import os
from pathlib import Path

import bumblehive
from bumblehive.console import ConsoleStreamRenderer


def resolve_path(path: str | Path, workspace: Path) -> Path:
    """Resolve a local path relative to the tool call's workspace."""
    raw = Path(path).expanduser()
    return raw.resolve() if raw.is_absolute() else (workspace / raw).resolve()


async def main() -> None:
    workspace = Path(__file__).resolve().parent
    print(f"工作目录：{workspace}")
    renderer = ConsoleStreamRenderer()

    async def approve_tool(
        request: bumblehive.ToolApprovalRequest,
    ) -> bumblehive.ToolApprovalDecision:
        target = resolve_path(request.arguments["path"], request.workspace)
        if target.is_relative_to(request.workspace):
            return bumblehive.ToolApprovalDecision.approve()

        with renderer.pause():
            print(f"工具：{request.name}")
            print(f"工作目录：{request.workspace}")
            print(f"目标路径：{target}")
            print(f"写入内容：\n{request.arguments['content']}")
            answer = await asyncio.to_thread(
                input,
                "允许写入工作目录外的文件？[y/N] ",
            )
            approved = answer.strip().lower() in {"y", "yes"}
            print("已批准工具调用：" if approved else "已拒绝工具调用：", request.name)
        if approved:
            return bumblehive.ToolApprovalDecision.approve()
        return bumblehive.ToolApprovalDecision.reject("The user rejected this file write.")

    config = bumblehive.RuntimeArguments(
        model=os.environ["BUMBLEHIVE_MODEL"],
        api_key=os.environ["BUMBLEHIVE_API_KEY"],
        base_url=os.environ["BUMBLEHIVE_BASE_URL"],
        workspace=workspace,
        tool_names=["write_file"],
    )

    async with bumblehive.from_config(config) as runtime:
        await runtime.run_console(
            "请依次调用 write_file 创建两个文件："
            "先创建 approval-demo.txt，内容为 hello inside；"
            "再创建 ../approval-outside-demo.txt，内容为 hello outside。"
            "如果调用被拒绝，不要重试，直接说明文件未创建。",
            approval_handler=approve_tool,
            renderer=renderer,
        )


if __name__ == "__main__":
    asyncio.run(main())
