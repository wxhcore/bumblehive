from html import escape

from .models import Skill


SKILLS_INSTRUCTIONS = (
    "These skills extend your capabilities. To use a skill, call read_file "
    "on its path, then follow the SKILL.md instructions."
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
                "  </skill>",
            ]
        )
    lines.append("</skills>")
    return "\n".join(lines)
