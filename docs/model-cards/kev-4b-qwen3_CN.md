---
language: en
license: apache-2.0
library_name: peft
base_model: Qwen/Qwen3-4B-Base
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
  - name: Kev-4B (Qwen3)
    results:
      - task: { type: text-classification, name: typed decision (choice / noul / score) }
        dataset: { type: mixed, name: "decision-v4 development (1,204 records; ten trained public sources + programmatic policy pairs)" }
        metrics:
          - { type: accuracy, value: 0.854 }
          - { type: expected_calibration_error, value: 0.065, name: "ECE, raw probabilities" }
      - task: { type: text-classification, name: typed decision, out-of-domain }
        dataset: { type: mixed, name: "transfer-v4 development (764 records; six never-trained sources + held-out policy structures)" }
        metrics:
          - { type: accuracy, value: 0.790 }
          - { type: brier_score, value: 0.328 }
---

<p align="center">
  <a href="./kev-4b-qwen3_CN.md"><img alt="中文" src="https://img.shields.io/badge/%E4%B8%AD%E6%96%87-orange?style=for-the-badge"></a>
  <a href="./kev-4b-qwen3.md"><img alt="English" src="https://img.shields.io/badge/English-blue?style=for-the-badge"></a>
</p>


# Kev-4B (Qwen3)

> **上一代（Qwen3）。** 该检查点作为 Apple Silicon 上的快速选项保留（其仅注意力的主干网络在 MPS 上以全速运行打包前向传播）。就准确率与校准而言请使用 [Kev-4B (Qwen3.5)](kev-4b.md)：在锁定测试上，对相同的样本，本模型域外得分为 0.806，而其为 0.832。权重：`jaredpalmer/kev-4b@qwen3`。

Kev-4B 是一个**决策模型**：一篇文档（即 *state*，状态）与一组带类型的问题作为输入，每个问题输出一个概率分布，在一次前向传播中完成。不生成文本。它是一个 LoRA 适配器（r=16）加上一个指针头，建立在 `Qwen/Qwen3-4B-Base` 之上，服务于 TypeSafe 公开的 `/v1/systemone` 契约。

**推荐的 Kev。** 在冻结、做校验和（checksummed）的协议下，经过约 40 次受控的 4B 试验后表现最好的 4B 检查点，也是首个在相同样本上域外表现进入距 Jev 七个百分点以内的 Kev。同一配方以三个种子运行：域外 0.773 / **0.790** / 0.770；本检查点是开发分区上选定的种子（绝不在锁定测试上选定）。

