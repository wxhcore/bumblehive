# 工具与审批

通过 runtime.tools 注册和执行工具。审批处理器在参数校验后运行，决定当前调用是否执行。

[工具调用指南](../getting-started/first-tool.md) · [交互式审批示例](../concepts/tool-safety.md) · [MCP 配置](skills.md)

## 常用接口

| 接口 | 用途 |
| --- | --- |
| [`ToolManager`](#bumblehive.tools.ToolManager) | 注册、选择和执行工具，管理内置工具与 MCP 连接。 |
| [`ToolApprovalRequest`](#bumblehive.ToolApprovalRequest) | 处理器读取 call_id、name 和校验后的 arguments。 |
| [`ToolApprovalDecision`](#bumblehive.ToolApprovalDecision) | approve() 批准；reject(reason) 拒绝并把原因交给 Agent。 |
| [`ToolPathPolicy`](#bumblehive.tools.ToolPathPolicy) | 为路径感知的内置工具设置额外读写根目录和命令路径检查。 |

## 注册与执行

注册、选择和执行工具，管理内置工具与 MCP 连接。execute_many() 返回按输入顺序排列的结果。

::: bumblehive.tools.ToolManager
    options:
      heading_level: 3
      show_root_heading: true
      show_root_full_path: false

保存工具定义，准备参数并查询可用工具。

::: bumblehive.tools.ToolRegistry
    options:
      heading_level: 3
      show_root_heading: true
      show_root_full_path: false


## 工具定义

把普通 Python 函数转换成工具。

::: bumblehive.tools.CallableTool
    options:
      heading_level: 3
      show_root_heading: true
      show_root_full_path: false

自定义工具基类，定义 schema、参数校验与执行。

::: bumblehive.tools.Tool
    options:
      heading_level: 3
      show_root_heading: true
      show_root_full_path: false

已经解析的工具调用，包含 ID、名称与参数。

::: bumblehive.protocols.ToolCall
    options:
      heading_level: 3
      show_root_heading: true
      show_root_full_path: false

工具的内容或结构化错误。

::: bumblehive.protocols.ToolResult
    options:
      heading_level: 3
      show_root_heading: true
      show_root_full_path: false

把模型的工具调用数据转换为 ToolCall。

::: bumblehive.protocols.parse_tool_call
    options:
      heading_level: 3
      show_root_heading: true
      show_root_full_path: false


## 执行前审批

处理器读取 call_id、name 和校验后的 arguments。

<span id="bumblehive.tools.ToolApprovalRequest"></span>

::: bumblehive.ToolApprovalRequest
    options:
      heading_level: 3
      show_root_heading: true
      show_root_full_path: false

approve() 批准；reject(reason) 拒绝并把原因交给 Agent。

<span id="bumblehive.tools.ToolApprovalDecision"></span>

::: bumblehive.ToolApprovalDecision
    options:
      heading_level: 3
      show_root_heading: true
      show_root_full_path: false

异步审批函数类型。同一批次可有多个并行审批请求；处理器异常会使当前工具调用失败。

<span id="bumblehive.tools.ToolApprovalHandler"></span>

::: bumblehive.ToolApprovalHandler
    options:
      heading_level: 3
      show_root_heading: true
      show_root_full_path: false


## 路径策略

为路径感知的内置工具设置额外读写根目录和命令路径检查。它不是操作系统沙箱。

::: bumblehive.tools.ToolPathPolicy
    options:
      heading_level: 3
      show_root_heading: true
      show_root_full_path: false

## 相关类型

<span id="bumblehive.tools.MCPServerStatus"></span>

[`MCPServerStatus`](skills.md#bumblehive.tools.MCPServerStatus) 的完整定义已集中到对应主题。
