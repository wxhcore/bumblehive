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
| `ToolPathPolicy` | 配置内置工具的额外读写根目录和 `exec` 路径限制 |
| `MCPServerStatus` | 查看 MCP 连接和工具状态 |

`ToolPathPolicy` 是运行级应用层策略，不是操作系统沙箱。自定义 Python 工具和 MCP 工具需要自行检查访问权限。

## 公开接口

::: bumblehive.tools
    options:
      show_root_heading: false
      show_root_full_path: false
