# 状态与并发

Bumblehive 支持无状态、内存历史和持久化会话三种对话方式。

## 选择一种状态方式

| 调用方式 | 是否记住上一轮 | 是否写入磁盘 | 适合场景 |
| --- | --- | --- | --- |
| 不传任何参数 | 否 | 否 | 独立任务、批处理 |
| `history=MessageHistory()` | 手动更新后 | 否 | 单进程临时对话 |
| `session_id="user:42"` | 是 | 是 | 需要重启后继续的对话 |

不传 `history` 或 `session_id` 时，每次调用都是独立的：

```python
await runtime.run("记住数字 7")
result = await runtime.run("刚才的数字是什么？")
```

第二次调用不会自动看到第一次的内容。

## `MessageHistory` 的所有者是调用者

Runtime 只读取你传入的对象，不会自动修改它。需要继续对话时，调用方手动更新历史：

```python
history = bumblehive.MessageHistory()

first = await runtime.run("记住数字 7", history=history)
history.replace_run_messages(first.messages)

result = await runtime.run("刚才的数字是什么？", history=history)
```

`replace_run_messages()` 会去掉每轮运行产生的 system message 和 runtime context。是否保存正常结果、`model_error` 或 `max_iterations` 结果，由调用方决定。

> 不要让两个并发任务共享同一个 `MessageHistory`。并发对话应各自创建历史对象。

## `session_id` 由 Runtime 管理

相同 `session_id` 会读取同一份持久化历史。默认文件保存在 `~/.bumblehive/sessions/`。

同一个 Runtime 内：

- 相同 `session_id` 的调用会依次执行；
- 不同 `session_id` 可以并发执行；
- 中断的会话会在下一轮开始前修复消息边界。

锁只存在于当前 Runtime 的 Session Manager 中。不要让多个 Runtime 或多个进程同时写入同一个 `session_id`。

## 两者不能同时使用

下面的调用会抛出 `ValueError`：

```python
await runtime.run(
    "你好",
    history=history,
    session_id="demo",
)
```

原因是 Bumblehive 无法判断应该以哪份历史为准。

## 删除持久化会话

```python
deleted = await runtime.delete_session("user:42")
```

返回 `True` 表示删除了磁盘文件或缓存状态；不存在时返回 `False`。

会话内容以本地 JSON 保存，并非加密存储。不要保存不必要的敏感信息。

下一步：阅读[保存多轮对话](../how-to/memory-and-sessions.md)。
