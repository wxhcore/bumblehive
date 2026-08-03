# 使用流式输出

`runtime.stream()` 会在 Agent 运行时持续返回结构化事件，适合终端输出、聊天界面和运行日志。

## 输出模型文本

```python
import asyncio
import os

import bumblehive
from bumblehive.observability import MODEL_STREAM_CONTENT_DELTA


async def main() -> None:
    config = bumblehive.RuntimeArguments(
        model=os.environ["BUMBLEHIVE_MODEL"],
        api_key=os.environ["BUMBLEHIVE_API_KEY"],
        base_url=os.environ["BUMBLEHIVE_BASE_URL"],
        tool_names=[],
    )

    async with bumblehive.from_config(config) as runtime:
        stream = runtime.stream("用三句话解释 Agent Loop")

        async for event in stream:
            if event.kind == MODEL_STREAM_CONTENT_DELTA:
                print(event.payload["delta"], end="", flush=True)

        result = await stream.result()

    print()
    if result.error:
        print("运行失败：", result.error.message)


asyncio.run(main())
```

## 为什么最后还要调用 `result()`

事件流用于展示过程，`AgentRunResult` 才是完整结果。它包含最终文本、工具使用情况、token 用量和错误。

必须先把事件消费完，再读取结果：

```python
async for event in stream:
    ...

result = await stream.result()
```

提前调用 `result()` 会抛出 `RuntimeError`。

## 常用事件

| 事件 | 用途 |
| --- | --- |
| `MODEL_STREAM_CONTENT_DELTA` | 普通回答增量 |
| `MODEL_STREAM_REASONING_DELTA` | Provider 提供的推理增量 |
| `MODEL_STREAM_TOOL_CALL_DELTA` | 工具调用参数增量 |
| `TOOL_CALL_STARTED` | 一个工具开始执行 |
| `TOOL_CALL_FINISHED` | 一个工具执行结束 |
| `FINAL_RESULT` | 完整结果已经生成 |

每个 `AgentEvent` 都包含 `kind`、`run_id`、`payload`、`timestamp`，还可能包含 `iteration` 和 `session_id`。

## 提前停止

```python
await stream.aclose()
```

提前关闭会取消后台任务，因此之后不能取得最终结果。一个 Stream 也只能消费一次。

## 只需要终端显示

`run_console()` 会处理事件并返回同一个 `AgentRunResult`：

```python
result = await runtime.run_console("解释当前项目")
```

下一步：阅读[处理运行错误](error-handling.md)。
