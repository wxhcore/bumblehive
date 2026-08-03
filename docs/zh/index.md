# 快速开始

Bumblehive 是一个 Python Agent 运行时。它把模型、工具和对话上下文组合起来，让你可以专注于自己的业务代码。

## 第一次使用

这一部分带你从安装开始，逐步创建一个能够调用 Python 工具的 Agent。

| 步骤 | 你将完成什么 | 预计时间 |
| --- | --- | --- |
| [1. 安装](getting-started/installation.md) | 创建 Python 环境并安装 Bumblehive | 5 分钟 |
| [2. 第一次调用](getting-started/first-call.md) | 获得第一条模型回答 | 5 分钟 |
| [3. 第一个工具](getting-started/first-tool.md) | 让 Agent 调用你的 Python 函数 | 10 分钟 |

你只需要具备基础 Python 知识，不需要提前了解 Agent 框架。完成后，你就拥有了一个可以继续扩展的最小 Agent。

## 你想做什么？

| 目标 | 从这里开始 |
| --- | --- |
| 快速构建 Agent | 使用 `BumblehiveRuntime`，从[运行第一个 Agent](getting-started/first-call.md)开始 |
| 给 Agent 添加业务能力 | 阅读[注册第一个 Python 工具](getting-started/first-tool.md) |
| 理解 Agent 的基本结构 | 阅读[Agent 的基本结构](concepts/mental-model.md) |
| 把 Bumblehive 集成到已有项目 | 先阅读[接下来学什么](getting-started/next-steps.md) |

!!! tip "普通项目优先使用 Runtime"
    `BumblehiveRuntime` 已经组合好常用组件。只有需要自定义底层执行流程时，才需要直接使用 `AgentLoop`。

## 文档范围

当前文档只介绍 Bumblehive Python SDK，示例要求 Python 3.11 或更高版本。
