import shutil
from collections.abc import Sequence
from pathlib import Path
from tempfile import TemporaryDirectory

from ..paths import get_skills_path
from .loader import load_skills
from .models import Skill, SkillLoadResult
from .render import render_skills_summary

SkillFilesSnapshot = tuple[tuple[str, int, int], ...]


class SkillsManager:
    """Load user-installed skills and render their prompt context."""

    def __init__(self, skills_dir: str | Path | None = None) -> None:
        self.skills_dir = get_skills_path(skills_dir)
        self._cache: tuple[SkillFilesSnapshot, SkillLoadResult] | None = None

    def set_skills_dir(self, skills_dir: str | Path | None) -> None:
        """Switch the managed skills directory and clear cached results."""
        resolved = get_skills_path(skills_dir)
        if resolved == self.skills_dir:
            return

        self.skills_dir = resolved
        self._cache = None

    def list_skills(self, *, force_reload: bool = False) -> SkillLoadResult:
        snapshot = self._snapshot_skill_files()
        cached = self._cache
        if (
            not force_reload
            and cached is not None
            and cached[0] == snapshot
        ):
            return cached[1]

        result = load_skills(self.skills_dir)
        self._cache = (snapshot, result)
        return result

    def reload(self) -> SkillLoadResult:
        return self.list_skills(force_reload=True)

    def install_skills(
        self,
        sources: Sequence[str | Path],
        *,
        replace: bool = False,
    ) -> SkillLoadResult:
        """Install skill package directories and reload the catalog.

        Every source must be a directory containing ``SKILL.md``. Packages are
        copied and validated in a temporary staging directory before any
        installed skill is changed.
        """
        if isinstance(sources, (str, Path)):
            raise TypeError("sources must be a sequence of skill directories")

        source_paths = [self._resolve_skill_source(source) for source in sources]
        if not source_paths:
            return self.reload()

        self.skills_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        with TemporaryDirectory(prefix=".install-", dir=self.skills_dir) as temp:
            temporary_root = Path(temp)
            staging_root = temporary_root / "packages"
            staging_root.mkdir()
            for source in source_paths:
                staged = staging_root / source.name
                if staged.exists():
                    raise ValueError(
                        f"Duplicate skill directory: {source.name}"
                    )
                shutil.copytree(source, staged)

            staged_result = load_skills(staging_root)
            if staged_result.errors or len(staged_result.skills) != len(source_paths):
                details = "; ".join(
                    f"{error.path.parent.name}: {error.message}"
                    for error in staged_result.errors
                )
                suffix = f": {details}" if details else ""
                raise ValueError(f"Invalid skill package{suffix}")

            staged_skills = {
                skill.name: skill.path.parent
                for skill in staged_result.skills
            }

            targets = {
                name: self.skills_dir / name
                for name in staged_skills
            }
            conflicts = [
                name
                for name, target in targets.items()
                if target.exists() or target.is_symlink()
            ]
            if conflicts and not replace:
                raise FileExistsError(
                    f"Skills already installed: {', '.join(sorted(conflicts))}"
                )

            self._commit_staged_skills(
                staged_skills,
                targets,
                temporary_root / "backups",
            )

        return self.reload()

    def remove_skill(self, name: str) -> SkillLoadResult:
        """Remove an installed skill by its declared name and reload."""
        skill = self.get_skill(name)
        if skill is None:
            return self.reload()

        target = skill.path.parent.resolve()
        if target.parent != self.skills_dir:
            raise ValueError(f"Skill is outside the managed directory: {name}")

        shutil.rmtree(target)
        return self.reload()

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
        return [by_name[name] for name in names if name in by_name]

    def get_skill(self, name: str) -> Skill | None:
        skills = self.get_skills([name])
        return skills[0] if skills else None

    def load_skill_content(self, name: str) -> str | None:
        skill = self.get_skill(name)
        if skill is None:
            return None
        return skill.path.read_text(encoding="utf-8")

    def _resolve_skill_source(self, source: str | Path) -> Path:
        path = Path(source).expanduser()
        if path.is_symlink():
            raise ValueError(f"Skill source cannot be a symbolic link: {path}")
        try:
            resolved = path.resolve(strict=True)
        except FileNotFoundError as exc:
            raise FileNotFoundError(f"Skill source does not exist: {path}") from exc
        if not resolved.is_dir():
            raise ValueError(f"Skill source must be a directory: {path}")
        if not (resolved / "SKILL.md").is_file():
            raise ValueError(f"Skill source is missing SKILL.md: {path}")
        if any(child.is_symlink() for child in resolved.rglob("*")):
            raise ValueError(f"Skill source cannot contain symbolic links: {path}")
        return resolved

    def _commit_staged_skills(
        self,
        staged_skills: dict[str, Path],
        targets: dict[str, Path],
        backups_root: Path,
    ) -> None:
        backups_root.mkdir()
        committed: list[tuple[Path, Path | None]] = []
        try:
            for name in sorted(staged_skills):
                staged = staged_skills[name]
                target = targets[name]
                backup: Path | None = None
                if target.exists() or target.is_symlink():
                    backup = backups_root / name
                    target.replace(backup)
                try:
                    staged.replace(target)
                except BaseException:
                    if backup is not None:
                        backup.replace(target)
                    raise
                committed.append((target, backup))
        except BaseException:
            for target, backup in reversed(committed):
                shutil.rmtree(target)
                if backup is not None:
                    backup.replace(target)
            raise

    def _snapshot_skill_files(self) -> SkillFilesSnapshot:
        snapshot: list[tuple[str, int, int]] = []
        for skill_file in sorted(self.skills_dir.glob("*/SKILL.md")):
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
        snapshot.append((path.resolve().as_posix(), stat.st_mtime_ns, stat.st_size))
