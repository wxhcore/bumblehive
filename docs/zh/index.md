---
hide:
  - toc
---

# BumbleHive：用 Python 构建 Agent

BumbleHive 是一个 Python Agent SDK。你提供模型、任务和工具，它负责调用模型、执行工具，并把结果交回模型，直到任务完成。

可以用它构建文件助手、业务查询助手或交互式聊天应用。需要 Python 3.11+；模型通过 OpenAI Chat Completions 兼容接口接入。

[开始使用](getting-started/installation.md){ .md-button .md-button--primary }

## 能做什么

| 能力 | 用途 |
| --- | --- |
| [工具调用](getting-started/first-tool.md) | 把 Python 函数交给 Agent 使用 |
| [多轮对话与记忆](how-to/memory-and-sessions.md) | 保留对话，在下一轮或程序重启后继续 |
| [流式输出](how-to/streaming.md)与[图片输入](how-to/images.md) | 逐步显示回答，处理文字和图片 |
| [审批](concepts/tool-safety.md)、[引导](how-to/steering.md)、[追问](how-to/ask-user.md) | 让用户参与 Agent 的决策和执行 |
| [文件与命令](how-to/files-and-commands.md) | 阅读项目、修改文件、执行验证 |
| [MCP](how-to/mcp.md)与[Skills](how-to/skills.md) | 接入外部工具和可复用的任务方法 |
| [上下文](how-to/context.md)与[Hooks](how-to/hooks.md) | 提供任务信息，观察运行过程 |
| [子 Agent 协作](examples/sub-agents.md) | 委派独立任务，等待结果或后台执行 |

想看完整应用，可以从[文件助手](examples/file-assistant.md)或[交互式聊天助手](examples/chat-interface.md)开始。
