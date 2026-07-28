# BumbleHive

An agent runtime designed for tool-driven loop engineering.

BumbleHive is a lightweight Python library for building AI agents around a clear execution loop: build context, call the model, execute tools, observe events, and continue until a final result is produced.

## Highlights

- Tool-driven agent loop with built-in and MCP-backed tools.
- Streaming lifecycle events for model deltas, tool calls, errors, and final results.
- Session-aware runtime with isolated history and concurrency control.
- Modular Python APIs for configuration, providers, tools, skills, and observability.

## Quick Start

```python
import asyncio
import os

import bumblehive


async def main() -> None:
    config = bumblehive.RuntimeArguments(
        model=os.environ["BUMBLEHIVE_MODEL"],
        api_key=os.environ["BUMBLEHIVE_API_KEY"],
        base_url=os.getenv("BUMBLEHIVE_BASE_URL"),
        workspace="./demo",
    )
    runtime = bumblehive.from_config(config)
    result = await runtime.run("Summarize Agent Loop in agent-loop.md.")


asyncio.run(main())
```

## Examples

See [examples](examples/README.md) for independently runnable Runtime, Loop,
Provider, Tools, Skills, and Observability examples.

## Local Development

The Python SDK, Server, and WebUI development workflow supports macOS, Windows, and Ubuntu Linux. It requires Python 3.11+, Node.js 22.12+, and pnpm 10.33.0. A dedicated Conda environment is recommended:

```bash
conda create -n bumblehive_env python=3.11 -y
conda activate bumblehive_env
pnpm run setup
```

`pnpm run setup` is the only project setup entry point. It installs every Node workspace dependency from the root lockfile, then uses the active Python interpreter to install the SDK, Server, test, and desktop packaging dependencies before running the core environment check. `pnpm run dev` repeats that lightweight preflight before starting either process. If a requirement is missing, the command stops with a targeted error. The same command works on Ubuntu Linux and does not require the desktop system toolchain. Set `BUMBLEHIVE_PYTHON` to an interpreter path to override the active interpreter.

For daily development:

```bash
conda activate bumblehive_env
pnpm run dev
```

This starts the Server on `127.0.0.1:18421` and the WebUI on `127.0.0.1:1420`. Use `pnpm run dev:server` or `pnpm run dev:web` to run one component, and `pnpm test` for the Python test suite.

### Desktop

The optional desktop workflow currently targets macOS and Windows. macOS additionally requires Rust and Xcode Command Line Tools. Windows additionally requires the Rust MSVC toolchain, WebView2, and Microsoft C++ Build Tools with the Desktop development with C++ workload.

After the shared `pnpm run setup`, start development or create the installer for the current platform:

```bash
pnpm run dev:desktop
pnpm run build:desktop
```

Both commands verify Rust, Tauri, and the platform toolchain, then automatically package the Python Server as a sidecar before starting Tauri. `build:desktop` creates an app and DMG on macOS or an NSIS installer on Windows.
