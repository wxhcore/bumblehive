# 测试一个 Agent

测试应尽量离线、确定并且快速。不要让普通单元测试依赖真实模型回答。

## 推荐分三层测试

| 层级 | 测试内容 | 是否需要网络 |
| --- | --- | --- |
| 工具单元测试 | 输入、输出、参数校验和权限 | 否 |
| Agent Loop 测试 | 上下文、工具选择、结果处理 | 否，使用 Fake Provider |
| 少量冒烟测试 | 真实 API 和模型兼容性 | 是 |

## 用 Fake Provider 测试 Agent Loop

下面的测试不会发送网络请求：

```python
import pytest

from bumblehive.agent import AgentLoop, ContextBuilder, ToolCallingRunner
from bumblehive.providers import ModelProvider, ModelRequest, ModelResponse
from bumblehive.skills import SkillsManager
from bumblehive.tools import ToolManager


class FakeProvider(ModelProvider):
    def __init__(self) -> None:
        self.requests: list[ModelRequest] = []

    async def generate(self, request: ModelRequest) -> ModelResponse:
        self.requests.append(request)
        return ModelResponse(content="这是固定回答")


@pytest.mark.asyncio
async def test_agent_returns_expected_answer(tmp_path) -> None:
    provider = FakeProvider()
    loop = AgentLoop(
        tools=ToolManager(),
        context=ContextBuilder(),
        skills=SkillsManager(tmp_path / "skills"),
        runner=ToolCallingRunner(),
    )

    result = await loop.run_turn(
        "你好",
        provider=provider,
        model="fake-model",
        workspace=tmp_path,
        skill_names=[],
        tool_names=[],
    )

    assert result.final_content == "这是固定回答"
    assert result.error is None
    assert provider.requests[0].messages[-1]["role"] == "user"
```

运行：

```bash
python -m pytest
```

## 单独测试工具

工具是普通 Python 逻辑，优先直接测试函数。需要验证 Bumblehive 的参数处理时，再通过 `ToolManager` 调用：

```python
from bumblehive.protocols import ToolCall
from bumblehive.tools import ToolManager


@pytest.mark.asyncio
async def test_add_tool() -> None:
    tools = ToolManager()

    @tools.tool(
        name="add",
        description="计算两个整数的和。",
    )
    def add(left: int, right: int) -> int:
        return left + right

    result = await tools.execute_call(
        ToolCall("call-1", "add", {"left": "2", "right": 3})
    )

    assert result.error is None
    assert result.content == 5
```

## 应该断言什么

优先断言稳定的行为：

- `final_content`、`stop_reason` 和 `error`；
- 模型收到的工具名称；
- 工具的结构化输入和输出；
- `MessageHistory` 中的角色顺序；
- 关键事件是否出现。

不要断言真实模型必须逐字返回某句话。冒烟测试只检查请求成功、结果结构正确和关键能力可用。

下一步：在 CI 中运行离线测试，再单独配置需要密钥的冒烟测试。
