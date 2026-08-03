# 配置

Bumblehive 提供两种常用配置方式：

- 简单项目使用 `RuntimeArguments`。
- 需要保存或分层管理时使用 `BumblehiveConfig`。

单次 `run()` 可以通过 `config` 覆盖部分设置，但不能在单次运行中更换 `mcp_servers`。

| 配置对象 | 负责内容 |
| --- | --- |
| `ProviderConfig` | 模型、API Key 和 Base URL |
| `AgentConfig` | 指令、动态上下文、Skills 和工具选择 |
| `RuntimeConfig` | 工作区、时区、上下文和迭代限制 |
| `GenerationConfig` | 温度、输出长度和模型扩展参数 |

## 公开接口

::: bumblehive.config
    options:
      show_root_heading: false
      show_root_full_path: false
