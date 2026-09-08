# 消息与会话

MessageHistory 管理应用提供的内存历史；持久化通过 Runtime 的 session_id 使用。会话存储内部对象不是公开接口。

[保存并继续会话](../how-to/memory-and-sessions.md) · [图片输入](../how-to/images.md) · [运行结果](runtime.md)

## 常用接口

| 接口 | 用途 |
| --- | --- |
| [`Message`](#bumblehive.protocols.Message) | 模型消息字典，包含角色、内容和可选工具调用信息。 |
| [`UserMessage`](#bumblehive.protocols.UserMessage) | Runtime 接受的用户输入类型。 |
| [`normalize_user_message`](#bumblehive.protocols.normalize_user_message) | 将用户输入转换成标准消息序列。 |
| [`MessageHistory`](#bumblehive.MessageHistory) | Runtime 仅读取传入的历史。用 replace_run_messages(result.messages) 显式更新，避免把 system 和运行上下文重复保存。 |
| [`AgentError`](#bumblehive.protocols.AgentError) | 结构化错误的 code、message 和 recoverable 字段。它与直接抛出的 Python 异常需要分别处理。 |

## 消息输入

模型消息字典，包含角色、内容和可选工具调用信息。

::: bumblehive.protocols.Message
    options:
      heading_level: 3
      show_root_heading: true
      show_root_full_path: false

Runtime 接受的用户输入类型。

::: bumblehive.protocols.UserMessage
    options:
      heading_level: 3
      show_root_heading: true
      show_root_full_path: false

将用户输入转换成标准消息序列。

::: bumblehive.protocols.normalize_user_message
    options:
      heading_level: 3
      show_root_heading: true
      show_root_full_path: false


## 对话历史

Runtime 仅读取传入的历史。用 replace_run_messages(result.messages) 显式更新，避免把 system 和运行上下文重复保存。

::: bumblehive.MessageHistory
    options:
      heading_level: 3
      show_root_heading: true
      show_root_full_path: false


## 错误对象

结构化错误的 code、message 和 recoverable 字段。它与直接抛出的 Python 异常需要分别处理。

::: bumblehive.protocols.AgentError
    options:
      heading_level: 3
      show_root_heading: true
      show_root_full_path: false

## 相关类型

<span id="bumblehive.protocols.GenerationConfig"></span>

[`GenerationConfig`](config.md#bumblehive.protocols.GenerationConfig) 的完整定义已集中到对应主题。

<span id="bumblehive.protocols.MCPServerConfig"></span>

[`MCPServerConfig`](skills.md#bumblehive.protocols.MCPServerConfig) 的完整定义已集中到对应主题。

<span id="bumblehive.protocols.ToolCall"></span>

[`ToolCall`](tools.md#bumblehive.protocols.ToolCall) 的完整定义已集中到对应主题。

<span id="bumblehive.protocols.ToolResult"></span>

[`ToolResult`](tools.md#bumblehive.protocols.ToolResult) 的完整定义已集中到对应主题。

<span id="bumblehive.protocols.parse_tool_call"></span>

[`parse_tool_call`](tools.md#bumblehive.protocols.parse_tool_call) 的完整定义已集中到对应主题。

<span id="bumblehive.protocols.ToolApprovalRequest"></span>

[`ToolApprovalRequest`](tools.md#bumblehive.ToolApprovalRequest) 的完整定义已集中到对应主题。

<span id="bumblehive.protocols.ToolApprovalDecision"></span>

[`ToolApprovalDecision`](tools.md#bumblehive.ToolApprovalDecision) 的完整定义已集中到对应主题。

<span id="bumblehive.protocols.ToolApprovalHandler"></span>

[`ToolApprovalHandler`](tools.md#bumblehive.ToolApprovalHandler) 的完整定义已集中到对应主题。
