"""阶段处理器的包标记：注册表在 Task 5 建成（见 .git/sdd/task-5-brief.md Step 6）。

先存在这里是因为 pyproject.toml 的 [tool.setuptools] packages 已经声明了 kev.console.stages，
setuptools 遇到声明了却缺失的包目录会直接构建失败（`package directory ... does not exist`），
那会让 `uv run`（进而让整个测试套件）在本任务里跑不起来。本文件不含任何实现。
"""
