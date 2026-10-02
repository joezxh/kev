---
language: en
license: apache-2.0
library_name: transformers
base_model: Qwen/Qwen3.8-27B
base_model_relation: finetune
pipeline_tag: text-classification
tags:
  - decision-model
  - calibration
  - full-weight-sft
  - weight-averaging
  - multiple-choice
  - typesafe
  - qwen3.8
datasets:
  - deepmind/aqua_rat
  - allenai/ai2_arc
  - coastalcph/lex_glue
  - allenai/cosmos_qa
  - tau/commonsense_qa
  - tasksource/esci
  - openai/gsm8k
  - nvidia/HelpSteer2
  - nvidia/HelpSteer3
  - hotpotqa/hotpot_qa
  - AmazonScience/massive
  - allenai/math_qa
  - openlifescienceai/medmcqa
  - pfb30/multi_woz_v22
  - sentence-transformers/natural-questions
  - allenai/openbookqa
  - google-research-datasets/poem_sentiment
  - allenai/qasc
  - allenai/quartz
  - allenai/social_i_qa
  - stanfordnlp/snli
  - ChilleD/StrategyQA
  - allenai/winogrande
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
  - name: Kev-27B
    results:
      - task: { type: text-classification, name: typed decisions, out-of-domain (locked test, read once) }
        dataset: { type: mixed, name: "transfer-v4 test: six never-trained public sources and held-out policy structures (656 questions)" }
        metrics:
          - { type: accuracy, value: 0.8887 }
          - { type: brier_score, value: 0.154 }
      - task: { type: text-classification, name: typed decisions, held-out public datasets (test) }
        dataset: { type: mixed, name: "breadth-v1 test: 10 of 14 held-out public datasets (2,489 questions)" }
        metrics:
          - { type: accuracy, value: 0.832 }
      - task: { type: text-classification, name: typed decisions, held-out task families (test) }
        dataset: { type: mixed, name: "tasksource-heldout-v1 test: 17 of 24 held-out task families (2,024 questions)" }
        metrics:
          - { type: accuracy, value: 0.795 }
      - task: { type: text-classification, name: typed decisions, skills, developer tooling and documents (test) }
        dataset: { type: mixed, name: "hard-v1 + devtools-v1 + documents-v1 test (2,795 questions)" }
        metrics:
          - { type: accuracy, value: 0.889 }
---

# Kev-27B

## 模型概述（Model summary）

Kev-27B 是一个决策模型（decision model）。它读取一篇文档（即 *state*，状态）以及一组关于该文档的带类型问题，并在单次前向传播（forward pass）中不生成文本，直接返回为每个问题所提供的选项之上的、经过校准的概率分布。它面向那些对最多 64k token 的文档进行分类、路由、分诊（triage）或核查，并需要可用于设定阈值（thresholded）的概率的开发者，例如将不确定的案例交由人工复核。它实现了 TypeSafe 公开的 System One API（`POST /v1/systemone`），因此 TypeSafe SDK 无需改动即可与之配合。本卡片描述的是第 2 版（version 2），发布于 2026-09-30：是 Qwen3.8-27B 的全权重微调（full-weight fine-tune）与第 1 版的权重平均（weight-averaging）。

## 模型细节（Model details）

