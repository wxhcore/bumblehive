# 工具审批与访问范围

通过 `approval_handler` 在工具执行前批准或拒绝调用。工具白名单控制模型能调用什么，文件路径规则控制内置工具能访问哪里。

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

只有参数校验通过后才调用审批处理器。处理器抛出异常时，本次工具不会执行，错误以 `tool_approval_error` 交回 Agent。拒绝使用 `tool_approval_denied`；这不一定使整个运行失败。

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

用审批输出或事件确认处理器确实被调用。工具白名单与明确的提示词仍不能强制模型发起调用。

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

## 文件访问范围

内置文件工具默认可以：

- 在 `workspace` 中读写；
- 在 `extra_read_roots` 中读取；
- 在 `extra_write_roots` 中读写。

`readable roots` 是 `workspace`、`extra_read_roots` 和
`extra_write_roots` 合并后的有效可读目录集合；可写目录同时也是可读目录。相对路径从
`workspace` 解析。额外目录应尽量小，不要直接开放用户主目录或磁盘根目录。

默认 `restrict_exec_paths=False`：`working_dir` 可以是任意存在的目录，
不检查命令中的 `../` 和绝对路径。设为 `True` 后，`working_dir`
必须位于 `readable roots`，命令中的 `../` 会被拒绝，绝对路径必须位于
当前 `working_dir`。无论开关状态如何，内置危险命令正则都会执行。

子进程的 `PATH` 优先包含当前 Python 解释器所在目录，然后继承父进程中有效的绝对路径，因此当前 Python 环境可以直接使用；如果父进程的 `PATH` 包含 Conda，子进程也可以直接调用 `conda`。

```python
config = bumblehive.RuntimeArguments(
    workspace="./project",
    extra_read_roots=["./shared-docs"],
    extra_write_roots=["./output"],
    restrict_exec_paths=True,
    tool_names=["read_file", "write_file"],
)
```

### 路径策略的边界

路径策略只约束 Bumblehive 中了解该规则的内置工具。

它不会自动限制：

- 自定义 Python 工具；
- MCP Server；
- `exec` 启动的子进程对文件系统的访问。

`exec` 的命令路径检查只是对命令字符串的尽力而为检查，不会解析 Shell
变量、脚本内部访问或所有间接路径。即使开启 `restrict_exec_paths`，也不代表子进程受到操作系统沙箱限制。

## 相关接口

[工具与审批 API](../reference/tools.md) · [文件与命令](../how-to/files-and-commands.md) · [运行事件](../reference/observability.md)
