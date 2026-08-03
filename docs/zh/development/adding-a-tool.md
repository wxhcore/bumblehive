# 增加一个工具

工具让模型能够调用你的 Python 代码。

## 推荐方式

```python
@runtime.tools.tool(
    name="get_weather",
    description="查询指定城市未来几天的天气。",
)
def get_weather(city: str, days: int = 1) -> str:
    return f"{city}: sunny for {days} day(s)"
```

`name` 指定工具名称，`description` 告诉模型工具的用途。Bumblehive 会根据类型注解生成参数结构。

确保 Runtime 只暴露需要的工具：

```python
RuntimeArguments(
    ...,
    tool_names=["get_weather"],
)
```

## 同步与异步工具

同步函数会在线程中运行。需要访问异步 API 时，可以直接定义异步工具：

```python
@runtime.tools.tool(
    name="fetch_course",
    description="查询一门课程。",
)
async def fetch_course(course_id: str) -> dict[str, str]:
    return {"id": course_id, "status": "open"}
```

## 并行安全

工具默认不会假设可以并行执行。只有在函数没有共享可变状态时，才设置 `parallel_safe=True`。

例如，纯计算通常可以并行；修改同一个文件或数据库记录通常不应该并行。

## 安全边界

自定义工具就是普通 Python 代码。它可以访问进程拥有的文件、网络和环境变量。

因此应当：

- 只暴露当前任务需要的工具。
- 在工具内部校验路径和参数。
- 不把密钥返回给模型。
- 为有副作用的操作编写测试。

下一步：阅读[工具 API](../reference/tools.md)。
