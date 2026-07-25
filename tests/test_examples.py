import runpy
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).parents[1]
EXAMPLE_FILES = sorted((ROOT / "examples").glob("*/*.py"))
LOCAL_EXAMPLES = [
    ROOT / "examples/tools/basic.py",
    ROOT / "examples/tools/builtins.py",
    ROOT / "examples/skills/basic.py",
]


@pytest.mark.parametrize("path", EXAMPLE_FILES, ids=lambda path: path.stem)
def test_example_imports(path: Path) -> None:
    runpy.run_path(str(path))


@pytest.mark.parametrize("path", LOCAL_EXAMPLES, ids=lambda path: path.stem)
def test_local_example_runs(path: Path) -> None:
    completed = subprocess.run(
        [sys.executable, str(path)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
