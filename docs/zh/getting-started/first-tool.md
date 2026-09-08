# 工具调用

把 Python 函数注册为工具，让 Agent 查询业务数据或执行具体操作。SDK 根据函数参数类型生成工具定义，并在执行前校验参数。

## 注册 Python 函数

先完成[模型配置](installation.md#configure-model)。以下完整示例使用本地课程表：

```python title="examples/runtime/custom_tool.py"
--8<-- "examples/runtime/custom_tool.py"
```

从仓库根目录运行 `python examples/runtime/custom_tool.py`。终端会输出成功使用的工具名称与回答；`result.error` 表示本次运行的结构化错误。

## 定义输入和返回值

`name` 是模型看到的名称，`description` 说明何时使用和需要什么输入。为每个参数提供准确的 Python 类型，工具返回值应包含模型完成任务所需的信息。

以下代码在已创建的 `runtime` 中运行：

```python
@runtime.tools.tool(name="add", description="计算两个整数的和。")
def add(a: int, b: int) -> int:
    return a + b

result = await runtime.run(
    "请调用 add 计算 21 加 34。",
    config={"agent": {"tool_names": ["add"]}},
)
```

网络或数据库操作可以使用 `async def`。SDK 也接受同步函数；耗时阻塞操作应由应用妥善处理，避免阻塞运行事件。

## 选择可用工具

| `tool_names` | 模型可用的工具 |
| --- | --- |
| `None` | 全部已注册工具 |
| `[]` | 不提供工具 |
| `["add"]` | 仅列出的工具 |

工具必须先注册，再调用 `run()`。同名工具不能靠不同描述区分；MCP 工具名称通常为 `mcp_<server>_<tool>`。

工具列表限定可见范围，并不强制模型一定调用工具。提示词应明确要求完成具体动作，模型也必须支持 Tool Calling。

## 处理工具失败

参数错误或工具异常会作为工具结果交回模型，它可以修改参数或继续处理。因此某个工具失败，并不意味着最终 `result.error` 一定非空。

`result.tools_used` 只记录成功执行的工具。检查单次调用的成败，使用[工具事件与 Hooks](../how-to/hooks.md)。需要用户确认时传入[审批处理器](../concepts/tool-safety.md)。

## 相关接口

[ToolManager、Tool 与 CallableTool](../reference/tools.md) · [文件与命令](../how-to/files-and-commands.md) · [MCP](../how-to/mcp.md)
