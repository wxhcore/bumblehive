# 图片输入

将图片和文字放入同一条消息，交给支持视觉的模型。图片可以来自 URL 或 Base64 Data URL。

## 发送图片

先完成[模型配置](../getting-started/installation.md#configure-model)，选择支持图片输入的模型。下面片段在已创建的 `runtime` 中运行：

```python
import base64
from pathlib import Path

image = base64.b64encode(Path("diagram.png").read_bytes()).decode("ascii")
result = await runtime.run([
    {
        "role": "user",
        "content": [
            {"type": "text", "text": "描述这张架构图中的主要模块。"},
            {"type": "image_url", "image_url": {
                "url": f"data:image/png;base64,{image}",
            }},
        ],
    },
])
if result.error:
    print(result.error.message)
else:
    print(result.final_content)
```

准备当前目录下的 `diagram.png`。程序直接读取并编码图片，不需要向 Agent 开放文件工具。预期结果是模型返回的图片说明。

## 使用远程图片

把 `url` 替换成模型服务可以读取的 HTTPS 图片地址。使用其他图片格式时，相应调整 Data URL 的 MIME 类型。SDK 传递消息，不会替不支持视觉的模型增加图片理解能力。

[URL 示例源码](https://github.com/wxhcore/bumblehive/blob/main/examples/runtime/multimodal.py) 使用占位图片地址，运行前必须替换。不要将占位地址作为可用资源。

[消息类型参考](../reference/protocols.md) · [模型配置](configuration.md)
