# 工具安全

工具可以读写文件或执行命令。正式项目应只向模型开放完成当前任务所需的工具。

## 先理解 `tool_names`

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

## Runtime 会注册哪些内置工具

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

相对路径从 `workspace` 解析。额外目录应尽量小，不要直接开放用户主目录或磁盘根目录。

`exec` 的 `working_dir` 可以位于任意可读目录中。子进程的 `PATH` 优先包含当前 Python 解释器所在目录，然后继承父进程中有效的绝对路径，因此当前 Python 环境可以直接使用；如果父进程的 `PATH` 包含 Conda，子进程也可以直接调用 `conda`。

```python
config = bumblehive.RuntimeArguments(
    workspace="./project",
    extra_read_roots=["./shared-docs"],
    extra_write_roots=["./output"],
    tool_names=["read_file", "write_file"],
)
```

## `PathAllowlist` 不是操作系统沙箱

路径白名单只约束 Bumblehive 中了解该规则的内置工具。

它不会自动限制：

- 自定义 Python 工具；
- MCP Server；
- `exec` 启动的子进程对文件系统的访问。

`exec` 不会静态解析命令中的绝对路径或 `../`。限制它的工作目录，只是在调用前校验进程的起始目录，不代表子进程无法读取或修改其他系统路径。

## 最小权限建议

1. 使用明确的 `tool_names`，不要在生产环境依赖 `None`。
2. 只开放必要的读写目录。
3. 面对不可信输入时，不开放 `exec`、`write_file` 或 `apply_patch`。
4. 自定义工具自行校验路径、用户身份和业务权限。
5. MCP 使用 `enabled_tools` 再过滤一次远端工具。

下一步：阅读[配置 Runtime](../how-to/configuration.md)。
