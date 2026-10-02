---
language: en
license: apache-2.0
library_name: peft
base_model: Qwen/Qwen3-8B-Base
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
  - allenai/ai2_arc
  - allenai/openbookqa
  - tau/commonsense_qa
metrics:
  - accuracy
  - brier_score
  - expected_calibration_error
model-index:
  - name: Kev-8B (Qwen3)
    results:
      - task: { type: text-classification, name: typed decision (choice / noul / score) }
        dataset: { type: mixed, name: "decision-v4/v6 development (1,204 records; trained public sources + programmatic policy pairs)" }
        metrics:
          - { type: accuracy, value: 0.869 }
          - { type: expected_calibration_error, value: 0.061, name: "ECE, raw probabilities" }
      - task: { type: text-classification, name: typed decision, out-of-domain }
        dataset: { type: mixed, name: "transfer-v4 development (764 records; six never-trained sources + held-out policy structures)" }
        metrics:
          - { type: accuracy, value: 0.796 }
          - { type: brier_score, value: 0.337 }
---

# Kev-8B (Qwen3)

> **上一代（Qwen3）。** 该检查点作为 Apple Silicon 上的快速选项保留（其仅注意力的主干网络在 MPS 上以全速运行打包前向传播）。就准确率与校准而言请使用 [Kev-9B](kev-9b.md)：在锁定测试上，对相同的样本，本模型域外得分为 0.780，而其为 0.837。权重：`jaredpalmer/kev-8b`。

Kev-8B 是一个**决策模型**：一篇文档（即 *state*，状态）与一组带类型的问题作为输入，每个问题输出一个概率分布，在一次前向传播中完成。不生成文本。它是一个 LoRA 适配器（r=16）加上一个指针头，建立在 `Qwen/Qwen3-8B-Base`（版本 `49e3418f`）之上，服务于 TypeSafe 公开的 `/v1/systemone` 契约。

**最准确的 Kev。** 在冻结、做校验和（checksummed）的协议下，任何规模中表现最好的检查点：最佳的分布内准确率、最佳的域外准确率（transfer-v4 dev 上 0.796，距 Jev 六个点）、任何 Kev 在 8B 上最佳的留出规则推理。同一配方以两个种子运行：0.796 / 0.774；本检查点是开发分区上选定的种子。

