import time
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class AgentEvent:
    """One structured lifecycle event emitted by an agent run."""

    kind: str
    run_id: str
    payload: dict[str, Any] = field(default_factory=dict)
    iteration: int | None = None
    timestamp: float = field(default_factory=time.time)


def new_run_id() -> str:
    """Return an opaque identifier shared by all events from one run."""

    return uuid.uuid4().hex


def make_event(
    kind: str,
    *,
    run_id: str,
    iteration: int | None = None,
    **payload: Any,
) -> AgentEvent:
    """Build an event, omitting payload entries whose value is None."""

    return AgentEvent(
        kind=kind,
        run_id=run_id,
        iteration=iteration,
        payload={key: value for key, value in payload.items() if value is not None},
    )


TURN_STARTED = "turn.started"
TURN_CONTEXT_BUILT = "turn.context_built"
TURN_FINISHED = "turn.finished"
TURN_ERROR = "turn.error"

RUN_STARTED = "run.started"
RUN_FINISHED = "run.finished"
RUN_ERROR = "run.error"

ITERATION_STARTED = "iteration.started"
ITERATION_FINISHED = "iteration.finished"

MODEL_REQUEST_STARTED = "model.request.started"
MODEL_RESPONSE_FINISHED = "model.response.finished"

TOOL_CALLS_STARTED = "tool.calls.started"
TOOL_CALL_STARTED = "tool.call.started"
TOOL_CALL_FINISHED = "tool.call.finished"
TOOL_CALLS_FINISHED = "tool.calls.finished"

FINAL_RESULT = "final_result"
