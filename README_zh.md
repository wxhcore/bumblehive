# BumbleHive

一个面向工具驱动 Loop 工程设计的 Agent Runtime。

BumbleHive 是一个轻量的 Python 库，用清晰的执行循环来构建 AI Agent：构建上下文、调用模型、执行工具、观察事件，并持续推进直到得到最终结果。

## 特性

- 工具驱动的 Agent Loop，支持内置工具和 MCP 工具。
- 流式生命周期事件，覆盖模型 delta、工具调用、错误和最终结果。
- 支持 session 的 runtime，隔离历史并控制并发。
- 模块化 Python API，覆盖配置、provider、工具、skills 和可观测能力。

## 快速开始

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
    result = await runtime.run("简述 Agent Loop，保存为 agent-loop.md。")


asyncio.run(main())
```

## 示例

参见 [examples](examples/README.md)，其中包含可独立运行的 Runtime、Loop、
Provider、Tools、Skills 和 Observability 示例。

## 本地开发

Python SDK、Server 和 WebUI 的开发流程支持 macOS、Windows 和 Ubuntu Linux。基础环境需要 Python 3.11+、Node.js 20.19+/22.12+。推荐使用独立的 Conda 环境：

```bash
conda create -n bumblehive_env python=3.11 -y
conda activate bumblehive_env
npm run setup
```

`npm run setup` 使用当前激活的 Python，不依赖固定的 Conda 安装路径。它会安装 Python SDK、Server 和 WebUI 依赖，并自动检查核心环境；`npm run dev` 也会在启动两个进程前重复这项轻量预检。缺少任何必要条件时，命令都会停止并给出明确提示。Ubuntu Linux 使用相同命令，该流程不需要安装 Tauri 系统依赖。如需覆盖当前解释器，可以通过 `BUMBLEHIVE_PYTHON` 指定 Python 路径。

日常开发只需：

```bash
conda activate bumblehive_env
npm run dev
```

该命令同时启动 Server（`127.0.0.1:18421`）和 WebUI（`127.0.0.1:1420`）。也可以单独运行 `npm run dev:server` 或 `npm run dev:web`，使用 `npm test` 执行 Python 测试。

### 桌面端

可选的桌面端流程目前面向 macOS 和 Windows。macOS 还需要 Rust 和 Xcode Command Line Tools；Windows 还需要 Rust MSVC toolchain、WebView2，以及包含“使用 C++ 的桌面开发”工作负载的 Microsoft C++ Build Tools。

全新检出项目后，只需安装一次额外的桌面端依赖：

```bash
npm run setup:desktop
```

之后可以启动桌面开发模式，或为当前平台生成安装包：

```bash
npm run dev:desktop
npm run build:desktop
```

`npm run setup:desktop` 会执行 SDK、Server 和 WebUI 的安装，额外安装 Tauri 与 PyInstaller 依赖，并自动检查完整的桌面环境。`dev:desktop` 和 `build:desktop` 也会重复这项预检，再使用当前 Python 环境自动将 Server 打包成 sidecar，然后启动 Tauri。`build:desktop` 在 macOS 生成 app 和 DMG，在 Windows 生成 NSIS 安装包。
