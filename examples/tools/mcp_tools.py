import asyncio
import os

from bumblehive.protocols import MCPServerConfig
from bumblehive.tools import ToolManager


async def main() -> None:
    server = MCPServerConfig(
        name="example",
        url=os.environ["BUMBLEHIVE_MCP_URL"],
    )
    async with ToolManager(mcp_servers=[server]) as tools:
        registered = await tools.connect_mcp()
        print("Registered tools:", registered)


if __name__ == "__main__":
    asyncio.run(main())
