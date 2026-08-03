# Runtime 生命周期

一个 Runtime 应在一组相关任务中复用，并在最后明确关闭。

## 推荐写法

使用 `async with` 最安全：

```python
async with bumblehive.from_config(config) as runtime:
    first = await runtime.run("第一个问题")
    second = await runtime.run("第二个问题")
```

进入上下文时，Runtime 会：

1. 注册内置工具；
2. 连接配置中的 MCP Server；
3. 注册允许使用的 MCP 工具。

退出上下文时，Runtime 会关闭：

- MCP 连接；
- 尚未结束的内置命令执行会话；
- 已创建的 Provider 客户端。

## 不使用 `async with`

也可以手动管理生命周期。先初始化工具，并始终在 `finally` 中关闭 Runtime：

```python
runtime = bumblehive.from_config(config)

try:
    await runtime.initialize_tools()
    result = await runtime.run("你好")
finally:
    await runtime.close()
```

`run()` 和 `stream()` 会自动初始化工具。只有在第一次运行前就要查看或使用已注册工具时，才需要显式调用 `initialize_tools()`。

## Runtime 应该创建几次

推荐按应用或任务作用域创建，而不是每次提问都重新创建：

```text
应用启动 → 创建 Runtime → 多次 run/stream → close → 应用结束
```

这样可以复用 Provider 和 MCP 连接。Runtime 关闭后不要继续使用，应创建新的实例。

## 流式调用的关闭顺序

应先消费完事件并取得结果，再离开 Runtime 上下文：

```python
async with bumblehive.from_config(config) as runtime:
    stream = runtime.stream("请简要回答")

    async for event in stream:
        ...

    result = await stream.result()
```

如果要提前停止，调用 `await stream.aclose()`。提前关闭的流不会产生可读取的最终结果。

下一步：阅读[状态与并发](state-and-concurrency.md)。
