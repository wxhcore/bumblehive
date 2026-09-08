# 配置与模型 Provider

使用 RuntimeArguments 创建简单配置，BumblehiveConfig 保存分层配置。单次 config 覆盖会深度合并，不会修改基础配置。MCP 连接与 Skills 目录不能在单次调用中更换。

[模型配置指南](../how-to/configuration.md) · [自定义 Provider](../development/adding-a-provider.md)

## 常用接口

| 接口 | 用途 |
| --- | --- |
| [`RuntimeArguments`](#bumblehive.config.RuntimeArguments) | 常用扁平配置，适合在 Python 中直接创建。 |
| [`BumblehiveConfig`](#bumblehive.config.BumblehiveConfig) | 分层配置，支持字典与 JSON。 |
| [`GenerationConfig`](#bumblehive.protocols.GenerationConfig) | 温度、输出预算、推理参数和供应商扩展字段；可用性取决于模型。 |
| [`ModelProvider`](#bumblehive.providers.ModelProvider) | 自定义 Provider 的基类，实现 generate()，需要时实现流式生成和关闭。 |

## 应用配置

常用扁平配置，适合在 Python 中直接创建。

::: bumblehive.config.RuntimeArguments
    options:
      heading_level: 3
      show_root_heading: true
      show_root_full_path: false

分层配置，支持字典与 JSON。

::: bumblehive.config.BumblehiveConfig
    options:
      heading_level: 3
      show_root_heading: true
      show_root_full_path: false

模型名、密钥、Base URL 与 Provider 类型。

::: bumblehive.config.ProviderConfig
    options:
      heading_level: 3
      show_root_heading: true
      show_root_full_path: false

指令、动态上下文和能力选择。

::: bumblehive.config.AgentConfig
    options:
      heading_level: 3
      show_root_heading: true
      show_root_full_path: false

工作目录、上下文预算、迭代次数和文件路径规则。

::: bumblehive.config.RuntimeConfig
    options:
      heading_level: 3
      show_root_heading: true
      show_root_full_path: false

配置入口接受的输入类型。

::: bumblehive.config.ConfigInput
    options:
      heading_level: 3
      show_root_heading: true
      show_root_full_path: false

将配置输入转换成配置对象。

::: bumblehive.config.load_config
    options:
      heading_level: 3
      show_root_heading: true
      show_root_full_path: false

从 JSON 文件读取配置。

::: bumblehive.config.load_json_config
    options:
      heading_level: 3
      show_root_heading: true
      show_root_full_path: false


## 生成参数

温度、输出预算、推理参数和供应商扩展字段；可用性取决于模型。

::: bumblehive.protocols.GenerationConfig
    options:
      heading_level: 3
      show_root_heading: true
      show_root_full_path: false


## 模型接入

自定义 Provider 的基类，实现 generate()，需要时实现流式生成和关闭。

::: bumblehive.providers.ModelProvider
    options:
      heading_level: 3
      show_root_heading: true
      show_root_full_path: false

高层 Runtime 当前使用的 Chat Completions 兼容实现。

::: bumblehive.providers.OpenAIChatCompletionsProvider
    options:
      heading_level: 3
      show_root_heading: true
      show_root_full_path: false

按连接配置缓存 Provider，关闭时释放连接。

::: bumblehive.providers.ProviderManager
    options:
      heading_level: 3
      show_root_heading: true
      show_root_full_path: false

发送给模型的统一请求。

::: bumblehive.providers.ModelRequest
    options:
      heading_level: 3
      show_root_heading: true
      show_root_full_path: false

模型回答、工具请求、用量和结构化错误。

::: bumblehive.providers.ModelResponse
    options:
      heading_level: 3
      show_root_heading: true
      show_root_full_path: false

模型流式内容的回调接口。

::: bumblehive.providers.ModelStreamCallbacks
    options:
      heading_level: 3
      show_root_heading: true
      show_root_full_path: false

可恢复模型请求的重试设置。

::: bumblehive.providers.RetryConfig
    options:
      heading_level: 3
      show_root_heading: true
      show_root_full_path: false
