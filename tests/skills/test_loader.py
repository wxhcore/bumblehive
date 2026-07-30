from bumblehive.skills.loader import load_skills


def _write_skill(root, directory, frontmatter, *, newline="\n"):
    skill_dir = root / directory
    skill_dir.mkdir(parents=True)
    content = newline.join(["---", *frontmatter, "---", "", "# Body", ""])
    path = skill_dir / "SKILL.md"
    path.write_text(content, encoding="utf-8")
    return path


def test_loader_discovers_sorted_skills_and_optional_resources(tmp_path) -> None:
    beta = _write_skill(
        tmp_path,
        "beta",
        ["name: beta", "description: Uses CRLF."],
        newline="\r\n",
    )
    alpha = _write_skill(
        tmp_path,
        "alpha",
        ["name: alpha", "description: Alpha skill."],
    )
    for name in ("scripts", "references", "assets"):
        (alpha.parent / name).mkdir()

    result = load_skills(tmp_path)

    assert result.errors == []
    assert [skill.name for skill in result.skills] == ["alpha", "beta"]
    first = result.skills[0]
    assert first.path == alpha.resolve()
    assert first.scripts == (alpha.parent / "scripts").resolve()
    assert first.references == (alpha.parent / "references").resolve()
    assert first.assets == (alpha.parent / "assets").resolve()
    assert result.skills[1].path == beta.resolve()


def test_loader_reports_each_invalid_skill_without_hiding_valid_skills(tmp_path) -> None:
    valid = _write_skill(tmp_path, "valid", ["name: valid", "description: Works."])
    missing = _write_skill(tmp_path, "missing", ["name: missing"])
    resource = _write_skill(
        tmp_path,
        "resource",
        ["name: resource", "description: Invalid resource."],
    )
    (resource.parent / "scripts").write_text("not a directory", encoding="utf-8")

    result = load_skills(tmp_path)

    assert [skill.path for skill in result.skills] == [valid.resolve()]
    assert {error.path for error in result.errors} == {missing, resource}
    assert any("description" in error.message for error in result.errors)
    assert any("scripts" in error.message for error in result.errors)


def test_loader_rejects_a_name_that_does_not_match_its_directory(tmp_path) -> None:
    skill = _write_skill(
        tmp_path,
        "legacy-directory",
        ["name: audit", "description: Audit the project."],
    )

    result = load_skills(tmp_path)

    assert result.skills == []
    assert len(result.errors) == 1
    assert result.errors[0].path == skill
    assert "must match directory name" in result.errors[0].message


def test_loader_rejects_a_name_that_is_not_lowercase_hyphen_case(tmp_path) -> None:
    skill = _write_skill(
        tmp_path,
        "audit_skill",
        ["name: audit_skill", "description: Audit the project."],
    )

    result = load_skills(tmp_path)

    assert result.skills == []
    assert len(result.errors) == 1
    assert result.errors[0].path == skill
    assert "lowercase letters, digits, and hyphens" in result.errors[0].message
