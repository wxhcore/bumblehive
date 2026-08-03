import re
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).parents[1]
DOCS = ROOT / "docs" / "zh"
SNIPPET = re.compile(r'--8<--\s+"([^"]+)"')


@pytest.mark.parametrize(
    "path",
    sorted(DOCS.rglob("*.md")),
    ids=lambda path: path.relative_to(DOCS).as_posix(),
)
def test_documentation_snippets_exist(path: Path) -> None:
    references = SNIPPET.findall(path.read_text(encoding="utf-8"))
    missing = [reference for reference in references if not (ROOT / reference).is_file()]

    assert not missing, f"Missing snippets in {path}: {missing}"


def test_public_api_is_in_reference() -> None:
    completed = subprocess.run(
        [sys.executable, "docs/scripts/check_api_coverage.py"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
