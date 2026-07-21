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
