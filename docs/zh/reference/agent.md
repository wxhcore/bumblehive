# Agent Loop

当 `BumblehiveRuntime` 不能满足组合需求时，再使用底层 Agent API。

| 接口 | 适合场景 |
| --- | --- |
| `AgentLoop` | 自己组合 Context、Skills、Tools 和 Provider |
| `ToolCallingRunner` | 已经准备好消息，只需要模型与工具循环 |
| `ContextBuilder` | 自定义运行上下文 |
| `MessageHistory` | 调用者管理的对话历史 |

`skill_names` 与 `tool_names` 都支持三种选择：`None` 表示全部，`[]` 表示不提供，非空列表表示只选择指定项。Skill 只把摘要加入上下文，Tool 才是模型可以调用的函数。完整规则见[配置 Runtime](../how-to/configuration.md#capability-lists)。

## 公开接口

::: bumblehive.agent
    options:
      show_root_heading: false
      show_root_full_path: false
