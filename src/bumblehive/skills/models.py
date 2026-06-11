from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Skill:
    """Model-visible summary for a local skill."""

    name: str
    description: str
    path: Path


@dataclass(frozen=True)
class SkillError:
    """Non-fatal error found while loading one skill file."""

    path: Path
    message: str


@dataclass(frozen=True)
class SkillLoadResult:
    """Loaded skills plus non-fatal parse/load errors."""

    skills: list[Skill]
    errors: list[SkillError]
