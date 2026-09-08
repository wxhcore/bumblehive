# 提示词与上下文

用指令定义 Agent 的任务，再通过动态上下文补充项目和用户信息。上下文预算控制每次发给模型的消息量。

## 设置指令与动态信息

先完成[快速开始](../getting-started/installation.md)。以下代码在已创建的 `runtime` 中运行，覆盖本次请求的 Agent 配置：

```python
result = await runtime.run(
    "根据项目状态列出下一步工作。",
    config={
        "agent": {
            "instructions": "你是项目助手。回答简洁，不编造项目事实。",
            "dynamic_context": {"project": "Bumblehive", "stage": "文档整理"},
            "tool_names": [],
        },
    },
)
print(result.final_content)
```

创建 Runtime 时，对应扁平参数为 `agent_instructions` 和 `dynamic_context`；单次覆盖使用 `agent.instructions`。这些配置不代替会话历史，连续对话另见[会话与历史](memory-and-sessions.md)。

## 控制上下文大小

```python
result = await runtime.run(
    "概括已有对话。",
    config={
        "runtime": {
            "context_window_tokens": 64000,
            "max_tool_result_chars": 12000,
        },
        "generation": {"max_completion_tokens": 2048},
    },
)
```

| 参数 | 作用 |
| --- | --- |
| `context_window_tokens` | 请求的上下文预算，应匹配实际模型限制 |
| `max_completion_tokens` | 为输出预留的 token 数 |
| `max_tool_result_chars` | 工具结果进入模型前的字符上限 |
| `max_iterations` | 模型与工具循环次数上限，不是 token 预算 |

Runtime 准备一份面向模型的消息副本，修复工具消息顺序、截断工具结果，并在超出预算时裁剪较早的历史。若系统消息和工具定义已经占满预算，或裁剪后仍超限，会报告错误。

这是裁剪和截断，不会自动生成摘要。重要任务信息应明确放入指令或动态上下文；大量工具定义也会消耗预算。Token 数量是估算，不能代替模型服务的实际限制。

## 检查结果

检查 `result.error` 和 `result.usage`，通过[Hooks](hooks.md)观察模型请求与结果。排查长会话时，同时检查工具返回内容是否过大。

[配置参考](../reference/config.md) · [ContextBuilder 与 AgentLoop](../reference/agent.md)
