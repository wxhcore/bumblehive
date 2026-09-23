"""App approval policy and decisions waiting on the chat connection."""

import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from bumblehive.protocols.tool_approval import ToolApprovalDecision, ToolApprovalRequest

SendFrame = Callable[[dict[str, Any]], Awaitable[None]]
_AUTO_APPROVE = {
    "read_file",
    "list_dir",
    "find_files",
    "grep",
    "list_exec_sessions",
    "sub_agent",
}


def resolve_path(path: str | Path, workspace: Path) -> Path:
    raw = Path(path).expanduser()
    return raw.resolve() if raw.is_absolute() else (workspace / raw).resolve()


def approval_details(request: ToolApprovalRequest) -> dict[str, Any] | None:
    """Return display facts when a call needs confirmation, otherwise allow it."""
    name, arguments, workspace = request.name, request.arguments, request.workspace
    if name in _AUTO_APPROVE:
        return None
    if name == "apply_patch" and arguments.get("dry_run"):
        return None
    if name in {"write_file", "edit_file", "apply_patch"}:
        paths = (
            [
                resolve_path(edit["path"].strip(), workspace)
                for edit in arguments["edits"]
            ]
            if name == "apply_patch"
            else [resolve_path(arguments["path"], workspace)]
        )
        paths = list(dict.fromkeys(paths))
        outside = [path for path in paths if not path.is_relative_to(workspace)]
        if not outside:
            return None
        return {
            "reason": name,
            "paths": [str(path) for path in paths],
            "outside_paths": [str(path) for path in outside],
        }
    if name == "exec":
        return {
            "reason": "exec",
            "command": arguments["command"],
            "working_dir": str(
                resolve_path(arguments.get("working_dir") or workspace, workspace)
            ),
        }
    if name == "write_stdin":
        # The tool itself checks that the exec process belongs to this session.
        if not arguments.get("chars") and not arguments.get("close_stdin"):
            return None
        return {"reason": "write_stdin"}
    return {"reason": "tool"}


class ToolApprovals:
    def __init__(
        self,
        session_id: str,
        send: SendFrame,
        mode: Literal["request", "full_access"] = "request",
    ) -> None:
        self.mode = mode
        self.session_id = session_id
        self.send = send
        self.pending: dict[str, tuple[ToolApprovalRequest, asyncio.Future[bool]]] = {}

    async def __call__(self, request: ToolApprovalRequest) -> ToolApprovalDecision:
        if self.mode == "full_access":
            return ToolApprovalDecision.approve()
        details = approval_details(request)
        if details is None:
            return ToolApprovalDecision.approve()

        approval_id = uuid4().hex
        future: asyncio.Future[bool] = asyncio.get_running_loop().create_future()
        self.pending[approval_id] = (request, future)
        try:
            await self.send(
                {
                    "type": "approval_request",
                    "approval_id": approval_id,
                    "session_id": self.session_id,
                    "call_id": request.call_id,
                    "name": request.name,
                    "workspace": str(request.workspace),
                    "arguments": dict(request.arguments),
                    **details,
                }
            )
            approved = await future
            return (
                ToolApprovalDecision.approve()
                if approved
                else ToolApprovalDecision.reject("The user rejected this tool call.")
            )
        finally:
            self.pending.pop(approval_id, None)

    async def decide(self, approval_id: str, approved: bool) -> None:
        pending = self.pending.get(approval_id)
        if pending is None:
            return
        request, future = pending
        if future.done():
            return
        await self.send(
            {
                "type": "approval_resolved",
                "approval_id": approval_id,
                "session_id": self.session_id,
                "call_id": request.call_id,
                "approved": approved,
            }
        )
        if not future.done():
            future.set_result(approved)

    def clear(self) -> None:
        for _, future in self.pending.values():
            future.cancel()
        self.pending.clear()
