# 多轮对话与记忆

让 Agent 记住上一轮内容，只需在连续调用中使用同一个 `session_id`。不传会话或历史时，每次调用独立。

## 记住项目名称

完成[模型配置](../getting-started/installation.md#configure-model)，运行 `python examples/runtime/sessions.py`：

```python
--8<-- "examples/runtime/sessions.py"
```

两次调用使用同一个 ID。第二次回答应包含 `BumbleHive`，因为 SDK 会读取第一轮的对话。

会话默认保存在 `~/.bumblehive/sessions/`。程序重启后仍可使用相同 ID 继续；换一个 ID 就是另一段对话。

## 只在内存中保存

临时对话可以使用 `MessageHistory`。运行 `python examples/runtime/conversation_history.py`：

```python
--8<-- "examples/runtime/conversation_history.py"
```

与 `session_id` 不同，Runtime 不会自动修改这个对象。每轮用 `history.replace_run_messages(result.messages)` 更新后，下一轮才能看到新内容。该方法会去除运行生成的系统上下文。

## 清空对话

```python
history.clear()  # 清空内存历史。
await runtime.delete_session("hello-agent")  # 删除持久化会话。
```

一次调用只选择 `history` 或 `session_id` 其中一种。并发使用约束见[消息与会话参考](../reference/protocols.md)。
