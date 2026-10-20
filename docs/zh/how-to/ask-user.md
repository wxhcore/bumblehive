# 主动追问

用户让 Agent 写报告，却没有说明目标读者。Agent 可以先提问，拿到答案后再继续。用 SDK 注册一个自定义 `ask_user` 工具即可实现。

## 提问并等待回答

完成[模型配置](../getting-started/installation.md#configure-model)，运行：

```bash
python examples/runtime/ask_user.py
```

```python
--8<-- "examples/runtime/ask_user.py"
```

工具描述告诉模型什么时候提问；`read_answer()` 接收用户输入；工具把答案返回给模型。本例一直等待，直到用户回答或输入 `/skip`。

## 运行效果

```text
问题：这段 Python 开场白面向哪些读者？
  1. 没有编程经验的初学者
  2. 有其他语言经验的开发者
输入答案或选项编号；/skip 跳过：1
…Agent 为初学者写出开场白…
```

问题和选项由模型生成，实际措辞可能不同。输入编号会选择对应答案，也可以直接输入任何文字。不传 `options` 时只显示输入提示。输入 `/skip` 返回 `skipped`，Agent 按任务要求继续或说明缺少什么信息，不把跳过当成同意。

## 用户没有立即回答怎么办

不希望一直等待时，可以设置等待时长。这里复用[工具的等待与后台执行](background-tools.md)，不需要另写一套超时机制。

从仓库根目录运行以下进阶示例。它会导入上面的 `read_answer()` 和公共示例辅助代码：

```bash
python -m examples.runtime.ask_user_timeout
```

```python
--8<-- "examples/runtime/ask_user_timeout.py"
```

修改 `WAIT_SECONDS` 调整等待时间，例如改为 `5` 方便体验。这里的等待时长和返回状态都是示例定义的，不是 SDK 内置配置。

| 用户操作 | Agent 收到什么 |
| --- | --- |
| 等待期间回答 | 工具直接返回 `answered` 和答案 |
| 等待期间跳过 | 工具直接返回 `skipped` |
| 等待超时 | 工具返回 `pending`，输入仍然有效 |
| 超时后回答 | 原问题和答案作为后续消息送达 |
| 超时后跳过 | 结束提问，不再发送消息 |

例如先不回答，让等待超时：Agent 可以先给通用提纲。随后输入“初学者”，它会结合回答继续。运行中收到答案用 `steer()`；本轮已经结束则用原历史开始下一轮，具体代码集中在[后台工具示例](background-tools.md#delivery)。

`pending` 表示尚未回答。如果剩下的工作必须依赖答案，Agent 应说明阻碍并结束本轮；应用继续等待用户，不要猜测答案或反复提问。

这个终端示例使用一个输入口，适合一次回答一个问题。`input()` 在线程中等待，取消协程不能终止终端读取；退出前输入答案或 `/skip`。接入界面时，把 `read_answer()` 换成等待该问题提交事件的异步函数即可。
