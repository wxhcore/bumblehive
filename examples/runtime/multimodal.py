import asyncio
import os

import bumblehive


user_input = [
    {
        "role": "user",
        "content": [
            {
                "type": "image_url",
                "image_url": {
                    # URL or Base64 Data URL:
                    # data:image/png;base64,<base64-data>
                    "url": "https://example.com/image.png",
                },
            },
            {
                "type": "text",
                "text": "这张图片是什么？",
            },
        ],
    }
]


async def main() -> None:
    config = bumblehive.RuntimeArguments(
        model=os.environ["BUMBLEHIVE_MODEL"],
        api_key=os.environ["BUMBLEHIVE_API_KEY"],
        base_url=os.environ["BUMBLEHIVE_BASE_URL"],
    )

    async with bumblehive.from_config(config) as runtime:
        result = await runtime.run(user_input)

    print(result.final_content)


if __name__ == "__main__":
    asyncio.run(main())
