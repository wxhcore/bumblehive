# MCP

MCP 让 Agent 使用外部服务提供的工具。你不需要在应用里重写工具函数，只需连接服务并选择要开放的工具。

## 启动一个示例服务

为了直接体验，仓库提供一个本地课程查询服务。在第一个终端运行：

```bash
python examples/tools/mcp_server.py
```

```python
--8<-- "examples/tools/mcp_server.py"
```

服务监听 `http://127.0.0.1:8000/mcp`。保持这个终端运行，在第二个终端配置[模型环境变量](../getting-started/installation.md#configure-model)。

## 让 Agent 调用远端工具

```bash
python examples/runtime/mcp.py
```

```python
--8<-- "examples/runtime/mcp.py"
```

模型应通过 MCP 查到“周一 10:00，教学楼 A101”。这里有两个名称：

- `enabled_tools=["get_course_info"]` 选择从服务注册的工具。
- `tool_names=["mcp_courses_get_course_info"]` 选择交给 Agent 的工具。名称由 `mcp_服务名_工具名` 组成。

## 换成自己的服务

修改 `url`、`name` 和工具名称。需要 HTTP 鉴权时，在 `MCPServerConfig` 中添加：

```python
headers={"Authorization": f"Bearer {os.environ['MCP_TOKEN']}"}
```

`enabled_tools=["*"]` 可以注册服务的全部工具。连接在进入 Runtime 时建立，退出时关闭。

`tool_timeout` 控制 MCP 调用超时，默认 30 秒；它不是[后台工具](background-tools.md)的“超时后继续等待结果”。

[MCP 配置参考](../reference/skills.md)
