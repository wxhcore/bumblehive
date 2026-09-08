---
hide:
  - toc
---

<div class="bh-hero" markdown>


# 让你的 Agent，开始工作。

用 Python 连接模型、调用工具、保存会话。通过 MCP、Skills 和执行前审批，把一个简单的 Agent Loop 组合成你的应用。

[开始构建 :material-arrow-right:](getting-started/installation.md){ .md-button .md-button--primary }
[查看应用示例 :material-arrow-up-right:](examples/file-assistant.md){ .md-button }

</div>

## 一个能调用工具的 Agent

先[安装 SDK 并设置模型环境变量](getting-started/installation.md#configure-model)。下面是在已创建的 `runtime` 中注册和调用工具的核心代码：

```python title="注册工具，交给 Agent 调用"
@runtime.tools.tool(name="add", description="计算两个整数的和。")
def add(a: int, b: int) -> int:
    return a + b

result = await runtime.run(
    "请调用 add 计算 21 加 34。",
    config={"agent": {"tool_names": ["add"]}},
)
print(result.error.message if result.error else result.final_content)
```

??? example "查看完整可运行程序：查询课程信息"

    保存为 `agent.py`，运行 `python agent.py`。示例使用本地数据，终端会显示使用的工具名称和最终回答。

    ```python title="agent.py"
    --8<-- "examples/runtime/custom_tool.py"
    ```

## 按需构建你的 Agent

<div class="grid cards bh-capabilities" markdown>

-   :material-wrench-outline: **[工具调用](getting-started/first-tool.md)**

    把 Python 函数交给 Agent，完成查询和业务操作。

-   :material-connection: **[MCP](how-to/mcp.md)**

    连接外部服务，选择向模型开放的远端工具。

-   :material-book-open-outline: **[Skills](how-to/skills.md)**

    按需加载可复用的工作方法与资源。

-   :material-message-text-outline: **[会话与历史](how-to/memory-and-sessions.md)**

    保存多轮对话，在程序重启后继续。

-   :material-radio-tower: **[流式输出](how-to/streaming.md)**

    显示回答增量、工具进度与最终结果。

-   :material-shield-check-outline: **[工具审批](concepts/tool-safety.md)**

    在执行之前，让应用或用户批准、拒绝调用。

</div>

## 把能力组合成应用

| 你想构建 | 组合方式 |
| --- | --- |
| [文件与代码助手](examples/file-assistant.md) | 文件搜索、修改、命令验证与人工审批 |
| [聊天界面](examples/chat-interface.md) | 文本增量、工具状态、会话与停止操作 |
| [子 Agent 委派](examples/sub-agents.md) | 用工具委派任务，隔离上下文和工具范围 |

需要查询具体参数时，直接访问 [API 参考](reference/runtime.md)。文档面向 Python 3.11+，高层 Runtime 使用 OpenAI Chat Completions 兼容接口。
