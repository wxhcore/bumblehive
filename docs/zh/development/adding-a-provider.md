# 自定义 Provider 与底层组装

Provider 负责把模型服务转换为统一的 `ModelRequest` 和 `ModelResponse`。

当前高层 Runtime 只创建 `openai_chat_completions` Provider。自定义 Provider 应直接传给 `AgentLoop`。

## 选择接口层

| 需求 | 入口 |
| --- | --- |
| 构建普通应用，复用会话和资源管理 | `BumblehiveRuntime` |
| 替换 Provider，组合上下文与工具 | `AgentLoop` |
| 已有消息构建，只需要模型与工具循环 | `ToolCallingRunner` |
| 只使用工具注册与执行 | `ToolManager` |

[SDK 架构](sdk-architecture.md)说明各层关系。下面的静态 Provider 不访问网络，适合测试底层组装。

## 最小 Provider

```python
from bumblehive.providers import ModelProvider, ModelRequest, ModelResponse


class StaticProvider(ModelProvider):
    async def generate(self, request: ModelRequest) -> ModelResponse:
        return ModelResponse(content="这是一个离线回答。")
```

`generate()` 不应直接返回字符串，而应返回 `ModelResponse`。

## 接入 AgentLoop

```python
from bumblehive.agent import AgentLoop, ContextBuilder, ToolCallingRunner
from bumblehive.skills import SkillsManager
from bumblehive.tools import ToolManager

loop = AgentLoop(
    tools=ToolManager(),
    context=ContextBuilder(),
    skills=SkillsManager(),
    runner=ToolCallingRunner(),
)

result = await loop.run_turn(
    "你好",
    provider=StaticProvider(),
    model="offline-model",
    tool_names=[],
    skill_names=[],
)
```

## 需要实现什么

- 必须实现 `generate()`。
- 支持原生流式输出时实现 `generate_stream()`。
- 持有网络客户端时实现 `close()`。
- 模型服务返回失败时，转换成带 `AgentError` 的 `ModelResponse`。
- 可恢复错误要正确设置 `recoverable=True`，重试逻辑才会生效。

先使用确定性响应测试 Provider，再连接真实服务。

[配置与 Provider API](../reference/config.md) · [AgentLoop API](../reference/agent.md)
