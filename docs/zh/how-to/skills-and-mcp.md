# 使用 Skills 和 MCP

Skill 提供工作方法，MCP 提供远端工具。两者可以单独使用，也可以组合使用。

## 创建一个 Skill

一个 Skill 至少包含 `SKILL.md`：

```text
skills/
└── course-summary/
    ├── SKILL.md
    ├── scripts/       # 可选
    ├── references/    # 可选
    └── assets/        # 可选
```

`SKILL.md` 示例：

```markdown
---
name: course-summary
description: 把课程笔记整理成简洁的复习提纲。
---

# 课程提纲

1. 先读取用户指定的笔记。
2. 按“核心概念、例子、易错点”整理。
3. 不确定的内容明确标注，不要猜测。
```

名称必须满足两个条件：

- 使用小写字母、数字和连字符；
- `name` 与目录名完全相同。

## 安装并启用 Skill

```python
import os
from pathlib import Path

import bumblehive


config = bumblehive.RuntimeArguments(
    model=os.environ["BUMBLEHIVE_MODEL"],
    api_key=os.environ["BUMBLEHIVE_API_KEY"],
    base_url=os.environ["BUMBLEHIVE_BASE_URL"],
    workspace=".",
    skills_dir="./skills",
    skill_names=["course-summary"],
    tool_names=["read_file"],
)
```

`skills_dir` 指向包含各个 Skill 子目录的根目录。省略时默认使用 `~/.bumblehive/skills/`；目录会在首次安装 Skill 时创建，单纯创建 Runtime 或列出空目录不会创建它。

`SkillsManager` 也保留运行前切换目录的能力；切换时会清空旧目录的加载缓存，但不会立即创建新目录：

```python
manager = bumblehive.SkillsManager()
manager.set_skills_dir(Path("./other-skills"))
```

该方法适合独立使用 `SkillsManager`。Runtime 的 Skill 目录仍应通过 `RuntimeArguments.skills_dir` 在创建时确定，避免配置状态与实际目录不一致。

默认不会覆盖同名 Skill；确认需要替换时，再传入 `replace=True`。

模型最初只会看到 Skill 的名称、描述和文件路径。Runtime 会将安装目录作为只读目录提供给路径感知的内置文件工具；模型需要使用 `read_file` 打开 `SKILL.md`，因此启用 Skill 时通常也要开放 `read_file`。启用 `exec` 后可以直接运行其中的脚本，但当前没有子进程沙箱，输出位置仍应明确设为 workspace 或 `extra_write_roots`。

然后创建 Runtime，安装 Skill 并运行：

```python
async with bumblehive.from_config(config) as runtime:
    runtime.skills.install_skills([Path("skills/course-summary")])
    result = await runtime.run("根据 notes.md 生成复习提纲")
```

开发时可以检查加载结果：

```python
async with bumblehive.from_config(config) as runtime:
    catalog = runtime.skills.list_skills()

    print([skill.name for skill in catalog.skills])
    for error in catalog.errors:
        print(error.path, error.message)
```

`skill_names=None` 表示向模型提供全部已加载 Skill 的摘要，`[]` 表示不提供任何 Skill。正式项目建议明确列出名称。

## 连接 MCP Server

下面连接一个提供 `search` 工具的 HTTP MCP Server：

```python
import os

import bumblehive
from bumblehive.protocols import MCPServerConfig


docs_server = MCPServerConfig(
    name="docs",
    url=os.environ["DOCS_MCP_URL"],
    headers={
        "Authorization": f"Bearer {os.environ['DOCS_MCP_TOKEN']}"
    },
    tool_timeout=30,
    enabled_tools=["search"],
)

config = bumblehive.RuntimeArguments(
    model=os.environ["BUMBLEHIVE_MODEL"],
    api_key=os.environ["BUMBLEHIVE_API_KEY"],
    mcp_servers=(docs_server,),
    tool_names=["mcp_docs_search"],
)

async with bumblehive.from_config(config) as runtime:
    print(runtime.tools.registered_mcp_tool_names)
    result = await runtime.run("搜索安装 Bumblehive 的方法")
```

MCP 工具在本地的名称通常是：

```text
mcp_<server name>_<original tool name>
```

例如 `docs` Server 的 `search` 会注册为 `mcp_docs_search`。

## 两层工具过滤

MCP 有两层限制：

1. `enabled_tools` 决定从远端注册哪些工具；
2. Agent 的 `tool_names` 决定本次向模型开放哪些已注册工具。

`enabled_tools=["*"]` 会注册远端全部工具。面对第三方 Server 时，建议改成明确列表。

## 生命周期与安全

- Runtime 进入 `async with` 时连接 MCP，退出时关闭；
- MCP 配置不能通过单次 `run(config=...)` 修改；
- Header 只适用于 HTTP 或 SSE 传输；
- 默认工具超时为 30 秒；
- `ToolPathPolicy` 不会限制 MCP Server 的文件访问能力。

连接失败时，Runtime 初始化会直接抛出异常。请检查 URL、鉴权 Header 和 Server 是否可用。

下一步：阅读[处理运行错误](error-handling.md)。
