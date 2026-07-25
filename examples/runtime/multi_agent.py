import asyncio
import os

import bumblehive


READ_ONLY_TOOLS = ("read_file", "list_dir", "find_files", "grep")


async def main() -> None:
    config = bumblehive.RuntimeArguments(
        model=os.environ["BUMBLEHIVE_MODEL"],
        api_key=os.environ["BUMBLEHIVE_API_KEY"],
        base_url=os.getenv("BUMBLEHIVE_BASE_URL"),
        workspace=".",
        tool_names=["sub_agent"],
    )

    async with bumblehive.from_config(config) as runtime:
        @runtime.tools.tool(
            name="sub_agent",
            description="Delegate a self-contained task to a stateless sub-agent.",
        )
        async def sub_agent(task: str) -> str:
            response = await runtime.run(
                task,
                config={"agent": {"tool_names": READ_ONLY_TOOLS}},
            )
            return response.final_content or ""

        result = await runtime.run(
            "Ask a sub-agent to explain the main modules in this project."
        )

    print(result.final_content)


if __name__ == "__main__":
    asyncio.run(main())
