# Bumblehive 如何工作

Bumblehive 把模型、工具、上下文和对话状态组合成一个可以反复运行的 Agent。

一次调用大致经过下面几步：

```text
用户消息
  → 构建上下文
  → 请求模型
  → 模型直接回答，或请求调用工具
  → 执行工具并把结果交还模型
  → 得到最终结果
```

如果模型继续调用工具，这个过程会重复，直到模型给出最终回答或达到最大迭代次数。这就是 **Agent 循环（Agent Loop）**。

## 五个核心对象

| 对象 | 作用 | 简单理解 |
| --- | --- | --- |
| `BumblehiveRuntime` | 组合并管理整个 Agent | Agent 的运行容器 |
| `ModelProvider` | 向模型发送请求 | 模型连接器 |
| `ToolManager` | 注册并执行工具 | Agent 的工具箱 |
| `SkillsManager` | 向模型提供工作方法和资源位置 | Agent 的说明书目录 |
| `MessageHistory` / `session_id` | 保存多轮对话 | Agent 的记忆 |

## Tool 和 Skill 有什么区别

**工具（Tool）执行一个具体动作。**

例如 `get_weather(city)` 会真正查询天气并返回结果。

**技能（Skill）告诉 Agent 应该怎样完成一类任务。**

例如 `code-review` 技能可以要求 Agent：先运行测试，再检查变更，最后按固定格式输出报告。

Skill 不会自动执行其中的脚本。模型需要先使用 `read_file` 读取 `SKILL.md`，再按照里面的说明工作。

## 一次运行返回什么

`runtime.run()` 返回 `AgentRunResult`。最常用的字段是：

| 字段 | 含义 |
| --- | --- |
| `final_content` | 最终回答 |
| `tools_used` | 成功执行过的工具名称 |
| `usage` | 模型返回的 token 用量 |
| `stop_reason` | 为什么停止 |
| `error` | 结构化错误；成功时为 `None` |

不要只打印 `final_content`。正式项目还应检查 `error`。

```python
result = await runtime.run("用一句话介绍 Bumblehive")

if result.error:
    print(result.error.code, result.error.message)
else:
    print(result.final_content)
```

下一步：阅读[选择合适的接口层](choose-your-layer.md)。
