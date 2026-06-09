import asyncio
import inspect
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from ..base import Tool


@dataclass(frozen=True)
class CallableTool(Tool):
    """A callable object exposed as an LLM-callable tool."""

    handler: Callable[..., Any]

    async def execute(self, **kwargs: Any) -> Any:
        """Execute the wrapped function, supporting sync and async functions."""
        if inspect.iscoroutinefunction(self.handler):
            return await self.handler(**kwargs)

        return await asyncio.to_thread(self.handler, **kwargs)
