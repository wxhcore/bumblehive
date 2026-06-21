from pathlib import Path
from typing import Any

import yaml

from .models import Skill, SkillError, SkillLoadResult


FRONTMATTER_DELIMITER = "---"


def load_skills(skills_root: Path) -> SkillLoadResult:
    """Load skills from <skills_root>/*/SKILL.md."""
    skills_root = Path(skills_root).expanduser().resolve()
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


def resolve_skills_root(workspace: Path) -> Path:
    """Resolve the workspace-local directory that contains skill folders."""
    return Path(workspace).expanduser().resolve() / "skills"


def _parse_skill_file(path: Path) -> Skill:
    content = path.read_text(encoding="utf-8")
    frontmatter = _extract_frontmatter(content)
    metadata = yaml.safe_load(frontmatter) or {}
    if not isinstance(metadata, dict):
        raise ValueError("frontmatter must be a YAML object")

    name = _required_string(metadata, "name")
    description = _required_string(metadata, "description")
    root = path.parent.resolve()
    return Skill(
        name=name,
        description=description,
        path=path.resolve(),
        scripts=_optional_resource_dir(root, "scripts"),
        references=_optional_resource_dir(root, "references"),
        assets=_optional_resource_dir(root, "assets"),
    )


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


def _optional_resource_dir(root: Path, name: str) -> Path | None:
    path = root / name
    if not path.exists():
        return None
    if not path.is_dir():
        raise ValueError(f"optional skill resource must be a directory: {name}")
    return path.resolve()
