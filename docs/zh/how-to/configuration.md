# 配置 Runtime

简单项目优先使用 `RuntimeArguments`。需要保存配置时，再使用字典或 JSON 文件。

## 使用 `RuntimeArguments`

```python
import os

import bumblehive


config = bumblehive.RuntimeArguments(
    model=os.environ["BUMBLEHIVE_MODEL"],
    api_key=os.environ["BUMBLEHIVE_API_KEY"],
    base_url=os.environ["BUMBLEHIVE_BASE_URL"],
    workspace="./workspace",
    skills_dir="./skills",
    timezone="Asia/Shanghai",
    max_completion_tokens=2_048,
    temperature=0.2,
    max_iterations=12,
    agent_instructions="回答要简洁，并优先使用提供的工具。",
    dynamic_context={"project": "course-helper"},
    skill_names=[],
    tool_names=[],
)

runtime = bumblehive.from_config(config)
```

Bumblehive 不会自动读取这些环境变量。上面的 `os.environ` 和 `os.getenv` 是应用自己的读取逻辑。

## 常用配置

| 分类 | 参数 | 作用 |
| --- | --- | --- |
| Provider | `model` | 模型名称 |
| Provider | `api_key`、`base_url` | API 凭证和 OpenAI 兼容地址 |
| 生成 | `max_completion_tokens` | 最大输出 token 数 |
| 生成 | `temperature`、`reasoning_effort` | 控制生成行为 |
| Agent | `agent_instructions` | Agent 的长期行为要求 |
| Agent | `dynamic_context` | 项目名、用户角色等动态信息 |
| 能力 | `skill_names`、`tool_names` | 本次 Runtime 默认开放的能力 |
| 能力 | `skills_dir` | Runtime 加载和安装 Skill 的根目录 |
| 运行 | `workspace`、`timezone` | 工作目录和时区 |
| 运行 | `max_iterations` | 最多执行多少轮模型/工具循环 |
| 运行 | `context_window_tokens` | 上下文窗口预算 |
| 运行 | `max_tool_result_chars` | 单个工具结果进入模型前的字符预算 |

`model` 应明确设置。`base_url=None` 时，OpenAI SDK 使用自己的默认地址。

## 使用嵌套字典

字典适合从应用配置系统动态组装：

```python
config = {
    "skills_dir": "./skills",
    "provider": {
        "model": os.environ["BUMBLEHIVE_MODEL"],
        "api_key": os.environ["BUMBLEHIVE_API_KEY"],
        "base_url": os.environ["BUMBLEHIVE_BASE_URL"],
    },
    "generation": {"temperature": 0.2},
    "agent": {
        "instructions": "回答要简洁。",
        "tool_names": [],
    },
    "runtime": {
        "workspace": "./workspace",
        "timezone": "Asia/Shanghai",
    },
}

runtime = bumblehive.from_config(config)
```

## 从 JSON 文件加载

`from_config()` 也接受 `.json` 路径：

```python
runtime = bumblehive.from_config("bumblehive.json")
```

JSON 不会展开环境变量。不要把真实 API Key 提交到 Git 仓库；正式项目更适合在 Python 中从环境变量注入密钥。

## 覆盖单次调用配置

`run()` 的 `config` 会与 Runtime 基础配置深度合并：

```python
result = await runtime.run(
    "只回答最终数字",
    config={
        "generation": {"temperature": 0},
        "agent": {"tool_names": ["calculate"]},
    },
)
```

单次覆盖不会修改 Runtime 的基础配置。

`mcp_servers` 和 `skills_dir` 不能按调用覆盖，因为 MCP 连接和 Skill 目录属于 Runtime 生命周期。应在创建 Runtime 时配置。

## 能力列表：省略、`None` 和空列表 { #capability-lists }

创建 Runtime 时，省略 `skill_names` 或 `tool_names` 等同于传入 `None`。

| 配置值 | `skill_names` | `tool_names` |
| --- | --- | --- |
| 省略或 `None` | 向模型提供全部已加载 Skill 的摘要 | 向模型开放全部已注册工具 |
| `[]` | 不提供任何 Skill | 不开放任何工具 |
| `['name']` | 只提供指定 Skill | 只开放指定工具 |

Skill 是加入上下文的能力说明，不是可调用函数。未知工具名会触发 `Unknown tools` 错误；未知 Skill 名目前会被忽略。

在 `run(config=...)` 中省略这两个字段会继承 Runtime 配置；显式传入 `None` 才会改为全部。正式项目建议写出明确列表。

下一步：阅读[工具安全](../concepts/tool-safety.md)。
