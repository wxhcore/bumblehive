import asyncio
import contextvars
import threading

import pytest

from bumblehive.tools import CallableTool


_REQUEST_ID = contextvars.ContextVar("request_id", default="missing")
_EMPTY_PARAMETERS = {
    "type": "object",
    "properties": {},
    "additionalProperties": False,
}


@pytest.mark.asyncio
async def test_callable_tool_runs_sync_handlers_off_loop_with_context_and_awaits_async_handlers() -> None:
    loop_thread = threading.get_ident()
    release_sync_handler = threading.Event()

    def sync_handler() -> tuple[str, int]:
        release_sync_handler.wait(timeout=1)
        return _REQUEST_ID.get(), threading.get_ident()

    async def async_handler() -> tuple[str, int]:
        await asyncio.sleep(0)
        return _REQUEST_ID.get(), threading.get_ident()

    sync_tool = CallableTool(
        name="sync",
        description="Sync handler.",
        parameters=_EMPTY_PARAMETERS,
        handler=sync_handler,
    )
    async_tool = CallableTool(
        name="async",
        description="Async handler.",
        parameters=_EMPTY_PARAMETERS,
        handler=async_handler,
    )

    token = _REQUEST_ID.set("run-7")
    try:
        sync_task = asyncio.create_task(sync_tool.execute())
        await asyncio.sleep(0)
        assert not sync_task.done()
        release_sync_handler.set()
        sync_result, async_result = await asyncio.gather(
            sync_task,
            async_tool.execute(),
        )
    finally:
        _REQUEST_ID.reset(token)

    assert sync_result[0] == async_result[0] == "run-7"
    assert sync_result[1] != loop_thread
    assert async_result[1] == loop_thread
