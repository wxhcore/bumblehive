# 模型配置

高层 Runtime 连接 OpenAI Chat Completions 兼容服务。开始时只需提供模型名、密钥和接口地址，完整程序见[快速开始](../getting-started/installation.md)。

## 连接模型

```python
import os
import bumblehive

config = bumblehive.RuntimeArguments(
    model=os.environ["BUMBLEHIVE_MODEL"],
    api_key=os.environ["BUMBLEHIVE_API_KEY"],
    base_url=os.environ["BUMBLEHIVE_BASE_URL"],
    skill_names=[],
    tool_names=[],
)
```

环境变量由这里的 `os.environ` 读取。`base_url` 填服务提供的 API 基地址；省略时使用 OpenAI SDK 的默认地址。工具调用需要模型支持 Tool Calling，图片输入需要视觉能力。

## 按需增加配置

在上面的 `RuntimeArguments(...)` 中加入所需参数即可：

| 需求 | 示例 |
| --- | --- |
| 控制回答长度 | `max_completion_tokens=2048` |
| 限制工具循环次数 | `max_iterations=12` |
| 设置工作目录 | `workspace="./workspace"` |
| 定义 Agent 的任务与风格 | `agent_instructions="你是课程助手，回答简洁。"` |
| 使用工具 | `tool_names=["read_file"]` |

生成参数是否支持取决于模型。提示词和预算的用法见[上下文指南](context.md)，所有字段见[配置参考](../reference/config.md)。

## 覆盖一次调用 { #overrides }

在已经创建的 `runtime` 中，只修改这一次运行的要求：

```python
result = await runtime.run(
    "解释什么是 Agent。",
    config={"agent": {"instructions": "使用中文，最多两句话。"}},
)
print(result.error.message if result.error else result.final_content)
```

单次配置与基础配置合并，不修改后续调用的默认值。MCP 连接和 Skill 目录在创建 Runtime 时确定，不能按调用覆盖。

## 选择工具和 Skills { #capability-lists }

| 配置值 | 含义 |
| --- | --- |
| 省略或 `None` | 全部可用项 |
| `[]` | 不使用任何项 |
| `["name"]` | 只使用指定项 |

这个规则同时适用于 `tool_names` 和 `skill_names`。在单次调用的 `config` 中省略字段则继承基础配置。

## 使用配置文件

配置较多时，`from_config()` 也接受嵌套字典或 JSON 文件路径：

```python
runtime = bumblehive.from_config("bumblehive.json")
```

JSON 使用 `provider`、`agent`、`generation`、`runtime` 等分组，不会展开环境变量。字段结构见[配置参考](../reference/config.md)。密钥可以在 Python 中读取后放入字典，不必写进配置文件。
