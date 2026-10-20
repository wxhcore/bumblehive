# 工具的等待与后台执行

生成报告或委派子任务时，工具可能需要一段时间才能完成。如果 Agent 还有独立工作，可以让工具先返回“处理中”，完成后再把结果交给 Agent。

`async def` 只表示 Python 异步函数，不会自动让 Agent 越过工具继续。下面用 SDK 的工具注册、`steer()` 和对话历史组合实现后台执行。

## 选择等待方式

| 方式 | 适合什么情况 | 示例辅助代码的参数 |
| --- | --- | --- |
| 等待完成 | 下一步必须依赖结果 | `wait_seconds=None` |
| 直接后台执行 | 可以先做其他工作 | `wait_seconds=0` |
| 等待一段时间后转后台 | 希望尽快取得结果，又不想一直等待 | `wait_seconds=5` |

这些参数属于下面的示例辅助代码，不是 SDK 内置配置。超时只结束本次等待，原任务继续运行。

## 生成一份后台报告

完成[模型配置](../getting-started/installation.md#configure-model)，从仓库根目录运行：

```bash
python -m examples.runtime.background_tools
```

示例包含两部分：本页的工具代码，以及共用的 `examples/runtime/background_support.py`。从仓库运行时无需额外安装辅助包。

```python
--8<-- "examples/runtime/background_tools.py"
```

`make_report` 用三秒延迟模拟计算。`background=True` 时立即返回 `pending` 和任务标识；`False` 时直接等待报告结果。

运行过程类似：

```text
调用 make_report → 工具返回 pending
Agent 先说明报告的用途
后台计算完成 → 发送包含任务标识的结果
Agent 总结：12 笔订单，总金额 360
```

如果报告很快完成，结果也可能在主 Agent 给出首次回答前到达。

## 设置等待时间

将工具中的 `submit()` 改为：

```python
return await jobs.submit(work(), wait_seconds=1)
```

三秒任务超过一秒等待，会返回 `pending`。改为 `5` 则直接返回报告。关键实现只有：

```python
task = asyncio.ensure_future(work)
done, _ = await asyncio.wait({task}, timeout=wait_seconds)
if done:
    return task.result()
# task 仍在运行，登记完成后的投递，再返回 pending。
```

这里使用 `asyncio.wait()`，超时不会取消 `task`。工具只返回一次；晚到结果通过新消息送达，不会修改之前的工具结果。

## 结果如何回到 Agent { #delivery }

共用辅助代码做两件事：

- `BackgroundTools` 管理等待及完成通知，失败也会作为结果通知。
- `Conversation` 在运行中调用 `steer()`；本轮结束后则更新历史，收到晚到结果再开始下一轮。

??? example "查看完整辅助代码"

    ```python
    --8<-- "examples/runtime/background_support.py"
    ```

应用需要保持运行才能接收结果。本例等待所有后台任务完成后退出，任务保存在当前进程中，不提供重启恢复。

同一机制可以用于[子 Agent 协作](../examples/sub-agents.md)和[主动追问](ask-user.md)。工具描述应明确告诉模型：`pending` 不是最终答案，不要重复发起同一任务；还有独立工作就继续，必须依赖结果时就等待后续消息。