- Hub：`jaredpalmer/kev-4b`，版本标签 `qwen3`（试验 `v7-rc3/01-trial-1`）；该仓库的 main 版本现在保存的是 Qwen3.5 检查点
- 代码、测试套件、每次带哈希与配对 bootstrap 的试验：[github.com/jaredpalmer/kev](https://github.com/jaredpalmer/kev) —— `PLAN.md`（完整记录在 git 标签 `research-archive-2026-09-24`）、`runs/leaderboard.md`

## 结果（每一行使用相同的冻结样本）

| | Kev-0.5B（原型） | Kev-0.6B | **Kev-4B** | Jev |
|---|---|---|---|---|
| 分布内准确率（decision-v4 dev，1,200 q） | 0.712 | 0.801 | **0.854** | 0.845 |
| 域外准确率（transfer-v4 dev，560 q） | 0.561 | 0.620 | **0.790** | 0.857 |
| 域外 Brier | 0.50 | 0.536 | **0.328** | 0.211 |
| 域外置信错误（p ≥ 0.9 且错误） | – | 10.8% | 8.2% | 3.7% |
| 留出策略结构，两个兄弟都正确 | – | 0.08 | 0.73 | 0.86 |
| 选项顺序翻转率 | 0.21 | 0.07 | 0.06 | 0.00 |

各数据源域外准确率（Kev-4B / Jev）：QNLI 0.89 / 0.93、SciQ 0.99 / 0.99、TweetEval-offensive 0.75 / 0.81、PAWS 0.72 / 0.79、MMLU 0.65 / 0.90、Emotion 0.66 / 0.59、deadline（3 等级日期运算）0.53 / 0.93、(A and B) or not C 0.97 / 0.97、if A then not B else C 0.88 / 0.78。

种子：在 decision-v7 上的三个种子：域外 0.773 / **0.790** / 0.770，留出规则对 0.62 / **0.73** / 0.67（Jev 0.86）；本检查点为种子 1，依据开发域外准确率选定。训练于 `decision-v7`（1 万条公开记录 + 覆盖九个模板族的 896 条策略记录，含四个有序 Score 阈值族 + 来自 60 个随机规则结构、否定可出现在任何位置的 1,680 条记录）；开发/测试样本与 v4 逐字节一致，因此这里的每个数字都可与此前的检查点比较。

**锁定测试，只读一次**（`runs/locked/kev-4b-v7-preview-ungated/`）：分布内 **0.856**（Brier 0.211），域外 **0.806**（Brier 0.294，置信错误 6.6%，留出对 0.66）。该分区将不再为本检查点读取。

## 我们在构建过程中学到的

- **容量在域外起主导作用。** 在公开示例与合成预算相同的情况下，0.6B → 4B 提升 14–19 个百分点；4B → 8B 提升 1–7 个百分点。
- **微调会侵蚀基座能力，而学习率控制着这一点。** 4B 基座以字母读出（letter readout）零样本在相同的 MMLU 样本上得分为 0.688，在 PAWS 上为 0.787；默认配方（lr 2e-4）将其训练降至 0.60–0.66 / 0.56–0.71。将 lr 降至 5e-5 能恢复其中的大部分，这是我们找到的单一最大配方改进；更少的 LoRA 目标模块与更小的 rank 帮助较小。
- **更多公开训练数据在 4B 上提升分布内准确率但降低迁移**（1 万 vs 3.4k 条记录：−3 个百分点）。知识类 MCQ 数据源（ARC、OpenBookQA、CommonsenseQA）将分布内准确率提升至 0.86，但不改变迁移表现。
- 程序化对比策略对（programmatic contrastive policy pairs）教会了训练过的规则结构（both-correct 0.85–1.0），但对未见结构的迁移只是部分（4B 上 0.5–0.6，0.6B 上 0.03–0.11）。

## 已知局限

- 留出的策略推理（未见过的规则组合、带宽限期的日期运算）远不及 Jev。
- 没有训练类比的产品形态问题无法保证：在 TypeSafe 文档示例中（"two charges on my card" → *Is there a billing problem?*），本检查点回答为 0.48（Kev-8B 0.95，Kev-0.6B 0.97），但正确选择了退货原因（wrong size 0.53；Kev-8B 0.84；Kev-0.6B 倾向于"none of the above" 0.58）。请在你自己的输入上测量。
- 域外概率可用但未校准（原始 ECE 0.096）；在域内拟合的温度无法迁移。
- 4B fp32 需要约 16 GB；在 32 GB 的 Mac 上使用 `KEV_DTYPE=bf16`。在 H100 上延迟约为每个打包请求 45 毫秒；在 M5 上为数百毫秒。

## 训练

冻结套件 `evals/v4/decision-v4`：10,000 条公开记录（每数据源 1,000 条，十个数据源）加上两个各 448 条的程序化策略分支，两个 epoch，注意力与 MLP 投影上 LoRA r=16，从头训练指针头，对选项分布的交叉熵，**lr 5e-5**（OneCycle），有效批次 8，bf16 自动混合精度（autocast）配合 fp32 主权重，梯度检查点（gradient checkpointing），单张 H100（约 40 分钟）。增强：选项排列、无上述选项插入、干扰项、在 25% 的 Choice 记录上的无最小对。训练未使用任何 Jev 输出。

## 评估协议

开发分区用于筛选模型；锁定测试分区每个候选最多读取一次。每个数字都带有套件哈希、代码哈希以及 `result.json` 中的 git commit。参见 git 标签 `research-archive-2026-09-24` 处的 `PLAN.md`（"Evidence and corrections"）中关于我们对自身早期声明所做修正的说明。

## 使用

```bash
uv run --extra serve python -m kev.serve --run jaredpalmer/kev-4b --port 8008      # KEV_DTYPE=bf16 on a 32 GB Mac
```

任何 TypeSafe 兼容的客户端均可使用：`TypeSafeClient(api_key="local", base_url="http://127.0.0.1:8008", model="kev-latest")`。

## 许可证

适配器与头为 Apache-2.0；Qwen3 基座为 Apache-2.0；数据集各自带有其许可证。
