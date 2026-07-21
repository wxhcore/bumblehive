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
import bumblehive


runtime = bumblehive.from_config(
    {
        "provider": {"model": "gpt-5.4"},
        "agent": {"tool_names": []},
    }
)

result = await runtime.run("Hello", session_id="user:123")
print(result.final_content)
```

## Streaming

```python
async for event in runtime.stream("Hello", session_id="user:123"):
    print(event.kind, event.session_id, event.payload)
```

## Local Development

The base requirements are Python 3.11+ and Node.js 20.19+/22.12+. A dedicated Conda environment is recommended:

```bash
conda create -n bumblehive_env python=3.11 -y
conda activate bumblehive_env
npm run setup
npm run doctor
```

`npm run setup` uses the currently active Python interpreter, does not depend on a fixed Conda path, and installs the SDK dependencies, Server, WebUI, and desktop dependencies together.

For daily development:

```bash
conda activate bumblehive_env
npm run dev
```

This starts the Server on `127.0.0.1:18421` and the WebUI on `127.0.0.1:1420`. Use `npm run dev:server` or `npm run dev:web` to run one component, and `npm test` for the Python test suite.

### Desktop

macOS additionally requires Rust and Xcode Command Line Tools. Windows additionally requires the Rust MSVC toolchain, WebView2, and Microsoft C++ Build Tools with the Desktop development with C++ workload.

On a clean checkout, build the generated desktop sidecar before running the full desktop environment check:

```bash
npm run build:sidecar
npm run doctor:desktop
```

Then start development or create a platform-specific installer:

```bash
npm run dev:desktop
npm run build:mac
npm run build:win
```

The sidecar is a generated artifact and is not created by `npm run setup`. `dev:desktop` and both packaging commands rebuild it automatically with the current Python environment. Use `build:mac` only on macOS and `build:win` only on Windows.
