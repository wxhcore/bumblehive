# 参与 SDK 开发

Python SDK 的源码位于 `src/bumblehive/`，示例位于 `examples/`。底层接口的分工见[自定义 Provider 与底层组装](adding-a-provider.md)。修改内置工具时，实现在 `src/bumblehive/tools/builtins/`，对应测试在 `tests/tools/`。

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

用假 Provider 测试模型调用、验证工具参数的例子见[测试一个 Agent](../how-to/testing-an-agent.md)。

## 检查文档

```bash
python -m mkdocs build --strict -f mkdocs.zh.yml
python -m mkdocs build --strict -f mkdocs.en.yml
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
