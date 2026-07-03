from dataclasses import dataclass, field

from .events import AgentEvent


@dataclass(slots=True)
class EventRecorder:
    """Small hook useful for tests, diagnostics, and examples."""

    events: list[AgentEvent] = field(default_factory=list)

    async def on_event(self, event: AgentEvent) -> None:
        self.events.append(event)

    def by_kind(self, kind: str) -> list[AgentEvent]:
        return [event for event in self.events if event.kind == kind]
