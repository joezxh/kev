# Kev 基础知识学习文档

> 面向"想读懂 Kev 这个仓库"的你：从第一性原理出发，把 **模型架构 · 训练框架 · 推理服务 · 评估系统** 四条主线讲清楚，
> 每个概念都配 **真实代码锚点**、**Mermaid 图表**，并有一个 **带数据流转动画的交互式页面**。

## 这套文档解决什么问题

Kev 不是"又一个会聊天的 LLM"。它是一族 **决策模型（decision models）**：给定一段"状态"（state，比如一份合同、
一条告警、一段工单）和若干"问题"（questions），它 **不生成任何文字**，而是对每个问题直接吐出一组 **经过校准的概率**。
理解 Kev 的难点不在深度学习有多深，而在于它把一整套不寻常的设计决策缝在了一起——这套文档就是来拆解这些决策的。

## 学习路线图

| # | 文档 | 你会搞懂 | 前置 |
|---|---|---|---|
| 00 | [交互式数据流转动画 →](./architecture-flow.html) | state → questions → probabilities 一次请求如何在模型里流动（动画） | 无（先看这个建立直觉） |
| 01 | [模型架构基础 →](./01-model-architecture.md) | causal LM、hybrid (DeltaNet)、block-causal mask、pointer readout | Transformer 基础 |
| 02 | [训练框架 →](./02-training-framework.md) | LoRA vs 全量、损失设计、数据管线、分布式/resume/snapshot | 01 |
| 03 | [推理服务 →](./03-inference-serving.md) | TypeSafe 契约、`/v1/systemone`、prefix cache、Docker/Modal/MLX 部署 | 01 |
| 04 | [评估系统 →](./04-evaluation-system.md) | 校准指标（ECE/Brier/NLL/AURC）、冻结套件、rounds 科研流程 | 01 |

## 建议的使用方式

1. **先在浏览器打开** [`architecture-flow.html`](./architecture-flow.html) —— 看一次推理请求的粒子如何沿着
   `encode → prefill → readout` 流动，建立"这玩意儿到底在算什么"的肌肉记忆。
2. **再读 01** —— 把动画里每个节点对应到 `kev/model.py` 的真实函数。
3. **按兴趣深入 02/03/04** —— 训练、服务、评估三条线相对独立，可以任选顺序。
4. **动手验证** —— 每个文档末尾有"跑一遍"小节，用一条 smoke 命令把阅读和运行对齐。

## 一条命令建立体感

在正式阅读前，先花 1 分钟跑通一次最小训练 + 一次评分，让抽象概念落地：

```bash
# 安装依赖（含 FastAPI 服务层）
uv sync --extra serve

# ~1 分钟 smoke 训练：每个公开数据源取 40 条
uv run python -m kev.train --n_per_source 40 --accum 4 --out runs/smoke

# 对一个冻结评测套件打分，产出 rows.json + report.json
uv run python -m kev.benchmark --run runs/smoke/checkpoint --suite evals/smoke-v1 --out runs/smoke-bench
```

## 代码锚点约定

文档中形如 [`kev/model.py:encode()`](../../kev/model.py) 的链接指向仓库真实文件。行号会随代码演进漂移，
所以正文更倾向引用 **函数名/类名/常量名**（如 `PointerHead`、`branch_mask_batch`、`SERVE_MAX_STATE`），
你可以在编辑器里用符号搜索（LSP）直接跳转，比行号更可靠。

## 术语小抄

| 术语 | 一句话解释 |
|---|---|
| state（状态） | 请求里的那段"待判断的文本"（文档/告警/工单），所有问题共享它 |
| question branch（问题分支） | 一个问题的指令 + 候选项 + `<decide>` 标记，编成一段 token |
| block-causal mask | 让分支能读 state、但读不到兄弟分支的注意力掩码 |
| pointer readout | 用 `<decide>` 的隐向量对每个 `</opt>` 边界隐向量做注意力打分，得到选项 logits |
| noul / choice / score | 三种问题类型：是/否、多选、有序等级评分 |
| temperature | 校准温度：推理时把 logits 除以它，让概率更可信（argmax 不变） |
| suite（套件） | 冻结的评测数据集，含 train/calibration/development/test 四个分区 |
| hybrid backbone | 含 Gated DeltaNet 线性注意力层的基座（Qwen3.5），无法用 block-causal 掩码，走 row 形式 |
