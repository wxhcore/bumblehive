from html import escape
from pathlib import Path

from .models import Skill


SKILLS_INSTRUCTIONS = (
    "These skills extend your capabilities. To use a skill, call read_file "
    "on its path, then follow the SKILL.md instructions. Resolve relative "
    "paths such as scripts/foo.py or references/bar.md from the directory "
    "containing SKILL.md. Read references only when needed, prefer bundled "
    "scripts for repeatable workflows, and reuse assets or templates instead "
    "of recreating them."
)


def render_skills_summary(skills: list[Skill]) -> str:
    """Render a system-prompt XML summary of available skills."""
    if not skills:
        return ""

    lines = [
        "<skills>",
        "  <instructions>",
        f"    {escape(SKILLS_INSTRUCTIONS)}",
        "  </instructions>",
    ]
    for skill in skills:
        lines.extend(
            [
                "  <skill>",
                f"    <name>{escape(skill.name)}</name>",
                f"    <description>{escape(skill.description)}</description>",
                f"    <path>{escape(skill.path.as_posix())}</path>",
            ]
        )
        _append_optional_path(lines, "scripts", skill.scripts)
        _append_optional_path(lines, "references", skill.references)
        _append_optional_path(lines, "assets", skill.assets)
        lines.append("  </skill>")
    lines.append("</skills>")
    return "\n".join(lines)


def _append_optional_path(lines: list[str], tag: str, path: Path | None) -> None:
    if path is not None:
        lines.append(f"    <{tag}>{escape(path.as_posix())}</{tag}>")
