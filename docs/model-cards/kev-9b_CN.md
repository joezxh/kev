---
language: en
license: apache-2.0
library_name: peft
base_model: Qwen/Qwen3.5-9B-Base
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
  - name: Kev-9B
    results:
      - task: { type: text-classification, name: typed decisions, out-of-domain (locked test, read once) }
        dataset: { type: mixed, name: "transfer-v4 test: six never-trained public sources and held-out policy structures (656 questions)" }
        metrics:
          - { type: accuracy, value: 0.852 }
          - { type: brier_score, value: 0.199 }
      - task: { type: text-classification, name: typed decisions, held-out public datasets (test) }
        dataset: { type: mixed, name: "breadth-v1 test: 14 held-out public datasets (3,089 questions)" }
        metrics:
          - { type: accuracy, value: 0.698 }
      - task: { type: text-classification, name: typed decisions, skill records (test) }
        dataset: { type: mixed, name: "hard-v1 test (1,088 questions; programmatic labels, held-out templates)" }
        metrics:
          - { type: accuracy, value: 0.834 }
      - task: { type: text-classification, name: typed decisions, developer tooling (test) }
        dataset: { type: mixed, name: "devtools-v1 test (1,071 questions; six public developer-tooling sources)" }
        metrics:
          - { type: accuracy, value: 0.791 }
      - task: { type: text-classification, name: typed decisions, real documents (test) }
        dataset: { type: mixed, name: "documents-v1 test (936 questions on CFPB complaint narratives)" }
        metrics:
          - { type: accuracy, value: 0.900 }
---

# Kev-9B

## 模型概述（Model summary）

Kev-9B 是一个决策模型（decision model）。它读取一篇文档（即 *state*，状态）以及一组关于该文档的带类型问题，并在单次前向传播（forward pass）中不生成文本，直接返回为每个问题所提供的选项之上的、经过校准的概率分布。它面向那些对文档进行分类、路由、分诊（triage）或核查，并需要可用于设定阈值（thresholded）的概率的开发者，例如将不确定的案例交由人工复核。它实现了 TypeSafe 公开的 System One API（`POST /v1/systemone`），因此 TypeSafe SDK 无需改动即可与之配合。它是一个 LoRA 适配器（adapter）和一个指针头（pointer head），运行在 Qwen3.5-9B-Base 之上，可放入一块 24 GB 级 GPU。本卡片描述的是第 2 版（version 2），发布于 2026-09-30，并纳入 Kev 1.0。

## 模型细节（Model details）

