# Skills

Skill 是可复用的任务说明，可以附带脚本、参考资料和模板。下面让 Agent 按固定结构整理一份课程笔记。

## 一份最小 Skill

仓库中的 `examples/skills/course-summary/SKILL.md` 内容如下：

```markdown
--8<-- "examples/skills/course-summary/SKILL.md"
```

`name` 与目录名一致，使用小写字母、数字和连字符。`description` 帮助模型判断何时使用，正文说明具体步骤。

## 让 Agent 使用它

仓库已准备好 `examples/skills/notes.md`。完成[模型配置](../getting-started/installation.md#configure-model)，运行：

```bash
python examples/runtime/skills.py
```

```python
--8<-- "examples/runtime/skills.py"
```

`skills_dir` 指向存放各个 Skill 的根目录，`skill_names` 选择启用项。Agent 先看到名称、简介和路径，再使用 `read_file` 读取详细说明和笔记。

输出应按“核心概念、例子、易错点”三部分整理 Python 列表知识，例如把“索引从 0 开始”列入易错点。Skill 提供方法，读取笔记仍由工具完成。

## 换成自己的任务方法

复制 Skill 目录，修改名称、描述和正文，再调整示例的 `skills_dir`、`skill_names` 与任务。需要额外资源时再加入 `scripts/`、`references/` 或 `assets/`；模型使用资源仍需要相应的工具。

检查加载结果可以在已创建的 Runtime 中运行：

```python
catalog = runtime.skills.list_skills()
print([skill.name for skill in catalog.skills])
for error in catalog.errors:
    print(error.path, error.message)
```

安装外部 Skill、刷新和目录设置等接口见 [Skills 参考](../reference/skills.md)。
