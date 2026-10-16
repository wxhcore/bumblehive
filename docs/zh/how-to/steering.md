# 运行期间追加指令

通过 `steer()` 补充或纠正当前任务。指令先进入本次运行的队列，在下一轮请求模型前加入对话；当前模型响应和工具执行会继续完成。

## 基本用法

在已创建的 `runtime` 中，保存运行对象，将下面的回调接到应用的用户输入事件：

```python
import asyncio

run = runtime.run("修改登录页面")

def on_user_input(text: str) -> None:
    run.steer(text)

task = asyncio.create_task(run)
result = await task
```

例如，用户在运行中输入“背景改成蓝色”，应用调用 `on_user_input("背景改成蓝色")`。SDK 不会自动注册回调或接收界面消息。

`steer()` 是同步方法，返回表示输入已入队，不表示模型已经处理。它接收与原始输入相同的 `UserMessage`：字符串或只含一条 user 消息的列表，入队时会校验并复制消息。

回调须在运行所属的 asyncio 事件循环中执行，可以连续提交多条指令。

上例使用 Task 在后台运行，也支持直接 `result = await run`。取消与清理方式见[运行对象的生命周期](../concepts/runtime-lifecycle.md#run-lifecycle)。

## 流式输出与控制台

使用 `stream()` 时，同样保存运行对象，通过 `steer()` 追加输入：

```python
stream = runtime.stream("修改登录页面")

def on_user_input(text: str) -> None:
    stream.steer(text)

try:
    async for event in stream:
        ...  # 展示事件。
    result = await stream.result()
finally:
    await stream.aclose()
```

将回调接到应用的输入事件后，首次迭代启动运行。事件展示方式见[流式输出](streaming.md)。

需要控制台自动展示时，将基本用法中的 `runtime.run(...)` 换成 `runtime.run_console(...)`，其余代码相同。

<span id="steering-rules"></span>

## 指令何时生效

每轮请求模型前，一次取出所有待处理指令，按顺序追加到对话末尾：

| 提交时机或运行状态 | 行为 |
| --- | --- |
| 运行启动前 | 随首次模型请求发送 |
| 模型请求、重试、审批或工具执行中 | 当前操作继续完成，指令留待下一轮处理 |
| 模型响应包含工具调用 | 等整批工具执行完成，追加在工具结果之后 |
| 模型响应为普通回答 | 有待处理指令则追加在回答之后，继续请求模型；否则结束运行 |
| 输入入口已关闭 | `steer()` 抛出 `RuntimeError` |

例如，在工具调用期间提交指令，后续对话顺序为：

```text
assistant（tool_calls）→ tool（整批工具结果）→ user（追加指令）
```

`FINAL_RESULT` 表示整次运行的最终结果，不是每轮模型响应。引导仍受上下文预算和 `max_iterations` 限制；错误、取消和迭代上限仍会终止运行。

## 运行结束与剩余输入

流式输出可能仍在展示缓冲事件，而后台运行已经结束。应用应处理 `steer()` 的 `RuntimeError`，再决定是否把用户输入作为下一次运行的新消息。

输入关闭后，可以取回尚未被消费的指令：

```python
pending = run.take_pending()  # stream.take_pending() 用法相同。
```

此操作会清空待处理队列；关闭前调用会抛出 `RuntimeError`。待处理输入只保存在内存中，已加入对话的消息不会因后续保存或请求失败而退回队列。

每次运行独立持有输入队列，等待同一 Session 的前一次运行完成时也可提交引导。会话并发规则见[会话与历史](memory-and-sessions.md)。

## 可运行示例

配置[模型环境变量](../getting-started/installation.md#configure-model)后，从仓库根目录运行对应脚本：

| 示例 | 展示内容 |
| --- | --- |
| [steering_run.py](https://github.com/wxhcore/bumblehive/blob/main/examples/runtime/steering_run.py) | 模型开始调用课程查询工具时追加指令，工具完成后改用中文回答 |
| [steering_stream.py](https://github.com/wxhcore/bumblehive/blob/main/examples/runtime/steering_stream.py) | 启动前追加指令，逐段展示模型输出 |
| [steering_console.py](https://github.com/wxhcore/bumblehive/blob/main/examples/runtime/steering_console.py) | 启动前追加指令，由控制台自动展示输出 |

例如：`python examples/runtime/steering_run.py`。

[Runtime API](../reference/runtime.md) · [流式输出](streaming.md) · [会话与历史](memory-and-sessions.md)