| | |
|---|---|
| Developer（开发者） | Jared Palmer ([github.com/jaredpalmer/kev](https://github.com/jaredpalmer/kev)) |
| Model type（模型类型） | 决策模型：因果语言模型骨干（backbone）仅运行预填充（prefill-only），并在选项之上使用一个指针头 |
| Backbone（骨干） | `Qwen/Qwen3.5-9B-Base`（版本 `68c46c4b`）：32 层，24 个 Gated DeltaNet（线性注意力）和 8 个全注意力（full attention），隐藏大小 4,096；已冻结 |
| Adapter（适配器） | LoRA，秩（rank）16，α 32，作用于注意力、MLP 和 DeltaNet 投影（45.4M 参数） |
| Head（头） | 指针头：两个投影将每个选项的结束 token 与问题的最后一个 token 进行打分；经 softmax 得到概率 |
| Precision（精度） | 以 bf16 自动混合精度（autocast）在 fp32 权重之上训练；以 bf16 提供服务（适配器在加载时合并进基座）；以 fp32 评估 |
| Context（上下文） | 最多可服务 65,536 token 的状态，每个问题另加至少 8,192 token。训练时的状态最多 7,552 token。 |
| Validated context length（经验证的上下文长度） | 8,192 token（见长文档 Long documents） |
| Calibration（校准） | 单一温度，T = 2.19，存储于 `head.pt` 并在加载时应用 |
| Languages（语言） | 英语 |
| License（许可证） | Apache-2.0（适配器与头）；基座模型为 Apache-2.0 |
| Version（版本） | v2（Kev 1.0）：[`jaredpalmer/kev-9b`](https://huggingface.co/jaredpalmer/kev-9b) 的 `main` 分支，版本 `b5d8c18e`（发布于 2026-09-30） |
| Previous version（先前版本） | v1，同一配方但不含文档与技能阶段（T = 2.30），位于标签 [`v1`](https://huggingface.co/jaredpalmer/kev-9b/tree/v1)；其卡片为该标签的 README |

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
- 在单块 24 GB 级 GPU 上自托管、可即插即用的 System One 端点替代，以及在你自己标签上微调（fine-tuning）的起点（`kev.train --init_from jaredpalmer/kev-9b`）。

## 不适用范围（Out-of-scope uses）

- 文本生成、聊天、摘要或开放式问答。该模型只对给定的选项进行打分。
- 对人有法律、医疗、金融、就业或类似后果、且未经人工复核的完全自动化决策。
- 答案依赖于状态之外的、非通用知识的事实的问题，以及偏重知识的考试（见局限性 Limitations）。
- 没有 `KEV_DATE_FACTS=1` 预处理器情况下的日精度日期运算，超过 65,536 token 的状态，以及英语以外的语言。

## 使用方式（How to use）

通过 Kev 代码仓库提供服务（serve）。在 CUDA 上，它以 bf16 配合融合（fused）DeltaNet 内核和 CUDA 图运行（一块 L40S 或 H100；常驻约 22 GB）；在 Apple Silicon 上，相同的命令通过 MLX 提供服务，自动选择。

```bash
git clone https://github.com/jaredpalmer/kev.git && cd kev && uv sync --extra serve
uv run --extra serve python -m kev.serve --run jaredpalmer/kev-9b --port 8008          # v2，Kev 1.0（本卡片）
uv run --extra serve python -m kev.serve --run jaredpalmer/kev-9b@v1 --port 8008       # v1
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
| 文档与技能，单阶段 | 16,539 | `documents-v1` 训练集：5,219 条美国消费者金融投诉叙述（CFPB，约 7k token），含 7,488 个问题，当两个开放权重（open-weight）教师模型与消费者自身提交一致时保留标签。`hard-v1` 训练集：6,000 条以程序化方式标注的记录，涵盖七个技能家族（长策略、权衡、概率、多跳、日期与运算、评判所提答案、缺失事实弃答），模板 0–3。`devtools-v1` 训练集：来自 CodeReviewer、CommitPackFT、FlakeFlagger 和 Aegis 的 5,320 条记录，使用各数据集自有标签 |

两个微调阶段分别重放（replay）来自 `decision-v7` 的 2,000 和 10,000 条记录。未使用 Jev（TypeSafe 托管的决策模型）的任何输出。CodeReviewer 和 FlakeFlagger 来自 Zenodo；CFPB 叙述为美国政府作品；各来源的许可证与版本记录在测试套件（suite）清单中。以下仅用于评估的套件（breadth-v1、tasksource-heldout-v1、transfer-v4、longdoc-v1，以及 devtools-v1 的 When2Call 和 prompt-injection 来源）从不进入训练。

## 训练过程（Training procedure）

1. **基础配方。** 在 `decision-v7` 上从基座训练两个 epoch：LoRA 秩 16，α 32；学习率 5e-5，单周期（one-cycle）调度；有效批大小 8（4 × 2 累积，accumulation）；bf16 自动混合精度，梯度检查点（gradient checkpointing）。损失为每个问题选项之上的交叉熵（cross-entropy）。选项顺序被打乱，随机插入“以上都不是（none of the above）”选项和干扰项（distractors），四分之一的 choice 记录还生成最小对（同一问题带“以上都不是”选项，一次包含正确选项、一次移除正确选项）。
2. **日期与缺失证据。** 从第 1 阶段以学习率 2e-5 训练一个 epoch，重放 2,000 条记录。这就是 v1。
3. **文档与技能。** 从 v1 开始，在所有三个训练集上一起以学习率 2e-5 训练一个 epoch，重放 10,000 条记录；批大小 2 × 4 累积；状态最多 7,552 token；种子 1；3,318 个优化器步（optimizer steps）。
4. **校准（Calibration）。** 单一温度，T = 2.19，在 648 个来自留出数据集的问题上最小化负对数似然（negative log-likelihood）：448 个来自 transfer-r3 的校准划分（六个公开数据集 QNLI、SciQ、TweetEval-offensive、PAWS、MMLU 和 Emotion，外加两个生成策略记录的留出家族），以及 200 个 MMLU-Pro 问题（transfer-v9 开发）。在拟合前，该池已针对检查点的训练套件进行了检查。

## 评估（Evaluation）

**方法（Methodology）。** 每次比较都是针对 Kev-9B v1 在相同项上进行，每个模型使用其自身服务温度（v1：2.30）。比较及其标准（bars）在确认读取（confirmation reads）之前已登记；测试划分（test partitions）为该检查点只读一次；transfer-v4 测试为锁定（locked，每位候选只读一次）。配对区间（paired intervals）为 95% 自举（bootstrap）区间，对整条记录重采样（2,000 次重采样），因此共享同一状态的问题一同变动。差异以百分点（percentage points, pp）计。Jev（TypeSafe 的托管模型，经 Vercel AI Gateway 查询）在与其读取相同项时给出。各套件如下：

- **breadth-v1**：五个领域（知识、语言、检索、工具、艺术）中的 14 个留出的公开数据集，从未训练过。
- **transfer-v4**：来自六个从未训练的公开来源外加留出策略与规则结构的分布外决策。
- **transfer-r3**：与校准池相同八个留出来源的短状态面板。
- **hard-v1**：上述技能家族；测试划分留出已训练生成器的模板。
- **devtools-v1**：来自六个经许可证检查的来源（四个已训练，两个仅评估）的开发者工具决策。
- **documents-v1 / documents-v2**：CFPB 投诉叙述；v2 为私有的留出测试集。
- **longdoc-v1**：CUAD 商业合同与生成的协议包（agreement bundles），状态为 4k 至 64k token。

devtools-v1 标题面板排除两个状态并不能决定标签的任务（`flakeflagger`、commit 变更类型）；相同行从两侧一并剔除。

**与 v1 的结果对比（已登记确认）。**

| Panel（面板，问题数） | Kev-9B v2 | Kev-9B v1 | Δ [95% CI] |
|---|---|---|---|
| hard-v1 + devtools-v1 开发，已审计（1,855） | 0.821 | 0.628 | +19.3 [+17.2, +21.6] |
| documents-v1 开发（920） | 0.902 | 0.833 | +7.0 [+4.8, +9.2] |
| 短状态：transfer-v4 开发 + transfer-r3 测试，不含 `emotion`（1,586） | 0.871 | 0.871 | +0.1 [−1.1, +1.2] |
| **hard-v1 + devtools-v1 测试，已审计（1,859）** | **0.822** | 0.635 | +18.7 [+16.7, +20.8] |
| **documents-v1 测试（936）** | **0.900** | 0.829 | +7.1 [+4.7, +9.2] |
| **分布外，transfer-v4 锁定测试（656）：准确率** | **0.852** | 0.852 | +0.0 [−1.7, +1.8] |
| transfer-v4 锁定测试：服务 Brier | 0.199 | 0.224 | −0.025 [−0.047, −0.007] |

**留出数据（从未训练过）。**

| Panel（面板，问题数） | Kev-9B v2 | Kev-9B v1 | Jev |
|---|---|---|---|
| breadth-v1 开发，全部 14 个数据集（3,075） | 0.700 | 0.697 | 0.757 |
| **breadth-v1 测试，全部 14 个数据集（3,089）** | **0.698** | 0.692 | 0.757 |
| breadth-v1 测试，机会校正指数¹ [95% CI] | 41.0 [38.8, 43.9] | 40.0 [38.1, 43.0] | 54.0 [51.2, 57.0] |
| 分布外，transfer-v4 开发（656）：准确率 / Brier | 0.820 / 0.262 | 0.822 / 0.264 | 0.857 / 0.211 |
| transfer-v4 锁定测试：ECE / 置信错误（p ≥ 0.9 且答错）/ ≤ 5% 误差下的覆盖率 | 0.034 / 1.4% / 0.742 | 0.042 / 3.2% / 0.645 | – |
| 短状态，transfer-r3 测试（1,150） | 0.847 | 0.847 | – |
| MMLU-Pro，10 个选项（transfer-v9 开发） | 0.590 | 0.515 | 0.840 |
| 以 p ≥ 0.9 回答不可答项（越低越好） | 0.00 | 0.00 | 0.09 |

与 v1 相比，breadth-v1 准确率差异在开发上为 +0.3 [−0.7, +1.3]，在测试上为 +0.6 [−0.4, +1.6]。tasksource-heldout-v1 开发已为本检查点读取，但其读出尚未完成；此处不报告。

**已训练的家族（留出项与模板）。**

| Panel（面板，问题数） | Kev-9B v2 | Kev-9B v1 | Jev |
|---|---|---|---|
| hard-v1 开发（1,083）/ 测试（1,088） | 0.813 / **0.834** | 0.574 / 0.584 | 0.777 / – |
| devtools-v1 开发（1,072）/ 测试（1,071），全部来源 | 0.772 / **0.791** | 0.631 / 0.637 | 0.713 / – |
| documents-v1 开发（920）/ 测试（936） | 0.902 / 0.900 | 0.833 / 0.829 | 0.868 / – |
| documents-v2，私有留出测试（953） | 0.900 | 0.821 | – |
| decision-v7 开发（1,264）/ 锁定测试（1,200） | 0.874 / 0.873 | 0.872 / – | 0.845 / – |
| 生成决策的留出域，ood-v2（4,988） | 0.889 | – | – |

与 v1 的测试差异：hard-v1 +25.0 [+22.0, +28.1]，devtools-v1（全部来源）+15.4 [+11.0, +19.4]，documents-v2 +8.0 [+5.9, +10.2]。

**长文档（Long documents）。**

- 经验证的上下文长度：8,192 token，即训练长度。16k 区间（bucket）超出容差（tolerance）：其下界为 −3.7 pp，低于 −3 pp，因此不验证更长长度。
- 规则（在读取前固定）：经验证长度为从 16,384 token 起、最大的区间的名义大小，要求该区间及其与 8,192 之间每个区间都在容差内。在容差内是指，与 8k 区间（状态 6,553–7,618 token，即训练长度）的 CUAD 准确率差异，在相同的合同、重复和问题上配对，其 95% 下界至少为 −3 pp，且每条记录都得到回答。若 16k 区间失败，则经验证长度为 8,192 token。

CUAD 准确率、ECE 以及按名义状态长度与 8k 区间的配对差异（longdoc-v1 开发）：

| Nominal state length（名义状态长度） | CUAD questions（CUAD 问题数） | Accuracy（准确率） | ECE | Δ vs 8k, pp [95% CI] |
|---|---|---|---|---|
| 4k | 443 | 0.876 | 0.049 | – |
| 8k | 453 | 0.850 | 0.051 | reference（基准） |
| 16k | 452 | 0.839 | 0.033 | −1.4 [−3.7, +0.9] |
| 32k | 454 | 0.819 | 0.041 | −3.6 [−6.4, −0.9] |
| 64k | 452 | 0.801 | 0.056 | −5.2 [−7.9, −2.5] |

ECE 在出货温度 T = 2.19 下。Δ 对在两个长度上就相同合同提出的 445–447 个问题进行配对。4k 区间包含不同的合同，不作为该规则的基准。来源：`runs/r28-readout/context.json`（第 28 轮的已登记读出，`runs/r29-9b-r18a-longdoc`）。

**校准（Calibration）**（预期校准误差 ECE，按服务状态；越低越好）：

| Panel（面板） | Kev-9B v2（T = 2.19） | Kev-9B v1（T = 2.30） |
|---|---|---|
| breadth-v1 测试，全部 14 个数据集 | 0.034 | 0.044 |
| transfer-v4 开发 / 锁定测试 | 0.041 / 0.034 | 0.042 / 0.042 |
| hard-v1 测试 | 0.054 | 0.075 |
| devtools-v1 测试，全部来源 | 0.098 | 0.147 |
| documents-v1 测试 | 0.017 | 0.103 |

温度的 90% 自举区间为 [2.05, 2.41]。v1 的 2.30 拟合在其自身训练分布的开发行上；v2 是第一个以留出数据集上拟合的温度提供服务的 9B 模型。

**其他结果（Other results）。**

| Suite（套件） | Kev-9B v2 | Jev |
|---|---|---|
| 日期运算，`deadline` 策略（transfer-v9 开发） | 0.725 | 0.95 |
| MMLU，4 个选项（transfer-v9 开发） | 0.725 | 0.90 |
| SemIf（144 个人工编写决策；接近饱和，仅报告） | 0.917 | 0.965 |

**服务（Serving）。** CUDA，bf16 配合融合内核与 CUDA 图；每个请求模型时间（20 次中位数），新 / 重复状态，在 v1 上测量（相同的架构与适配器形状）：

| GPU | 6 个问题，短状态 | 5 个问题，2,200-token 状态 | 请求/秒，64 客户端 |
|---|---|---|---|
| L40S | 66.4 / 42.7 ms | 235.6 / 57.5 ms | 32.7 |
| H100 | 24.0 / 16.6 ms | 88.5 / 26.4 ms | 79.5 |

常驻 GPU 内存为 21.9 GB。服务概率与 fp32 评估路径在 280 个问题上相差不超过 0.017，无答案改变。在 fp32 评估路径（H100，v2）上，16k / 32k / 64k token 的状态分别耗时 5.1 / 10.9 / 25.4 s，并在权重之外额外占用 4.6 / 9.1 / 18.2 GiB。

Apple Silicon（MLX）：为 Kev-0.8B 和 Kev-4B 所做的长状态测量尚未在此规模下完成；在用于它们的 32 GB M5 上，19.3 GB 的 bf16 骨干及其工作集无法装入可用内存。

¹ 社区 Decision Index 0.2 的机会校正指数：按数据集 (score − chance) / (1 − chance)，在每个领域内取平均，再 100 × 五个领域的均值。Jev 的指数来自对同一测试项的单独读取。

## 局限性与权衡（Limitations and trade-offs）

- **选取（Selection）。** 该检查点在更早一轮中于开发数据上训练并读取，随后在已知那些数字的情况下按更晚的规则重新选取。测试划分与锁定读取（各自为其只读一次）是护栏（guard）；请将开发边际视为乐观。
- **其大增益来自分布内。** hard-v1、devtools-v1 和 documents-v1 的训练划分在其训练数据中；那些增益是已训练家族的留出项与模板，而非向新任务的迁移。
- **在新任务上并不优于 v1。** breadth-v1 测试 +0.6 pp [−0.4, +1.6]，transfer-v4 开发 −0.2 pp [−2.4, +1.8]，transfer-r3 测试 +0.0 pp [−1.2, +1.2]。Kev-27B 在 breadth-v1 指数上领先它 11 分，Jev 领先 13 分。
- **知识由基座决定。** MMLU-Pro 为 0.590，对照 Kev-27B 的 0.675 和 Jev 的 0.840。
- **日期运算是其最弱的家族**：在 `deadline` 策略问题上为 0.725，而 Jev 为 0.95；`KEV_DATE_FACTS=1` 预处理器有帮助。
- **校准（Calibration）。** devtools-v1 是其校准最差的套件（测试 ECE 0.098）。温度区间为 [2.05, 2.41]。该温度由于有记录的缘由，从已登记池拟合写入 `head.pt`，因为校准脚本无法列出合并训练文件的来源以重新检查池本身；该轮自身的检查已覆盖它。该检查不覆盖 v1 的日期与缺失证据数据，其清单未列出任何来源；那些记录是四个生成家族，没有一个在池中。
- **未训练的长度。** 训练状态最多 7,552 token。更长状态可服务至 65,536 token；准确率能维持多远即上述经验证的上下文长度。
- **选项顺序**可能改变答案；问题隔离并不能防止这一点。

## 偏差、风险与伦理考量（Bias, risks and ethical considerations）

- 校准概率可能造成不应有的信任。该温度拟合在公开留出数据集上，并不迁移到每种工作负载；在设定阈值之前，请在你自己数据的带标签样本上测量准确率和校准，并在那里重新拟合温度（`python -m kev.calibrate`）。
- 准确率和校准在领域变化下会发生偏移。请监控生产环境的错误率，而非依赖上述数字。
- 请勿在没有人工复核的情况下，将其用于对有法律、医疗、金融、就业或类似后果之人的重大自动化决策。基座模型和训练数据（包括由其他模型生成的标签）的偏差未被测量。
- 状态可能包含个人或机密数据。自托管（self-hosting）可将输入保留在你自己的硬件上；除非设置 `KEV_API_KEY`，否则服务器是开放的，因此请应用你自己的访问控制与数据处理策略。

## 算力（Compute）

- 基础配方与日期阶段（v1）：单块 NVIDIA H100 GPU。
- 文档与技能阶段：一块 NVIDIA H200 上 2.6 小时（峰值 74.1 GB）。
- 评估与服务检查：Modal 上的单块 H100 / H200 / L40S GPU。

## 来源与可复现性（Provenance and reproducibility）

- 代码、套件与评估报告：[github.com/jaredpalmer/kev](https://github.com/jaredpalmer/kev)。发布编号：`runs/release/kev-9b-r27.json`（`scripts/release_numbers.py --release kev-9b-r27`）；已登记规则与判定 `experiments/rounds/r27.json`、`runs/r27-readout/`、`runs/r27-verdict/`；2026-09-30 的家族读取 `runs/fam-9bnew-breadth/`、`runs/fam-9b-breadth/` 和 `runs/fam-breadth-test-report/`；ood-v2 `runs/r29-9b-r18a-ood/`；服务 `runs/serve-9b-l40s/`、`runs/serve-9b-h100/`、`runs/long-state-9b-h100/`。
- 各阶段：基础试验 `q35-9b/01-trial-1`（标签 `v7-base`）；日期 `night2-9b-du/00-trial-0`（v1，标签 `v1`）；文档与技能第 18 轮分支（a）`r18-9b/00-trial-0`（`experiments/round18/joint.json`），作为第 27 轮的 `9b-r18a` 选取并确认。
- 发布权重：Hub commit `b5d8c18e`；适配器 sha256 `2b2a70cf4ef4440b6c22899e1f72c2f8ea5c6f65b19aa344539b4b8971d1f13d`，`head.pt` sha256 `8e1dab2c…`（T = 2.1936）。
- 验证（Verification）：从 Hub 匿名加载后，在 T = 2.19 下于 252 个 SemIf 行中的 252 个、764 个 transfer-v4 开发行中的 764 个上复现了发布前评估的答案（`runs/rel9-public/`）。

## 引用（Citation）

```bibtex
@misc{palmer2026kev9b,
  title        = {Kev-9B: a calibrated decision model on Qwen3.5-9B},
  author       = {Palmer, Jared},
  year         = {2026},
  howpublished = {\url{https://huggingface.co/jaredpalmer/kev-9b}},
  note         = {Version 2, released 2026-09-30; Kev 1.0}
}
```

## 联系（Contact）

问题与 issue：[github.com/jaredpalmer/kev/issues](https://github.com/jaredpalmer/kev/issues)。
