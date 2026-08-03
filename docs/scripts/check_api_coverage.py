"""Check that every public Python module is included in API Reference."""

from __future__ import annotations

import importlib
import re
import sys
from pathlib import Path
from types import ModuleType


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

PUBLIC_API = importlib.import_module("tests.public_api_contract").PUBLIC_API
DIRECTIVE = re.compile(r"^:::\s+([A-Za-z_][\w.]*)\s*$", re.MULTILINE)


def main() -> int:
    reference_dir = ROOT / "docs" / "zh" / "reference"
    directives: set[str] = set()
    for path in reference_dir.glob("*.md"):
        directives.update(DIRECTIVE.findall(path.read_text(encoding="utf-8")))

    documented_objects: set[int] = set()
    for identifier in directives:
        obj = _resolve_identifier(identifier)
        if isinstance(obj, ModuleType):
            documented_objects.update(
                id(getattr(obj, name))
                for name in getattr(obj, "__all__", ())
            )
        else:
            documented_objects.add(id(obj))

    missing: list[str] = []
    public_count = 0
    for module in PUBLIC_API:
        module_name = module.__name__
        exports = tuple(getattr(module, "__all__", ()))
        public_count += len(exports)

        missing.extend(
            f"{module_name}.{name}"
            for name in exports
            if id(getattr(module, name)) not in documented_objects
        )

    if missing:
        print("Missing API reference directives:")
        for identifier in missing:
            print(f"- {identifier}")
        return 1

    print(
        f"API reference covers {public_count} public exports "
        f"from {len(PUBLIC_API)} modules."
    )
    return 0


def _resolve_identifier(identifier: str) -> object:
    parts = identifier.split(".")
    for index in range(len(parts), 0, -1):
        module_name = ".".join(parts[:index])
        try:
            obj: object = importlib.import_module(module_name)
        except ModuleNotFoundError:
            continue

        for name in parts[index:]:
            obj = getattr(obj, name)
        return obj

    raise ValueError(f"Cannot resolve API documentation identifier: {identifier}")


if __name__ == "__main__":
    raise SystemExit(main())
