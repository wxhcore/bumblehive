# 消息与协议对象

这些对象用于 Provider、工具和 Agent Loop 之间交换数据。

| 接口 | 用途 |
| --- | --- |
| `Message` | 模型消息字典类型 |
| `UserMessage` | `run()` 接受的用户输入 |
| `ToolCall` | 已解析的工具调用 |
| `ToolResult` | 工具执行结果 |
| `AgentError` | 结构化错误 |
| `GenerationConfig` | 单次模型生成参数 |
| `MCPServerConfig` | 一个 MCP Server 的连接设置 |

业务代码通常不需要手动构造 `ModelRequest`，但自定义 Provider 会使用它。

## 公开接口

::: bumblehive.protocols
    options:
      show_root_heading: false
      show_root_full_path: false
