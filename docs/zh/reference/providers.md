# 模型 Provider

`ModelProvider` 把不同模型服务转换成 Bumblehive 使用的统一请求和响应。

| 接口 | 用途 |
| --- | --- |
| `ModelProvider` | 自定义 Provider 的抽象基类 |
| `ModelRequest` | 发送给模型的统一请求 |
| `ModelResponse` | Provider 返回的统一结果 |
| `RetryConfig` | 可恢复错误的重试设置 |
| `ProviderManager` | 缓存并关闭默认 Provider |

当前高层 Runtime 创建的是 `openai_chat_completions` Provider。接入自定义 Provider 时，请使用 `AgentLoop` 并显式传入 Provider。

## 公开接口

::: bumblehive.providers
    options:
      show_root_heading: false
      show_root_full_path: false
