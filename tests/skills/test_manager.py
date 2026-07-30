from pathlib import Path

import pytest

from bumblehive.skills import SkillsManager


def _write_skill(root, name, description="Skill description.", body=""):
    skill_dir = root / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    content = f"---\nname: {name}\ndescription: {description}\n---\n{body}"
    (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")
    return content


def test_manager_uses_an_explicit_directory_and_exposes_selected_skills(tmp_path) -> None:
    skills_dir = tmp_path / "custom-skills"
    github_content = _write_skill(
        skills_dir,
        "github",
        "Use A & B.",
        "\n# GitHub\n\nUse gh.\n",
    )
    _write_skill(skills_dir, "audit", "Audit the project.")
    github_dir = skills_dir / "github"
    for name in ("scripts", "references", "assets"):
        (github_dir / name).mkdir()
    manager = SkillsManager(skills_dir)

    assert manager.skills_dir == skills_dir.resolve()
    assert [skill.name for skill in manager.get_skills(["github", "missing", "audit"])] == [
        "github",
        "audit",
    ]
    assert manager.get_skill("github").name == "github"
    assert manager.get_skill("missing") is None
    assert manager.load_skill_content("github") == github_content
    assert manager.load_skill_content("missing") is None

    rendered = manager.build_skills_summary(["github"])
    assert "<name>github</name>" in rendered
    assert "<description>Use A &amp; B.</description>" in rendered
    assert "<name>audit</name>" not in rendered
    for name in ("scripts", "references", "assets"):
        assert f"<{name}>{(github_dir / name).resolve().as_posix()}</{name}>" in rendered
    assert manager.build_skills_summary([]) == ""


def test_manager_cache_tracks_skill_and_resource_changes(tmp_path) -> None:
    skills_dir = tmp_path / "skills"
    _write_skill(skills_dir, "audit", "Old description.")
    manager = SkillsManager(skills_dir)

    first = manager.list_skills()
    assert manager.list_skills() is first

    _write_skill(skills_dir, "audit", "New description.")
    changed = manager.list_skills()
    assert changed is not first
    assert changed.skills[0].description == "New description."

    (skills_dir / "audit" / "scripts").mkdir()
    resources_changed = manager.list_skills()
    assert resources_changed is not changed
    assert resources_changed.skills[0].scripts == (skills_dir / "audit" / "scripts").resolve()

    _write_skill(skills_dir, "new", "New skill.")
    added = manager.list_skills()
    assert [skill.name for skill in added.skills] == ["audit", "new"]
    assert manager.reload() is not added


def test_manager_installs_multiple_skills_and_reloads(tmp_path) -> None:
    sources = tmp_path / "sources"
    _write_skill(sources, "github", "Use GitHub.")
    _write_skill(sources, "audit", "Audit the project.")
    (sources / "github" / "scripts").mkdir()
    manager = SkillsManager(tmp_path / "skills")

    result = manager.install_skills([
        sources / "github",
        sources / "audit",
    ])

    assert [skill.name for skill in result.skills] == ["audit", "github"]
    assert (manager.skills_dir / "github" / "SKILL.md").is_file()
    assert (manager.skills_dir / "github" / "scripts").is_dir()
    assert (manager.skills_dir / "audit" / "SKILL.md").is_file()
    assert list(manager.skills_dir.glob(".install-*")) == []


def test_manager_rejects_conflicts_without_installing_part_of_batch(tmp_path) -> None:
    skills_dir = tmp_path / "skills"
    _write_skill(skills_dir, "audit", "Installed.")
    sources = tmp_path / "sources"
    _write_skill(sources, "audit", "Replacement.")
    _write_skill(sources, "new", "New skill.")
    manager = SkillsManager(skills_dir)

    with pytest.raises(FileExistsError, match="audit"):
        manager.install_skills([
            sources / "audit",
            sources / "new",
        ])

    assert manager.get_skill("audit").description == "Installed."
    assert manager.get_skill("new") is None


def test_manager_replaces_the_whole_skill_directory(tmp_path) -> None:
    skills_dir = tmp_path / "skills"
    _write_skill(skills_dir, "audit", "Old description.")
    (skills_dir / "audit" / "scripts").mkdir()
    (skills_dir / "audit" / "scripts" / "old.py").write_text(
        "print('old')",
        encoding="utf-8",
    )
    sources = tmp_path / "sources"
    _write_skill(sources, "audit", "New description.")
    (sources / "audit" / "assets").mkdir()
    manager = SkillsManager(skills_dir)

    result = manager.install_skills(
        [sources / "audit"],
        replace=True,
    )

    assert [skill.name for skill in result.skills] == ["audit"]
    assert result.skills[0].description == "New description."
    assert not (skills_dir / "audit" / "scripts").exists()
    assert (skills_dir / "audit" / "assets").is_dir()


def test_manager_rolls_back_the_batch_when_a_replacement_fails(
    tmp_path,
    monkeypatch,
) -> None:
    skills_dir = tmp_path / "skills"
    _write_skill(skills_dir, "alpha", "Old alpha.")
    _write_skill(skills_dir, "beta", "Old beta.")
    sources = tmp_path / "sources"
    _write_skill(sources, "alpha", "New alpha.")
    _write_skill(sources, "beta", "New beta.")
    manager = SkillsManager(skills_dir)
    original_replace = Path.replace

    def replace_with_failure(path, target):
        if path.name == "beta" and target.name == "beta":
            raise OSError("simulated replacement failure")
        return original_replace(path, target)

    monkeypatch.setattr(Path, "replace", replace_with_failure)

    with pytest.raises(OSError, match="simulated replacement failure"):
        manager.install_skills(
            [sources / "alpha", sources / "beta"],
            replace=True,
        )

    assert manager.get_skill("alpha").description == "Old alpha."
    assert manager.get_skill("beta").description == "Old beta."


def test_manager_rejects_an_invalid_batch_before_installing(tmp_path) -> None:
    sources = tmp_path / "sources"
    _write_skill(sources, "valid", "Valid skill.")
    invalid_dir = sources / "invalid"
    invalid_dir.mkdir()
    (invalid_dir / "SKILL.md").write_text(
        "---\nname: invalid\n---\n",
        encoding="utf-8",
    )
    manager = SkillsManager(tmp_path / "skills")

    with pytest.raises(ValueError, match="Invalid skill package"):
        manager.install_skills([
            sources / "valid",
            invalid_dir,
        ])

    assert manager.list_skills().skills == []


def test_manager_rejects_duplicate_skill_directories(tmp_path) -> None:
    first_source = tmp_path / "first-source"
    second_source = tmp_path / "second-source"
    _write_skill(first_source, "audit", "First skill.")
    _write_skill(second_source, "audit", "Second skill.")
    manager = SkillsManager(tmp_path / "skills")

    with pytest.raises(ValueError, match="Duplicate skill directory: audit"):
        manager.install_skills([
            first_source / "audit",
            second_source / "audit",
        ])

    assert manager.list_skills().skills == []


def test_manager_removes_a_skill_and_is_idempotent(tmp_path) -> None:
    skills_dir = tmp_path / "skills"
    _write_skill(skills_dir, "audit", "Installed skill.")
    manager = SkillsManager(skills_dir)

    removed = manager.remove_skill("audit")
    removed_again = manager.remove_skill("audit")

    assert removed.skills == []
    assert removed_again.skills == []
    assert not (skills_dir / "audit").exists()


def test_manager_rejects_a_single_path_as_the_sources_sequence(tmp_path) -> None:
    source = tmp_path / "audit"
    source.mkdir()
    (source / "SKILL.md").write_text(
        "---\nname: audit\ndescription: Audit the project.\n---\n",
        encoding="utf-8",
    )
    manager = SkillsManager(tmp_path / "skills")

    with pytest.raises(TypeError, match="sequence of skill directories"):
        manager.install_skills(source)
