# Skills

Skill 提供一类任务的工作方法和资源路径。模型先看到摘要，需要时再读取详细说明。

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

## 加载并启用 Skill

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

如果 Skill 位于外部目录，可在已创建的 `runtime` 中安装到配置的 `skills_dir`：

```python
runtime.skills.install_skills([Path("./downloaded/course-summary")])
```

目标目录已存在同名 Skill 时，默认不会覆盖；需要替换时传入 `replace=True`。已直接放在 `skills_dir` 中的 Skill 无需重复安装。

模型最初只会看到 Skill 的名称、描述和文件路径。Runtime 会将安装目录作为只读目录提供给路径感知的内置文件工具；模型需要使用 `read_file` 打开 `SKILL.md`，因此启用 Skill 时通常也要开放 `read_file`。启用 `exec` 后可以直接运行其中的脚本，但当前没有子进程沙箱，输出位置仍应明确设为 workspace 或 `extra_write_roots`。

在工作目录准备 `notes.md`，写入需要整理的课程笔记。该 Skill 已位于 `skills_dir` 下，可以直接加载；在 `async main()` 中创建 Runtime 并运行：

```python
async with bumblehive.from_config(config) as runtime:
    result = await runtime.run("根据 notes.md 生成复习提纲")
    print(result.error.message if result.error else result.final_content)
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


## 运行与检查

完成[模型配置](../getting-started/installation.md#configure-model)，把以上配置和调用放入 `async main()`。调用 `list_skills()` 应能看到 `course-summary`；错误列表应为空。模型仍需实际读取 Skill，选中名称不代表脚本已经执行。

[完整加载示例](https://github.com/wxhcore/bumblehive/blob/main/examples/skills/basic.py) · [MCP 与 Skills API](../reference/skills.md)
