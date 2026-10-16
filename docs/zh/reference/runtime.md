# Runtime 与运行结果

Runtime 组合模型、工具、Skills 与会话。使用 `async with` 初始化并释放资源，复用同一 Runtime 可以发起多次运行。

[快速开始](../getting-started/installation.md) · [流式输出](../how-to/streaming.md) · [会话与历史](../how-to/memory-and-sessions.md)

## 常用接口

| 接口 | 用途 |
| --- | --- |
| [`from_config`](#bumblehive.from_config) | 从配置对象、字典或 JSON 路径创建 Runtime。 |
| [`BumblehiveRuntime`](#bumblehive.BumblehiveRuntime) | `run()` 获取结果；`stream()` 消费事件；`run_console()` 在终端展示过程。`history` 与 `session_id` 不能同时使用，`approval_handler` 仅影响当前调用。 |
| [`AgentRun`](#bumblehive.AgentRun) | `run()` 和 `run_console()` 返回的单次运行对象，支持 `await`、`asyncio.create_task()` 和 `steer()`。 |
| [`AgentRunStream`](#bumblehive.AgentRunStream) | `stream()` 返回的单次事件流，支持 `steer()`、`result()` 和 `aclose()`。 |
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


<span id="steering"></span>

## 运行期间追加输入

保存运行对象，通过 `steer()` 补充或纠正当前任务。`run()` 和 `run_console()` 返回的对象在等待或调度后开始执行：

```python
import asyncio

run = runtime.run("修改登录页面")

# 将此回调接到应用的用户输入事件。
def on_user_input(text: str) -> None:
    run.steer(text)

task = asyncio.create_task(run)
result = await task
```

需要终端展示时，将 `runtime.run(...)` 换成 `runtime.run_console(...)`。输入由应用接收，回调须在运行所属的 asyncio 事件循环中执行；启动前也可以调用 `steer()`。

<span id="steering-rules"></span>

### 输入处理规则

`steer(message)` 接收与原始输入相同的 `UserMessage`：字符串或只含一条 user 消息的列表。它同步校验、复制并排队，每轮模型请求前按顺序取出当前待处理输入。

| 场景 | 行为 |
| --- | --- |
| 当前模型请求、重试、审批或工具执行中 | 当前操作继续完成，输入留待下一轮处理 |
| 响应包含工具调用 | 输入追加在整批工具结果之后 |
| 响应为普通回答 | 有待处理输入则追加在回答之后，继续请求模型；否则结束运行 |
| 输入入口已关闭 | `steer()` 抛出 `RuntimeError` |

一次模型响应结束不等于整次运行结束，最终结果事件只发送一次。引导仍受上下文预算和 `max_iterations` 限制；错误、取消和迭代上限仍会终止运行。

关闭后可用 `take_pending()` 取回并清空尚未消费的输入；关闭前调用会抛出 `RuntimeError`。待处理输入只保存在内存中，已加入历史的消息不会因后续保存或请求失败而退回队列。

每次运行独立持有输入队列。同一 Runtime 内，相同 Session 的运行依次执行，等锁期间也可提交引导；不同 Session 可并发。会话用法见[会话与历史](../how-to/memory-and-sessions.md)。

## 运行对象

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
