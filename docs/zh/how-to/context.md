# 提示词与上下文

用指令说明 Agent 应该怎样工作，用动态上下文提供当前项目或用户的信息。

## 提供任务背景

完成[模型配置](../getting-started/installation.md#configure-model)，运行 `python examples/runtime/context.py`：

```python
--8<-- "examples/runtime/context.py"
```

`agent_instructions` 定义助手的职责与回答要求，`dynamic_context` 提供项目名称和当前阶段。回答应提到 BumbleHive 正在整理文档，并据此建议下一步。

这些配置不是对话记忆；保存用户此前说过的话，使用[会话与历史](memory-and-sessions.md)。单次修改指令的方式见[模型配置](configuration.md#overrides)。

## 控制长对话的大小

在 `RuntimeArguments(...)` 中按模型容量添加：

```python
context_window_tokens=64000,
max_completion_tokens=2048,
max_tool_result_chars=12000,
```

分别控制上下文预算、为输出预留的 token 数，以及单个工具结果的字符预算。

SDK 会截断过长的工具结果，并在超出预算时裁剪较早的历史，不会自动生成摘要。重要的任务要求应放在指令或动态上下文中。预算无法容纳必要内容时，运行会返回错误。

[配置参考](../reference/config.md) · [上下文构建接口](../reference/agent.md)
