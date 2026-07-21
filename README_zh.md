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
import bumblehive


runtime = bumblehive.from_config(
    {
        "provider": {"model": "gpt-5.4"},
        "agent": {"tool_names": []},
    }
)

result = await runtime.run("你好", session_id="user:123")
print(result.final_content)
```

## 流式事件

```python
async for event in runtime.stream("你好", session_id="user:123"):
    print(event.kind, event.session_id, event.payload)
```

## 本地开发

基础环境需要 Python 3.11+、Node.js 20.19+/22.12+。推荐使用独立的 Conda 环境：

```bash
conda create -n bumblehive_env python=3.11 -y
conda activate bumblehive_env
npm run setup
npm run doctor
```

`npm run setup` 使用当前激活的 Python，不依赖固定的 Conda 安装路径，并一次性安装 SDK 依赖、Server、WebUI 和桌面端依赖。

日常开发只需：

```bash
conda activate bumblehive_env
npm run dev
```

该命令同时启动 Server（`127.0.0.1:18421`）和 WebUI（`127.0.0.1:1420`）。也可以单独运行 `npm run dev:server` 或 `npm run dev:web`，使用 `npm test` 执行 Python 测试。

### 桌面端

macOS 还需要 Rust 和 Xcode Command Line Tools；Windows 还需要 Rust MSVC toolchain、WebView2，以及包含“使用 C++ 的桌面开发”工作负载的 Microsoft C++ Build Tools。

全新检出项目后，先生成桌面 sidecar，再执行完整的桌面环境检查：

```bash
npm run build:sidecar
npm run doctor:desktop
```

之后可以启动桌面开发模式或生成对应平台的安装包：

```bash
npm run dev:desktop
npm run build:mac
npm run build:win
```

sidecar 是生成产物，`npm run setup` 不会创建它。`dev:desktop` 和两个打包命令都会使用当前 Python 环境自动重建 sidecar。`build:mac` 仅在 macOS 使用，`build:win` 仅在 Windows 使用。
