# 引导与纠偏

用户在 Agent 工作期间补充要求，例如“改用中文回答”，可以通过 `steer()` 交给当前任务，不必重新开始。

## 运行中补充要求

下面的例子在 Agent 开始查询课程时追加要求，模拟应用收到用户输入。

完成[模型配置](../getting-started/installation.md#configure-model)，运行 `python examples/runtime/steering_run.py`：

```python
--8<-- "examples/runtime/steering_run.py"
```

- `run = runtime.run(...)` 保存本次运行对象。
- `run.steer(...)` 把新要求送入当前运行。
- 例子用工具开始事件触发输入，便于直接观察效果；实际应用可以在用户提交消息时调用同一方法。

## 运行效果 { #steering-rules }

```text
模型开始调用工具，追加引导。
工具结果：Python 入门：周一 10:00，教学楼 A101。
最终回答：…改用中文回答课程时间和地点…
```

追加要求不会中断正在执行的模型请求或工具。它会在下一次请求模型前加入对话；工具调用期间收到的要求会放在这批工具结果之后。

## 接入用户输入

在已经创建的 `runtime` 中，可以让任务运行的同时接收界面消息：

```python
run = runtime.run("分析项目")
task = asyncio.create_task(run)

# 接到用户输入后，在同一事件循环中调用：
run.steer("重点看安装和启动步骤。")

result = await task
```

流式输出使用 `stream.steer(text)`，用法相同，见[流式引导示例](https://github.com/wxhcore/bumblehive/blob/main/examples/runtime/steering_stream.py)。

运行已经结束时，`steer()` 会抛出 `RuntimeError`。这时用同一份[会话历史](memory-and-sessions.md)开始下一轮。[后台工具](background-tools.md)提供了完整的结果回传示例；运行对象的细节见 [API 参考](../reference/runtime.md)。
