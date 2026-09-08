# Hooks 与运行记录

Hook 接收结构化运行事件，可用于调试、日志、工具成败检查和测试。审批决定通过 approval_handler 返回。

## 记录一次运行

完成[模型配置](../getting-started/installation.md#configure-model)，从仓库根目录执行 `python examples/observability/hooks.py`：

```python title="examples/observability/hooks.py"
--8<-- "examples/observability/hooks.py"
```

终端会显示选定事件、最终回答和记录数量。示例通过 `hooks=[callback, recorder]` 同时调用回调并保留事件。

## 检查工具成败

以下片段在已创建的 `runtime` 中运行：

```python
from bumblehive import EventRecorder
from bumblehive.observability import TOOL_CALL_FINISHED

recorder = EventRecorder()
result = await runtime.run("检查项目", hooks=recorder)
for event in recorder.by_kind(TOOL_CALL_FINISHED):
    if not event.payload["ok"]:
        print(event.payload["error"])
print("Token 用量：", result.usage)
```

工具失败时，模型仍可能继续并得到最终结果。`result.tools_used` 只统计成功执行的工具；完整过程需要检查事件。

## 关联运行与调用

| 字段 | 用途 |
| --- | --- |
| `run_id` | 关联一次运行产生的事件 |
| `session_id` | 关联持久化会话，独立调用可能没有 |
| `iteration` | 区分模型与工具循环轮次 |
| `payload` | 当前事件的数据，各类事件结构不同 |

`EventRecorder` 在内存中记录事件；持久日志、脱敏、保存周期和展示由应用实现。事件可能包含用户输入和工具内容，写入外部日志前按业务要求处理。

[事件与 Hooks API](../reference/observability.md) · [流式输出](streaming.md) · [工具审批](../concepts/tool-safety.md)
