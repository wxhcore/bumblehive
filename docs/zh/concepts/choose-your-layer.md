# 选择合适的接口层

大多数项目从 `BumblehiveRuntime` 开始即可。只有需要替换底层组件时，才使用更低层接口。

## 快速选择

| 你的目标 | 推荐接口 |
| --- | --- |
| 快速构建一个完整 Agent | `BumblehiveRuntime` |
| 自己组合 Provider、上下文、Skills 和工具 | `AgentLoop` |
| 已有消息构建逻辑，只需要模型与工具循环 | `ToolCallingRunner` |
| 只想注册或独立执行工具 | `ToolManager` |

## `BumblehiveRuntime`：普通项目首选

Runtime 会管理：

- Provider 的创建和关闭；
- 内置工具和 MCP 的初始化；
- 上下文、Skills 和 Agent 循环；
- 内存历史与持久化会话；
- 流式事件。

```python
async with bumblehive.from_config(config) as runtime:
    result = await runtime.run("你好")
```

如果你要把 Bumblehive 作为项目的 Agent Core，通常只需要在 Runtime 外再封装一层业务配置和业务工具。

## `AgentLoop`：需要自定义 Provider 时使用

`AgentLoop` 仍然会构建上下文、加载 Skills，并运行工具循环，但 Provider 由调用者传入。

适合以下情况：

- 接入自定义 `ModelProvider`；
- 为测试传入离线 Fake Provider；
- 自己管理 Provider 的生命周期；
- 复用自定义的 `ContextBuilder`、`SkillsManager` 或 `ToolManager`。

当前高层 Runtime 只创建 `openai_chat_completions` Provider。其他 Provider 应通过 `AgentLoop` 接入。

## `ToolCallingRunner`：只保留工具调用循环

这一层要求你自己准备完整的 `messages`，并显式传入 Provider、模型和工具。

它不会替你完成 Runtime 的配置管理、Skills 组合或持久化会话。适合已经有消息系统的项目，不适合作为初学者入口。

## `ToolManager`：独立使用工具

`ToolManager` 可以在没有模型的情况下注册、检查和执行工具，适合：

- 单元测试工具；
- 把现有 Python 函数转换为 Tool；
- 管理 MCP 连接；
- 检查模型能够看到哪些工具。

## 推荐规则

> 先使用能完成任务的最高层接口。只有 Runtime 无法满足扩展需求时，再下降到 `AgentLoop` 或 `ToolCallingRunner`。

下一步：阅读[Runtime 生命周期](runtime-lifecycle.md)。
