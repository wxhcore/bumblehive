# Runtime 与推荐入口

普通项目优先使用 `BumblehiveRuntime`。它负责组合模型、工具、Skills、历史和 Agent Loop。

## 常用入口

| 接口 | 用途 |
| --- | --- |
| `RuntimeArguments` | 用一组扁平参数创建 Runtime |
| `from_config()` | 根据参数、字典或配置对象创建 Runtime |
| `BumblehiveRuntime.run()` | 运行一次对话 |
| `BumblehiveRuntime.stream()` | 流式接收运行事件 |
| `MessageHistory` | 保存调用者管理的内存历史 |
| `AgentRunResult` | 获取回答、工具、用量和错误 |

推荐使用：

```python
async with bumblehive.from_config(config) as runtime:
    result = await runtime.run("你好", history=history)
    history.replace_run_messages(result.messages)
```

Runtime 只读取 `history`，不会自动修改它；`session_id` 则由 Runtime 自动持久化。

不要同时传入 `history` 和 `session_id`。

## `BumblehiveRuntime`

::: bumblehive.BumblehiveRuntime
    options:
      show_root_heading: false
      show_root_full_path: false

## `from_config()`

::: bumblehive.from_config
    options:
      show_root_heading: false
      show_root_full_path: false
