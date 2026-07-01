from pathlib import Path

from ..config import get_workspace_path
from .loader import load_skills
from .models import Skill, SkillLoadResult
from .render import render_skills_summary

SkillFilesSnapshot = tuple[tuple[str, int, int], ...]
SkillsCacheKey = tuple[str, ...]
_BUILTIN_SKILLS_DIR = Path(__file__).parent / "builtin" / "skills"


class SkillsManager:
    """Facade for loading local skills and rendering prompt context."""

    def __init__(
        self,
        workspace: Path | str | None = None,
    ) -> None:
        self.workspace = get_workspace_path(workspace)
        self._cache: dict[SkillsCacheKey, tuple[SkillFilesSnapshot, SkillLoadResult]] = {}

    def list_skills(
        self,
        *,
        workspace: Path | str | None = None,
        force_reload: bool = False,
    ) -> SkillLoadResult:
        roots = self._skills_roots(workspace)
        cache_key = tuple(root.as_posix() for root in roots)
        snapshot = self._snapshot_skill_files(roots)
        cached = self._cache.get(cache_key)
        if (
            not force_reload
            and cached is not None
            and cached[0] == snapshot
        ):
            return cached[1]

        result = self._load_from_roots(roots)
        self._cache[cache_key] = (snapshot, result)
        return result

    def reload(self, *, workspace: Path | str | None = None) -> SkillLoadResult:
        return self.list_skills(workspace=workspace, force_reload=True)

    def build_skills_summary(
        self,
        skill_names: list[str] | None = None,
        *,
        workspace: Path | str | None = None,
    ) -> str:
        """Render skills for prompt context.

        ``skill_names=None`` renders all skills, ``[]`` renders none, and a
        non-empty list renders only the named skills in the given order.
        """
        result = self.list_skills(workspace=workspace)
        skills = result.skills
        if skill_names is not None:
            skills = self.get_skills(skill_names, workspace=workspace)
        return render_skills_summary(skills)

    def get_skills(
        self,
        names: list[str],
        *,
        workspace: Path | str | None = None,
    ) -> list[Skill]:
        result = self.list_skills(workspace=workspace)
        by_name = {skill.name: skill for skill in result.skills}
        return [
            by_name[name]
            for name in names
            if name in by_name
        ]

    def get_skill(
        self,
        name: str,
        *,
        workspace: Path | str | None = None,
    ) -> Skill | None:
        skills = self.get_skills([name], workspace=workspace)
        return skills[0] if skills else None

    def load_skill_content(
        self,
        name: str,
        *,
        workspace: Path | str | None = None,
    ) -> str | None:
        skill = self.get_skill(name, workspace=workspace)
        if skill is None:
            return None
        return skill.path.read_text(encoding="utf-8")

    def _skills_roots(self, workspace: Path | str | None) -> list[Path]:
        active_workspace = (
            get_workspace_path(workspace)
            if workspace is not None
            else self.workspace
        )
        return [
            _BUILTIN_SKILLS_DIR.resolve(),
            active_workspace / "skills",
        ]

    def _load_from_roots(self, roots: list[Path]) -> SkillLoadResult:
        by_name: dict[str, Skill] = {}
        errors = []
        for root in roots:
            result = load_skills(root)
            errors.extend(result.errors)
            for skill in result.skills:
                by_name[skill.name] = skill
        return SkillLoadResult(skills=list(by_name.values()), errors=errors)

    def _snapshot_skill_files(self, roots: list[Path]) -> SkillFilesSnapshot:
        snapshot: list[tuple[str, int, int]] = []
        for root in roots:
            if not root.exists():
                continue
            for skill_file in sorted(root.glob("*/SKILL.md")):
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
