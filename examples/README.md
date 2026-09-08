# Bumblehive examples

## Recommended learning path

If you are new to Bumblehive, run these examples in order:

1. `runtime/basic.py` — make one model call.
2. `runtime/custom_tool.py` — register a Python tool.
3. `runtime/tool_approval.py` — approve or reject a tool call before execution.

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

`runtime/tool_approval.py` 会在终端等待确认。通过 Conda 直接启动时使用 `conda run --no-capture-output -n bumblehive_env python examples/runtime/tool_approval.py`，以保留实时输入输出。

`tools/basic.py`, `tools/builtins.py`, and `skills/basic.py` do not require a
model API. `tools/mcp_tools.py` additionally requires `BUMBLEHIVE_MCP_URL`.
