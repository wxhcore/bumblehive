"""Validate that a desktop release tag matches the desktop manifests."""

from __future__ import annotations

import json
import re
import sys
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TAG_PATTERN = re.compile(r"desktop-v(?P<version>\d+\.\d+\.\d+)")


def main(tag: str) -> int:
    match = TAG_PATTERN.fullmatch(tag)
    if match is None:
        print(
            "Desktop release tags must use the form desktop-vX.Y.Z.",
            file=sys.stderr,
        )
        return 1

    expected = match.group("version")
    versions = {
        "desktop/src-tauri/tauri.conf.json": _json_version(
            ROOT / "desktop" / "src-tauri" / "tauri.conf.json"
        ),
        "desktop/package.json": _json_version(
            ROOT / "desktop" / "package.json"
        ),
        "desktop/src-tauri/Cargo.toml": _cargo_version(
            ROOT / "desktop" / "src-tauri" / "Cargo.toml"
        ),
    }
    mismatches = {
        path: version for path, version in versions.items() if version != expected
    }

    if mismatches:
        print(
            f"Release tag {tag} expects desktop version {expected}, "
            "but these files do not match:",
            file=sys.stderr,
        )
        for path, version in mismatches.items():
            print(f"- {path}: {version}", file=sys.stderr)
        return 1

    print(f"Desktop release version verified: {expected}")
    return 0


def _json_version(path: Path) -> str:
    data = json.loads(path.read_text(encoding="utf-8"))
    return str(data["version"])


def _cargo_version(path: Path) -> str:
    with path.open("rb") as file:
        data = tomllib.load(file)
    return str(data["package"]["version"])


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(
            "Usage: python desktop/scripts/check_release_version.py "
            "desktop-vX.Y.Z"
        )
    raise SystemExit(main(sys.argv[1]))
