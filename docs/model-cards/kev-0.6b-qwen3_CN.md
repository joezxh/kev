---
language: en
license: apache-2.0
library_name: peft
base_model: Qwen/Qwen3-0.6B-Base
base_model_relation: adapter
pipeline_tag: text-classification
tags:
  - decision-model
  - calibration
  - lora
  - multiple-choice
  - typesafe
  - decision-model
datasets:
  - legacy-datasets/banking77
  - google/boolq
  - fancyzhx/ag_news
  - nyu-mll/multi_nli
  - SetFit/sst5
  - Yelp/yelp_review_full
  - CogComp/trec
  - fancyzhx/dbpedia_14
  - SetFit/amazon_reviews_multi_en
  - stanfordnlp/imdb
metrics:
  - accuracy
  - brier_score
  - expected_calibration_error
model-index:
  - name: Kev-0.6B (Qwen3)
    results:
      - task: { type: text-classification, name: typed decision (choice / noul / score) }
        dataset: { type: mixed, name: "decision-v4 development (1,204 records; ten trained public sources + programmatic policy pairs)" }
        metrics:
          - { type: accuracy, value: 0.801 }
          - { type: expected_calibration_error, value: 0.086, name: "ECE, raw probabilities" }
      - task: { type: text-classification, name: typed decision, out-of-domain }
        dataset: { type: mixed, name: "transfer-v4 development (764 records; six never-trained sources + held-out policy structures)" }
        metrics:
          - { type: accuracy, value: 0.620 }
          - { type: brier_score, value: 0.536 }
---

<p align="center">
  <a href="./kev-0.6b-qwen3_CN.md"><img alt="中文" src="https://img.shields.io/badge/%E4%B8%AD%E6%96%87-orange?style=for-the-badge"></a>
  <a href="./kev-0.6b-qwen3.md"><img alt="English" src="https://img.shields.io/badge/English-blue?style=for-the-badge"></a>
</p>


# Kev-0.6B (Qwen3)

> **上一代（Qwen3）。** 作为 Apple Silicon 上的快速小模型选项保留（每个五问题请求 0.12 秒，而 Kev-0.8B 为 0.33 秒）。就准确率而言请使用 [Kev-0.8B](kev-0.8b.md)：在锁定测试（locked test）上，对相同的样本，本模型域外得分为 0.642，而其为 0.668。权重：`jaredpalmer/kev-0.6b`。

Kev-0.6B 是一个**决策模型**：一篇文档（即 *state*，状态）与一组带类型的问题作为输入，每个问题输出一个概率分布，在一次前向传播中完成。不生成文本。它是一个 LoRA 适配器（r=16）加上一个指针头，建立在 `Qwen/Qwen3-0.6B-Base` 之上，并服务于 TypeSafe 公开的 `/v1/systemone` 契约。

**Kev 家族中的小成员。** 在冻结、做校验和（checksummed）的评估协议下，它是表现最好的 0.6B 检查点：采用 4B/8B 配方的数据（`decision-v7`），学习率 lr 1e-4，三个种子（域外 0.613 / 0.605 / **0.620**），在经过八次单参数变动（one-knob mutation）以及基于先前数据三个种子的探索后，未发现优于 0.61 的方案。在域外它就是一个 0.6B 模型——若追求准确率请使用 Kev-4B；在内存或延迟使得 4B 不可行之处使用本模型，并在你自己的数据上进行测量。

