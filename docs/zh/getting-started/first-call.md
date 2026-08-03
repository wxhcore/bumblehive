# 运行第一个 Agent

本页将使用 `BumblehiveRuntime` 向模型发送一个问题，并打印回答。

预计时间：5 分钟。

## 前置条件

- 已经[安装 Bumblehive](installation.md)
- 有一个兼容 OpenAI Chat Completions 的模型服务
- 已准备好模型名称和 API Key

## 1. 设置环境变量

=== "macOS / Linux"

    ```bash
    export BUMBLEHIVE_MODEL="你的模型名称"
    export BUMBLEHIVE_API_KEY="你的 API Key"
    export BUMBLEHIVE_BASE_URL="https://你的服务地址/v1"
    ```

=== "Windows PowerShell"

    ```powershell
    $env:BUMBLEHIVE_MODEL="你的模型名称"
    $env:BUMBLEHIVE_API_KEY="你的 API Key"
    $env:BUMBLEHIVE_BASE_URL="https://你的服务地址/v1"
    ```

## 2. 编写代码

新建 `first_call.py`，写入：

```python
--8<-- "examples/runtime/basic.py"
```

## 3. 运行

在 `first_call.py` 所在目录执行：

```bash
python first_call.py
```

预期输出类似：

```text
回答：Agent Runtime 负责组织模型、上下文和工具，并完成一次 Agent 运行。
```

模型生成的具体文字可能不同。

## 代码说明

- `RuntimeArguments` 保存模型连接和运行配置。
- `skill_names=[]` 表示这次不向模型提供任何 Skill。
- `tool_names=[]` 表示这次不向模型开放任何工具，包括内置工具。
- `async with bumblehive.from_config(config) as runtime` 会在退出时关闭 Runtime 管理的资源。
- `result.error` 表示本次运行已经得到结果，但模型调用或执行过程失败。
- `result.final_content` 是最终回答。

!!! warning "不要随意删除两个空列表"
    `skill_names` 和 `tool_names` 省略时都默认为 `None`，表示使用全部可用项；传入 `[]` 才表示一个也不使用。第一次运行时建议明确使用空列表。

## 常见问题

### 提示缺少环境变量

如果看到 `KeyError: 'BUMBLEHIVE_MODEL'` 或 `KeyError: 'BUMBLEHIVE_API_KEY'`，说明环境变量没有在当前终端中设置。

### 输出“运行失败”

先阅读错误代码和消息。常见原因是 API Key 无效、模型名称错误，或 `BUMBLEHIVE_BASE_URL` 不是兼容接口的 `/v1` 地址。

### 程序直接抛出异常

网络中断、配置类型错误等情况可能直接抛出异常。`result.error` 只适用于已经返回 `AgentRunResult` 的失败。

## 下一步

[注册第一个 Python 工具](first-tool.md)。
