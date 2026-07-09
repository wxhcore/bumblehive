from dataclasses import dataclass
from typing import Any

from .events import make_event, new_run_id
from .hooks import AgentHook, HookInput, normalize_hooks


@dataclass(frozen=True, slots=True)
class EventEmitter:
    """Emit lifecycle events for one observed run."""

    hook: AgentHook
    run_id: str
    session_id: str | None = None
    iteration: int | None = None

    @classmethod
    def from_hooks(
        cls,
        hooks: HookInput = None,
        *,
        run_id: str | None = None,
        session_id: str | None = None,
    ) -> "EventEmitter":
        """Create an emitter from user-provided hooks and an optional run id."""

        return cls(
            hook=normalize_hooks(hooks),
            run_id=run_id or new_run_id(),
            session_id=session_id,
        )

    @classmethod
    def noop(
        cls,
        *,
        run_id: str | None = None,
        session_id: str | None = None,
    ) -> "EventEmitter":
        """Create an emitter that drops events but still carries a run id."""

        return cls.from_hooks(None, run_id=run_id, session_id=session_id)

    def with_iteration(self, iteration: int | None) -> "EventEmitter":
        """Return an emitter that attaches a default iteration to events."""

        return EventEmitter(
            hook=self.hook,
            run_id=self.run_id,
            session_id=self.session_id,
            iteration=iteration,
        )

    async def emit(
        self,
        kind: str,
        *,
        iteration: int | None = None,
        **payload: Any,
    ) -> None:
        """Build and deliver one event to the configured hook."""

        await self.hook.on_event(
            make_event(
                kind,
                run_id=self.run_id,
                session_id=self.session_id,
                iteration=self.iteration if iteration is None else iteration,
                **payload,
            )
        )
