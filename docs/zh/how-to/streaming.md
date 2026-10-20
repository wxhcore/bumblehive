# 流式输出

希望用户在回答完成前就看到内容时，使用 `runtime.stream()` 逐段接收模型输出。

## 逐段打印回答

完成[模型配置](../getting-started/installation.md#configure-model)，运行 `python examples/runtime/streaming.py`：

```python
--8<-- "examples/runtime/streaming.py"
```

`MODEL_STREAM_CONTENT_DELTA` 事件中的 `delta` 是新增文本。程序边接收边打印，最终组成一段回答；具体分块由模型服务决定。

完整消费事件后，`await stream.result()` 返回最终结果。`finally` 中关闭事件流，使提前退出时也能清理运行。

## 显示工具进度

在事件循环中增加两个分支，就能显示工具执行状态：

```python
from bumblehive.observability import TOOL_CALL_STARTED, TOOL_CALL_FINISHED

# 放入 async for event in stream 循环：
if event.kind == TOOL_CALL_STARTED:
    print("开始：", event.payload["tool_call"]["name"])
elif event.kind == TOOL_CALL_FINISHED:
    print("完成：", event.payload["ok"])
```

工具进度与最终回答是不同事件。接入界面的完整映射见[聊天助手](../examples/chat-interface.md#ui)。事件字段全集见[事件参考](../reference/observability.md)。

## 只需要终端显示

`run_console()` 已封装终端展示。在已有的 `runtime` 中可以直接使用：

```python
result = await runtime.run_console("用三句话解释 Agent Loop。")
```

运行期间追加要求使用 `stream.steer(text)`，见[引导与纠偏](steering.md)。提前停止使用 `await stream.aclose()`；停止后不能再读取最终结果。
