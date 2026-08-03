# 处理运行错误

Bumblehive 的失败分为两类：返回结构化错误，以及直接抛出异常。项目代码需要同时处理。

## 先检查 `AgentRunResult`

模型请求失败或达到最大迭代次数时，通常仍会返回 `AgentRunResult`：

```python
result = await runtime.run("分析这个项目")

if result.error is not None:
    print("错误代码：", result.error.code)
    print("错误信息：", result.error.message)
    print("是否可恢复：", result.error.recoverable)
else:
    print(result.final_content)
```

当前常见的 `stop_reason`：

| 值 | 含义 |
| --- | --- |
| `completed` | 正常完成 |
| `model_error` | Provider 返回模型错误 |
| `max_iterations` | 达到工具循环上限 |

Provider 会在返回可恢复错误前自动重试。默认最多重试 3 次。

## 再处理直接异常

配置错误、MCP 连接失败、状态参数冲突等问题会直接抛出异常：

```python
try:
    async with bumblehive.from_config(config) as runtime:
        result = await runtime.run("你好")
except (TypeError, ValueError) as exc:
    print("配置或参数错误：", exc)
except Exception as exc:
    print("运行失败：", exc)
else:
    if result.error:
        print(result.error.code, result.error.message)
    else:
        print(result.final_content)
```

库代码通常应记录异常后继续向上抛出，而不是统一转换成空字符串。

## 工具失败不一定是整个运行失败

工具不存在、参数不合法或工具函数抛出异常时，错误会作为工具结果交给模型。模型可能改正参数或换一种方法继续回答。

因此可能出现：

```text
result.error is None
但某个工具执行失败
```

`result.tools_used` 只记录成功执行的工具。需要检查单个工具失败时，可以使用事件 Hook：

```python
from bumblehive import EventRecorder
from bumblehive.observability import TOOL_CALL_FINISHED


recorder = EventRecorder()
result = await runtime.run("执行任务", hooks=recorder)

for event in recorder.by_kind(TOOL_CALL_FINISHED):
    if not event.payload["ok"]:
        print(event.payload["error"])
```

## 不要忽略资源清理

使用 `async with` 关闭 Runtime。流式调用提前停止时，调用 `await stream.aclose()`。

对于持久化会话，不要在捕获异常后直接重复提交同一条消息。先确认业务是否允许重复执行工具，再决定是否重试。

遇到具体问题时，查看[故障排查](../troubleshooting.md)。
