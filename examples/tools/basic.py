import asyncio

from bumblehive.protocols import ToolCall
from bumblehive.tools import ToolManager


async def main() -> None:
    tools = ToolManager()

    @tools.tool(description="Add two integers.")
    def add(a: int, b: int) -> int:
        return a + b

    call = ToolCall(id="sum", name="add", arguments={"a": 2, "b": 5})
    result = await tools.execute_call(call)
    print(result.content)


if __name__ == "__main__":
    asyncio.run(main())
