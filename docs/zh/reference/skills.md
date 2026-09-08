# MCP 与 Skills

MCP 提供远端工具，Skills 提供任务说明和资源位置。两者有独立的配置、加载与关闭行为。

[MCP 指南](../how-to/mcp.md) · [Skills 指南](../how-to/skills.md) · [ToolManager](tools.md#bumblehive.tools.ToolManager)

## 常用接口

| 接口 | 用途 |
| --- | --- |
| [`MCPServerConfig`](#bumblehive.protocols.MCPServerConfig) | 连接 URL、HTTP Header、超时与远端工具过滤。 |
| [`MCPServerStatus`](#bumblehive.tools.MCPServerStatus) | 查询 MCP 连接状态和注册工具。 |
| [`SkillsManager`](#bumblehive.skills.SkillsManager) | 安装、加载、选择与删除本地 Skill。 |

## MCP 连接

连接 URL、HTTP Header、超时与远端工具过滤。应在创建 Runtime 时设置。

::: bumblehive.protocols.MCPServerConfig
    options:
      heading_level: 3
      show_root_heading: true
      show_root_full_path: false

查询 MCP 连接状态和注册工具。连接与关闭方法见 ToolManager。

::: bumblehive.tools.MCPServerStatus
    options:
      heading_level: 3
      show_root_heading: true
      show_root_full_path: false


## Skills 管理

安装、加载、选择与删除本地 Skill。

::: bumblehive.skills.SkillsManager
    options:
      heading_level: 3
      show_root_heading: true
      show_root_full_path: false

已加载的 Skill 元数据与路径。

::: bumblehive.skills.Skill
    options:
      heading_level: 3
      show_root_heading: true
      show_root_full_path: false

加载的 Skills 与非致命错误。

::: bumblehive.skills.SkillLoadResult
    options:
      heading_level: 3
      show_root_heading: true
      show_root_full_path: false

单个 Skill 的加载错误与路径。

::: bumblehive.skills.SkillError
    options:
      heading_level: 3
      show_root_heading: true
      show_root_full_path: false

把可用 Skills 生成面向模型的摘要。

::: bumblehive.skills.render_skills_summary
    options:
      heading_level: 3
      show_root_heading: true
      show_root_full_path: false
