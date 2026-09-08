# 工具

大多数项目通过 `runtime.tools.tool` 注册普通 Python 函数。

```python
@runtime.tools.tool(
    name="add",
    description="计算两个整数的和。",
)
def add(a: int, b: int) -> int:
    return a + b
```

| 接口 | 用途 |
| --- | --- |
| `ToolManager` | 注册、查询和执行工具 |
| `ToolRegistry` | 保存工具定义 |
| `Tool` | 自定义工具基类 |
| `CallableTool` | 把 Python 函数包装成工具 |
| `ToolApprovalRequest` | 描述一个等待审批的已校验工具调用 |
| `ToolApprovalDecision` | 返回允许或拒绝决定 |
| `ToolApprovalHandler` | 异步审批函数类型 |
| `ToolPathPolicy` | 配置内置工具的额外读写根目录和 `exec` 路径限制 |
| `MCPServerStatus` | 查看 MCP 连接和工具状态 |

`ToolPathPolicy` 是运行级应用层策略，不是操作系统沙箱。自定义 Python 工具和 MCP 工具需要自行检查访问权限。

## 执行前审批

向一次运行传入异步 `approval_handler`，即可在参数校验通过后、工具执行前决定是否允许调用：

```python
from bumblehive import ToolApprovalDecision, ToolApprovalRequest


async def approve_tool(
    request: ToolApprovalRequest,
) -> ToolApprovalDecision:
    if request.name == "write_file":
        return ToolApprovalDecision.reject("Writing is not allowed.")
    return ToolApprovalDecision.approve()


result = await runtime.run(
    "检查项目内容",
    approval_handler=approve_tool,
)
```

Request 中包含经过校验和类型转换的参数。批准后工具继续执行；拒绝会作为工具结果返回给 Agent。审批沿用现有批次调度，同一并行批次中可以同时存在多个待审批调用。

## 公开接口

::: bumblehive.tools
    options:
      show_root_heading: false
      show_root_full_path: false
