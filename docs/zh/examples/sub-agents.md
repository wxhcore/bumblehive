# 子 Agent 与任务委派

把子 Agent 包装成一个 Python 工具，让主 Agent 将独立任务交出去，再使用返回结果继续工作。这是 Runtime 与工具的组合，不需要额外的调度 API。

## 运行示例

完成[模型配置](../getting-started/installation.md#configure-model)，在要分析的项目目录中运行示例；代码的 `workspace="."` 指向启动目录：

```bash
python examples/runtime/multi_agent.py
```

```python title="examples/runtime/multi_agent.py"
--8<-- "examples/runtime/multi_agent.py"
```

主 Agent 只看到 `sub_agent` 工具。子调用只开放读取和搜索工具，工具描述中不包含自身，因此不能通过该工具继续递归委派。

## 隔离上下文与权限

子调用没有传入 `history` 或 `session_id`，所以使用独立的消息历史。它仍复用 Runtime 的基础配置与资源；业务指令、Skills 和工作区不会自动全部隔离，需要时在子调用中明确选择或创建独立 Runtime。

`approval_handler` 只作用于当前调用。子 Agent 若开放了写入或命令工具，应用也应为子调用传入审批处理器。

## 返回结果与错误

主 Agent 会把子工具的返回文本当作工具结果使用。示例已检查子运行的结构化错误，并将失败交回主 Agent；最终结果还应通过工具事件确认是否真的发生过委派。

该方式不自动提供任务队列、进度聚合、跨进程调度或工作区隔离。需要并发多个任务时，应用应管理各自的上下文、资源范围与取消行为。

[工具调用](../getting-started/first-tool.md) · [会话与历史](../how-to/memory-and-sessions.md) · [Runtime API](../reference/runtime.md)
