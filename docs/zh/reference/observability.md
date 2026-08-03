# 事件与可观测性

Hook 用于接收 Agent 运行事件。它适合日志、调试、界面输出和测试。

```python
from bumblehive import EventRecorder

recorder = EventRecorder()
result = await runtime.run("你好", hooks=recorder)
print([event.kind for event in recorder.events])
```

常用事件：

| 事件 | 含义 |
| --- | --- |
| `turn.started` | 开始处理用户输入 |
| `model.request.started` | 开始请求模型 |
| `model.stream.content_delta` | 收到一段流式文本 |
| `tool.call.finished` | 一个工具执行完成 |
| `final_result` | 得到最终结果 |
| `turn.error` | 本轮抛出异常 |

## 公开接口

::: bumblehive.observability
    options:
      show_root_heading: false
      show_root_full_path: false