- Hub：`jaredpalmer/kev-8b`（本仓库；试验 `v7-final/00-trial-0`）
- 代码、测试套件、每次带哈希与配对 bootstrap 的试验：[github.com/jaredpalmer/kev](https://github.com/jaredpalmer/kev) —— `PLAN.md`（完整记录在 git 标签 `research-archive-2026-09-24`）、`runs/leaderboard.md`

## 结果（每一行使用相同的冻结样本）

| | Kev-0.5B（原型） | Kev-0.6B | Kev-4B | **Kev-8B** | Jev |
|---|---|---|---|---|
| 分布内准确率（decision-v4 dev，1,200 q） | 0.712 | 0.801 | 0.854 | **0.863** | 0.845 |
| 域外准确率（transfer-v4 dev，560 q） | 0.561 | 0.620 | 0.790 | **0.796** | 0.857 |
| 域外 Brier | 0.50 | 0.536 | 0.328 | **0.337** | 0.211 |
| 域外置信错误（p ≥ 0.9 且错误） | – | 10.8% | 8.2% | 9.9% | 3.7% |
| 留出策略结构，两个兄弟都正确 | – | 0.08 | 0.73 | 0.69 | 0.86 |
| 选项顺序翻转率 | 0.21 | 0.02 | 0.00 | 0.00 | 0.00 |

各数据源域外准确率（Kev-8B / Jev）：QNLI 0.91 / 0.93、SciQ 1.00 / 0.99、TweetEval-offensive 0.79 / 0.81、PAWS 0.78 / 0.79、MMLU 0.70 / 0.90、Emotion 0.56 / 0.59、deadline（3 等级日期运算）0.60 / 0.93、(A and B) or not C 0.91 / 0.97、if A then not B else C 0.59 / 0.78。

种子：在 decision-v7 上的两个种子：域外 **0.796** / 0.774，留出规则对 0.69 / 0.64（Jev 0.86）；本检查点为种子 0。训练于 `decision-v7`（1 万条公开记录 + 覆盖九个模板族的 896 条策略记录，含四个有序 Score 阈值族 + 来自 60 个随机规则结构、否定可出现在任何位置的 1,680 条记录）；开发/测试样本与 v4 逐字节一致，因此这里的每个数字都可与此前的检查点比较。

**锁定测试，只读一次**（`runs/locked/kev-8b-v7-preview-ungated/`）：分布内 **0.870**（Brier 0.193），域外 **0.780**（Brier 0.327，置信错误 7.6%，留出对 0.62）。该分区将不再为本检查点读取。

## 我们在构建过程中学到的

- **容量在域外起主导作用。** 在公开示例与合成预算相同的情况下，0.6B → 4B 提升 14–19 个百分点；4B → 8B 提升 1–7 个百分点。
- **微调会侵蚀基座能力，而学习率控制着这一点。** 4B 基座以字母读出（letter readout）零样本在相同的 MMLU 样本上得分为 0.688，在 PAWS 上为 0.787；默认配方（lr 2e-4）将其训练降至 0.60–0.66 / 0.56–0.71。将 lr 降至 5e-5 能恢复其中的大部分，这是我们找到的单一最大配方改进；更少的 LoRA 目标模块与更小的 rank 帮助较小。
- **更多公开训练数据在 4B 上提升分布内准确率但降低迁移**（1 万 vs 3.4k 条记录：−3 个百分点）。知识类 MCQ 数据源（ARC、OpenBookQA、CommonsenseQA）将分布内准确率提升至 0.86，但不改变迁移表现。
- 程序化对比策略对（programmatic contrastive policy pairs）教会了训练过的规则结构（both-correct 0.85–1.0），但对未见结构的迁移只是部分（4B 上 0.5–0.6，0.6B 上 0.03–0.11）。

## 已知局限

- 留出的策略推理（未见过的规则组合、带宽限期的日期运算）远不及 Jev。
- 没有训练类比的产品形态问题无法保证；请在你自己的输入上测量。
- 域外概率可用但未校准（原始 ECE 0.128）；在域内拟合的温度无法迁移。
- 8B fp32 需要约 33 GB，无法装入 32 GB 的 Mac；`KEV_DTYPE=bf16`（约 17 GB）可以。训练在单张 H100 上耗时约 70 分钟。

## 训练

冻结套件 `evals/v6/decision-v6`（开发/测试字节与 v4 一致）：13,000 条公开记录（每数据源 1,000 条：十个 v4 数据源加上 ARC-Challenge、OpenBookQA、CommonsenseQA）加上两个各 448 条的程序化策略分支，两个 epoch，注意力与 MLP 投影上 LoRA r=16，从头训练指针头，对选项分布的交叉熵，**lr 5e-5**（OneCycle），有效批次 8，bf16 自动混合精度（autocast）配合 fp32 主权重，梯度检查点（gradient checkpointing），单张 H100（约 70 分钟）。增强：选项排列、无上述选项插入、干扰项、在 25% 的 Choice 记录上的无最小对。训练未使用任何 Jev 输出。

## 评估协议

开发分区用于筛选模型；锁定测试分区每个候选最多读取一次。每个数字都带有套件哈希、代码哈希以及 `result.json` 中的 git commit。参见 git 标签 `research-archive-2026-09-24` 处的 `PLAN.md`（"Evidence and corrections"）中关于我们对自身早期声明所做修正的说明。

## 使用

```bash
uv run --extra serve python -m kev.serve --run jaredpalmer/kev-8b --port 8008      # KEV_DTYPE=bf16 on a 32 GB Mac
```

任何 TypeSafe 兼容的客户端均可使用：`TypeSafeClient(api_key="local", base_url="http://127.0.0.1:8008", model="kev-latest")`。

## 许可证

适配器与头为 Apache-2.0；Qwen3 基座为 Apache-2.0；数据集各自带有其许可证。
