# 文件操作与命令执行

内置工具覆盖文件读写、搜索、补丁和命令执行。创建 Runtime 时显式指定工作目录与工具列表，让相对路径有明确起点。

## 选择工作区和工具

在[快速开始](../getting-started/installation.md)的 `RuntimeArguments` 中加入：

```python
import os
from pathlib import Path

import bumblehive

workspace = Path(__file__).resolve().parent
# 在创建 Runtime 的配置中使用：
config = bumblehive.RuntimeArguments(
    model=os.environ["BUMBLEHIVE_MODEL"],
    api_key=os.environ["BUMBLEHIVE_API_KEY"],
    base_url=os.environ["BUMBLEHIVE_BASE_URL"],
    workspace=workspace,
    tool_names=["read_file", "list_dir", "find_files", "grep"],
)
```

示例脚本中的相对路径从 `workspace` 解析，Python 交互环境没有 `__file__` 时请直接传入目录路径。

## 常用内置工具

| 任务 | 工具 | 典型输入 |
| --- | --- | --- |
| 阅读文件 | `read_file` | `path` |
| 写入文件 | `write_file` | `path`、`content` |
| 替换文本 | `edit_file` | `path`、替换前后的文本 |
| 应用补丁 | `apply_patch` | 补丁内容 |
| 列出和查找文件 | `list_dir`、`find_files` | 目录或匹配模式 |
| 搜索内容 | `grep` | 搜索词与范围 |
| 执行命令 | `exec` | `command`、`working_dir` |
| 跟进命令 | `write_stdin` | `session_id`、输入或轮询选项 |
| 查看命令会话 | `list_exec_sessions` | 当前会话范围 |

Runtime 会注册内置工具，但是否向模型开放取决于 `tool_names`。修改文件或执行命令时可以接入[人工审批](../concepts/tool-safety.md)。

## 直接验证文件工具

不调用模型也可以执行工具。这个完整示例在临时目录中写入、读取并列出文件，退出后自动清理：

```python title="examples/tools/builtins.py"
--8<-- "examples/tools/builtins.py"
```

从仓库根目录执行 `python examples/tools/builtins.py`，检查读取结果是否包含 `hello`。这也展示了额外可写目录的配置。

## 持续运行的命令

`exec` 省略 `yield_time_ms` 时等待命令结束；传入后，未完成的命令可返回 `session_id`。后续将该 ID 交给 `write_stdin`：

| 操作 | `write_stdin` 参数 |
| --- | --- |
| 查看新增输出 | `session_id` 与空 `chars` |
| 发送输入 | `session_id` 与 `chars` |
| 发送 EOF | `close_stdin=True` |
| 停止进程 | `terminate=True` |

默认命令超时为 60 秒。关闭 Runtime 会清理其管理的执行会话；应用应及时释放不再需要的资源。

## 文件访问范围

`workspace` 默认可读写，`extra_read_roots` 增加只读目录，`extra_write_roots` 增加可读写目录。`restrict_exec_paths=True` 增加命令路径检查，但不是操作系统沙箱；自定义工具、MCP 和子进程需要应用自行约束。

[工具与审批 API](../reference/tools.md) · [文件与代码助手](../examples/file-assistant.md)
