import asyncio
import os

from bumblehive.agent import ToolCallingRunner
from bumblehive.protocols import GenerationConfig
from bumblehive.providers import ProviderManager
from bumblehive.tools import ToolManager


async def main() -> None:
    providers = ProviderManager()
    provider = await providers.get(
        api_key=os.environ["BUMBLEHIVE_API_KEY"],
        base_url=os.environ["BUMBLEHIVE_BASE_URL"],
    )
    tools = ToolManager()

    @tools.tool(
        name="multiply",
        description="Multiply two integers.",
    )
    def multiply(a: int, b: int) -> int:
        return a * b

    result = await ToolCallingRunner().run(
        provider=provider,
        tools=tools,
        model=os.environ["BUMBLEHIVE_MODEL"],
        messages=[
            {"role": "system", "content": "Use tools for calculations."},
            {"role": "user", "content": "What is 17 multiplied by 8?"},
        ],
        generation=GenerationConfig(temperature=0),
        workspace=".",
        tool_names=["multiply"],
    )
    await providers.close()

    print("Answer:", result.final_content)
    print("Messages:", len(result.messages))
    print("Usage:", result.usage)


if __name__ == "__main__":
    asyncio.run(main())
