# 引导与纠偏

用户在 Agent 工作期间补充要求，例如“改用中文回答”，可以通过 `steer()` 交给当前任务，不必重新开始。

## 追加要求

下面的两条要求都会在第一次模型请求前送达，因为这时还没有 `await run`：

```python
run = runtime.run("用英文解释 Agent Loop。")
run.steer("改用中文，只说两句话。")
result = await run
print(result.final_content)
```

## 运行中追加要求 { #steering-rules }

完成[模型配置](../getting-started/installation.md#configure-model)后，运行 `python examples/runtime/steering_run.py`。这个脚本在工具开始执行时调用 `run.steer()`，可以观察新要求何时生效。

??? example "查看完整可运行脚本"

    ```python title="examples/runtime/steering_run.py"
    --8<-- "examples/runtime/steering_run.py"
    ```

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
