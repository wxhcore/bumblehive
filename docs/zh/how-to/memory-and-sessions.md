# 保存多轮对话

临时对话使用 `MessageHistory`；需要重启后继续时使用 `session_id`。

## 使用内存历史

```python
import asyncio
import os

import bumblehive


async def main() -> None:
    config = bumblehive.RuntimeArguments(
        model=os.environ["BUMBLEHIVE_MODEL"],
        api_key=os.environ["BUMBLEHIVE_API_KEY"],
        base_url=os.environ["BUMBLEHIVE_BASE_URL"],
        tool_names=[],
    )
    history = bumblehive.MessageHistory()

    async with bumblehive.from_config(config) as runtime:
        await runtime.run("记住：我的项目叫 Bumblehive", history=history)
        result = await runtime.run("我的项目叫什么？", history=history)

    print(result.final_content)


asyncio.run(main())
```

可以查看或清空历史：

```python
messages = history.get_history()
history.clear()
```

`get_history()` 返回消息副本，修改它不会直接改变原历史。

## 使用持久化会话

```python
async with bumblehive.from_config(config) as runtime:
    await runtime.run(
        "记住：我的课程是操作系统",
        session_id="user-42:course-helper",
    )
    result = await runtime.run(
        "我的课程是什么？",
        session_id="user-42:course-helper",
    )
```

会话默认保存在 `~/.bumblehive/sessions/`。创建新的 Runtime 后，使用同一个 `session_id` 仍能继续对话。

`session_id` 必须是非空字符串。建议由业务身份和对话标识组成，例如：

```text
user-42:course-helper
team-7:project-18
```

## 删除会话

```python
deleted = await runtime.delete_session("user-42:course-helper")
```

删除后，再使用相同 ID 会开始一段新对话。

## 选择建议

| 需求 | 选择 |
| --- | --- |
| 单个脚本中的临时多轮对话 | `MessageHistory` |
| 测试中明确检查消息 | `MessageHistory` |
| 应用重启后继续 | `session_id` |
| 同一用户的多个独立对话 | 不同 `session_id` |
| 每次都是独立任务 | 两者都不传 |

## 重要限制

- `history` 与 `session_id` 不能同时传入；
- 同一个 `MessageHistory` 不要并发使用；
- 同一 Runtime 会串行处理相同 `session_id`；
- 不要让多个 Runtime 或进程同时写同一个 `session_id`；
- 持久化会话是本地 JSON，不是加密数据库。

更多原理见[状态与并发](../concepts/state-and-concurrency.md)。
