# 接入聊天界面

把 SDK 事件转换为界面更新：追加回答文本、显示工具进度、保存会话并支持停止。下面的示例打印 JSON 行，展示传输层之前的数据映射；完整浏览器应用可参考仓库中的 Server 和 WebUI。

## 运行事件适配示例

完成[模型配置](../getting-started/installation.md#configure-model)，执行：

```bash
python examples/runtime/chat_events.py
```

```python title="examples/runtime/chat_events.py"
--8<-- "examples/runtime/chat_events.py"
```

模型实际调用工具时，可观察到以下更新。不同模型的文本分块和工具选择可能不同：

```text
工具开始 → 工具完成 → 文本增量（多条） → 最终结果
```

## 映射界面状态

| 更新类型 | 界面处理 |
| --- | --- |
| `text_delta` | 追加到当前回答，而不是覆盖之前的文本 |
| `tool_started` | 按 `run_id` 和 `call_id` 新增工具状态 |
| `tool_finished` | 更新同一调用的状态，用 `ok` 区分成功与失败 |
| `finished` | 用最终文本校准回答，展示用量或错误，退出运行中状态 |

应用负责 WebSocket 或 SSE 传输、鉴权与页面渲染。不要把模型 API Key 发到浏览器。向界面传递工具内容时，应按应用需要选择字段。

## 保存与继续对话

示例使用固定 `session_id="chat-events-demo"`，重复运行会继续同一会话。真实应用为每段对话分配自己的 ID，并验证用户对该会话的访问权限。同一 Runtime 对同一个 ID 串行运行，不应让不同进程并发写入它。

## 处理停止与断开

将页面的停止按钮或连接断开事件转发给服务端，由服务端调用 `await stream.aclose()`，并向界面报告“已停止”。`finally` 中也应关闭流。

提前关闭会取消后台任务；此时不要再请求 `stream.result()`。已执行过的工具不会被撤销。流可能直接抛出异常，应用需要捕获并更新界面，不能让状态一直停留在“生成中”。

审批交互需要在 `approval_handler` 中等待对应请求的用户决定，不能仅靠事件 Hook 完成批准操作。

## 查看完整应用

- [服务端流式处理](https://github.com/wxhcore/bumblehive/blob/main/server/src/bumblehive_server/chat/streaming.py)
- [浏览器连接](https://github.com/wxhcore/bumblehive/blob/main/webui/src/api/chat-socket.ts)
- [前端事件处理](https://github.com/wxhcore/bumblehive/blob/main/webui/src/lib/chat-events.ts)

[流式输出](../how-to/streaming.md) · [会话与历史](../how-to/memory-and-sessions.md) · [事件参考](../reference/observability.md)
