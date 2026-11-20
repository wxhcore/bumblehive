# 工具调用

把 Python 函数注册为工具，让 Agent 查询业务数据或执行具体操作。SDK 根据函数参数类型生成工具定义，并在执行前校验参数。

## 注册 Python 函数

先完成[模型配置](installation.md#configure-model)。以下完整示例使用本地课程表：

```python title="examples/runtime/custom_tool.py"
--8<-- "examples/runtime/custom_tool.py"
```

把上面的代码保存为 `course.py`，在配置过模型的终端运行 `python course.py`。输出类似：

```text
工具： ['get_course_info']
Python 入门课在周一 10:00，于教学楼 A101 上课。
```

`@runtime.tools.tool` 默认用函数名注册工具。`course: str` 定义输入，`description` 告诉模型何时查询，函数返回的时间和地点供模型组织回答。需要访问网络或数据库时，工具也可以写成 `async def`。

## 选择可用工具 { #tool-selection }

示例通过 `tool_names=["get_course_info"]` 只开放课程查询工具。省略、空列表和指定列表的完整区别见[能力选择](../how-to/configuration.md#capability-lists)。工具必须在调用 `run()` 前注册。

工具可用不代表模型必定调用；任务应明确需要该工具，模型也要支持 Tool Calling。

## 等待还是后台执行

普通工具会等待函数完成后把结果交给模型。`async def` 也遵循这个规则。如果希望 Agent 在工具工作期间继续其他任务，见[等待结果与后台执行](../how-to/background-tools.md)。

## 处理工具失败

参数错误或工具异常会作为工具结果交回模型，它可以修改参数或继续处理。因此某个工具失败，并不意味着最终 `result.error` 一定非空。

`result.tools_used` 只记录成功执行的工具。检查单次调用的成败，使用[工具事件与 Hooks](../how-to/hooks.md)。需要用户确认时传入[审批处理器](../concepts/tool-safety.md)。

## 相关接口

[ToolManager、Tool 与 CallableTool](../reference/tools.md) · [文件与命令](../how-to/files-and-commands.md) · [MCP](../how-to/mcp.md)
