from pathlib import Path
from typing import Any

import yaml

from .models import Skill, SkillError, SkillLoadResult


FRONTMATTER_DELIMITER = "---"


def load_skills(
    workspace: Path | None = None,
    *,
    skills_path: Path | None = None,
) -> SkillLoadResult:
    """Load skills from <skills_path>/*/SKILL.md or <workspace>/skills/*/SKILL.md."""
    skills_root = resolve_skills_root(workspace, skills_path=skills_path)
    if not skills_root.exists():
        return SkillLoadResult(skills=[], errors=[])

    skills: list[Skill] = []
    errors: list[SkillError] = []
    for skill_file in sorted(skills_root.glob("*/SKILL.md")):
        try:
            skills.append(_parse_skill_file(skill_file))
        except Exception as exc:
            errors.append(SkillError(path=skill_file, message=str(exc)))

    return SkillLoadResult(skills=skills, errors=errors)


def resolve_skills_root(
    workspace: Path | None = None,
    *,
    skills_path: Path | None = None,
) -> Path:
    """Resolve the directory that contains skill folders."""
    if skills_path is not None:
        return Path(skills_path).expanduser().resolve()

    root = Path.cwd() if workspace is None else Path(workspace)
    return root.expanduser().resolve() / "skills"


def _parse_skill_file(path: Path) -> Skill:
    content = path.read_text(encoding="utf-8")
    frontmatter = _extract_frontmatter(content)
    metadata = yaml.safe_load(frontmatter) or {}
    if not isinstance(metadata, dict):
        raise ValueError("frontmatter must be a YAML object")

    name = _required_string(metadata, "name")
    description = _required_string(metadata, "description")
    return Skill(name=name, description=description, path=path.resolve())


def _extract_frontmatter(content: str) -> str:
    lines = content.splitlines()
    if not lines or lines[0].strip() != FRONTMATTER_DELIMITER:
        raise ValueError("missing YAML frontmatter")

    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == FRONTMATTER_DELIMITER:
            return "\n".join(lines[1:index])

    raise ValueError("unterminated YAML frontmatter")


def _required_string(metadata: dict[str, Any], key: str) -> str:
    value = metadata.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"missing required frontmatter field: {key}")
    return value.strip()
