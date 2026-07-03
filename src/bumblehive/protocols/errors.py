from dataclasses import dataclass


@dataclass(frozen=True)
class AgentError:
    """Structured error shared by Bumblehive subsystems."""

    code: str
    message: str
    recoverable: bool = False
