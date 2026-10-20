"""最小追问：等待回答；输入 /skip 跳过。"""

import asyncio
import os

import bumblehive


async def read_answer(question: str, options: list[str] | None = None) -> dict:
    print(f"\n问题：{question}")
    choices = options or []
    for index, option in enumerate(choices, 1):
        print(f"  {index}. {option}")
    while True:
        answer = (await asyncio.to_thread(
            input, "输入答案或选项编号；/skip 跳过："
        )).strip()
        if answer == "/skip":
            return {"status": "skipped"}
        if not answer:
            continue
        if answer.isdecimal() and 1 <= int(answer) <= len(choices):
            answer = choices[int(answer) - 1]
        return {"status": "answered", "answer": answer}


async def main() -> None:
    config = bumblehive.RuntimeArguments(
        model=os.environ["BUMBLEHIVE_MODEL"],
        api_key=os.environ["BUMBLEHIVE_API_KEY"],
        base_url=os.environ["BUMBLEHIVE_BASE_URL"],
        skill_names=[],
        tool_names=["ask_user"],
    )
    async with bumblehive.from_config(config) as runtime:
        @runtime.tools.tool(
            description=(
                "缺少无法从上下文确定的关键信息时，向用户提出一个简短问题。"
                "可提供建议选项，用户也能自由输入。"
                "answered 包含回答；skipped 表示用户跳过，不要重复提问或当作同意。"
            ),
        )
        async def ask_user(question: str, options: list[str] | None = None) -> dict:
            return await read_answer(question, options)

        result = await runtime.run(
            "帮我写一段介绍 Python 的开场白。请先用 ask_user 询问目标读者，"
            "收到回答后再写；如果用户跳过，就写一个通用版本。"
        )
        print(result.error.message if result.error else result.final_content)


if __name__ == "__main__":
    asyncio.run(main())
