# Bumblehive examples

## Recommended learning path

If you are new to Bumblehive, run these examples in order:

1. `runtime/basic.py` — make one model call.
2. `runtime/custom_tool.py` — register a Python tool.
3. `runtime/tool_approval.py` — interactively approve or reject a file write.

Application examples:

- `runtime/file_assistant.py` — edit a sample file and validate it with human approval.
- `runtime/chat_events.py` — map streamed SDK events to JSON updates for a chat UI.
- `runtime/multi_agent.py` — delegate an isolated task through a custom tool.

These examples are organized by the SDK layer they use:

- `runtime/` — high-level application API.
- `loop/` — independently composed agent loops.
- `providers/` — managed model-provider access.
- `tools/` — local, built-in, and MCP tools.
- `skills/` — skill discovery and rendering.
- `observability/` — lifecycle hooks and event recording.

| Area | Covered workflows |
| --- | --- |
| Runtime | Basic calls, streaming, tool approval, history, sessions, sub-agents |
| Loop | `AgentLoop` context composition and low-level tool calling |
| Providers | Provider creation, requests, and cleanup |
| Tools | Function tools, schemas, batch execution, built-ins, path scope, MCP |
| Skills | Package layout, discovery, resources, content, rendering, reload |
| Observability | Callback hooks, event recording, event filtering |

Network-backed examples read their connection settings from the environment:

```bash
export BUMBLEHIVE_API_KEY="..."
export BUMBLEHIVE_MODEL="your-model"
export BUMBLEHIVE_BASE_URL="https://your-provider.example/v1"
```

Run an example from the repository root:

```bash
python examples/runtime/basic.py
python examples/runtime/tool_approval.py
python examples/loop/agent_loop.py
python examples/tools/basic.py
```

`runtime/tool_approval.py` 将工作目录设为脚本所在的 `examples/runtime/`，启动时会打印其绝对路径；请求模型调用 `write_file` 在该目录创建 `approval-demo.txt`，内容为 `hello`。模型发出有效工具调用后，终端会展示工具名称和参数并等待确认：输入 `y` 或 `yes` 批准实际写入（可能覆盖同名文件），回车或其他输入拒绝，本次调用不会修改文件。终端会打印批准或拒绝结果。如果没有审批提示，请检查模型是否实际请求了工具调用。通过 Conda 启动时使用 `conda run --no-capture-output -n bumblehive_env python examples/runtime/tool_approval.py`，以保留实时输入输出。

`tools/basic.py`, `tools/builtins.py`, and `skills/basic.py` do not require a
model API. `tools/mcp_tools.py` additionally requires `BUMBLEHIVE_MCP_URL`.
