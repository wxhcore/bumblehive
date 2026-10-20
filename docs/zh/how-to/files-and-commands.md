# 文件操作与命令执行

内置工具覆盖文件读写、搜索、补丁和命令执行。创建 Runtime 时显式指定工作目录与工具列表，让相对路径有明确起点。

## 让 Agent 阅读文件

完成[模型配置](../getting-started/installation.md#configure-model)，运行 `python examples/runtime/files.py`：

```python
--8<-- "examples/runtime/files.py"
```

`workspace` 指向示例目录，`tool_names` 开放读取工具。运行后，Agent 应概括 `basic.py` 的配置、调用和输出流程。

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

从仓库根目录执行 `python examples/tools/builtins.py`，检查读取结果是否包含 `hello`。

## 持续运行的命令

`exec` 省略 `yield_time_ms` 时等待命令结束；传入后，未完成的命令可返回 `session_id`。后续将该 ID 交给 `write_stdin`：

| 操作 | `write_stdin` 参数 |
| --- | --- |
| 查看新增输出 | `session_id` 与空 `chars` |
| 发送输入 | `session_id` 与 `chars` |
| 发送 EOF | `close_stdin=True` |
| 停止进程 | `terminate=True` |

默认命令超时为 60 秒。关闭 Runtime 会清理其管理的执行会话；应用应及时释放不再需要的资源。

## 路径与工作目录 { #paths }

文件工具的 `path` 接受绝对路径和相对于 `workspace` 的路径。Shell 的 `working_dir` 省略时使用 workspace，也可以指定其他目录。

工作目录是路径解析起点，不是文件或进程沙箱；相对路径可以包含 `..`。需要用户决定是否执行时，接入[审批](../concepts/tool-safety.md)。Shell 命令还会检查自身的 `deny_patterns` 规则，匹配时拒绝执行。

子进程的 `PATH` 优先包含当前 Python 解释器目录，再继承父进程中的有效绝对路径。

[工具与审批 API](../reference/tools.md) · [文件与代码助手](../examples/file-assistant.md)
