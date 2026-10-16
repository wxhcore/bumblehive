# Runtime 与运行结果

Runtime 组合模型、工具、Skills 与会话。使用 `async with` 初始化并释放资源，复用同一 Runtime 可以发起多次运行。

[快速开始](../getting-started/installation.md) · [流式输出](../how-to/streaming.md) · [会话与历史](../how-to/memory-and-sessions.md)

## 常用接口

| 接口 | 用途 |
| --- | --- |
| [`from_config`](#bumblehive.from_config) | 从配置对象、字典或 JSON 路径创建 Runtime。 |
| [`BumblehiveRuntime`](#bumblehive.BumblehiveRuntime) | 发起运行、消费事件流或在控制台展示过程。 |
| [`AgentRun`](#bumblehive.AgentRun) | `run()` 和 `run_console()` 返回的单次运行对象，支持 `await`、`asyncio.create_task()` 和 `steer()`。 |
| [`AgentRunStream`](#bumblehive.AgentRunStream) | `stream()` 返回的单次事件流，支持 `steer()`、`result()` 和 `aclose()`。 |
| [`AgentRunResult`](#bumblehive.AgentRunResult) | 运行完成后的结果，包含回答、工具使用情况、模型用量和错误。 |

## 创建与运行

从配置对象、字典或 JSON 路径创建 Runtime。

::: bumblehive.from_config
    options:
      heading_level: 3
      show_root_heading: true
      show_root_full_path: false

等待 `run()` 获取结果；迭代 `stream()` 消费事件；等待 `run_console()` 在终端展示过程并获取结果。`history` 与 `session_id` 不能同时使用，`approval_handler` 仅影响当前调用。

::: bumblehive.BumblehiveRuntime
    options:
      heading_level: 3
      show_root_heading: true
      show_root_full_path: false

## 运行对象

<span id="steering"></span>
<span id="steering-rules"></span>

运行期间补充或纠正任务，见[运行期间追加指令](../how-to/steering.md)。

::: bumblehive.AgentRun
    options:
      heading_level: 3
      show_root_heading: true
      show_root_full_path: false
      members:
        - steer
        - take_pending
        - close

`AgentRun` 支持直接 `await` 或交给 `asyncio.create_task()`，只能由一个 await 或 Task 驱动。需要多次读取结果时，等待同一个 Task。

未调度的对象用 `run.close()` 丢弃；运行中通过 Task 取消并等待清理。完整示例见[运行对象的生命周期](../concepts/runtime-lifecycle.md#run-lifecycle)。

需要检查协程类型时：`run()` 和 `run_console()` 是普通方法，`inspect.iscoroutinefunction()` 返回 `False`；返回对象实现 Coroutine 协议，但 `inspect.iscoroutine(run)` 也为 `False`。

::: bumblehive.AgentRunStream
    options:
      heading_level: 3
      show_root_heading: true
      show_root_full_path: false
      members:
        - steer
        - take_pending
        - result
        - aclose
      inherited_members: true

`AgentRunStream` 首次迭代时启动，只能消费一次。完整消费后读取 `result()`，提前退出时调用 `aclose()`。它支持 `async for`，不支持直接 `await stream`。示例见[流式输出](../how-to/streaming.md)。

## 读取结果

`final_content` 是最终回答，`usage` 是模型用量，`stop_reason` 说明结束原因。首先检查 `error`；`tools_used` 只记录成功执行的工具。

::: bumblehive.AgentRunResult
    options:
      heading_level: 3
      show_root_heading: true
      show_root_full_path: false
