# MCP

连接远端 MCP Server，将它提供的工具注册到 Runtime，再选择向模型开放哪些工具。

## 连接服务

先完成[模型配置](../getting-started/installation.md#configure-model)，并准备可访问的 MCP URL 与凭据。将以下代码放入 `async main()`，连接一个提供 `search` 工具的 HTTP MCP Server：

```python
import os

import bumblehive
from bumblehive.protocols import MCPServerConfig


docs_server = MCPServerConfig(
    name="docs",
    url=os.environ["DOCS_MCP_URL"],
    headers={
        "Authorization": f"Bearer {os.environ['DOCS_MCP_TOKEN']}"
    },
    tool_timeout=30,
    enabled_tools=["search"],
)

config = bumblehive.RuntimeArguments(
    model=os.environ["BUMBLEHIVE_MODEL"],
    api_key=os.environ["BUMBLEHIVE_API_KEY"],
    base_url=os.environ["BUMBLEHIVE_BASE_URL"],
    mcp_servers=(docs_server,),
    tool_names=["mcp_docs_search"],
)

async with bumblehive.from_config(config) as runtime:
    print(runtime.tools.registered_mcp_tool_names)
    result = await runtime.run("搜索安装 Bumblehive 的方法")
    print(result.error.message if result.error else result.final_content)
```

MCP 工具在本地的名称通常是：

```text
mcp_<server name>_<original tool name>
```

例如 `docs` Server 的 `search` 会注册为 `mcp_docs_search`。

## 两层工具过滤

MCP 有两层限制：

1. `enabled_tools` 决定从远端注册哪些工具；
2. Agent 的 `tool_names` 决定本次向模型开放哪些已注册工具。

`enabled_tools=["*"]` 会注册远端全部工具。面对第三方 Server 时，建议改成明确列表。

## 生命周期与安全

- Runtime 进入 `async with` 时连接 MCP，退出时关闭；
- MCP 配置不能通过单次 `run(config=...)` 修改；
- Header 只适用于 HTTP 或 SSE 传输；
- 默认工具超时为 30 秒；
- MCP Server 的文件访问能力由服务端自身控制。

连接失败时，Runtime 初始化会直接抛出异常。请检查 URL、鉴权 Header 和 Server 是否可用。

[错误处理](error-handling.md) · [MCP 与 Skills API](../reference/skills.md)
