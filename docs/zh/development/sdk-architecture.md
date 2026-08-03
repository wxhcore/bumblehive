# Python SDK 架构

Bumblehive 分成三层。普通项目从第一层开始，需要扩展时再向下使用。

| 层级 | 主要接口 | 负责内容 |
| --- | --- | --- |
| 应用层 | `BumblehiveRuntime` | 配置、资源、历史、Session 和运行入口 |
| Agent 层 | `AgentLoop` | 构建上下文并选择 Skills、Tools |
| 执行层 | `ToolCallingRunner` | 重复执行“模型 → 工具 → 模型” |

一次调用的主要流程：

```text
用户消息
  ↓
BumblehiveRuntime
  ↓ 读取配置、历史和 Session
AgentLoop
  ↓ 构建上下文，选择 Skills 和 Tools
ToolCallingRunner
  ↓
ModelProvider ⇄ ToolManager
  ↓
AgentRunResult
```

## 如何选择入口

- 只想开发 Agent：使用 `BumblehiveRuntime`。
- 需要传入自己的 Provider：使用 `AgentLoop`。
- 已经拥有消息构建系统：使用 `ToolCallingRunner`。
- 只想管理和执行工具：使用 `ToolManager`。

不要为了“灵活”而直接使用底层接口。更低的层级意味着需要自己管理更多配置和资源。

## 公开接口边界

公开接口由各模块的 `__all__` 定义，并由 `tests/test_public_api.py` 检查。

没有出现在 `__all__` 中的对象属于内部实现，升级时可能发生变化。

下一步：阅读[增加一个工具](adding-a-tool.md)或[增加一个 Provider](adding-a-provider.md)。
