<div align="center">

![BumbleHive](./assets/bumblehive.png)

**小核心，大轰鸣 | Small Core, Big Buzz**

A lightweight Python SDK for building a complete Agent Loop in just a few lines of code.

[![PyPI](https://img.shields.io/pypi/v/bumblehive?label=PyPI)](https://pypi.org/project/bumblehive/)
[![Python](https://img.shields.io/badge/Python-3.11%2B-blue)](https://www.python.org/)
[![Python SDK CI](https://github.com/wxhcore/bumblehive/actions/workflows/sdk-ci.yml/badge.svg?branch=main)](https://github.com/wxhcore/bumblehive/actions/workflows/sdk-ci.yml)
[![Platforms](https://img.shields.io/badge/SDK-macOS%20%7C%20Windows%20%7C%20Linux-lightgrey)](#local-development)
[![MCP](https://img.shields.io/badge/MCP-Supported-green)](https://modelcontextprotocol.io/)
[![License](https://img.shields.io/badge/License-Apache%202.0-yellow.svg)](https://opensource.org/licenses/Apache-2.0)

English | [简体中文](./README_zh.md)

</div>

---

## Highlights

- Tool-driven agent loop with built-in and MCP-backed tools.
- Streaming lifecycle events for model deltas, tool calls, errors, and final results.
- Session-aware runtime with isolated history and concurrency control.
- Modular Python APIs for configuration, providers, tools, skills, and observability.

## Quick Start

Install the Python SDK:

```bash
python -m pip install bumblehive
```

Set `BUMBLEHIVE_MODEL`, `BUMBLEHIVE_API_KEY`, and `BUMBLEHIVE_BASE_URL`. Then run:

```python
import asyncio
import os

import bumblehive


async def main() -> None:
    config = bumblehive.RuntimeArguments(
        model=os.environ["BUMBLEHIVE_MODEL"],
        api_key=os.environ["BUMBLEHIVE_API_KEY"],
        base_url=os.environ["BUMBLEHIVE_BASE_URL"],
    )
    async with bumblehive.from_config(config) as runtime:
        result = await runtime.run("Explain Agent Loop in one sentence.")

    print(result.final_content)


asyncio.run(main())
```

## Documentation

Start with the [Bumblehive Python SDK documentation](docs/en/index.md). The complete guide is currently available in Chinese:

- [Installation and first call](docs/zh/getting-started/installation.md)
- [Register your first Python tool](docs/zh/getting-started/first-tool.md)
- [Understand the basic Agent structure](docs/zh/concepts/mental-model.md)
- [Choose the right abstraction layer](docs/zh/concepts/choose-your-layer.md)
- [API Reference](docs/zh/reference/runtime.md)

## Examples

See [examples](examples/README.md) for independently runnable Runtime, Loop,
Provider, Tools, Skills, and Observability examples.

## Local Development

The Python SDK, Server, and WebUI development workflow supports macOS, Windows, and Ubuntu Linux. It requires Python 3.11+, Node.js 22.12+, and pnpm 10.33.0. A dedicated Conda environment is recommended:

```bash
pnpm run setup
```

`pnpm run setup` is the only project setup entry point. It installs every Node workspace dependency from the root lockfile, then uses the active Python interpreter to install the SDK, Server, test, and desktop packaging dependencies before running the core environment check. `pnpm run dev` repeats that lightweight preflight before starting either process. If a requirement is missing, the command stops with a targeted error. The same command works on Ubuntu Linux and does not require the desktop system toolchain. Set `BUMBLEHIVE_PYTHON` to an interpreter path to override the active interpreter.

For daily development:

```bash
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
