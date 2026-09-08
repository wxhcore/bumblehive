# 安装与快速开始

安装 Python SDK，连接模型，然后运行一个能查询课程信息的 Agent。需要 Python 3.11+ 和支持工具调用的 Chat Completions 兼容服务。

## 安装 SDK

建议在独立 Python 环境中安装：

=== "macOS / Linux"

    ```bash
    python3 -m venv .venv
    source .venv/bin/activate
    python -m pip install bumblehive
    ```

=== "Windows PowerShell"

    ```powershell
    py -m venv .venv
    .venv\Scripts\Activate.ps1
    python -m pip install bumblehive
    ```

=== "Conda"

    ```bash
    conda create -n bumblehive_env python=3.11 -y
    conda activate bumblehive_env
    python -m pip install bumblehive
    ```

## 配置模型 { #configure-model }

替换模型名、密钥和服务地址。`base_url` 是 API 基地址，通常以 `/v1` 结尾，具体以你的服务为准。

=== "macOS / Linux"

    ```bash
    export BUMBLEHIVE_MODEL="your-model"
    export BUMBLEHIVE_API_KEY="your-api-key"
    export BUMBLEHIVE_BASE_URL="https://your-provider.example/v1"
    ```

=== "Windows PowerShell"

    ```powershell
    $env:BUMBLEHIVE_MODEL = "your-model"
    $env:BUMBLEHIVE_API_KEY = "your-api-key"
    $env:BUMBLEHIVE_BASE_URL = "https://your-provider.example/v1"
    ```

这些变量由示例中的 `os.environ` 读取，SDK 不会自动读取它们。

## 运行第一个 Agent

新建 `agent.py`，复制以下完整程序：

```python title="agent.py"
--8<-- "examples/runtime/custom_tool.py"
```

```bash
python agent.py
```

输出示例：

```text
工具：get_course_info
回答：Python 入门课在周一 10:00，于教学楼 A101 上课。
```

具体措辞由模型决定。检查工具一行是否包含 `get_course_info`；若没有，查看[工具调用排错](../troubleshooting.md)。

## 理解这次运行

`from_config()` 创建 Runtime，`async with` 初始化工具并在退出时释放模型和 MCP 连接。装饰器注册 Python 函数；`tool_names` 指定本次开放的工具；`run()` 驱动模型与工具循环，并返回 `AgentRunResult`。

一个 Runtime 可以执行多次调用。每次调用默认独立；需要多轮对话时传入[会话或历史](../how-to/memory-and-sessions.md)。从源码仓库运行同一个示例：

```bash
python examples/runtime/custom_tool.py
```

## 继续构建

- [工具调用](first-tool.md)：参数、异步函数与执行结果。
- [流式输出](../how-to/streaming.md)：展示回答与工具进度。
- [工具审批](../concepts/tool-safety.md)：执行前等待用户确认。
- [Runtime API](../reference/runtime.md)：查询调用参数和结果字段。
