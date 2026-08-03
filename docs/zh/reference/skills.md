# Skills

Skill 是一个包含 `SKILL.md` 的本地能力包。它主要向模型提供说明和资源位置，不等同于 Python 工具。

| 接口 | 用途 |
| --- | --- |
| `SkillsManager` | 安装、加载、删除和选择 Skills |
| `Skill` | 一个已加载 Skill 的信息 |
| `SkillLoadResult` | Skills 和非致命加载错误 |
| `SkillError` | 单个 Skill 的加载错误 |

`skill_names=None` 表示向模型提供全部已加载 Skill 的摘要，`skill_names=[]` 表示不提供任何 Skill。

## 公开接口

::: bumblehive.skills
    options:
      show_root_heading: false
      show_root_full_path: false
