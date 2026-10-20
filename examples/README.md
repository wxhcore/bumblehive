# SDK 示例

先安装 SDK，并在当前终端设置模型连接：

```bash
python -m pip install -e .
export BUMBLEHIVE_MODEL="your-model"
export BUMBLEHIVE_API_KEY="your-api-key"
export BUMBLEHIVE_BASE_URL="https://your-provider.example/v1"
```

PowerShell 配置见[快速开始](../docs/zh/getting-started/installation.md#configure-model)。以下命令均从仓库根目录执行。

## 从这里开始

```bash
python examples/runtime/basic.py
python examples/runtime/custom_tool.py
python examples/runtime/sessions.py
```

分别体验模型回答、课程查询工具和多轮记忆。

## 按功能选择

| 功能 | 示例与运行方式 |
| --- | --- |
| 流式输出 | `python examples/runtime/streaming.py` |
| 图片输入 | `python examples/runtime/multimodal.py /path/to/image.png` |
| 内存历史 | `python examples/runtime/conversation_history.py` |
| 审批 | `python examples/runtime/tool_approval.py`；输入 y 才写入脚本目录下的 approval-demo.txt，可能覆盖同名文件 |
| 引导 | `python examples/runtime/steering_run.py`；查询工具开始时追加中文回答要求 |
| 流式引导 | `python examples/runtime/steering_stream.py` |
| 控制台引导 | `python examples/runtime/steering_console.py` |
| 追问 | `python examples/runtime/ask_user.py`；自由输入、选项编号或 /skip |
| 超时追问 | `python -m examples.runtime.ask_user_timeout`；默认等待 60 秒 |
| 后台工具 | `python -m examples.runtime.background_tools` |
| 子 Agent | `python examples/runtime/multi_agent.py` |
| 后台子 Agent | `python -m examples.runtime.multi_agent_background` |
| 文件读取 | `python examples/runtime/files.py` |
| MCP | 先运行 `python examples/tools/mcp_server.py`，另一个终端运行 `python examples/runtime/mcp.py` |
| Skills | `python examples/runtime/skills.py` |
| 上下文 | `python examples/runtime/context.py` |
| Hooks | `python examples/observability/hooks.py` |

后台示例共用 [background_support.py](runtime/background_support.py)，这是示例辅助代码，不是 SDK 内置 API。用 `python -m` 运行，以便导入同目录下的示例模块。终端追问结束前请输入答案或 `/skip`；取消协程不能终止线程中的 `input()`。

## 完整应用

- [file_assistant.py](runtime/file_assistant.py)：读取、修改文件并执行验证，修改前等待审批。
- [chat.py](runtime/chat.py)：多轮流式聊天，`/quit` 退出。
- [chat_events.py](runtime/chat_events.py)：将文本和工具事件转成 JSON 更新。

## 底层接口

`loop/` 展示 AgentLoop 和 Runner；`providers/` 展示模型 Provider；`tools/` 展示独立工具调用；`skills/basic.py` 展示 Skill 管理。

以下例子无需模型或密钥：

```bash
python examples/tools/basic.py
python examples/tools/builtins.py
python examples/skills/basic.py
```

`examples/tools/mcp_tools.py` 另需 `BUMBLEHIVE_MCP_URL`，用于独立测试远端工具连接。完整教学说明见[中文文档](../docs/zh/index.md)。
