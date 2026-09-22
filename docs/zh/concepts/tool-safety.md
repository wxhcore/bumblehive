# 工具审批与执行

通过 `tool_names` 选择可用工具，通过 `approval_handler` 在工具执行前批准或拒绝调用。

## 等待用户确认

先完成[模型配置](../getting-started/installation.md#configure-model)，从仓库根目录运行：

```bash
python examples/runtime/tool_approval.py
```

```python title="examples/runtime/tool_approval.py"
--8<-- "examples/runtime/tool_approval.py"
```

示例把工作目录设为脚本所在的 `examples/runtime/`，并打印绝对路径。模型请求调用后，终端展示工具名称和校验后的参数：输入 `y` 或 `yes` 批准，回车或其他输入拒绝。

批准后工具会创建或覆盖 `approval-demo.txt`，内容为 `hello`。拒绝后本次调用不会修改文件，原因交回 Agent。通过 Conda 运行时使用 `conda run --no-capture-output -n bumblehive_env python examples/runtime/tool_approval.py`，以保留输入输出。

## 执行顺序

```text
模型请求工具 → 参数校验 → 等待审批 → 批准：执行工具
                                  → 拒绝：返回拒绝原因
```

参数校验通过后，SDK 将工具名称和校验后的参数交给审批处理器，路径参数保持调用时的相对或绝对路径形式。处理器抛出异常时，本次工具不会执行，错误以 `tool_approval_error` 交回 Agent。拒绝使用 `tool_approval_denied`；这不一定使整个运行失败。未配置 `approval_handler` 时，SDK 直接进入工具执行阶段。

## 按规则自动拒绝

下面的片段在已创建的 `runtime` 中运行，将审批改为固定策略：

```python
from bumblehive import ToolApprovalDecision, ToolApprovalRequest

async def approve_tool(request: ToolApprovalRequest) -> ToolApprovalDecision:
    print("已拒绝工具调用：", request.name)
    return ToolApprovalDecision.reject("当前任务不允许写入文件。")

result = await runtime.run(
    "请调用 write_file 创建 approval-demo.txt，内容为 hello。"
    "如果被拒绝，不要重试，说明文件未创建。",
    config={"agent": {"tool_names": ["write_file"]}},
    approval_handler=approve_tool,
)
```

通过审批输出或事件确认处理器是否被调用；模型根据任务决定是否调用已开放的工具。

## 在界面中显示审批

`tool.approval.started` 和 `tool.approval.finished` 位于 `tool.call.started` 与 `tool.call.finished` 之间，用 `call_id` 关联请求。同一并行批次可能存在多个待审批请求，界面应分别保存状态；用户选择通过审批处理器返回，事件 Hook 负责展示和记录。

## 选择可用工具

| 配置 | 含义 |
| --- | --- |
| 省略 `tool_names` 或传入 `None` | 开放全部已注册工具 |
| `tool_names=[]` | 不开放任何工具 |
| `tool_names=["read_file"]` | 只开放列出的工具 |

`None` 和空列表含义完全不同。初学者的第一次调用建议使用 `[]`。

```python
import os

import bumblehive


config = bumblehive.RuntimeArguments(
    model=os.environ["BUMBLEHIVE_MODEL"],
    api_key=os.environ["BUMBLEHIVE_API_KEY"],
    workspace="./workspace",
    tool_names=["read_file", "list_dir"],
)
```

### 内置工具

第一次初始化时会注册：

- 文件：`read_file`、`write_file`、`edit_file`、`apply_patch`；
- 查找：`list_dir`、`find_files`、`grep`；
- 命令：`exec`、`write_stdin`、`list_exec_sessions`。

注册不等于开放。模型最终能否看到并执行某个工具，仍由 `tool_names` 决定。

## 路径与工作目录

文件工具接受绝对路径和相对路径。相对路径以本次 `workspace` 为基准，`~` 展开为用户主目录。例如，workspace 为 `/project/app` 时，`notes.txt` 解析为 `/project/app/notes.txt`，`../data.txt` 解析为 `/project/data.txt`。

`exec` 的 `working_dir` 指定命令执行目录，相对路径以 workspace 为基准，省略时使用 workspace。该目录必须存在。

Shell 在启动命令前检查 `deny_patterns`，匹配禁止规则时返回 `command blocked by safety policy`。这项检查在审批通过和未配置审批处理器时都会执行。

子进程的 `PATH` 优先包含当前 Python 解释器所在目录，然后继承父进程中有效的绝对路径，因此当前 Python 环境可以直接使用；如果父进程的 `PATH` 包含 Conda，子进程也可以直接调用 `conda`。

## 相关接口

[工具与审批 API](../reference/tools.md) · [文件与命令](../how-to/files-and-commands.md) · [运行事件](../reference/observability.md)
