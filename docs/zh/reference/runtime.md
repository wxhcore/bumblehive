# Runtime 与运行结果

Runtime 组合模型、工具、Skills 与会话。使用 `async with` 初始化并释放资源，复用同一 Runtime 可以发起多次运行。

[快速开始](../getting-started/installation.md) · [流式输出](../how-to/streaming.md) · [会话与历史](../how-to/memory-and-sessions.md)

## 常用接口

| 接口 | 用途 |
| --- | --- |
| [`from_config`](#bumblehive.from_config) | 从配置对象、字典或 JSON 路径创建 Runtime。 |
| [`BumblehiveRuntime`](#bumblehive.BumblehiveRuntime) | `run()` 获取结果；`stream()` 消费事件；`run_console()` 在终端展示过程。`history` 与 `session_id` 不能同时使用，`approval_handler` 仅影响当前调用。 |
| [`AgentRunResult`](#bumblehive.AgentRunResult) | `final_content` 是最终回答，`usage` 是模型用量，`stop_reason` 说明结束原因。首先检查 `error`；`tools_used` 只记录成功执行的工具。 |

## 创建与运行

从配置对象、字典或 JSON 路径创建 Runtime。

::: bumblehive.from_config
    options:
      heading_level: 3
      show_root_heading: true
      show_root_full_path: false

`run()` 获取结果；`stream()` 消费事件；`run_console()` 在终端展示过程。`history` 与 `session_id` 不能同时使用，`approval_handler` 仅影响当前调用。

::: bumblehive.BumblehiveRuntime
    options:
      heading_level: 3
      show_root_heading: true
      show_root_full_path: false


## 读取结果

`final_content` 是最终回答，`usage` 是模型用量，`stop_reason` 说明结束原因。首先检查 `error`；`tools_used` 只记录成功执行的工具。

::: bumblehive.AgentRunResult
    options:
      heading_level: 3
      show_root_heading: true
      show_root_full_path: false
