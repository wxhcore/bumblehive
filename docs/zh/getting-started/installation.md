# 安装 Bumblehive

本页将创建一个独立的 conda 环境，并安装 Bumblehive 。

## 1. 创建并激活虚拟环境

```bash
conda create -n bumblehive_env python=3.11 -y
conda activate bumblehive_env
```

虚拟环境可以把当前项目的依赖与其他 Python 项目隔离开。

## 2. 安装 Bumblehive

```bash
python -m pip install bumblehive
```

## 常见问题

### Python 版本过低

如果安装时提示 Python 版本不兼容，请安装 Python 3.11 或更高版本，然后重新创建虚拟环境。

## 下一步

[运行第一个 Agent](first-call.md)。
