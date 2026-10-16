"""Per-run input queue, shared only within the owning asyncio event loop."""

from ..protocols import Message, UserMessage, normalize_user_message


class _RunControl:
    def __init__(self) -> None:
        self._pending: list[Message] = []
        self._closed = False

    def steer(self, message: UserMessage) -> None:
        if self._closed:
            raise RuntimeError("Run input is closed")
        self._pending.extend(normalize_user_message(message))

    def _drain_all(self) -> list[Message]:
        pending, self._pending = self._pending, []
        return pending

    def _close_if_empty(self) -> bool:
        if self._pending:
            return False
        self._closed = True
        return True

    def _close(self) -> None:
        self._closed = True

    def take_pending(self) -> list[Message]:
        if not self._closed:
            raise RuntimeError(
                "Run input must be closed before taking pending messages"
            )
        return self._drain_all()
