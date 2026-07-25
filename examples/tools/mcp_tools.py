import asyncio
import os

from bumblehive.protocols import MCPServerConfig
from bumblehive.tools import ToolManager


async def main() -> None:
    server = MCPServerConfig(
        name="example",
        url=os.environ["BUMBLEHIVE_MCP_URL"],
    )
    tools = ToolManager(mcp_servers=[server])

    registered = await tools.connect_mcp()
    status = tools.get_mcp_server_status("example")

    print("Registered tools:", registered)
    print("Connected:", status.connected if status else False)
    print("Available tools:", tools.tool_names)

    await tools.close()


if __name__ == "__main__":
    asyncio.run(main())
