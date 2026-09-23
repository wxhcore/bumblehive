"""Run a file-editing task with an explicit workspace and human approval."""

import asyncio
import json
import os
from pathlib import Path

import bumblehive
from bumblehive.console import ConsoleStreamRenderer


async def main() -> None:
    workspace = Path(__file__).resolve().parent / "file-assistant-workspace"
    workspace.mkdir(exist_ok=True)
    source = workspace / "notes.txt"
    if not source.exists():
        source.write_text("Bumblehive documantation\n", encoding="utf-8")
    print(f"工作目录：{workspace}")
    renderer = ConsoleStreamRenderer()

    async def approve_tool(
        request: bumblehive.ToolApprovalRequest,
    ) -> bumblehive.ToolApprovalDecision:
        if request.name in {"read_file", "list_dir", "find_files", "grep"}:
            return bumblehive.ToolApprovalDecision.approve()
        with renderer.pause():
            arguments = json.dumps(dict(request.arguments), ensure_ascii=False)
            answer = await asyncio.to_thread(
                input, f"允许 {request.name}({arguments})？[y/N] "
            )
        if answer.strip().lower() in {"y", "yes"}:
            return bumblehive.ToolApprovalDecision.approve()
        return bumblehive.ToolApprovalDecision.reject("The user rejected this operation.")

    config = bumblehive.RuntimeArguments(
        model=os.environ["BUMBLEHIVE_MODEL"],
        api_key=os.environ["BUMBLEHIVE_API_KEY"],
        base_url=os.environ["BUMBLEHIVE_BASE_URL"],
        workspace=workspace,
        tool_names=["read_file", "list_dir", "find_files", "grep", "edit_file", "exec"],
        max_iterations=8,
    )
    async with bumblehive.from_config(config) as runtime:
        result = await runtime.run_console(
            "读取 notes.txt，把拼写错误 documantation 改为 documentation。"
            "修改后再次读取文件，并运行一条 Python 命令检查拼写是否正确。"
            "如果审批被拒绝，不要尝试其他修改方式，直接说明未完成的步骤。",
            approval_handler=approve_tool,
            renderer=renderer,
        )
    if result.error:
        print(f"运行失败：{result.error.message}")
    print(f"最终文件内容：{source.read_text(encoding='utf-8').strip()}")


if __name__ == "__main__":
    asyncio.run(main())
