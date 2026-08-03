# 注册第一个 Python 工具

本页将把普通 Python 函数注册为工具，让 Agent 查询课程信息。

预计时间：10 分钟。

## 前置条件

- 已经完成[运行第一个 Agent](first-call.md)
- 当前终端仍然设置了模型相关环境变量

## 1. 编写代码

新建 `first_tool.py`，写入：

```python
--8<-- "examples/runtime/custom_tool.py"
```

## 2. 运行

```bash
python first_tool.py
```

预期输出类似：

```text
工具：get_course_info
回答：Python 入门课在周一 10:00，于教学楼 A101 上课。
```

回答的具体文字可能不同，但“工具”一行应该包含 `get_course_info`。

## 工具是什么？

模型本身不知道你项目中的实时数据。工具可以理解为你提供给模型的“可调用函数”。

这个示例的过程是：

```text
用户询问课程 → 模型选择 get_course_info → Runtime 执行函数 → 模型根据结果回答
```

## 代码说明

- `@runtime.tools.tool(...)` 把下面的 Python 函数注册为工具。
- `name` 指定模型看到的工具名称。
- 参数类型 `course: str` 会帮助 Bumblehive 生成工具参数说明。
- `description` 告诉模型这个工具能做什么。
- `tool_names=["get_course_info"]` 表示只向模型开放这个工具。
- `result.tools_used` 记录本次成功执行过的工具名称。

工具可以是同步函数，也可以使用 `async def` 定义异步函数。

!!! warning "工具会执行真实代码"
    只注册当前 Agent 确实需要的工具。自定义工具如果可以访问文件、数据库或网络，应在函数内部做好权限和参数检查。

## 常见问题

### Agent 没有调用工具

确认 `agent_instructions` 明确要求先调用工具，并检查 `tool_names` 中的名称与装饰器中的 `name` 完全一致。

### 提示 Unknown tools

工具必须在调用 `runtime.run()` 之前通过 `@runtime.tools.tool(...)` 注册，并且名称必须出现在 `tool_names` 中。

### 工具收到了错误参数

为函数参数添加准确的 Python 类型，并让 `description` 清楚说明输入要求。Bumblehive 会在执行前校验参数。

## 下一步

[选择接下来的学习路径](next-steps.md)。
