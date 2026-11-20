# 图片输入

把图片和问题放在同一条消息中，让支持视觉的模型描述或分析图片。

## 使用图片地址

在已连接视觉模型的 `runtime` 中，把可访问的图片地址和问题放在一起：

```python
content = [
    {"type": "text", "text": "描述这张图片。"},
    {"type": "image_url", "image_url": {"url": image_url}},
]
result = await runtime.run([{"role": "user", "content": content}])
print(result.final_content)
```

将 `image_url` 设为模型服务能访问的 HTTPS 图片地址。

## 读取本地图片

完成[模型配置](../getting-started/installation.md#configure-model)，选择支持图片输入的模型，准备一张 PNG 或 JPEG 图片：

```bash
python examples/runtime/multimodal.py /你的路径/diagram.png
```

```python
--8<-- "examples/runtime/multimodal.py"
```

代码将图片编码为 Base64 Data URL，与文字一起放入 `content`。不需要给 Agent 开放文件工具。

运行后会打印模型对图片的描述。支持的格式和图片大小以模型服务的要求为准。

[消息格式参考](../reference/protocols.md)
