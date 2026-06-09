import asyncio
from dataclasses import dataclass
from typing import Any

from ..base import Tool

_TRANSIENT_MCP_ERROR_NAMES = frozenset(
    {
        "ClosedResourceError",
        "BrokenResourceError",
        "EndOfStream",
        "BrokenPipeError",
        "ConnectionResetError",
        "ConnectionRefusedError",
        "ConnectionAbortedError",
        "ConnectionError",
    }
)
_TRANSIENT_RETRY_DELAY_SECONDS = 0.1


def _is_transient_mcp_error(exc: BaseException) -> bool:
    """Return true for MCP transport errors worth retrying once."""
    return type(exc).__name__ in _TRANSIENT_MCP_ERROR_NAMES


def _text_from_content_blocks(blocks: Any) -> str:
    parts: list[str] = []
    for block in blocks:
        if getattr(block, "type", None) == "text" and hasattr(block, "text"):
            parts.append(block.text)
        elif hasattr(block, "model_dump_json"):
            parts.append(block.model_dump_json())
        else:
            parts.append(str(block))
    return "\n".join(parts) or "(no output)"


def _mcp_result_payload(result: Any) -> Any:
    is_error = bool(getattr(result, "is_error", False))
    data = getattr(result, "data", None)
    if not is_error and data is not None:
        return data

    output = _text_from_content_blocks(getattr(result, "content", []))
    if is_error:
        return f"Error: {output}"

    structured_content = getattr(result, "structured_content", None)
    if structured_content is not None:
        return structured_content
    return output


@dataclass(frozen=True)
class MCPToolWrapper(Tool):
    """Expose an MCP tool through Bumblehive's Tool interface."""

    client: Any
    original_name: str
    server_name: str
    timeout: int = 30

    async def _call_once(self, arguments: dict[str, Any]) -> Any:
        return await self.client.call_tool(
            self.original_name,
            arguments,
            timeout=self.timeout,
            raise_on_error=False,
        )

    async def execute(self, **kwargs: Any) -> Any:
        retried_transient = False

        while True:
            try:
                result = await self._call_once(kwargs)
            except (asyncio.TimeoutError, TimeoutError):
                return f"Error: MCP tool '{self.name}' timed out after {self.timeout} seconds"
            except Exception as exc:
                if not _is_transient_mcp_error(exc):
                    raise
                if retried_transient:
                    return f"Error: MCP tool '{self.name}' failed after retry: {type(exc).__name__}: {exc}"
                retried_transient = True
                await asyncio.sleep(_TRANSIENT_RETRY_DELAY_SECONDS)
                continue

            return _mcp_result_payload(result)
