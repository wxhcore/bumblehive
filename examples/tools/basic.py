import asyncio

from bumblehive.protocols import ToolCall
from bumblehive.tools import CallableTool, ToolManager


async def main() -> None:
    tools = ToolManager()

    @tools.tool(
        name="add",
        description="Add two integers.",
        parallel_safe=True,
    )
    def add(a: int, b: int) -> int:
        return a + b

    async def uppercase(text: str) -> str:
        return text.upper()

    tools.register(
        CallableTool(
            name="uppercase",
            description="Convert text to uppercase.",
            parameters={
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
                "additionalProperties": False,
            },
            handler=uppercase,
            parallel_safe=True,
        )
    )

    definitions = tools.get_openai_tool_definitions()
    results = await tools.execute_many(
        [
            ToolCall(id="add", name="add", arguments={"a": "2", "b": 5}),
            ToolCall(
                id="uppercase",
                name="uppercase",
                arguments={"text": "bumblehive"},
            ),
        ]
    )
    tools.unregister("uppercase")

    print("Tools:", [item["function"]["name"] for item in definitions])
    print("Results:", [result.content for result in results])
    print("Remaining tools:", tools.tool_names)


if __name__ == "__main__":
    asyncio.run(main())