| | |
|---|---|
| Developer（开发者） | Jared Palmer ([github.com/jaredpalmer/kev](https://github.com/jaredpalmer/kev)) |
| Model type（模型类型） | 决策模型：因果语言模型骨干（backbone）仅运行预填充（prefill-only），并在选项之上使用一个指针头 |
| Backbone（骨干） | `Qwen/Qwen3.8-27B`（版本 `1d4bf0f2`，Qwen 的后训练发布）：64 层，48 个 Gated DeltaNet（线性注意力）和 16 个全注意力（full attention），隐藏大小 5,120；每个骨干权重均经微调 |
| Head（头） | 指针头：两个 5,120 → 256 投影将每个选项的结束 token 与问题的最后一个 token 进行打分；经 softmax 得到概率 |
| Parameters（参数） | 骨干 25.6B（视觉塔、LM 头和多头预测层的权重未加载），头 2.6M |
| Precision（精度） | bf16（一个 51.3 GB 检查点）；以 bf16 提供服务 |
| Context（上下文） | 最多可服务 65,536 token 的状态，每个问题另加至少 8,192 token。训练时的状态最多 32,768 token。 |
| Validated context length（经验证的上下文长度） | 65,536 token（见长文档 Long documents） |
| Calibration（校准） | 单一温度，T = 1.32，存储于 `head.pt` 并在加载时应用 |
| Languages（语言） | 英语 |
| License（许可证） | Apache-2.0（权重与头）；基座模型为 Apache-2.0 |
| Version（版本） | v2（Kev 1.0），于 2026-09-30 发布于 [`jaredpalmer/kev-27b`](https://huggingface.co/jaredpalmer/kev-27b) 的 `main` 分支 |
| Previous version（先前版本） | v1，同一基座上的秩 16 LoRA 适配器（adapter）（T = 1.38），位于标签 [`v1-lora`](https://huggingface.co/jaredpalmer/kev-27b/tree/v1-lora)；其卡片为该标签的 README |

**Input（输入）。** 一个状态（文本，或渲染为带标签文本的 JSON 对象或数组）以及任意数量的具名问题，每个问题属于以下三种类型之一：

| Type（类型） | Options（选项） | Output（输出） |
|---|---|---|
| `choice` | 1–255 个具名选项，每个选项可带可选描述 | 每个选项一个概率、最可能的选项以及一个置信度 |
| `score` | 1–255 个有序等级 | 每个等级一个概率以及期望等级索引 |
| `noul` | 是 / 否，可带可选描述 | 为“是”的概率 |

每个问题作为独立的一行作答，共享状态之后继续，因此问题之间不会相互影响；状态只计算一次并缓存。

## 预期用途（Intended uses）

- 对文档的带类型决策：分类、路由、分诊、抽取选择、政策与资格核查，以及依据既定标准评判所提答案。
- 基于置信度行动的工作流：自动化处理置信的案例、将其余排队，阈值在用户自身工作负载的带标签样本上冻结。
- 自托管、可即插即用的 System One 端点替代。

## 不适用范围（Out-of-scope uses）

- 文本生成、聊天、摘要或开放式问答。该模型只对给定的选项进行打分。
- 对人有法律、医疗、金融、就业或类似后果、且未经人工复核的完全自动化决策。
- 答案依赖于状态之外的、非通用知识的事实的问题（模型无法查找任何内容），以及偏重知识的考试（见局限性 Limitations）。
- 超过 65,536 token 的状态、英语以外的语言，以及小于 80 GB 级 GPU 或约 96 GB 内存的 Mac 这类硬件（见局限性 Limitations）。

## 使用方式（How to use）

在一块 B200、H200 或 H100 80 GB GPU 上通过 Kev 代码仓库提供服务（serve）。权重占用 51 GB，服务器常驻约 65.5 GB；64k-token 状态在 H200 上峰值达 87.1 GB，32k-token 状态峰值 78.7 GB，因此最长状态需要超过 80 GB。

```bash
git clone https://github.com/jaredpalmer/kev.git && cd kev && uv sync --extra serve
uv run --extra serve python -m kev.serve --run jaredpalmer/kev-27b --port 8008          # v2（本卡片）
uv run --extra serve python -m kev.serve --run jaredpalmer/kev-27b@v1-lora --port 8008  # v1
```

在 Apple Silicon 上，相同的命令通过 MLX 提供服务（自动选择），按保存的原样加载完整 bf16 权重，不做任何合并。该路径预期可在 96–128 GB 的 Mac 上运行，但尚未在此规模下实际跑过（见局限性 Limitations）。

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

默认应用校准温度；`KEV_TEMPERATURE=1.0` 返回原始概率。服务器使用 bf16、融合（fused）DeltaNet 内核和 CUDA 图；`KEV_DTYPE=fp32` 选择用于评估的确切路径。

## 训练数据（Training data）

在 145,840 条记录的私有语料（337,130 个问题）上训练一个 epoch，状态最多 32,768 token。仅其清单（manifest）公开（`evals/sft-v2-r22/manifest.json`，位于 GitHub 仓库中）。

| Component（组成部分） | Records（记录数） | Content and labels（内容与标签） |
|---|---|---|
| Kev 语料 | 78,786 | Kev-27B v1 的训练集（十个公开分类数据集、生成的策略与规则记录、日期运算与缺失证据案例、埋有事实的长状态）；Kev 技能（hard-v1）、开发者工具（devtools-v1）和消费者投诉（documents-v1）套件（suite）的训练划分；每个上限 500 条的 24 个公开数据集；七个生成家族（长文档、工具路由、检索、意图、rubric 评判、弃答、数值推理） |
| 授权任务家族 | 24,000 | 来自公开多任务集合的 119 个任务家族，使用允许商业使用且带原生标签的许可证；家族列表未公开 |
| 长状态 | 3,200 | 嵌入 8k–32k-token 文档的 Kev 语料状态；标签完全一致继承 |
| 长文档 | 7,617 | 由代码组装的文档，标签由代码计算 |
| 分布外决策 | 7,312 | 不同领域生成的决策 |
| 语气（Tone） | 7,544 | 同样文本写成冷静、沮丧或愤怒的最小对（minimal pairs） |
| 提示注入 | 2,699 | 识别间接提示注入（防御性） |
| 智能体会话（Agent sessions） | 4,875 | 关于代码生成的智能体会话日志的问题 |
| PII | 4,152 | 对由代码插入的个人数据分类（全部为虚构） |
| 依据（Grounding） | 5,655 | 某说法是否由文档支持 |

**来源与标签（Sources and labels）。** 公开数据集列于本卡片元数据中；两个开发者工具来源 CodeReviewer 和 FlakeFlagger 来自 Zenodo，且 CodeReviewer 的 diff 仅保留自宽松许可证（permissively licensed）项目。生成的文本与标签来自代码或开放权重（open-weight）模型（GLM-5.3、DeepSeek-V4-Pro、Inkling、Mistral Large 3、gpt-oss-120b、MiMo-V2.6-Pro）。消费者投诉标签来自开放权重模型，经闭源（closed）模型评判员过滤与裁定（adjudication）。未使用 Jev（TypeSafe 托管的决策模型）的任何输出。

**许可证（Licences）。** 受限的（share-alike）公开数据集中有四个：ARC（CC-BY-SA-4.0）、HotpotQA（CC-BY-SA-4.0）、Natural Questions（CC-BY-SA-3.0）和 SNLI（CC-BY-SA-4.0）；其余为 CC-BY-4.0、MIT 或 Apache-2.0。CFPB 投诉叙述为美国政府作品。GLM-5.3 的许可证为类 MIT，但对超大型模型即服务（model-as-a-service）运营商附带条件。各来源的许可证、版本与署名记录在组成部分清单中。

**污染筛查（Contamination screening）。** 训练前，每条记录都针对 102 个评估划分（76,549 个参考项）进行筛查：每个冻结的 Kev 套件、私有评估集、JevBench 的公开项，以及以下仅评估的套件。在以下任一情况下移除记录：精确归一化字符串匹配、词级 8-gram Jaccard 相似度高于 0.2，或包含度（containment）至少 0.5；共移除 6,388 条训练记录。

## 训练过程（Training procedure）

1. **全权重微调（Full-weight fine-tuning）。** 在 8 块 NVIDIA H200 GPU（FSDP2）上从 `Qwen/Qwen3.8-27B` 训练一个 epoch。AdamW（β 0.9 / 0.999，权重衰减 0.01），在 bf16 骨干之上使用 fp32 主权重与动量（moments）；骨干学习率 2e-6、头学习率 1e-4，单周期（one-cycle）调度含 10% 预热（warm-up）；梯度范数裁剪（gradient norm clipped）至 1.0；每个优化器步 128 条记录（每 GPU 8 条，2 个累积步），共 1,140 步；种子 0。损失为每个问题选项之上的交叉熵（cross-entropy）（数据有软目标（soft targets）时使用软目标）。选项顺序被打乱，随机插入“以上都不是（none of the above）”选项和干扰项（distractors）。状态最多 8,192 token 的四分之一 choice 记录还生成最小对：同一问题带“以上都不是”选项，一次包含正确选项、一次移除正确选项。每个状态只运行一次，其问题从该状态分支。
2. **权重平均（Weight averaging）。** 每个骨干张量为 0.85 × 微调权重 + 0.15 × v1 权重（v1 的 LoRA 适配器以 fp32 合并进基座），在 fp32 中计算并一次性舍入（rounded）到 bf16。保留微调模型的指针头。该比例是在开发数据上从六种混合（0.85 / 0.70 / 0.50，配任一头）中选出的。
3. **校准（Calibration）。** 单一温度，T = 1.32，在 648 个来自留出数据集的问题上最小化负对数似然（negative log-likelihood），这些数据集两个母模型都未曾训练：448 个来自 transfer-r3 的校准划分（六个公开数据集 QNLI、SciQ、TweetEval-offensive、PAWS、MMLU 和 Emotion，外加两个生成策略记录的留出家族），以及 200 个 MMLU-Pro 问题（transfer-v9 开发）。未使用任何训练语料的划分，且一项检查未发现与训练数据重叠。

## 评估（Evaluation）

**方法（Methodology）。** 每次比较都是针对 Kev-27B v1 在相同项上进行，每个模型使用其自身服务温度。测试划分（test partitions）为该检查点只读一次；transfer-v4 测试为锁定（locked，每位候选只读一次），并对照事先固定的标准（bar）评判（准确率 ≥ 0.886、Brier ≤ 0.165）。区间为 95% 配对自举（bootstrap）区间，对整条记录重采样（2,000 次重采样），因此共享同一状态的问题一同变动。差异以百分点（percentage points, pp）计。各套件如下：

- **breadth-v1**：五个领域（知识、语言、检索、工具、艺术）中的 14 个留出的公开数据集，从未训练过。
- **tasksource-heldout-v1**：与授权组成部分相同的多任务集合的 24 个完整任务家族，留出训练。
- **hard-v1**：以程序化方式标注的技能记录（长策略、权衡、概率、多跳、日期与数字、评判、弃答）；测试划分留出已训练生成器的模板。
- **devtools-v1**：来自经许可证检查的公开来源的开发者工具决策（代码审查、commit 信息、安全、不稳定测试）。
- **documents-v1 / documents-v2**：美国消费者金融投诉叙述（CFPB）；v2 为私有的留出测试集。
- **transfer-v4**：来自六个从未训练的公开来源外加留出策略结构的分布外决策。
- **longdoc-v1**：最长 64k token 的 CUAD 商业合同，以及生成的协议包（agreement bundles）。

标题面板排除在本检查点构建前完成的标签审计认定不成立的项¹；每次排除都会从两个模型中移除相同行。

**与 v1 的结果对比（测试划分）。**

| Panel（面板，问题数） | Kev-27B v2 | Kev-27B v1 | Δ [95% CI] |
|---|---|---|---|
| 留出公开数据集，breadth-v1，10 个数据集（2,489） | 0.832 | 0.820 | +1.2 [+0.3, +2.2] |
| 留出任务家族，tasksource-heldout-v1，17 个家族（2,024） | 0.795 | 0.743 | +5.3 [+3.7, +6.8] |
| 技能、开发者工具与文档，合并（2,795） | 0.889 | 0.800 | +8.9 [+7.5, +10.3] |
| &nbsp;&nbsp;hard-v1（1,088） | 0.918 | 0.749 | +16.9 [+14.2, +19.8] |
| &nbsp;&nbsp;devtools-v1，已审计来源（771） | 0.825 | 0.789 | +3.6 [+1.3, +5.9] |
| &nbsp;&nbsp;documents-v1（936） | 0.908 | 0.869 | +4.0 [+2.1, +5.9] |
| documents-v2，私有留出（953） | 0.921 | 0.881 | +4.0 [+2.0, +6.1] |
| breadth-v1，全部 14 个数据集（3,089） | 0.757 | 0.748 | +0.8 [−0.1, +1.8] |
| **分布外，transfer-v4 锁定测试（656）：准确率** | **0.8887** | 0.8963 | −0.8 [−2.0, +0.5] |
| 分布外，transfer-v4 锁定测试：Brier / ≤ 5% 误差下的覆盖率 | 0.154 / 0.875 | 0.160 / 0.835 | – |

**与其他决策模型的比较** 在 breadth-v1 测试（全部 14 个数据集）上，采用社区 Decision Index 0.2 的机会校正指数评分（按数据集 (score − chance) / (1 − chance)，在每个领域内取平均，再 100 × 五个领域的均值）。Jev 经 Vercel AI Gateway 查询，AutoJev-27B（`denis-pplx/autojev-27b`，同一基座的全权重微调）经其自身服务器查询，各自一次，针对相同项。

| | Kev-27B v2 | Kev-27B v1 | Jev | AutoJev-27B |
|---|---|---|---|---|
| Index [95% CI] | **52.3** [49.2, 55.4] | 50.2 [47.0, 53.2] | 54.0 [51.2, 57.0] | 50.0 [47.0, 53.3] |

与 v1 相比，指数差异为 +2.1 [−0.4, +4.6]。未计算与 Jev 的配对区间。

**长文档（Long documents）**（longdoc-v1 测试中的 CUAD 合同，按状态长度（token）的准确率 / ECE）：

| State length（状态长度，问题数） | Kev-27B v2 | Kev-27B v1 |
|---|---|---|
| under 8k（867） | 0.874 / 0.059 | 0.900 / 0.025 |
| 8k–16k（443） | 0.880 / 0.052 | 0.892 / 0.028 |
| 16k–32k（442） | 0.873 / 0.061 | 0.882 / 0.019 |
| 32k–64k（442） | 0.867 / 0.060 | 0.876 / 0.014 |
| all（2,194） | 0.874 / 0.053 | 0.890 / 0.007 |

所有长度上的准确率差异：−1.6 [−3.0, −0.3]。在生成的协议包（2,400 个问题）上，两个模型均得 1.000。

**上下文长度（Context length）。** 经验证的上下文长度：65,536 token，即服务上限，来自 longdoc-v1 开发（与 8k 区间配对的 CUAD 准确率差异，pp [95% CI]：16k +0.2 [−0.7, +1.2]，32k −0.2 [−1.2, +0.7]，64k −1.1 [−2.4, +0.0]；各 445–447 个问题）。规则是对每个 Kev 1.0 尺寸所应用的那条：经验证长度为从 16,384 token 起、最大的区间的名义大小，要求该区间及其与 8,192 之间每个区间都在容差（tolerance）内，即与 8k 区间的 CUAD 准确率差异，在相同的合同、重复和问题上配对，其 95% 下界至少为 −3 pp，且每条记录都得到回答。

**校准（Calibration）**（预期校准误差 ECE，按服务状态；越低越好）：

| Panel（面板） | Kev-27B v2 | Kev-27B v1 |
|---|---|---|
| breadth-v1 测试，10 个数据集 | 0.015 | 0.013 |
| tasksource-heldout-v1 测试 | 0.049 | 0.051 |
| hard-v1 + devtools-v1 + documents-v1 测试 | 0.014 | 0.027 |
| transfer-v4 锁定测试 | 0.019 | 0.018 |
| CUAD 合同，longdoc-v1 测试 | 0.053 | 0.007 |

在 648 个拟合问题上，5 折组不相交交叉验证（5-fold group-disjoint cross-validation）将 ECE 从 0.048（原始）降至 0.038（折外，out of fold）；两个区间重叠。温度的 90% 自举区间为 [1.20, 1.45]。在其两端，标题面板朝相反方向移动：breadth-v1 ECE 在 T = 1.20 时升至 0.026，tasksource-heldout-v1 ECE 在 T = 1.45 时升至 0.067。

**其他结果（Other results）。**

| Suite（套件） | Kev-27B v2 | Kev-27B v1 |
|---|---|---|
| transfer-v4 开发，准确率 / Brier | 0.851 / 0.218 | 0.848 / 0.229 |
| 短状态，transfer-r3 测试（1,150） | 0.858 | 0.879 |
| devtools-v1 测试，全部来源（1,071） | 0.790 | 0.711 |
| decision-v7 开发（v1 的训练分布） | 0.865 | 0.866 |
| MMLU-Pro，10 个选项（transfer-v9 开发） | 0.675 | 0.665 |
| 以 p ≥ 0.9 回答不可答项（越低越好） | 0.00 | 0.00 |
| SemIf（144）/ WANLI-v2（1,002）/ TypeSafe（89 个已回答行） | 0.965 / 0.756 / 0.854 | 0.972 / 0.745 / 0.865 |
| 已训练生成器的留出域，准确率 / ECE：ood-v2（4,988） | 0.956 / 0.020 | 0.944 / 0.044 |
| &nbsp;&nbsp;agents-ood-v1（2,084） | 0.988 / 0.032 | 0.967 / 0.137 |
| &nbsp;&nbsp;guardrails-ood-v1（4,949） | 0.984 / 0.010 | 0.944 / 0.079 |

transfer-r3 测试是与校准池相同八个留出来源的短状态面板；decision-v7 是 v1 的训练分布；transfer-v9 包含 MMLU-Pro 以及判定证据被移除的项。SemIf（来自 SemIf 项目的人工编写决策）、WANLI-v2（来自 WANLI 测试划分的自然语言推理对）和 TypeSafe（SemIf 对 TypeSafe 工作流案例的选择）仅报告：标签审计认为它们太小、饱和或噪声过大，无法对模型排序。WANLI-v2 和 TypeSafe 于 2026-09-30 作为评估退役（约四分之一的 WANLI 对由两个标注者标注不同，而金标（gold）被设为这两个标签之一；TypeSafe 的金标是两个闭源前沿模型的平均答案，问题太少无法区分检查点）；其数值作为记录保留。

**服务一致性（Serving parity）**（H200，bf16 配合融合内核与 CUDA 图，200 个 decision-v7 开发记录 / 280 个问题）：

| Check（检查） | Result（结果） |
|---|---|
| 服务 vs fp32 评估路径，最大 \|Δp\| | 0.0223，无答案改变 |
| 单个问题 vs 完整请求，最大 \|Δp\| | 0.0039，无答案改变 |
| 服务 vs 8k / 32k / 64k-token 状态上的评估，最大 \|Δp\| | 0.0064 / 0.0095 / 0.0017，无答案改变 |
| 64k-token 状态下的模型时间，新 / 缓存状态 | 9.4 s / 733 ms |
| 常驻内存 / 从热缓存加载时间 | 65.5 GB / 17.6 s |
| 1 / 64 并发客户端的吞吐 | 21.1 / 36.4 请求/秒 |

¹ 从标题面板排除：四个 breadth-v1 数据集（`routerbench`，其状态缺少所问信息；`cfcolor` 和 `humicroedit`，对每个系统都接近随机；`chessbench`，对每个系统都处于地板值）；七个标签无效或不可恢复的 tasksource-heldout-v1 家族（名称不公开）；以及两个 devtools-v1 任务（其状态并不能决定标签：`flakeflagger`、commit 变更类型）。transfer-r3 的 `emotion` 来源（远程关键词标签）在局限性的短状态面板中被排除。

## 局限性与权衡（Limitations and trade-offs）

- **选取（Selection）。** 发布的检查点是在已知更早候选者的测试结果之后选定的，并在相同测试集上确认。请将测试边际视为乐观。
- **在短状态上无增益。** 它在短输入上并不优于 v1：锁定 transfer-v4 测试上 −0.8 pp [−2.0, +0.5]，短状态开发面板（transfer-v4 开发与不含量 `emotion` 的 transfer-r3 测试）上 −0.9 pp [−2.0, +0.1]，整个 transfer-r3 测试上 −2.1 pp [−3.5, −0.8]。
- **在长合同上更差且过度自信。** 在 CUAD 上它比 v1 低 1.6 pp，且其 ECE 在每个长度上都是 v1 的 2 到 4 倍（总体 0.053 对 0.007）。CUAD 的问题包含一些错误或争议的金标，但差距在各长度上一致。对于合同审查，请在你自己带标签的文档上重新拟合温度（`python -m kev.calibrate`）或使用 v1。
- **分布内增益。** hard-v1、devtools-v1 和 documents-v1 的训练划分在训练数据中，且 ood-v2、agents-ood-v1 和 guardrails-ood-v1 套件是同样产出训练数据的生成器的留出域。那里的增益衡量的是已训练家族的留出项，而非向新任务的迁移。
- **未知基座训练。** 基座是 Qwen 的后训练发布；其训练数据未知，因此它与任何评估之间的重叠不能排除。
- **知识（Knowledge）。** 知识由基座决定：MMLU-Pro 为 0.675，在相同项上 Jev 为 0.840。
- **未训练的长度。** 32k–64k token 的状态已评估（longdoc-v1）但未经训练。
- **退役套件（Retired suite）。** 用于选取 v1 的一个支持工单套件（scienthoon）在 v2 构建前因不成立而退役，因此 v2 在其上没有结果。v2 未平均的微调母模型在那里比 v1 低 5.5 pp [−7.8, −3.2]。
- **温度不确定性（Temperature uncertainty）。** 温度区间（[1.20, 1.45]）使测试 ECE 变动最多约 0.02。
- **硬件（Hardware）。** 它需要 80 GB 级的数据中心 GPU（最长状态需要超过 80 GB）。通过 MLX 的 Apple Silicon：v2 的完整 bf16 权重约需 51 GB 外加工作内存，因此 64 GB 的 Mac 处于临界，96–128 GB 的 Mac 应当能放下。这是基于在较小模型上的测量预期，尚未在大型 Mac 上测量：通过相同路径加载完整权重的 Kev-4B 峰值达到其权重大小（8.4 GB），其答案与 fp32 评估路径相差在 0.015 内（`runs/mlx-full-4b`）。v1（LoRA 适配器，标签 `v1-lora`）由外部贡献者通过 MLX 在 128 GB M5 Max 上提供服务（[PR #175](https://github.com/jaredpalmer/kev/pull/175)）：transfer-v4 开发上准确率 0.849，对照发布的 0.848，稳定 52 GB、合并适配器时峰值 97 GB。

## 偏差、风险与伦理考量（Bias, risks and ethical considerations）

- 校准概率可能造成不应有的信任。该温度拟合在公开留出数据集上，并不迁移到每种工作负载；在设定阈值之前，请在你自己数据的带标签样本上测量准确率和校准。
- 准确率和校准在领域变化下会发生偏移（例如在长合同上）。请监控生产环境的错误率，而非依赖上述数字。
- 请勿在没有人工复核的情况下，将其用于对有法律、医疗、金融、就业或类似后果之人的重大自动化决策。基座模型和训练数据（包括由其他模型生成的标签）的偏差未被测量。
- 状态可能包含个人或机密数据。自托管（self-hosting）可将输入保留在你自己的硬件上；除非设置 `KEV_API_KEY`，否则服务器是开放的，因此请应用你自己的访问控制与数据处理策略。

## 算力（Compute）

- 微调：8 × NVIDIA H200，训练时间 16.2 小时（129 GPU-小时），不含重启与评估。
- 权重平均：CPU 上约 6 分钟。
- 评估与服务检查：Modal 上的单块 H200 GPU。

## 来源与可复现性（Provenance and reproducibility）

- 代码、套件与评估报告：[github.com/jaredpalmer/kev](https://github.com/jaredpalmer/kev)。发布编号：`runs/release/kev-27b-r23.json`（`scripts/release_numbers.py --release kev-27b-r23`）。
- 微调：第 22 轮试验 `r22-27b-lr2e6/00-trial-0`（`experiments/round22/lr2e6.json`），权重 sha256 `3fa0182a…`。混合（Blend）：第 23 轮分支 `27b-k-w85`（`scripts/interpolate_checkpoint.py --toward`；Hub 仓库中的 `interpolation.json`），选择规则与确认阶段在 `experiments/rounds/r23.json`；结果在 `runs/r23-readout/`、`runs/r23-verdict/`、`runs/r23-breadth-report/`、`runs/serving-27b-r23*/`。
- 混合来源：v1 位于 `jaredpalmer/kev-27b@01b81998`（试验 `r6-27b-v2/01-trial-1`），现为标签 `v1-lora`。
- 发布权重 sha256 `d27af6ab2be16824166ac639907b4dba40979ff338599c2872721aa6c5072022`；`head.pt` sha256 `7968f17b03479c1ef9d1c0f3ab8a15e31ecb441cf40691b07ee945ab554d45ad`（T = 1.3195）。权重发布于 Hub commit `28be62e9`。
- 验证（Verification）：从 Hub 匿名加载后，它在 252 个 SemIf 行中的 252 个、764 个 transfer-v4 开发行中的 764 个上精确复现了发布前评估的 logits（`runs/release/kev-27b-r23-published.json`、`runs/release/kev-27b-r23-staging.json`）。

## 引用（Citation）

```bibtex
@misc{palmer2026kev27b,
  title        = {Kev-27B: a calibrated decision model on Qwen3.8-27B},
  author       = {Palmer, Jared},
  year         = {2026},
  howpublished = {\url{https://huggingface.co/jaredpalmer/kev-27b}},
  note         = {Version 2, released 2026-09-30}
}
```

## 联系（Contact）

问题与 issue：[github.com/jaredpalmer/kev/issues](https://github.com/jaredpalmer/kev/issues)。
