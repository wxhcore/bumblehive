# 交互式聊天助手

将输入、流式回答和会话保存组合起来，得到一个可以连续对话的终端助手。

## 运行

完成[模型配置](../getting-started/installation.md#configure-model)，运行：

```bash
python examples/runtime/chat.py
```

```python
--8<-- "examples/runtime/chat.py"
```

## 体验对话

```text
你：记住，我的项目叫 BumbleHive。
Agent：…确认项目名称…
你：我的项目叫什么？
Agent：你的项目叫 BumbleHive。
你：/quit
```

同一个 `session_id` 保留对话，`stream()` 逐段输出回答。重新运行程序会继续 `chat-example` 会话；修改 ID 可以开始新对话。

## 接入界面 { #ui }

把终端输入换成用户消息事件，把输出换成界面更新即可。下面的适配示例将文本和工具事件转换成 JSON 行：

```bash
python examples/runtime/chat_events.py
```

```python
--8<-- "examples/runtime/chat_events.py"
```

| 更新 | 用途 |
| --- | --- |
| `text_delta` | 追加回答文本 |
| `tool_started` | 按 `run_id` 和 `call_id` 显示工具开始 |
| `tool_finished` | 更新同一个工具调用的结果 |
| `finished` | 显示最终回答或错误 |

需要人工参与时，接入[审批](../concepts/tool-safety.md)、[引导](../how-to/steering.md)或[追问](../how-to/ask-user.md)。这些交互的实现集中在对应教程中。
