from pathlib import Path

from .loader import load_skills, resolve_skills_root
from .models import Skill, SkillLoadResult
from .render import render_skills_summary

SkillFilesSnapshot = tuple[tuple[str, int, int], ...]


class SkillsManager:
    """Facade for loading local skills and rendering prompt context."""

    def __init__(
        self,
        workspace: Path | None = None,
        *,
        skills_path: Path | None = None,
    ) -> None:
        root = Path.cwd() if workspace is None else Path(workspace)
        self.workspace = root.expanduser().resolve()
        self.skills_root = resolve_skills_root(self.workspace, skills_path=skills_path)
        self._cached_result: SkillLoadResult | None = None
        self._cached_snapshot: SkillFilesSnapshot | None = None

    def list_skills(self, *, force_reload: bool = False) -> SkillLoadResult:
        snapshot = self._snapshot_skill_files()
        if (
            not force_reload
            and self._cached_result is not None
            and self._cached_snapshot == snapshot
        ):
            return self._cached_result

        result = load_skills(skills_path=self.skills_root)
        self._cached_result = result
        self._cached_snapshot = snapshot
        return result

    def reload(self) -> SkillLoadResult:
        return self.list_skills(force_reload=True)

    def build_skills_summary(self, skill_names: list[str] | None = None) -> str:
        """Render skills for prompt context.

        ``skill_names=None`` renders all skills, ``[]`` renders none, and a
        non-empty list renders only the named skills in the given order.
        """
        result = self.list_skills()
        skills = result.skills
        if skill_names is not None:
            skills = self.get_skills(skill_names)
        return render_skills_summary(skills)

    def get_skills(self, names: list[str]) -> list[Skill]:
        result = self.list_skills()
        by_name = {skill.name: skill for skill in result.skills}
        return [
            by_name[name]
            for name in names
            if name in by_name
        ]

    def get_skill(self, name: str) -> Skill | None:
        skills = self.get_skills([name])
        return skills[0] if skills else None

    def load_skill_content(self, name: str) -> str | None:
        skill = self.get_skill(name)
        if skill is None:
            return None
        return skill.path.read_text(encoding="utf-8")

    def _snapshot_skill_files(self) -> SkillFilesSnapshot:
        if not self.skills_root.exists():
            return ()

        snapshot: list[tuple[str, int, int]] = []
        for skill_file in sorted(self.skills_root.glob("*/SKILL.md")):
            self._append_snapshot_entry(snapshot, skill_file)
            skill_dir = skill_file.parent
            for resource_name in ("scripts", "references", "assets"):
                resource_path = skill_dir / resource_name
                if resource_path.exists():
                    self._append_snapshot_entry(snapshot, resource_path)
        return tuple(snapshot)

    def _append_snapshot_entry(
        self,
        snapshot: list[tuple[str, int, int]],
        path: Path,
    ) -> None:
        try:
            stat = path.stat()
        except OSError:
            return
        snapshot.append((path.resolve().as_posix(), stat.st_mtime_ns, stat.st_mode))
