import asyncio
import os

from bumblehive.providers import ModelRequest, ProviderManager


async def main() -> None:
    providers = ProviderManager()
    provider = await providers.get(
        api_key=os.environ["BUMBLEHIVE_API_KEY"],
        base_url=os.environ["BUMBLEHIVE_BASE_URL"],
    )
    response = await provider.generate_with_retry(
        ModelRequest(
            model=os.environ["BUMBLEHIVE_MODEL"],
            messages=[
                {"role": "user", "content": "Reply with one short sentence."}
            ],
        )
    )
    await providers.close()

    print("Content:", response.content)
    print("Usage:", response.usage)


if __name__ == "__main__":
    asyncio.run(main())
