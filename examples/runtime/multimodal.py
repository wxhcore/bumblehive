import argparse
import asyncio
import base64
import mimetypes
import os
from pathlib import Path

import bumblehive


async def main(path: Path) -> None:
    image = base64.b64encode(path.read_bytes()).decode("ascii")
    mime = mimetypes.guess_type(path.name)[0] or "image/png"
    config = bumblehive.RuntimeArguments(
        model=os.environ["BUMBLEHIVE_MODEL"],
        api_key=os.environ["BUMBLEHIVE_API_KEY"],
        base_url=os.environ["BUMBLEHIVE_BASE_URL"],
        skill_names=[],
        tool_names=[],
    )
    async with bumblehive.from_config(config) as runtime:
        result = await runtime.run([{
            "role": "user",
            "content": [
                {"type": "text", "text": "描述这张图片。"},
                {"type": "image_url", "image_url": {
                    "url": f"data:{mime};base64,{image}",
                }},
            ],
        }])
        print(result.error.message if result.error else result.final_content)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("image", type=Path)
    asyncio.run(main(parser.parse_args().image))
