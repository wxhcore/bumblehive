# 子 Agent 协作

把独立任务交给另一个 Agent，再使用它的结果完成主任务。实现方式是将一次 `runtime.run()` 封装成工具，也就是 Agent as Tool。

## 委派任务并等待结果

完成[模型配置](../getting-started/installation.md#configure-model)，从仓库根目录运行：

```bash
python examples/runtime/multi_agent.py
```

```python
--8<-- "examples/runtime/multi_agent.py"
```

主 Agent 调用 `sub_agent`，子 Agent 阅读 `README_zh.md` 并概括项目用途，主 Agent 再整理回答。

- 子调用没有传入历史，因此不会自动继承主 Agent 的对话。任务描述应包含它需要的信息。
- 子调用只开放文件读取和搜索工具。它仍复用 Runtime 的模型配置与工作目录。
- 子调用返回的文本就是工具结果，主 Agent 会等待它完成。

## 后台委派

如果主 Agent 还有独立工作，可以让子任务后台执行。下面复用[后台工具](../how-to/background-tools.md)的示例辅助代码：

```bash
python -m examples.runtime.multi_agent_background
```

```python
--8<-- "examples/runtime/multi_agent_background.py"
```

运行过程类似：

```text
主 Agent：委派练习题 → 拟文章提纲
子 Agent：设计练习题 → 结果送回主 Agent
主 Agent：将提纲与练习题整合
```

本例的 `sub_agent` 默认 `background=True`。如果下一步依赖结果，传 `background=False`，工具就等待完成后返回。可以将提示词改为“先让子 Agent 设计练习题，调用时传 background=false，再围绕练习题组织文章”来体验。

`sub_agent` 和 `background` 都是示例注册的工具及参数，不是 `runtime.run()` 的内置选项。等待、后台返回和后续投递的共同机制只在[后台工具教程](../how-to/background-tools.md)中解释。

子调用若需要人工审批，应像普通调用一样传入 `approval_handler`，主调用的回调不会自动传给它。
