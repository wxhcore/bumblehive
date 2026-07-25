import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory

from bumblehive.protocols import ToolCall
from bumblehive.tools import PathAllowlist, ToolManager


async def main() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        workspace = root / "workspace"
        output = root / "output"
        workspace.mkdir()
        output.mkdir()

        tools = ToolManager()
        tools.register_builtin_tools()
        allowlist = PathAllowlist.from_roots(extra_write_roots=[output])

        written, read, listed = await tools.execute_many(
            [
                ToolCall(
                    id="write",
                    name="write_file",
                    arguments={
                        "path": str(output / "notes.txt"),
                        "content": "hello",
                    },
                ),
                ToolCall(
                    id="read",
                    name="read_file",
                    arguments={"path": str(output / "notes.txt")},
                ),
                ToolCall(
                    id="list",
                    name="list_dir",
                    arguments={"path": str(output)},
                ),
            ],
            workspace=workspace,
            path_allowlist=allowlist,
        )

        print("Written:", written.content)
        print("Read:", read.content)
        print("Listed:", listed.content)


if __name__ == "__main__":
    asyncio.run(main())
