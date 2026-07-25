import asyncio
import os

from bumblehive.agent import (
    AgentLoop,
    ContextBuilder,
    ToolCallingRunner,
)
from bumblehive.providers import ProviderManager
from bumblehive.skills import SkillsManager
from bumblehive.tools import ToolManager


async def main() -> None:
    providers = ProviderManager()
    provider = await providers.get(
        api_key=os.environ["BUMBLEHIVE_API_KEY"],
        base_url=os.getenv("BUMBLEHIVE_BASE_URL"),
    )

    loop = AgentLoop(
        tools=ToolManager(),
        context=ContextBuilder(),
        skills=SkillsManager(),
        runner=ToolCallingRunner(),
    )

    result = await loop.run_turn(
        "Which project and audience are you helping?",
        provider=provider,
        model=os.environ["BUMBLEHIVE_MODEL"],
        workspace=".",
        dynamic_context={
            "project": "Bumblehive",
            "audience": "Python SDK developers",
        },
        agent_instructions="Answer in one sentence using the runtime context.",
        skill_names=[],
        tool_names=[],
    )
    await providers.close()

    print("Answer:", result.final_content)


if __name__ == "__main__":
    asyncio.run(main())
