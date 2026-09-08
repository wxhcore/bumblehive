# AgentLoop 与 Runner

直接组装底层对象时，需要自行管理 Provider、工具与资源生命周期。普通应用从 Runtime 开始。

[Agent 如何工作](../concepts/mental-model.md) · [上下文指南](../how-to/context.md) · [消息与会话](protocols.md)

## 常用接口

| 接口 | 用途 |
| --- | --- |
| [`AgentLoop`](#bumblehive.agent.AgentLoop) | 构建上下文、选择 Skills 和 Tools，再驱动运行。 |
| [`ToolCallingRunner`](#bumblehive.agent.ToolCallingRunner) | 对已经准备好的消息执行模型与工具循环。 |
| [`ContextBuilder`](#bumblehive.agent.ContextBuilder) | 组装指令、动态信息和能力说明。窗口裁剪与工具结果截断的应用配置见上下文指南。 |

## 循环与执行

构建上下文、选择 Skills 和 Tools，再驱动运行。

::: bumblehive.agent.AgentLoop
    options:
      heading_level: 3
      show_root_heading: true
      show_root_full_path: false

对已经准备好的消息执行模型与工具循环。

::: bumblehive.agent.ToolCallingRunner
    options:
      heading_level: 3
      show_root_heading: true
      show_root_full_path: false


## 上下文组装

组装指令、动态信息和能力说明。窗口裁剪与工具结果截断的应用配置见上下文指南。

::: bumblehive.agent.ContextBuilder
    options:
      heading_level: 3
      show_root_heading: true
      show_root_full_path: false

## 相关类型

<span id="bumblehive.agent.AgentRunResult"></span>

[`AgentRunResult`](runtime.md#bumblehive.AgentRunResult) 的完整定义已集中到对应主题。

<span id="bumblehive.agent.MessageHistory"></span>

[`MessageHistory`](protocols.md#bumblehive.MessageHistory) 的完整定义已集中到对应主题。