- Hub：`jaredpalmer/kev-0.6b`（本仓库；试验 `v7-06b/02-trial-2`，三个种子中的种子 2）
- 代码、测试套件、结果与完整研究日志：[github.com/jaredpalmer/kev](https://github.com/jaredpalmer/kev) —— 参见 `PLAN.md`（完整记录在 git 标签 `research-archive-2026-09-24`）、`runs/leaderboard.md` 和 `evals/v4/*/manifest.json`

## 自 Kev-0.5B 以来的变化

| | Kev-0.5B | Kev-0.6B（本模型） |
|---|---|---|
| 主干网络 | Qwen2.5-0.5B | Qwen3-0.6B-Base |
| 训练记录 | 9,000（六个数据源） | 12,576（十个公开数据源 + 896 个策略最小对 + 来自 60 个随机规则结构的 1,680 条记录） |
| 无上述选项（none-of-the-above） | 仅增强修复 | + 最小对：同一状态分别渲染为包含与移除正确选项 |
| 分布内准确率（decision-v4 dev） | 0.712 | **0.801** |
| 域外准确率（transfer-v4 dev） | 0.561 | **0.620** |
| 无选项存在时的准确率 | 0.25（transfer-v1） | 0.80 |
| 数字背后的种子数 | 1 | 3（域外 0.605–0.620） |

Jev（`typesafe-ai/jev`，经 Vercel AI Gateway）在相同的冻结开发集上：分布内 **0.845**，域外 **0.857**。该检查点各数据源的域外准确率：QNLI 0.85、SciQ 0.93、TweetEval-offensive 0.69、PAWS 0.59、Emotion 0.49、MMLU 0.50；留出策略结构接近随机水平。

## 已知局限

- **域外它就是一个 0.6B 模型。** 域外准确率在我们尝试的每个超参数下都平稳维持在约 0.60（八次单参数变动，三个种子）。同一配方在 4B 上达到 0.72–0.75，在 8B 上达到 0.74–0.77；在此规模下瓶颈是容量而非数据。
- **留出的策略推理失败**：对于从未训练过规则结构的程序化策略对（programmatic policy pairs），两个兄弟都正确的比例为 6–11%（Kev-4B 为 0.73，Jev 为 0.86）。
- **有序性保守（ordinal hedging）**：在带有日期运算的 3 等级 Score 问题上，它会塌缩到中间等级。
- 域外的置信错误率为 11%（置信度 ≥0.9 且错误）；原始 ECE 在域内为 0.09，域外为 0.15。概率在域内可用；在其他地方请将其视为参考性意见。
- **锁定测试，只读一次**（`runs/locked/kev-06b-v7-ungated/`）：分布内准确率 **0.808**（Brier 0.266，ECE 0.089），域外 **0.642**（Brier 0.483，ECE 0.128，置信错误 7.9%）。该分区将不再为本检查点读取。

## 架构

仅预填充（prefill-only）的因果 LM，带有块因果注意力掩码：一个共享的状态前缀、每个问题一个隔离分支，以及对选项边界 token 的指针读出（pointer readout）。打包进一个请求的问题得到的正是它们单独请求时会得到的概率（测得最大差值 4e-6）。详见仓库 README。

## 训练

冻结套件 `evals/v7/decision-v7`（manifest 固定了数据集与基座模型的版本）：10,000 条公开记录（每数据源 1,000 条）、覆盖九个模板族的 896 条策略最小对记录，以及来自 60 个随机生成规则结构的 1,680 条记录，两个 epoch，注意力与 MLP 投影上 LoRA r=16，学习率 lr 1e-4，从头训练指针头，对选项分布的交叉熵，bf16 自动混合精度（autocast）配合 fp32 主权重，在单张 H100 上（约 12 分钟）。增强：选项排列、无上述选项插入、干扰项，以及在 25% 的 Choice 记录上的无最小对。训练未使用任何 Jev 输出。

## 评估协议

开发分区用于筛选模型；存在一个锁定测试分区，每个晋级候选最多读取一次。上述每个数字都带有套件哈希、代码哈希以及 `result.json` 中的 git commit。对比使用记录聚类的配对 bootstrap。参见 git 标签 `research-archive-2026-09-24` 处的 `PLAN.md`（"Evidence and corrections"）中关于我们对自身早期声明所做修正的说明。

## 使用

```python
from typesafe import TypeSafeClient   # 任何 TypeSafe 兼容的客户端
client = TypeSafeClient(api_key="local", base_url="http://127.0.0.1:8008", model="kev-latest")
```

从仓库使用 `uv run --extra serve python -m kev.serve --run jaredpalmer/kev-0.6b --port 8008` 启动服务。

## 许可证

适配器与头为 Apache-2.0。基座模型为 Apache-2.0（Qwen3）。训练数据集各自带有其许可证。
