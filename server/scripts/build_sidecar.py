"""Build the Bumblehive FastAPI server as a Tauri sidecar binary."""

import importlib.util
import os
from pathlib import Path
import subprocess
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SERVER_ROOT = PROJECT_ROOT / "server"
TAURI_ROOT = PROJECT_ROOT / "desktop" / "src-tauri"


def _target_triple() -> str:
    result = subprocess.run(
        ["rustc", "--print", "host-tuple"],
        check=True,
        capture_output=True,
        text=True,
    )
    target = result.stdout.strip()
    if not target:
        raise RuntimeError("rustc returned an empty host target")
    return target


def main() -> None:
    if importlib.util.find_spec("PyInstaller") is None:
        raise SystemExit(
            "PyInstaller is not installed. Run: "
            'python -m pip install "pyinstaller==6.21.0"'
        )

    target = _target_triple()
    executable_suffix = ".exe" if "windows" in target else ""
    binary_name = "bumblehive-server"
    sidecar_dir = TAURI_ROOT / "sidecar"
    build_dir = PROJECT_ROOT / "build" / "sidecar" / target
    sidecar_dir.mkdir(parents=True, exist_ok=True)
    build_dir.mkdir(parents=True, exist_ok=True)
    environment = os.environ.copy()
    environment["PYINSTALLER_CONFIG_DIR"] = os.fspath(build_dir / "cache")

    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        *(["--noconsole"] if "windows" in target else []),
        "--onedir",
        "--name",
        binary_name,
        "--distpath",
        os.fspath(sidecar_dir),
        "--workpath",
        os.fspath(build_dir / "work"),
        "--specpath",
        os.fspath(build_dir),
        "--paths",
        os.fspath(PROJECT_ROOT / "src"),
        "--paths",
        os.fspath(SERVER_ROOT / "src"),
        "--collect-submodules",
        "uvicorn",
        "--add-data",
        (
            os.fspath(
                PROJECT_ROOT
                / "src"
                / "bumblehive"
                / "agent"
                / "context"
                / "prompts"
            )
            + os.pathsep
            + "bumblehive/agent/context/prompts"
        ),
        "--hidden-import",
        "bumblehive.agent.context.prompts",
        "--copy-metadata",
        "fastmcp",
        "--copy-metadata",
        "fastmcp-slim",
        os.fspath(SERVER_ROOT / "sidecar.py"),
    ]
    subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        env=environment,
        check=True,
    )

    output = sidecar_dir / binary_name / f"{binary_name}{executable_suffix}"
    if not output.is_file():
        raise RuntimeError(f"sidecar build completed without output: {output}")
    print(f"Sidecar ready: {output}")


if __name__ == "__main__":
    main()
