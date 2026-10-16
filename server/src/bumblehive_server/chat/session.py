"""Session-owned runs and pending input, independent of WebSocket connections."""

import asyncio
from dataclasses import dataclass
from time import time
from typing import Any

from bumblehive import AgentRunStream

from ..schemas import ChatRequest
from .approval import ToolApprovals
from .streaming import RuntimeLease, stream_turn


class InputError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass
class PendingMessage:
    request: ChatRequest
    order: int
    steer_requested: bool = False


class SessionController:
    def __init__(self, lease: RuntimeLease, session_id: str) -> None:
        self._lease = lease
        self.session_id = session_id
        self.active_task: asyncio.Task[None] | None = None
        self.active_stream: AgentRunStream | None = None
        self.active_request: ChatRequest | None = None
        self.pending: list[PendingMessage] = []
        self._steered: list[PendingMessage] = []
        self._next_input_order = 0
        self.approvals: ToolApprovals | None = None
        self._subscribers: set[asyncio.Queue] = set()
        self._lock = asyncio.Lock()
        self._closing = False
        self._stopping = False
        self._started_at: float | None = None

    @staticmethod
    def _message(request: ChatRequest) -> dict[str, str]:
        return {"message_id": request.message_id, "content": request.content}

    def subscribe(self) -> tuple[asyncio.Queue, dict[str, Any]]:
        queue: asyncio.Queue = asyncio.Queue()
        self._subscribers.add(queue)
        return queue, {
            "type": "ready",
            "session_id": self.session_id,
            "running": self.active_task is not None,
            "active_message_id": self.active_request.message_id
            if self.active_request
            else None,
            "active_message": self._message(self.active_request)
            if self.active_request
            else None,
            "started_at": self._started_at,
            "pending": [self._message(item.request) for item in self.pending],
            "approvals": self.approvals.snapshot() if self.approvals else [],
        }

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        self._subscribers.discard(queue)

    async def publish(self, frame: dict[str, Any]) -> None:
        for queue in self._subscribers:
            queue.put_nowait(frame)

    async def _status(
        self, request: ChatRequest, status: str, *, position: int | None = None
    ) -> None:
        await self.publish(
            {
                "type": "message_status",
                "session_id": self.session_id,
                **self._message(request),
                "status": status,
                **({"position": position} if position is not None else {}),
            }
        )

    def _find(self, message_id: str) -> PendingMessage:
        if self.active_request and self.active_request.message_id == message_id:
            raise InputError(
                "message_not_pending", "message is already being dispatched"
            )
        for item in self.pending:
            if item.request.message_id == message_id:
                return item
        raise InputError("message_not_pending", "message is no longer pending")

    async def submit(self, request: ChatRequest, *, steer: bool = False) -> None:
        async with self._lock:
            if self._closing:
                raise InputError("session_closed", "session is closed")
            if any(
                item.request.message_id == request.message_id for item in self.pending
            ) or (
                self.active_request
                and self.active_request.message_id == request.message_id
            ):
                raise InputError(
                    "duplicate_message", "message has already been submitted"
                )
            was_empty = not self.pending
            item = PendingMessage(request, self._next_input_order)
            self._next_input_order += 1
            self.pending.append(item)
            await self._status(request, "queued")
            if steer and not self._stopping:
                await self._steer(item)
            elif self.active_task is None and was_empty and not self._stopping:
                self._start(item)

    async def steer(self, message_id: str) -> None:
        async with self._lock:
            if self._closing or self._stopping:
                raise InputError("run_stopping", "wait for the run to stop")
            await self._steer(self._find(message_id))

    async def _steer(self, item: PendingMessage) -> None:
        if self.active_task is None:
            self._start(item)
        elif self.active_stream is None:
            item.steer_requested = True
        else:
            try:
                self.active_stream.steer(item.request.content)
            except RuntimeError:
                return  # Keep its original position for follow-up after closure.
            self.pending.remove(item)
            self._steered.append(item)
            await self._status(item.request, "steered")

    async def _restore_unconsumed(self) -> None:
        if self.active_stream is not None and self._steered:
            count = len(self.active_stream.take_pending())
            # The SDK drains the whole input queue before each model request;
            # unconsumed inputs are a suffix of the steering dispatch order.
            restored = self._steered[-count:] if count else []
            self.pending.extend(restored)
            self.pending.sort(key=lambda item: item.order)
            for item in sorted(restored, key=lambda item: item.order):
                await self._status(
                    item.request, "queued", position=self.pending.index(item)
                )
        for item in self.pending:
            item.steer_requested = False
        self._steered.clear()

    async def remove_pending(self, message_id: str) -> None:
        async with self._lock:
            item = self._find(message_id)
            self.pending.remove(item)
            await self._status(item.request, "removed")

    def _start(self, item: PendingMessage) -> None:
        self.active_request = item.request
        self._started_at = time()
        self.approvals = ToolApprovals(
            self.session_id, self.publish, item.request.approval_mode
        )
        self.active_task = asyncio.create_task(self._execute(item, self.approvals))

    async def _execute(self, item: PendingMessage, approvals: ToolApprovals) -> None:
        successful = False
        terminal: dict[str, Any] | None = None

        async def ready(stream: AgentRunStream) -> None:
            async with self._lock:
                self.active_stream = stream
                self.pending.remove(item)
                await self._status(item.request, "started")
                for pending in list(self.pending):
                    if pending.steer_requested:
                        await self._steer(pending)

        try:
            result = await stream_turn(
                self.publish,
                self._lease,
                self.session_id,
                item.request,
                approvals,
                on_stream_ready=ready,
            )
            successful = result.error is None
        except asyncio.CancelledError:
            terminal = {"type": "cancelled", "session_id": self.session_id}
        except Exception as exc:
            terminal = {
                "type": "error",
                "session_id": self.session_id,
                "code": "runtime_error",
                "message": str(exc),
            }
        finally:
            approvals.clear()
            async with self._lock:
                if not self._closing:
                    await self._restore_unconsumed()
                else:
                    self._steered.clear()
                self.active_task = None
                self.active_stream = None
                self.active_request = None
                self.approvals = None
                self._started_at = None
                if terminal is not None:
                    await self.publish(terminal)
                if (
                    successful
                    and self.pending
                    and not self._closing
                    and not self._stopping
                ):
                    self._start(self.pending[0])

    async def decide_approval(self, approval_id: str, approved: bool) -> None:
        approvals = self.approvals
        if approvals is not None:
            await approvals.decide(approval_id, approved)

    async def cancel(self) -> None:
        async with self._lock:
            task = self.active_task
            if task is None:
                return
            self._stopping = True
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        async with self._lock:
            # Also covers cancellation before _execute first starts.
            if self.active_task is task:
                await self._restore_unconsumed()
                if self.approvals:
                    self.approvals.clear()
                self.active_task = self.active_stream = self.active_request = None
                self.approvals = None
                self._started_at = None
                await self.publish({"type": "cancelled", "session_id": self.session_id})
            self._stopping = False

    async def close(self) -> None:
        self._closing = True
        await self.cancel()
        self.pending.clear()
        self._subscribers.clear()
