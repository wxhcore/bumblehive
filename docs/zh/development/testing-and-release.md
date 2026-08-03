# 测试与发布检查

## 安装开发依赖

只开发 Python SDK 时：

```bash
python -m pip install -e ".[dev,docs]"
```

不需要安装 Web 或桌面端依赖。

## 运行测试

```bash
python -m pytest
```

修改某个模块时，可以先运行对应目录：

```bash
python -m pytest tests/tools
python -m pytest tests/agent
```

## 测试 Agent

不要让普通单元测试依赖真实模型服务。推荐使用一个按顺序返回 `ModelResponse` 的假 Provider。

重点测试：

- 模型能看到哪些工具。
- 工具参数是否正确。
- 工具失败后返回什么错误。
- History 是否按预期更新。
- 最大迭代和模型错误是否写入 `AgentRunResult.error`。

## 检查文档

```bash
python -m mkdocs build --strict -f mkdocs.zh.yml
python docs/scripts/check_api_coverage.py
```

`--strict` 会把文档警告作为构建失败处理。

## 修改公开接口时

如果修改模块的 `__all__`，同时检查：

1. `tests/test_public_api.py`。
2. 对应 API Reference 页面。
3. 至少一个使用示例。
4. README 或迁移说明是否需要更新。

内部对象不应为了方便而随意重新导出。公开接口一旦发布，就会成为用户依赖的契约。
