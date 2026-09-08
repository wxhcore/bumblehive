# 事件与 Hooks

事件描述一次运行的进度，Hook 接收事件，AsyncEventStream 支持边运行边消费。事件记录默认在内存中，持久日志由应用实现。

[流式输出](../how-to/streaming.md) · [Hooks 指南](../how-to/hooks.md) · [接入聊天界面](../examples/chat-interface.md)

## 常用接口

| 接口 | 用途 |
| --- | --- |
| [`AgentEvent`](#bumblehive.observability.AgentEvent) | 包含 kind、run_id、payload、timestamp，以及可选 iteration 和 session_id。 |
| [`AsyncEventStream`](#bumblehive.observability.AsyncEventStream) | 单次消费的异步事件流。 |
| [`EventRecorder`](#bumblehive.observability.EventRecorder) | 在内存中记录事件，并按 kind 查询。 |

## 事件与流

包含 kind、run_id、payload、timestamp，以及可选 iteration 和 session_id。

::: bumblehive.observability.AgentEvent
    options:
      heading_level: 3
      show_root_heading: true
      show_root_full_path: false

单次消费的异步事件流。消费结束后调用 result()；提前关闭使用 aclose()。

::: bumblehive.observability.AsyncEventStream
    options:
      heading_level: 3
      show_root_heading: true
      show_root_full_path: false


## 监听与记录

监听事件的协议，实现 on_event()。

::: bumblehive.observability.AgentHook
    options:
      heading_level: 3
      show_root_heading: true
      show_root_full_path: false

把事件回调包装为 Hook。

::: bumblehive.observability.CallbackHook
    options:
      heading_level: 3
      show_root_heading: true
      show_root_full_path: false

在内存中记录事件，并按 kind 查询。

::: bumblehive.observability.EventRecorder
    options:
      heading_level: 3
      show_root_heading: true
      show_root_full_path: false

事件回调函数类型。

::: bumblehive.observability.EventCallback
    options:
      heading_level: 3
      show_root_heading: true
      show_root_full_path: false

运行入口接受的 Hook 输入类型。

::: bumblehive.observability.HookInput
    options:
      heading_level: 3
      show_root_heading: true
      show_root_full_path: false


## 事件常量

按 `kind` 区分事件；不要假设不同事件的 `payload` 结构一致。工具开始、审批与结束通过调用 ID 关联。

::: bumblehive.observability.DEFAULT_STREAM_QUEUE_SIZE
    options:
      heading_level: 4
      show_root_heading: true
      show_root_full_path: false

::: bumblehive.observability.FINAL_RESULT
    options:
      heading_level: 4
      show_root_heading: true
      show_root_full_path: false

::: bumblehive.observability.ITERATION_FINISHED
    options:
      heading_level: 4
      show_root_heading: true
      show_root_full_path: false

::: bumblehive.observability.ITERATION_STARTED
    options:
      heading_level: 4
      show_root_heading: true
      show_root_full_path: false

::: bumblehive.observability.MODEL_REQUEST_STARTED
    options:
      heading_level: 4
      show_root_heading: true
      show_root_full_path: false

::: bumblehive.observability.MODEL_RESPONSE_FINISHED
    options:
      heading_level: 4
      show_root_heading: true
      show_root_full_path: false

::: bumblehive.observability.MODEL_STREAM_CONTENT_DELTA
    options:
      heading_level: 4
      show_root_heading: true
      show_root_full_path: false

::: bumblehive.observability.MODEL_STREAM_REFUSAL_DELTA
    options:
      heading_level: 4
      show_root_heading: true
      show_root_full_path: false

::: bumblehive.observability.MODEL_STREAM_REASONING_DELTA
    options:
      heading_level: 4
      show_root_heading: true
      show_root_full_path: false

::: bumblehive.observability.MODEL_STREAM_RECOVERED
    options:
      heading_level: 4
      show_root_heading: true
      show_root_full_path: false

::: bumblehive.observability.MODEL_STREAM_TOOL_CALL_DELTA
    options:
      heading_level: 4
      show_root_heading: true
      show_root_full_path: false

::: bumblehive.observability.RUN_ERROR
    options:
      heading_level: 4
      show_root_heading: true
      show_root_full_path: false

::: bumblehive.observability.RUN_FINISHED
    options:
      heading_level: 4
      show_root_heading: true
      show_root_full_path: false

::: bumblehive.observability.RUN_STARTED
    options:
      heading_level: 4
      show_root_heading: true
      show_root_full_path: false

::: bumblehive.observability.TOOL_APPROVAL_FINISHED
    options:
      heading_level: 4
      show_root_heading: true
      show_root_full_path: false

::: bumblehive.observability.TOOL_APPROVAL_STARTED
    options:
      heading_level: 4
      show_root_heading: true
      show_root_full_path: false

::: bumblehive.observability.TOOL_CALL_FINISHED
    options:
      heading_level: 4
      show_root_heading: true
      show_root_full_path: false

::: bumblehive.observability.TOOL_CALL_STARTED
    options:
      heading_level: 4
      show_root_heading: true
      show_root_full_path: false

::: bumblehive.observability.TOOL_CALLS_FINISHED
    options:
      heading_level: 4
      show_root_heading: true
      show_root_full_path: false

::: bumblehive.observability.TOOL_CALLS_STARTED
    options:
      heading_level: 4
      show_root_heading: true
      show_root_full_path: false

::: bumblehive.observability.TURN_CONTEXT_BUILT
    options:
      heading_level: 4
      show_root_heading: true
      show_root_full_path: false

::: bumblehive.observability.TURN_ERROR
    options:
      heading_level: 4
      show_root_heading: true
      show_root_full_path: false

::: bumblehive.observability.TURN_FINISHED
    options:
      heading_level: 4
      show_root_heading: true
      show_root_full_path: false

::: bumblehive.observability.TURN_STARTED
    options:
      heading_level: 4
      show_root_heading: true
      show_root_full_path: false
