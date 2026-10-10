"""医疗微调控制台的编排层（见 docs/superpowers/specs/2026-10-04-medical-finetune-console-design.md）。

编排服务整体跑在 WSL2 内（与 torch 同环境），把 docs/medical 的 12 步管线变成可编排的长任务。
不改 kev/train.py、kev/serve.py、kev/benchmark.py 任何代码。
"""
