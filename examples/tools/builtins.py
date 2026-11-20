import asyncio
from tempfile import TemporaryDirectory

from bumblehive.protocols import ToolCall
from bumblehive.tools import ToolManager


async def main() -> None:
    with TemporaryDirectory() as directory:
        tools = ToolManager()
        tools.register_builtin_tools()

        written, read, listed = await tools.execute_many(
            [
                ToolCall(
                    id="write",
                    name="write_file",
                    arguments={
                        "path": "notes.txt",
                        "content": "hello",
                    },
                ),
                ToolCall(
                    id="read",
                    name="read_file",
                    arguments={"path": "notes.txt"},
                ),
                ToolCall(
                    id="list",
                    name="list_dir",
                    arguments={"path": "."},
                ),
            ],
            workspace=directory,
        )

        print("Written:", written.content)
        print("Read:", read.content)
        print("Listed:", listed.content)


if __name__ == "__main__":
    asyncio.run(main())
