---
language: en
license: apache-2.0
library_name: peft
base_model: Qwen/Qwen3.5-4B-Base
base_model_relation: adapter
pipeline_tag: text-classification
tags:
  - decision-model
  - calibration
  - lora
  - multiple-choice
  - typesafe
  - qwen3.5
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
  - bigcode/commitpackft
  - nvidia/Aegis-AI-Content-Safety-Dataset-2.0
  - davidheineman/consumer-finance-complaints-large
metrics:
  - accuracy
  - brier_score
  - expected_calibration_error
model-index:
  - name: Kev-4B
    results:
      - task: { type: text-classification, name: typed decisions, out-of-domain (locked test, read once) }
        dataset: { type: mixed, name: "transfer-v4 test: six never-trained public sources and held-out policy structures (656 questions)" }
        metrics:
          - { type: accuracy, value: 0.838 }
          - { type: brier_score, value: 0.224 }
      - task: { type: text-classification, name: typed decisions, held-out public datasets (test) }
        dataset: { type: mixed, name: "breadth-v1 test: 14 held-out public datasets (3,089 questions)" }
        metrics:
          - { type: accuracy, value: 0.690 }
      - task: { type: text-classification, name: typed decisions, held-out task families (development) }
        dataset: { type: mixed, name: "tasksource-heldout-v1 development: 17 of 24 held-out task families (1,993 questions)" }
        metrics:
          - { type: accuracy, value: 0.677 }
      - task: { type: text-classification, name: typed decisions, skill records (test) }
        dataset: { type: mixed, name: "hard-v1 test (1,088 questions; programmatic labels, held-out templates)" }
        metrics:
          - { type: accuracy, value: 0.803 }
          - { type: brier_score, value: 0.278 }
      - task: { type: text-classification, name: typed decisions, developer tooling (test) }
        dataset: { type: mixed, name: "devtools-v1 test (1,071 questions; six public developer-tooling sources)" }
        metrics:
          - { type: accuracy, value: 0.756 }
          - { type: brier_score, value: 0.342 }
---

# Kev-4B

## 模型概述（Model summary）

Kev-4B 是一个决策模型（decision model）。它读取一篇文档（即 *state*，状态）以及一组关于该文档的带类型问题，并在单次前向传播（forward pass）中不生成文本，直接返回为每个问题所提供的选项之上的、经过校准的概率分布。它面向那些对文档进行分类、路由、分诊（triage）或核查，并需要可用于设定阈值（thresholded）的概率的开发者，例如将不确定的案例交由人工复核。它实现了 TypeSafe 公开的 System One API（`POST /v1/systemone`），因此 TypeSafe SDK 无需改动即可与之配合。它是一个 LoRA 适配器（adapter）和一个指针头（pointer head），运行在 Qwen3.5-4B-Base 之上，足够小以放入一块 24 GB GPU 或一台 32 GB 的 Apple Silicon Mac。本卡片描述的是 Kev 1.0 中的检查点（checkpoint），首次发布于 2026-09-24。

## 模型细节（Model details）

