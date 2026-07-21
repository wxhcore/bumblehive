import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


@pytest.fixture(autouse=True)
def isolated_bumblehive_directories(tmp_path, monkeypatch) -> None:
    """Keep every test independent from the user's Bumblehive data."""
    import bumblehive.paths as paths

    monkeypatch.setattr(paths, "DEFAULT_SKILLS", tmp_path / "skills")
    monkeypatch.setattr(paths, "DEFAULT_SESSIONS", tmp_path / "sessions")
    monkeypatch.setattr(paths, "DEFAULT_WORKSPACE", tmp_path / "bumblehive-workspace")
