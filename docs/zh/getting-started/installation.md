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
Agent Runtime 负责组织模型调用和工具执行，推动 Agent 完成任务。
```

具体措辞由模型决定。如果打印出 `None`，可查看 `result.error` 获取错误信息，详见[错误排查](../how-to/error-handling.md)。

## 这段代码做了什么

- `RuntimeArguments` 设置模型名、密钥和接口地址。默认开放已注册工具和可用 Skills；只支持纯文本的服务可以设置 `tool_names=[]`。详见[能力选择](../how-to/configuration.md#capability-lists)。
- `async with from_config(...)` 创建 Runtime，并在退出时释放连接。
- `await runtime.run(...)` 执行任务，`final_content` 是最终回答，`error` 是运行错误。

一个 Runtime 可以执行多次任务。不传入对话历史时，每次调用独立。

## 下一步

[给 Agent 添加一个工具](first-tool.md)，让它查询课程信息。

后续教程中以 `python examples/...` 或 `python -m examples...` 开头的命令使用仓库里的示例文件。要运行它们，在当前虚拟环境中执行一次：

```bash
git clone https://github.com/wxhcore/bumblehive.git
cd bumblehive
python -m pip install -e .
```

之后从这个仓库目录运行示例命令。