| | |
|---|---|
| Developer（开发者） | Jared Palmer ([github.com/jaredpalmer/kev](https://github.com/jaredpalmer/kev)) |
| Model type（模型类型） | 决策模型：因果语言模型骨干（backbone）仅运行预填充（prefill-only），并在选项之上使用一个指针头 |
| Backbone（骨干） | `Qwen/Qwen3.5-4B-Base`（版本 `1001bb4d`）：32 层，24 个 Gated DeltaNet（线性注意力）和 8 个全注意力（full attention），隐藏大小 2,560；已冻结 |
| Adapter（适配器） | LoRA，秩（rank）16，α 32，作用于注意力、MLP 和 DeltaNet 投影（33.8M 参数） |
| Head（头） | 指针头：两个投影将每个选项的结束 token 与问题的最后一个 token 进行打分；经 softmax 得到概率 |
| Precision（精度） | 以 bf16 自动混合精度（autocast）在 fp32 权重之上训练；以 bf16 提供服务（适配器在加载时合并进基座）；以 fp32 评估 |
| Context（上下文） | 最多可服务 65,536 token 的状态，每个问题另加至少 8,192 token。训练时的状态最多 7,552 token。 |
| Validated context length（经验证的上下文长度） | 8,192 token（见长文档 Long documents） |
| Calibration（校准） | 单一温度，T = 2.41，存储于 `head.pt` 并在加载时应用 |
| Languages（语言） | 英语 |
| License（许可证） | Apache-2.0（适配器与头）；基座模型为 Apache-2.0 |
| Version（版本） | Kev 1.0：[`jaredpalmer/kev-4b`](https://huggingface.co/jaredpalmer/kev-4b) 的 `main` 分支，版本 `139fdd94`（发布于 2026-09-24） |
| Previous versions（先前版本） | Hub 标签 `r8-documents-release`（仅文档阶段）、`night2-du-release`、`v7-base` 和 `qwen3`（Qwen3-4B 代） |

**Input（输入）。** 一个状态（文本，或渲染为带标签文本的 JSON 对象或数组）以及任意数量的具名问题，每个问题属于以下三种类型之一：

| Type（类型） | Options（选项） | Output（输出） |
|---|---|---|
| `choice` | 1–255 个具名选项，每个选项可带可选描述 | 每个选项一个概率、最可能的选项以及一个置信度 |
| `score` | 1–255 个有序等级 | 每个等级一个概率以及期望等级索引 |
| `noul` | 是 / 否，可带可选描述 | 为“是”的概率 |

每个问题作为独立的一行作答，共享状态之后继续，因此问题之间不会相互影响；状态只计算一次并缓存。

## 预期用途（Intended uses）

- 对几千 token 的文档进行带类型决策：分类、路由、分诊、抽取选择、政策与资格核查，以及依据既定标准评判所提答案。
- 基于置信度行动的工作流：自动化处理置信的案例、将其余排队，阈值在用户自身工作负载的带标签样本上冻结。
- 在适中硬件上自托管、可即插即用的 System One 端点替代，以及在你自己标签上微调（fine-tuning）的起点（`kev.train --init_from jaredpalmer/kev-4b`）。

## 不适用范围（Out-of-scope uses）

- 文本生成、聊天、摘要或开放式问答。该模型只对给定的选项进行打分。
- 对人有法律、医疗、金融、就业或类似后果、且未经人工复核的完全自动化决策。
- 答案依赖于状态之外的、非通用知识的事实的问题，以及偏重知识的考试（见局限性 Limitations）。
- 没有 `KEV_DATE_FACTS=1` 预处理器情况下的日精度日期运算，超过 65,536 token 的状态，以及英语以外的语言。

## 使用方式（How to use）

通过 Kev 代码仓库提供服务（serve）。在 CUDA 上，它以 bf16 配合融合（fused）DeltaNet 内核和 CUDA 图运行（一块 L40S、H100 或任何约有 16 GB 空闲的 GPU）；在 Apple Silicon 上，相同的命令通过 MLX 提供服务，自动选择。

```bash
git clone https://github.com/jaredpalmer/kev.git && cd kev && uv sync --extra serve
uv run --extra serve python -m kev.serve --run jaredpalmer/kev-4b --port 8008           # Kev 1.0（本卡片）
uv run --extra serve python -m kev.serve --run jaredpalmer/kev-4b@v1.0 --port 8008      # 相同权重，固定版本
```

```python
from typesafe_sdk import Choice, Noul, TypeSafeClient

client = TypeSafeClient(api_key="local", base_url="http://127.0.0.1:8008", model="kev-latest")
response = client.system_one(
    state="I was charged twice for order 1182. Please refund one of the charges.",
    questions={
        "team": Choice(instructions="Which team should handle this?",
                       criteria={"billing": "Charges and refunds", "shipping": "Deliveries", "returns": "Exchanges"}),
        "urgent": Noul(instructions="Does this need a reply today?"),
    },
)
print(response.choices["team"].choice, response.nouls["urgent"].noul)
```

默认应用校准温度；`KEV_TEMPERATURE=1.0` 返回原始概率。`KEV_DTYPE=fp32` 选择用于评估的确切路径。`KEV_DATE_FACTS=1` 会附加状态中每对日期之间的天数，该模型经训练后学会使用它。超过 65,536 token 的状态会以 422 拒绝，并返回其 token 数量。

## 训练数据（Training data）

| Stage（阶段） | Records（记录数） | Content and labels（内容与标签） |
|---|---|---|
| 基础配方（`decision-v7`） | 12,576 | 来自十个公开分类数据集的 10,000 条记录（每个 1,000 条，列于本卡片元数据中），带各自原生标签；896 条在九个模板家族上生成的策略最小对（minimal pairs）；来自 60 个随机生成规则结构、四种渲染方式的 1,680 条记录；标签由代码计算 |
| 日期与缺失证据 | 1,425 | 生成数据：900 个含日期的策略案例（纯文本、含天数统计句，或含 `date_facts` 字段）；255 个删去判定句并采用均匀目标的案例，外加 270 个完整对照 |
| 真实文档（`documents-v1` 训练集） | 5,219 | 美国消费者金融投诉叙述（CFPB，约 7k token），含 7,488 个问题（产品、主要问题）；当两个开放权重（open-weight）教师模型与消费者自身提交一致时保留标签 |
| 技能（`hard-v1` 训练集） | 6,000 | 七个家族中以程序化方式标注的记录：带例外和子限额的长策略文档、在既定优先级下的权衡、概率与期望值、多跳推理、日期与运算、评判所提答案，以及缺失事实弃答；生成器模板 0–3 |
| 开发者工具（`devtools-v1` 训练集） | 5,320 | CodeReviewer（评审员是否对某个 hunk 作了评论）、CommitPackFT（commit 类型）、FlakeFlagger（不稳定测试，flaky tests）和 Aegis（内容安全），各使用其数据集自有标签 |

第一个阶段之后的每个微调阶段都重放（replay）来自 `decision-v7` 的记录（分别为 2,000、2,000 和 4,000）。未使用 Jev（TypeSafe 托管的决策模型）的任何输出。CodeReviewer 和 FlakeFlagger 来自 Zenodo；CFPB 叙述为美国政府作品；各来源的许可证与版本记录在测试套件（suite）清单中。以下仅用于评估的套件（breadth-v1、tasksource-heldout-v1、transfer-v4、longdoc-v1，以及 devtools-v1 的 When2Call 和 prompt-injection 来源）从不进入训练。

## 训练过程（Training procedure）

1. **基础配方。** 在 `decision-v7` 上从基座训练两个 epoch：LoRA 秩 16，α 32；学习率 5e-5，单周期（one-cycle）调度；有效批大小 8（4 × 2 累积，accumulation）；bf16 自动混合精度，梯度检查点（gradient checkpointing）；种子 2。损失为每个问题选项之上的交叉熵（cross-entropy）。选项顺序被打乱，随机插入“以上都不是（none of the above）”选项和干扰项（distractors），四分之一的 choice 记录还生成最小对（同一问题带“以上都不是”选项，一次包含正确选项、一次移除正确选项）。
2. **日期与缺失证据。** 从第 1 阶段以学习率 2e-5 训练一个 epoch，重放 2,000 条记录。
3. **真实文档。** 从第 2 阶段在 `documents-v1` 训练集上以学习率 2e-5 训练一个 epoch，重放 2,000 条记录；批大小 2 × 4 累积；状态最多 7,552 token。
4. **技能。** 从第 3 阶段在 `hard-v1` 和 `devtools-v1` 训练集上一起以学习率 2e-5 训练一个 epoch，重放 4,000 条记录；批大小 2 × 4 累积；状态最多 7,552 token；种子 1；1,915 个优化器步（optimizer steps）。
5. **校准。** 单一温度，T = 2.41，在第 4 阶段试验的 `decision-v7` 开发行（1,264 个问题）上最小化负对数似然（negative log-likelihood）。这些是训练语料中留出（held-out）的项。尝试了在留出数据集上的重新拟合（refit）但未采用（见校准 Calibration）。

## 评估（Evaluation）

**方法（Methodology）。** 除非另有说明，每个数字都是出货温度（shipped temperature）下的 fp32 评估路径。开发划分（development partitions）用于筛选；测试划分（test partitions）为该检查点只读一次；transfer-v4 测试为锁定（locked，每位候选只读一次），并对照事先固定的标准（bar）评判。配对区间（paired intervals）为 95% 自举（bootstrap）区间，对整条记录重采样（2,000 次重采样），因此共享同一状态的问题一同变动。差异以百分点（percentage points, pp）计。Jev（TypeSafe 的托管模型，经 Vercel AI Gateway 查询）在与其读取相同项时给出。各套件如下：

- **breadth-v1**：五个领域（知识、语言、检索、工具、艺术）中的 14 个留出的公开数据集，从未训练过。
- **tasksource-heldout-v1**：同一公开多任务集合的 24 个完整任务家族，从未训练过（家族名称不公开）。
- **transfer-v4**：来自六个从未训练的公开来源（QNLI、SciQ、TweetEval-offensive、PAWS、MMLU、Emotion）的分布外决策，外加留出的策略和规则结构。
- **hard-v1**：上述技能家族；测试划分留出已训练生成器的模板。
- **devtools-v1**：来自六个经许可证检查的来源（四个已训练，两个仅评估）的开发者工具决策。
- **documents-v1 / documents-v2**：CFPB 投诉叙述；v2 为私有的留出测试集。
- **longdoc-v1**：CUAD 商业合同与生成的协议包（agreement bundles），状态为 4k 至 64k token。

标有“audited（已审计）”的标题面板排除经标签审计认定不成立的项¹；每次排除都会从对比的两侧移除相同行。

**留出数据（从未训练过）。**

| Panel（面板，问题数） | Kev-4B | Jev |
|---|---|---|
| 留出公开数据集，breadth-v1 开发，已审计，10 个数据集（2,475） | 0.768 | – |
| breadth-v1 开发，全部 14 个数据集（3,075） | 0.696 | 0.757 |
| **breadth-v1 测试，全部 14 个数据集（3,089）** | **0.690** | 0.757 |
| breadth-v1 测试，机会校正指数² [95% CI] | 38.0 [35.5, 41.3] | 54.0 [51.2, 57.0] |
| 留出任务家族，tasksource-heldout-v1 开发，已审计，17 个家族（1,993） | 0.677 | – |
| tasksource-heldout-v1 开发，全部 24 个家族（2,788） | 0.632 | – |
| 分布外，transfer-v4 开发（656）：准确率 / Brier | 0.817 / 0.243 | 0.857 / 0.211 |
| **分布外，transfer-v4 锁定测试（656）：准确率 / Brier** | **0.838 / 0.224** | – |
| transfer-v4 锁定测试：ECE / 置信错误（p ≥ 0.9 且答错）/ ≤ 5% 误差下的覆盖率 | 0.017 / 1.5% / 0.701 | – |
| MMLU-Pro，10 个选项（transfer-v9 开发） | 0.565 | 0.840 |
| 以 p ≥ 0.9 回答不可答项（越低越好） | 0.00 | 0.09 |

**已训练的家族（留出项与模板）。**

| Panel（面板，问题数） | Kev-4B | Jev |
|---|---|---|
| hard-v1 开发（1,083）/ 测试（1,088） | 0.786 / **0.803** | 0.777 / – |
| devtools-v1 开发，已审计来源（772） | 0.780 | – |
| devtools-v1 开发（1,072）/ 测试（1,071），全部来源 | 0.739 / **0.756** | 0.713 / – |
| documents-v1 开发（920）/ 测试（936） | 0.891 / 0.903 | 0.868 / – |
| decision-v7 开发（1,264）/ 锁定测试（1,200） | 0.873 / 0.865 | 0.845 / – |
| 生成决策的留出域，ood-v2（4,988） | 0.864 | – |

Jev 的 devtools-v1 数值覆盖全部 1,074 个开发问题；Kev 的行剔除了套件构建者复用于两条记录的 CodeReviewer id（2 个问题）。

**与先前版本对比**（文档阶段检查点，标签 `r8-documents-release`，其自身温度 2.96；已登记标准，每个测试只读一次）：

| Panel（面板） | Δ [95% CI] |
|---|---|
| hard-v1 测试 | +26.3 [+23.3, +29.5] |
| devtools-v1 测试 | +13.4 [+10.1, +16.1] |
| hard-v1 + devtools-v1 测试，合并 | +19.9 [+17.8, +21.8] |
| documents-v1 开发 | −0.3 [−1.5, +0.9] |
| transfer-v4 锁定测试 | +0.3 [−1.8, +2.3] |

**长文档（Long documents）。**

- 经验证的上下文长度：8,192 token，即训练长度。16k 区间（bucket）超出容差（tolerance）：其下界为 −3.4 pp，低于 −3 pp，因此不验证更长长度。
- 规则（在读取前固定）：经验证长度为从 16,384 token 起、最大的区间的名义大小，要求该区间及其与 8,192 之间每个区间都在容差内。在容差内是指，与 8k 区间（状态 6,553–7,618 token，即训练长度）的 CUAD 准确率差异，在相同的合同、重复和问题上配对，其 95% 下界至少为 −3 pp，且每条记录都得到回答。若 16k 区间失败，则经验证长度为 8,192 token。

CUAD 准确率、ECE 以及按名义状态长度与 8k 区间的配对差异（longdoc-v1 开发）：

| Nominal state length（名义状态长度） | CUAD questions（CUAD 问题数） | Accuracy（准确率） | ECE | Δ vs 8k, pp [95% CI] |
|---|---|---|---|---|
| 4k | 443 | 0.847 | 0.047 | – |
| 8k | 453 | 0.837 | 0.048 | reference（基准） |
| 16k | 452 | 0.823 | 0.057 | −1.1 [−3.4, +1.2] |
| 32k | 454 | 0.788 | 0.022 | −5.8 [−9.0, −2.8] |
| 64k | 452 | 0.781 | 0.035 | −5.2 [−8.2, −2.0] |

ECE 在出货温度 T = 2.41 下。Δ 对在两个长度上就相同合同提出的 445–447 个问题进行配对。4k 区间包含不同的合同，不作为该规则的基准。来源：`runs/r28-readout/context.json`（第 28 轮的已登记读出，`runs/r28-4b-r10-longdoc`）。

**校准（Calibration）**（预期校准误差 ECE，在出货温度 T = 2.41 下；越低越好）：

| Panel（面板） | ECE |
|---|---|
| breadth-v1 开发，已审计 / 全部 14 个数据集 | 0.021 / 0.028 |
| breadth-v1 测试，全部 14 个数据集 | 0.029 |
| tasksource-heldout-v1 开发，已审计 | 0.042 |
| transfer-v4 开发 / 锁定测试 | 0.042 / 0.017 |
| hard-v1 开发 / 测试 | 0.095 / 0.084 |
| devtools-v1 开发，已审计 | 0.072 |
| documents-v1 开发 / 测试 | 0.093 / 0.101 |
| decision-v7 开发（拟合行） | 0.013 |
| ood-v2 | 0.084 |

出货温度拟合在训练语料的留出项上，而项目规则已不再允许新版本这样做。一次在留出数据集上的已登记重新拟合（648 个问题，来自 transfer-r3 的校准划分、八个来源，以及 200 个 MMLU-Pro 问题）给出 T = 2.30（90% 自举区间 [2.05, 2.52]）。在 4,468 个已审计的 breadth-v1 和 tasksource-heldout-v1 开发问题上，它并未改善出货值：Brier 两侧均为 0.368，差异为 −0.0001 [−0.0005, +0.0003]，ECE 0.025 对 0.024。规则要求 Brier 区间低于零且 ECE 更低，因此 T = 2.41 保持不变。答案不依赖于 T。

**其他结果（Other results）。**

| Suite（套件） | Kev-4B | Jev |
|---|---|---|
| 日期运算，`deadline` 策略（transfer-v9 开发） | 0.65 | 0.95 |
| MMLU，4 个选项（transfer-v9 开发） | 0.725 | 0.90 |
| When2Call / 提示注入（prompt injection）（devtools-v1 开发，仅评估来源） | 0.660 / 0.753 | – / 0.893 |
| SemIf（144 个人工编写决策；接近饱和，仅报告） | 0.889 | 0.965 |
| JevBench 公开项，全部 231 / 困难档 111（ECE） | 0.758 / 0.541 (0.112) | – |

**服务（Serving）。** CUDA，bf16 配合融合内核与 CUDA 图；每个请求模型时间（20 次中位数），新 / 重复状态：

| GPU | 6 个问题，短状态 | 5 个问题，2,200-token 状态 | 请求/秒，64 客户端 |
|---|---|---|---|
| L40S | 41.5 / 27.7 ms | 145.2 / 43.0 ms | 51.4 |
| H100 | 18.1 / 12.9 ms | 89.4 / 22.5 ms | 100.8 |

常驻 GPU 内存为 14.3 GB。服务概率与 fp32 评估路径在 280 个问题上相差不超过 0.017，无答案改变。在 fp32 评估路径（H100）上，16k / 32k / 64k token 的状态分别耗时 3.0 / 6.8 / 17.2 s，并在权重之外额外占用 4.3 / 8.6 / 17.2 GiB。

Apple Silicon（MLX，bf16，32 GB M5；三个问题，其中一个关于埋在 60% 深度的真实事实；状态以 1,024-token 块预填充）：

| State tokens（状态 token 数） | New state（新状态） | Cached state（缓存状态） | MLX peak（8.4 GB weights，MLX 峰值） | Process footprint（进程占用） | Planted fact（埋入事实，p） |
|---|---|---|---|---|---|
| 8,192 | 6.6 s | 354 ms | 10.2 GB | 11.9 GB | 正确 (0.97) |
| 16,384 | 14.0 s | 427 ms | 11.0 GB | 12.8 GB | 正确 (0.95) |
| 32,768 | 30.5 s | 533 ms | 11.9 GB | 13.7 GB | 正确 (0.96) |
| 65,000 | 84.5 s | 716 ms | 13.0 GB | 14.1 GB | 正确 (0.94) |

在 60 个短状态问题上，MLX 路径与 fp32 评估路径相差在 0.018 内，无答案改变。

¹ 从已审计面板排除：四个 breadth-v1 数据集（`routerbench`，其状态缺少所问信息；`cfcolor` 和 `humicroedit`，对每个系统都接近随机；`chessbench`，对每个系统都处于地板值）；七个标签无效或不可恢复的 tasksource-heldout-v1 家族（名称不公开）；两个 devtools-v1 任务（其状态并不能决定标签：`flakeflagger`、commit 变更类型）。

² 社区 Decision Index 0.2 的机会校正指数：按数据集 (score − chance) / (1 − chance)，在每个领域内取平均，再 100 × 五个领域的均值。Jev 的指数来自对同一测试项的单独读取。

## 局限性与权衡（Limitations and trade-offs）

- **其最大增益来自分布内。** hard-v1、devtools-v1 和 documents-v1 的训练划分在其训练数据中，且 hard-v1 测试项是已训练生成器的新模板。在留出数据集上它落后 Jev 16 分（breadth-v1 指数）；在 JevBench 公开困难档（一个分布外检查）上，技能阶段获得的增益约为在 hard-v1 上的三分之一（+9.0 pp [+2.7, +15.3]，基于 111 项）。
- **部分 devtools-v1 标签是代理（proxies）。** 训练前，包括 Jev 在内的每个模型在 CodeReviewer 和 FlakeFlagger 上都接近随机；在那些来源上训练后，它在开发上达到 0.633 和 0.693，这可能是学到了标注启发式（labelling heuristic）而非决策本身。
- **知识由基座决定。** MMLU-Pro 为 0.565，而 Jev 为 0.840。
- **日期运算是其最弱的家族**：在 `deadline` 策略问题上为 0.65，而 Jev 为 0.95。本模型源自的早期检查点上 `KEV_DATE_FACTS=1` 预处理器有帮助（0.60 → 0.85）；本检查点未重新测量。
- **校准是单一的分布内温度。** 在留出数据集上校准良好（breadth-v1 测试 ECE 0.029），在已训练的技能和文档家族上稍差（ECE 0.084–0.101），且单一温度无法对置信度重新排序：分布外 ≤ 5% 误差下的覆盖率在开发上为 0.620，而 Jev 为 0.70。
- **未训练的长度。** 训练状态最多 7,552 token。更长状态可服务至 65,536 token；准确率能维持多远即上述经验证的上下文长度。
- **选项顺序**可能改变答案；问题隔离并不能防止这一点。

## 偏差、风险与伦理考量（Bias, risks and ethical considerations）

- 校准概率可能造成不应有的信任。该温度拟合在训练分布的开发行上，并不迁移到每种工作负载；在设定阈值之前，请在你自己数据的带标签样本上测量准确率和校准，并在那里重新拟合温度（`python -m kev.calibrate`）。
- 准确率和校准在领域变化下会发生偏移。请监控生产环境的错误率，而非依赖上述数字。
- 请勿在没有人工复核的情况下，将其用于对有法律、医疗、金融、就业或类似后果之人的重大自动化决策。基座模型和训练数据（包括由其他模型生成的标签）的偏差未被测量。
- 状态可能包含个人或机密数据。自托管（self-hosting）可将输入保留在你自己的硬件上；除非设置 `KEV_API_KEY`，否则服务器是开放的，因此请应用你自己的访问控制与数据处理策略。

## 算力（Compute）

- 基础配方：一块 NVIDIA H100 上约 56 分钟（峰值 24.6 GB）。日期阶段：一块 H100 上 9 分钟。
- 文档阶段：一块 NVIDIA H200 上 43 分钟。技能阶段：一块 H200 上 1.4 小时（峰值 47.7 GB）。
- 评估与服务检查：Modal 上的单块 H100 / H200 / L40S GPU；MLX 测量在 Apple M5 上进行。

## 来源与可复现性（Provenance and reproducibility）

- 代码、套件与评估报告：[github.com/jaredpalmer/kev](https://github.com/jaredpalmer/kev)。发布编号：`runs/release/kev-4b-r10.json`（`scripts/release_numbers.py --release kev-4b-r10`），锁定读取 `runs/locked/kev-4b-r10-ungated/`，2026-09-30 的家族读取 `runs/fam-4b-breadth/`、`runs/fam-4b-breadthtest/`、`runs/fam-4b-docs1test/` 和 `runs/fam-breadth-test-report/`，校准重新拟合 `runs/r28-readout/round28.json`，服务 `runs/serve-4b-l40s/`、`runs/grouping-4b-h100/`、`runs/long-state-4b-h100/`、`runs/mlx-long-states/`、`runs/mlx-full-4b/`。
- 各阶段：基础试验 `q35-4b-s23/00-trial-0`（标签 `v7-base`）；日期 `night2-4b-du/00-trial-0`（标签 `night2-du-release`）；文档第 8 轮 `r8-small/00-trial-0`（标签 `r8-documents-release`）；技能第 10 轮 `r10-skills/00-trial-0`（`experiments/round10/skills.json`，规则 `experiments/rounds/r10.json`）。校准重新拟合：第 28 轮分支 `4b-r10`（`experiments/rounds/r28.json`）。
- 发布权重：Hub 版本 `139fdd94`；适配器 sha256 `90e81735…`，`head.pt` sha256 `dd633435…`（T = 2.4061）。
- 发布历史：于 2026-09-24 作为第 10 轮确认候选发布；原样纳入 Kev 1.0。其如何被选取的记录（包括此后因不成立而退役的套件 scienthoon、WANLI-v2、TypeSafe）见于 Hub 版本 `139fdd94` 的 README，以及 git 标签 `research-archive-2026-09-24` 的 `PLAN.md`。

## 引用（Citation）

```bibtex
@misc{palmer2026kev4b,
  title        = {Kev-4B: a calibrated decision model on Qwen3.5-4B},
  author       = {Palmer, Jared},
  year         = {2026},
  howpublished = {\url{https://huggingface.co/jaredpalmer/kev-4b}},
  note         = {Kev 1.0}
}
```

## 联系（Contact）

问题与 issue：[github.com/jaredpalmer/kev/issues](https://github.com/jaredpalmer/kev/issues)。
