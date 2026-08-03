# 接下来学什么

你已经会创建 Runtime、调用模型，并注册 Python 工具。接下来可以按自己的目标选择内容。

| 目标 | 推荐内容 |
| --- | --- |
| 理解 Agent 的基本结构 | [Agent 的基本结构](../concepts/mental-model.md) |
| 保留多轮对话 | [使用消息历史和持久化会话](../how-to/memory-and-sessions.md) |
| 实时显示运行过程 | [使用流式输出](../how-to/streaming.md) |
| 处理失败和异常 | [处理运行错误](../how-to/error-handling.md) |
| 选择 Runtime 或底层组件 | [选择合适的抽象层](../concepts/choose-your-layer.md) |
| 查找接口和参数 | [Runtime API](../reference/runtime.md) |

普通项目继续使用 `BumblehiveRuntime` 即可。只有需要替换上下文构建、Provider 或执行循环时，才需要直接组合底层组件。
