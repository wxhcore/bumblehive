import pytest

from bumblehive import paths


@pytest.mark.parametrize(
    ("helper", "default_name", "child"),
    [
        (paths.get_workspace_path, "DEFAULT_WORKSPACE", "workspace"),
    ],
)
def test_path_helpers_create_default_and_explicit_directories(
    tmp_path,
    monkeypatch,
    helper,
    default_name,
    child,
) -> None:
    default = tmp_path / f"default-{child}"
    explicit = tmp_path / f"explicit-{child}"
    monkeypatch.setattr(paths, default_name, default)

    assert helper() == default.resolve()
    assert helper(explicit) == explicit.resolve()
    assert default.is_dir()
    assert explicit.is_dir()


@pytest.mark.parametrize(
    ("helper", "default_name", "child"),
    [
        (paths.get_skills_path, "DEFAULT_SKILLS", "skills"),
        (paths.get_sessions_path, "DEFAULT_SESSIONS", "sessions"),
    ],
)
def test_storage_path_helpers_resolve_without_creating_directories(
    tmp_path,
    monkeypatch,
    helper,
    default_name,
    child,
) -> None:
    default = tmp_path / f"default-{child}"
    explicit = tmp_path / f"explicit-{child}"
    monkeypatch.setattr(paths, default_name, default)

    assert helper() == default.resolve()
    assert helper(explicit) == explicit.resolve()
    assert not default.exists()
    assert not explicit.exists()
