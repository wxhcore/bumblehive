# 构建文件与代码助手

组合文件读取、修改、命令执行和人工审批，让 Agent 修正一个文本文件并验证结果。工作区固定在示例脚本旁，便于查看实际变化。

## 准备环境

完成[模型配置](../getting-started/installation.md#configure-model)，从仓库根目录运行：

```bash
python examples/runtime/file_assistant.py
```

脚本会创建 `examples/runtime/file-assistant-workspace/`，仅在 `notes.txt` 不存在时写入初始内容。修改文件和运行验证命令之前，终端都会展示调用参数并等待确认。

## 完整示例

```python title="examples/runtime/file_assistant.py"
--8<-- "examples/runtime/file_assistant.py"
```

## 观察运行结果

```text
读取 notes.txt → 请求修改 → 用户确认 → 修改文件
                                      → 读取结果 → 确认验证命令 → 返回结果
```

批准修改后，最终文件内容应为 `Bumblehive documentation`。拒绝时检查原文件是否保留；不要只依赖模型声称“修改成功”。重复运行时文件可能已经修正，Agent 不一定再请求修改。

## 换成你的项目

将 `workspace` 改为项目目录，提示词改为具体任务。只读工具自动批准；示例对其他开放工具逐次确认。`exec` 可以启动真实进程，工作目录不构成进程沙箱。接入你的应用时，复用同一审批接口呈现命令和参数。

[工具审批](../concepts/tool-safety.md) · [文件与命令](../how-to/files-and-commands.md) · [Runtime API](../reference/runtime.md)
