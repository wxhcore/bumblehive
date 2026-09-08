# 错误、重试与常见问题

Bumblehive 的失败分为两类：返回结构化错误，以及直接抛出异常。项目代码需要同时处理。

## 先检查 `AgentRunResult`

模型请求失败或达到最大迭代次数时，通常仍会返回 `AgentRunResult`：

```python
result = await runtime.run("分析这个项目")

if result.error is not None:
    print("错误代码：", result.error.code)
    print("错误信息：", result.error.message)
    print("是否可恢复：", result.error.recoverable)
else:
    print(result.final_content)
```

当前常见的 `stop_reason`：

| 值 | 含义 |
| --- | --- |
| `completed` | 正常完成 |
| `model_error` | Provider 返回模型错误 |
| `max_iterations` | 达到工具循环上限 |

Provider 会在返回可恢复错误前自动重试。默认最多重试 3 次。

## 再处理直接异常

配置错误、MCP 连接失败、状态参数冲突等问题会直接抛出异常：

```python
try:
    async with bumblehive.from_config(config) as runtime:
        result = await runtime.run("你好")
except (TypeError, ValueError) as exc:
    print("配置或参数错误：", exc)
except Exception as exc:
    print("运行失败：", exc)
else:
    if result.error:
        print(result.error.code, result.error.message)
    else:
        print(result.final_content)
```

库代码通常应记录异常后继续向上抛出，而不是统一转换成空字符串。

## 工具失败不一定是整个运行失败

工具不存在、参数不合法或工具函数抛出异常时，错误会作为工具结果交给模型。模型可能改正参数或换一种方法继续回答。

因此可能出现：

```text
result.error is None
但某个工具执行失败
```

`result.tools_used` 只记录成功执行的工具。需要检查单个工具失败时，可以使用事件 Hook：

```python
from bumblehive import EventRecorder
from bumblehive.observability import TOOL_CALL_FINISHED


recorder = EventRecorder()
result = await runtime.run("执行任务", hooks=recorder)

for event in recorder.by_kind(TOOL_CALL_FINISHED):
    if not event.payload["ok"]:
        print(event.payload["error"])
```

## 不要忽略资源清理

使用 `async with` 关闭 Runtime。流式调用提前停止时，调用 `await stream.aclose()`。

对于持久化会话，不要在捕获异常后直接重复提交同一条消息。先确认业务是否允许重复执行工具，再决定是否重试。

## 按症状定位

| 症状 | 检查方向 |
| --- | --- |
| 无法导入 SDK、环境变量 KeyError | Python 环境与模型变量是否配置，见[快速开始](../getting-started/installation.md) |
| 模型错误 401 / 403 / 404 / 429 | 检查凭据、Base URL、模型名与服务限流 |
| 没有调用工具、Unknown tools | 检查注册顺序、tool_names 和模型的工具能力，见[工具调用](../getting-started/first-tool.md) |
| 审批提示没有出现 | 模型是否发出有效工具请求；参数校验先于审批，见[审批指南](../concepts/tool-safety.md) |
| Skill 未生效 | 名称、目录、SKILL.md 和 read_file 是否可用，见[Skills](skills.md) |
| MCP 连接失败 | URL、Header 和远端状态；连接在 Runtime 初始化时发生，见[MCP](mcp.md) |
| 文件路径被拒绝 | workspace 和额外读写根目录是否包含该路径，见[访问范围](../concepts/tool-safety.md) |
| 忘记前一轮 | 是否复用了 history 或 session_id，见[会话](memory-and-sessions.md) |
| 无法获取流式结果 | 是否已消费完整事件流，是否提前关闭，见[流式输出](streaming.md) |
| 达到最大迭代次数 | 检查工具是否持续失败、指令是否冲突，再考虑提高 max_iterations |

[详细诊断步骤](../troubleshooting.md) · [AgentError 参考](../reference/protocols.md#bumblehive.protocols.AgentError)
