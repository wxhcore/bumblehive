# 故障排查

先区分两种失败：

1. `runtime.run()` 返回了 `AgentRunResult`，检查 `result.error`；
2. 调用直接抛出异常，查看异常类型和完整 traceback。

```python
result = await runtime.run("你好")

if result.error:
    print(result.error.code)
    print(result.error.message)
```

## 无法导入 `bumblehive`

确认安装到了当前 Python 环境：

```bash
python -m pip install bumblehive
python -c "import bumblehive; print(bumblehive.__file__)"
```

在源码仓库中开发时使用：

```bash
python -m pip install -e "."
```

## 环境变量出现 `KeyError`

`os.environ["BUMBLEHIVE_API_KEY"]` 在变量不存在时会抛出 `KeyError`。先设置：

```bash
export BUMBLEHIVE_API_KEY="..."
export BUMBLEHIVE_MODEL="..."
```

PowerShell：

```powershell
$env:BUMBLEHIVE_API_KEY = "..."
$env:BUMBLEHIVE_MODEL = "..."
```

## 模型请求返回错误

如果 `result.stop_reason == "model_error"`：

- 401 / 403：检查 API Key 和权限；
- 404：检查 `base_url`、模型名称和 Provider 路径；
- 429：检查额度和限流；
- timeout：检查网络和服务状态。

错误详情在 `result.error.message`。不要只看 `final_content`。

## 模型没有调用工具

依次检查：

1. `tool_names` 中是否包含该工具；
2. 自定义工具是否在 `run()` 前完成注册；
3. 工具函数是否有清楚的类型标注和 docstring；
4. 当前模型是否支持 Tool Calling；
5. 提示词是否真的需要调用该工具。

进入 Runtime 后可以查看已注册工具：

```python
async with bumblehive.from_config(config) as runtime:
    print(runtime.tools.tool_names)
```

注意：`tool_names=None` 表示全部，`tool_names=[]` 表示一个也不开放。

## 出现 `Unknown tools`

配置中列出了尚未注册的工具。确认名称完全一致，并在运行前注册：

```python
@runtime.tools.tool(
    name="lookup_course",
    description="查询课程。",
)
def lookup_course(name: str) -> str:
    return name
```

MCP 工具使用包装后的名称，例如 `mcp_docs_search`。

## Skill 没有生效

检查加载结果：

```python
catalog = runtime.skills.list_skills(force_reload=True)
print([skill.name for skill in catalog.skills])
print([error.message for error in catalog.errors])
```

常见原因：

- 目录中缺少 `SKILL.md`；
- YAML frontmatter 缺少 `name` 或 `description`；
- `name` 与目录名不同；
- 名称没有使用小写字母、数字和连字符；
- `skill_names` 没有选中该 Skill；
- 没有向模型开放 `read_file`，模型无法读取 `SKILL.md`。

## MCP 无法连接

MCP 在 Runtime 初始化时连接，因此错误可能出现在 `async with` 入口。

检查：

- URL 和服务进程是否可访问；
- 鉴权 Header 是否正确；
- `enabled_tools` 是否包含需要的远端工具；
- Agent 的 `tool_names` 是否使用包装后的名称；
- Header 是否用于 HTTP 或 SSE 传输。

连接成功后可以查看状态：

```python
for status in runtime.tools.list_mcp_server_statuses():
    print(status.name, status.connected, status.registered_tools)
```

`mcp_servers` 不能通过单次 `run(config=...)` 修改。

## 文件路径被拒绝

出现 `outside readable roots` 或 `outside writable roots` 时：

- 相对路径应相对于 `workspace`；
- 额外读取目录加入 `extra_read_roots`；
- 额外写入目录加入 `extra_write_roots`。

不要为了省事开放整个主目录。路径限制也不会自动约束自定义工具、MCP 和子进程。

## Agent 没有记住上一轮

不传状态参数时，每次调用都是无状态的。连续对话必须复用同一个 `MessageHistory`，或使用同一个 `session_id`。

```python
history = bumblehive.MessageHistory()
await runtime.run("第一轮", history=history)
await runtime.run("第二轮", history=history)
```

`history` 与 `session_id` 不能同时传入。

## 无法读取流式结果

必须先完整消费事件，再调用 `result()`：

```python
async for event in stream:
    ...

result = await stream.result()
```

一个 Stream 只能消费一次。提前调用 `aclose()` 后没有最终结果。

## 达到 `max_iterations`

这表示模型持续调用工具，没有在限制内给出最终回答。

优先检查：

- 工具返回值是否清楚；
- 工具是否持续报错；
- Agent 指令是否互相冲突；
- 是否开放了不需要的工具。

确认循环确实需要更多轮后，再提高 `max_iterations`。

## 程序退出时提示资源未关闭

优先使用：

```python
async with bumblehive.from_config(config) as runtime:
    ...
```

手动管理时，把 `await runtime.close()` 放进 `finally`。

更多错误处理方式见[处理运行错误](how-to/error-handling.md)。
