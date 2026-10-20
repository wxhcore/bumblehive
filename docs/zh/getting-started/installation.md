# 快速开始

安装 SDK，连接模型，运行第一个 Agent。需要 Python 3.11+ 和 OpenAI Chat Completions 兼容服务。

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
--8<-- "examples/runtime/basic.py"
```

```bash
python agent.py
```

输出类似：

```text
回答：Agent Runtime 负责组织模型调用和工具执行，推动 Agent 完成任务。
```

具体措辞由模型决定。如果运行失败，根据错误检查模型名、密钥和接口地址，详见[错误排查](../how-to/error-handling.md)。

## 这段代码做了什么

- `RuntimeArguments` 提供模型配置。`tool_names=[]` 和 `skill_names=[]` 让第一个例子只进行文本问答。
- `async with from_config(...)` 创建 Runtime，并在退出时释放连接。
- `await runtime.run(...)` 执行任务，`final_content` 是最终回答，`error` 是运行错误。

一个 Runtime 可以执行多次任务。不传入对话历史时，每次调用独立。

## 下一步

[给 Agent 添加一个工具](first-tool.md)，让它查询课程信息，而不只是生成文本。
