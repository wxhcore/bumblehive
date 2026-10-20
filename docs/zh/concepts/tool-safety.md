# 审批：执行前征求同意

当 Agent 要写文件或执行需要用户确认的操作时，用 `approval_handler` 决定是否允许执行。审批发生在工具参数校验之后、实际执行之前。

## 让用户批准一次写入

完成[模型配置](../getting-started/installation.md#configure-model)，从仓库根目录运行：

```bash
python examples/runtime/tool_approval.py
```

```python
--8<-- "examples/runtime/tool_approval.py"
```

`approve_tool()` 收到工具名称和参数，等待用户输入，再返回 `approve()` 或 `reject()`。把它传给 `runtime.run()` 的 `approval_handler` 即可启用。

## 运行效果

```text
工作目录：…/examples/runtime
工具：write_file
参数：{'path': 'approval-demo.txt', 'content': 'hello'}
允许执行？[y/N] y
已批准
…模型说明文件已经写入…
```

输入 `y` 或 `yes` 后，工具会写入 `approval-demo.txt`，可能覆盖同名文件。回车或输入其他内容会拒绝，本次写入不执行，拒绝原因会交回模型。模型的具体措辞可能不同。

## 只对部分操作询问

如果还开放了只读工具，可以在回调开头自动放行它们，其余操作继续询问：

```python
if request.name in {"read_file", "list_dir", "find_files", "grep"}:
    return bumblehive.ToolApprovalDecision.approve()
```

工具的可用范围由 `tool_names` 决定，详见[工具调用](../getting-started/first-tool.md#tool-selection)。未传 `approval_handler` 时不会自动询问。

接入自己的界面时，把 `input()` 换成等待用户选择的异步函数，仍然返回同一种审批决定。完整组合见[文件助手](../examples/file-assistant.md)。

[审批接口参考](../reference/tools.md) · [文件路径与工作目录](../how-to/files-and-commands.md#paths)
