<p align="center">
  <a href="./PLAN_CN.md"><img alt="中文" src="https://img.shields.io/badge/%E4%B8%AD%E6%96%87-orange?style=for-the-badge"></a>
  <a href="./PLAN.md"><img alt="English" src="https://img.shields.io/badge/English-blue?style=for-the-badge"></a>
</p>

# 研究计划

本文件说明了 Kev 目前的进展、我们学到的东西、每个实验都要遵循的规则，以及接下来的工作。它刻意保持简短。完整的研究记录（从 Qwen3 原型到 night 3、round 4-18 的每一次注册、读取、裁定和事件）已冻结在 git 标签 `research-archive-2026-09-24`；下面以 `A:<path>` 形式给出的指针表示 `git show research-archive-2026-09-24:<path>`（例如 `A:PLAN.md`，那份 1,322 行的记录，或 `A:PLAN_27b.md`，即 Kev-27B 计划）。如何运行无人值守的研究会话见 [`docs/autoresearch.md`](docs/autoresearch.md)。

## 我们目前的进展 (2026-09-30)

### 已发布的模型族

这四款模型都已在 [Kev collection](https://huggingface.co/collections/jaredpalmer/kev-6aad9d0ea49f2589665e07cd) 公开发布。Kev-4B round 10 与 Kev-0.8B round 15 已发布，Kev-27B 于 2026-09-24 公开（文档见 PR #106）。Kev-27B v2（round 23 的 `27b-k-w85`，全权重）于 2026-09-30 取代了它；v1（LoRA 适配器）保留在 `jaredpalmer/kev-27b@v1-lora`（"Released: Kev-27B v2"）。Kev-9B v2（round 27 的 `9b-r18a`）于同一天取代了 Kev-9B；v1 保留在 `jaredpalmer/kev-9b@v1`（"Released: Kev-9B v2"）。这四款模型于 2026-10-01 作为 Kev 1.0 一同发布（见下；"Released: Kev 1.0"）。

| model | checkpoint | T | locked transfer-v4: acc / Brier | other confirmation reads (once each) | JevBench public: all / hard (hard ECE) |
|---|---|---|---|---|---|
| Kev-27B v2 | round 23 `27b-k-w85` (0.85 round-22 full-weight SFT + 0.15 v1, SFT head), full bf16 weights `d27af6ab…`, `Qwen/Qwen3.8-27B@1d4bf0f2` (post-trained), Hub `28be62e9` (weights) | 1.32 (pool) | **0.889 / 0.154** | vs v1: breadth-v1 test +1.2 [+0.3, +2.2]; tasksource-heldout-v1 test +5.3 [+3.7, +6.8]; pooled hard / devtools / documents test +8.9 [+7.5, +10.3]; locked −0.8 [−2.0, +0.5]; CUAD test −1.6 [−3.0, −0.3], ECE 0.053 vs 0.007 | 未读取 |
| Kev-27B v1 (tag `v1-lora`) | `r6-27b-v2/01-trial-1` (B1 v2 seed 2), LoRA, Hub `01b81998` | 1.38 | 0.896 / 0.160 | decision-v7 locked 0.870; transfer-r6 test 0.863 vs Kev-9B 0.842 (+2.1 pp [+0.35, +3.8]); longstate-v3 0.833 vs 0.556 | **0.866 / 0.721** (0.128) |
| Kev-9B v2 | round 27 `9b-r18a` (`r18-9b/00-trial-0`: v1 + one epoch on documents-v1 + hard-v1 + devtools-v1, replay 10,000), Hub `b5d8c18e` | 2.19 (pool) | **0.852 / 0.199** | vs v1: hard-v1 + devtools-v1 test +18.7 [+16.7, +20.8]; documents-v1 test +7.1 [+4.7, +9.2]; locked +0.0 [−1.7, +1.8] | 未读取 |
| Kev-9B v1 (tag `v1`) | `night2-9b-du/00-trial-0` (v7 + dates/unknowable delta), Hub `2629c06a` | 2.30 | 0.852 / 0.224 | - | 0.762 / 0.568 (0.19) |
| Kev-4B | `r10-skills/00-trial-0` (night2 + documents-v1 (round 8) + hard-v1 & devtools-v1 (round 10)), Hub `139fdd94` | 2.41 | 0.838 / 0.224 | hard-v1 test 0.540 → 0.803; devtools-v1 test 0.623 → 0.756 | 0.758 / 0.541 (0.112) |
| Kev-0.8B | `r15-08b/00-trial-0` (night2 + documents-v1, hard-v1, devtools-v1 in one delta), Hub `9a45d25e` | 2.35 | 0.697 / 0.397 | documents-v1 test 0.608 → 0.851; hard-v1 test 0.396 → 0.665; devtools-v1 test 0.472 → 0.637; documents-v2 (private) 0.848 | 0.636 / 0.360 (0.181) |
| Jev (reference) | hosted | - | transfer-v4 dev 0.857 (never locked) | - | 0.866 / 0.741 (0.06; their board, tiers include held-out items) |

T 是 `head.pt` 中的温度，拟合于该次试验的 decision-v7 开发行（Kev-27B v2 与 Kev-9B v2：其各自 round 注册过的留出数据集池，648 道题；round 28 对 Kev-4B 和 Kev-0.8B 测试了同一池并保留了已发布的 T）；锁定的 Brier 在该 T 下提供。
证据：`runs/release/kev-{27b-r23,27b-v2,9b-r27,4b-r10,08b-r15}.json`（`kev-27b-v2` = v1 的 B1 v2 记录）、`experiments/releases/*.json`、`runs/release/kev-27b-r23-published.json`、`runs/jevbench-public/`、各模型卡。先前的权重是 Hub 标签（`kev-27b@v1-lora`、`kev-4b@r8-documents-release`、`kev-4b@night2-du-release`、`kev-0.8b@night2-du-release`、`@v7-base`）。

### Kev 1.0 基线（发布于 2026-10-01）

**Kev 1.0 是衡量 Kev 2 所用的基线。** 某个尺寸的 Kev 2 候选，会在相同的题目上、在各侧已发布的温度下，与该尺寸的 Kev 1.0 检查点进行比较，下面这些 1.0 读取便是它的父级读取。Kev 1.0 不训练任何东西：它只是用正式的模型卡（PR #206）给这四份已发布的检查点做了版本化。以 `jaredpalmer/kev-<size>@v1.0` 加载一个父级；GitHub 的 `kev-1.0` 发布包含三个适配器 tarball，而 Kev-27B 仅在 Hub 上（"Released: Kev 1.0"、`runs/release/kev-1.0.json`）。

| size | checkpoint (trial) | Hub revision (weights) | T (fit) | locked transfer-v4 acc / Brier | breadth-v1 test index (all 14) | transfer-v4 dev | validated context |
|---|---|---|---|---|---|---|---|
| Kev-0.8B | `r15-08b/00-trial-0` | `9a45d25e` | 2.35 (in-distribution; kept by round 28) | 0.697 / 0.397 | 23.3 [21.2, 25.9] | 0.648 | 8,192 (16k lower bound −8.5 pp, `runs/r28-readout/context.json`) |
| Kev-4B | `r10-skills/00-trial-0` | `139fdd94` | 2.41 (in-distribution; kept by round 28) | 0.838 / 0.224 | 38.0 [35.5, 41.3] | 0.817 | 8,192 (16k lower bound −3.4 pp, `runs/r28-readout/context.json`) |
| Kev-9B v2 | `r18-9b/00-trial-0` (round 27 `9b-r18a`) | `b5d8c18e` | 2.19 (held-out pool) | 0.852 / 0.199 | 41.0 [38.8, 43.9] | 0.820 | 8,192 (16k lower bound −3.7 pp, `runs/r28-readout/context.json`) |
| Kev-27B v2 | round 23 `27b-k-w85` | `28be62e9` (`v1.0` = `af0e6d55`: card commits since) | 1.32 (held-out pool) | 0.889 / 0.154 | 52.3 [49.2, 55.4] | 0.851 | 65,536 (64k lower bound −2.4 pp, `runs/r28-readout/context.json`) |
| Jev (reference) | hosted | – | – | 未读取 | 54.0 [51.2, 57.0] | 0.857 | – |

- Index：`runs/fam-breadth-test-report/report.json`（2026-09-30 的模型族读取；Kev-27B v2 那一行是 round 23 的 `r23c-27b-cand-breadthtest`），以及 Jev 的 `runs/r23-breadth-report/report.json`。锁定读取：`runs/locked/kev-{08b-r15,4b-r10,9b-r27,27b-r23}-ungated`。每个尺寸的其余内容均在其模型卡上（`docs/model-cards/`），在 `docs/claims.json` 中可追溯。
- 一个 Kev 2 规则应当对照这些父级读取的留出数据集面板：breadth-v1 dev / test（已审计：去掉了 `routerbench`、`cfcolor`、`humicroedit`、`chessbench`）、tasksource-heldout-v1 dev（去掉了七个私有族；4B 0.677、0.8B 0.515 在其已发布的 T 下，`runs/r28-readout/round28.json`；9B v2 0.706 在池 T = 其已发布 T 下，`runs/r29-readout/round29.json`；27B test 0.795）、transfer-v4 dev，以及锁定的 transfer-v4 test，每个候选各读一次。breadth-v1 test 与 tasksource-heldout-v1 test 分区已为 27B（round 23/24）读取过，而 breadth-v1 test 已为每个尺寸（模型族读取）读取过：在它们之上做 Kev 2 确认属于第二次读取，证据弱于一个全新的面板。
- 经验证的上文长度（仅报告，round 28 的规则）：从 16k 起最大的名义桶，其与 8k 桶的配对 CUAD 准确率差，其 95% 下界须 ≥ −3 pp（其下所有桶也如此）；若 16k 失败则为 8,192。数值来自阶段 B 的 longdoc-v1 开发读取（Kev-27B：round 23 的 `r23-27b-k-w85-longdoc`），`runs/r28-readout/context.json`：Kev-0.8B、Kev-4B 与 Kev-9B v2 为 8,192（各自在 16k 失败：下界分别为 −8.5、−3.4、−3.7 pp；在 32k 三者都明显低于 8k），而 Kev-27B v2 为 65,536（64k 下界 −2.4 pp）。
- Kev 2 应当据此评判的已知差距：分布内的增益（hard / devtools / documents 分区是被训练过的）、27B 的 CUAD 校准（ECE 0.053 vs v1 的 0.007）、27B 以下的日期运算（`deadline` 0.35 / 0.65 / 0.725，Jev 0.95）、Kev-0.8B 的 When2Call 回退（test 0.133）、Kev-4B / 0.8B 在分布内拟合的温度，以及没有对 Kev-9B 或 Kev-27B 的 Mac 测量。

### 与 Jev 及外部模型对比

- **Decision Index 0.2**（`multimodalart/jev-decision-index`，40 个基准，机会校正）：Jev 51.67（ECE 0.065）、AutoJev-27B 50.94（ECE 0.023）、Kev-9B 35.41（ECE 0.16）、Kev-4B 31.31（ECE 0.20）。Kev 各项都是旧的检查点（4B 那项早于 round 10）；Kev-27B 不在其中。
- **AutoJev-27B vs Kev-27B**（仅报告，协议写在任何 AutoJev 读取之前；`A:runs/autojev-h2h/report.json`、`A:PLAN.md` 的 "External head-to-head"）。`denis-pplx/autojev-27b` 是基于同一基础版本、在 73k 精选合成决策上做的全权重 SFT。AutoJev 由其自有服务器提供；Kev-27B 在其已发布的 T 1.38 下（脚本的第一版用了试验内拟合的 1.19；当天纠正，准确率不变）。仅在共享题目、开发或公开分区上配对：

  | suite (questions) | AutoJev | Kev-27B | Jev | AutoJev − Kev, acc [95 %] | ECE AJ / Kev |
  |---|---|---|---|---|---|
  | transfer-v4 dev (656) | 0.863 | 0.848 | 0.857 | +1.5 [−0.6, +3.7] | 0.041 / 0.043 |
  | hard-v1 dev (1,083) | 0.782 | 0.733 | 0.777 | **+4.9 [+2.4, +7.3]** | 0.103 / 0.047 |
  | devtools-v1 dev (1,072) | 0.708 | 0.702 | 0.715 | +0.6 [−0.7, +1.8] | 0.105 / 0.096 |
  | documents-v1 dev (920) | 0.877 | 0.862 | 0.868 | +1.5 [−0.1, +3.3] | 0.015 / 0.088 |
  | SemIf (144) | 0.993 | 0.972 | 0.965 | +2.1 [0.0, +4.9] | 0.048 / 0.068 |
  | scienthoon (873) | 0.769 | 0.796 | 0.753 | **−2.7 [−4.9, −0.6]** | 0.071 / 0.044 |
  | WANLI-v2 (1,002) | 0.764 | 0.745 | - | **+2.0 [+0.3, +3.7]** | 0.082 / 0.070 |
  | TypeSafe (89) | 0.865 | 0.865 | - | +0.0 [−7.4, +8.1] | 0.082 / 0.057 |
  | transfer-v9 dev (1,046) | 0.812 | 0.822 | 0.854 | −1.1 [−3.0, +0.9] | 0.045 / 0.050 |

  宏观准确率 0.826 vs 0.816；在九个套件中有七个的 Brier 是 AutoJev 更优。JevBench 公开：AutoJev 0.870（hard 0.739，hard ECE 0.075）对比 Kev-27B 0.866（0.721，0.128）；在 111 道 hard 题上配对为 +1.8 pp [−3.6, +7.2]。Kev-27B 未发布的 round-10 skills 分支（hard-v1 0.885、devtools-v1 0.787）会在那两个套件上领先；但它没通过我们的 scienthoon 守门。
- 宏观准确率 0.826 对 0.816；在九个套件中有七个 Brier 更优的是 AutoJev。JevBench 公开：AutoJev 0.870（hard 0.739，hard ECE 0.075）对 Kev-27B 0.866（0.721，0.128）；在 111 道 hard 题上配对为 +1.8 pp [−3.6, +7.2]。Kev-27B 未发布的 round-10 skills 分支（hard-v1 0.885、devtools-v1 0.787）会在那两个套件上领先；但它没通过我们的 scienthoon 守门。

### 进行中与待处理

- **Round 19**（基于 `sft-v1` 对 Qwen3.8-27B 做全权重 SFT）已读取结果：**无候选**；每个分支都未通过 scienthoon、合并的外部集以及校准标准（见 "Round 19 result"）。**Round 20**（无训练；在留出数据集上拟合温度来提供 round 19 的检查点，外加与基础模型的 WiSE-FT 插值）已读取结果：**无候选**，6 个插值中有 0 个通过。注册的固定校准温度：分支 (a) breadth ECE 0.0085 vs Kev-27B 0.0118。每个分支仍没通过 scienthoon 和合并的外部集（见 "Round 20 result"）。一份仅报告的分析发现，scienthoon 失败的全部代价来自一个边界判断（把平和的抱怨读成"愤怒"），并且在该套件上 Kev-27B 是基于 Kev 数据从基础模型训练出的六个 LoRA 检查点中最好的一个。其余五个，包括其自身配方的第二个种子，都无法通过针对它的守门（`runs/r20-scienthoon/analysis.md`）。**Round 21**（基于 `sft-v2-r21` 从基础模型做全权重 SFT，32k 状态，在 8k 处无配对门控，两个学习率，快照作为候选读取）**在启动时失败**：两个分支都在第 62 步耗尽 GPU 内存，在任何快照之前，因此没有任何读取（"Round 21 result"）。**Round 22** 以每遍内存上限和按 round 21 实测速率确定的训练集规模，重复了其科学与规则（`sft-v2-r22`，145,840 条记录），一个分支（lr 2e-6），已读取结果：**无候选**，4 个（在 0.25 / 0.5 / 0.75 与最终的快照）中有 0 个通过。主指标通过并随训练增长（最终：breadth +1.3 [+0.3, +2.3]、tasksource-heldout +3.8 [+2.3, +5.3]、Kev panel +7.8），域外套件好得多，而 scienthoon（−5.5 [−7.8, −3.2]）、合并的外部集（−2.2）、短状态准确率以及 CUAD 校准（ECE ~0.10 vs 各长度下 0.06-0.07）失败（"Round 22 result"）。Modal 给这次试验提供了其 3 次尝试中的 2 次；最终由一次手动续跑完成（PR #163 修复重试）。
- **Round 24**（回顾性选择：2026-09-27 审计的套件裁定作为一个规则作用于全部 12 个全权重 27B 检查点，无训练）选定了 `27b-r22-final`（round 22 的最终），它**未确认**（"Round 24 confirmation"）。它在未触碰的测试分区上通过了测试阶段：breadth-v1 +1.5 [+0.5, +2.5]、tasksource-heldout-v1 +5.3 [+3.7, +7.0]、合并的 hard/devtools/documents-v1 +8.6 [+7.1, +10.0]、documents-v2 +3.8。其测试上的 breadth 指数 53.7 [50.5, 56.7]，对比 Jev 54.0、Kev-27B 50.2 与 AutoJev 50.0。它**未通过锁定阶段**：锁定 transfer-v4 0.8841（656 题中 580 题）对比注册门槛 0.886（需要 582 题；Kev-27B 0.8963）。提供的 Brier 0.155 通过了，bf16 提供检查也通过了。在 longdoc CUAD 测试上它更差：−1.8 [−3.2, −0.5]，ECE 0.055 vs 0.007（仅报告）。门槛维持注册值，未发布任何内容。
- **Round 23** 被重新注册（2026-09-28），未启动：无训练，六组将 round 22 最终向 Kev-27B 自身权重做的混合（α 0.85 / 0.70 / 0.50，SFT 头或混合头），在 round 24 审计过的规则下、用 round 24 的确认来读取（"Round 23 (registered)"）。其首次注册（round 22 的规则，含 scienthoon）从未启动，已被取代。
- **Round 25**（持续的、从 **Kev-27B** 出发的全权重 SFT，其 LoRA 已合并进全权重，基于 `sft-v2-r25`：45,515 条记录，b1v2 replay 占 30%，无长文档族，状态 ≤ 16k；lr 1e-6 与 2e-6；8 个候选）已读取结果：**无候选**（8 个中 0 个；"Round 25 result"）。两个研究各一次尝试即训练完成（各 1.5 小时）。每个候选都没通过 breadth-v1 ECE（0.023-0.035 对照门槛 0.0176）。`27b-lr1e6` 与 `27b-lr1e6-s75` 仅这项失败，通过了 12 项标准中的 11 项。lr 2e-6 分支还失败了短状态准确率与 breadth 主指标。Replay 在 lr 1e-6 下守住了短状态（−0.3 到 −0.8 pp）且 CUAD 准确率在开发集上守住，但 CUAD ECE 仍然上升（0.087-0.103 对照 0.063）。对照 round 23 已确认的 `27b-k-w85`（仅报告），没有任何分支在任何门控面板上领先。未确认也未发布任何内容。
- **Round 26**（round 25 的 lr 1e-6 分支，相同的合并 Kev-27B 初始化与计划，仅一处改动：tasksource-v1 在 `sft-v2-r26` 上翻倍，58,515 条记录；4 个候选）已读取结果：**无候选**（4 个中 0 个；"Round 26 result"）。该研究一次尝试训练完成（1.62 小时）。最终 `27b-lr1e6` 通过 12 项标准中的 11 项，仅失败于 breadth-v1 ECE（0.0233 对照门槛 0.0176），与 round 25 的最终（0.0235）相同。快照也失败了 breadth 主指标（下界 −0.16 到 −0.04 pp），且 s50 失败于短状态准确率。把 tasksource-v1 翻倍并未改变 breadth：对照 round 25 的 lr 1e-6 最终（仅报告，同比例的运行）breadth +0.2 [−0.3, +0.7]、tasksource-heldout +0.5 [−0.5, +1.5]、breadth ECE −0.000。对照 `27b-k-w85`（仅报告）没有任何分支在任何门控面板上领先。未确认也未发布任何内容。
- **Round 17**（从 Kev-27B 出发的 27B skills 增量，replay 10,000，研究 `r17-27b`，spec `experiments/rounds/r17.json`）。分支 (a)，lr 2e-5，已读取（`runs/r17-readout/round17.json`，在研究检出中，尚未提交到任何地方）且**不是候选**：主指标 +12.1 [+10.4, +13.9]（hard-v1 dev 0.733 → 0.895，+16.2 [+13.5, +19.0]；devtools-v1 dev 0.702 → 0.783，+8.0 [+5.7, +10.4]）、短状态 +0.3 [−0.9, +1.5]、合并外部集 −0.1 [−1.0, +0.7]、hard-set ECE 0.047 → 0.018，但 documents −1.5 [−2.8, −0.4] 未通过 ≥ −2 pp 下界守门，且 scienthoon 低于其界限。分支 (b)，lr 1e-5，仍在训练或读取中；**结果待定**。其读取落在研究检出（`research/overnight-r6`）；用 `uv run python -m kev.rounds readout experiments/rounds/r17.json --root <research checkout>` 在那里读取。主分支的框架拒绝为已记录的 round 启动读取，因此若分支 (b) 通过，确认将从该检出启动。
- **scienthoon 已移除**（2026-09-27）：`evals/external/scienthoon-v1` 不再是 Kev 的评估；过去的裁定仍然有效，且从 round 23 起不再有 scienthoon 读取或守门（见下 "scienthoon removed"）。Round 24 的审计规则（round 23 现在遵循）不对合并的外部集设门：SemIf、WANLI-v2 与 TypeSafe 仅为报告。
- **Kev-27B v2 已发布**（2026-09-30，Jared 批准）：round 23 的 `27b-k-w85`、T 1.32，即 `jaredpalmer/kev-27b` 主分支（权重提交 `28be62e9`、卡片 `0d7f9b49`）；v1 为标签 `v1-lora`（"Released: Kev-27B v2"）。
- **documents-v1 与 hard-v1 训练分区已发布**（2026-09-30）：两者都在 `jaredpalmer/kev-suites` 的 `cc4bac80`（`SUITES_REVISION`）中，因此 Kev-4B 与 Kev-0.8B 的训练数据可获取（Next，第 3 项）。
- **Rounds 28 和 29**（Kev 1.0 准备，无训练）。其扫描的阶段 A（68 次短状态开发读取，PR #203）已完成。**Round 28 已读取结果：两个尺寸均无候选**（`runs/r28-readout/round28.json`），因此 Kev-4B 保留 T 2.41、Kev-0.8B 保留 T 2.35。`4b-r10`（池 T 2.297 [2.047, 2.520]）两个条件都失败：Brier −0.0001 [−0.0005, +0.0003]、ECE 0.0252 对照 0.0240。`08b-r15`（池 T 2.520 [2.194, 2.828]）两个条件都通过（ECE 0.0375 对照 0.0484、Brier −0.0020 [−0.0025, −0.0014]），但失败于 hard-v1、devtools-v1 与 documents-v1 的 ECE 守门（相对 0.005 的容差分别为 +0.011、+0.007、+0.020）。阻碍阶段 B 的长状态内存墙已修复（PR #202）。阶段 B 对已发布检查点的 longdoc-v1 读取给出了每个尺寸的已验证上下文长度（仅报告，`runs/r28-readout/context.json`）：Kev-0.8B、4B 与 9B v2 为 8,192，Kev-27B v2 为 65,536。**Round 29：无候选；Kev-9B v2 维持不变**（`runs/r29-readout/round29.json`；每个分支都没通过 tasksource-heldout-v1 主指标，v2 还失败于 breadth-v1；十个分支的 longdoc 读取因预算中止，这不会改变裁定）。见 "Round 28 (registered)" 与 "Round 29 (registered)"。
- 等待 Jared 决策的事项：将 Kev-27B（以及新的 4B / 0.8B）提交到 Decision Index。
- 花费：Modal 在 2026-09-29T13:01Z（round 26 最后一次读取之后）计量 $4,558.69（+$104.88，相对于其启动读取时的 $4,453.81；11:17Z 的读数为 $4,650.37，+$196.56，并在 12:56Z 被下调；夜间上限 ≈ $5,980，硬停止 $5,700）。在 2026-09-29T06:00Z（round 25 最后一次读取之后）为 $4,461.42（相对于其注册读取的 $3,966.94 增加了 $494.5；夜间上限 ≈ $5,980，硬停止 $5,600）。更早：约 $3,790（含约 $80 的计量延迟）于 round 23 重新注册读取时、2026-09-28、round 24 确认之后（全工作区；夜间上限 $5,000 已计量）。$3,571.88 于 2026-09-27T13:32Z（round 23 的首次注册读取；round 22 相对其注册读取 +$903.36，全工作区）。$2,668.52 于 2026-09-26T13:42Z（round 22 的注册读取：round 21 失败的试验与父级读取约 $135，round 22 的上限探测约 $12；夜间上限 $5,000 已计量）。$2,522.65 于 2026-09-26T06:49Z（round 21 的注册基线）。在此之前，$2,488.88 于 2026-09-26T00:02Z（round 20：相对其注册基线 $2,434.01 增加了 $54.87，全工作区）；$2,434.01 于 2026-09-25T22:53Z，相对 round 19 的注册基线 $1,599.26 增加了 $834.75（其训练、重打分与读取，加上工作区的其他应用）；更早，$1,377.01 于 2026-09-24T12:11Z 加 round 17 的准入上限（$100.24），night 3 用了 $1,000 授权中的 $292。AI Gateway $0.13（仅 Jev 参考读取；其中 $0.064 是 round 24 的 breadth-v1 test 读取）。Modal 赞助该项目（$5,000 额度，可追加）。

## 我们学到的东西

每条发现都标注了其证据。比率以百分点计，区间为配对记录聚类的 95% bootstrap。

1. **真实文档与技能数据是被测出的最大杠杆。** 单轮增量在留出的 CFPB 文档上获得 +7 到 +24 pp、在 hard-v1 上 +15 到 +30 pp、在 devtools-v1 上 +8 到 +17 pp，在每个尺寸上都成立（round 7-18，`A:PLAN.md` 的 "Night 3"）。这些增益按构造就在分布内（相同来源或生成器、留出的模板）。分布外检查是 JevBench：Kev-4B round 10 在其公开 hard 层上获得 +9.0 pp [+2.7, +15.3]（新对 12 题、新错 2 题）；Kev-0.8B round 15 +2.7 pp [−1.8, +7.2]（`runs/jevbench-public/`）。
2. **此类增量的代价落在其他套件上，并随尺寸增大。** 在 4B 处免费（round 8、10）。约 1 pp 的短状态准确率损失出现在 0.8B，这只有合并的 1,800 题短面板（transfer-v4 dev + transfer-r3 test）能约束（round 7-9 仅在 656 题面板上失败；round 11 与 15 在合并面板上通过）。WANLI-v2、scienthoon 或 documents 在 9B（round 7、9、11、12、16、18）。scienthoon 在 27B（round 10：−1.8 [−3.0, −0.7]），以及 scienthoon 加 documents 在 27B 配合更多 replay（round 17，分支 (a)）。
3. **在 0.8B，堆叠的增量会相互侵蚀；同一份数据放在一次增量中则通过。** 在 documents 候选之上的 skills 损失了 documents 与短状态准确率（round 13）；documents + skills 一起训练则全部通过（round 15）。在 4B，堆叠有效（round 8 → round 10），而来自相同生成器的更多数据收益递减（round 14：前 6,000 条 hard-v1 记录 +26 pp，接下来 12,000 条 +5 pp）。
4. **在 9B replay 不再有帮助，且未能修复 27B 的外部代价。** Replay 6,000 消除了 documents 增量的外部代价（round 9）但未消除 skills 增量（round 12：合并外部集 −2.1 / −3.5）。Replay 10,000 削减了外部代价（round 16：−0.6）但随后代价落在 documents；将 documents 与 skills 配合 replay 10,000 一起训练修复了 documents（+7.0）但仍失败于 WANLI-v2 与 scienthoon（round 18）。round 7、9、11 的每个 9B documents 分支都获得 +6.5 到 +7.3；种子之间变化的是 WANLI-v2。在 27B，skills 增量配合 replay 4,000 失败于 scienthoon（round 10）；配合 replay 10,000（round 17，分支 (a)）仍失败于 scienthoon，且现在也失败于 documents（−1.5 [−2.8, −0.4]），尽管合并外部集持平（−0.1 [−1.0, +0.7]）。
5. **一个在简单分布内行上拟合的温度，无法迁移到困难或遥远的工作负载。** 在 hard-v1 开发集上提供的 ECE：Kev-4B 0.137、Kev-9B 0.073、Kev-27B 0.047；一个在 hard-v1 自身行上重拟合的温度（组不相交、折叠外）给出 0.067 / 0.034 / 0.041（`A:PLAN.md` 的 "Target A, first measurement"）。在 WANLI 上，一个工作负载温度将 Kev-9B 的 ECE 从 0.131 降到 0.037（round 4.1，`runs/kev-*-wanli-v1/calibration.json`）。Decision Index 的 ECE：Kev-9B 0.16、Kev-4B 0.20、AutoJev 0.023。在 hard 数据上训练也会移动它（Kev-4B round 10：JevBench hard ECE 0.263 → 0.112）。单一的全局 T 确实能从 decision-v7 迁移到 transfer-v4（night 2，#2a）；按（类型、K）的温度以及一个 logistic 可靠性头反而更差（night 2 #2a、round 4.10）。训练来源的留出*题目*仍在分布内：round 19 的 SFT 分支，以在 `sft-v1` 开发行上拟合的 T 0.955 提供，其 breadth-v1 ECE 为 0.059 / 0.065 对比 Kev-27B 的 0.012；一个在留出*数据集*上拟合的温度将分支 (a) 带到 0.017（探索性的，在看 breadth-v1 之后选定；"Round 19 result"）。Round 20 注册了这样一个池（八个留出公开来源的 648 道题，外加 MMLU-Pro，没有任何规则面板读取它）。它给出分支 (a) 的 T 1.41：breadth ECE 0.0085 vs Kev-27B 0.0118，Kev-panel ECE 0.0193 vs 0.0216。每个最终以及每个低至 α 0.70 的插值都通过了两个校准标准（"Round 20 result"）。
6. **hard-v1 逐个族地追踪 JevBench 的 hard 层**，且无共享题目（屏计数见 `evals/hard-v1/overlap.json`）：Jev 在概率、日期与判断上领先；Kev-27B 在长策略与歧义上持平或领先（两边都如此，`A:PLAN.md` 的 "Round 10"、基线段落，以及 "JevBench"）。
7. **在广泛数据上的全权重 SFT，在同一基础上略微胜过我们的 LoRA 配方**（见上 AutoJev 表）：在九个套件中有八个持平或领先，在 JevBench 的 hard 层与 documents 上校准好得多，在 scienthoon 上落后。这不是一个受控比较：AutoJev 在方法（全权重）与数据（73k 广泛合成决策；我们的 replay 仅限 decision-v7）上同时不同。Round 19 在我们自己的语料上把它们分开：广泛数据承载了增益（在 `sft-v1` 上的全权重 vs 在 Kev-27B 自身数据上的全权重：Kev panel +9.1 [+7.8, +10.5]、短状态 +2.9 [+1.7, +4.3]），而全权重取代 LoRA 用在相同数据上，代价是短状态 −3.0 [−4.3, −1.9] 与 scienthoon −3.7 [−6.0, −1.5]，且毫无增益（"Round 19 result"）；SFT 分支保留了那份 scienthoon 代价（−2.9、−3.6）。Round 22（从基础模型在扩展的 `sft-v2-r22`、32k 状态上做全权重）随训练增长增益（最终：breadth +1.3、留出的 tasksource 数据集 +3.8、Kev panel +7.8、域外套件 +1.5 到 +3.9 且 ECE 低得多）并保留了在 scienthoon（−5.5）、合并外部集（−2.2）、短状态（−1.2）与 CUAD 校准上的代价。其语气配对消除了"平静被称愤怒"的错误（0 次，对比 Kev-27B 的 9 次），但它现在漏掉愤怒工单（28 次对比 2 次）并丢失了 `priority`（0.419 vs 0.529）（"Round 22 result"）。
8. **知识由基础模型决定。** MMLU-Pro：未训练的 Qwen3.5-9B 0.540、Kev-9B 0.545（经过 night-2 增量后为 0.515），Kev on Qwen3.6-35B-A3B 0.550，未训练的 Qwen3.8-27B 0.635，Kev-27B 0.665，Jev 0.840（night 2 #7/#8；`A:PLAN.md` 的 "Qwen3.5 port" 阶段 0；A2）。Solomon 在 27B 发现了相同结论。
9. **在我们格式上的 LoRA 训练会侵蚀一个 Base 检查点的日期运算；写明天数计数可修复读取结果。** Qwen3.5-9B `deadline` 零样本 0.82 → 训练后 0.72；适配后的主干通过 LM 头打分与通过指针打分相同（该技能在表示中丢失了，`A:PLAN.md` 的 "Qwen3.5 port" §10）。一个 post-trained 的 9B 侵蚀更多（0.70 → 0.47，round 4.8）；问题侧 LoRA 在 4B / 9B 未保护它（A1）。写明天数计数后，在新诊断上 0.65 → 1.00（4B）（`runs/binding-diagnostic-v1`）。post-trained 的 27B 保持了 0.975，然而 JevBench 的 temporal_numeric 族是其最弱项（0.07）。
10. **用软目标继续训练，而非硬标签。** 歧义软目标（开放教师以 p ≥ 0.6 与公开标签不一致）在准确率与 Brier 上击败了匹配的硬标签增量（round 4.9；发布确认：Brier −0.011、在 round-3 最终面板上准确率 +1.1），但单独并不能构成一次发布。软化的 MNLI 目标导致了 WANLI 的下滑（round 6：−2.0 vs 保留 MNLI 硬标签时的 +0.3）；阈值 0.8 是长状态增量的最佳规则。
11. **被埋没的合成状态不是真实文档。** 将一个状态埋入 1-4k token 的不相关记录中代价 22-43 pp（round 4.12），而训练弥补了其中的 +17 到 +20 pp（round 5、6）；但在真实 CFPB 叙述上 Kev-9B 从短到长损失 2.6 pp，且长状态训练将 documents-v1 移动了 ±1 pp（`A:PLAN_27b.md` 的 "documents-v1 result"）。在真实文档上评判长文档工作。
12. **守门必须按一个套件所能分辨的程度来设定规模。** 在 656 道题上，准确率区间约为 ±1.7 pp，因此 −1 pp 的下界需要接近 +0.7 的点估计；TypeSafe 的 89 行摆动 ±6 pp；27B 在 200 题上的 MMLU-Pro 门控将两种子分成 0.630 / 0.665。Round 5 因三道 WANLI 题而翻转，round 6 因 0.05 pp 而翻转。9B 的种子方差在短状态上约 ±1 pp、在长面板上约 ±2 pp；单种子的 1 pp 领先是噪声。在 scienthoon 上，六个从基础模型在 Kev 数据上训练的 27B LoRA 检查点得分 0.740-0.796（sd 2.1 pp），Kev-27B 是其中最好的。大部分离散来自一个边界 Noul（"听起来愤怒"）加上 `priority`，其标签不在文本中。其余五个都无法通过针对 Kev-27B 的 −2 pp scienthoon 守门或合并外部集守门（`runs/r20-scienthoon/analysis.md`）。
13. **值得记住的负面结果**（每项都尝试并记录；没有新理由不要重复）：
    - 校准损失（标签平滑、CE + Brier、focal）对照匹配的 CE 控制：无候选（round 3）；
    - 问题侧 LoRA（A1）：在 4B / 9B 相对同种子全放置试验为 −3.4 到 −6.0 pp 的迁移，且未保持任何日期运算；在 27B 试验 C 相对试验 A 在保持 `deadline`（0.97 vs 0.975）下为 −0.9 pp，但丢失了 MMLU（0.850 vs 0.863）、留出配对（0.89 vs 0.92）、≤ 5% 误差下的覆盖率（0.645 vs 0.720）以及条件规则任务（相对 Kev-9B −21.9 pp）；放置保持 `full`；
    - 以 post-trained 的 Qwen3.5-9B 作基础（round 4.8）、Qwen3.6-35B-A3B（night 2 #8：+1.2 pp、校准更差、8× 内存）、DeltaNet-frozen LoRA（night 2 #5）；
    - 检查点平均（4.5）、可靠性头（4.10）、9B → 0.8B 自蒸馏（4.11）、默认使用 `KEV_DATE_FACTS`（4.2：将 TypeSafe 文档推过上下文）；
    - 将 night-2 增量数据折叠回后续增量（round 6 `soft-du`）、在 27B 用两轮而非一轮（round 6 后续）、在 skills 增量之上更多同生成器数据（round 14）；
    - 全权重 SFT 检查点与基础模型在 α 0.85 / 0.70 / 0.50 的 WiSE-FT 插值（round 20）：准确率守门保持失败，且 scienthoon 对分支 (a) 朝基础模型变差、对分支 (b) 变好；
    - 向基础模型的答案锚定、WiSE-FT 插值、选项隔离、特殊嵌入、`head_dim`、`perm_kl`、`ord_w`、在 4B 上更多公开数据；围绕 lr 5e-5 的从零配置空间已穷尽（overnight-1 与 "Toward v0.2"、`A:PLAN.md` 的 History）；
    - 强化学习我们尚未尝试；Laya 的评审论证，针对恰当分数的 REINFORCE 与我们最小化的对数损失有相同最优解（`A:PLAN.md` 的 "Qwen3.5 port" §6）。

## 每个 round 的常设规则

这些是经得住考验的方法。`docs/autoresearch.md` 将它们转化为一套操作程序。

- **在训练或读取之前注册。** PLAN.md 中该 round 的小节及其 spec `experiments/rounds/r<N>.json`（分支、父级、读取、规则、确认阶段）在任何训练或读取之前提交。提交时间即注册时间；不要把时钟估计写进标题。
- **开发分区用于选择。** 选择集是开发分区与已读取的面板。
- **测试与锁定分区每个候选只读取一次**，仅针对被提交规则选中的候选，且仅在该规则通过之后。绝不为第二个候选；绝不重读。一个读取面板成为其之后一切的选择集或回归集。锁定读取命名为 `kev-<size>-r<N>`（当试验内筛选门失败时加 `-ungated`）。
- **配对记录聚类的 bootstrap** 做决定：在同一行上候选减父级，`kev.rounds.paired`（2,000 次重采样、seed 0、micro）。标准基于区间界限；每个数字都带有检查点、套件与分区、n 以及报告路径。
- **守门按一个套件所能分辨的程度来设定规模。** 合并小套件（合并的外部守门、合并的 1,800 题短状态面板）；仅通过合并来为小套件设门；"不更差"守门没有点估计要求。
- **以提供的对提供的。** 每一侧都在其自身 decision-v7 开发行上拟合的温度下提供（`kev.metrics.served`）；一次发布将该 T 写入 `head.pt`（`scripts/calibrate_checkpoint.py`），其报告数字使用已发布的 T。一个硬集校准守门（hard-v1 提供的 ECE ≤ 父级 + 0.01）自 round 10 起是每个 skills round 的一部分。自 round 20 起，为校准标准提供或发布所用的温度，都是在留出*数据集*的池上拟合的（spec 的 `temperature`），绝不在训练语料自身的校准/开发行上（那些在分布内，round 19：T 0.955，breadth-v1 ECE 0.059 vs 在留出池上的 0.0085）。`kev.rounds validate` 与 `scripts/calibrate_checkpoint.py` 会拒绝一个与检查点训练数据共享数据的拟合集（`kev.rounds.pool_conflicts`）；`docs/autoresearch.md` 第 3 节有该规则及其检查。
- **每个尺寸一个候选**：通过的分支中注册排名最好的那一个；归因分支只报告，从不选择；说明尝试了多少个分支（"五次中一次通过"）。
- **训练中绝不使用任何 Jev 输出。** Jev 是通过 AI Gateway 读取的参考，有预算上限。
- **仅开放权重教师用于训练标签**（DeepSeek、Qwen 及类似）或程序化解算器；封闭前沿模型只能用于评判或筛选评估标签。
- **冻结文件永不更改。** 新数据是带清单（每个分区及输入的 sha256）的新版本化目录；之后发现的缺陷是被记录下来的，而不是就地修复。
- **一个被发现作为门控不稳健的套件是被移除，而非修补，且过去的裁定仍然有效。** 它的目录与脚本离开仓库，并列入 `kev.suite.REMOVED_SUITES`，附上原因与最后一次读取它的 round。直到该 round 的各 round 保留其注册规则与已提交的行（`kev.rounds validate` 将读取列为已归档；读取结果从各行复现）。`load_split` 拒绝该套件，`validate` / `launch` 拒绝任何后续命名它的 round。`evals/external/scienthoon-v1` 于 2026-09-27 被移除（最后一次读取：round 22；见下 "scienthoon removed"）。从 round 23 起不再有 scienthoon 守门。也不再有任何合并外部集守门：SemIf、WANLI-v2 与 TypeSafe 是被报告的，而非设门。2026-09-27 的审计发现该面板在没有 scienthoon 时（81% WANLI、分半 r 0.08；round 24）不稳健，且 round 23 在 round 24 的规则上重新注册。`evals/external/wanli-v2`、`wanli-v1` 与 `typesafe-v1` 于 2026-09-30 被移除（最后一次读取：round 26、wanli-v1 为 round 5；见下 "WANLI and TypeSafe removed"）。从 round 27 起 SemIf 是唯一外部读取，仅报告。
- **预算与状态。** 每个会话一个花费授权，在每次启动前对照已计量花费加运行中的准入上限进行检查；一个状态文件记录每个 spawn id、上限、拉取与读取。
- **负面结果要与正面结果一样充分报告**，在 PLAN.md 中，附上失败的标准。
- **未经 Jared 明确同意，不得发布或更改 Hub；代码只能通过经过评审的 PR 进入 main。**

## SFT 工作的数据策略（由 Jared 于 2026-09-24 决定）

- Kev-27B 的 SFT 语料保持私有。其数据位于一个私有 Hub 数据集（计划 `jaredpalmer/kev-private-train`）；这个公开仓库只持有每个套件的 `manifest.json`，带一个 `"mirror"` 条目，如同 `evals/documents-v2`。
- 它的构建器与生成提示位于一个私有的配套仓库，而非此公开仓库。清单记录私有仓库的提交与代码的 sha256。
- 训练标签与生成仅来自开放权重教师（DeepSeek、Qwen 及类似）或程序化解算器。封闭前沿模型只能用于评判或筛选评估标签。Jev 永不。
- 模型卡披露每个来源的种类、规模、许可、生成方法以及污染筛查，而非文本。

## Round 19 (registered)

### Round 19 - 基于广泛语料对 Kev-27B 的全权重 SFT（注册于 2026-09-25T03:45Z，在任何训练或读取之前）

**Why.** 三个结果指向同一方向。(1) 在相同基础权重上，AutoJev-27B（在 73k 广泛合成决策上的全权重 SFT）在我们九个套件中的八个上，以及在社区 Decision Index 上（50.94 vs Jev 51.67；Kev-9B 35.41），都略微胜过 Kev-27B（在 Kev 较窄混合上的 LoRA）。(2) 在 `breadth-v1`（Decision Index 五个领域中 14 个留出数据集，从未训练过）上，开发指数为 Jev 53.3、AutoJev 51.7、Kev-27B 50.2、Kev-4B 40.8，且几乎整个差距都在 Retrieval & Classification（Kev-27B 62.9 vs 75.4 / 76.1）。(3) 在 9B 与 27B 上，每个学习新技能的 LoRA 增量都在 WANLI-v2 / scienthoon 上付出代价，且更多 replay 未能修复（round 10、16、17、18）：缺失的要素是训练数据的广度，而非 replay。本 round 测试基于广泛语料对基础模型做全权重 SFT 是否能击败 Kev-27B，以及它能在多大程度上缩小与 Jev 和 AutoJev 的差距，校准采用在广泛留出池上拟合，而非在简单的分布内行上。

**Data（私有；策略见 "Data policy for the SFT work"）。** `evals/sft-v1`（本仓库仅含清单；分区在私有数据集 `jaredpalmer/kev-private-train` @ `119c1e7d`；清单 sha256 `6e0d0150`）：
- 公开训练切分：来自五个领域中 24 个经许可检查来源的 93,798 条训练记录（原生标签；仅训练切分；15 个 breadth-v1 数据集、Kev 评估套件背后的每个来源、WANLI、MMLU / MMLU-Pro 与 JevBench 被排除；每条记录都针对它们全部做了筛查）；
- Kev 现有的训练数据：Kev-27B 自身的训练集（b1v2：带软目标的 decision-v7 + dates/unknowable + 长状态）、documents-v1 训练（减去针对 documents-v1/v2 评估叙述标记的 142 条近似重复）、hard-v1 训练 + 一个全新种子的 hard-v1 集、devtools-v1 训练（减去针对其自身 dev/test 的 258 个筛查命中）；
- 合成：65,667（训练 61,094 + 来自训练组的 6,259 条软目标记录）保留记录，仅由开放权重模型（GLM-5.3、DeepSeek-V4-Pro、Inkling；第四个开放模型对分歧投票）写入并标注，一道题仅当两个盲标注者都同意生成器的预期答案时才保留；族：意图 / 对话状态 / 超出范围路由、检索相关性、长文档、工具路由、rubric 评判、abstention 孪生、数值（代码计算的答案）；软目标（标注者投票分布）仅用于评判 / abstention；针对 JevBench 与每个 Kev dev/test 分区做了筛查；
- 分区：训练 198,691（337,406 题；共享每条记录的状态，141.8M 行 token）条记录；校准 8,470（14,960 题）；开发 3,483（6,146 题）（公开留出表述 + 合成留出项）。从未训练过：校准、开发。与训练数据共享数据集的 Decision Index 基准（对任何后续 Index 读取都在分布内）：ARC-Easy/Challenge、OpenBookQA、CommonsenseQA、GSM8K、WinoGrande、Amazon ESCI、BANKING77。

**Arms**（spec `experiments/rounds/r19.json`、计划 `experiments/round19/`；每次试验 8×H200、FSDP2、fp32 主参数、前缀共享行、均衡 micro-batch、每小时恢复点）：全新从 `Qwen/Qwen3.8-27B` @ `1d4bf0f2`（不是从 Kev-27B）开始，整个文本主干 + 指针头，一轮，每步 128 条记录（batch 8 × accum 2 × 8 GPU），bf16 autocast，OneCycle（10% 预热），头 lr 1e-4、`p_none_pair 0.25`（Kev-27B 的配方），最大状态 7,552 token：
- (a) `27b-lr2e6`：lr 2e-6（AutoJev 的）；
- (b) `27b-lr5e6`：lr 5e-6；
- (c) `27b-olddata`（归因，永不候选）：分支 (b) 的设置用于 Kev-27B 自身的训练集（`evals/round6/b1v2/train.jsonl` 经 `--data`；校准与开发来自 `evals/sft-v1`，如同 (a) 与 (b)），两轮——在旧数据上的全权重，因此 (b) vs (c) 衡量数据，(c) vs Kev-27B 衡量全权重 vs LoRA。

**Calibration（注册的方案）。** 温度在一个广泛留出池上拟合，而非在 decision-v7 开发行上：每个比较的每一侧都在其自身开发行上拟合的温度下提供（对 SFT 分支是 `evals/sft-v1` 开发：所有公开来源的留出表述加合成留出项；Kev-27B 保留其已发布的 1.38）；一个发布的 SFT 检查点通过 `scripts/calibrate_checkpoint.py` 在相同行上获得其温度，带折叠外检查。软目标仅用于开放权重标注者真正分歧之处；无标签平滑、focal 或 Brier 项（round 3：无一改善排序；平滑损害了 AURC）。报告、不设门：按问题类型的温度（choice / noul / score）与按选项计数，仅当折叠外 ECE 有分离区间时改善才选；breadth-v1 与 Kev panel 上 ≤ 5% 误差的覆盖率与 AURC（issue #111）；排列翻转率（训练时每条记录选项顺序重排；测试时旋转平均仍是一个提供选项）。

**Rule**（针对 Kev-27B，配对记录聚类的 bootstrap，2,000 次重采样）：
1. 主指标：breadth-v1 开发准确率下界 > 0；合并的 Kev 开发面板（transfer-v4 dev、hard-v1、devtools-v1、documents-v1）准确率下界 ≥ −1 pp；
2. 守门：短状态（transfer-v4 dev + transfer-r3 test）准确率下界 ≥ −2 pp、Brier 上界 ≤ +0.01、置信错误上界 ≤ +1 pp；WANLI-v2 与 scienthoon 各自下界 ≥ −2 pp；合并外部集（SemIf、scienthoon、WANLI-v2、TypeSafe）下界 ≥ −1.5 pp；transfer-v9 上 unknowable 占比 ≤ 0.05；
3. 校准：breadth-v1 ECE ≤ Kev-27B 的 + 0.01，且 Kev-panel ECE ≤ Kev-27B 的 + 0.01；
4. 候选：通过的可选择分支中 breadth + Kev-panel 准确率增益最大的那一个。

与之一起报告（永不设门）：Jev 与 AutoJev 在同一 breadth-v1 开发项上（其已提交的读取）以及带区间的机会校正 breadth 指数；通过未改动框架的 JevBench 公开项。

**Confirmation**（仅候选，每项读取一次，在规则之后）：breadth-v1 test（相对 Kev-27B 下界 > 0；Jev 与 AutoJev 在同一测试项上读取一次，报告）；hard-v1 + devtools-v1 + documents-v1 test 合并下界 ≥ −1 pp；documents-v2 报告；锁定 transfer-v4 准确率 ≥ 0.886（Kev-27B 0.896 − 1 pp）且提供 Brier ≤ 0.165；在任何发布之前，main 路径上的 bf16 提供检查（max |Δp| ≤ 0.03、280 题中 ≤ 1 次翻转、隔离）。

**Budget.** Modal：准入上限 $988 + $988 + $371 = $2,347（预期花费 ~$800-950：分支 (a)/(b) 各约 9 小时、带 p_none_pair，因此各一次自动恢复；分支 (c) 约 1.5 小时）（在 8×H200 上全混合一轮实测约 7.1 小时 / ~$293；重试计入每个上限），读取每分支约 $20；程序上限 $2,000 含读取与确认。AI Gateway：合成数据占 $2,460 密钥中的 $1,666（在本注册之前花费，非训练）。基线：注册时 Modal 计量 $1599.26。

### Round 19 result

**无候选。** 三个分支都完整读取：可选择的这两个分支都未通过注册规则，归因分支也失败了。读取结果 `runs/r19-readout/round19.json`（`python -m kev.rounds readout experiments/rounds/r19.json`；由 `tests/test_rounds.py::test_readout_reproduces_round_19` 精确复现）。每一侧都在其自身开发行上拟合的温度下提供：SFT 分支在 T 0.955（(a)、(b)；`sft-v1` 开发，6,146 题）与 1.0（(c)）；Kev-27B 在 1.38（其 decision-v7 开发行，即发布值）。针对 Kev-27B 的配对记录聚类 bootstrap，2,000 次重采样，micro；准确率与置信错误以 pp 计，Brier 为绝对值，ECE 为提供的相对其门槛（Kev-27B 的 + 0.01）。

| criterion (panel, n) | (a) `27b-lr2e6` | (b) `27b-lr5e6` | (c) `27b-olddata` (attribution) |
|---|---|---|---|
| 1 breadth-v1 dev acc, lower > 0 (3,075) | +1.5 [+0.4, +2.5] pass | +0.6 [−0.6, +1.7] **fail** | −0.1 [−1.0, +0.7] **fail** |
| 1 Kev panel acc, lower ≥ −1 (3,731) | +8.7 [+7.3, +10.0] pass | +8.3 [+6.9, +9.7] pass | −0.8 [−1.6, +0.1] **fail** |
| 2 short acc, lower ≥ −2 (1,806) | −1.0 [−2.16, +0.2] **fail** | −0.1 [−1.3, +1.2] pass | −3.0 [−4.3, −1.9] **fail** |
| 2 short Brier, upper ≤ +0.01 | +0.014 [+0.002, +0.024] **fail** | +0.005 [−0.007, +0.016] **fail** | +0.037 [+0.026, +0.049] **fail** |
| 2 short confident errors, upper ≤ +1 | +1.6 [+0.8, +2.4] **fail** | +0.6 [−0.3, +1.3] **fail** | +1.5 [+0.7, +2.2] **fail** |
| 2 WANLI-v2 acc, lower ≥ −2 (1,002) | +0.0 [−2.10, +2.0] **fail** | −0.1 [−2.30, +2.0] **fail** | +0.8 [−1.2, +2.7] pass |
| 2 scienthoon acc, lower ≥ −2 (873) | −2.9 [−4.5, −1.4] **fail** | −3.6 [−5.3, −1.7] **fail** | −3.7 [−6.0, −1.5] **fail** |
| 2 pooled externals acc, lower ≥ −1.5 (2,108) | −1.2 [−2.4, +0.0] **fail** | −1.6 [−2.9, −0.3] **fail** | −1.2 [−2.6, +0.1] **fail** |
| 2 unknowable share ≤ 0.05 (transfer-v9) | 0.000 pass | 0.000 pass | 0.000 pass |
| 3 breadth ECE ≤ 0.022 (Kev-27B 0.012) | 0.059 **fail** | 0.065 **fail** | 0.060 **fail** |
| 3 Kev-panel ECE ≤ 0.032 (Kev-27B 0.022) | 0.038 **fail** | 0.037 **fail** | 0.064 **fail** |

准确率（分支 / Kev-27B）：breadth 0.760 / 0.751 / 0.744 vs 0.745；Kev panel 0.863 / 0.860 / 0.768 vs 0.776；short 0.858 / 0.867 / 0.837 vs 0.868；scienthoon 0.767 / 0.761 / 0.759 vs 0.796。分支 (a) 两个主指标都通过，但失败了六个守门与两个校准标准；分支 (b) 还失败了 breadth 主指标。

**Attribution**（仅报告；注册的方案）。(b) vs (c)，即数据（相同全权重配方，`sft-v1` vs Kev-27B 自身训练集；`runs/r19-readout/b-vs-c.json`，(c) 在其自身 T 1.0 下提供）：Kev panel +9.1 [+7.8, +10.5]、短状态 +2.9 [+1.7, +4.3]（Brier −0.032 [−0.044, −0.021]）、breadth +0.7 [−0.5, +1.8]、scienthoon +0.1 [−1.6, +1.8]、WANLI-v2 −0.9 [−2.8, +0.9]、合并外部集 −0.4 [−1.6, +0.8]；Kev-panel ECE −0.027。(c) vs Kev-27B，相同数据上的全权重 vs LoRA（表末列）：任何地方都没有准确率增益（breadth −0.1、Kev panel −0.8），短状态 −3.0 [−4.3, −1.9]、scienthoon −3.7 [−6.0, −1.5]、ECE +0.043 到 +0.048。因此广泛数据承载了增益，而 scienthoon 与短状态的代价来自全权重，而非数据。

**Breadth index**（仅报告；`scripts/breadth_report.py`，机会校正，按领域与整体的 0-100 指数；`runs/r19-breadth-report/report.md`；行按保存值，不改变准确率）：

| area | Kev-27B | AutoJev | SFT (a) | SFT (b) | (c) | Jev |
|---|---|---|---|---|---|---|
| Knowledge & Reasoning | 33.8 | 32.7 | 34.4 | 34.5 | 32.5 | 37.7 |
| Language Understanding | 75.6 | 77.9 | 76.0 | 74.8 | 72.1 | 77.4 |
| Retrieval & Classification | 62.9 | 76.1 | 70.9 | 70.8 | 60.5 | 75.4 |
| Tools & Automation | 64.2 | 62.4 | 64.6 | 62.5 | 66.1 | 63.6 |
| Arts & Human Taste | 14.7 | 9.3 | 19.3 | 16.0 | 14.7 | 12.7 |
| **Overall** | **50.2** | **51.7** | **53.0** | **51.7** | **49.2** | **53.3** |

SFT 分支弥合了与 Jev 和 AutoJev 在 Retrieval & Classification 上的大部分差距（CLINC150 0.873 → 0.953 / 0.960、SGD 0.647 → 0.727 / 0.720）；(c) 没有（60.5）。

**Calibration finding.** 注册的温度是在 `sft-v1` 开发行上拟合的，这些是训练来源的留出*题目*：为此目的它们处于分布内。它得出 T 0.955（锐化），且每个校准标准都失败。一个改为在留出*数据集*上拟合的温度，修复了同一检查点上的 breadth ECE。两次探索性计算，都在看过 breadth-v1 开发之后做的，因此都不是结果：Jared 的，分支 (a) 用拟合于 transfer-v4 开发 + SemIf + scienthoon + WANLI-v2 + TypeSafe 行的 T：T 1.59、breadth ECE 0.017（Brier 0.311，对比 0.955 时的 0.319）、Kev-panel ECE 0.028；一次用 SemIf + scienthoon + WANLI-v2 + TypeSafe + transfer-v9 + transfer-r3 test 行的重建：对 (a) 相同的 T 1.59 与数字，对 (b) T 1.45 / breadth ECE 0.018 / Kev-panel ECE 0.018，对 (c) T 1.59 / 0.022 / 0.030。两个池都与规则面板重叠（transfer-v4 开发或 transfer-r3 test，以及外部集），因此 round 20 注册了一个不同的、没有任何规则面板读取的池。

**Deviations.**
- (i) 试验内打分命中了 `kev.experiment` 的 384-token 默认上下文。三个试验都训练到结束并保存了检查点（(c) 17:11Z、(a) 17:17Z、(b) 20:57Z），然后在第一条 `sft-v1` 校准记录上失败（`ContextOverflow: state exceeds 384 tokens: 2641`）：`score_trial` 用 `kev.suite.CONTEXT` 而非套件的上下文（7,552）构建其预测器。Main 在 #136（9648d37）中修复了它。三个检查点被重新打分（仅校准、开发与 transfer；未重训），从分支 `rounds/r19-score` 用 `modal_app.py::resume`：注册提交 059d3b1、作为 e11e770 遴选的 #136、以及 5ea55aa（`run_resume` 遵循 `--timeout` 并为全权重 27B 检查点获取宿主机内存；仅编排）。无法使用 Main，因为 #135（f2bb629）在训练后更改了 `kev/model.py` 这个评估器文件，而 `resume_trial` 拒绝被更改的评估器。每个试验的 `provenance.json` 记录了 `resumed_git_commit` 5ea55aa 以及被更改的非评估器文件（`kev/experiment.py`、`modal_app.py`）。
- (ii) (a) 与 (c) 的规则读取在 18:28:40Z 启动（由另一个会话、从注册检出用 `kev.rounds launch-reads`），在它们的重打分完成之前（18:52Z 与 18:47Z）；(b) 的读取在 21:05Z 启动，而其重打分仍在运行（22:03Z 完成）。它们是对最终检查点（`/runs/<trial>/checkpoint`）的注册命令，重打分不触及这些；只有拟合温度所用的开发行来自重打分。
- (iii) 一个工作区 GPU 上限将两个分支串行化：(b) 从 11:49Z 训练，(a) 继续而 (c) 直到 16:04Z 才启动。(a) 与 (b) 在 8 小时超时后各用了一次自动重试，从它们最后的恢复点继续（(b) 从 step 1352；其重试的 loss 在 steps 1360-1420 与尝试 1 匹配到 0.001，接近但登录值并非逐位一致）。

**Evidence**（已提交；总计 30 MB）：读取结果与 `b-vs-c.json`；每个分支读取的 `report.json` + `rows.json`（`runs/r19-27b-{lr2e6,lr5e6,olddata}-<tag>`）；三个试验的 `result.json`、`provenance.json`、试验内 transfer 行与 `calibration/temperature.json`；Kev-27B 的 transfer-r3 test 读取（`runs/r19-P27-r3test`）与锁定 transfer-v4 行（`runs/locked/kev-27b-v2-ungated/transfer/rows.json`，即锁定阶段的父级侧）；breadth 报告。试验的开发行带有 `sft-v1` 记录 id 与选项键，因此在数据策略下它们位于私有数据集 `jaredpalmer/kev-private-train` @ `6cc50f5d` 的 `runs/r19/` 下，sha256 在 `runs/r19-readout/private-rows.json`（`scripts/private_rows.py restore` 为有权限的账户把它们放到位）。检查点（各 48 GB）留在 `kev-runs` 卷上。花费：Modal 在 22:20Z 计量 $2,432.57，相对注册基线 +$833.31，全工作区。

## Round 20 (registered)

### Round 20 - 对 round 19 检查点的事后补救：一个留出数据集温度以及与基础模型的 WiSE-FT 插值（随本提交注册，写于任何 round-20 插值或读取之前）

**Why.** Round 19 的 SFT 分支在两个问题上失败。校准：注册的温度，拟合于训练来源的留出题目，处于分布内（T 0.955），使 breadth ECE 停在 0.059 / 0.065 对照门槛 0.022。来自基础模型的准确率漂移：scienthoon −2.9 / −3.6 pp，以及短状态 Brier 与置信错误。旧数据上的全权重显示相同的漂移（分支 (c)：scienthoon −3.7、短状态 −3.0），因此它来自全权重，而非新数据。本 round 在相同训练好的检查点上测试两种事后补救，无训练：(1) 在留出数据集上拟合的温度下提供；(2) WiSE-FT，将每个最终主干与基础模型插值（Wortsman et al., 2022），在保留 SFT 学到的一部分的同时把每个权重拉回基础模型。WiSE-FT 在我们的 LoRA 负面清单上（`lora_scale`、overnight-1 与 "Toward v0.2"）；新理由是：全权重 SFT 移动了每个权重，而增益（Kev panel +8.7、breadth +1.5）可能在部分回退后存活，同时基础模型丢失的技能回归。

**Candidates**（spec `experiments/rounds/r20.json`；父级 Kev-27B、`r6-27b-v2/01-trial-1`，读取如 round 19）：

| arm | checkpoint | weight on the SFT backbone | selectable |
|---|---|---|---|
| `27b-a` | round 19 arm (a) final, `runs/r19-27b-lr2e6/00-trial-0` | 1 | no (reference) |
| `27b-b` | round 19 arm (b) final, `runs/r19-27b-lr5e6/00-trial-0` | 1 | no (reference) |
| `27b-a-w85`, `27b-a-w70`, `27b-a-w50` | `/runs/r20-wise/27b-a-w{85,70,50}/checkpoint` | 0.85 / 0.70 / 0.50 | yes |
| `27b-b-w85`, `27b-b-w70`, `27b-b-w50` | `/runs/r20-wise/27b-b-w{85,70,50}/checkpoint` | 0.85 / 0.70 / 0.50 | yes |

最终项已经失败于任何温度都无法改变的准确率守门（argmax 与温度无关）：对两者都是 scienthoon、WANLI-v2 与合并外部集，外加 (a) 的短状态准确率与 (b) 的 breadth。它们被读取只是为了展示注册温度对校准标准的效果，并作为每条插值路径的 α = 1 端点；六个插值是唯一可选择的候选（最终项上 `"select": false`）。

**Interpolation.** `scripts/interpolate_checkpoint.py`（`modal_app.py::interpolate`、CPU 容器、`kev.budget` `INTERPOLATE_*`）：文本主干 = α · SFT + (1 − α) · base，在 fp32 中，一次性舍入到检查点的 bf16；基础模型 `Qwen/Qwen3.8-27B` @ `1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0` 由训练所用的同一 `DecisionModel` 路径构建，因此张量名匹配，任何名称或形状不匹配在写入任何内容之前就被拒绝；保留 SFT 指针头与 tokenizer 文件；`head.pt` 记录 `interpolation: {alpha, sft: {path, weights_sha256}, base}`；每个检查点先写入 `.partial`，完成后再重命名，旁边附带 `interpolation.json`。在随机两层 Qwen3.5 上的测试：α = 1 与 α = 0 精确复现 SFT 与基础模型，0.5 是 fp32 中点；结果作为全权重检查点通过 `kev.checkpoint` 加载。

**Temperature（注册的校准方法）。** 每个候选都在一个留出数据集池的自身行上拟合的温度下提供（`kev.metrics.served`，每个提供温度所用的目标），该池没有任何 round-19 或 round-20 规则面板读取：`transfer-r3` **calibration** 分区（读取 `r3cal`，580 条单题记录；spec 的 `sources` 允许列表保留其八个留出公开来源（composition_holdout、emotion、legacy_holdout、mmlu、paws、qnli、sciq、tweet_offensive）并丢弃其 66 条 unknowable 记录与 66 条 intact 控制，这些是 Kev 训练所用的生成策略项：448 题）外加仅 `transfer-v9` 开发的 **MMLU-Pro** 行（200 题；spec 的 `sources` 允许列表丢弃 transfer-v9 的埋入状态，它们来自与 transfer-v4 项相同的公开来源，以及其 unknowable 记录与控制）：**每个候选 648 题**。其 id 位于候选的 transfer-v4 开发行中的记录被移除（`exclude_reads`；预期无；按状态哈希，该池与 transfer-v4 开发或 transfer-r3 开发或测试都不共享任何内容）。`kev.rounds` 拒绝在任何温度相关标准读取的面板内部做池读取；每个候选的拟合（行、计数、T）写入读取结果。Kev-27B 在其已发布的 1.38 下提供，同 round 19。选择留出数据集作为池遵循 round 19 的探索性发现，但该池尚未针对任何候选查看过，且裁定依赖于未触碰的测试分区。一个发布的候选发布在相同的池上拟合的温度（`scripts/calibrate_checkpoint.py --rows <r3cal rows>:composition_holdout,emotion,legacy_holdout,mmlu,paws,qnli,sciq,tweet_offensive --rows <v9 rows>:mmlu_pro --exclude_rows <transfer4 rows>`）。

**Reads.** 每个插值候选：round 19 的十个规则读取（breadth、hard、devtools、docs、semif、scienthoon、wanli2、typesafe、v9、r3test）+ `transfer4`（transfer-v4 开发：插值没有试验内 transfer 读取；它通过 `transfer_read` 在 Kev 与短面板中代表 "transfer"）+ `r3cal`：72 次读取。两个最终项复用其 round-19 读取（相同检查点、相同套件；`runs/r19-27b-{lr2e6,lr5e6}-<tag>` 及其试验内 transfer 读取）；对它们只有 `r3cal` 是新的：2 次读取。共 74 次读取，各一个 H200，读取超时 3,600 s（round 19 的 27B 全权重读取在启动后约 9 分钟落地；round 19 注册了 14,400 s）。

**Rule**（round 19 的，未变；针对 Kev-27B，配对记录聚类的 bootstrap，2,000 次重采样，seed 0，micro）：
1. 主指标：breadth-v1 开发准确率下界 > 0；合并的 Kev 开发面板（transfer-v4 dev、hard-v1、devtools-v1、documents-v1）准确率下界 ≥ −1 pp；
2. 守门：短状态（transfer-v4 dev + transfer-r3 test）准确率下界 ≥ −2 pp、Brier 上界 ≤ +0.01、置信错误上界 ≤ +1 pp；WANLI-v2 与 scienthoon 各自下界 ≥ −2 pp；合并外部集（SemIf、scienthoon、WANLI-v2、TypeSafe）下界 ≥ −1.5 pp；transfer-v9 上 unknowable 占比 ≤ 0.05；
3. 校准：breadth-v1 ECE ≤ Kev-27B 的 + 0.01，且 Kev-panel ECE ≤ Kev-27B 的 + 0.01；
4. 候选：通过的可选择分支中 breadth + Kev-panel 准确率增益最大的那一个（`drop_ids` 同 round 19）。读取结果说明六个中有几个通过。

**Confirmation**（仅候选，每项读取一次，在规则之后）：`tests`：breadth-v1 test 准确率相对 Kev-27B 下界 > 0；合并 hard-v1 + devtools-v1 + documents-v1 test 准确率下界 ≥ −1 pp；documents-v2 报告；`locked`：锁定 transfer-v4 准确率 ≥ 0.886 且提供 Brier ≤ 0.165（绝对门槛；round 19 的 spec 将它们编码为相对 Kev-27B 提供的 0.896 / 0.160）。spec 之外仅报告的步骤，同 round 19：Jev 与 AutoJev 在同一 breadth-v1 test 项上读取一次（`kev.jev`、AutoJev 自身服务器；`scripts/breadth_report.py`），以及在任何发布之前 main 路径上的 bf16 提供检查（`uv run modal run modal_app.py::serving --run <checkpoint> --gpu H200 --name serving-27b-r20 --flags=--isolation`：max |Δp| ≤ 0.03、280 题中 ≤ 1 次翻转）。

**Run steps**（在此 PR 合并之后）：(1) `KEV_APP_NAME=kev-sft uv run modal run --detach modal_app.py::interpolate --sft /runs/r19-27b-lr2e6/00-trial-0/checkpoint --prefix 27b-a`，然后对 `r19-27b-lr5e6` 与 `--prefix 27b-b` 做相同操作，间隔 60 秒；(2) 两者都完成后 `uv run python -m kev.rounds launch-reads experiments/rounds/r20.json`，然后 `readout`；(3) 按 `docs/autoresearch.md` 所说确认，且在锁定阶段之前从合并的 main 执行 `KEV_GPU=H200 KEV_APP_NAME=kev-sft uv run modal deploy modal_app.py`，因为 `run_locked_test` 现在读取一个没有试验的检查点（如同 `-ungated`）。

**Budget.** 准入上限：读取 74 × $6.27（H200 在 `kev.budget` 的试验资源 × 1 小时）= $463.62，插值 2 × $4.21（8 CPU、128 GiB、3 小时）= $8.41：**$472.04**；预期约 $110（一次读取约 15 分钟、约 $5.66/小时，一次插值约 1 小时 CPU）。确认，仅候选：tests 10 次读取（候选 + 父级）$62.65、锁定 $25.06、提供检查 $6.27：**约 $94**；通过 AI Gateway 在 breadth-v1 test 上的 Jev（约 $0.07，按开发读取费率，上限 $3）。基线：Modal 在 **2026-09-25T22:53Z 计量 $2,434.01**。

### Round 20 result

**无候选。** 6 个可选择的插值中有 0 个通过注册规则，且两个参考最终项都未通过。未做任何确认读取。读取结果：`runs/r20-readout/round20.json`（`python -m kev.rounds readout experiments/rounds/r20.json`；由 `tests/test_rounds.py::test_readout_reproduces_round_20` 精确复现）。每个分支都在其自身 648 池题上拟合的温度下提供：transfer-r3 校准、八个来源、448 题，外加 transfer-v9 MMLU-Pro、200 题；没有任何作为 transfer-v4 重复项被排除。Kev-27B 在其已发布的 1.38 下提供。Delta 是相对 Kev-27B 的配对记录聚类 bootstrap（2,000 次重采样、seed 0、micro）：准确率与置信错误以 pp 计，Brier 为绝对值，ECE 为提供的相对其门槛。

| criterion (panel, n) | 27b-a (final) | 27b-a-w85 | 27b-a-w70 | 27b-a-w50 | 27b-b (final) | 27b-b-w85 | 27b-b-w70 | 27b-b-w50 |
|---|---|---|---|---|---|---|---|---|
| T (pool of 648) | 1.414 | 1.414 | 1.447 | 1.447 | 1.382 | 1.350 | 1.350 | 1.350 |
| 1 breadth acc, lower > 0 (3,075) | +1.5 [+0.4, +2.5] | +1.4 [+0.4, +2.5] | +1.7 [+0.7, +2.6] | +1.5 [+0.5, +2.5] | +0.6 [−0.6, +1.7] **fail** | +1.1 [−0.1, +2.3] **fail** | +1.4 [+0.3, +2.5] | +1.7 [+0.7, +2.8] |
| 1 Kev panel acc, lower ≥ −1 (3,731) | +8.7 [+7.3, +10.0] | +8.7 [+7.3, +10.1] | +8.8 [+7.5, +10.1] | +7.4 [+6.2, +8.5] | +8.3 [+6.9, +9.7] | +8.6 [+7.2, +10.0] | +8.8 [+7.4, +10.1] | +8.2 [+7.0, +9.5] |
| 2 short acc, lower ≥ −2 (1,806) | −1.0 [−2.2, +0.2] **fail** | −0.7 [−1.8, +0.4] | −0.6 [−1.7, +0.5] | −0.6 [−1.7, +0.5] | −0.1 [−1.3, +1.2] | −0.2 [−1.3, +1.0] | −0.3 [−1.4, +0.8] | −0.2 [−1.2, +0.9] |
| 2 short Brier, upper ≤ +0.01 | +0.005 [−0.006, +0.014] **fail** | +0.004 [−0.007, +0.013] **fail** | +0.000 [−0.010, +0.009] | −0.001 [−0.011, +0.009] | −0.001 [−0.012, +0.009] | −0.002 [−0.013, +0.008] | −0.004 [−0.015, +0.004] | −0.005 [−0.016, +0.004] |
| 2 short confident errors, upper ≤ +1 | −0.7 [−1.4, −0.1] | −0.7 [−1.4, −0.1] | −0.8 [−1.6, −0.2] | −0.7 [−1.4, −0.1] | −0.6 [−1.4, +0.1] | −0.7 [−1.4, +0.0] | −0.9 [−1.7, −0.2] | −0.8 [−1.6, −0.2] |
| 2 WANLI-v2, lower ≥ −2 (1,002) | +0.0 [−2.1, +2.0] **fail** | +0.0 [−2.1, +1.9] **fail** | +0.6 [−1.3, +2.4] | +0.0 [−1.9, +2.0] | −0.1 [−2.3, +2.0] **fail** | +0.1 [−2.1, +2.2] **fail** | +0.7 [−1.4, +2.8] | +1.1 [−1.0, +3.1] |
| 2 scienthoon, lower ≥ −2 (873) | −2.9 [−4.5, −1.4] **fail** | −3.2 [−4.8, −1.7] **fail** | −3.3 [−5.0, −1.7] **fail** | −3.9 [−5.6, −2.3] **fail** | −3.6 [−5.3, −1.7] **fail** | −3.8 [−5.7, −1.9] **fail** | −3.0 [−4.8, −1.3] **fail** | −1.8 [−3.4, −0.2] **fail** |
| 2 pooled externals, lower ≥ −1.5 (2,108) | −1.2 [−2.4, +0.0] **fail** | −1.3 [−2.6, −0.2] **fail** | −1.2 [−2.4, −0.1] **fail** | −1.9 [−3.1, −0.7] **fail** | −1.6 [−2.9, −0.3] **fail** | −1.7 [−3.0, −0.3] **fail** | −1.1 [−2.4, +0.1] **fail** | −0.5 [−1.7, +0.7] **fail** |
| 2 unknowable share ≤ 0.05 (transfer-v9) | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| 3 breadth ECE ≤ 0.0218 (Kev-27B 0.0118) | 0.0085 | 0.0087 | 0.0131 | 0.0237 **fail** | 0.0173 | 0.0171 | 0.0196 | 0.0244 **fail** |
| 3 Kev-panel ECE ≤ 0.0316 (Kev-27B 0.0216) | 0.0193 | 0.0213 | 0.0146 | 0.0249 | 0.0158 | 0.0148 | 0.0198 | 0.0148 |

准确率（分支，Kev-27B 的在中括号里）。Breadth：0.760 / 0.759 / 0.762 / 0.760 / 0.751 / 0.756 / 0.759 / 0.762（0.745）。Kev panel：0.863 / 0.863 / 0.864 / 0.850 / 0.860 / 0.862 / 0.864 / 0.858（0.776）。Scienthoon：0.767 / 0.764 / 0.763 / 0.757 / 0.761 / 0.758 / 0.766 / 0.778（0.796）。Scienthoon 与合并外部集对每个分支都失败。`27b-a-w70` 与 `27b-b-w70` 仅失败于那两项。`27b-b-w50` 还失败于 breadth ECE。

**Calibration：注册的方法奏效了。** 在留出数据集池上拟合，温度落在 1.35-1.45，而 round 19 在 `sft-v1` 开发行上拟合出 0.955。每个最终项以及每个低至 α 0.70 的插值都通过两个 ECE 标准。分支 (a) 的最终项：breadth ECE 0.0085 vs Kev-27B 0.0118、Kev-panel 0.0193 vs 0.0216。在 round 19 的 T 0.955 下，相同行给出 0.059 / 0.038（分支 (b)：0.065 / 0.037；`runs/r20-readout/served.json`，仅报告）。短状态 Brier 守门现在除了 (a) 与 (a)-w85 之外每个分支都通过：(b) 的上界从 +0.016 降到 +0.009。在 α 0.50 处两条路径的 breadth ECE 都升到门槛之上（0.0237、0.0244）。

**Interpolation：朝基础模型移动并未恢复 scienthoon。** 对分支 (a) 它使 scienthoon 更差（−2.9 → −3.2 → −3.3 → −3.9，在 α 1 → 0.85 → 0.70 → 0.50）。对分支 (b) 它有助益，但不够：`27b-b-w50` 最接近，scienthoon −1.83 [−3.44, −0.23]（门槛 −2）、合并外部集 −0.47 [−1.68, +0.72]（门槛 −1.5）、breadth ECE 0.0244 > 0.0218。Kev-panel 增益在回退后存活（各处 +7.4 到 +8.8 pp），breadth 增益也如此（+1.1 到 +1.7）。WANLI-v2 在 α 0.70 移到 +0.6 / +0.7，对 `27b-b-w50` 为 +1.1。短状态在每个插值中都保持在 −0.7 到 −0.2 pp 内。

**Breadth index**（仅报告；每个分支的 breadth 行在其池 T 下由 `scripts/breadth_report.py` 提供，Kev-27B 在 1.38；`runs/r20-breadth-report/report.md`）：机会校正指数，带相对 Kev-27B 的配对差。

| | index [95 %] | vs Kev-27B |
|---|---|---|
| 27b-b-w50 | 53.7 [51.0, 56.4] | +3.4 [+0.6, +6.2] |
| 27b-a-w70 | 53.5 [50.7, 56.4] | +3.3 [+0.7, +5.8] |
| 27b-a-w50 | 53.4 [50.4, 56.2] | +3.2 [+0.5, +5.7] |
| Jev | 53.3 [50.7, 56.3] | +3.1 [−0.1, +6.2] |
| 27b-b-w70 | 53.3 [50.5, 56.2] | +3.0 [−0.0, +6.0] |
| 27b-b-w85 | 53.1 [50.2, 56.1] | +2.8 [−0.1, +5.8] |
| 27b-a (final) | 53.0 [50.3, 55.9] | +2.8 [+0.2, +5.3] |
| 27b-a-w85 | 52.9 [50.0, 55.7] | +2.7 [+0.0, +5.2] |
| AutoJev | 51.7 [49.2, 54.7] | +1.5 [−1.2, +4.6] |
| 27b-b (final) | 51.7 [48.9, 54.6] | +1.5 [−1.4, +4.3] |
| Kev-27B | 50.2 [47.4, 53.3] | - |

插值多出的指数大部分来自 Retrieval & Classification：SGD 0.647（Kev-27B）→ 0.807（a-w50）/ 0.793（b-w50），对照 Jev 的 0.793。

**Scienthoon analysis**（仅报告，已提交的行，无新读取；`runs/r20-scienthoon/analysis.md`，数字在 `drift.json`、`scripts/scienthoon_drift.py`，于 2026-09-27 随套件移除，在 git 历史 `9c41005`）：
- **损失来自一种问题类型。** 在 `angry`（"The customer sounds angry."）上 round-19/20 分支损失 5.8-13.1 pp。`queue` 多对了一题，而 `priority`（其标签遵循文本中缺失的一条规则）移动 −3.1 到 +1.7。去掉 `angry` 后，分支落在 −1.4 到 +1.0 pp。
- **出了什么问题。** 这些分支把一张关于真实问题的平和工单称为愤怒。例如："The box for order #8223 was crushed and the item inside is broken." 以及 "17일 전에 반품했는데 환불이 안 됐어요." 它们制造了 28-54 个这样的假阳性；Kev-27B 制造 9 个，Jev 8 个。55 个翻转问题中 53 个有平和文本与金标 "not angry"，因此金标是健全的。另外 15 个 `angry` 标签与其文本矛盾（每个模型都错过的标签噪声），使上限落在 0.948。
- **Kev-27B 是一个有利的抽样。** 六个 LoRA 检查点从基础模型在 Kev 数据上训练而来：B1 v2 s1 与 s2、B1 试验 A 与 B，以及两个 2-epoch 种子。它们得分 0.740-0.796（均值 0.765、sd 0.021），有 9-59 个假阳性，而 Kev-27B 是其中最好的。相对 Kev-27B，**其余五个无一通过 scienthoon 守门或合并外部集守门**。B1 v2 seed 1，即 Kev-27B 自身的配方，在 −2.7 [−4.2, −1.4] / −1.5 [−2.6, −0.5]。全权重分支得分 0.757-0.778，在或高于族均值。
- **合并外部集的损失是同一份损失。** 去掉 scienthoon 的 `angry` 题后，合并 delta 对 (a) 为 −0.4 [−1.8, +0.8]、对 (b) 为 0.0、对 (c) 为 +0.7、对 b-w50 为 +0.5 [−0.8, +1.8]。短状态损失是另一种、弥散的：对 (a) 是分散在 qnli、composition、emotion 与 tweet_offensive 上的 −18 题。
- **不是数据，也不是全权重本身。** 分支 (c)，在 Kev-27B 自身数据上的全权重，是最差的（54 个假阳性）。AutoJev，在其他数据上的全权重，制造 0 个。未训练基础模型没有 scienthoon 读取；插值指向两边。
- **对 round 21 的建议：(d) 加一个便宜的 (a)。** 接受这不是配方的回退，并将 scienthoon 与合并外部集守门登记为针对 Kev-27B 单一最佳抽样之外的某物。两个选项：针对 LoRA 族设门（例如，点估计 ≥ 其均值，且相对其中位检查点（B1 试验 A）的下界 ≥ −2 pp），或不带 `priority` 地给 scienthoon 打分，并将平和文本的 `angry` 假阳性作为诊断报告。这是 Jared 的决断，在注册时做出，而非事后。向扩展数据加入一个小的开放权重语气最小对族（同一问题写成平和或愤怒，除零售工单外的其他领域，英文与韩文；针对 scienthoon、breadth-v1 与 transfer-r3 的 `emotion` / `tweet_offensive` 筛查；绝不 paraphrasing scienthoon）。把快照作为报告读取，绝不按 scienthoon 选择：(c) 是免费的，因为 lr 2e-6 比 5e-6 制造更少的假阳性（28 vs 45）。现在不要构建 (b)，即向 Kev-27B 提供答案的 KL 锚定。它是可行的：`--anchor` 接受任何 `{record: {qid: {key: p}}}` 文件，因此需要一个行 → 目标的转换器以及一次 Kev-27B 对 replay 池的读取。但 Kev-27B 自身的 seed 1 显示其训练数据并不能修复这个边界，因此在那数据上的蒸馏也不会。

**Deviations.**
- (i) 两个插值作业运行在 Modal 应用 `kev-research` 下，而非注册的 `kev-sft`。代码、卷与命令相同，输出不受影响：每个检查点的 `weights_sha256` 与输入都在 `runs/r20-wise/<arm>/interpolation.json`，各 850 个张量，每个 α 149-230 s。
- (ii) 一个读取客户端（`27b-b-w50`）在 23:56Z 丢失 DNS。其分离的 Modal 应用继续运行，其 12 次读取在 23:57Z 手工从 `/bench` 拉取。它们是注册命令的输出。
- 时间线：插值在 23:39Z 前完成，72 次插值读取在 23:39:46Z 启动（在其之前的为两个最终项的 `r3cal` 读取），全部 74 次在 23:59:30Z 前落地，读取结果在 00:02Z 做出。

**Evidence**（已提交）：读取结果；`runs/r20-readout/served.json`（各侧在其提供 T 下的每面板准确率 / ECE / Brier / NLL，以及最终项在 round 19 的 T 下；仅报告）；每次读取的 `report.json` + `rows.json`（`runs/r20-27b-<arm>-<tag>`，仅公开套件行，无 `sft-v1` id）；`runs/r20-wise/*/interpolation.json`；breadth 报告；scienthoon 分析，外加它所用的两个不在 git 中的 scienthoon 读取（`runs/jev-scienthoon-v1/rows.json`，由 `scripts/freeze_scienthoon.py` 转换，以及 round 17 分支 (a) 的 `runs/r17-27b-r10k-lr2e5-scienthoon`）。最终项的开发行如 round 19 留在私有数据集；读取结果的复现测试用 `scripts/private_rows.py` 恢复它们，无权限时跳过。六个插值检查点（各 51 GB）留在 `kev-runs` 卷的 `/runs/r20-wise/<arm>/checkpoint`。花费：Modal 在 2026-09-26T00:02Z 计量 $2,488.88，相对注册基线 +$54.87（全工作区），在预期约 $110 与 $472.04 准入上限之内。

## Round 21 (registered)

### Round 21 - 基于 sft-v2 对 Qwen3.8-27B 的全权重 SFT：长状态与扩展数据（随本 spec 的提交注册，写于任何 round-21 训练或读取之前）

**Why.** Round 19 基于 `sft-v1` 的全权重 SFT 在广泛数据触及之处获得增益（对分支 (a) Kev panel +8.7 pp、breadth-v1 +1.5 pp），且 round 20 用一个在留出数据集上拟合的温度修复了其校准（breadth ECE 0.0085 vs Kev-27B 0.0118）。仍失败的是 scienthoon 与合并外部集。Round 20 的分析将该代价追溯到一处边界判断（把平和的抱怨读成"愤怒"），其参考 Kev-27B 是其配方六个 LoRA 抽样中最好的一个（`runs/r20-scienthoon/analysis.md`）。Round 21 从基础模型在一个扩展语料上重训：针对"愤怒"边界的语气最小对、一个经许可过滤的公开多任务组件及其自身的留出数据集、到训练上限的长状态、域外、提示注入识别与 agent trace、PII、grounding 记录。它在 round-20 证据上将 scienthoon 与合并外部集守门重置基线，在读取之前于此决定。（在 Jared 评审 PR #152 之后、任何启动之前修订：接受 32k 状态；none 配对仅在至多 8,192 token 的状态上保留于 0.25，其兄弟计入 micro-batch 代价，这是 PR #153 中的一个训练器旋钮，本 round 依赖它；sft-v1 公开来源的每个来源上限从 2,000 收紧到 1,200；`sft-v2-r21` 的校准与开发限制为至多 8,192 token 的状态。更早的 `sft-v2-r21`、kev-private-train @ `97d545ff` 与 @ `ef38326e`，从未使用。）

**Data**（私有；策略见 "Data policy for the SFT work"；本仓库仅含清单，分区在 `jaredpalmer/kev-private-train` / `jaredpalmer/kev-private-evals`；由 kev-sft `assemble-v2` @ `1b5c7f6`、`assemble/build_v2.py` 构建）。

`evals/sft-v2`（镜像 `97d545ff`）是这些冻结组件（每个文件哈希校验其组件清单；清单记录每个组件的清单路径、提交、sha256 与镜像修订）的并集：

| component | kind | train | calibration | development |
|---|---|---|---|---|
| sft-v1 (`119c1e7d`) | round 19 的语料（公开 24 来源、Kev 组件、开放权重合成） | 194,247 | 8,468 | 3,483 |
| tasksource-v1 (`f572d8f6`) | 公开多任务集合，原生标签（119 族，私有列表） | 58,191 | 3,481 | 2,088 |
| longify (`0bfa4c69`) | 由 sft-v1 训练构建的 8k-64k 状态，精确标签 | 8,000 | - | - |
| longdoc (`dce09c29`) | 代码组装的长文档 8k-64k，代码标签 | 9,060 | 484 | 197 |
| ood (`3550e29b`) | 开放权重域外 | 7,312 | 388 | 156 |
| tone (`0a56df5d`) | 开放权重语气最小对（calm / frustrated / angry） | 7,544 | 372 | 159 |
| injection (`9160a875`) | 间接提示注入识别（防御性） | 2,761 | 133 | 55 |
| agents (`45ff503c`) | 基于代码生成 trace 的 agent 会话分析 | 5,174 | 221 | 93 |
| guardrails-pii (`0ad2dbc6`) | PII 分类（代码插入的假 PII） | 4,152 | 219 | 77 |
| guardrails-grounding (`0ad2dbc6`) | grounding / 声明支持 | 5,662 | 258 | 162 |

未合并：longify 的两个监控分片（由留出的 sft-v1 *训练*记录构建，而 sft-v2 训练于其上，因此它们不是 sft-v2 的留出项）、longdoc 的 `programmatic_split` 以及 ood、injection、agents、guardrails-pii 与 guardrails-grounding 的 `adjudicated` 池（不在它们组件的默认混合中），以及 agents 的 `ood_eval_soft`（软目标评估题：仅筛查，非套件，因为 `kev.benchmark` 给硬标签打分）。

筛选：每个分区的每条记录实体化，其软目标命名选项键且和为一，并在 Kev-27B tokenizer 下严格于 `kev.model.training_context(MAX_TRAIN_STATE)`（64k 状态）中被接纳。整个并集用 kev-sft 筛查规则（精确归一化状态或内容字符串、词 8-gram Jaccard > 0.2、较小侧包含 ≥ 0.5）针对每个冻结 Kev 套件的每个评估分区（102 个分区：breadth-v1、longdoc-v1、documents-v2、tasksource-heldout-v1、transfer-r3 含其校准分区、transfer-v9 以及每个更旧的面板）、JevBench 公开以及下面新的仅评估分区（76,549 个参考项）重新筛查。该筛查丢弃了 6,581 条记录：sft-v1 4,446、guardrails-pii 816、tasksource-v1 626、injection 466、agents 135、ood 88、guardrails-grounding 4。大多是模板重叠而非题目文本。在 sft-v1（4,446）中：hard-v1 自身的生成器跨越其 train / dev / test 模板（2,794：仅按问题措辞 1,316、按带新数字与名字的场景文本 1,478）、round-4 埋入记录以及被更旧套件（decision-v1 / v2 / v5）放入校准的 decision-v7 项，以及针对 transfer-r3 / transfer-v9 的 unknowable 记录的 night-2 unknowable 模板。在合成与 tasksource 组件中，1,956 是仅按问题措辞的精确匹配，是与该组件自身至多五个留出项共享的模板，因此筛查的模板过滤器（出现在五个以上参考项中的字符串）抓不到它：guardrails-pii 816 个命中（其训练的 15%）、injection 466（14%）、tasksource-v1 529、ood 88、agents 53、grounding 4（每个命中通过比较匹配字符串核对；仅计数，无文本）。无论如何，规则按所写应用：它是注册的筛查，丢弃它们会损失语料的 2.0%。一个后续版本可以在超过五个训练记录也携带某措辞时，将其计为模板文本。没有任何命中落在温度池来源上：仅有的 transfer-r3 / transfer-v9 匹配是它们的 unknowable 记录与 intact 控制（night-2 与 round-4 生成器），而池的 `sources` 允许列表已经丢弃它们。组件间无状态重复；sft-v1 train 内 6,286 个重复（按冻结）与 tone 内 539 个（其软池与硬池共享状态）按组件冻结方式保留。记录变更：除 clean 之外的 `_meta.variant`（longdoc 的 abstention 孪生、tone 的 calm / frustrated / angry 版本、injection、agents 与 guardrails 的视图标签；31,313 条记录）移到 `_meta.twin`，因为 `kev.benchmark` 仅给 clean 行打分；tasksource-v1 记录携带来源 `tasksource`（族移到私有数据的 `_meta.tasksource_source`），因此无公开文件列出 tasksource 的族（Jared 的决定）。

| partition | records | questions | state tokens | row tokens (prefix shared) | soft-target questions |
|---|---|---|---|---|---|
| train | 302,103 | 586,690 | 609.0M | 647.8M | 19,947 |
| calibration | 14,024 | 28,018 | 20.4M | 22.2M | 297 |
| development | 6,470 | 12,655 | 8.7M | 9.5M | 179 |

训练记录的状态 token（`<state>` token 加渲染状态，Kev-27B tokenizer）：

| ≤256 | 257-512 | 513-1k | 1k-2k | 2k-4k | 4k-8k | 8k-16k | 16k-32k | 32k-64k |
|---|---|---|---|---|---|---|---|---|
| 163,741 | 30,612 | 36,473 | 35,323 | 10,697 | 4,376 | 9,359 | 8,110 | 3,412 |

`trainable_sources`：68 个名字（sft-v1 的 59 个，外加 `tasksource`、`longify`、`synthetic-v2/longdoc`、`synthetic-v2/ood`、`synthetic-v2/tone`、`synthetic-v2-guardrails/injection`、`synthetic-v2-guardrails/grounding`、`synthetic-v2-guardrails/pii`、`synthetic-v2/agent_sessions`）。校准与开发是训练组件的留出项，因此它们处于分布内：仅试验内筛查，绝不作为提供的或发布的温度。

`evals/sft-v2-r21`（本 round 的训练套件；kev-private-train @ `c00d1c95`）：sft-v2 的记录，相同顺序，训练限制为至多 32,768 token 的状态，且每个 sft-v1 公开来源至多 1,200 条记录（种子与记录摘要的 sha256 最小的那些），校准与开发限制为至多 8,192 token 的状态：训练 233,265（496,146 题、434.2M 状态 token、共享状态后 468.0M 行 token）、校准 13,385（25,362 题；剩 554 条更长记录）、开发 6,201（11,569 题；剩 231 条）。筛查上限是为试验内打分代价而设：校准与开发是分布内筛查分区（训练组件的留出项，仅用于试验的试验内温度与开发打分），没有规则标准读取它们（每个候选通过自身读取读 transfer-v4，且提供温度来自留出数据集池），且它们超过 8k token 的 785 条记录约占了一个试验在单 GPU 上试验内打分时间的一半。3,412 条超过状态上限的训练记录离开（longify 1,600、longdoc 1,443、其余 369），65,426 条离开 23 个被上限的来源（multiwoz、massive、helpsteer3 5,580 → 1,200；helpsteer2、snli、gsm8k、hotpotqa、nq、esci 4,650 以及 ledgar 4,640 → 1,200；openbookqa、medmcqa、math_qa、siqa、cosmos_qa、winogrande、casehold、csqa、aqua_rat、qasc 3,720 → 1,200；arc 2,991、quartz 2,340、strategyqa 1,215 → 1,200）。按组件，训练：sft-v1 128,821、tasksource-v1 58,190、longdoc 7,617、tone 7,544、ood 7,312、longify 6,400、guardrails-grounding 5,655、agents 4,875、guardrails-pii 4,152、injection 2,699。其训练记录的状态 token：≤256 114,262 · 257-512 25,490 · 513-1k 32,383 · 1k-2k 29,841 · 2k-4k 9,563 · 4k-8k 4,257 · 8k-16k 9,359 · 16k-32k 8,110。

为什么 32k 与这些上限：见下 "Budget and memory"。

Eval-only suites（私有镜像 `d6498d4c`，仅开发分区，仅报告；每个是其组件冻结的记录，遵循相同的变体规则，因此 ood-v2 逐字节等于其组件文件；每条 sft-v2 记录都针对它们做了筛查）：`evals/ood-v2`（1,686 条记录、4,988 题：ood 组件的留出域与葡萄牙语）、`evals/agents-ood-v1`（373 条记录、2,084 题：agents/ood_eval.jsonl）、`evals/guardrails-ood-v1`（1,263 条记录、4,949 题：guardrails-pii/ood.jsonl + guardrails-grounding/ood.jsonl + injection/ood.jsonl）。`evals/tasksource-heldout-v1`（开发 2,386 条记录 / 2,788 题，锁定 test 2,395 / 2,833；从 tasksource-v1 留出的 24 个完整数据集族，kev-private-evals @ `e4f2c71d`）仅以哈希与计数公开；其族列表在私有 kev-sft 清单（`tasksource-v1` @ `3ffc81b`），且因为行携带每条记录的来源，其行与每来源报告留在私有数据集（如同 sft-v1 的开发行，`scripts/private_rows.py`）。`kev.suite.load_split` 获取并哈希校验它。

**Arms**（spec `experiments/rounds/r21.json`、计划 `experiments/round21/`）：全新从 `Qwen/Qwen3.8-27B` @ `1d4bf0f2` 做全权重 SFT，每次试验 8×H200（FSDP2、fp32 主参数、前缀共享行），`evals/sft-v2-r21` 一轮，batch 8 × accum 2 × 8 ranks = 每步 128 条记录（`--length_sort 1`）、bf16 autocast、OneCycle（10% 预热）、头 lr 1e-4、`--max_state 32768`、`p_none_pair 0.25` 配合 `none_pair_max_state 8192`（PR #153）、seed 0；长记录的问题数按组件上限（longify 每条记录至多 6 个、32k 以上 4 个）：
- (a) `27b-lr2e6`：lr 2e-6（round 19 的分支 (a)）；
- (b) `27b-lr1e6`：lr 1e-6。

每次试验在其 1,823 个优化器步骤的 0.25 / 0.5 / 0.75 处写快照（steps 456 / 912 / 1368；`/runs/r21-27b-<lr>/00-trial-0/snapshots/step-000NNNN/checkpoint`，各约 51 GB，留在卷上；无 Hub 镜像）。候选是每个分支的三个快照及其最终检查点：共 8 个，每个可选择（`27b-<lr>-s25/s50/s75`）。每个候选的 "transfer" 行来自其自身的 `transfer4` 读取（spec 的 round 级 `transfer_read`），最终项也包含，因此规则不需要试验内打分的任何东西：该打分（校准、开发、试验内 transfer）仅用于筛查。快照还防备一次耗尽其尝试的运行：每个快照在写入时提交到卷，无论其后运行发生什么它都保持候选，且最终检查点在完成时立即提交（`modal_app.VolumeWatcher`），在试验内打分开始之前。框架无需改动即支持此点：快照分支即检查点分支，用 `launch-reads --arms` 启动；一个其试验以无 `result.json` 结束（打分期间尝试耗尽）的最终分支，从其所提交检查点以相同方式读取；一个完全没有检查点的分支由读取结果报告为未完成，不能被选择，而其他分支照常排名。

**与计划配方的一处偏离（32k 状态）与一个训练器改动（门控 none 配对），在启动之前决定。** 两者都来自 `assemble/epoch_estimate.py`（kev-sft），它将冻结训练分区的 token 形状通过 kev.train 自身的 micro-batch 代码（`microbatch_plan` / `balanced_runs` / `pass_tokens`，带 PR #153 的兄弟代价）发出，并逐 GPU 计时每遍；一步，按 micro-batch 槽，持续到最慢 rank 的该遍（FSDP2 在每层等待每个 rank）。两个遍时间模型，因为短状态测量在 none 配对代价上不一致：**A**，遍秒数 = a + 0.478·P + 0.00282·n·S²（P 以千计的填充 token、S 最长状态、n 状态数；长状态探测 `runs/sft-probe/lc-27b-8xh200`），a = 1.55 s 拟合使仅 sft-v1 记录复现 round 19 分支 (a) 实测的每记录 0.1475 s（none 配对 0.25）；**B**，对超过 8k token 的遍相同（a = 1.0，该探测），而对更短的遍为 6.91 + 0.15·P，拟合到 round 19（0.1475 s、配对）与无配对语料探测（0.13 s，`runs/sft-probe/sft2-*`）。每 GPU 内存 ≈ 59.3 + 1.17·P GiB（同一探测：在 16k / 32k / 48k / 64k 为 78 / 96 / 115 / 134 GiB）；一遍超过 64.7k 填充 token 计为超限。

| training suite (train records), none pairs | one epoch, model A | model B | peak pass | passes over the limit |
|---|---|---|---|---|
| sft-v2 at 64k (302,103), 0.25, today's trainer (as planned) | 168,100 s (46.7 h) | - | ~292 GiB | 2,529 |
| sft-v2 at 64k (302,103), none | 95,440 s (26.5 h) | - | ~137 GiB | 8 |
| sft-v2-r21 (233,265), 0.25, today's trainer | 107,482 s (29.9 h) | 101,592 s (28.2 h) | ~211 GiB | 1,416 |
| sft-v2 at 32k (298,691), 0.25 gated at 8k | 73,149 s (20.3 h) | 69,941 s (19.4 h) | ~126 GiB | 0 |
| public cap 2,000 (250,880), 0.25 gated at 8k | 68,230 s (19.0 h) | 65,203 s (18.1 h) | ~126 GiB | 0 |
| public cap 1,500 (239,880), 0.25 gated at 8k | 67,595 s (18.8 h) | 64,604 s (17.9 h) | ~130 GiB | 0 |
| **sft-v2-r21, cap 1,200 (233,265), 0.25 gated at 8k (registered)** | **67,224 s (18.7 h)** | **64,268 s (17.9 h)** | ~129 GiB | 0 |
| sft-v2-r21, 0.25 gated at 2k (not registered) | 63,415 s (17.6 h) | 60,764 s (16.9 h) | ~122 GiB | 0 |
| sft-v2-r21, no none pairs (not registered) | 55,491 s (15.4 h) | 53,691 s (14.9 h) | ~121 GiB | 0 |

- 64k 状态装不下（Jared 接受了 32k 回退，PLAN "Next" 第 0 项自身的顺序）：在 64k 下长记录设定每步的长度（一个 64k 记录让它的 GPU 忙碌约 44 s，其他 rank 在每层等它），而去掉每个 sft-v1 公开记录仍投影到试验内打分之前的 79,981 s（22.2 h）训练。64k 记录留在 `evals/sft-v2`。在 64k 读取不受影响（longdoc-v1 的 32k 与 64k 桶被读取并设门；Kev-27B 在 7.5k 状态训练，读取它们而无可分辨的下降，`runs/longdoc-v1-report/README.md`）。能让 64k 可训练的是一处训练器改动：长度分桶的步骤，使全部八个 rank 一起运行长遍。
- none 配对保留（它们教 "none of the above"，unknowable 守门与 abstention 校准依赖它），但今天的训练器无法在这些长度下运行它们：一个配对把整个记录（含状态）的两份副本加入同一遍，而均衡器看不到它们，因此任何超过约 21k token 且带一个合格 Choice 的记录都成为一次超过 GPU 的遍。PR #153 加入 `--none_pair_max_state`：仅在至多 N token 的状态上配对（此处 8,192，其中每个 sft-v2-r21 短记录都如 round 19 配对；sft-v2-r21 训练记录的 92.5% 至多 8k），从每条记录自身的流中抽取，并计入 micro-batch 代价，因此没有遍超出其代价（0 次超限遍，峰值约 129 GiB）。
- 每来源上限移动很小：长记录设定关键路径，因此每个公开来源少 500 条记录约节省 0.1-0.2 h。Jared 的规则是收紧 2,000 → 1,500 → 1,200，直到该 round 适配约 21 h 预期 / 23 h 最坏、含打分的每分支；在 1,200 它仍不适配（见下），更进一步只换来分钟级（上限 700：−0.2 h）。注册停在 1,200 并如此说明；会弥合差距的杠杆列在预算下。

**Budget and memory**（每分支，`evals/sft-v2-r21`，none 配对门控于 8k）：训练 67,224 s（A）/ 64,268 s（B）投影，× 1.03 用于每小时恢复点，外加每尝试约 10 分钟用于门控的状态 token 计数（PR #153；在 M 系列核心上约 6 分钟）与约 10 分钟模型加载：**19.9 h（A）/ 19.1 h（B）** 训练容器时间。试验内打分（校准 + 开发 + transfer-v4：20,350 条记录，全部至多 8k token，按 round 19 实测的每条 0.292 s）再加 **1.65 h**：21.6 h（A）/ 20.7 h（B）容器时间。两次超时各损失最多一小时训练回到最后的恢复点，外加约 15 分钟重启（预期总计 1.5 h，最坏 2.5 h）：

| per arm | training done (checkpoint + snapshots committed) | training + in-trial scoring | Jared's bar (incl. scoring) |
|---|---|---|---|
| expected | 21.4 h (A) / 20.6 h (B) | **23.1 h (A) / 22.2 h (B)** | ~21 h |
| worst | 22.4 h (A) / 21.6 h (B) | **24.1 h (A) / 23.2 h (B)** | ~23 h |

训练、每个快照与最终检查点都装进三个 8 小时尝试（24 小时）内，留有 1.6-3.4 h 余量；有筛查上限，试验内打分在预期情形（余 0.9-1.8 h）与模型 B 最坏情形也装得下，而在模型 A 最坏情形下超出最后一次尝试 0.1 h，此时第三次尝试会在打分的最后几分钟超时。那不会让该 round 损失任何东西：每个候选的规则读取都是独立的读取（见上），且最终检查点在打分之前提交。相对 Jared 的门槛，预期情形仍超出 1.2-2.1 h，最坏情形超出 0.2-1.1 h；剩余的杠杆未注册（Jared 保留了 8k 门控），即门控于 2,048 token（−1.0 h，B）。稍后用 `modal_app.py::resume` 完成一次被打断的试验内打分将花费约 1.7 h × $41.17 ≈ 每分支 $70，超出研究上限，未计划。峰值内存投影约 140 中的 129 GiB（round 19 在 7.5k 状态实测 94.6 GB）。

Timeout 28,800 s、`FULL_FT_RETRIES` 2：准入上限 **每研究 $987.99**（H200:8 在 $41.17/h × 8 h × 3）、两者 $1,975.98；预期 **每分支约 $914（B）- $951（A）**（22.2 / 23.1 h × $41.17/h）。若工作区 GPU 上限将两个试验串行化，如 round 19，则该 round 耗时约两倍。读取（H200，每套件超时 `modal_app.READ_TIMEOUTS`，无尺寸覆盖）：每候选 $72-75 准入上限（longdoc-v1 10,800 s、documents-v1 5,400 s、transfer-v9 3,600 s、其余 1,800 s），8 个候选 **$595**；预期约每个 $30。Kev-27B 仍缺父级读取（tsheld、ood、agentsood、guardood）：$13 上限。确认，仅候选：tests 阶段（候选 + 父级，14 次读取）$100、锁定 $25、提供检查约 $6。

相对于夜间 **$5,000 已计量** 上限的花费，基线 **2026-09-26T06:49Z 的 $2,522.65**：启动时 $2,522.65 + $1,975.98 研究上限 = $4,498.63。规则阶段结束时的预期 ≈ $2,522.65 + $1,828-1,902（研究）+ 约 $250（候选读取）+ 约 $10（父级读取）≈ **$4,610-4,685**；加确认阶段（预期约 $60、上限 $131）≈ $4,670-4,745。

在花费规则下（`docs/autoresearch.md` 第 2 节），一旦两个研究都花完其上限，读取就不能一次性全部准入（$4,499 + $595 > $5,000）：先启动一个分支的四个候选，待第一批落地后再启动另一个的。预期储备约 $255-330，因此超出注册读取的任何内容都需要新的读取。

**Temperature（MUST，`docs/autoresearch.md` 第 3 节）。** Round 20 的池，不变：每个候选都在一个留出数据集池的自身行上拟合的温度下提供（`kev.metrics.served`），该池为 transfer-r3 **calibration**（读取 `r3cal`，允许列表 composition_holdout、emotion、legacy_holdout、mmlu、paws、qnli、sciq、tweet_offensive：448 题）外加 transfer-v9 **开发 MMLU-Pro**（读取 `v9`，允许列表 mmlu_pro：200 题），减去其 transfer-v4 开发行中的任何记录（`exclude_reads: transfer`）。`kev.rounds validate` 针对分支的训练检查该池（研究套件 `evals/sft-v2-r21`，它命名 `evals/sft-v2`，后者命名 `evals/sft-v1` 及其组件；快照分支命名 `trained_on: [evals/sft-v2-r21]`）：没有池化套件是训练数据，没有池化来源是被训练的来源，且没有任何训练语料的校准/开发分区被池化。该检查是名义上的（来源名）；语义一侧是上面的筛查（没有 sft-v2 记录匹配任何池来源的题）以及 tasksource-v1 的目录，它在任何其他东西之前按名字排除 MMLU（因而 MMLU-Pro）、emotion / go_emotions、tweet_eval、QNLI 及其 SQuAD 父级、PAWS、SciQ 与 SciTail。Kev-27B 在其发布值 1.38 下提供（其试验的 decision-v7 开发行，同一拟合）。一个发布的候选发布 `scripts/calibrate_checkpoint.py` 在相同池行上拟合的温度（`--rows <r3cal rows>:<the eight sources> --rows <v9 rows>:mmlu_pro --exclude_rows <transfer rows>`），绝不带 `--allow-in-distribution`。

**Reads per candidate**（标签：套件、分区）：breadth（breadth-v1 dev）、tsheld（tasksource-heldout-v1 dev）、Kev panel 的 hard / devtools / docs（hard-v1、devtools-v1、documents-v1 dev）配合 transfer-v4 dev（每个候选的 `transfer4` 读取）、semif、scienthoon、wanli2、typesafe、v9（transfer-v9 dev：unknowable 占比与池的 MMLU-Pro）、r3test（transfer-r3 test，短面板）、longdoc（longdoc-v1 dev）、ood（ood-v2）、agentsood（agents-ood-v1）、guardood（guardrails-ood-v1）、r3cal（该池）。Kev-27B（`r6-27b-v2/01-trial-1`，Hub `01b81998`）已有除 tsheld、ood、agentsood 与 guardood 之外的每次读取的提交，`kev.rounds launch-reads experiments/rounds/r21.json --parents` 会生成它们（`runs/r21-P27-<tag>`）；其 longdoc-v1 读取是 `runs/longdoc-v1-kev-27b`（未固定的 Hub id，在其行中提供原始 logits）。

**Rule**（针对 Kev-27B，配对记录聚类的 bootstrap，`kev.rounds.paired`：2,000 次重采样、seed 0、micro；每个候选在其池温度下，Kev-27B 在 1.38）：
1. 主指标：breadth-v1 dev 准确率下界 > 0；tasksource-heldout-v1 dev 准确率下界 > 0；Kev panel（transfer-v4 dev、hard-v1、devtools-v1、documents-v1 dev）准确率下界 ≥ −1 pp；
2. 守门：短状态（transfer-v4 dev + transfer-r3 test）准确率下界 ≥ −2 pp、Brier 上界 ≤ +0.01、置信错误上界 ≤ +1 pp；WANLI-v2 下界 ≥ −2 pp；**scienthoon 下界 ≥ −4 pp；合并外部集（SemIf、scienthoon、WANLI-v2、TypeSafe）下界 ≥ −2.5 pp**；longdoc-v1 CUAD 部分：所有长度上准确率下界 ≥ −2 pp，且在 16k+ 状态（`acc_16k_plus`）上候选 − 父级 ≥ −2 pp；transfer-v9 上 unknowable 占比 ≤ 0.05；
3. 校准（池温度）：breadth ECE ≤ Kev-27B 的 + 0.01；Kev-panel ECE ≤ Kev-27B 的 + 0.01；tasksource-heldout ECE ≤ Kev-27B 的 + 0.01；longdoc-v1 CUAD ECE 在 16k+ 状态（`ece_16k_plus`、`by_length`）≤ Kev-27B 的 + 0.01；
4. 候选：通过的分支中 breadth + tasksource-heldout + Kev-panel 准确率增益（三个配对 delta 之和）最大的那一个。读取结果说明八个中有几个通过。

scienthoon 与合并外部集门槛被重置基线，这是一次预注册改动，随本提交、在任何 round-21 读取之前，基于 round 20 的证据（`runs/r20-scienthoon/analysis.md`、`drift.json`）：Kev-27B 是从基础模型在 Kev 数据上训练的六个 LoRA 检查点中最好的（scienthoon 0.740-0.796、均值 0.765、sd 2.1 pp），且其五个兄弟无一能通过针对它的旧门槛，包括其自身配方的第二个种子（B1 v2 seed 1：scienthoon −2.7 [−4.2,−1.4]、合并外部集 −1.5 [−2.6, −0.5]）。旧的 −2 / −1.5 pp 门槛衡量的是参考的一个种子抽样，而非一次回退。相对新的 −4 / −2.5 pp 门槛（Jared 的决断，记录于此），五个兄弟中有一个同时通过两者（B1 试验 A，族的中央检查点：−3.9 / −1.9），B1 v2 seed 1 以 0.2 / 0.1 pp 错过两者，两轮 seed 1 以 0.01 pp 错过 scienthoon，而两个最差抽样（−7.7 / −3.7、−7.7 / −3.8）仍失败；round 19 的三个最终项仍会失败于 scienthoon（下界 −4.5、−5.3、−6.0 pp；`drift.json` 的 `lora_siblings_under_the_guards`，"Round 19 result"）。与规则一起报告、不设门：每个候选在 `angry` 题上的假阳性（被称为愤怒的平和文本工单，scienthoon-v1，用 `scripts/scienthoon_drift.py` 的文本分类规则计数（2026-09-27 移除）；Kev-27B 9、Jev 8、round 19/20 分支 28-54），以及 breadth 指数（`scripts/breadth_report.py`）。

`16k_plus` 是 `kev.metrics.calibration_by_length` 中至少 16,384 token（Kev-27B tokenizer）状态的尾部：longdoc-v1 的名义 32k 与 64k 桶；其名义 16k 桶持有 13.1k-15.2k-token 的状态，算作 8k-16k。引擎给一个按长度桶一个值但无配对区间，因此注册的长期准确率守门是上面的配对：整个 CUAD 部分（全部五个桶）上的配对下界，以及 16k+ 处的点差。longdoc-v1 的生成半（迄今每个系统读取都达上限）、ood-v2、agents-ood-v1 与 guardrails-ood-v1 仅报告准确率与 ECE，不设门。

**Confirmation**（仅候选，每项读取一次，在规则之后；`docs/autoresearch.md` 第 4 节）：
- `tests`：breadth-v1 test 准确率相对 Kev-27B 下界 > 0；tasksource-heldout-v1 test 准确率下界 > 0；合并 hard-v1 + devtools-v1 + documents-v1 test 准确率下界 ≥ −1 pp；documents-v2 与 longdoc-v1 test（CUAD 与生成的，按长度）报告。spec 之外，各一次并报告：Jev 与 AutoJev 在同一 breadth-v1 test 项上（`kev.jev`、AutoJev 自身服务器、`scripts/breadth_report.py`），以及 Jev 在 longdoc-v1 test 上（`kev.jev --count-refusals`；它拒绝 64k 桶）。
- `locked`：锁定 transfer-v4 准确率 ≥ 0.886（Kev-27B 0.896 − 1 pp）且提供 Brier ≤ 0.165，在池温度下（`runs/locked/kev-27b-r21-ungated`，如同 round 20 的无试验读取检查点）。
- 在任何发布之前：main 路径上在 8k、32k 与 64k 状态的 bf16 提供检查（`modal_app.py::serving --flags=--isolation` 用于短状态，以及用 `scripts/longdoc_report.py --parity` 对 longdoc-v1 开发相对 fp32 读取的 bf16 融合读取，按桶）：max |Δp| ≤ 0.03 且 280 题中 ≤ 1 次翻转。发布温度是通过 `scripts/calibrate_checkpoint.py` 加 `--rows` 池行所做的上述池拟合。

**Run steps**（在 PR #153 与本 PR 合并之后）：(1) 将 `evals/sft-v2-r21` 与新的评估套件获取到检出（`load_split`），然后 `KEV_GPU=H200 KEV_APP_NAME=kev-sft uv run modal deploy modal_app.py`（镜像复制 `evals/`；不要把 `evals/sft-v2/*.jsonl` 留在检出中，~3 GB 镜像并不需要）；(2) 读取已计量花费，然后 `uv run python -m kev.rounds launch experiments/rounds/r21.json` 与 `watch`；在头几分钟检查日志的 `none pairs: N of 233265 records` 行，并将每分钟优化器步数与投影（1,823 步、平均约 35-37 s/步，携带长记录的步更长）对照；(3) 当快照落地，以及对任何无 `result.json` 结束试验的最终项，`launch-reads experiments/rounds/r21.json --arms <arms>` 一次一个分支的候选（见上花费规则）；`launch-reads --parents` 用于 Kev-27B 的四个新读取；(4) 读取结果，然后按所写确认。可提交的内容：公开套件行与报告，同 round 19-20。试验的校准 / 开发行（sft-v2 记录 id）以及每个 tasksource-heldout-v1 读取的行与报告（其每来源拆解命名私有族）用 `scripts/private_rows.py` 进入私有数据集。the private dataset with `scripts/private_rows.py`。

### Round 21 result

**在启动时失败，两个分支都如此；无候选，无读取。** 两个试验（`r21-27b-lr2e6`、`r21-27b-lr1e6`，启动于 2026-09-26 ~11:05Z）在其第 62 个优化器步骤的反向传播中于 rank 1 耗尽 GPU 内存（日志最后一行是 step 60；崩溃在 75-86 s 后来临）："Tried to allocate 3.05 GiB ... 137.69 GiB in use of 139.80 GiB"，发生在状态遍的 MLP 投影的检查点重计算中（`kev/shared_prefix.py:129`，来自 `kev/train.py:567`）。相同的种子与数据顺序，因此两个分支中相同的 micro-batch。`failed.json` 被写入，且试验未被重试。未到达任何快照（第一个在 step 456），因此规则从未被读取且保持未受污染。花费：06:49Z 的 $2,522.65 → 12:41Z 的 $2,657.58，约 $135（两个试验各约 1.5 h 与 Kev-27B 的四个父级读取，它们被保留：`runs/r21-P27-{tsheld,ood,agentsood,guardood}`，agents-ood 来自重跑 `r21-P27-agentsood-b` 复制到 `runs/r21-P27-agentsood`）。

**Why it ran out of memory**（离线重放：kev.train 的 epoch-0 洗牌、`none_pairs` 与 `sft-v2-r21` 的 `microbatch_plan` 带注册参数，然后每个 micro-batch 编码为 `encode_batch` 构建它）。第 62 步在 rank 1 的第一个 micro-batch 持有 8 条记录（一个 guardrails-PII 记录、两个工具路由、两个合成长文档、一个 grounding 记录、一个 hard-v1 长策略与一个 tasksource 记录）以及其中 4 个的 none-pair 兄弟：16 个状态。`--length_sort` 在*字符*上削减运行，在编码之前已知，而这些字符曾使该运行像其槽中另外七个（每个 208k 字符填充代价）那样计费。但该 PII 记录的状态是 11,559 字符与 5,877 token（每 token 1.97 字符；在超过 200 token 的语料状态上中位数是 4.1，p1 1.9，p99 5.5），因此在 token 上它把所有 16 个状态的填充设为 5,877：16 × 5,877 = 94,032 填充状态 token 加 31 分支 × 150，一个**98,682-token 遍**，而该槽其他遍持有 33-50k。失败的分配恰好是那个状态遍的一个 MLP 中间结果：94,032 × 17,408 × 2 字节 = 3.05 GiB。三件事叠加：(1) 字符以 2.8× 的离散度代表 token；(2) 共享前缀遍把每个状态（含兄弟）填充到其最长，因此一个稠密状态被放大；(3) 均衡器削减的是*步*（切成 16 个运行的最便宜方式），而非一遍，因此一步带 8 个长记录会把其余 120 个塞进 8 个运行。整个 epoch 中字符计划持有 29,160 遍，1,442 个超过 49,152 token，209 个超过 64k，最大 111k；早先两个 72.4k（step 16、20 个短状态）与 69.2k（step 58、三个 22k 状态）的遍曾幸存。

**Why it was slow**（每步 65 s 对照注册的 35 s；从日志测得的速率：lr 1e-6 的 10 → 60 步用 3,245 s、lr 2e-6 的 10 → 50 用 2,623 s，即 **1.96 records/s**、每步 128 条记录；顺序是洗牌过的，因此开头有代表性；该速率下约 119,000 s ≈ 33 h 一轮）。两个原因：注册投影（`assemble/epoch_estimate.py`）处理 token 形状，训练器处理字符，而字符在 token 上更差的均衡使同一遍时间模型从 18.7 h 升到 22.6 h；且测得步数运行在该模型的 1.47× 上（拟合于五个 10 步区间，残差约 5%），这复现了测得速率（每 epoch 32.4 h）。下面的探测指向带长状态的填充多状态遍（用显式状态掩码取代 flash kernel 的因果路径）：两个约 19k token 的不等状态每步 38.7 s，而一个 32k 状态每步 18.7。
约 19k tokens 的 states 每步耗时 38.7 s，而单个 32k 的 state 耗时 18.7。

针对 round 22 的修复：在 trainer 中引入逐 pass 的内存上限（PR #156，`--pass_tokens_max`），并将训练集规模按实测速率设定（`evals/sft-v2-r22`）。

## Round 22（已注册）

### Round 22 - round 21 的可训练配方复现：在 sft-v2-r22 上对 Qwen3.8-27B 做 full-weight SFT，采用逐 pass 内存上限，单 arm（随本 spec 的 commit 注册，写于任何 round-22 训练或读取之前）

**原由.** Round 21 已注册并在启动即失败、未做任何读取（见上文），因此其问题仍然成立：在扩展语料（长 state、tone pairs、tasksource、out-of-domain、guardrails 与 agent 记录）上从 base 做 full-weight SFT，能否在 round 21 重新设定的 guards 下击败 Kev-27B？Round 22 以相同的 rule、pool、reads 与 parents 再次提出该问题，且仅保留 round 21 的 arm (a)（lr 2e-6）；recipe 的内存规划、训练集规模与读取超时均做了改变，改变的原因来自 round 21 的实测结果，而 arm (b) 因预算原因被舍弃（见下文「Budget」）。

**Trainer 改动：逐 pass 内存上限**（PR #156，本 round 依赖此项）。`--pass_tokens_max 40960`：该规划按精确的 token 形状切分每个 step（`kev.train.plan_shapes`：epoch 训练的全部变体，含 siblings；branches 编码时不带其 state，state 由 `state_token_counts` 只计一次），对于代价最高的 pass 超过 40,960 个 padded tokens 的 step（`pass_tokens`：states × 最长 state + branches × 最长 branch），每个 rank 再增加 one micro-batch，直到没有 pass 超限，且每个 rank 增加的数量相同。不加该 flag 时，规划与当前逐字节一致。该数值来自内存：long-state probe 的单条记录在 16k / 32k / 48k / 64k 时的峰值分别为 78 / 96 / 115 / 134 GiB（`runs/sft-probe/lc-27b-8xh200`），而新的 probe 在 8 张 H200 上复现了 round-22 规划所允许的最差 passes（`scripts/sft_probe.py --passes`、`runs/sft-probe/r22-ceiling-27b-8xh200`，单个容器，约 18 分钟，约 $12）：

| pass（来自 round-22 规划） | padded tokens | states × 最长 | branches × 最长 | 每 GPU 峰值 GiB | 每 step s |
|---|---|---|---|---|---|
| 含 ≥ 8 个 states 的最大 padded tokens | 40,944 | 18 × 1,512 | 39 × 352 | 103.2 | 18.1 |
| 最大 branches × state（一条 agents 轨迹） | 30,951 | 1 × 29,631 | 10 × 132 | 103.7 | 18.5 |
| 最多 states | 38,130 | 74 × 337 | 97 × 136 | 101.6 | 15.7 |
| 含两个长 states 的最大 padded tokens | 40,958 | 2 × 18,859 | 9 × 360 | 108.2 | 38.7 |
| round 21 失败的 pass（复现） | 98,682 | 16 × 5,877 | 31 × 150 | 在 137.4 处 out of memory | - |

规划所允许的每个 pass 峰值都不超过 140 GiB 中的 108.2（上限约 125）。对 round 21 那个 pass 的复现，与 round 21 一样逐字节失败：「Tried to allocate 3.05 GiB」，PyTorch 已分配 135.34 GiB，位于 `kev/shared_prefix.py:129`。49,152 的上限按单条记录的斜率会增加约 10 GiB，且按 pass-time 模型不会节省时间（更少但更长的 passes：在某个候选集上为 20.0 h vs 19.5 h），因此注册了较低的取值。在 sft-v2-r22 上，该上限给出每个 rank 2,945 个 micro-batches，对应 1,140 个 steps（每个 accumulation slot 1.29 而非 1），最大的 pass 为 40,954 tokens。

**数据**（私有；本仓库仅有 manifests）。`evals/sft-v2-r22`（kev-private-train @ `f8d59fbb`；由 kev-sft `assemble-v2-r22` @ `0ba98a3` 构建，`assemble/build_v2.py --derived sft-v2-r22`，它先逐字节重建了 `sft-v2`，因此验证与筛选沿用 round 21 的，针对相同的 102 个 evaluation partitions 与 76,549 条 reference items）：sft-v2 的记录保持相同顺序，沿用 round 21 的上限（states ≤ 32,768 tokens；calibration 与 development ≤ 8,192 tokens，与 sft-v2-r21 逐字节一致），然后在为本 round 设定的优先级集合中，下采样直到一个 epoch 能匹配实测速率：

| 组件 | sft-v2-r21 训练 | sft-v2-r22 训练 | 规则 |
|---|---|---|---|
| tone、injection、guardrails-pii、guardrails-grounding、agents、ood、longdoc | 7,544 / 2,699 / 4,152 / 5,655 / 4,875 / 7,312 / 7,617 | 全部保留 | - |
| sft-v1 Kev 组件（b1v2、documents-v1、hard-v1、devtools-v1） | 33,108 | 全部保留 | - |
| longify | 6,400 | 3,200 | 最小的 sha256(seed:keep:longify: + digest) |
| tasksource-v1 | 58,190（119 个 families） | 24,000（全部 119 个 families） | 按 family 分层抽样，先取下限再取最大余数（family 列表私有） |
| sft-v1 public sources | 28,362（上限 1,200） | 12,000（上限 500） | 每个 source 500 的 round 21 hash 规则 |
| sft-v1 synthetic（7 个 sources） | 67,351 | 33,678 | 每个 source 取一半，相同 hash 规则 |
| **合计** | **233,265** | **145,840** | |

训练 145,840 条记录、337,130 道题目、332.0M state tokens（共享 state 时为 355.1M row tokens）；state tokens 分布：≤256 为 67,187 · 257-512 为 16,368 · 513-1k 为 20,065 · 1k-2k 为 18,651 · 2k-4k 为 5,802 · 4k-8k 为 3,510 · 8k-16k 为 7,690 · 16k-32k 为 6,567。Calibration 13,385 条、development 6,201 条记录，与 round 21 相同（仅做 in-trial 筛选）。没有任何公开文件名提及 tasksource family。

为何这样裁剪：时间花在长记录上。按 pass-time 模型，每条记录来看，longdoc 占 round 21 一个 epoch 的 26 %，sft-v1 synthetic 占 22 %（仅其长文档就占 9.5 %），longify 占 22 %，agents 占 12 %；tasksource（2.6 %）与 public sources（1.9 %）占比很小，因此单独裁掉它们只能省下几分钟。按本 round 的建议将 longify 减半，保留了那个以长文本重复 sft-v1 训练记录的唯一组件的一半；tasksource 保留了每一个 family；public 上限再减半；而优先级最低的 sft-v1 synthetic 被减半，因为再没有其他部分能触及所剩的时间。

**Epoch 时间，来自实测速率。** pass-time 模型（每 GPU：1.55 s + 每 1k padded tokens 0.478 s + 0.00282 s × states ×（最长 state，单位 k）²，取每个 micro-batch slot 中最慢的 rank 求和）乘以能够复现 round 21 实测 steps 的 1.47 系数，再套用精确的 round-22 规划（注册参数中的 shuffle、pairs 与上限）：**66,818 s = 18.6 h**，对应 1,140 个 steps（每 step 58.6 s）。对于上限所允许的那些 passes，这是偏保守的：probe 的短多 state passes 以缩放后模型的 0.6× 运行，单长 state 以未缩放模型运行，只有双长 state 的 passes 更慢（1.16×）；若以 probe 的实测时间为基准，相同规划只需 **14.8 h**。按每个 arm、18.6 h 计：训练 × 1.03（按小时设恢复点）= 19.1 h；三次启动（加载、gate 与上限的 token 计数）约 1.25 h；两次超时各退回上一个恢复点损失约 0.5 h（最坏各 1 h）：训练在 **预期 21.4 h / 最坏 22.4 h** 完成；in-trial 评分（calibration + development + transfer-v4，20,350 条记录，每条 0.292 s）1.65 h：在 3 × 8 h 中 **预期 23.0 h / 最坏 24.0 h**。最终 checkpoint 在评分前提交，且每个 candidate 的 rule reads 都是它自己的 reads，因此第三次尝试若在评分时超时，对本 round 没有任何损失。快照设在 1,140 steps 的 0.25 / 0.5 / 0.75 处：285 / 570 / 855。

**Arms**（spec `experiments/rounds/r22.json`，plans `experiments/round22/`）：沿用 round 21 的，从 `Qwen/Qwen3.8-27B` @ `1d4bf0f2` 全新开始，每次 trial 用 8×H200，对 `evals/sft-v2-r22` 训练一个 epoch，batch 8 × accum 2 × 8 ranks = 每 step 128 条记录（`--length_sort 1`、`--pass_tokens_max 40960`），bf16 autocast，OneCycle（10 % warm-up），head lr 1e-4，`--max_state 32768`，`p_none_pair 0.25` 配合 `none_pair_max_state 8192`，seed 0，**单 arm**：
- `27b-lr2e6`：lr 2e-6（round 19 的 arm (a) 与 round 21 的 arm (a)；在 round 19 中 lr 2e-6 是两种 SFT 学习率中较好的一个：arm (b) 5e-6 也未能通过 breadth primary）。

Round 21 的 arm (b) `27b-lr1e6`（lr 1e-6）未注册（Jared 关于预算的决定，见下文）。它的意义——从 base 出发更小的步长——部分由快照覆盖：s25 / s50 / s75 是 lr 2e-6 的运行在经历了 epoch 的四分之一、一半和四分之三之后的结果，是同一运行、训练更少的若干点（并非完整 schedule 下更小的学习率，本 round 不测试后者）。

Candidates：该 arm 在 step 285 / 570 / 855 的快照（`27b-lr2e6-s25/s50/s75`，`/runs/r22-27b-lr2e6/00-trial-0/snapshots/step-000NNNN/checkpoint`）及其最终 checkpoint，**共 4 个**，每个都用自己的 `transfer4` read，完全按 round 21 的注册方式。

**温度、reads、parents、rule 与 confirmation：沿用 round 21，不变**（见上文「Round 21（已注册）」；本 spec 与 `r21.json` 仅差 round 编号、一个 study 及其四个 arms（而非两个 study 与八 arms）、arm 路径、confirmation read 路径与 `read_timeout`）。温度 pool（transfer-r3 calibration 的八个 held-out sources + transfer-v9 MMLU-Pro，减去 transfer 行）、每个 candidate 的 reads、primaries（breadth-v1、tasksource-heldout-v1 开发准确率下界 > 0；Kev panel ≥ −1 pp）、guards（short state、WANLI-v2、scienthoon ≥ −4 pp、pooled externals ≥ −2.5 pp、longdoc CUAD 所有长度与 16k+、unknowable ≤ 0.05）、四个 calibration 标准、rank 以及 tests / locked 阶段均照此处所写。Kev-27B 的 reads 原样复用：其已提交的 reads 加上 round 21 的四个 parent reads，即 `runs/r21-P27-tsheld`、`runs/r21-P27-ood`、`runs/r21-P27-agentsood`（重跑的 `r21-P27-agentsood-b`，373 / 373 条记录，已复制到此处）与 `runs/r21-P27-guardood`，这些均在 round-21 任何 candidate 出现之前就已生成。

**Read 超时.** 对 agents-ood-v1 的一次 27B read 耗时 68 分钟（默认超时 30），guardrails-ood-v1 耗时 26 分钟，longdoc-v1 耗时 2 h 46 min（其超时为 3 h），因此一次仅作报告的 read 可能超时，导致某个 candidate 不完整。该 spec 注册了 `read_timeout: {"27b": 14400}`（每个 27B read 均为 4 h）。它将一个 candidate 的 17 次 reads 的准入上限提高到 17 × $25.06 = $426（H200，每个 4 h）；预期成本不变（约每个 candidate $30）。

**Budget：单 arm**（Jared 在注册时的决定）。两个 arms 仅在纸面上符合 $5,000 的计量上限：两个 study 上限加上约 $250 的 reads 合计为 $4,894.51，这连 docs/autoresearch.md 第 2 节要求每个 plan 留出的约 10 % 储备（计费读数有滞后且会被修订）都没剩下；且有了 4 h 的 read 超时，一个 candidate 的 read batch 准入上限为 $426.03，因此读取全部 8 个 candidates 将受制于计量支出，并且如果 study 用尽各自上限，还将受制于提高后的上限。采用一个 study 后，每个 candidate 的 reads 都能在规则下被准入，一次一个 batch，且储备保持完整：

| 项目（计量读数 $2,668.52，时间 2026-09-26T13:42Z，滞后；包含大部分 probe） | 准入上限 | 预期 |
|---|---|---|
| 截至目前已计量支出 | $2,668.52 | $2,668.52 |
| study `r22-27b-lr2e6`（H200:8，单价 $41.17/h × 8 h × 3 次尝试） | $987.99 | 约 $947（按缩放模型 23.0 h；若以 probe 为基准约 $750、18.2 h） |
| 4 个 candidates 的 reads（17 次 reads × 4 h × $6.27/h = 每 candidate $426.03） | 合计 $1,704.13，一次只启动一个 candidate：任意时刻 $426.03 | 约 $120（约每 candidate $30） |
| **rule 阶段的预测** | 任意时刻 **$4,082.54**（计量 + study + 一个 read batch） | **约 $3,736** |
| $5,000 中剩余储备 | **$917.46（18 %）** | **约 $1,264（25 %）** |
| confirmation，仅 candidate（tests 阶段 14 次 reads × $25.06、locked read 4 h、serving 检查） | $350.85 + 约 $25 + 约 $6 | 约 $60 |

rule 阶段这一数值把 study 的上限全额计入，即便其支出已计入计量，因此偏保守；study 结束后，两个 candidates 的 read batches 也可以同时容纳（$2,668.52 + 约 $947 + 2 × $426.03 ≈ $4,468）。Confirmation 在 rule 的 read-out 之后运行，此时 study 与 reads 均已计量：约 $3,736 + 约 $382 的上限仍留在储备之内。

**运行步骤**（在 PR #156 与本 PR 合并之后）：(1) 将 `evals/sft-v2-r22` 拉入 checkout（`load_split`；不是 `evals/sft-v2/*.jsonl`），将 round 21 的四个 parent reads 复制到 `runs/`，然后执行 `KEV_GPU=H200 KEV_APP_NAME=kev-sft uv run modal deploy modal_app.py`；(2) 读取计量成本，然后执行 `uv run python -m kev.rounds launch experiments/rounds/r22.json` 与 `watch`；头几分钟内检查日志中是否出现 `none pairs: N of 145840 records` 与 `plan: 2945 micro-batches per rank for 1140 steps (--accum 2); the plan's largest pass ... of --pass_tokens_max 40960`，并按每 step 58.6 s（预测值；以 probe 为基准为 45-47 s）核对每分钟 step 数；(3) 快照一落地，就执行 `launch-reads experiments/rounds/r22.json --arms <arm>`，一次一个 candidate（见预算表），每次之前都读取计量成本；(4) read-out，然后按所写进行 confirmation。可提交内容：同 round 21。

### Round 22 结果

**无 candidate.** 四个 candidates 全部被完整读取（每个均为 17 / 17 次 reads），且没有一个通过注册的 rule，因此没有做 confirmation read。Read-out：`runs/r22-readout/round22.json`（`python -m kev.rounds readout experiments/rounds/r22.json`；在可获取私有行时由 `tests/test_rounds.py::test_readout_reproduces_round_22` 精确复现）。每个 candidate 都在基于其自身 648 道 pool 题目拟合的温度下服务（transfer-r3 calibration、八个 sources、448 道，加上 transfer-v9 MMLU-Pro、200 道；没有作为 transfer-v4 重复项被排除），Kev-27B 使用其发布的 1.38。最终模型的 pool fit 1.382，与 Kev-27B 处于该 fit 的 121 点对数网格上的同一点（其 fit 报告注明了它自己的 r3cal + v9 reads）。Deltas 为相对 Kev-27B 的成对、按记录聚类的 bootstrap（2,000 次重采样，seed 0，micro）：准确率与 confident errors 以 pp 计，Brier 为绝对值，ECE 按服务时相对其 bar。

| 标准（panel，n） | s25（step 285） | s50（step 570） | s75（step 855） | final（step 1,140） |
|---|---|---|---|---|
| T（648 的 pool） | 1.176 | 1.516 | 1.320 | 1.382 |
| 1 breadth-v1 准确率，下界 > 0（3,075） | +0.9 [−0.1, +1.8] **fail** | +0.9 [−0.2, +2.0] **fail** | +1.2 [+0.2, +2.2] | +1.3 [+0.3, +2.3] |
| 1 tasksource-heldout 准确率，下界 > 0（2,788） | +3.0 [+1.5, +4.3] | +3.1 [+1.6, +4.6] | +3.3 [+1.9, +4.7] | +3.8 [+2.3, +5.3] |
| 1 Kev panel 准确率，下界 ≥ −1（3,731） | +6.0 [+4.7, +7.2] | +7.2 [+5.9, +8.4] | +7.0 [+5.8, +8.4] | +7.8 [+6.6, +9.1] |
| 2 short 准确率，下界 ≥ −2（1,806） | −0.7 [−1.8, +0.4] | −0.7 [−1.9, +0.6] | −1.7 [−2.9, −0.6] **fail** | −1.2 [−2.3, −0.2] **fail** |
| 2 short Brier，上界 ≤ +0.01 | +0.009 [−0.002, +0.019] **fail** | +0.001 [−0.010, +0.011] **fail** | +0.009 [+0.000, +0.019] **fail** | +0.001 [−0.007, +0.010] |
| 2 short confident errors，上界 ≤ +1 | −0.8 [−1.5, −0.1] | −1.1 [−1.8, −0.5] | −0.8 [−1.5, −0.2] | −1.2 [−1.9, −0.5] |
| 2 WANLI-v2，下界 ≥ −2（1,002） | +0.6 [−1.5, +2.7] | −0.5 [−2.5, +1.4] **fail** | +0.8 [−1.2, +2.7] | +0.5 [−1.5, +2.4] |
| 2 scienthoon，下界 ≥ −4（873） | −2.3 [−4.5, −0.2] **fail** | −6.2 [−8.7, −3.8] **fail** | −6.1 [−8.6, −3.7] **fail** | −5.5 [−7.8, −3.2] **fail** |
| 2 pooled externals，下界 ≥ −2.5（2,108） | −0.7 [−2.1, +0.6] | −3.1 [−4.6, −1.8] **fail** | −2.3 [−3.7, −1.0] **fail** | −2.2 [−3.6, −0.9] **fail** |
| 2 longdoc CUAD 准确率，下界 ≥ −2（2,254） | +0.5 [−0.8, +1.8] | −0.0 [−1.4, +1.3] | +0.5 [−0.5, +1.6] | +0.6 [−0.3, +1.6] |
| 2 CUAD 准确率，16k+，cand − parent ≥ −2（906） | 0.841 vs 0.837 | 0.831 vs 0.837 | 0.838 vs 0.837 | 0.839 vs 0.837 |
| 2 unknowable 占比 ≤ 0.05（transfer-v9） | 0.000 | 0.000 | 0.000 | 0.000 |
| 3 breadth ECE ≤ 0.0218（Kev-27B 0.0118） | 0.0181 | 0.0191 | 0.0172 | 0.0202 |
| 3 Kev-panel ECE ≤ 0.0316（Kev-27B 0.0216） | 0.0132 | 0.0207 | 0.0220 | 0.0188 |
| 3 tasksource-heldout ECE ≤ 0.1037（Kev-27B 0.0937） | 0.0652 | 0.0445 | 0.0518 | 0.0473 |
| 3 CUAD ECE 在 16k+ ≤ 0.0808（Kev-27B 0.0708） | 0.1102 **fail** | 0.1074 **fail** | 0.1042 **fail** | 0.1023 **fail** |

s25 的 scienthoon 下界为 −4.47（bar −4），s50 的 WANLI-v2 下界为 −2.50（bar −2）。准确率（s25 / s50 / s75 / final，括号内为 Kev-27B）：breadth 0.754 / 0.754 / 0.757 / 0.758（0.745）；tasksource-heldout 0.707 / 0.708 / 0.711 / 0.716（0.678）；Kev panel 0.836 / 0.848 / 0.847 / 0.854（0.776）；short 0.861 / 0.861 / 0.850 / 0.855（0.868）；scienthoon 0.773 / 0.734 / 0.735 / 0.741（0.796）；pooled externals 0.779 / 0.755 / 0.763 / 0.764（0.787）。

**规律.** Primaries 通过并随训练增长：到 final 时，breadth +1.30 [+0.33, +2.32]，tasksource-heldout +3.80 [+2.34, +5.29]（ECE 0.047 vs Kev-27B 的 0.094），Kev panel +7.8 [+6.6, +9.1]。仅作报告的 out-of-domain suites 在每个点都好得多（final vs Kev-27B，准确率 / ECE）：ood-v2 0.959 / 0.022 vs 0.944 / 0.044（4,988 道题），agents-ood-v1 0.988 / 0.031 vs 0.967 / 0.137（2,084 道），guardrails-ood-v1 0.983 / 0.010 vs 0.944 / 0.079（4,949 道）；longdoc-v1 的 generated 一半对两者均为 1.000。失败之处正是 round 19 的 SFT 失败之处，并且它在 epoch 的第一个四分之一之后愈发严重：scienthoon（s25 时 −2.3，final 时 −5.5 [−7.8, −3.2]）以及 pooled externals（其携带 scienthoon，从 −0.7 到 −2.2 [−3.6, −0.9]）；s75 与 final 时的 short-state 准确率（final 时下界 −2.27）；以及 CUAD calibration。CUAD 准确率在每个长度上都保持住，但其 ECE 在**每个**长度桶中都约为 0.10，而 Kev-27B 为 0.06-0.07（final：8k 以下 0.094 vs 0.059，8k-16k 0.101 vs 0.063，16k-32k 0.103 vs 0.070，32k-64k 0.106 vs 0.072）：这是 pool 温度下的合同领域问题，而非 state 长度问题。其余三个 calibration 标准在每个点都通过。

**Scienthoon**（仅作报告；将四个 candidates 加入的 `scripts/scienthoon_drift.py`，`runs/r22-scienthoon/drift.json`；该脚本随 suite 于 2026-09-27 被删除，现位于 git 历史的 `9c41005`）。
Tone pairs 消除了 round 20 追踪到的那个错误：被误判为 angry 的 calm 工单在每个点都是 **0**，而 Kev-27B 为 9，round-19/20 的 arms 为 28-54。错误反而变了符号：被误判为 calm 的 angry 工单为 13 / 35 / 28 / 28（Kev-27B 为 2），所以 `angry` 在 final 时为 0.852，而 Kev-27B 为 0.911。而 `priority`（其标签遵循一条文本中不存在的规则）从 0.529 下降到 0.464 / 0.423 / 0.402 / 0.419（final −11.0 pp [−16.5, −6.2]）。去掉 `angry` 这一题后，final 仍为 −5.3 [−7.9, −2.9]；`queue` 持平（0.952 vs 0.948）。

**Breadth 指数**（仅作报告；`scripts/breadth_report.py`，`runs/r22-breadth-report/report.md`，每个 candidate 用其 pool T，Kev-27B 用 1.38）：final 为 52.3 [49.5, 55.2]，相对 Kev-27B 的 50.2 为 +2.1 [−0.6, +4.7]；s25 为 51.7，s50 为 52.1，s75 为 52.0；AutoJev 为 51.7，Jev 为 53.3。增益再次来自 Retrieval & Classification（70.7 vs 62.9；CLINC150 0.953 vs 0.873，SGD 0.740 vs 0.647）。

**偏差.**
- (i) Modal 只给了该 trial 其 3 次尝试中的 2 次。尝试 1 在 22:50:13Z、约 step 560 处超时（上一个恢复点 510）；尝试 2 从 510 恢复，写入快照 570，并在 06:56:25Z、约 step 1,040 处超时（上一个恢复点 998）；那个 `FunctionTimeoutError` 是终态，没有再调度第三个容器。根本原因是（由 PR #163 中的 `scripts/modal_retry_probe.py` 在 CPU 上复现）：一个超时的尝试若在 30 s 内不回应 Modal 的取消信号，就会被杀掉，而这个杀掉动作自己消耗一次重试，且它触发的重试甚至可能紧挨着一个正在运行的尝试启动，因此 `Retries(2)` 实际只给了 2 次尝试。PR #163（开放中）关闭了 Modal 对 trials 的重试，并让 watcher 从超时 trial 的恢复点继续，一次尝试一次调用，计入同一上限。
- (ii) watcher 在 07:10Z 将 trial 标记为失败，并写了一份不含 final 的初步 read-out。Final 由一次手动续跑完成，即 study 上限已计入的第三次尝试：`modal_app.py::resume`（调用 fc-01M3GW90WZZ1Q4S60DFYCF4SGK，07:29Z），从恢复点 998 开始，逐字节精确（step 1,010-1,040 的 loss 与尝试 2 相等）。最终 checkpoint 于 09:53:27Z 提交。In-trial 评分（仅筛选）于 12:12Z 完成：objective −0.410，`sft-v2-r22` development 准确率 0.909，in-trial transfer 0.849，in-trial T 0.933；fp32 `isolation_and_packing` gate 在 0.00213 处失败，与每个 bf16 27B trial 一样。
- (iii) trainer 的规划为每 rank 2,950 个 micro-batches 对应 1,140 个 steps，最大 pass 为 40,947 tokens（注册时写的是 2,945 / 40,954；上限相同，仅作记录，非停止条件）；none pairs 出现在 145,840 条记录中的 22,921 条；每 step 约 50 s（预测 58.6，以 probe 为基准 45-47）；每 GPU 峰值 98.2 GiB。step 285 / 570 / 855 的快照按注册方式提交。
- (iv) reads 的本地客户端多次丢失连接或 DNS（s25：agents-ood 与 longdoc；s50：agents-ood；s75 与 final：各 12 个作业）。每个远程调用都已完成，其输出是手工从 `/bench` 拉取的：它们就是所注册命令的输出（每 candidate 17 / 17；TypeSafe 回答了 102 道中的 89 道，与 parent 相同）。
- 时间线：trial 于 2026-09-26 14:50Z 启动；reads 于 s25 约 21:12Z、s50 约 00:51Z、s75 约 04:49Z、final 约 10:25Z 启动；read-out 于 2026-09-27 13:26Z 完成。监控日志：`runs/r22-readout/monitor.log`、`final.log`。

**证据**（已提交）：read-out 及其私有行 manifest；每个公开 suite read 的 `report.json` + `rows.json`（`runs/r22-27b-lr2e6[-s25|-s50|-s75]-<tag>`）；ood-v2 / agents-ood-v1 / guardrails-ood-v1 的 reads 报告（聚合）以及 round 21 的这三份 parent 报告；final trial 的 `provenance.json`、`result-public.json`（即去掉逐任务表的 `result.json`）、in-trial transfer 行、in-trial calibration 温度以及三个 `snapshot.json` 记录；breadth 报告；scienthoon drift。私有部分，位于 `jaredpalmer/kev-private-train` @ `edec3920` 下的 `runs/r22/`，其 sha256 在 `runs/r22-readout/private-rows.json`（`scripts/private_rows.py restore`）：每个 tasksource-heldout-v1 的 read、行与报告，因为两者都点名了 held-out families（四个 candidates 与 Kev-27B 的 `r21-P27-tsheld`）；ood-v2 / agents-ood-v1 / guardrails-ood-v1 的行（sft-v2 私有组件的 held-out 记录，candidates 与 parent 的）；trial 的 development 行（sft-v2 记录 id）及其完整 `result.json`，其逐任务表点名了 tasksource-v1 的 families。Checkpoints（每个约 51 GB）留在 `kev-runs` 卷上。支出：Modal 在 2026-09-27T13:32Z 计量为 $3,571.88（首次读为 $3,572.09，后修订），相对注册读数 $2,668.52 **+$903.36**，为全工作区范围（study 的三次尝试、68 次 reads 与 PR #163 的 CPU probe），处于 $987.99 的 study 上限加 reads 上限之内；final 的 reads 计费可能仍有滞后。

## scienthoon 已移除（2026-09-27）

Jared 于 2026-09-27 将 `evals/external/scienthoon-v1`（scienthoon/jev-ood-calibration 的验证工单）从 Kev 中移除：其 manifest、partitions、builder（`scripts/freeze_scienthoon.py`）以及 round-20 分析脚本（`scripts/scienthoon_drift.py`）均已从 main 删除；它们仍保留在 git 历史中，例如在 `9c41005`。它作为一个 gate 是不健全的：
- 它是 291 个模板化合成支持工单 × 3 道题。
- `queue`（Choice）已饱和：每个 27B 都得 0.948-0.952。
- `priority`（Score）按构造无法被学习：它自己的 manifest 说其标签遵循一条文本中不存在的组织规则。
- `angry`（Noul）的 291 个 gold 标签中有 15 个与文本矛盾，并且它依赖于约 12 个约定有争议的固定收尾套话。正是这一题，被 round 20 的分析发现是整笔 27B 成本的背后原因（`runs/r20-scienthoon/analysis.md`）。

哪些改变、哪些不变：
- **过往结论按注册保持有效.** Rounds 5-22 注册了 scienthoon 的 reads、guards 以及与之配套的 pooled externals；它们的结局，包括本文件与 model cards 中每一处「failed scienthoon」，均不再重审。Round 22 的 reads（含 scienthoon）是在移除之前做出的，因此其 read-out 按所写应用其 rule。
- **记录仍可再生.** `runs/` 下已提交的行保留（Jev 的 `runs/jev-scienthoon-v1`、各 round 的 reads、`runs/r20-scienthoon/`）。`kev.suite.REMOVED_SUITES` 记录了该 suite 及原因，且 `kev.rounds validate` 会将 ≤ 22 的 round 中对该 suite 的 read 列为 archived 而非 failed。Read-outs 与结论由行计算得出，而非由 suite 计算，因此 `tests/test_rounds.py` 能不变地复现它们。Model-card 的数字仍通过 `scripts/verify_claims.py` 追溯到已提交的报告。README 的外部表格删掉了该行；其唯一一条仅出现在 README 的声明（0.911）也随之移除。
- **从 round 23 起：** 不再有 scienthoon read、panel 或 guard。Pooled external guard 改为 **SemIf + WANLI-v2 + TypeSafe**，且 `validate` / `launch` 会拒绝仍点名该 suite 的 round。「Next」中关于 scienthoon 补救的项均已关闭。（2026-09-28 被取代：round 24 的审计后 rule 不再 gate 任何 pooled externals，且 round 23 已在其上重新注册，因此这三个 suites 是被报告而非被 gate；此为常设规则。）

## WANLI 与 TypeSafe 已移除（2026-09-30）

Jared 于 2026-09-30 将 `evals/external/wanli-v2`、`evals/external/wanli-v1` 与 `evals/external/typesafe-v1` 从 Kev 中移除，连同它们的 builder（`scripts/freeze_semif_external.py`）与 `scripts/compare_typesafe.py`；它们仍保留在 git 历史中。2026-09-27 的审计已将它们设为仅作报告（round 24 的 rule）。移除它们的检查依据：
- *WANLI（v2：1,002 对，v1：SemIf 的 256）.* WANLI 公开发布了每个测试对的两份众包标注（位于固定修订 `61c95318` 的 `anonymized_annotations.jsonl`）。两位标注者在 wanli-v2 的 1,002 对中，有 271 对（27 %）意见不一；在 wanli-v1 的 256 对中，有 63 对（25 %）意见不一；且发布的 gold 始终是两种标签之一：在那些对上，gold 在人与人之间就像抛硬币。每个 Kev 在那里得分都低得多（development 行，按服务时）：

  | | 一致（731） | 有争议（271） |
  |---|---|---|
  | Kev-27B v2（`runs/r23-27b-k-w85-wanli2`） | 0.808 | 0.616 |
  | Kev-9B | 0.802 | 0.572 |
  | Kev-4B | 0.767 | 0.491 |
  | Kev-0.8B | 0.644 | 0.487 |

  Round 18 的 9B arm (a) 未能通过 WANLI-v2 guard，相对发布的 Kev-9B，其在一致对上低 0.6 pp，在有争议对上低 3.0 pp。审计在 23 个 checkpoints 上测得 split-half r 为 0.04，全部落在 0.735-0.763 之间，半宽（1.95-2.10 pp）与 2 pp 的 bar 一样宽，且约 11 % 为无效标签。
- *TypeSafe（`typesafe-v1`，20 个 case 上的 102 道题，89 道在其被评分所用的 8k 上下文下作答）.* gold 是 TypeSafe 参考分布的 argmax，evals.typesafe.ai 将其描述为两个封闭前沿模型回答的平均值（GPT-6 Astra 与 Claude Fable 5.1，high thinking）。它衡量的是与那些模型的一致性，而非正确性；且 102 个 references 中有 13 个将其回答置于 0.75 以下（两者分裂）。在 20 个 Kev-27B checkpoints 上，split-half 相关性为 −0.01（审计：−0.27），89 道中有 70 道对它们全部正确，其余无法对 checkpoints 排序。
- *SemIf（`semif-v1`，144 道人工撰写的决策题）保留，仅作报告.* 其标签站得住：在某些 Kev-27B checkpoint 遗漏的 14 道题中，遗漏是真正的难题（两个候选都不授权该动作，因此答案为 insufficient），而非标签错误。但它已饱和（20 个 Kev-27B checkpoints 上为 0.931-0.979，144 道中有 130 道全部正确，split-half r 0.19），因此它是一项健全性检查，而非排序依据。

哪些改变、哪些不变：过往结论按注册保持有效（rounds 5-26 读取过这些 suites；它们的 read-outs 与 confirmations 由已提交的行复现，`kev.suite.REMOVED_SUITES` 将 reads 归档）。从 round 27 起，任何 round 都不得读取它们。README 的外部表格仅保留 SemIf；model cards 保留其 WANLI 与 TypeSafe 数值作为记录。Round 18 的 9B arm (a) 仅未能通过 WANLI-v2、scienthoon 与 pooled externals，而三者现均已移除或不再 gate；它是否算一个 Kev-9B candidate，是一个留给基于 round 24 的 rule 重新注册 round 来回答的问题，而非重读 round 18。

## Round 24（已注册）

### Round 24 - 回顾性选择：将审计的结论作为单一 rule，应用于每一个 full-weight 27B checkpoint（随本 spec 的 commit 注册，写于其下任何计算之前）

**这是什么，直说.** 这是在已经存在、且已经在 development 数据上被读取过的 checkpoints 之间做 **事后选择**：round 19 的两个 finals、round 20 的六个 WiSE-FT blends，以及 round 22 的三个快照与 final（共 12 个 checkpoints；无训练、无新的 development read）。它们各自 round 的结论按注册保持有效：round 19、20、22 各自都未选出 candidate，此处不修订任何结论。下述 rule 是 2026-09-27 评估 suite 审计的结论（报告 `audit/REPORT.md`，位于 `9c41005` 的审计工作树；只读，花去 $6.68 的盲审第二意见支出）的统一应用：round 所读取的每个 suite 都按相同的九条标准（可学习性、标签噪声、种子噪声、可靠性、区分度、功效、饱和、污染、冗余）评分，无论 SFT checkpoints 通过还是未通过，且下述每项修复都是该审计对其 suite 的结论。在任一 checkpoint 在其下的结果被计算出之前，它已冻结于本次 commit。它并非盲的：审计读取了这些 checkpoints 的 development 行（其主表，以及为 round 22 做的事后反事实，例如 round 22 final：去掉 `emotion` 的 short state 为 −0.88 [−1.95, +0.19]，breadth 可学习 +1.54 [+0.57, +2.47]，去掉七个 families 的 tasksource-heldout +4.06 [+2.31, +5.77]），因此任何读到此处的人都能大致知道 round 22 的 candidates 落在何处。在 12 个模型中挑选 development panels 上的最优者，从构造上就是乐观的。对抗这种乐观的屏障是 confirmation：breadth-v1、tasksource-heldout-v1、hard-v1、devtools-v1、documents-v1、documents-v2 与 longdoc-v1 的未触碰测试 partitions，以及 locked transfer-v4 read，每个只读一次，且只针对具名 candidate，在相同排除项下。

**为何 rule 改变**（审计的数字；「P0」= 一个与 Kev-27B 同样好的 candidate 未能通过注册 bar 的概率，来自 round 22 的半宽）：
- *scienthoon-v1*：移除（另行从仓库中移除）。盲审读者在 45 个全错题中仅 1 道与 gold 一致；round 22 final 的 −5.5 pp 涉及 `priority` 上 48 道净题中的 32 道，而该标签没有任何文本能确定；Kev-27B 高出其六个 LoRA siblings 3.1 pp，且其余 5 个中有 3 个未能通过相对它的 −4 pp guard。
- *WANLI-v2*：仅作报告。在 23 个 checkpoints 上 split-half r 为 0.04（全部落在 0.735-0.763）；半宽 1.95-2.10 pp 对应 2 pp 的 bar，P0 为 48-54 %；约 11 % 为无效标签。
- *pooled externals*：移除。去掉 scienthoon 后它由 81 % 的 WANLI 组成（τ 0.75），split-half r 0.08。SemIf（饱和：最优 0.993，每个 checkpoint 有 90 % 的题正确；144 道题）与 TypeSafe（gold = 一个参考 argmax；89 道题，split-half r −0.27）被报告。
- *`emotion`*（transfer-v4 dev 与 transfer-r3 test）：从 short-state 与 Kev panels 中剔除。关键词远监督：每个 checkpoint 都有 26 % / 28 % 的题是错误的，且盲审读者在 21 道中 2 道、25 道中 1 道与 gold 一致。它保留在温度 pool 中：仅在那里去掉它，T 会移到 1.23，并使 breadth ECE 变差（0.020 → 0.028）。
- *short-state Brier*：+0.01 的 bar 对应 P0 36-55 %（半宽 0.85-1.07 pp）。审计的建议是一个半宽能分辨的边界，「例如 Brier 上界 ≤ +0.02」，且 P(fail | Δ = 0) ≤ 10 %；在 +0.02 处，用相同半宽（bar − 半宽，再除以半宽 / 1.96）约为 0.4-4.5 %。注册：上界 ≤ +0.02。Confident errors 保留 +1 pp（P0 13-22 %），照原规定。
- *breadth-v1*：`routerbench` 剔除（它问哪个模型答对了，但 state 中并无答案：44 % 全错，准确率等于先验）；`cfcolor`、`humicroedit`（对每个系统都是随机水平，含 Jev）与 `chessbench`（地板值，54 % 全错）移至报告。Split-half r 从 0.41 升到 0.57。
- *tasksource-heldout-v1*：剔除七个 families，编码为 T11 T12 T14 T15 T18 T22 T24（全错率 21-55 %，盲审读者与 gold 一致 ≤ 25 %；无效标签、2 路 → 3 路映射、丢失的 span 标注、打乱词序的 NLI、缺少判据的偏好；占 2,788 道 development 题中的 795 道）。名字是私有的（family 列表保密），因此该 panel 读取一个按路径与 sha256 注册的私有排除文件（见下文）。
- *devtools-v1*：将从代码不可见的重跑中得到的标签 `flakeflagger`（3 个 development 项目），以及 commitpackft 的 `change_type`（任务 `commitpackft_type`：对 state 未展示的提交信息做动词启发式；24 % 全错，盲审读者 25 道中仅 1 道与 gold 一致）从 Kev panel 中剔除。
- *longdoc CUAD*：准确率触发线保留（P0 1-18 %）；ECE 16k+ 仅作报告（final 的 206 个 confident errors 中有 80 % 落在错误、非唯一或有争议的 gold 上；差距真实存在，但题目集需要重建）。Generated 一半（每个 checkpoint 均为 1.000）以及 ood-v2 / agents-ood-v1 / guardrails-ood-v1（标签正确但接近天花板，且是 SFT 组件自身的生成器）被报告。hard-v1（标签精确，但其训练模板在 SFT 语料中，且它贡献了 round 22 final 的 +291 个净 Kev-panel 题中的 +191 个）留在 Kev 保留 gate 内，并且也单独报告、以及作为去掉它的 Kev panel 报告。
- 未采纳审计的前瞻性建议（它们需要新的 reads 或新的 suite 版本）：ECE 标准上的区间与更宽边界（其采样 sd 为 0.006-0.010，对应 0.01 的边界；会报告 ECE deltas 的成对区间）、针对 LoRA sibling family 的 gating，以及每个 suite 一次 sibling read。

**Candidates**（spec `experiments/rounds/r24.json`；全部可选；每个都是 `kev-runs` 卷上的一个 checkpoint arm，带有标明其训练 suite 的 `trained_on`，因此 pool 检查能覆盖它；parent Kev-27B 为 `r6-27b-v2/01-trial-1`，使用 rounds 21-22 的 reads）：

| arm | checkpoint | trained on | 其 development reads |
|---|---|---|---|
| `27b-r19a`、`27b-r19b` | round 19 (a) lr 2e-6 / (b) lr 5e-6 finals，`/runs/r19-27b-{lr2e6,lr5e6}/00-trial-0/checkpoint` | `evals/sft-v1` | `runs/r19-27b-*-<tag>`；transfer-v4 dev = trials 的 in-trial transfer read；`r3cal` 来自 round 20；tasksource-heldout、longdoc 与三个 OOD suites 来自 2026-09-27 的 sweep（`runs/sweep-r19-{a,b}-<tag>`） |
| `27b-r20{a,b}-w{85,70,50}` | round 20 blends，`/runs/r20-wise/27b-{a,b}-w{85,70,50}/checkpoint` | `evals/sft-v1` | `runs/r20-27b-*-<tag>`（含 `transfer4`、`r3cal`）；sweep 的 `runs/sweep-r20-*-<tag>` |
| `27b-r22-s25`、`-s50`、`-s75`、`-final` | round 22 在 step 285 / 570 / 855 的快照与 final，`/runs/r22-27b-lr2e6/00-trial-0/...` | `evals/sft-v2-r22` | round 22 各自的 17 次 reads（`runs/r22-27b-lr2e6[-sNN]-<tag>`） |

Sweep 补齐了 round-19/20 checkpoints 所缺的 development reads（tasksource-heldout、longdoc、ood-v2、agents-ood-v1、guardrails-ood-v1；通过 `modal_app.py::benchmarks` 写入 `/runs/<checkpoint>`，原始 logits），且早于本次注册、没有 rule。缺失任何 gating read 的 candidate 不完整，永不被选中；仅作报告的 panels 标记为 `optional`，永不会使 candidate 不完整。

**温度.** Round 20-23 的 pool，不变：transfer-r3 calibration 的八个 held-out sources + transfer-v9 MMLU-Pro（648 道题），减去 transfer-v4 dev 记录；Kev-27B 使用其发布的 1.38。新增、仅作报告（审计：final 的 T 1.382 有 90 % CI [1.20, 1.52]，且 breadth ECE 在其上从 0.020 变到 0.031）：每个 candidate 的 pooled T 的 90 % bootstrap 区间，2,000 次重采样（在每个 source 内对 pool 的 (source, record) 簇重采样），seed 0，相同的 121 点网格与目标（`temperature.ci`）。

**Rule**（相对 Kev-27B；成对、按记录聚类的 bootstrap，2,000 次重采样，seed 0，micro；`drop_ids` 同前）：
1. primaries：去掉 `routerbench`、`cfcolor`、`humicroedit`、`chessbench` 后，breadth-v1 dev 准确率下界 > 0；去掉七个 families 后，tasksource-heldout-v1 dev 准确率下界 > 0；Kev panel（去掉 `emotion` 的 transfer-v4 dev、hard-v1、去掉 `flakeflagger` 与 `commitpackft_type` 的 devtools-v1、documents-v1）准确率下界 ≥ −1 pp；
2. guards：short state（transfer-v4 dev + transfer-r3 test，两者均去掉 `emotion`）准确率下界 ≥ −2 pp，Brier 上界 ≤ +0.02，confident errors 上界 ≤ +1 pp；transfer-v9 上 unknowable 占比 ≤ 0.05；longdoc CUAD 准确率下界 ≥ −2 pp，且 CUAD 16k+ 准确率 candidate − Kev-27B ≥ −2 pp（同 round 22）；
3. calibration：breadth、Kev-panel 与 tasksource-heldout 的 ECE ≤ Kev-27B 的 + 0.01（相同排除项）；
4. candidate：通过 checkpoints 中 breadth + tasksource-heldout + Kev-panel 准确率增益最大的那个。

仅作报告（不 gate）：SemIf、WANLI-v2、TypeSafe；按长度的 CUAD ECE（含 16k+）；longdoc generated；ood-v2、agents-ood-v1、guardrails-ood-v1；单独的 hard-v1；去掉 hard-v1 的 Kev panel；覆盖全部 14 个 sources 的 breadth（指数的构成）以及覆盖三个被移走 sources 的 breadth；覆盖全部 24 个 families 的 tasksource-heldout；机会修正后的 breadth 指数（`scripts/breadth_report.py`）。无 pooled-externals guard；不读取 scienthoon。

**私有排除列表.** `runs/r24-private/tsheld-exclude.json`（gitignored）：七个 family sources 加上一个随机 salt（使公开 sha256 无法与猜测的列表匹配），以 `{path, sha256}`（`a72030ab…`）注册于 spec 中，并上传到 `jaredpalmer/kev-private-train` 下的 `runs/r24/`（manifest 为 `runs/r24-readout/private-exclude.json`；`scripts/private_rows.py restore`）。`kev.rounds` 会拒绝哈希不符的文件，并在缺少它时报告该 panel 缺失。

**Harness**（本 PR）：panel 过滤器 `exclude_sources`、`exclude_tasks`、`exclude_file` 以及作为列表的 `source`（`kev.rounds.panel_filter`：相同的行从两侧以及任何 `versus` 参考中移除；panel 记录 `excluded`）；
`optional` 仅作报告的 panels；`temperature.ci`。没有这些键的 specs 计算方式完全同前（`tests/test_rounds.py` 复现 rounds 5-20）。

**Confirmation**（仅具名 candidate，每个只读一次，按 `docs/autoresearch.md` 所述；若无 candidate 则为空）：
- `tests`：breadth-v1 test 准确率下界 > 0（相同四个 sources 剔除；全部 14 个均报告），且 Jev 与 AutoJev 在同一测试项上各读一次（报告；`kev.jev`、AutoJev 的 server、`scripts/breadth_report.py`）；tasksource-heldout-v1 test 下界 > 0（相同七个 families 剔除）；pooled hard-v1 + devtools-v1（去掉 `flakeflagger`、`commitpackft_type`）+ documents-v1 test 下界 ≥ −1 pp；documents-v2 与 longdoc-v1 test（按长度的 CUAD、generated）作报告。Kev-27B 一侧也只读一次（`runs/r24c-27b-parent-<tag>`；不存在这些 suites 的 27B test read）。
- `locked`：locked transfer-v4 准确率 ≥ 0.886，且服务时 Brier ≤ 0.165（`kev-27b-r24-ungated`）。
- 任何发布之前：bf16 serving 检查（`modal_app.py::serving --run <checkpoint> --gpu H200 --name serving-27b-r24 --flags=--isolation`：max |Δp| ≤ 0.03，280 题中 ≤ 1 个翻转）以及在 8k / 32k / 64k 的长 state 运行（`--flags "--state_tokens 8192,32768,65536 --reps 3"`，按长度的服务 vs benchmark 一致性，相同 bar）；发布温度 = 由 `scripts/calibrate_checkpoint.py --rows <r3cal rows>:composition_holdout,emotion,legacy_holdout,mmlu,paws,qnli,sciq,tweet_offensive --rows <v9 rows>:mmlu_pro --exclude_rows <transfer4 rows>` 写出的 pool fit。

**Budget.** rule 阶段零成本（已有 reads；sweep 的 reads 此前已生成并单独付费）。Confirmation，仅 candidate：tests 14 次 reads × $25.06（H200，4 h 上限）= $350.85 上限（预期约 $60），locked 约 $25，serving 检查约 $6，经 AI Gateway 的 Jev 在 breadth-v1 test 上约 $0.10（上限 $3）。

**运行步骤.** (1) 把 reads 放到位：来自 round-22 checkout 的 round-22 与 round-21 parent reads（公开行随 read-out 提交，私有行从 `jaredpalmer/kev-private-train` 恢复），sweep 的 reads 复制到 `runs/sweep-<checkpoint>-<tag>`；(2) `uv run python -m kev.rounds validate experiments/rounds/r24.json`；(3) `uv run python -m kev.rounds readout experiments/rounds/r24.json`；(4) 由 Jared 做 confirmation（若有 candidate）。提交内容：read-out、它评分所用的公开行，以及一份针对 tasksource-heldout 与 OOD 行的私有行 manifest。

### Round 24 结果

**Candidate：`27b-r22-final`**（round 22 的 final checkpoint，`/runs/r22-27b-lr2e6/00-trial-0/checkpoint`）。12 个 checkpoints 中有 2 个通过注册的 rule，即 round 22 final 与 round 20 的 `27b-r20a-w85`；rank（breadth + tasksource-heldout + Kev-panel 准确率增益）将 final 排第一，+13.5 pp 对 +12.3。这是在 development 数据上已被读取过的 checkpoints 之间的事后选择（见上文）；尚未做 confirmation read，结论取决于 confirmation 阶段。Read-out：`runs/r24-readout/round24.json`（`python -m kev.rounds readout experiments/rounds/r24.json`，运行于 2026-09-27T23:57Z，晚于 23:53:28Z 的注册 commit `523e6ea`；在可获取私有行时由 `tests/test_rounds.py::test_readout_reproduces_round_24` 复现）。每个 checkpoint 都在其 pooled T 下服务（648 道题，没有作为 transfer-v4 重复项被排除），Kev-27B 使用 1.38；deltas 为相对 Kev-27B 的成对、按记录聚类的 bootstrap（2,000 次重采样，seed 0，micro），准确率与 confident errors 以 pp 计，Brier 为绝对值，ECE 按服务时相对其 bar。排除项从两侧移除了 600 道 breadth 题、795 道 tasksource-heldout 题、380 道 Kev-panel 题（`emotion` 80、`flakeflagger` 150、`commitpackft_type` 150）以及 220 道 short-state 题（`emotion` 80 + 140）。

| 标准 | r19 (a) | r19 (b) | r20 a-w85 | r20 a-w70 | r20 a-w50 | r20 b-w85 | r20 b-w70 | r20 b-w50 | r22 s25 | r22 s50 | r22 s75 | r22 final |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| T（pool，648）[90 % CI] | 1.414 [1.29, 1.55] | 1.382 [1.23, 1.52] | 1.414 [1.29, 1.55] | 1.447 [1.29, 1.59] | 1.447 [1.32, 1.59] | 1.350 [1.23, 1.48] | 1.350 [1.20, 1.48] | 1.350 [1.23, 1.45] | 1.176 [1.05, 1.29] | 1.516 [1.38, 1.66] | 1.320 [1.18, 1.41] | 1.382 [1.23, 1.48] |
| 1 breadth 准确率，下界 > 0（2475） | +1.6 [+0.6, +2.5] | +0.8 [-0.4, +1.9] **fail** | +1.6 [+0.6, +2.5] | +1.7 [+0.7, +2.7] | +1.5 [+0.6, +2.3] | +1.2 [+0.1, +2.2] | +1.6 [+0.6, +2.6] | +2.1 [+1.1, +3.1] | +1.3 [+0.4, +2.1] | +1.0 [-0.0, +2.0] **fail** | +1.7 [+0.6, +2.6] | +1.5 [+0.6, +2.5] |
| 1 tasksource-heldout 准确率，下界 > 0（1993） | +1.4 [-0.3, +2.9] **fail** | -0.1 [-1.8, +1.7] **fail** | +1.7 [+0.2, +3.2] | +1.5 [-0.1, +3.1] **fail** | +1.0 [-0.5, +2.7] **fail** | +0.2 [-1.6, +1.8] **fail** | +1.4 [-0.2, +3.0] **fail** | +2.0 [+0.5, +3.6] | +2.4 [+0.8, +4.0] | +3.2 [+1.4, +4.9] | +3.7 [+2.0, +5.4] | +4.1 [+2.3, +5.8] |
| 1 Kev panel 准确率，下界 ≥ −1（3351） | +9.0 [+7.8, +10.1] | +8.2 [+7.0, +9.5] | +9.0 [+7.9, +10.2] | +8.9 [+7.8, +10.1] | +7.6 [+6.5, +8.8] | +8.5 [+7.3, +9.8] | +8.6 [+7.4, +9.8] | +8.3 [+7.1, +9.5] | +5.7 [+4.4, +7.0] | +7.3 [+6.1, +8.6] | +7.0 [+5.8, +8.3] | +7.9 [+6.7, +9.1] |
| 2 short 准确率，下界 ≥ −2（1586） | -0.9 [-2.1, +0.1] **fail** | -0.3 [-1.5, +0.9] | -0.7 [-1.8, +0.4] | -0.6 [-1.7, +0.4] | -0.7 [-1.8, +0.3] | -0.2 [-1.4, +1.0] | -0.4 [-1.5, +0.7] | -0.3 [-1.3, +0.8] | -0.8 [-2.0, +0.4] | -0.2 [-1.5, +1.1] | -1.4 [-2.7, -0.2] **fail** | -0.9 [-2.0, +0.2] |
| 2 short Brier，上界 ≤ +0.02 | +0.003 [-0.008, +0.013] | -0.002 [-0.013, +0.009] | +0.002 [-0.009, +0.012] | -0.002 [-0.013, +0.008] | -0.001 [-0.013, +0.009] | -0.003 [-0.015, +0.007] | -0.005 [-0.017, +0.004] | -0.005 [-0.017, +0.005] | +0.008 [-0.004, +0.020] **fail** | -0.002 [-0.013, +0.009] | +0.010 [-0.001, +0.021] **fail** | -0.000 [-0.009, +0.009] |
| 2 short confident errors，上界 ≤ +1 | -0.9 [-1.6, -0.3] | -0.6 [-1.3, +0.1] | -0.9 [-1.7, -0.3] | -1.1 [-1.8, -0.5] | -0.9 [-1.6, -0.3] | -0.6 [-1.4, +0.1] | -0.8 [-1.6, -0.2] | -0.8 [-1.5, -0.2] | -0.8 [-1.5, +0.0] | -1.2 [-2.0, -0.6] | -0.8 [-1.5, -0.1] | -1.1 [-1.9, -0.5] |
| 2 CUAD 准确率，下界 ≥ −2（2254） | +0.3 [-0.7, +1.3] | -0.4 [-1.8, +0.9] | +0.3 [-0.7, +1.2] | -0.1 [-1.1, +0.7] | -0.4 [-1.2, +0.5] | -0.5 [-1.7, +0.7] | -0.7 [-1.8, +0.4] | -0.8 [-2.0, +0.3] | +0.5 [-0.8, +1.8] | -0.0 [-1.4, +1.3] | +0.5 [-0.5, +1.6] | +0.6 [-0.3, +1.6] |
| 2 CUAD 16k+ 准确率，cand − parent ≥ −2 | 0.836 vs 0.837 | 0.831 vs 0.837 | 0.834 vs 0.837 | 0.831 vs 0.837 | 0.832 vs 0.837 | 0.832 vs 0.837 | 0.832 vs 0.837 | 0.830 vs 0.837 | 0.841 vs 0.837 | 0.831 vs 0.837 | 0.838 vs 0.837 | 0.839 vs 0.837 |
| 2 unknowable 占比 ≤ 0.05 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| 3 breadth ECE ≤ 0.0176（Kev-27B 0.0076） | 0.0094 | 0.0149 | 0.0077 | 0.0141 | 0.0206 **fail** | 0.0167 | 0.0139 | 0.0255 **fail** | 0.0173 | 0.0192 **fail** | 0.0087 | 0.0149 |
| 3 Kev-panel ECE ≤ 0.0327（Kev-27B 0.0227） | 0.0131 | 0.0099 | 0.0149 | 0.0169 | 0.0283 | 0.0094 | 0.0194 | 0.0210 | 0.0105 | 0.0275 | 0.0165 | 0.0155 |
| 3 tasksource-heldout ECE ≤ 0.0523（Kev-27B 0.0423） | 0.0185 | 0.0168 | 0.0207 | 0.0126 | 0.0235 | 0.0139 | 0.0203 | 0.0295 | 0.0351 | 0.0474 | 0.0470 | 0.0482 |
| rank 分数（Δ breadth + Δ tsheld + Δ Kev，pp） | +11.9 | +9.0 | +12.3 | +12.0 | +10.1 | +9.8 | +11.6 | +12.4 | +9.4 | +11.5 | +12.4 | +13.5 |
| verdict | fail | fail | **PASS** | fail | fail | fail | fail | fail | fail | fail | fail | **PASS** |

失败之处与位置：tasksource-heldout 的 primary 是 round 19/20 checkpoints 的常见失败点（8 个中 6 个：除 `27b-r20a-w85` 与 `27b-r20b-w50` 外的全部）；breadth ECE（`27b-r20a-w50`、`27b-r20b-w50`、`27b-r22-s50`）；short state（准确率：`27b-r19a`、`27b-r22-s75`；Brier 上界：`27b-r22-s25` 为 +0.0203、`27b-r22-s75` 为 +0.0208，相对 +0.02）；breadth（`27b-r19b`、`27b-r22-s50`，其下界为 −0.04 pp）。Round-22 final 之所以通过 short-state 准确率，仅因为去掉了 `emotion`（−0.9 [−2.0, +0.2]；若保留，round 22 的注册 read 为 −1.2 [−2.27, −0.22]），且其 CUAD ECE 在 16k+ 处相对 Kev-27B 的 0.071 仍为 0.102，现为报告而非 gate。

**温度不确定性**（仅作报告）。Pooled T 的 90 % bootstrap 区间在表中（±0.12-0.15）。在 interval 两端服务时，具名 candidate 的 calibration 通过性不成立：breadth ECE 在 T 1.231 时为 0.0234（bar 0.0176），tasksource-heldout ECE 在 T 1.481 时为 0.0617（bar 0.0523）；Kev-panel ECE 保持在内部（0.0096-0.0166）。`27b-r20a-w85` 在其整段 interval [1.289, 1.551] 内三个都保持在内部（breadth 0.0077-0.0171，Kev 0.0125-0.0269，tasksource-heldout 0.0207-0.0274）。Rule 在拟合点服务，因此这不改变任何结论；这正是审计所指出的一点：ECE 标准没有区间，而发布的温度就是相同的 pool fit（`scripts/calibrate_checkpoint.py`）。

**仅作报告的 panels**（相对 Kev-27B 的成对 deltas；ECE 为绝对值）：

| panel | r19 (a) | r19 (b) | r20 a-w85 | r20 a-w70 | r20 a-w50 | r20 b-w85 | r20 b-w70 | r20 b-w50 | r22 s25 | r22 s50 | r22 s75 | r22 final |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| breadth，全部 14 个 sources，准确率（3075） | +1.5 [+0.4, +2.5] | +0.6 [-0.6, +1.7] | +1.4 [+0.4, +2.5] | +1.7 [+0.7, +2.6] | +1.5 [+0.5, +2.5] | +1.1 [-0.1, +2.3] | +1.4 [+0.3, +2.5] | +1.7 [+0.7, +2.8] | +0.9 [-0.1, +1.8] | +0.9 [-0.2, +2.0] | +1.2 [+0.2, +2.2] | +1.3 [+0.3, +2.3] |
| breadth cfcolor+humicroedit+chessbench，准确率（450） | +1.3 [-2.9, +5.1] | +0.2 [-4.0, +4.4] | +0.9 [-3.1, +4.9] | +1.8 [-2.2, +5.6] | +1.6 [-2.7, +5.3] | +1.3 [-2.9, +5.6] | +0.9 [-3.3, +5.1] | +0.2 [-4.0, +4.4] | -1.1 [-4.7, +2.4] | +0.7 [-3.6, +4.7] | -1.3 [-5.3, +2.7] | -0.7 [-4.7, +3.3] |
| tasksource-heldout 全部 24 个 families，准确率（2788） | +1.0 [-0.3, +2.3] | +1.1 [-0.4, +2.6] | +1.1 [-0.1, +2.4] | +1.3 [+0.0, +2.6] | +0.9 [-0.5, +2.1] | +1.1 [-0.3, +2.5] | +2.0 [+0.7, +3.4] | +2.1 [+0.8, +3.4] | +3.0 [+1.5, +4.3] | +3.1 [+1.6, +4.6] | +3.3 [+1.9, +4.7] | +3.8 [+2.3, +5.3] |
| hard-v1 准确率（1083） | +19.9 [+17.1, +22.7] | +18.8 [+16.1, +21.8] | +19.6 [+16.9, +22.4] | +19.0 [+16.3, +21.9] | +16.4 [+13.8, +19.3] | +19.3 [+16.6, +22.3] | +19.3 [+16.7, +22.2] | +18.3 [+15.6, +21.2] | +14.0 [+11.2, +17.0] | +16.3 [+13.6, +19.2] | +17.3 [+14.3, +20.2] | +17.6 [+14.9, +20.5] |
| 去掉 hard-v1 的 Kev panel，准确率（2268） | +3.7 [+2.6, +5.0] | +3.2 [+1.9, +4.4] | +4.0 [+2.8, +5.1] | +4.1 [+3.0, +5.1] | +3.4 [+2.3, +4.5] | +3.3 [+2.1, +4.6] | +3.5 [+2.3, +4.7] | +3.5 [+2.3, +4.6] | +1.7 [+0.4, +3.0] | +3.0 [+1.7, +4.3] | +2.1 [+0.9, +3.3] | +3.2 [+2.0, +4.4] |
| SemIf 准确率（144） | -0.7 [-3.5, +2.1] | -1.4 [-4.2, +1.4] | -0.7 [-3.5, +2.1] | -2.1 [-5.6, +1.4] | -2.8 [-6.2, +0.7] | -2.1 [-5.6, +0.7] | -2.8 [-6.2, +0.7] | -4.2 [-7.6, -0.7] | +0.7 [-1.4, +2.8] | -2.1 [-5.6, +1.4] | -1.4 [-4.9, +1.4] | -1.4 [-4.9, +2.1] |
| WANLI-v2 准确率（1002） | +0.0 [-2.1, +2.0] | -0.1 [-2.3, +2.0] | +0.0 [-2.1, +1.9] | +0.6 [-1.3, +2.4] | +0.0 [-1.9, +2.0] | +0.1 [-2.1, +2.2] | +0.7 [-1.4, +2.8] | +1.1 [-1.0, +3.1] | +0.6 [-1.5, +2.7] | -0.5 [-2.5, +1.4] | +0.8 [-1.2, +2.7] | +0.5 [-1.5, +2.4] |
| TypeSafe 准确率（89） | +1.1 [-4.4, +5.4] | +0.0 [-6.2, +5.9] | +1.1 [-4.4, +5.4] | +0.0 [-5.0, +3.9] | -1.1 [-6.7, +3.5] | +0.0 [-6.2, +5.9] | -1.1 [-8.0, +5.4] | +1.1 [-5.0, +6.4] | -2.2 [-7.1, +2.2] | -4.5 [-9.3, +1.0] | -2.2 [-6.6, +2.0] | -2.2 [-6.6, +2.0] |
| ood-v2 准确率（4988） | +1.3 [+0.7, +1.8] | +1.0 [+0.5, +1.6] | +1.2 [+0.7, +1.8] | +1.2 [+0.6, +1.7] | +1.0 [+0.5, +1.5] | +1.2 [+0.6, +1.7] | +1.4 [+0.8, +1.9] | +1.1 [+0.6, +1.6] | +0.8 [+0.3, +1.4] | +1.0 [+0.5, +1.5] | +1.4 [+0.9, +2.0] | +1.5 [+1.0, +2.1] |
| agents-ood-v1 准确率（2084） | -0.1 [-0.9, +0.6] | -1.0 [-1.7, -0.3] | -0.0 [-0.8, +0.7] | -0.3 [-1.1, +0.5] | -1.1 [-2.0, -0.2] | -0.8 [-1.5, -0.0] | -0.6 [-1.3, +0.1] | -0.4 [-1.2, +0.3] | +1.7 [+0.9, +2.6] | +1.3 [+0.5, +2.1] | +2.4 [+1.6, +3.1] | +2.1 [+1.4, +2.8] |
| guardrails-ood-v1 准确率（4949） | +0.0 [-0.6, +0.6] | +0.5 [-0.2, +1.1] | +0.1 [-0.5, +0.7] | -0.1 [-0.7, +0.5] | -1.1 [-1.8, -0.4] | +0.8 [+0.2, +1.4] | +1.1 [+0.4, +1.6] | +0.7 [+0.1, +1.3] | +3.3 [+2.7, +3.9] | +3.4 [+2.7, +4.1] | +3.7 [+3.1, +4.4] | +3.9 [+3.3, +4.6] |
| ood-v2 ECE | -0.017 [-0.023, -0.012] | -0.015 [-0.021, -0.009] | -0.017 [-0.023, -0.012] | -0.015 [-0.020, -0.009] | -0.009 [-0.014, -0.003] | -0.015 [-0.021, -0.010] | -0.013 [-0.019, -0.007] | -0.010 [-0.015, -0.005] | -0.017 [-0.022, -0.011] | -0.017 [-0.022, -0.011] | -0.023 [-0.029, -0.016] | -0.022 [-0.027, -0.016] |
| agents-ood-v1 ECE | -0.066 [-0.074, -0.057] | -0.066 [-0.074, -0.059] | -0.065 [-0.073, -0.057] | -0.063 [-0.072, -0.054] | -0.055 [-0.065, -0.045] | -0.068 [-0.076, -0.061] | -0.064 [-0.072, -0.056] | -0.055 [-0.063, -0.046] | -0.087 [-0.097, -0.078] | -0.106 [-0.114, -0.097] | -0.104 [-0.113, -0.096] | -0.106 [-0.114, -0.097] |
| guardrails-ood-v1 ECE | -0.020 [-0.027, -0.014] | -0.011 [-0.018, -0.004] | -0.020 [-0.026, -0.013] | -0.017 [-0.024, -0.011] | -0.017 [-0.023, -0.010] | -0.013 [-0.020, -0.007] | -0.012 [-0.019, -0.006] | -0.012 [-0.019, -0.005] | -0.069 [-0.074, -0.061] | -0.069 [-0.075, -0.060] | -0.070 [-0.076, -0.062] | -0.068 [-0.074, -0.061] |
| breadth ECE Δ（gated panel） | +0.002 [-0.011, +0.012] | +0.007 [-0.008, +0.017] | +0.000 [-0.011, +0.011] | +0.006 [-0.008, +0.017] | +0.013 [-0.003, +0.021] | +0.009 [-0.006, +0.019] | +0.006 [-0.008, +0.015] | +0.018 [-0.001, +0.026] | +0.010 [-0.008, +0.019] | +0.012 [-0.006, +0.020] | +0.001 [-0.010, +0.012] | +0.007 [-0.007, +0.016] |
| Kev ECE Δ | -0.010 [-0.020, +0.001] | -0.013 [-0.022, -0.001] | -0.008 [-0.019, +0.003] | -0.006 [-0.018, +0.004] | +0.006 [-0.009, +0.014] | -0.013 [-0.023, -0.001] | -0.003 [-0.016, +0.007] | -0.002 [-0.014, +0.007] | -0.012 [-0.022, +0.001] | +0.005 [-0.009, +0.014] | -0.006 [-0.019, +0.007] | -0.007 [-0.019, +0.005] |
| tsheld ECE Δ | -0.024 [-0.038, +0.001] | -0.025 [-0.040, -0.001] | -0.022 [-0.037, -0.001] | -0.030 [-0.039, -0.003] | -0.019 [-0.034, +0.004] | -0.028 [-0.042, -0.003] | -0.022 [-0.036, -0.000] | -0.013 [-0.028, +0.008] | -0.007 [-0.025, +0.009] | +0.005 [-0.016, +0.024] | +0.005 [-0.015, +0.024] | +0.006 [-0.017, +0.024] |
| CUAD ECE 16k+（Kev-27B 0.071） | 0.084 | 0.060 | 0.081 | 0.077 | 0.072 | 0.066 | 0.070 | 0.068 | 0.110 | 0.107 | 0.104 | 0.102 |
| longdoc generated 准确率 | 1.000 | 0.999 | 1.000 | 1.000 | 1.000 | 0.999 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |

Breadth 指数（机会修正，全部 14 个 sources；`scripts/breadth_report.py`，取自 round 20 与 22 在相同温度下的报告，未重新计算）：Kev-27B 50.2 [47.4, 53.3]，AutoJev 51.7，Jev 53.3；round 19 (a) 53.0、(b) 51.7；round 20 a-w85 52.9、a-w70 53.5、a-w50 53.4、b-w85 53.1、b-w70 53.3、b-w50 53.7；round 22 s25 51.7、s50 52.1、s75 52.0、final 52.3 [49.5, 55.2]（相对 Kev-27B +2.1 [−0.6, +4.7]；`27b-r20a-w85` +2.7 [+0.0, +5.2]）。仅作报告的各列显示：round-22 checkpoints 是那些学到了 out-of-domain 生成器的（agents-ood +1.3 到 +2.4，guardrails-ood +3.3 到 +3.9，相对 round 19/20 的 −1.1 到 −0.0 与 −1.1 到 +1.1），也是那些取得了 tasksource 增益的（在有效 families 上为 +2.4 到 +4.1，相对 −0.1 到 +2.0），两者在 sft-v2-r22 的分布内（其 tasksource-v1 families 及其 OOD 组件的生成器）；round-19/20 checkpoints 则将 CUAD 16k+ ECE 保持在接近 Kev-27B 的水平（0.060-0.084 vs 0.071），而 round 22 的没有（0.102-0.110）。单独的 hard-v1 在各处都是 +14.0 到 +19.9 pp；去掉它后 Kev-panel 增益为 +1.7 到 +4.1。

**检查.** 去掉排除项后，各 panels 精确复现已提交的 read-outs：覆盖全部 14 个 sources 的 breadth（例如 round 20 a-w85 +1.43、round 22 final +1.30）、覆盖全部 24 个 families 的 tasksource-heldout（final +3.80），以及每一个 pooled T（round 20 与 round 22 的）。Round 22 已提交的 read-out 与本 PR 的 `kev.rounds` 逐位复现，且 `tests/test_rounds.py`（在 `KEV_ROUNDS_ROOT` 设为研究 checkout 时）复现 rounds 5-20。Round-22 final 的 gated 数字与审计的事后反事实吻合（breadth +1.54 [+0.57, +2.47]，tasksource-heldout +4.06 [+2.31, +5.77]，short −0.88 [−1.95, +0.19]）。

**偏差.** (i) 私有排除列表上传了两次：第一次 `scripts/private_rows.py upload` 推送了文件（`kev-private-train@8d7d0835`）但未能将其 manifest 写入一个缺失的目录；重跑的相同 commit 被 Hub 跳过，且 manifest 固定指向 `8d7d0835`，即相同的 sha256。(ii) Pooled T 的区间重采样为（source、record）在每个 source 内的簇（`kev.metrics.cluster_resamples`，2,000 次重采样），而审计抽取的是 200 次未分层重采样；final 的区间此处为 [1.231, 1.481]，审计处为 [1.20, 1.52]。(iii) Round 19 的 finals 的 transfer-v4 development 行是它们 trials 的 in-trial transfer reads（按 round 19 与 20 读取的方式）；其他每个 checkpoint 都有一次 `transfer4` read。

**后续（Jared）.** 按注册对 `27b-r22-final` 做 confirmation（tests 阶段含 Kev-27B 一侧、Jev 与 AutoJev 在 breadth-v1 test 上、locked、在 8k / 32k / 64k 的 bf16 serving 检查），每个只读一次。鉴于温度发现，一次通过的 confirmation 还应报告 candidate 的 T interval 上的 test-partition ECEs。

**证据**（已提交）：read-out 及其表格（`runs/r24-readout/readout.txt`）；它评分所用的公开行：round 22 的 reads（`runs/r22-27b-lr2e6[-sNN]-<tag>`，report + rows；OOD reads：仅报告）、round 22 final trial 的 in-trial transfer 行与 provenance、round 21 的 parent OOD 报告，以及 2026-09-27 sweep 的 reads（`runs/sweep-<checkpoint>-<tag>`：longdoc report + rows、OOD reports）。私有部分（`jaredpalmer/kev-private-train` 下 `runs/r24/`，`scripts/private_rows.py restore`）：排除列表（`runs/r24-readout/private-exclude.json`，@ `8d7d0835`）与 52 个行文件，每个 tasksource-heldout-v1 read 与 OOD 行（`runs/r24-readout/private-rows.json`，@ `9beb213b`）。支出：$0（无 Modal 作业、无 gateway 调用）。

### Round 24 confirmation

**未确认.** `27b-r22-final` 通过了 tests 阶段，但未通过 locked 阶段：locked transfer-v4 准确率为 0.8841（656 中 580），相对注册 bar 0.886（需要 582）。它差了 2 道题。Kev-27B 在同一 read 上得 0.8963（588）。未发布任何内容，Kev-27B 仍是 27B 发布版本。每个 confirmation read 都只做了一次，且只针对具名 candidate，按注册方式。结论：`runs/r24-verdict/27b-tests.json`、`runs/r24-verdict/27b-locked.json`（`python -m kev.rounds confirm experiments/rounds/r24.json --stage {tests,locked}`）。两侧都在 1.382 下服务：candidate 用其 pool fit（648 道题，无排除），Kev-27B 用其发布 T，即同一网格点。Deltas 为相对 Kev-27B 的成对、按记录聚类的 bootstrap（2,000 次重采样，seed 0，micro），以 pp 计。

**Locked bar 按注册保持有效.** 审计从 development rule 的 short-state 与 Kev panels 中去掉了 `emotion`。Locked 标准注册于整个 locked transfer-v4 partition，包含 `emotion`，且我们不在结果出来后调整它。在 candidate 差 2 道题未过之后，再去掉 `emotion` 重算 locked read，恰恰就是 confirmation 存在所要排除的那种事后操作，因此我们未计算它。Locked 阶段表明 candidate 在 short states 上并不优于 Kev-27B：−1.2 [−2.6, +0.2]。这与 development read 吻合，那里 short-state 准确率仅在去掉 `emotion` 时才通过（−0.9 [−2.0, +0.2]；见「Round 24 结果」）。

| 阶段 / 标准（panel，n） | 27b-r22-final | Kev-27B | Δ [95 %] | verdict |
|---|---|---|---|---|
| tests：breadth-v1 test 准确率，下界 > 0（去掉 `routerbench`、`cfcolor`、`humicroedit`、`chessbench`；2,489，600 剔除） | 0.835 | 0.820 | +1.5 [+0.5, +2.5] | pass |
| tests：tasksource-heldout-v1 test 准确率，下界 > 0（去掉七个 families；2,024，809 剔除） | 0.796 | 0.743 | +5.3 [+3.7, +7.0] | pass |
| tests：pooled hard-v1 + devtools-v1（去掉 `flakeflagger`、`commitpackft_type`）+ documents-v1 test 准确率，下界 ≥ −1（2,795，300 剔除） | 0.886 | 0.800 | +8.6 [+7.1, +10.0] | pass |
| **locked：transfer-v4 locked 准确率 ≥ 0.886（656）** | **0.8841（580）** | 0.8963（588） | −1.2 [−2.6, +0.2] | **fail**（需要 582） |
| locked：服务时 Brier ≤ 0.165（656） | 0.1549 | 0.1604 | −0.005 [−0.018, +0.006] | pass |

**仅作报告的 test reads**（相同排除项；ECE 按服务时）：

| panel（n） | 27b-r22-final | Kev-27B | Δ [95 %] |
|---|---|---|---|
| hard-v1 test（1,088） | 0.916 | 0.749 | +16.7 [+14.0, +19.7] |
| devtools-v1 test，gated sources（771） | 0.815 | 0.789 | +2.6 [+0.1, +4.9] |
| documents-v1 test（936） | 0.908 | 0.869 | +4.0 [+2.0, +6.0] |
| documents-v2，私有 held-out test（953） | 0.919 | 0.881 | +3.8 [+1.7, +6.0] |
| breadth-v1 test，全部 14 个 sources（3,089）；ECE | 0.762；0.017 | 0.748；0.019 | +1.3 [+0.4, +2.3] |
| breadth-v1 test ECE，gated panel | 0.014 | 0.013 | - |
| tasksource-heldout-v1 test ECE，gated panel | 0.055 | 0.051 | - |
| longdoc-v1 test CUAD 准确率（2,194） | 0.872 | 0.890 | **−1.8 [−3.2, −0.5]** |
| longdoc-v1 test CUAD ECE | **0.055** | 0.007 | - |
| 按长度 CUAD，准确率 / ECE：< 8k（867） | 0.873 / 0.058 | 0.900 / 0.025 | - |
| 8k-16k（443） | 0.880 / 0.056 | 0.892 / 0.028 | - |
| 16k-32k（442） | 0.871 / 0.062 | 0.882 / 0.019 | - |
| 32k-64k（442） | 0.862 / 0.066 | 0.876 / 0.014 | - |
| 16k+（884） | 0.867 / 0.062 | 0.879 / 0.013 | - |
| longdoc-v1 test generated（2,400）；ECE | 1.000；0.001 | 1.000；0.014 | - |

在 CUAD 上，test read 比 development 更差。Candidate 在每个长度上都损失准确率（−1.1 到 −2.7 pp），且其 ECE 在每个桶中都是 Kev-27B 的 2-5 倍。Development rule 的 CUAD 准确率 guard（下界 ≥ −2 pp）在 test 上不成立（−3.2）；16k+ 的差距（−1.2 pp）则成立。两者在此阶段都仅作报告，因此都不改变结论。这与 round 22 在 development 上发现的同一合同领域失校准一致（每个桶中 ECE 约 0.10 vs 0.06-0.07，见「Round 22 结果」、PR #165）；Kev-27B 的 test ECE（按桶 0.014-0.028）远低于其 development 的。

**TEST 上的 Breadth 指数**（机会修正，全部 14 个 sources；`scripts/breadth_report.py`，`runs/r24-breadth-report/report.md`；Jev 经 AI Gateway（`kev.jev`）、AutoJev 经其自身 server，各自在同一测试项上读一次）：candidate **53.7 [50.5, 56.7]**，Jev **54.0** [51.2, 57.0]，Kev-27B **50.2** [47.0, 53.2]，AutoJev **50.0** [47.0, 53.3]。相对 Kev-27B：candidate +3.5 [+1.0, +6.0]，Jev +3.9 [+0.9, +7.0]，AutoJev −0.2 [−3.3, +3.0]。Pooled ECE：candidate 0.017，Kev-27B 0.019，Jev 0.052，AutoJev 0.040。Candidate 的增益来自 Retrieval & Classification（69.7 vs 61.6；CLINC150 0.947 vs 0.847，SGD 0.720 vs 0.607）与 Arts & Human Taste（28.0 vs 18.7）。它交还了 Tools & Automation（62.6 vs 65.1；`routerbench` 0.300 vs 0.373）。在此测试 panel 上它达到了 Jev 的指数：点估计差 −0.3，未计算成对区间。

**温度区间两端的校准**（仅作报告，按 round-24 结果所要求的；candidate 在其 pooled T 的 90 % 区间 [1.231, 1.481] 两端以及拟合点服务，Kev-27B 在 1.382；`runs/r24-verdict/27b-tests-t-interval.json`）。ECE / Brier：

| test panel（n） | T 1.231 | T 1.382（已服务） | T 1.481 | Kev-27B @ 1.382 |
|---|---|---|---|---|
| breadth-v1，gated（2,489） | 0.025 / 0.2346 | 0.014 / 0.2335 | 0.018 / 0.2335 | 0.013 / 0.2516 |
| breadth-v1，全部 14（3,089） | 0.030 / 0.3122 | 0.017 / 0.3111 | 0.019 / 0.3111 | 0.019 / 0.3267 |
| tasksource-heldout-v1，gated（2,024） | 0.035 / 0.2972 | 0.055 / 0.3009 | 0.068 / 0.3041 | 0.051 / 0.3682 |
| pooled hard + devtools + documents-v1（2,795） | 0.022 / 0.1599 | 0.016 / 0.1603 | 0.021 / 0.1610 | 0.027 / 0.2720 |

Development 的发现也在 test 上成立。跨一个 interval，breadth ECE 在低端的 0.014 → 0.025，而 tasksource-heldout ECE 在高端的 0.055 → 0.068：它们朝相反方向拉动，因此 interval 内没有单一的 T 对两者都最优。Brier 几乎不动（≤ 0.004）。

**Serving 检查**（bf16，H200；通过；`runs/serving-27b-r24/report.json`、`runs/serving-27b-r24-long/report.json`）：
- Short states，280 道题：
  - CUDA graphs vs fp32：max |Δp| 0.0235，1 次 argmax 翻转；eager bf16 vs fp32：0.0267，1 次翻转（bar ≤ 0.03，≤ 1 次翻转）。
  - Graphs vs eager：0.022，0 次翻转。按服务时的题目隔离：0.0078，0 次翻转。
- Long states，服务 vs benchmark，每长度 3 条记录 / 15 道题：
  - 8k：max |Δp| 0.0083，0 次翻转；new state 1.37 s，cached 584 ms；峰值 70 GB。
  - 32k：0.0079，0 次翻转；4.17 s / 612 ms；79 GB。
  - 64k：0.0024，0 次翻转；9.47 s / 725 ms；87 GB。

**发布温度**（若通过）：pool fit，1.3819，90 % CI [1.231, 1.481]（648 道题；（source, group）在每个 source 内重采样，2,000 次重采样，seed 0）。

**偏差.** Tests 阶段的 reads 于 00:09:43Z 启动（`runs/r24-reads-27b-r22-final-tests.json`）。这是在 23:57Z 计算出、点名 candidate 的 read-out 之后，约比结果 commit `b9ceefe`（00:12:16Z）早 2.5 分钟。Locked read 于 00:22:56Z 从 `b9ceefe` 派生。没有 read 被重复。

**支出.** Modal 在 round 23 重新注册读数时全工作区计量约 $3,790，加上约 $80 的计量滞后。Round 23 首次注册读数为 $3,571.88（2026-09-27T13:32Z）。差额覆盖了 2026-09-27 审计 sweep 的 reads、本次 confirmation（14 次 test reads、locked read、两次 serving 检查、AutoJev 的 breadth-v1 test read）以及工作区其他应用；未按作业拆分。AI Gateway：$0.064（Jev 在 breadth-v1 test 上，1,992 次调用）。

**证据**（已提交）：结论与 T-interval 表格（`runs/r24-verdict/`）；启动记录（`runs/r24-reads-27b-r22-final-{tests,locked}.json`）；公开 test reads（`runs/r24c-27b-{cand,parent}-<tag>`：hard-v1、devtools-v1 与 documents-v1 的行，其余的报告）；locked read（`runs/locked/kev-27b-r24-ungated/`）；test breadth 报告（`runs/r24-breadth-report/`）；Jev 与 AutoJev 的 breadth-v1 test 报告；serving 报告。私有部分（`jaredpalmer/kev-private-train` 下 `runs/r24/`，`scripts/private_rows.py restore`）：tasksource-heldout-v1 的 test 行与报告、四个系统的 breadth-v1 test 行、documents-v2 行（`runs/r24-verdict/private-rows.json`，@ `79c69ff6`）与 longdoc-v1 test 行（`runs/r24-verdict/private-rows-longdoc.json`，@ `79272e0f`）。

**后续.** Candidate 的增益在每个未触碰的 test partition 上都成立。它在 Kev-27B 最强的地方失败，即 short states，且在 CUAD 上更差。Round 23（PR #165）基于 round 24 的审计后 rule 重新注册：将 round 22 final 向 Kev-27B 自身的权重混合，以保留广泛的增益并恢复 Kev-27B 最擅长的部分。

## Round 23（已注册）

### Round 23 - round 22 final SFT checkpoint 向 Kev-27B 自身权重的事后混合，在 round 24 的审计后 rule 下（随本 spec 的 commit 于 2026-09-28 重新注册，写于任何 round-23 插值或读取之前）

**重新注册.** Round 23 最初于 2026-09-27 注册（PR #165，commit `9345b17`），使用 round 22 的 rule，其中包含 scienthoon 与 pooled externals。那一版从未启动：没有任何插值，也没有任何读取。现被本版取代。Candidates、插值工具与温度 pool 不变。Rule、reads、parent reads 与 confirmation 现在**逐字采用 round 24 的**。Scienthoon 已不复存在（`kev.suite.REMOVED_SUITES` 拒绝从 round 23 读取它；见「scienthoon 已移除」）。本节与 `experiments/rounds/r23.json` 写于任何 round-23 read 之前。它们写于 round 24 的 confirmation 之后，且设计对此做出了反应（见下文「测试 partitions 的复用」）。

**原由.** Round 24 将 round 22 的 final checkpoint 提名为其 candidate，但**未获确认**（「Round 24 confirmation」）。其增益在每个未触碰的 test partition 上都成立：breadth-v1 +1.5 [+0.5, +2.5]，tasksource-heldout-v1 +5.3 [+3.7, +7.0]，pooled hard/devtools/documents-v1 +8.6 [+7.1, +10.0]，documents-v2 +3.8，test breadth 指数 53.7 相对 Kev-27B 的 50.2 与 Jev 的 54.0。它在 Kev-27B 最强的位置失败。Locked transfer-v4 为 0.8841，相对 0.886 的 bar 差 2 道题（Kev-27B 0.8963）。在 longdoc CUAD test 上它更差：−1.8 [−3.2, −0.5]，ECE 0.055 相对 0.007。Short states 与合同文档正是 Kev-27B 擅长的，因此将 SFT 向 Kev-27B 混合，应当能保留大部分广泛增益，并恢复 short-state 与 CUAD 的行为。

Round 20 将 round 19 的 SFT checkpoints 向 **base** 混合，且 scienthoon 并未恢复（对 arm (a) 而言，越靠近 base 越糟）。但 scienthoon 是那里失败的 guard，且此后已作为不健全而被移除。Base 也不是在 short states 与 CUAD 上表现好的模型；Kev-27B 才是。两个 checkpoints 都是同一组权重的 fine-tunes（`Qwen/Qwen3.8-27B` @ `1d4bf0f2`）：SFT 移动了每个权重（full weights，lr 2e-6，一个 epoch），而 Kev-27B 在每个线性投影上加了一个 rank-16 LoRA。对单一初始化的 fine-tunes 做平均，就是「model soups」意义上的权重平均（Wortsman et al., 2022）。它也是 WiSE-FT，只是用一个 fine-tuned 端点替代了 zero-shot 端点。风险在于两个已分离的 fine-tunes 之间存在 loss barrier。那会在 α 0.50 处最先显现；α 0.85 与 0.70 仍接近 SFT。

**Heads.** 一个混合后的 backbone 需要一支 pointer head。SFT 的 head 训练于 SFT backbone 上，Kev-27B 的 head 训练于其自身 backbone 上，因此两者都不匹配一个混合体。两种选择都不明显正确，因此两者都注册：保留 SFT head（每个混合体中大部分是 SFT），或用相同的 α 混合 heads。

**Candidates**（spec `experiments/rounds/r23.json`；parent Kev-27B 为 `r6-27b-v2/01-trial-1`，Hub `01b81998`）。每个 candidate 都可选，且没有参考 arms：α = 1 即 round 22 final（round 24 的 candidate），α = 0 且用混合 head 即为 Kev-27B。

| arm | checkpoint | 在 SFT backbone 上的权重 | head |
|---|---|---|---|
| `27b-k-w85`、`27b-k-w70`、`27b-k-w50` | `/runs/r23-wise/27b-k-w{85,70,50}/checkpoint` | 0.85 / 0.70 / 0.50 | SFT 的 |
| `27b-kh-w85`、`27b-kh-w70`、`27b-kh-w50` | `/runs/r23-wise/27b-kh-w{85,70,50}/checkpoint` | 0.85 / 0.70 / 0.50 | 用相同 α 混合 |

SFT 端点：round 22 的 final checkpoint，`/runs/r22-27b-lr2e6/00-trial-0/checkpoint`（full weights，bf16）。另一端点：`jaredpalmer/kev-27b@01b81998019be550f0ae858727df49bac9511195`，同一 base 与修订上的一个 LoRA adapter。

**插值**（本 PR 中的工具改动；与首次注册相同）。`scripts/interpolate_checkpoint.py --toward <checkpoint>`（`modal_app.py::interpolate --toward ... [--blend-head]`）将 SFT 的 base 与修订下的另一个 checkpoint 作为另一端点，而非 base。
- 一个 full-weight checkpoint 从其分片流式读取。
- 一个 LoRA checkpoint 在 fp32 中作为 W + delta 合并。W 是按其 loader 构建方式构建的 base（bf16 值精确向上转换）。delta 是 peft 对每个被适配层的 `get_delta_weight`：即 peft 合并所加的值，在混合前不四舍五入（已服务并融合的 Kev-27B 持有 round(W + delta)）。
- 每个输出张量在 fp32 中为 α · SFT + (1 − α) · other，一次性舍入为 bf16，同 round 20。
- 在写入任何内容之前拒绝：另一个 base 或修订；两个 backbones 之间任何张量名称或形状不同；DoRA 或其他 LoRA 变体、LoRA biases、`modules_to_save` 与已训练的 token embeddings（它们改变 W + delta 之外的权重）。
- `--blend_head`（需要 `--toward`）用相同 α 在 fp32 中混合 pointer heads。它拒绝张量、形状、dtypes、`head_dim`、`option_isolation` 或 `special_embeddings` 不同的 heads。Kev-27B 与 SFT 的 heads 都是带 bias 的 q/k 256 × 5120，fp32。
- `head.pt` 保留 SFT 的 meta，并记录 `interpolation: {alpha, sft: {path, weights_sha256}, base, toward: {path, resolved, kind, weights_sha256, head_sha256, merge, adapted_tensors}, head: {kind: sft | blend, sft: {head_sha256, temperature}, toward: {head_sha256, temperature}}}`。
- 内存同 round 20（base 常驻 bf16、adapter 小、每张量 fp32 临时量），因此 `kev.budget` 的插值资源不变。

在随机两层 Qwen3.5 上的测试（`tests/test_unit.py`）：
- 向一个 LoRA checkpoint 插值，α = 1 时精确等于 SFT。
- α = 0 且带 `--blend_head` 时精确等于 LoRA 模型：其 backbone 是 fp32 的 `merge_and_unload` 一次性舍入为 bf16，逐张量等于以合并方式加载的 checkpoint，且 head 为 LoRA 的。
- α = 0.5 是 SFT 与未舍入合并结果的 fp32 中点，heads 取平均；不带 `--blend_head` 时则是相同 backbone 配 SFT head。
- 向一个 full checkpoint 插值，α = 0 时精确等于其 backbone 与 head。
- 拒绝情形：base-修订不匹配、`--blend_head` 无 `--toward`、另一形状的 head、被重命名的张量。

**温度（必须，见 `docs/autoresearch.md` 第 3 节）：round 24 的 pool，含其区间.** 每个 candidate 都在基于其自身 transfer-r3 calibration 行（read `r3cal`，八个 held-out sources，按 round 24 含 `emotion`：448 道题）加上 transfer-v9 development MMLU-Pro（read `v9`：200 道题）、减去其 transfer-v4 development 记录所拟合的温度下服务。Kev-27B 使用其发布的 1.38。仅作报告、不 gate：每个 candidate 的 pooled T 的 90 % bootstrap 区间（`temperature.ci`：在每个 source 内对 (source, group) 簇的 2,000 次重采样，seed 0，相同网格与目标）。一个 blend 在两个端点的数据上都训练过，因此每个 candidate 都注明 `trained_on: [evals/sft-v2-r22, evals/v7/decision-v7, evals/round6/b1v2]`：round 22 的训练 suite，加上 Kev-27B 的 decision-v7（其 manifest 由其 provenance 哈希）以及其 `data` 文件的 suite b1v2。`kev.rounds validate` 对照它们全部检查 pool，未发现任何共享的 pooled suite、source 或训练 partition。

**Reads.** Round 24 的每 candidate 16 次，tag 与 suites 相同：breadth、tsheld、hard、devtools、docs、transfer4、semif、wanli2、typesafe、v9、r3test、r3cal、longdoc、ood、agentsood、guardood。没有 scienthoon read。`read_timeout` 为 `{"27b": 14400}`，且每个 candidate 的「transfer」行是其自身的 `transfer4` read（round 级 `transfer_read`）。Kev-27B 的 reads 就是 round 24 的，文件相同：其已提交的 reads 加上 round 21 的四个 parent reads `runs/r21-P27-{tsheld,ood,agentsood,guardood}`。tsheld read 与 OOD 行从私有数据集用 `scripts/private_rows.py restore --manifest runs/r22-readout/private-rows.json` 恢复。

**Rule：逐字采用 round 24 的.** 该 spec 的 `rule`、`reads`、`temperature` 与 `parents` 等于 `r24.json` 的。一切均相对 Kev-27B，采用成对、按记录聚类的 bootstrap（2,000 次重采样，seed 0，micro），每个 candidate 在其 pool 温度下，Kev-27B 在 1.38，且 `drop_ids` 同前。排除项从两侧移除：
- breadth-v1 去掉 `routerbench`、`cfcolor`、`humicroedit`、`chessbench`；
- tasksource-heldout-v1 去掉编码为 T11 T12 T14 T15 T18 T22 T24 的七个 families，从私有排除文件 `runs/r24-private/tsheld-exclude.json` 读取（按路径与 sha256 `a72030ab…` 注册；用 `scripts/private_rows.py restore --manifest runs/r24-readout/private-exclude.json` 恢复；`kev.rounds` 拒绝哈希不符的文件，并在缺少它时报告该 panel 缺失）；
- Kev panel 与 short state 去掉 `emotion`；devtools-v1 去掉 `flakeflagger` 与任务 `commitpackft_type`。

1. primaries：breadth-v1 dev 准确率下界 > 0；tasksource-heldout-v1 dev 准确率下界 > 0；Kev panel（transfer-v4 dev、hard-v1、devtools-v1、documents-v1）准确率下界 ≥ −1 pp；
2. guards：short state（transfer-v4 dev + transfer-r3 test）准确率下界 ≥ −2 pp，Brier 上界 ≤ +0.02，confident errors 上界 ≤ +1 pp；transfer-v9 上 unknowable 占比 ≤ 0.05；longdoc CUAD 准确率下界 ≥ −2 pp，且 CUAD 16k+ 准确率 candidate − Kev-27B ≥ −2 pp；
3. calibration：breadth、Kev-panel 与 tasksource-heldout 的 ECE ≤ Kev-27B 的 + 0.01（相同排除项）；
4. candidate：通过 checkpoints 中 breadth + tasksource-heldout + Kev-panel 准确率增益最大的那个。Read-out 会说明六个中有几个通过。

仅作报告（`optional` panels，永不 gate，永不会使 candidate 不完整）：
- SemIf、WANLI-v2 与 TypeSafe。无 pooled-externals guard，也无 scienthoon read。
- 按长度的 CUAD ECE（含 16k+），以及 longdoc generated。
- ood-v2、agents-ood-v1 与 guardrails-ood-v1。
- 单独的 hard-v1，以及去掉 hard-v1 的 Kev panel。
- 覆盖全部 14 个 sources 的 breadth 以及覆盖三个被移走 sources 的 breadth；覆盖全部 24 个 families 的 tasksource-heldout；机会修正后的 breadth 指数（`scripts/breadth_report.py`）。

关于 #167 常设规则的一条说明。#167 写明从 round 23 起，pooled external guard 应为 SemIf + WANLI-v2 + TypeSafe。审计发现该 panel 作为 gate 不健全：去掉 scienthoon 后它由 81 % 的 WANLI 组成，split-half r 0.08。因此 Round 24 将其去掉，且本 round 遵从 round 24，所以这三个 suites 是被报告而非被 gate。常设规则随本 PR 更新。

**Confirmation：与 round 24 完全相同**（仅具名 candidate，每个只读一次；若无 candidate 则为空）：
- `tests`，每个都是相对 Kev-27B 的成对下界：
  - breadth-v1 test 准确率下界 > 0（相同四个 sources 剔除；全部 14 个均报告）；
  - tasksource-heldout-v1 test 下界 > 0（相同七个 families 剔除）；
  - pooled hard-v1 + devtools-v1（去掉 `flakeflagger`、`commitpackft_type`）+ documents-v1 test 下界 ≥ −1 pp；
  - 报告项：documents-v2，以及 longdoc-v1 test（按长度的 CUAD、generated）。
  - Candidate reads 写入 `runs/r23c-27b-cand-<tag>`。Kev-27B 一侧**复用而非重读**：其 test reads 来自 round 24 的 confirmation，`runs/r24c-27b-parent-<tag>`（相同 checkpoint、suites 与服务 T；私有部分从 `runs/r24-verdict/private-rows{,-longdoc}.json` 恢复）。
  - Test breadth 指数与 round 24 的 Jev 与 AutoJev reads（`runs/r24c-{jev,autojev}-breadthtest`）比较，后者不再读取。
- `locked`：locked transfer-v4 准确率 ≥ 0.886，且服务时 Brier ≤ 0.165（`runs/locked/kev-27b-r23-ungated`）。
- 任何发布之前：bf16 serving 检查按 round 24 的方式运行（`modal_app.py::serving --gpu H200 --flags=--isolation`：max |Δp| ≤ 0.03，280 题中 ≤ 1 次翻转；加上在 8k / 32k / 64k 的长 state 运行，相同 bar）。发布温度是由 `scripts/calibrate_checkpoint.py` 在 candidate 的 r3cal + v9 行上写出的 pool fit，并报告其区间，且按 round 24 的方式报告该区间两端的 test-panel ECEs。

**测试 partitions 的复用（直说）.** Round 23 的 confirmation 读取与 round 24 的 candidate 及 Kev-27B 相同的 test partitions 与相同的 locked transfer-v4。本 round 的设计是在看到那次 confirmation 之后选定的：因为 candidate 在 locked short states 与 CUAD test 上失败，所以向 Kev-27B 混合。因此这些 partitions 对此问题而言不再是未触碰的，一次通过将是弱于 round 24 那些 reads 的证据。Bar 是 round 24 的，在任何 round-23 read 之前在此固定。只确认一个 candidate，且每次读取只做一次。一次通过应附带此 caveat 报告，而是否发布的决定权在 Jared。

**Budget.** 参考点：本次注册时计量约 $3,790，加上约 $80 的计量滞后，即约 $3,870。上限为计量 $5,000，每次启动都保留约 10 % 的储备（$500）。

| 项目 | 准入上限 | 预期 |
|---|---|---|
| 截至目前支出（计量 + 滞后） | 约 $3,870 | 约 $3,870 |
| 两次插值（CPU，8 核 / 128 GiB / 3 h；`kev.budget.interpolation_bound`） | $8.41 | 约 $3（round 20：每个 α 150-230 s，加上加载） |
| reads，一次一个 candidate（16 × $25.06，H200，每上限 4 h） | 任意时刻 $400.96；六个合计 $2,405.76 | 约每 candidate $30（含 longdoc，约 2.8 h），六个合计约 $180-250 |
| **rule 阶段的预测** | 任意时刻 **$4,279.37** | **约 $4,055-4,125** |
| $5,000 中剩余储备 | $720.63（14.4 %） | 约 $875-945（17.5-19 %） |
| confirmation，仅 candidate（tests 7 次 reads × $25.06、4 h 的 locked read、serving 检查与长 state 运行） | $175.42 + $25.06 + $12.54 = $213.02 | 约 $45-90 |

六个 candidates 的 read 上限合计撑不到上限之下，因此 reads **一次启动一个 candidate**，顺序为 `27b-k-w85`、`27b-kh-w85`、`27b-k-w70`、`27b-kh-w70`、`27b-k-w50`、`27b-kh-w50`。每个 batch 仅在前一个已落地、再次读取过计量成本、且计量支出 + 滞后低于 $4,099.04（$5,000 − $500 − $400.96）后才启动。Confirmation 仅当计量支出 + 滞后 + $213.02 ≤ $4,500 时才启动。Confirmation 时预期：约 $4,125 + $90 ≈ $4,215。

**运行步骤**（本 PR 合并之后；此前不启动任何内容）：
1. 用 `uv run python scripts/private_rows.py restore --manifest <m>` 恢复私有输入，针对 `runs/r22-readout/private-rows.json`（round 21 的 parent reads）与 `runs/r24-readout/private-exclude.json`（排除列表）。然后 `uv run python -m kev.rounds validate experiments/rounds/r23.json` 并读取计量成本。
2. 运行 `KEV_APP_NAME=kev-sft uv run modal run --detach modal_app.py::interpolate --sft /runs/r22-27b-lr2e6/00-trial-0/checkpoint --toward jaredpalmer/kev-27b@01b81998019be550f0ae858727df49bac9511195 --prefix 27b-k --study r23-wise`，60 秒后用 `--blend-head --prefix 27b-kh` 运行相同命令。
3. 当两者都写入了 `runs/r23-wise/<arm>/interpolation.json`，就按上述顺序、一次一个 candidate 运行 `uv run python -m kev.rounds launch-reads experiments/rounds/r23.json --arms <arm>`，每次之前都读取计量成本。
4. `readout`，然后按所写进行 confirmation。对于 tests 阶段，先恢复 `runs/r24-verdict/private-rows.json` 与 `private-rows-longdoc.json`，以便 Kev-27B 一侧就位且不被重新启动。

可提交内容：同 round 24。公开 suite 的行与报告会被提交。Tasksource-heldout-v1 的 reads、ood / agents-ood / guardrails-ood 的行，以及私有 test 行通过 `scripts/private_rows.py` 进入私有数据集，从不上传到 git，族名也从不公开写出。

### 第 23 轮结果

**候选：** `27b-k-w85`（0.85 · 第 22 轮最终结果 + 0.15 · 以 fp32 合并的 Kev-27B，即 SFT 的指针头；`/runs/r23-wise/27b-k-w85/checkpoint`）。**6 个候选中有 5 个**通过已登记的规则；`27b-k-w50` 未通过 breadth ECE（0.0195，高于阈值 0.0176）。排名（breadth + tasksource-heldout + Kev-panel 准确率提升）将通过的五个排序为 `27b-k-w85` +13.8、`27b-kh-w85` +13.7、`27b-k-w70` +13.6、`27b-kh-w70` +13.5、`27b-kh-w50` +12.8。读出： `runs/r23-readout/round23.json`（`python -m kev.rounds readout experiments/rounds/r23.json`，在最后一次读取落地后于 2026-09-28T20:31Z 运行），表格 `runs/r23-readout/readout.txt`，markdown `runs/r23-readout/tables.md`。每个候选都在其合并 T 下提供（648 道题，无一道作为 transfer-v4 重复项被排除），Kev-27B 在 1.382。Delta 为相对 Kev-27B 的成对记录聚类自助法（2,000 次重采样，seed 0，micro）：准确率与置信错误以 pp 计，Brier 为绝对值，ECE 按提供时相对其阈值给出。排除项移除的题目与第 24 轮相同：600 道 breadth、795 道 tasksource-heldout、380 道 Kev-panel 和 220 道 short-state，两侧一致。

**插值**（`modal_app.py::interpolate`，8-CPU 容器，每个 α 耗时 304–398 s；`runs/r23-wise/<arm>/interpolation.json`）。SFT 端点的权重 sha256 `3fa0182a…`，头 `bfcf801e…`（T 1.0）。Kev-27B 端点：类型 `lora`，以 fp32 作为 base + peft `get_delta_weight` 合并（850 个中有 496 个适配张量），权重 `41bf5af0…`，头 `1322189d…`（T 1.382）。混合骨干：α 0.85 `d27af6ab…`、α 0.70 `58332c7c…`、α 0.50 `7893a092…`；同一 α 下的 `k` 臂与 `kh` 臂逐位共享骨干。在拉取的 `head.pt` 文件上本地校验：每个 `k` 头都与 SFT 头完全一致（最大 |Δ| 0），每个 `kh` 头都等于 α · SFT + (1 − α) · Kev-27B 的 fp32 精确值，且 `head.pt["interpolation"]` 与 `interpolation.json` 以及两个端点头哈希一致。

| criterion | k-w85 | k-w70 | k-w50 | kh-w85 | kh-w70 | kh-w50 |
|---|---|---|---|---|---|---|
| T (pool, 648) [90 % CI] | 1.320 [1.203, 1.447] | 1.203 [1.097, 1.320] | 1.047 [0.955, 1.149] | 0.955 [0.871, 1.047] | 0.660 [0.602, 0.724] | 0.536 [0.489, 0.588] |
| 1 breadth acc, lower > 0 (2475) | +1.5 [+0.6, +2.4] | +1.5 [+0.6, +2.2] | +1.3 [+0.5, +2.0] | +1.6 [+0.7, +2.5] | +1.3 [+0.4, +2.1] | +1.7 [+0.9, +2.4] |
| 1 tasksource-heldout acc, lower > 0 (1993) | +4.2 [+2.5, +5.8] | +3.7 [+2.2, +5.3] | +3.3 [+1.9, +4.7] | +4.0 [+2.4, +5.6] | +3.8 [+2.3, +5.4] | +3.6 [+2.2, +4.9] |
| 1 Kev panel acc, lower ≥ −1 (3351) | +8.1 [+7.0, +9.4] | +8.4 [+7.4, +9.6] | +7.5 [+6.5, +8.6] | +8.1 [+7.0, +9.4] | +8.4 [+7.3, +9.6] | +7.6 [+6.6, +8.7] |
| 2 short acc, lower ≥ −2 (1586) | −0.9 [−1.95, +0.1] | −0.9 [−1.95, +0.0] | −0.8 [−1.7, +0.0] | −0.9 [−1.9, +0.1] | −0.8 [−1.8, +0.2] | −0.5 [−1.4, +0.4] |
| 2 short Brier, upper ≤ +0.02 | −0.000 [−0.009, +0.009] | +0.000 [−0.008, +0.008] | +0.000 [−0.007, +0.009] | −0.001 [−0.009, +0.008] | −0.001 [−0.009, +0.008] | −0.001 [−0.008, +0.007] |
| 2 short confident errors, upper ≤ +1 | −1.1 [−1.8, −0.4] | −0.5 [−1.1, +0.1] | −0.2 [−0.8, +0.3] | −0.9 [−1.7, −0.3] | −0.4 [−1.0, +0.2] | −0.1 [−0.7, +0.4] |
| 2 CUAD acc, lower ≥ −2 (2254) | +0.8 [−0.2, +1.8] | +0.7 [−0.1, +1.6] | +0.6 [+0.0, +1.4] | +0.8 [−0.2, +1.8] | +0.7 [−0.1, +1.6] | +0.6 [−0.1, +1.4] |
| 2 CUAD 16k+ acc, cand − parent ≥ −2 | 0.839 vs 0.837 | 0.840 vs 0.837 | 0.840 vs 0.837 | 0.839 vs 0.837 | 0.840 vs 0.837 | 0.841 vs 0.837 |
| 2 unknowable share ≤ 0.05 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| 3 breadth ECE ≤ 0.0176 (Kev-27B 0.0076) | 0.0103 | 0.0156 | 0.0195 **fail** | 0.0117 | 0.0159 | 0.0136 |
| 3 Kev-panel ECE ≤ 0.0327 (Kev-27B 0.0227) | 0.0146 | 0.0151 | 0.0189 | 0.0115 | 0.0150 | 0.0258 |
| 3 tasksource-heldout ECE ≤ 0.0523 (Kev-27B 0.0423) | 0.0432 | 0.0315 | 0.0311 | 0.0401 | 0.0306 | 0.0358 |
| rank score (Δ breadth + Δ tsheld + Δ Kev, pp) | +13.8 | +13.6 | +12.1 | +13.7 | +13.5 | +12.8 |
| verdict | **PASS** | **PASS** | fail | **PASS** | **PASS** | **PASS** |

最接近边界的情形：`27b-k-w85` 和 `27b-k-w70` 的 short-state 准确率下界为 −1.95 pp，相对 −2（与第 24 轮中第 22 轮最终结果的同一 −1.95 相同），以及 `27b-k-w70` 的 breadth ECE 0.0156。

**仅报告面板**（相对 Kev-27B 的成对 delta；标注处 ECE 为绝对值）：

| panel | k-w85 | k-w70 | k-w50 | kh-w85 | kh-w70 | kh-w50 |
|---|---|---|---|---|---|---|
| breadth, all 14 sources, acc (3075) | +1.2 [+0.3, +2.2] | +1.1 [+0.3, +2.1] | +1.1 [+0.3, +1.8] | +1.2 [+0.3, +2.2] | +1.1 [+0.2, +2.0] | +1.5 [+0.7, +2.2] |
| breadth cfcolor+humicroedit+chessbench, acc (450) | −1.1 [−5.1, +2.9] | −0.7 [−4.2, +2.9] | +0.2 [−2.7, +3.1] | −1.1 [−5.1, +2.7] | −0.4 [−4.0, +2.9] | +0.2 [−2.4, +2.9] |
| tasksource-heldout all 24 families, acc (2788) | +3.9 [+2.6, +5.3] | +3.7 [+2.5, +5.0] | +3.4 [+2.2, +4.5] | +3.8 [+2.4, +5.1] | +3.7 [+2.5, +5.0] | +3.3 [+2.2, +4.4] |
| hard-v1 acc (1083) | +17.9 [+15.3, +20.8] | +18.1 [+15.5, +20.8] | +16.1 [+13.5, +18.9] | +17.8 [+15.2, +20.7] | +18.1 [+15.5, +20.9] | +16.0 [+13.4, +18.8] |
| Kev panel without hard-v1, acc (2268) | +3.5 [+2.3, +4.7] | +3.8 [+2.7, +4.9] | +3.5 [+2.5, +4.5] | +3.5 [+2.4, +4.7] | +3.7 [+2.7, +4.8] | +3.6 [+2.6, +4.6] |
| SemIf acc (144) | −0.7 [−3.5, +2.1] | −1.4 [−4.2, +1.4] | +0.0 [−2.8, +2.8] | −0.7 [−3.5, +2.1] | −1.4 [−4.2, +1.4] | +0.0 [−2.8, +2.8] |
| WANLI-v2 acc (1002) | +1.2 [−0.7, +3.0] | +1.7 [+0.0, +3.4] | +2.3 [+0.9, +3.7] | +1.2 [−0.7, +3.0] | +1.8 [+0.1, +3.5] | +2.3 [+0.9, +3.7] |
| TypeSafe acc (89) | −1.1 [−5.1, +2.5] | −1.1 [−5.1, +2.5] | +0.0 [−3.4, +3.2] | −1.1 [−5.1, +2.5] | −1.1 [−5.1, +2.5] | +0.0 [−3.4, +3.2] |
| ood-v2 acc (4988) | +1.2 [+0.7, +1.8] | +1.3 [+0.8, +1.8] | +1.1 [+0.6, +1.5] | +1.2 [+0.7, +1.7] | +1.3 [+0.8, +1.8] | +1.1 [+0.7, +1.5] |
| agents-ood-v1 acc (2084) | +2.1 [+1.4, +2.8] | +2.1 [+1.4, +2.8] | +1.6 [+1.0, +2.3] | +2.1 [+1.4, +2.8] | +2.1 [+1.4, +2.8] | +1.6 [+1.0, +2.2] |
| guardrails-ood-v1 acc (4949) | +4.0 [+3.4, +4.6] | +3.8 [+3.2, +4.5] | +3.7 [+3.1, +4.3] | +4.0 [+3.4, +4.7] | +3.9 [+3.3, +4.6] | +3.7 [+3.1, +4.3] |
| ood-v2 ECE Δ | −0.024 [−0.029, −0.018] | −0.023 [−0.028, −0.018] | −0.022 [−0.027, −0.017] | −0.025 [−0.030, −0.019] | −0.022 [−0.027, −0.017] | −0.016 [−0.020, −0.011] |
| agents-ood-v1 ECE Δ | −0.105 [−0.113, −0.097] | −0.101 [−0.109, −0.093] | −0.092 [−0.098, −0.084] | −0.105 [−0.113, −0.097] | −0.099 [−0.107, −0.091] | −0.080 [−0.087, −0.072] |
| guardrails-ood-v1 ECE Δ | −0.069 [−0.074, −0.061] | −0.070 [−0.075, −0.063] | −0.066 [−0.071, −0.058] | −0.069 [−0.074, −0.062] | −0.069 [−0.074, −0.061] | −0.060 [−0.065, −0.052] |
| breadth ECE Δ (gated panel) | +0.003 [−0.008, +0.013] | +0.008 [−0.007, +0.015] | +0.012 [−0.005, +0.017] | +0.004 [−0.008, +0.014] | +0.008 [−0.006, +0.017] | +0.006 [−0.008, +0.013] |
| Kev ECE Δ | −0.008 [−0.021, +0.004] | −0.008 [−0.019, +0.003] | −0.004 [−0.017, +0.007] | −0.011 [−0.022, +0.002] | −0.008 [−0.019, +0.003] | +0.003 [−0.009, +0.013] |
| tsheld ECE Δ | +0.001 [−0.019, +0.020] | −0.011 [−0.029, +0.007] | −0.011 [−0.026, +0.006] | −0.002 [−0.022, +0.016] | −0.012 [−0.029, +0.006] | −0.006 [−0.021, +0.012] |
| CUAD ECE (Kev-27B 0.063) | 0.097 | 0.095 | 0.096 | 0.097 | 0.097 | 0.089 |
| CUAD ECE 16k+ (Kev-27B 0.071) | 0.102 | 0.100 | 0.100 | 0.102 | 0.101 | 0.099 |
| longdoc generated acc / ECE | 1.000 / 0.001 | 1.000 / 0.001 | 1.000 / 0.002 | 1.000 / 0.001 | 1.000 / 0.002 | 1.000 / 0.004 |
| short-state acc, candidate / Kev-27B | 0.8947 / 0.9042 | 0.8947 / 0.9042 | 0.8960 / 0.9042 | 0.8953 / 0.9042 | 0.8966 / 0.9042 | 0.8991 / 0.9042 |

**混合做了什么。** 几乎没做，即使在 α 0.50 时也是如此。每个候选读起来几乎都像第 22 轮的最终结果（第 24 轮：breadth +1.5、tasksource-heldout +4.1、Kev +7.9、short −0.9 [−2.0, +0.2]、CUAD ECE 16k+ 0.102）。混合本应挽回的两件事几乎没有动。使用混合头时，short-state 准确率在 α 0.50 下从 −0.9 变为 −0.5 pp。CUAD ECE 从 0.097（α 0.85）变为 0.089（α 0.50，混合头），相对于 Kev-27B 的 0.063；在 16k+ 处仍维持在 0.099–0.102，而 Kev-27B 为 0.071。Kev-27B 一半的权重几乎没能找回它的 short-state 或合同文档行为。准确率增益大体上在混合中保留了下来（hard-v1 +16 至 +18 pp，agents-ood 和 guardrails-ood 不变）。混合头需要低得多的温度（α 下降时 0.955 → 0.536，而使用 SFT 头时是 1.320 → 1.047）：对不同骨干上训练出的两个头取平均会缩小指针 logits。合并 T 重新校准了这一点，且同一 α 下的 `kh` 与 `k` 臂在每个受控准确率面板上彼此相差在 0.4 pp 以内。

**偏差。** (i) App 名称：未使用 spec 中的 `"app": "kev-sft"`。插值以 `KEV_APP_NAME=kev-r23` 运行。读取通过一个包装器进行，该包装器在 spec 的内存副本上调用 `kev.rounds.launch_arm_reads`，其中 `app = kev-r23`：相同的 `read_commands`、相同的启动记录 `runs/r23-reads-<arm>.json` 和相同的每臂锁。spec 文件未改动。(ii) 登记要求一次一个候选。从 12:40Z 起，按 Jared 加快进度的指示，两个候选的读取同时在进行：`27b-kh-w85` 在 `27b-k-w85` 的读取仍在运行时启动，此后每批在新的一个落地时开始。每次启动仍先读取计量成本，且都低于门限（计量值 + $80 < $4,099.04）。启动时间和读取记录在启动记录及下文中。(iii) 工具按 spec 所列对每个候选计数 16 次读取（运行请求说的是 17 次）。

**支出。** 计量值（Modal，workspace 范围）：$3,787.06（插值前），随后在首次读取启动时 $3,782.91（向下修订）。每次启动前的后续读数：$3,806.93、$3,842.55、$3,871.84、$3,887.04 和 $3,922.27。最后一次读取落地后为 $3,961.81（2026-09-28T20:30Z）。截至目前，规则阶段计量花费约 $175，未计计量滞后。

**证据**（已提交）：读出、其表格和启动记录；每个候选的 `interpolation.json`；公开套件读取 `runs/r23-27b-<arm>-<tag>`（报告 + 行；OOD 读取：仅报告）。私有（`jaredpalmer/kev-private-train`，位于 `runs/r23/`，`runs/r23-readout/private-rows.json` @ `4e8c117e`，`scripts/private_rows.py restore`）：六次 tasksource-heldout-v1 读取（行与报告）以及 ood / agents-ood / guardrails-ood 行（30 个文件）。

**下一步。** 对 `27b-k-w85` 进行已登记的确认，每次读取一次。测试阶段：候选测试读取写入 `runs/r23c-27b-cand-<tag>`，Kev-27B 一侧复用第 24 轮。然后是锁定阶段（`kev-27b-r23-ungated`）、bf16 服务检查和发布温度。与第 24 轮相同的注意事项适用：候选的 short-state 开发读取是第 22 轮最终结果的，距锁定阈值差 2 道题。

### 第 23 轮确认

**已确认，附带已登记的注意事项。** `27b-k-w85` 通过了两个阶段。它在全部三项准则上通过测试阶段，并在两项上通过锁定阶段。锁定的 transfer-v4 准确率为 **0.8887（656 题中 583 题）**，相对阈值 0.886（需要 582 题），因此以 **1 题**之差通过。Kev-27B 在同一读取上得分为 0.8963（588），第 22 轮最终结果在第 24 轮中得分为 0.8841（580）。测试划分和锁定读取是 round 24 读取的那批，本轮的设计针对该确认做了调整（见上文"测试划分的复用"）。此处的通过比第 24 轮的读取本可提供的证据更弱，而发布决定权在 Jared。未发布任何内容。每次确认读取只做一次，且只针对具名候选。判定：`runs/r23-verdict/27b-tests.json` 和 `runs/r23-verdict/27b-locked.json`（`python -m kev.rounds confirm experiments/rounds/r23.json --stage {tests,locked} --arm 27b-k-w85`）。候选以其池拟合值 1.320（648 题）提供服务，Kev-27B 以其发布的 1.382 提供服务。Kev-27B 的测试侧是第 24 轮的读取（`runs/r24c-27b-parent-<tag>`），未再读取。Delta 为相对 Kev-27B 的成对记录聚类自助法（2,000 次重采样，seed 0，micro），以 pp 计。

| stage / criterion (panel, n) | 27b-k-w85 | Kev-27B | Δ [95 %] | verdict |
|---|---|---|---|---|
| tests: breadth-v1 test acc, lower > 0 (without `routerbench`, `cfcolor`, `humicroedit`, `chessbench`; 2,489, 600 out) | 0.832 | 0.820 | +1.2 [+0.3, +2.2] | pass |
| tests: tasksource-heldout-v1 test acc, lower > 0 (without the seven families; 2,024, 809 out) | 0.795 | 0.743 | +5.3 [+3.7, +6.8] | pass |
| tests: pooled hard-v1 + devtools-v1 (without `flakeflagger`, `commitpackft_type`) + documents-v1 test acc, lower ≥ −1 (2,795, 300 out) | 0.889 | 0.800 | +8.9 [+7.5, +10.3] | pass |
| **locked: transfer-v4 locked acc ≥ 0.886 (656)** | **0.8887 (583)** | 0.8963 (588) | −0.8 [−2.0, +0.5] | **pass** (needed 582) |
| locked: served Brier ≤ 0.165 (656) | 0.1537 | 0.1604 | −0.007 [−0.018, +0.004] | pass |

**仅报告的测试读取**（相同排除项；ECE 按提供时给出）：

| panel (n) | 27b-k-w85 | Kev-27B | Δ [95 %] |
|---|---|---|---|
| hard-v1 test (1,088) | 0.918 | 0.749 | +16.9 [+14.2, +19.8] |
| devtools-v1 test, gated sources (771) | 0.825 | 0.789 | +3.6 [+1.3, +5.9] |
| documents-v1 test (936) | 0.908 | 0.869 | +4.0 [+2.1, +5.9] |
| documents-v2, private held-out test (953) | 0.921 | 0.881 | +4.0 [+2.0, +6.1] |
| breadth-v1 test, all 14 sources (3,089); ECE | 0.757; 0.019 | 0.749; 0.019 | +0.8 [−0.1, +1.8] |
| breadth-v1 test ECE, gated panel | 0.015 | 0.013 | - |
| tasksource-heldout-v1 test ECE, gated panel | 0.049 | 0.051 | - |
| longdoc-v1 test CUAD acc (2,194) | 0.874 | 0.890 | **−1.6 [−3.0, −0.3]** |
| longdoc-v1 test CUAD ECE | **0.053** | 0.007 | - |
| CUAD by length, acc / ECE: < 8k (867) | 0.874 / 0.059 | 0.900 / 0.025 | - |
| 8k-16k (443) | 0.880 / 0.052 | 0.892 / 0.028 | - |
| 16k-32k (442) | 0.873 / 0.061 | 0.882 / 0.019 | - |
| 32k-64k (442) | 0.867 / 0.060 | 0.876 / 0.014 | - |
| 16k+ (884) | 0.870 / 0.059 | 0.879 / 0.013 | - |
| longdoc-v1 test generated (2,400); ECE | 1.000; 0.001 | 1.000; 0.014 | - |
| decision-v7 locked test acc (1,200; read by `locked_test`, not a criterion) | 0.866 | 0.870 | - |

相对于第 22 轮最终结果在相同划分上的表现（第 24 轮的确认），混合在各处都处在噪声范围内。在 breadth-v1 测试（+1.2 对比相对 Kev-27B 的 +1.5）和 breadth 指数上略低。在合并面板（+8.9 对比 +8.6）和锁定 transfer-v4（583 对比 580）上略高。CUAD 测试仍劣于 Kev-27B：−1.6 [−3.0, −0.3] 对比第 22 轮的 −1.8，ECE 0.053 对比 0.055。开发规则的 CUAD 保护（下界 ≥ −2 pp）在测试上不成立（−3.0）。这在本阶段仅为报告内容，不改变任何判定。这是第 24 轮发现的合同领域校准偏差，而混合并未修复它。

**测试上的 breadth 指数**（机会校正，全部 14 个来源；`scripts/breadth_report.py --bootstrap 2000`，`runs/r23-breadth-report/report.md`；候选的行以 1.320 提供服务，Kev-27B、Jev 和 AutoJev 的行按第 24 轮的读取，均不再读取）：候选 **52.3 [49.2, 55.4]**，Kev-27B 50.2 [47.0, 53.2]，第 22 轮最终结果 53.7 [50.5, 56.7]（以 1.382 提供；这精确复现了第 24 轮的报告），Jev 54.0 [51.2, 57.0]，AutoJev 50.0 [47.0, 53.3]。相对 Kev-27B，候选为 +2.1 [−0.4, +4.6]；第 22 轮最终结果为 +3.5 [+1.0, +6.0]。合并 ECE：候选 0.019，Kev-27B 0.019。候选的提升来自 Retrieval & Classification（69.0 对比 61.6）和 Knowledge & Reasoning（33.8 对比 31.7）。它回吐了 Tools & Automation（62.9 对比 65.1）。

**温度区间两端的校准**（仅报告，如第 24 轮：候选在其合并 T 的 90 % 区间 [1.203, 1.447] 两端以及点拟合处，Kev-27B 在 1.382；`runs/r23-verdict/27b-tests-t-interval.json`）。ECE / Brier：

| test panel (n) | T 1.203 | T 1.320 (served) | T 1.447 | Kev-27B @ 1.382 |
|---|---|---|---|---|
| breadth-v1, gated (2,489) | 0.026 / 0.2358 | 0.015 / 0.2347 | 0.021 / 0.2346 | 0.013 / 0.2516 |
| breadth-v1, all 14 (3,089) | 0.029 / 0.3130 | 0.019 / 0.3120 | 0.020 / 0.3118 | 0.019 / 0.3267 |
| tasksource-heldout-v1, gated (2,024) | 0.034 / 0.2970 | 0.049 / 0.2998 | 0.067 / 0.3038 | 0.051 / 0.3682 |
| pooled hard + devtools + documents-v1 (2,795) | 0.019 / 0.1578 | 0.014 / 0.1584 | 0.024 / 0.1596 | 0.027 / 0.2720 |

第 24 轮的模式成立。在低温度端 breadth ECE 升至 0.026，在高温度端 tasksource-heldout ECE 升至 0.067。两者朝相反方向拉动，Brier 最多变动 0.004。

**服务检查**（bf16，H200；通过；`runs/serving-27b-r23/report.json`、`runs/serving-27b-r23-long/report.json`）：
- 短状态，280 题：
  - CUDA graphs 对比 fp32：最大 |Δp| 0.0223，0 翻转。Eager bf16 对比 fp32：0.0216，0 翻转。阈值：≤ 0.03、≤ 1 翻转。
  - Graphs 对比 eager：0.0270，0 翻转。按服务方式的题目隔离：0.0039，0 翻转。
- 长状态，服务对比基准，每个长度 3 条记录 / 15 题：
  - 8k：最大 |Δp| 0.0064，0 翻转；新状态 1.37 s，缓存 599 ms；峰值 70 GB。
  - 32k：0.0095，0 翻转；4.17 s / 630 ms；79 GB。
  - 64k：0.0017，0 翻转；9.41 s / 733 ms；87 GB。

**发布温度**（在 `head.pt` 的副本上；卷上的 checkpoint 未改动）：`scripts/calibrate_checkpoint.py --rows <r3cal rows>:composition_holdout,emotion,legacy_holdout,mmlu,paws,qnli,sciq,tweet_offensive --rows <v9 rows>:mmlu_pro --exclude_rows <transfer4 rows>` 给出 **1.3195**，即读出的池拟合值。其 90 % 区间为 [1.203, 1.447]（648 题；（source, group）簇在每个 source 内重采样，2,000 次重采样，seed 0）。在拟合行上，ECE 由 0.048 → 0.034。折外估计（5 个组不相交折，折 T 1.26–1.35）为 0.038 [0.028, 0.068]，与原始值未分离。transfer-v4 开发（已报告，未拟合）：ECE 0.058 → 0.038。该拟合将池与 SFT `head.pt` 所记录的训练（sft-v2-r22 及其组件）进行核对。Kev-27B 的 decision-v7 / b1v2 由 `kev.rounds validate` 核对（各臂的 `trained_on`）。

**偏差。** (i) 锁定读取于 20:38Z 启动，即测试阶段读取（20:37Z）后约 1 分钟。两者都在结果提交 `cc5f346`（20:37Z）之后启动，且锁定读取（20:43Z）在测试判定之前完成。第 24 轮做了同样的事，且 Jared 要求加快进度。两个判定互不依赖，且没有读取被重复。(ii) Modal app：锁定读取在一个新的部署 `kev-r23`（来自 `cc5f346`，`KEV_GPU=H200`）上运行，完成后即停止。测试读取和服务检查作为临时 `kev-r23` app 运行。`kev-sft` 未触碰。(iii) tasksource-heldout 测试行在启动器拉取之前已由另一个客户端下载，因此启动器自身的拉取拒绝覆盖它们。本地行与卷副本逐字节相同（sha256 `871e05bd…`）。

**支出。** Modal 计量值，workspace 范围：2026-09-28T23:14Z 时为 $3,977.18，即所有第 23 轮作业结束后。这比插值前读取的 $3,787.06（未计计量滞后）高出 $190.12，且在已登记的预测范围内（规则阶段约 $175；确认约 $15，阈值 $213.02）。AI Gateway：$0（Jev 和 AutoJev 的 breadth-v1 测试读取是第 24 轮的）。

**证据**（已提交）：判定和 T 区间表（`runs/r23-verdict/`）；启动记录（`runs/r23-reads-27b-k-w85-{tests,locked}.json`）；公开测试读取（`runs/r23c-27b-cand-<tag>`：hard-v1、devtools-v1 和 documents-v1 的行，breadth-v1、documents-v2 和 longdoc-v1 的报告）；锁定读取（`runs/locked/kev-27b-r23-ungated/`）；测试 breadth 报告（`runs/r23-breadth-report/`）；服务报告。私有（`jaredpalmer/kev-private-train`，位于 `runs/r23/`，`scripts/private_rows.py restore`）：tasksource-heldout-v1 测试行与报告、breadth-v1 测试行和 documents-v2 行（`runs/r23-verdict/private-rows.json`，@ `bab8219f`），以及 longdoc-v1 测试行（`runs/r23-verdict/private-rows-longdoc.json`，@ `ebf2b333`）。

**给 Jared。** `27b-k-w85`（`/runs/r23-wise/27b-k-w85/checkpoint`，权重 `d27af6ab…`）是第一个通过已登记确认的 27B 全权重 checkpoint。它尚未发布。如果发布，将以 T 1.3195 发布，用 `scripts/calibrate_checkpoint.py` 写入已发布的 `head.pt`。有四点值得权衡：
- 它仅以 1 题之差通过锁定阈值，比 Kev-27B 低 0.8 pp；
- 在 CUAD 测试上更差（−1.6 pp，ECE 0.053 对比 0.007）；
- 测试划分对本题并非未触及；
- 它仍是第 22 轮最终结果的 0.85，且混合几乎没能挽回 Kev-27B 的 short-state 或 CUAD 行为（"混合做了什么"）。

## 已发布：Kev-27B v2（2026-09-30）

Jared 于 2026-09-30 批准发布。Kev-27B v2（第 23 轮的 `27b-k-w85`，内部 id `kev-27b-r23`）现在是 `jaredpalmer/kev-27b` 的 main，公开的；v1（B1 v2 LoRA 适配器）的标签为 `v1-lora`。记录：`runs/release/kev-27b-r23-published.json`。

- **v1 优先。** 在任何上传之前，仓库的 main 经核为 `01b81998…` 并打上标签 `v1-lora`（带注释的标签对象 `512eeb74…`），对匿名客户端解析为 `01b81998`。
- **上传。** `modal_app.py::release_publish --public --confirm-public jaredpalmer/kev-27b --replace`（一个 CPU 容器，app `kev-release`；私有默认保留，且 `--public` 需要仓库名写两次）在 `/runs/release/kev-27b-r23/checkpoint` 上运行 `kev.publish`：提交 **`28be62e9`**。`kev.publish --replace`（新增）会删除上传在同一提交中未携带的每个文件（`upload_folder(delete_patterns="*")`），因此 v1 的 `adapter_config.json`、`adapter_model.safetensors`、`result.json`、`provenance.json`、`train.log`、`training_config.json` 和 `training_metrics.json` 被放入添加分片的那个提交中；若没有 `--replace`，向持有适配器的仓库进行全权重上传现已被拒绝，因为加载器规则会选择适配器。Hub 的 LFS 哈希给出的权重为 `d27af6ab…`，`head.pt` 为 `7968f17b…`，即发布副本的。模型卡元数据：`base_model: Qwen/Qwen3.8-27B`、`base_model_relation: finetune`、`library_name: transformers`。模型卡在没有验证行的情况下先上传了，验证行在下方的检查之后通过一个仅 README 的提交添加（`0d7f9b49`，自此为 main）。
- **匿名验证。** `modal_app.py::release_verify`（新增）：一台没有 Modal secret、没有 `kev-hf-cache` 卷、全新 `HF_HOME` 且无 token 的 H200（`get_token()` 在每个作业中均为 None）。`jaredpalmer/kev-27b` 解析为 T 1.3195 下的全权重布局，权重 `d27af6ab…`。提供的读取逐行复现了第 23 轮的读取：semif-v1 的 252/252 行和 transfer-v4 开发的 764/764 行，其 logits 与已提交的原始 logits 乘以 fp32(1/T) 逐位相等（`scripts/compare_release_rows.py`）。对 v2 的首次 decision-v7 开发读取（仅报告；README 的 trained-sources 单元格）得分为 0.865（v1 为 0.866）。`jaredpalmer/kev-27b@v1-lora` 解析为 v1 的适配器（`41bf5af0…`），在 T 1.3819 下并以 argmax 在 252/252 行上与 2026-09-23 的读取相等；其 logits 与该读取并非逐位相同（最大 |Δp| 0.032）。原因是 causal-conv1d 的 CUDA 内核，#125 在该读取之后将其加入 Modal 镜像；不涉及 kev 的代码（`runs/drift-v1/REPORT.md`）。行与报告：`runs/rel27-public/`。
- **文档。** `docs/model-cards/kev-27b.md` 现在是 v2 的模型卡（即候选模型卡，去掉候选措辞，并带有针对 `@v1-lora` 的"Previous version"说明；保留每一条限制和事后注意事项）；`kev-27b-v2.md` 已移除。README（Models 行、文本、来自 `runs/serving-27b-r23` 的 Serving H200 行）、家族图、kev-deploy 的 GPU 说明和 `docs/claims.json` 一并更新。集合已列出 `jaredpalmer/kev-27b`。Space 提供 4B / 0.8B，未改动。GitHub release `kev-family`：移除了 `kev-27b.tar.gz`（v1 的适配器），为其余三个 tarball 重新生成了 `SHA256SUMS.txt`（每个都重新验证），并更新了说明（v2 仅在 Hub 上：51 GB 超过了 2 GB 资源限制）。
- **支出。** Modal 计量值在上传前的 2026-09-30T17:49Z 为 $4,574.06，在上传及验证后的 18:23Z 为 $4,575.82（计量存在滞后；app `kev-release`：一次 CPU 上传、一个约 40 分钟的 H200 容器，外加一次约 10 分钟的首尝试，在加载后因已存在的输出目录而失败）。

### 发布候选（2026-09-28，私有；暂存记录）

第 23 轮已确认的候选 `27b-k-w85` 被暂存为**私有**发布候选 **Kev-27B v2**，供 Jared 审阅（2026-09-28）。没有任何公开内容：无公开仓库或修订、无公开模型卡、无 README、Space 或集合变更，无 GitHub release。Kev-27B（`jaredpalmer/kev-27b@01b81998`）保持为已发布的 27B 模型，直至 Jared 决定。内部发布 id 为 `kev-27b-r23`，因为 `kev-27b-v2` 已经命名了已发布 Kev-27B 的记录（B1 v2：`experiments/releases/kev-27b-v2.json`、`runs/release/kev-27b-v2.json`、卷上的 `/runs/release/kev-27b-v2`）。记录：`runs/release/kev-27b-r23-staging.json`。

- **卷副本。** `modal_app.py::release_copy`（新增；`scripts/release_checkpoint.py`，一个 CPU 容器，app `kev-release`）将 `/runs/r23-wise/27b-k-w85/checkpoint` 复制到 `/runs/release/kev-27b-r23/checkpoint`。它拒绝已存在的目标。副本的权重 sha256 与源相同，为 `d27af6ab…`（本轮的 `interpolation.json`）：11 个分片、17 个文件、51.3 GB。源未改动；其 `head.pt` 在 T 1.0 下仍为 `1a62fa3b…`。
- **发布温度。** `scripts/calibrate_checkpoint.py` 在副本的 `head.pt` 上拟合 T（拉取、拟合、放回），使用本轮已登记的池行：`r3cal` 限制为其八个来源，`v9` 限制为 `mmlu_pro`，并排除 `transfer4` 记录，共 648 题。它未发现与训练冲突。它给出 **T 1.3195**，正是本轮的池拟合值。折外 ECE（5 个组不相交折）由 0.048 降至 0.038，且区间重叠。T 的 90 % 区间为 [1.20, 1.45]。写入的 `head.pt`（`7968f17b…`）与监控副本逐字节相同。
- **私有 Hub 候选。** `modal_app.py::release_publish`（新增；在 CPU 容器中 `kev.publish --private`，因此权重永远不会到达笔记本）将副本上传到 `jaredpalmer/kev-27b-v2-candidate`，提交 `0dd33bcc`。使用 `--private` 时，`kev.publish` 现在会创建缺失的私有仓库，并拒绝已存在的公开仓库（`kev.mirror.ensure_private`）。它还将全权重分片链接到其暂存目录，而不是复制 51 GB，并上传 `interpolation.json`。该仓库为私有。Hub 的 LFS 哈希给出相同的权重 sha256（`d27af6ab…`）和 `head.pt`（`7968f17b…`）。`base_model_relation: finetune`：每个权重都源自同一 base 的微调。Hub 的 `merge` 关系用于多个列出 base 模型的合并，而 Kev-27B 是同一 base 的适配器。
- **验证。** 从 Hub 的认证加载（`kev.checkpoint`、H200、`benchmarks --jobs jaredpalmer/kev-27b-v2-candidate@0dd33bcc@evals/external/semif-v1@rel27-hub-semif`）逐行复现了第 23 轮的 semif-v1 读取。全部 252 行都在 T 1.3195 下提供，且其 logits 与已提交的原始 logits 乘以 fp32(1/T) 逐位相等，因此骨干和头输出完全相同。argmax 在 252/252 行上相等。
- **模型卡与数字。** `docs/model-cards/kev-27b-v2.md`。每个数字都可追溯到 `docs/claims.json` 中已提交的报告：`runs/r23-verdict/`、`runs/r23-readout/round23.json`、`runs/r23-breadth-report/`、服务报告、`runs/release/kev-27b-r23.json` 以及暂存记录。`runs/release/kev-27b-r23.json` 来自 `scripts/release_numbers.py --release kev-27b-r23`；发布 spec 现在可以给一个臂一个已登记的 `pool` 而非 trial。四条已记录的发布从研究 checkout 的行逐字节复现。
- **长合同。** 仅报告的 longdoc-v1 测试读取在本项暂存期间落地，模型卡也收录了它（`runs/r23-verdict/27b-tests.json`、`longtest`）。CUAD 测试：0.874 对比 Kev-27B 的 0.890，−1.6 [−3.0, −0.3]。ECE 为 0.053 对比 0.007，且在每个长度桶中是 Kev-27B 的 2 至 4 倍。第 24 轮未混合的 SFT 为 −1.8，ECE 0.055，因此混合几乎没挽回多少。生成的 bundle 准确率为 1.000。
- **模型卡所述的注意事项。** 第 23 轮是在第 24 轮确认之后设计的，并在相同的测试和锁定划分上确认。短状态不优于 Kev-27B 的（锁定 −0.8 [−2.0, +0.5]；带 `emotion` 的 transfer-r3 测试 −2.1 [−3.5, −0.8]）。长合同更差且过度自信（见上文）。没有 scienthoon 读取（已移除），而 SFT 父模型在那里为 −5.5。hard-v1、devtools-v1 和 documents-v1 处于分布内。
- **待发布（Jared 决定）。**
  1. 在 `jaredpalmer/kev-27b` 上为 Kev-27B 的当前权重打标签（例如 `b1v2-release`）。
  2. 从容器将 `/runs/release/kev-27b-r23/checkpoint` 发布到该处，并将模型卡移至 `kev-27b.md`。
  3. 然后是 README、Space、集合以及 kev-deploy 的 GPU 列表。
- **支出。** Modal 计量值在本项工作前为 $3,971.71，在复制、上传和验证之后为 $3,977.37（workspace 范围，含其他 app）。App `kev-release`：CPU 复制与上传，外加一次约 10 分钟的 H200 读取。

## 第 25 轮（已登记）

### 第 25 轮 — 从 Kev-27B 继续全权重 SFT：带回放的 breadth，不含长文档族（随本 spec 的提交登记，写于任何第 25 轮训练或读取之前）

**为什么。** 迄今为止的每次全权重运行都从 base 出发，并随着训练推进而偏离 Kev-27B 擅长的部分。第 22 轮最终结果和第 23 轮的 `27b-k-w85` 在广泛意义上有所提升（tasksource-heldout 测试 +5.3、breadth +1.2 至 +1.5），但在短状态上回退（锁定的 transfer-v4 相对 Kev-27B 为 −0.8 至 −1.2 pp），在长合同上也回退（CUAD 测试 −1.6 至 −1.8），而朝 Kev-27B 混合几乎没有改变这两者（"第 23 轮结果"）。第 25 轮**从 Kev-27B 出发**（其 LoRA 合并入全权重，并带其头），并通过回放 Kev-27B 自身的训练数据来补充 breadth。两个假设塑造了数据：(i) 回放能保持短状态技能；(ii) 长文档族（longify、longdoc）驱动了 CUAD 回退，而由于 Kev-27B 已经能泛化到 64k 状态，它们被排除，状态上限设为 16k。

**初始化 checkpoint。** `kev-runs` 卷上的 `/runs/r25-init/kev-27b-merged/checkpoint`：Kev-27B（`jaredpalmer/kev-27b@01b81998`、`r6-27b-v2/01-trial-1`），其 rank-16 LoRA 已合并入 bf16 骨干，并加上其指针头。它是单独生成的，在登记时尚不存在。`kev.train --init_from` 在加载任何内容之前，会比较 `base`、`base_revision`、`lora` (0)、`head_dim` (256)、`option_isolation`、`special_embeddings` 和 `weights`（"full"），并在每个 trial 的 provenance 中记录权重和头的 sha256。读出将每个候选与按服务方式提供的 Kev-27B（下文的父读取）比较，而非与合并后的 checkpoint 比较。

**数据**（私有；仅本仓库中有 manifest）。`evals/sft-v2-r25`（kev-private-train @ `1c855ff9`、`sft-v2-r25/`；由 kev-sft `assemble-r25` @ `c8644ef`、`assemble/derive_r25.py` 构建，确定性：第二次运行写出相同字节）。每条记录都是一条 `sft-v2-r22` 记录，未改动，保持 sft-v2-r22 的顺序；无新记录或标签。筛选：
1. 组件，按每条记录的来源：保留 tasksource-v1、tone、guardrails-pii、guardrails-grounding、injection、ood、agents、**b1v2**（Kev-27B 自身的训练数据，即回放）以及 sft-v1 的其他 Kev 组件（hard-v1、devtools-v1、documents-v1）。丢弃 longify 和 longdoc（假设 (ii)），以及 sft-v1 的 public 和 synthetic-v1 来源（不在此混合中）。
2. 用 sft-v2 的规则（kev-sft `assemble/screen_v2.py`）针对今天的 105 个评估划分再次筛选（76,207 个参考项：每个 Kev 套件、私有评估镜像、JevBench public）。**0 条记录**违规。
3. 训练状态最多 16,384 个 token（Kev-27B tokenizer），每条都检查是否适配 `training_context(16384)`；1,437 条超出上限的记录被剔除（1,161 agents、188 grounding、84 injection、4 tasksource）。校准和开发使用 sft-v2-r22 的（状态 ≤ 8,192），并限制为保留的组件，仅做筛选：kev.experiment 的在 trial 温度与开发得分，没有任何准则读取它们。
4. 训练进行下采样，使一个 epoch 适配一次 4 小时尝试（见预算）；每条按最小的 sha256(seed:keep:<component>: + record digest)：

| component | available (after 1-3) | kept | rule | state tokens | questions |
|---|---|---|---|---|---|
| **b1v2 (replay)** | 13,763 | **13,763 (30.2 % of records)** | all | 2.03M | 16,788 |
| tasksource-v1 | 23,996 (round 22's 24,000, 119 families) | 13,000 (all 119 families) | stratified by family, floors then largest remainders (family list private) | 1.82M | 17,757 |
| tone | 7,544 | 3,772 | half of each source | 0.61M | 15,874 |
| guardrails-pii | 4,152 | 2,076 | half | 1.72M | 5,329 |
| guardrails-grounding | 5,467 | 2,734 | half | 5.50M | 12,587 |
| injection | 2,615 | 1,308 | half | 2.07M | 5,519 |
| ood | 7,312 | 3,656 | half | 2.94M | 11,019 |
| agents (≤ 16k) | 3,714 | 371 | a tenth | 3.32M | 1,719 |
| hard-v1 / devtools-v1 / documents-v1 | 19,345 | 4,835 | a quarter of each source | 2.70M | 6,966 |
| **total** | | **45,515** | | **22.70M** (28.53M row tokens with the state shared) | **93,558** (3,417 soft) |

状态 token：中位数 120、均值 499、p90 1,164、p99 7,130、最大 16,365；≤256 30,896 · 257–512 4,662 · 513–1k 4,390 · 1k–2k 3,792 · 2k–4k 798 · 4k–8k 570 · 8k–16k 407。校准 4,904 条、开发 2,714 条记录。没有公开文件命名 tasksource 族。

超出大纲的选择，每一项都有所述理由：
- **b1v2 是筛选后的副本**（其 15,401 条记录中的 13,763 条）：sft-v1 / sft-v2 的筛选所移除的记录类似于评估项（其中多数为 b1v2 的长 v2 记录），因此回放它们会是在读取的近似副本上训练。
- **加入 hard-v1 / devtools-v1 / documents-v1 的四分之一。** 它们不是 Kev-27B 的训练数据。规则的主准则 `1_kev_lower_at_least_minus_1pp` 读取 transfer-v4 + hard-v1 + devtools-v1 + documents-v1 开发，其成对区间约 ±1.2 pp 宽，因此一个把这些 Kev-27B 表现好的套件丢掉的候选会无法通过它。第 22 轮在所有这些组件上训练（Kev 面板 +7.8）。没有它们，无论测试中的假设如何，本轮都可能无法通过该主准则。代价：4,835 条记录、约 0.25 小时。
- **新族取一半、agents 取十分之一**，而非全部；**13,000 条 tasksource 记录**，而非第 22 轮的 24,000。预算和 12 小时夜间窗口固定了一次约 4 小时的尝试（见下文），而 agents 轨迹（≤ 16k 时平均 8.9k token）、grounding 和 ood 占每条记录的大部分时间。回放占比（约 30 %）保持不变，各族的减半是均匀的。

**Epoch 时间，依据实测速率**（kev-sft `assemble/epoch_r25.py`、`assemble/manifests/sft-v2-r25.epoch_projection.json`）。对 kev.train 实际处理的精确计划（第 22 轮针对 `microbatch_plan` 校验过的 `balanced_runs` + 上限副本，8 个 rank、batch 8 × accum 2、`pass_tokens_max 40960`），套用第 22 轮的 pass-time 模型（每 GPU slot 1.55 s + 1.469 ×（每 1k 填充 token 0.478 s + 0.00282 s × 状态数 × 最长²），每 slot 取最慢的 rank 求和），作用于每条记录精确的 epoch-0 token 形状（seed 0、none pairs 在 0.25 处门限为 8,192：6,681 对配对记录）：**356 步、每 rank 712 个 micro-batch、最大 pass 25,590 token、2.22 小时（每步 22.5 s）**；锚定到第 22 轮实测的约 50 s/步（对比其预测的 58.6 s）时为 1.90 小时。快照在步 89 / 178 / 267。一次尝试：启动约 0.4 h + 训练 × 1.03（每小时恢复点）+ 在 trial 评分（4,904 + 2,714 + 656 条记录，每条 0.292 s）0.67 h = **3.36 小时**（锚定 3.02 小时），在 4 小时超时内。超时由 `kev.rounds watch` 从最后的恢复点继续，在台账的三次尝试范围内。

**臂**（spec `experiments/rounds/r25.json`、计划 `experiments/round25/`、app `kev-r25`）。两个研究并行，每个在 8 × H200 上一次 trial、`full_ft 1`、`init_from /runs/r25-init/kev-27b-merged/checkpoint`、`evals/sft-v2-r25` 一个 epoch、每步 128 条记录（`batch 8`、`accum 2`、`length_sort 1`、`pass_tokens_max 40960`）、bf16、`max_state 16384`、`p_none_pair 0.25` 配 `none_pair_max_state 8192`、seed 0、带 10 % 预热的 OneCycle：
- `r25-27b-lr1e6`：lr 1e-6。
- `r25-27b-lr2e6`：lr 2e-6（第 22 轮的学习率）。

两个臂的头 lr 均为 1e-5：第 22 轮的 1e-4 是针对从零训练的头；本头从已训练状态起步，而 1e-5 让它以骨干速率的 5–10 倍跟随移动的骨干。

计划：OneCycle 带 10 % 预热，即训练器唯一的计划，未改动。持续训练文献并未有力支持恒定学习率，以至于值得在关键路径上更换训练器。重新预热再重新衰减学习率、并配合回放，等价于在并集上重新训练（Ibrahim et al., 2024，"Simple and Scalable Strategies to Continually Pre-train LLMs"）。重新预热主要在高峰值速率下带来上游损失代价（Gupta et al., 2023，"Continual Pre-Training of Large Language Models: How to (re)warm your model?"），而此处峰值从 1/25 的起始点出发，仅为 1–2e-6。恒定或"无限"计划在后续会扩展训练时才划算，而本单 epoch 运行并非如此。衰减还意味着最终模型是经过退火的，快照是其训练较少的点，如第 22 轮。

候选：每个臂的快照（步 89 / 178 / 267，`/runs/r25-27b-lr{1e6,2e6}/00-trial-0/snapshots/step-00000NN/checkpoint`）及其最终 checkpoint，**共 8 个**（`27b-lr1e6-s25/s50/s75`、`27b-lr1e6`，lr2e6 同理）。每个臂都命名 `trained_on: [evals/sft-v2-r25, evals/round6/b1v2, evals/v7/decision-v7]`，因此池检查同时覆盖 Kev-27B 的训练和第 25 轮的训练（`validate` 沿 sft-v2-r25 → sft-v2-r22 → sft-v2 → sft-v1 及其组件）。

**规则、温度池、读取、父读取、读取超时、排除项与确认：第 24 轮经审计的规则，逐字沿用**（"第 24 轮（已登记）"；同第 23 轮重新登记）。spec 与 `r24.json` 仅在轮次编号、app、两个研究和八个臂，以及确认的候选读取路径（`runs/r25c-…`、`runs/locked/kev-{size}-r25-ungated/transfer`）上不同。父模型的测试读取是第 24 轮的（`runs/r24c-{size}-parent-{tag}`），是为 Kev-27B 做的。简言之：合并温度（transfer-r3 校准的八个留出来源 + transfer-v9 MMLU-Pro，减去 transfer 行）；主准则 breadth-v1（排除 4 个来源）和 tasksource-heldout-v1（排除审计的 7 个族）准确率下界 > 0、Kev 面板 ≥ −1 pp；保护项短状态（准确率 ≥ −2 pp、Brier ≤ +0.02、置信错误 ≤ +1 pp）、longdoc CUAD 全长度及 16k+ ≥ −2 pp、unknowable ≤ 0.05；三个 ECE 准则相对父模型 + 0.01；按 breadth、tasksource-heldout、Kev 的 delta 排名；可选报告面板同第 24 轮；然后是测试阶段（breadth-v1 和 tasksource-heldout-v1 测试下界 > 0，合并的 hard/devtools/documents-v1 测试 ≥ −1 pp）和锁定阶段（锁定的 transfer-v4 ≥ 0.886、提供的 Brier ≤ 0.165）。

**关于确认划分的坦诚注意事项。** 测试划分和锁定的 transfer-v4 集合已在第 22–24 轮中为其他模型（第 22 轮最终结果、第 24 轮候选、第 23 轮混合）读取过；尚无任何一次是为第 25 轮模型读取的。筛选仅使用开发读取，而确认每次只读取一次。阈值是在这些读取之前写下的，且是第 24 轮的。尽管如此，确认对本项目并非未触及；了解到早期候选离锁定阈值有多近（656 中 580 和 583，阈值为 582）塑造了本轮的设计。

**预算**（Jared 当晚授权：Modal +$2,000、计量上限 ≈ $5,980、12 小时墙钟）。计量读数 **2026-09-28T23:45Z 时为 $3,966.94**：余量 $2,013.06、储备约 $200（10 %），因此任何一次启动时准入上限与支出最多 **$1,813**。每次启动首先读取计量成本（docs/autoresearch.md 第 2 节）。

| item | admission bound | expected |
|---|---|---|
| study `r25-27b-lr1e6` (H200:8 at $41.17/h × 4 h × 3 attempts) | $494.00 | ~$138 (one attempt, 3.36 h; ~$124 anchored) |
| study `r25-27b-lr2e6` | $494.00 | ~$138 |
| reads of one candidate (16 reads × 4 h × $6.27/h) | $400.97 | ~$30 |
| reads of all 8 candidates | $400.97 each, spend-gated | ~$240 |
| confirmation, one candidate (tests stage 7 reads × $25.06; locked read at 4 h; serving check) | $175.43 + ~$25 + ~$6 | ~$25 |
| **peak at launch: both studies + one read batch** (+ ~$85 metered in the first hour) | **$1,389 + ~$85 ≈ $1,474** of $1,813 | |
| **projection at the end of the night** | | **~$4,510** (+$545; + whatever the init merge costs) |

为何尝试是 4 小时而非 8 小时：一个研究的边界计入三次尝试，因此 8 小时尝试（大纲允许的 6 小时 epoch）会把两个研究的边界定为 $1,976，占满当晚的全部余量，且在两个研究结束前无法开始任何读取。采用 4 小时尝试，从第一个快照起，一个候选的读取批次就能在两项研究旁边进行，且储备完好。两个批次同时进行（$802）会在第一小时的支出被计量后超出 $1,813。当研究结束时，其边界被释放，最多三个批次同时运行。

**墙钟计划**（t = 0 为启动时刻；模型时间，锚定者约早 15 %）：
- t ≈ 0–0.4 h：两个容器加载合并后的 27B 并统计 token。在最开始几分钟，检查日志中的 `none pairs: N of 45515 records` 和 `plan: 712 micro-batches per rank for 356 steps`（预测值；两个臂的数据与 seed 相同，因此计划相同），并按每步 22.5 s 统计每分钟步数。
- t ≈ 0.95 / 1.5 / 2.1 h：两个臂的快照 s25 / s50 / s75；最终模型在 ≈ 2.7 h，在 trial 评分在 ≈ 3.4 h 完成。
- 读取，按支出门限，顺序如下：lr1e6-s25 在 ≈ 1 h；然后在研究运行期间一次一个批次；从 ≈ 3.4 h 起最多三个批次同时进行。一个批次耗时约 3 h（longdoc-v1 2 小时 46 分是长板；其余在约 70 分钟内完成），因此全部 8 个候选在 **≈ 10–10.5 h** 读取完毕，随后是读出。
- 确认（刻意为之，从不自动）：测试阶段（约 3 h，longdoc-v1 测试为长板），然后是锁定读取（约 1 h）。它在读出之后开始，因此很可能在 12 小时窗口**之后**结束（≈ 14 h）。在已登记的支出规则下装不下其他内容；准入边界把一个读取批次高估了约 13 倍。

**运行步骤**（在本 PR 合并后）：(1) 确认 `/runs/r25-init/kev-27b-merged/checkpoint` 存在且其 `head.pt` meta 声明 `weights: full`、`lora: 0`、`head_dim: 256`；获取 `evals/sft-v2-r25`（`load_split`）并恢复私有父行和 tasksource-heldout 排除列表（`scripts/private_rows.py restore --manifest runs/r24-readout/private-exclude.json`、`runs/r24-readout/private-rows.json`、`runs/r22-readout/private-rows.json`）；(2) `KEV_GPU=H200 KEV_APP_NAME=kev-r25 uv run modal deploy modal_app.py`；(3) 读取计量成本，`uv run python -m kev.rounds launch experiments/rounds/r25.json`，然后 `watch`；(4) 读出，然后按所写进行确认。

### 第 25 轮结果

**无候选通过（8 个中 0 个）。** 每个候选都未通过 `3_breadth_ece_at_most_parent_plus_0.01`：breadth-v1 ECE 在 0.0227 至 0.0351 之间，相对阈值 0.0176（Kev-27B 0.0076）。`27b-lr1e6-s75` 和 `27b-lr1e6` 最终模型最接近。每个都通过 12 项准则中的 11 项，仅未通过 breadth ECE（0.0283 和 0.0235）。lr 2e-6 的臂还未能通过短状态准确率保护（下界 −2.08 至 −2.71 pp）和 breadth 主准则。没有任何候选进入确认，因此第 25 轮没有读取任何测试划分或锁定集合，也没有发布任何内容。读出：`runs/r25-readout/round25.json`（`python -m kev.rounds readout experiments/rounds/r25.json`，在最后一次读取落地后于 2026-09-29T05:51Z 运行）；表格 `runs/r25-readout/readout.txt`；markdown `runs/r25-readout/tables.md`。

提供方式：每个候选都在其合并 T 下（648 题；无一道作为 transfer-v4 重复项被排除），Kev-27B 在 1.382。Delta 为相对 Kev-27B 的成对记录聚类自助法（2,000 次重采样，seed 0，micro）。准确率与置信错误以 pp 计，Brier 为绝对值，ECE 按提供时相对其阈值给出。排除项移除的题目与第 23、24 轮相同，两侧一致：600 道 breadth、795 道 tasksource-heldout、380 道 Kev-panel 和 220 道 short-state。

**训练**（两个研究，各一次尝试，app `kev-r25`，8 × H200；`runs/r25-27b-lr{1e6,2e6}/00-trial-0`）：
- **设置：** 预热启动从 `/runs/r25-init/kev-27b-merged/checkpoint` 加载了 850 个完整张量外加指针头（`train.log`）。计划与预测一致：每 rank 712 个 micro-batch、356 步、最大 pass 40,960 填充 token 中的 25,590。共有 6,688 对 none pairs（预测为 6,681）。
- **速度与内存：** 训练耗时 5,635 s（lr 1e-6）和 5,282 s（lr 2e-6），即相对于预测的 2.22 h（锚定 1.90 h）为 1.47–1.57 h。整个 trial 耗时 8,539 s 和 7,968 s，在一次 4 小时尝试内。每 GPU 峰值内存为 80.4 GB。每个快照使训练暂停 18–44 s。
- **损失与梯度：** 训练损失从前 10 步的 0.52 降至末尾的 0.26–0.30。平均梯度范数为 12.6 / 10.9（最大 106.6 / 79.5），且全部 356 步都被裁剪。
- **在 trial 内筛选**（sft-v2-r25 开发，处于分布内；规则不读取）：0.887 / 0.896，在 trial 温度 1.0 / 0.966。

| criterion | lr1e6-s25 | lr1e6-s50 | lr1e6-s75 | lr1e6 | lr2e6-s25 | lr2e6-s50 | lr2e6-s75 | lr2e6 |
|---|---|---|---|---|---|---|---|---|
| T (pool, 648) [90 % CI] | 1.289 [1.149, 1.414] | 1.260 [1.122, 1.382] | 1.289 [1.149, 1.414] | 1.350 [1.203, 1.481] | 1.289 [1.176, 1.414] | 1.149 [1.023, 1.231] | 1.350 [1.231, 1.481] | 1.350 [1.203, 1.481] |
| 1 breadth acc, lower > 0 (2475) | +0.7 [+0.00, +1.4] **fail** | +0.6 [−0.04, +1.3] **fail** | +0.9 [+0.3, +1.6] | +0.8 [+0.2, +1.4] | +0.2 [−0.6, +1.0] **fail** | +0.6 [−0.1, +1.3] **fail** | +0.4 [−0.3, +1.1] **fail** | +0.4 [−0.3, +1.1] **fail** |
| 1 tasksource-heldout acc, lower > 0 (1993) | +0.8 [−0.5, +1.9] **fail** | +2.3 [+0.9, +3.7] | +2.9 [+1.6, +4.2] | +2.8 [+1.5, +4.1] | +1.6 [+0.1, +3.1] | +4.0 [+2.5, +5.5] | +4.5 [+3.1, +6.0] | +4.2 [+2.7, +5.7] |
| 1 Kev panel acc, lower ≥ −1 (3351) | +3.0 [+2.0, +4.0] | +5.2 [+4.2, +6.3] | +5.8 [+4.8, +7.0] | +6.2 [+5.2, +7.3] | +3.1 [+1.9, +4.2] | +5.6 [+4.4, +6.7] | +6.4 [+5.2, +7.6] | +6.4 [+5.3, +7.6] |
| 2 short acc, lower ≥ −2 (1586) | −0.50 [−1.20, +0.19] | −0.32 [−1.13, +0.50] | −0.76 [−1.51, +0.00] | −0.69 [−1.45, +0.06] | −1.64 [−2.71, −0.50] **fail** | −1.07 [−2.21, +0.13] **fail** | −0.88 [−2.08, +0.25] **fail** | −1.07 [−2.21, +0.13] **fail** |
| 2 short Brier, upper ≤ +0.02 | +0.006 [+0.001, +0.012] | +0.004 [−0.002, +0.010] | +0.001 [−0.005, +0.007] | +0.002 [−0.004, +0.008] | +0.017 [+0.005, +0.028] **fail** | +0.003 [−0.009, +0.013] | +0.001 [−0.011, +0.011] | +0.001 [−0.011, +0.012] |
| 2 short confident errors, upper ≤ +1 | +0.3 [−0.4, +0.8] | +0.3 [−0.4, +0.8] | +0.1 [−0.5, +0.7] | +0.2 [−0.4, +0.8] | +0.3 [−0.5, +1.0] **fail** | −0.1 [−0.9, +0.5] | −0.2 [−0.9, +0.4] | −0.2 [−0.9, +0.5] |
| 2 CUAD acc, lower ≥ −2 (2254) | +0.3 [−0.3, +0.9] | +0.4 [−0.4, +1.1] | +0.2 [−0.6, +0.9] | +0.1 [−0.7, +0.9] | −0.3 [−1.2, +0.5] | −0.0 [−0.8, +0.8] | −0.1 [−0.9, +0.7] | −0.2 [−1.0, +0.6] |
| 2 CUAD 16k+ acc, cand − parent ≥ −2 | 0.836 vs 0.837 | 0.838 vs 0.837 | 0.837 vs 0.837 | 0.837 vs 0.837 | 0.836 vs 0.837 | 0.839 vs 0.837 | 0.839 vs 0.837 | 0.837 vs 0.837 |
| 2 unknowable share ≤ 0.05 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| 3 breadth ECE ≤ 0.0176 (Kev-27B 0.0076) | 0.0227 **fail** | 0.0236 **fail** | 0.0283 **fail** | 0.0235 **fail** | 0.0294 **fail** | 0.0301 **fail** | 0.0351 **fail** | 0.0306 **fail** |
| 3 Kev-panel ECE ≤ 0.0327 (Kev-27B 0.0227) | 0.0129 | 0.0166 | 0.0164 | 0.0185 | 0.0191 | 0.0121 | 0.0117 | 0.0136 |
| 3 tasksource-heldout ECE ≤ 0.0523 (Kev-27B 0.0423) | 0.0561 **fail** | 0.0474 | 0.0502 | 0.0458 | 0.0623 **fail** | 0.0516 | 0.0520 | 0.0505 |
| rank score (Δ breadth + Δ tsheld + Δ Kev, pp) | +4.4 | +8.1 | +9.7 | +9.8 | +4.8 | +10.1 | +11.2 | +11.0 |
| criteria passed | 8/12 | 10/12 | 11/12 | 11/12 | 6/12 | 9/12 | 9/12 | 9/12 |
| verdict | fail | fail | fail | fail | fail | fail | fail | fail |

breadth 主准则的精确下界：s25 0.0000（不大于 0）、s50 −0.0004、lr2e6 各臂 −0.0012 至 −0.0061。

**仅报告面板**相对 Kev-27B（完整表格，含每个 OOD 与外部面板，见 `runs/r25-readout/tables.md`）：

| panel | lr1e6-s25 | lr1e6-s50 | lr1e6-s75 | lr1e6 | lr2e6-s25 | lr2e6-s50 | lr2e6-s75 | lr2e6 |
|---|---|---|---|---|---|---|---|---|
| breadth, all 14 sources, acc (3075) | +0.8 [+0.1, +1.5] | +0.7 [+0.1, +1.4] | +1.0 [+0.3, +1.6] | +0.8 [+0.1, +1.4] | +0.4 [−0.5, +1.2] | +0.6 [−0.1, +1.3] | +0.4 [−0.3, +1.1] | +0.5 [−0.3, +1.2] |
| tasksource-heldout all 24 families, acc (2788) | +1.2 [+0.1, +2.3] | +2.2 [+1.0, +3.4] | +2.9 [+1.8, +4.1] | +2.8 [+1.7, +4.0] | +2.3 [+1.1, +3.6] | +4.6 [+3.3, +5.9] | +5.2 [+4.0, +6.5] | +4.9 [+3.7, +6.2] |
| hard-v1 acc (1083) | +6.3 [+3.8, +8.8] | +10.2 [+7.6, +12.8] | +11.8 [+9.3, +14.4] | +12.5 [+10.0, +15.0] | +7.3 [+4.6, +10.1] | +10.2 [+7.5, +13.0] | +12.5 [+9.7, +15.3] | +12.7 [+10.0, +15.6] |
| Kev panel without hard-v1, acc (2268) | +1.4 [+0.5, +2.3] | +2.8 [+1.8, +3.8] | +3.0 [+2.0, +4.0] | +3.2 [+2.2, +4.2] | +1.1 [+0.0, +2.1] | +3.4 [+2.2, +4.5] | +3.4 [+2.3, +4.6] | +3.4 [+2.2, +4.6] |
| transfer-v4 dev only, acc (576; the locked read's suite) | −0.9 [−1.9, +0.0] | −0.3 [−1.6, +0.9] | −0.9 [−2.1, +0.2] | −0.9 [−2.1, +0.2] | −0.9 [−2.4, +0.7] | +0.2 [−1.9, +2.3] | +0.7 [−1.2, +3.0] | +0.3 [−1.6, +2.6] |
| SemIf / WANLI-v2 / TypeSafe acc | +0.0 / −0.3 / +1.1 | +0.0 / +0.1 / +0.0 | +0.7 / +0.4 / −1.1 | +0.7 / +0.4 / −1.1 | +0.7 / +0.6 / −2.2 | −1.4 / −0.7 / +1.1 | −3.5 / −0.8 / +1.1 | −2.8 / −0.7 / +0.0 |
| ood-v2 / agents-ood / guardrails-ood acc | +0.5 / −0.2 / +3.2 | +0.7 / +0.3 / +3.7 | +0.9 / +0.2 / +3.9 | +0.8 / +0.3 / +4.0 | +0.3 / +0.5 / +3.9 | +1.0 / +0.2 / +3.9 | +1.0 / +0.5 / +4.2 | +1.0 / +0.7 / +4.2 |
| ood-v2 / agents-ood / guardrails-ood ECE Δ | −0.020 / −0.074 / −0.055 | −0.025 / −0.083 / −0.064 | −0.025 / −0.092 / −0.065 | −0.026 / −0.091 / −0.064 | −0.022 / −0.098 / −0.068 | −0.025 / −0.085 / −0.069 | −0.027 / −0.097 / −0.065 | −0.027 / −0.096 / −0.065 |
| CUAD ECE (Kev-27B 0.063) | 0.087 | 0.098 | 0.101 | 0.103 | 0.102 | 0.100 | 0.102 | 0.103 |
| CUAD ECE 16k+ (Kev-27B 0.071) | 0.089 | 0.100 | 0.105 | 0.112 | 0.105 | 0.112 | 0.110 | 0.109 |
| short-state acc, candidate (Kev-27B 0.9042) | 0.8991 | 0.9010 | 0.8966 | 0.8972 | 0.8878 | 0.8934 | 0.8953 | 0.8934 |

CUAD 按长度（准确率 / ECE；Kev-27B 在前）：< 8k (896) 0.845 / 0.059，候选 0.842–0.852 / 0.092–0.102；8k–16k (452) 0.834 / 0.063，0.827–0.838 / 0.089–0.112；16k–32k (454) 0.841 / 0.070，0.839–0.844 / 0.087–0.116；32k–64k (452) 0.832 / 0.072，0.827–0.834 / 0.095–0.118（各臂见 `tables.md`）。生成的 longdoc 项准确率仍保持在 1.000。

**本轮说明了什么：**
- **回放在 lr 1e-6 下保持了短状态（假设 (i)）：** 短状态准确率 −0.3 至 −0.8 pp，每个下界 ≥ −1.51。在 lr 2e-6 下，短状态损失是 transfer-r3 测试，而非 transfer-v4。仅在 transfer-v4 开发上，lr 2e-6 的 s50 快照读取为 +0.2 至 +0.7，而合并面板停留在 −0.9 至 −1.6。
- **丢弃长文档族保住了 CUAD 准确率，却没保住其校准（假设 (ii)，仅开发）：**
  - 准确率：CUAD −0.3 至 +0.4 pp，且 16k+ 与 Kev-27B 持平（0.836–0.839 对比 0.837）。第 22 轮的 CUAD 损失出现在测试上（−1.8），而第 25 轮没有读取任何测试，因此这尚不能构成反证。
  - 校准：CUAD ECE 仍升至 0.087–0.103，并随训练增长（lr 1e-6：s25 0.087 → 最终 0.103）。第 22 轮最终模型用长文档数据训练，读取的 CUAD ECE 16k+ 为 0.102（第 24 轮读取），而第 23 轮混合在各长度上均为 0.097–0.102。因此，这种校准偏差伴随以合并短状态温度提供服务的持续全权重 SFT 而来，而非来自长文档族（开发读取，仅一轮）。
- **增益小于第 22 / 23 轮，且随步数增长：** breadth +0.2 至 +0.9（27b-k-w85 +1.5）、tasksource-heldout +0.8 至 +4.5（+4.2）、Kev 面板 +3.0 至 +6.4（+8.1）。guardrails-ood 的增益与 w85 相当（+3.2 至 +4.2 对比 +4.0），agents-ood 较小（−0.2 至 +0.7 对比 +2.1）；OOD ECE 全程改善（agents-ood −0.07 至 −0.10）。
- **breadth ECE 与 tasksource-heldout ECE 想要不同的温度**（仅报告，`runs/r25-readout/breadth-ece-by-t.json`）：
  - breadth 面板的 ECE 最小化 T 为 1.40–1.72，高于任何合并拟合值。
  - 在每个臂的 90 % T 区间高端，大多数臂的 breadth ECE 会通过（0.0099–0.021；lr 1e-6 最终模型 0.0135）。在该 T 下，tasksource-heldout ECE 升至 0.060–0.070，会无法通过其阈值 0.0523。
  - 在低端则相反。这又是第 24 轮的模式。没有任何一个臂的 90 % 区间内有任何 T 能同时通过两个阈值（41 点网格）。

**仅报告：相对第 23 轮已确认的 `27b-k-w85`。** 没有具名候选，因此对每个臂都进行比较。
- **方法：** 各方使用其自身的合并 T（w85 为 1.320）。对开发读取做成对自助法，相同的面板与排除项，并将 `short` 拆分为 transfer-v4 开发与 transfer-r3 测试。
- **文件：** `runs/r25-readout/vs-w85.md` 与 `vs-w85-<arm>.json`，来自 `runs/r25-readout/r25-vs-w85.py`。
- **结果：w85 在几乎每个面板上都领先或持平。**
  - 相对最接近的臂，即 lr 1e-6 最终模型：breadth −0.8 [−1.5, +0.0]、tasksource-heldout −1.4 [−2.7, +0.1]、Kev 面板 −1.9 [−2.9, −1.0]（hard-v1 −5.4，其余 −0.3）、agents-ood −1.8 [−2.5, −1.2]。
  - 短状态持平：+0.3 [−0.7, +1.2]；transfer-v4 开发 −1.2 [−2.6, +0.2]、transfer-r3 测试 +1.1 [+0.0, +2.4]。
  - 候选有更的置信错误：short +1.3 [+0.7, +2.0] pp。
  - CUAD 准确率持平（−0.6 [−1.7, +0.3]），CUAD ECE 为 +0.006 [−0.009, +0.016]。按长度，w85 读取 0.856 / 0.096（< 8k）和 0.839 / 0.102（16k+），对比 0.849 / 0.100 和 0.837 / 0.112。
- **排名：** 没有任何第 25 轮臂在规则所门控的任何面板上以高于 0 的下界领先于 w85。两个仅报告的面板是例外：`27b-lr1e6-s25` 的 CUAD ECE −0.011 [−0.022, −0.002]，以及 `27b-lr2e6-s75` 在 tasksource-heldout 的 24 个族上的 +1.3 [+0.1, +2.4]。lr 2e6 的 s75 和最终模型在 tasksource-heldout（+0.4、+0.0）和 transfer-v4 开发（+0.3、+0.0）上与 w85 持平，并在 breadth（−1.2、−1.1）和 hard-v1（−5.4、−5.2）上落后于它。Kev-27B 和 `27b-k-w85` 仍是 Jared 的发布选项（"第 23 轮确认"）；此处内容不改变该选择。

**偏差：**
- **(i) 四次读取重新启动。**
  - *失败原因：* 第一批的四个作业（`27b-lr1e6-s25`：agentsood、guardood、ood、tsheld）在加载时失败。私有套件 agents-ood-v1、guardrails-ood-v1、ood-v2 和 tasksource-heldout-v1 的开发划分不在本 checkout 中，且 Modal 容器无法读取私有镜像。
  - *修复：* 这些划分从第 23 轮 checkout 复制，按每个 manifest 做 sha256 校验，并以相同名称重新启动这四个作业一次。这些名称下此前未写入任何内容。
  - *记录：* `runs/r25-reads-27b-lr1e6-s25-retry.json`。之后每个批次都拥有这些划分并运行全部 16 次读取。
- **(ii) 支出核算与读取并发。**
  - *登记：* 在两个研究运行期间，一次一个候选的批次（每个 $400.97，按 16 × 4 h × $6.27）。
  - *实际操作：* 门限按 docs/autoresearch.md §2 的定义应用，使用仍在运行的调用的边界。每个读取作业都是其自身的调用（$25.06），因此短读取已落地的批次只计入其剩余作业，主要是 longdoc 读取（在 27B 上约 2 小时 40 分）。
  - *结果：* `27b-lr2e6-s25` 在 01:07Z 与 `27b-lr1e6-s25` 剩余的四个作业并排启动，此时两个研究都在运行。后续批次按门限允许启动（`runs/r25-readout/r25-gate.py`，计算它的本地辅助脚本）。每次启动都先读取计量成本，且 ≤ $1,813：00:52Z 时 $1,422.96（全批次边界），随后使用运行中的调用边界，两次重新启动为 $1,498 和约 $1,518，并在 01:07、01:31、02:09、02:46、03:02Z 分别为 $1,585、$1,770、$1,762、$1,705、$1,791。观察器（watcher）在 trial 结束时（02:36Z、02:45Z）自行启动了两个最终模型的读取，没有使用自己的门限。按同一核算，02:36Z 时约为 $1,650，当时还有一个研究在运行。
  - *相对登记的核算：* 若用全批次边界，01:07Z 的启动会被计为 95.81 + 988 + 802 = $1,886，超过 $1,813。实际支出远低于这些边界。
- **(iii) 启动时间：** s25 00:52Z / 01:07Z，lr1e6-s50 01:31Z，lr2e6-s50 02:09Z，最终模型 02:36Z / 02:45Z（watcher），lr1e6-s75 02:46Z，lr2e6-s75 03:02Z。最后一次读取在 05:49Z 落地。部署和读取都在 app `kev-r25` 上运行，部署的 app 在 06:00Z 停止。`kev-sft` 未触碰。

**支出**（Modal 计量值，workspace 范围）：
- 登记读数（23:45Z）时为 $3,966.94。
- 启动前读数：$3,969.07（00:22Z）、$4,000.93（00:51Z）、$4,062.75（01:06Z）、$4,197.70（01:30Z，至 01:45Z 修订为 $4,141）、$4,214.37（02:09Z）、$4,354.44（03:02Z）。
- 最后一次读取后 05:51Z 时为 $4,461.51，06:00Z 时为 $4,461.42。
- 总计：相对登记读数 **+$494.5**（两次一次尝试的研究按标价约 $185、128 次读取、4 次重新启动），未计计量滞后。这在已登记的预测（约 $4,510）范围内。当晚上限约为 $5,980，硬停止点为 $5,600。

**证据**（已提交）：
- 读出、其表格以及仅报告的额外内容（`vs-w85*`、`breadth-ece-by-t.json`、`transfer4-vs-parent.json`，以及写入它们的脚本，位于 `runs/r25-readout/`）。
- 启动记录 `runs/r25-reads-*.json`。
- 每个公开套件读取的报告与行（`runs/r25-27b-<arm>-<tag>`）；对于 OOD 读取，仅报告。
- 每个 trial：`provenance.json`、`result-public.json`（不含逐任务表）、在 trial 的 transfer 行与温度、`training_metrics.json`，以及三个 `snapshot.json` 记录。

私有（`jaredpalmer/kev-private-train` @ `03a62890`，位于 `runs/r25/`，sha256 在 `runs/r25-readout/private-rows.json` 中；用 `scripts/private_rows.py restore` 恢复）：
- 八次 tasksource-heldout-v1 读取（行与报告）；
- ood / agents-ood / guardrails-ood 行；
- 两个 trial 的开发行和完整的 `result.json`。

Checkpoint（每个约 51 GB：6 个快照 + 2 个最终模型）保留在 `kev-runs` 卷上。

**下一步**（提案，未登记；每个都需要自己的 spec）：
- **在投入更多之前，先找出是什么带来了 breadth-ECE 差距。** 它是 `27b-lr1e6` 和 `27b-lr1e6-s75` 唯一未通过的准则，差 0.006–0.011。朝 Kev-27B 混合并非显而易见的修复：在第 23 轮中，更多 Kev-27B 权重反而抬高了 breadth ECE（α 0.85 时为 0.0103 → α 0.50 时为 0.0195，SFT 头）。在合并 T 下按来源对受控 breadth 面板做仅报告的拆解（无需 GPU）可以显示是否有一两个数据集带来了差距。
- **两个校准面板现在把温度拉开了。** breadth-v1 想要 T 1.40–1.72，而 tasksource-heldout 想要更低。对每个臂而言，其合并 90 % 区间内没有任何 T 能同时通过两个 ECE 阈值（41 点网格，读出后检查过）。第 22 轮最终结果与 `27b-k-w85` 都在其合并 T 下同时通过，因此从 Kev-27B 出发的持续 SFT 拉大了差距。

## 第 26 轮（已登记）

### 第 26 轮 — 第 25 轮 lr 1e-6 臂配上两倍 breadth 数据（随本 spec 的提交登记，写于任何第 26 轮训练或读取之前）

**唯一的问题。** 在保持第 25 轮 lr 1e-6 臂其他一切不变的前提下，将 tasksource-v1 翻倍，能否让该臂微小的 breadth 增益变成能通过第 24 轮经审计规则的增益？固定部分包括初始化、学习率、计划、回放、其他族、状态上限、seed 和规则。第 26 轮只改一件事：再增加 13,000 条 tasksource-v1 记录（总共 26,000 条，在相同的 119 个族上分层）。

**为什么。** 第 25 轮的读出（`runs/r25-readout/round25.json`、PR #180）在安全学习率下读取 lr 1e-6 臂：
- 短状态保持：相对 Kev-27B 为 −0.3 至 −0.8 pp，每个下界 ≥ −1.51。
- CUAD 准确率在开发上保持。
- `27b-lr1e6-s75` 和最终模型通过了 12 项准则中的 11 项。各自仅未通过 breadth-v1 ECE：0.0283 和 0.0235，相对阈值 0.0176。
- breadth 增益很小：breadth-v1 在最终模型上为 +0.8 [+0.2, +1.4]，tasksource-heldout 为 +2.8，对比 `27b-k-w85` 的 +1.5 和 +4.2。
- lr 2e-6 获得了更多 tasksource-heldout 增益（+4.0 至 +4.5），但在短状态上发生漂移（下界 −2.08 至 −2.71 pp，未通过保护）。

更高的学习率被排除，因此剩下的杠杆是在安全速率下使用更多 breadth 数据。第 25 轮的增益随步数在两个速率上都增长（breadth s25 +0.7 → 最终 +0.8，tasksource-heldout +0.8 → +2.8）。更多的 breadth 记录能在不提高速率的情况下，让模型在 breadth 分布上走更多步。breadth ECE 未通过是本轮的另一问题。第 25 轮的分析（`runs/r25-readout/breadth-ece-by-t.json`）发现 breadth 想要比合并拟合更高的温度（1.40–1.72），而 tasksource-heldout 想要更低的。更多的 breadth 数据可能把 breadth 面板拉向合并温度，也可能不会。这里在校准方面没有任何变化：池、规则和阈值都是第 24 轮的。

**初始化 checkpoint。** 第 25 轮的：`/runs/r25-init/kev-27b-merged/checkpoint`（Kev-27B `jaredpalmer/kev-27b@01b81998`，其 rank-16 LoRA 已合并入 bf16 骨干，并加上其指针头）。它已经在 `kev-runs` 卷上。第 25 轮加载过它（850 个完整张量加头）。`kev.train --init_from` 在加载前会再次检查兼容性。

**数据**（私有；仅本仓库中有 manifest）。`evals/sft-v2-r26`（kev-private-train @ `187ac5f0`、`sft-v2-r26/`；由 kev-sft `assemble-r26` @ `a4d3526`、`assemble/derive_r26.py` 构建）。构建是确定性的：一次不带测量缓存的从头第二次运行写出了相同字节（train sha256 `4578275c…`）。每条记录都是一条 sft-v2-r21 记录，未改动，无新记录或标签。
- **来源。** 第 25 轮的来源 sft-v2-r22 仅持有 24,000 条 tasksource-v1 记录（上限内 23,996），因此无法提供 26,000 条。sft-v2-r21 持有 sft-v2 的全部 58,190 条。对于每个其他保留的组件，它都精确持有 sft-v2-r22 的记录，顺序相同，因为 sft-v2-r22 只下采样了 longify、tasksource-v1 以及 sft-v1 的 public 和 synthetic 来源。
- **步骤 1–3 沿用 derive_r25.py 的：** 相同的组件、相同的筛选和 16,384 token 的状态上限。
  - 筛选是 kev-sft `assemble/screen_v2.py`，针对相同的 105 个评估划分和 76,207 个参考项。自第 25 轮以来没有任何评估套件发生变化。**0 条记录**违规。
  - 有 1,443 条训练记录超出上限：1,161 agents、188 grounding、84 injection 和 10 tasksource。
- **步骤 4 是唯一的改动。**
  - 除 tasksource-v1 外的每个组件都按第 25 轮的规则和 salt 选取，因此它**精确保留 sft-v2-r25 的记录**。构建会检查这一点。
  - tasksource-v1 保留 sft-v2-r25 的全部 13,000 条记录，即一个超集，因此第 26 轮数据是 sft-v2-r25 加上增量。然后每个族用其尚未在 sft-v2-r25 中的记录补足到其在 26,000 中的份额（floor，再在 58,180 条上限记录上取最大余数），按最小的 sha256(seed:keep:tasksource-v1: + record digest) 排序。没有任何族的 round-25 记录超过其新份额。全部 119 个族都保留。
  - 构建还检查 train 是 sft-v2-r25 的 train 划分按顺序加上 13,000 条 tasksource-v1 记录，且校准与开发逐字节等于 sft-v2-r25（4,904 和 2,714 条记录；相同 sha256）。

| component | round 25 | **round 26** | state tokens | questions |
|---|---|---|---|---|
| **tasksource-v1** | 13,000 | **26,000 (+13,000; all 119 families)** | 3.68M | 35,548 |
| b1v2 (replay, kept whole) | 13,763 (30.2 %) | 13,763 (**23.5 %**) | 2.03M | 16,788 |
| tone / guardrails-pii / guardrails-grounding / injection / ood (half each) | 13,546 | 13,546 | 12.83M | 50,328 |
| agents (≤ 16k, a tenth) | 371 | 371 | 3.32M | 1,719 |
| hard-v1 / devtools-v1 / documents-v1 (a quarter) | 4,835 | 4,835 | 2.70M | 6,966 |
| **total** | 45,515 | **58,515** | **24.56M** (31.07M row tokens with the state shared) | **111,349** (4,645 soft) |

状态 token：中位数 102、均值 420、p90 1,015、p99 6,210、最大 16,365。直方图：≤256 42,126 · 257–512 5,745 · 513–1k 4,871 · 1k–2k 3,933 · 2k–4k 851 · 4k–8k 579 · 8k–16k 410。没有公开文件命名 tasksource 族。

**其他如实说明的变化。** 在添加记录的同时保持 b1v2 完整，会使回放占比从 30.2 % 降至 23.5 %。在相同的 epoch 数下，模型也改为走 458 步而非 356 步（在更长的运行上做 OneCycle，峰值 lr 相同），因此离初始化点走了更多步。两者都源于那一处改动。两者都未做调整，因为补偿（更多回放，或更短的计划）会构成第二处改动。如果短状态发生漂移，这些就是首要怀疑对象。

**Epoch 时间，依据第 25 轮的实测速率**（kev-sft `assemble/epoch_r26.py`、`assemble/manifests/sft-v2-r26.epoch_projection.json`）。
- **方法。** 第 22 轮的 pass-time 模型与精确计划副本（如第 25 轮）作用于每条记录精确的 epoch-0 token 形状，并校准到第 25 轮的**实测**训练时间。`runs/r25-27b-lr1e6/00-trial-0` 用 5,635 s 训练了 356 步（每步 15.8 s），而模型预测为 2.22 h，由此得到锚定系数 0.704。
- **预测。** **458 步**、每 rank 915 个 micro-batch、最大 pass 40,960 填充 token 中的 25,590、8,256 条未配对记录。
- **训练时间。** 未锚定 2.51 h，**锚定 1.77 h**（每步 13.9 s），在约 2.2 h 的目标内。
- **快照。** 步 **115 / 229 / 344**。
- **一次尝试。** 锚定训练加上第 25 轮同一 trial 的实测非训练时间（2,904 s：加载、token 计数、快照、最终保存、相同校准 / 开发和 transfer-v4 的在 trial 评分）= **2.57 h**。未锚定模型为 3.32 h。两者都适配 4 小时超时。超时由 `kev.rounds watch` 从最后的恢复点继续，在台账的三次尝试范围内。

**臂**（spec `experiments/rounds/r26.json`、计划 `experiments/round26/lr1e6.json`、app `kev-r26`）。一个研究，`r26-27b-lr1e6`：在 8 × H200 上一次 trial，尝试时长 14,400 s。
- 计划与 `experiments/round25/lr1e6.json` 逐字节相同：从合并 checkpoint 的 `full_ft 1`、lr 1e-6、头 lr 1e-5、带 10 % 预热的 OneCycle、一个 epoch、batch 8 × accum 2、`length_sort 1`、`pass_tokens_max 40960`、bf16、`max_state 16384`、`p_none_pair 0.25` 配 `none_pair_max_state 8192`、seed 0。
- 仅研究的套件不同：`evals/sft-v2-r26`。

候选：步 115 / 229 / 344 的快照（`/runs/r26-27b-lr1e6/00-trial-0/snapshots/step-0000NNN/checkpoint`）以及最终模型，**共 4 个**（`27b-lr1e6-s25/s50/s75`、`27b-lr1e6`）。
- 每个臂都命名 `trained_on: [evals/sft-v2-r26, evals/round6/b1v2, evals/v7/decision-v7]`。
- 快照步数即预测值。如果训练器的计划记录了不同的步数，快照路径会在任何读取之前被修正，其他不变。

**规则、温度池、读取、父读取、读取超时、排除项与确认：第 24 轮经审计的规则，逐字沿用，同第 25 轮。** spec 与 `r25.json` 仅在以下方面不同：
- 轮次编号、app 和 `registered` 文本；
- 一个研究而非两个，配第 26 轮的计划与套件；
- 四个臂；
- 确认的候选读取路径（`runs/r26c-…`、`runs/locked/kev-{size}-r26-ungated/transfer`）。

父模型是 Kev-27B，使用相同的读取，其测试读取是第 24 轮的（`runs/r24c-{size}-parent-{tag}`）。与第 25 轮相同的注意事项适用于确认划分：它们已在第 22–24 轮中为其他模型读取过，尚无任何一次是为第 25 或第 26 轮模型读取的。

**预算**（Jared 当晚授权：计量上限 ≈ $5,980）。登记时的计量读数 **≈ $4,454**：余量 ≈ $1,526、储备 ≈ $153（10 %）。因此在任何一次启动时，准入边界与支出最多 **≈ $1,373**。每次启动首先读取计量成本（docs/autoresearch.md 第 2 节）。

| item | admission bound | expected |
|---|---|---|
| study `r26-27b-lr1e6` (H200:8 at $41.17/h × 4 h × 3 attempts) | $494.00 | ~$106 (one attempt, 2.57 h; ~$137 unanchored) |
| reads of one candidate (16 reads × 4 h × $6.27/h) | $400.97 | ~$30 |
| reads of all 4 candidates | $400.97 each, spend-gated | ~$120 |
| confirmation, one candidate (tests stage 7 reads × $25.06; locked read; serving check) | $175.43 + ~$25 + ~$6 | ~$25 |
| **peak while training: study + two read batches** | **$1,296** of $1,373 | |
| **peak after training: three read batches** | **$1,203** of $1,373 | |
| **projection at the end of the round** | | **≈ $4,680-4,710** (+$226-257; + ~$25-50 if a candidate goes to confirmation) |

第四个并发批次（$1,604）装不下，因此读取在研究的边界释放后最多一次三个同时进行。在研究运行期间，最多两个批次与之并行。

**墙钟计划**（t = 0 为启动时刻；锚定时间，未锚定者约晚 40 %）：
- **t ≈ 0–0.4 h。** 容器加载合并后的 27B 并统计 token。在最开始几分钟，检查日志中的 `none pairs: N of 58515 records`（预测 8,256；第 25 轮的日志读到 6,688，对比 6,681）和 `plan: 915 micro-batches per rank for 458 steps`。然后按每步 13.9 s 统计每分钟步数。
- **训练。** 快照 s25 / s50 / s75 在 t ≈ 0.85 / 1.3 / 1.75 h。最终模型在 ≈ 2.2 h 落地，在 trial 评分在 ≈ 2.6 h 完成。
- **读取，按支出门限。**
  - `27b-lr1e6-s25` 在 ≈ 0.85 h、`27b-lr1e6-s50` 在 ≈ 1.3 h，与研究并行（两个批次）。
  - `27b-lr1e6-s75` 在 trial 结束时（≈ 2.6 h，三个同时）。
  - 最终模型在第一个批次结束时（≈ 3.85 h）。
  - 一个批次耗时约 3 h：longdoc-v1 2 小时 46 分是长板，其余在约 70 分钟内完成。快照在 ≈ 5.6 h 读取完毕，最终模型在 **≈ 6.9 h**，随后是读出。
- **确认**（刻意为之，从不自动）在读出之后：测试阶段（约 3 h），然后是锁定读取（约 1 h）。它会在 Jared 的夜间时段之后结束。

**运行步骤**（在本 PR 合并后）：
1. 确认 `/runs/r25-init/kev-27b-merged/checkpoint` 仍在卷上。获取 `evals/sft-v2-r26`（`load_split`）。按第 25 轮的方式恢复私有父行和 tasksource-heldout 排除列表。
2. `KEV_GPU=H200 KEV_APP_NAME=kev-r26 uv run modal deploy modal_app.py`。
3. 读取计量成本，然后运行 `uv run python -m kev.rounds launch experiments/rounds/r26.json`，然后 `watch`。
4. 读出，然后按所写进行确认。

### 第 26 轮结果

**无候选通过（4 个中 0 个）。** 每个候选都未通过 `3_breadth_ece_at_most_parent_plus_0.01`：breadth-v1 ECE 在 0.0197 至 0.0287 之间，相对阈值 0.0176（Kev-27B 0.0076）。最终模型 `27b-lr1e6` 通过了其余 11 项准则，与第 25 轮最终模型一致（此处 breadth ECE 0.0233，彼处 0.0235）。三个快照也未能通过 breadth 主准则：它们的下界为 −0.12、−0.16 和 −0.04 pp。`27b-lr1e6-s50` 还未能通过短状态准确率保护（下界 −2.52 pp），而 `27b-lr1e6-s25` 未能通过 tasksource-heldout ECE（0.0627 对比 0.0523）。没有任何候选进入确认，因此第 26 轮没有读取任何测试划分或锁定集合，也没有发布任何内容。读出：`runs/r26-readout/round26.json`（`python -m kev.rounds readout experiments/rounds/r26.json`，由 watcher 在最后一次读取落地后于 12:53Z 写入，并于 12:57Z 重新运行）；表格 `runs/r26-readout/readout.txt`；markdown `runs/r26-readout/tables.md`。

提供方式：每个候选都在其合并 T 下（648 题；无一道作为 transfer-v4 重复项被排除），Kev-27B 在 1.382。Delta 为相对 Kev-27B 的成对记录聚类自助法（2,000 次重采样，seed 0，micro）。准确率与置信错误以 pp 计，Brier 为绝对值，ECE 按提供时相对其阈值给出。排除项移除的题目与第 23–25 轮相同，两侧一致：600 道 breadth、795 道 tasksource-heldout、380 道 Kev-panel 和 220 道 short-state。

**训练**（一次尝试，app `kev-r26`，8 × H200；`runs/r26-27b-lr1e6/00-trial-0`）：
- **设置：** 预热启动从 `/runs/r25-init/kev-27b-merged/checkpoint` 加载了 850 个完整张量外加指针头（`train.log`："delta: warm start from ..."；58,515 个训练请求）。计划与预测完全一致：每 rank 915 个 micro-batch、458 步、最大 pass 40,960 填充 token 中的 25,590、在步 115 / 229 / 344 之后做快照。因此 `r26.json` 中的快照路径是正确的，无需修正。共有 8,263 对 none pairs（预测 8,256）。
- **速度与内存：** 训练耗时 5,836 s（1.62 h，每步 12.7 s），对比预测的锚定 1.77 h（未锚定 2.51 h）。整个 trial 耗时 8,843 s，在一次 4 小时尝试内。每 GPU 峰值内存为 80.4 GB。快照使训练暂停 19.8、19.9 和 29.2 s。
- **损失与梯度：** 训练损失从步 10 的 0.41 降至最后几步的 0.27–0.31。平均梯度范数为 12.2（最大 61.2），且全部 458 步都被裁剪。
- **在 trial 内筛选**（sft-v2-r26 开发，处于分布内；规则不读取）：0.893，在 trial 温度 0.966。transfer-v4 开发原始值 0.855（第 25 轮 lr 1e-6 trial：0.840）。

| criterion | lr1e6-s25 | lr1e6-s50 | lr1e6-s75 | lr1e6 |
|---|---|---|---|---|
| T (pool, 648) [90 % CI] | 1.350 [1.203, 1.447] | 1.350 [1.203, 1.447] | 1.203 [1.097, 1.320] | 1.320 [1.176, 1.414] |
| 1 breadth acc, lower > 0 (2475) | +0.5 [−0.1, +1.2] **fail** | +0.6 [−0.2, +1.2] **fail** | +0.6 [−0.04, +1.3] **fail** | +1.0 [+0.3, +1.7] |
| 1 tasksource-heldout acc, lower > 0 (1993) | +2.4 [+1.1, +3.7] | +2.7 [+1.2, +4.2] | +3.5 [+2.0, +4.9] | +3.3 [+1.8, +4.8] |
| 1 Kev panel acc, lower ≥ −1 (3351) | +3.7 [+2.7, +4.7] | +5.0 [+3.9, +6.1] | +5.6 [+4.6, +6.7] | +5.6 [+4.5, +6.6] |
| 2 short acc, lower ≥ −2 (1586) | −0.57 [−1.26, +0.13] | −1.45 [−2.52, −0.44] **fail** | −0.63 [−1.58, +0.32] | −1.01 [−1.95, −0.06] |
| 2 short Brier, upper ≤ +0.02 | +0.005 [−0.001, +0.011] | +0.008 [−0.003, +0.018] | +0.000 [−0.011, +0.009] | +0.003 [−0.008, +0.011] |
| 2 short confident errors, upper ≤ +1 | −0.3 [−1.0, +0.4] | −0.2 [−1.0, +0.5] | −0.3 [−1.1, +0.4] | −0.2 [−0.9, +0.5] |
| 2 CUAD acc, lower ≥ −2 (2254) | +0.8 [+0.2, +1.5] | +0.1 [−0.5, +0.9] | +0.2 [−0.6, +1.0] | +0.2 [−0.6, +1.0] |
| 2 CUAD 16k+ acc, cand − parent ≥ −2 | 0.843 vs 0.837 | 0.834 vs 0.837 | 0.836 vs 0.837 | 0.834 vs 0.837 |
| 2 unknowable share ≤ 0.05 | 0.000 | 0.000 | 0.000 | 0.000 |
| 3 breadth ECE ≤ 0.0176 (Kev-27B 0.0076) | 0.0209 **fail** | 0.0197 **fail** | 0.0287 **fail** | 0.0233 **fail** |
| 3 Kev-panel ECE ≤ 0.0327 (Kev-27B 0.0227) | 0.0180 | 0.0190 | 0.0170 | 0.0197 |
| 3 tasksource-heldout ECE ≤ 0.0523 (Kev-27B 0.0423) | 0.0627 **fail** | 0.0416 | 0.0394 | 0.0419 |
| rank score (Δ breadth + Δ tsheld + Δ Kev, pp) | +6.6 | +8.2 | +9.7 | +9.8 |
| criteria passed | 9/12 | 9/12 | 10/12 | 11/12 |
| verdict | fail | fail | fail | fail |

breadth primary 的精确下界：s25 −0.0012，s50 −0.0016，s75 −0.0004，final +0.0028。final 的 short-state 下界为 −0.0195，处于其保护阈值内 0.05 pp 处。

**仅报告面板**（对照 Kev-27B；含全部 OOD 与外部面板的完整表格在 `runs/r26-readout/tables.md`）：

| panel | lr1e6-s25 | lr1e6-s50 | lr1e6-s75 | lr1e6 |
|---|---|---|---|---|
| breadth, all 14 sources, acc (3075) | +0.6 [−0.1, +1.3] | +0.5 [−0.2, +1.2] | +0.6 [−0.1, +1.3] | +0.8 [+0.1, +1.6] |
| tasksource-heldout all 24 families, acc (2788) | +2.3 [+1.1, +3.4] | +2.9 [+1.7, +4.2] | +3.6 [+2.4, +4.8] | +3.4 [+2.2, +4.7] |
| hard-v1 acc (1083) | +9.3 [+6.8, +12.0] | +11.2 [+8.6, +13.8] | +12.7 [+10.1, +15.4] | +12.7 [+10.0, +15.3] |
| Kev panel without hard-v1, acc (2268) | +1.0 [+0.2, +1.9] | +2.1 [+1.1, +3.1] | +2.2 [+1.3, +3.2] | +2.2 [+1.1, +3.2] |
| SemIf / WANLI-v2 / TypeSafe acc | +0.0 / +0.4 / +1.1 | −0.7 / +0.4 / +0.0 | +0.7 / +0.3 / +0.0 | +0.7 / +0.1 / +0.0 |
| ood-v2 / agents-ood / guardrails-ood acc | +0.2 / −0.2 / +3.5 | +0.3 / +0.0 / +3.7 | +0.6 / +0.3 / +4.1 | +0.5 / +0.5 / +4.1 |
| ood-v2 / agents-ood / guardrails-ood ECE Δ | −0.024 / −0.071 / −0.056 | −0.022 / −0.072 / −0.058 | −0.029 / −0.092 / −0.066 | −0.029 / −0.088 / −0.065 |
| CUAD ECE (Kev-27B 0.063) | 0.078 | 0.086 | 0.099 | 0.096 |
| CUAD ECE 16k+ (Kev-27B 0.071) | 0.077 | 0.090 | 0.102 | 0.104 |
| short-state acc, candidate (Kev-27B 0.9042) | 0.8985 | 0.8897 | 0.8979 | 0.8941 |

CUAD 按长度分层（accuracy / ECE；先列 Kev-27B）：< 8k（896）0.845 / 0.059，候选 0.848-0.853 / 0.083-0.096；8k-16k（452）0.834 / 0.063，0.832-0.847 / 0.081-0.106；16k-32k（454）0.841 / 0.070，0.837-0.848 / 0.082-0.105；32k-64k（452）0.832 / 0.072，0.830-0.838 / 0.083-0.108（各组臂见 `tables.md`）。生成的长文档项保持 1.000 accuracy。

**仅报告：对照第 25 轮在其运行相同比例处的 lr 1e-6 组**（s25 / s50 / s75 / final 对第 25 轮的 s25 / s50 / s75 / final；每一侧都使用各自的 pooled T；规则的面板加上 short states 拆分为 transfer-v4 development 与 transfer-r3 test；`runs/r26-readout/vs-r25.md`、`vs-r25-<arm>.json`，来自 `r26-vs-ref.py --ref r25`）：

| vs round 25 (panel, n) | s25 | s50 | s75 | final |
|---|---|---|---|---|
| T: round 26 / round 25 | 1.350 / 1.289 | 1.350 / 1.260 | 1.203 / 1.289 | 1.320 / 1.350 |
| breadth gated acc (2475) | −0.2 [−0.8, +0.4] | −0.0 [−0.6, +0.5] | −0.3 [−0.9, +0.3] | +0.2 [−0.3, +0.7] |
| breadth gated ECE Δ | −0.002 [−0.012, +0.010] | −0.004 [−0.013, +0.005] | +0.000 [−0.009, +0.010] | −0.000 [−0.008, +0.008] |
| tasksource-heldout gated acc (1993) | +1.7 [+0.7, +2.7] | +0.4 [−0.6, +1.5] | +0.6 [−0.5, +1.6] | +0.5 [−0.5, +1.5] |
| tasksource-heldout all 24 families (2788) | +1.1 [+0.2, +2.0] | +0.8 [−0.2, +1.7] | +0.6 [−0.3, +1.6] | +0.6 [−0.2, +1.6] |
| Kev panel acc (3351) | +0.7 [+0.0, +1.4] | −0.2 [−0.9, +0.5] | −0.2 [−1.0, +0.5] | −0.7 [−1.4, +0.0] |
| hard-v1 acc (1083) | +3.0 [+1.2, +4.9] | +1.0 [−0.6, +2.7] | +0.9 [−0.8, +2.6] | +0.2 [−1.4, +1.8] |
| short acc (1586) | −0.1 [−0.6, +0.4] | −1.1 [−2.1, −0.2] | +0.1 [−0.7, +0.9] | −0.3 [−1.1, +0.5] |
| transfer-v4 development acc (576) | +0.2 [−0.3, +0.9] | +0.2 [−1.2, +1.7] | +1.2 [+0.2, +2.6] | +1.2 [+0.2, +2.6] |
| transfer-r3 test acc (1010) | −0.2 [−1.1, +0.5] | −1.9 [−3.2, −0.8] | −0.5 [−1.6, +0.4] | −1.2 [−2.2, −0.3] |
| short confident errors | −0.5 [−1.0, −0.1] | −0.4 [−0.9, −0.1] | −0.4 [−0.9, +0.0] | −0.4 [−0.9, +0.0] |
| CUAD acc (2254) | +0.6 [+0.1, +1.1] | −0.2 [−0.5, +0.0] | +0.0 [−0.3, +0.3] | +0.0 [−0.2, +0.3] |
| CUAD ECE Δ | −0.008 [−0.017, +0.001] | −0.012 [−0.018, −0.005] | −0.002 [−0.008, +0.003] | −0.007 [−0.012, −0.001] |

**本轮说明了什么**（development 读数，单轮）：
- **把 tasksource-v1 记录翻倍并未提高 breadth 增益。** 对照第 25 轮相同比例处的组，breadth 在每个点都持平（−0.3 到 +0.2，每个区间都跨越 0），并且 final 的秩分数与第 25 轮相等（+9.8）。Tasksource-heldout 仅早期偏高（s25 +1.7 [+0.7, +2.7]）；到 final 时增益为 +0.5 [−0.5, +1.5]。对照 Kev-27B，breadth primary 为 +0.5 到 +1.0（第 25 轮 lr 1e-6：+0.6 到 +0.9）。
- **breadth ECE 也未变动：** 0.0197-0.0287，而第 25 轮在相同比例为 0.0227-0.0283；相对第 25 轮的配对差异为 −0.004 到 +0.000，所有区间都跨越 0。
- **注册中针对 short-state 漂移所点名的疑点（replay 占比 23.5 % 而非 30.2 %，458 步而非 356 步）只表现出微小影响，且仅限于 transfer-r3 test：** short-state 面板相对 Kev-27B 读数为 −0.6 到 −1.5 pp（第 25 轮 lr 1e-6：−0.3 到 −0.8），且 s50 未能通过保护阈值。对照第 25 轮，损失出现在 transfer-r3 test（s50 −1.9 [−3.2, −0.8]，final −1.2 [−2.2, −0.3]），而 transfer-v4 development 有增益（s75 与 final 处为 +1.2 [+0.2, +2.6]），并且 short-state confident errors 下降（−0.4 到 −0.5 pp）。
- **CUAD 校准比第 25 轮略好，但并未修复：** CUAD ECE 0.078-0.099（第 25 轮 0.087-0.103，Kev-27B 0.063）；final 相对第 25 轮 final 为 −0.007 [−0.012, −0.001]。它仍随步数增长（s25 0.078 → final 0.096）。
- **温度（仅报告，`runs/r26-readout/breadth-ece-by-t.json`、`both-bars-by-t.json`）：** 与第 25 轮一样，gated breadth 面板中 ECE 最小化的 T 为 1.44-1.56，高于每一个 pooled fit，而 tasksource-heldout 的 T 为 0.92-1.14（`27b-k-w85`：1.32 和 1.10）。与第 25 轮不同，对于 s50 和 final，pooled 90 % 区间内的某些温度能同时满足两条 ECE 约束（41 点网格：s50 14 个点，T 1.368-1.447；final 6 个点，T 1.367-1.408；final 最接近的点 T 1.372 读数为 breadth 0.0168 和 tasksource-heldout 0.0473）。对于 s25 和 s75 则没有点满足。规则服务于 pool fit，因此这不改变任何 verdict。

**仅报告：对照第 23 轮已确认的 `27b-k-w85`。** 没有点名候选，因此每个组都参与比较。
- **方法：** 每一侧使用各自的 pooled T（w85 1.320）。对 development 读数做配对 bootstrap，使用相同的面板与排除项，并将 `short` 拆分为 transfer-v4 development 与 transfer-r3 test。
- **文件：** `runs/r26-readout/vs-w85.md` 与 `vs-w85-<arm>.json`，来自 `runs/r26-readout/r26-vs-ref.py --ref w85`（w85 行从 round-23 的 checkout 读取）。
- **结果：w85 在几乎每个面板上都领先或持平。**
  - 对照 final：breadth −0.6 [−1.4, +0.2]，tasksource-heldout −0.9 [−2.2, +0.4]，Kev panel −2.6 [−3.6, −1.7]（hard-v1 −5.3，其余 −1.3），agents-ood −1.6 [−2.2, −1.0]。
  - short states 持平：−0.1 [−1.0, +0.9]；transfer-v4 development +0.0 [−1.6, +1.7]，transfer-r3 test −0.1 [−1.2, +1.0]。候选有更高的 confident errors：short +0.9 [+0.4, +1.5] pp。
  - CUAD accuracy 持平（−0.6 [−1.7, +0.4]），CUAD ECE −0.001 [−0.014, +0.009]。按长度，w85 读作 0.856 / 0.096（< 8k）和 0.839 / 0.102（16k+），对照分别为 0.849 / 0.093 和 0.834 / 0.104。w85 的 breadth ECE-by-T：在其 pooled T 处为 0.0103。
- **排序：** 没有任何第 26 轮的组在规则所设的任何面板上以高于 0 的下界领先 w85。仅报告例外项为：s25 处的 CUAD ECE（−0.019 [−0.032, −0.007]）和 s50（−0.012 [−0.024, −0.001]），以及 s75 处的 ood-v2 ECE（−0.005 [−0.010, −0.001]）。Kev-27B 与 `27b-k-w85` 仍是 Jared 的发布可选项（"Round 23 confirmation"）；此处的发现不改变该选择。

**偏差：**
- **(i) final 的读数通过已注册的支出闸门启动，而非由 watcher 启动。** watcher 在没有闸门的情况下启动一个已完成 trial 的读数。在 trial 结束时，预计支出（约 $160-200）加上两个运行中的批次（$802）再加上 final 的（$401）可能已突破 $1,373。因此 watcher 在 08:02Z 被停止（当时 trial 仍在训练），并由一个本地辅助脚本（`runs/r26-readout/r26-finish.sh`）替代。该辅助脚本轮询 trial 的调用，准备在超时时立即重启 watcher。它等待 `27b-lr1e6-s75` 的启动，然后等待闸门，再于 10:13Z 重启 watcher。watcher 拉取 study，启动一次 final 的读数并写出 read-out。顺序（trial 结束时的 s75，然后 final）是注册中的挂钟计划。
- **(ii) 闸门按整批计数，与注册一致**（`runs/r26-readout/r26-gate.py`）：trial 调用运行时为 $494，而每个读批在其 16 个作业全部拥有 `report.json` 之前计 $400.97。它在每次启动前读取计量成本。启动（在 $4,453.81 的启动读数之上，闸门 ≤ $1,373）：
  - s25 于 07:37Z：$917.50；
  - s50 于 08:00Z：$1,346.60；
  - s75 于 09:32Z：$1,353.53。它在 08:26Z 快照完成时（$1,782.50）暂停，并在 study 的边界释放后启动。
  - final 于 10:15Z：$1,369.81。它从 09:36Z（$1,758.52）起暂停，直到 s25 的批次落地。
  辅助脚本为 `runs/r26-readout/r26-autolaunch.sh` 与 `r26-finish.sh`；它们是原本位于 `runs/` 的运行脚本的副本。
- **(iii) 一个辅助脚本的 bug，无影响。** 快照启动器最初在 `checkpoint/` 的上一级目录寻找 `snapshot.json`。它在 07:36Z 被修复并重启，在 s25 快照提交后一分钟内，并立即启动了 s25。
- **(iv) 没有读数失败。** 私有套件的 development 分区在部署前已存在于 checkout 中（经 sha256 与其 manifest 校验），因此全部 64 个读数首次运行即成功。最后一个读数于 12:53Z 落地。部署、训练与读数运行在 app `kev-r26` 上，部署的 app 于 12:57Z 停止。`kev-sft` 未被触碰。

**支出**（Modal 计量，全工作区）：
- 启动读数时为 $4,453.81（07:03Z），对照注册时约 $4,454。
- 启动前的读数：$4,464.25（07:16Z）、$4,476.34（07:36Z）、$4,504.47（08:00Z）、$4,539.40（08:26Z）、$4,604.43（09:32Z）、$4,620.71（10:13Z）、$4,650.37（11:17Z）。
- 最后一个读数之后的 12:56Z 与 13:01Z 为 $4,558.69。这低于 11:17Z 的读数，因此计量被向下修订。
- 总计：在最新读数上较启动读数 **+$104.88**（在 11:17Z 读数上 +$196.56），用于一个一次尝试的 study（列表价约 $100）与 64 个读数。计量滞后尚待结算。预计为约 $4,680-4,710。当晚的支出上限约 $5,980，硬停止于 $5,700。

**证据**（已提交）：
- read-out、其表格以及仅报告的附加项（`vs-r25*`、`vs-w85*`、`breadth-ece-by-t.json`、`both-bars-by-t.json`），以及写入它们的脚本和位于 `runs/r26-readout/` 下的闸门 / 启动辅助脚本。
- 启动记录 `runs/r26-reads-*.json`。
- 每个公共套件读数的 report 与行（`runs/r26-27b-<arm>-<tag>`）；对于 OOD 读数，仅 report。
- 对于 trial：`provenance.json`、`result-public.json`（不含逐任务表）、trial 内的 transfer 行与温度、`training_metrics.json`，以及三份 `snapshot.json` 记录。

私有（`jaredpalmer/kev-private-train` @ `2f2c44d3`，位于 `runs/r26/` 下，sha256 见 `runs/r26-readout/private-rows.json`；用 `scripts/private_rows.py restore` 恢复）：
- 四份 tasksource-heldout-v1 读数（行与 report）；
- ood / agents-ood / guardrails-ood 行；
- trial 的 development 行与完整 `result.json`。

Checkpoint（每个约 51 GB：3 个快照 + final）保留在 `kev-runs` 卷上。

**下一步**（提议，未注册；每一项都需要自己的 spec）：
- **在 lr 1e-6 上增加更多 breadth 数据并非杠杆。** 同一配方运行两轮（13,000 与 26,000 份 tasksource-v1 记录）读出了相同的 breadth accuracy 与相同的 breadth ECE。在 Kev panel 上相对 w85 的差距（hard-v1 −5.3）和在 breadth 上的差距（−0.6）也保持不变。
- **breadth-ECE 失败现在落在 final 的温度采样噪声之内。** 其 pooled 90 % 区间内的温度满足两条 ECE 约束。若要做一轮实验来检验一个更大或不同的 held-out 池（在 transfer-r3 的八个源与 MMLU-Pro 之外加入更多 held-out 公共源）是否拟合出一个能同时服务于 breadth 与 tasksource-heldout 的 T，则无需训练即可直接验证。池的变更必须在任何在该池下进行的读数之前注册。
- **short-state 漂移与 replay 占比相关。** 当 replay 从 30.2 % 降到 23.5 % 时，transfer-r3 test 相对第 25 轮下降。从 Kev-27B 出发的任何进一步 continued-SFT 轮都应保持 replay 占比，而不是 replay 数量。

## Round 27（已注册）

**问题。** 第 18 轮的 9B documents-and-skills delta 在经审计的规则下是否构成 Kev-9B 候选？第 18 轮（2026-09-24）未选出任何 9B 候选：组 (a) 通过了两个 primary（skills +19.0，documents +7.0），仅未通过 WANLI-v2、scienthoon 以及 pooled externals，而这些此后都已被移除或取消设限（scienthoon 已移除、审计、"WANLI 与 TypeSafe 已移除"）。第 18 轮的 verdict 仍然成立；这是在其两个已完成 trial 之上的一个新的、已注册的筛选，无需训练。

**组**（checkpoint 在卷上；其 development 读数来自第 18 轮，未变）：`9b-r18a` = `runs/r18-9b/00-trial-0`（lr 2e-5），`9b-r18b` = `runs/r18-9b/01-trial-1`（lr 1e-5）；父模型为已发布的 Kev-9B（`jaredpalmer/kev-9b@2629c06a`、`night2-9b-du/00-trial-0`、其第 18 轮读数）。

**规则**（第 18 轮的规则，并如第 24 轮那样应用了 2026-09-27 审计的 verdict）：primary 为 hard-v1 + devtools-v1 development pooled accuracy 下界 > 0，以及 documents-v1 development 下界 > 0；保护阈值为：short state（transfer-v4 dev + transfer-r3 test，不含 `emotion`）accuracy 下界 ≥ −2 pp、Brier 上界 ≤ +0.02、confident errors 上界 ≤ +1 pp；unknowable 占比 ≤ 0.05（transfer-v9）；hard-v1 ECE ≤ 父模型 + 0.01。devtools-v1 在每个面板中去掉 `flakeflagger` 与 `commitpackft_type` 任务（审计的 Kev-panel 排除项）。不做 WANLI、TypeSafe、scienthoon 或 pooled external 读数；SemIf 为报告项（可选）。候选：通过的两个 primary 估计值之和更大的组。

**温度。** 每个组都在一个温度上提供服务，该温度拟合于第 24 轮的 held-out 池（transfer-r3 calibration 的八个源 + transfer-v9 的 `mmlu_pro`，90 % bootstrap 区间；固定规则：绝不使用 in-distribution 分区），而非每个 trial 的 head 所携带的 in-distribution T。`trained_on` 列出 decision-v7、documents-v1 与 round10/skills（round15/joint 是它们的拼接）；它遗漏了 `evals/night2`（已发布的 Kev-9B 的 delta），其 manifest 未列出任何源，因此引擎无法检查它：其记录是四个合成族（`night2_dates`、`night2_assertion`、`night2_unknowable`、`night2_unknowable_control`），均不在池中。父模型保留其发布的 T 2.30。

**确认**（第 18 轮的规则，使用相同的排除项）：hard-v1 + devtools-v1 test pooled 下界 > 0 且 documents-v1 test 下界 > 0（documents-v2 为报告项）；锁定的 transfer-v4 accuracy ≥ 父模型 − 1 pp，且服务的 Brier ≤ 父模型 + 0.005。

**非盲。** development 读数于 2026-09-24 做出，其头条数字在 "Round 18 result" 中；移除 WANLI-v2 的 WANLI 分析将组 (a) 与父模型进行了比较。在已经看过的读数上从两个已完成组之间进行选择是乐观的；未触及的 test 分区与锁定的读数是保护手段。发布一个新的 Kev-9B 仍需 Jared 的明确同意。

## Round 27 结果（2026-09-30）— Kev-9B v2 已确认

两个组都通过了每一项判据（`runs/r27-readout/round27.json`）；候选为 `9b-r18a`（lr 2e-5，primary 之和更大）。以池温度提供服务（组 (a) T 2.194 [2.047, 2.406]，组 (b) 2.000，648 个问题）；对照以其发布值 2.30 提供服务的已发布 Kev-9B：

| arm | primary (hard + devtools dev) | hard-v1 dev | devtools-v1 dev | documents-v1 dev | short acc | short Brier | hard ECE |
|---|---|---|---|---|---|---|---|
| 9b-r18a | **+19.3 [+17.2, +21.6]** | +23.8 | +13.0 | **+7.0 [+4.8, +9.2]** | +0.1 [−1.1, +1.2] | −0.000 [−0.009, +0.009] | −0.023 |
| 9b-r18b | +16.5 [+14.4, +18.7] | +19.0 | +13.0 | +6.4 [+4.3, +8.6] | −0.4 [−1.5, +0.8] | +0.003 [−0.006, +0.011] | −0.014 |

**9b-r18a 的确认**（`runs/r27-verdict/9b-{tests,locked}.json`，各读一次）：tests 通过 — hard-v1 + devtools-v1 test pooled +18.7 [+16.7, +20.8]（hard-v1 +25.0，devtools-v1 +9.9，含审计排除项），documents-v1 test +7.1 [+4.7, +9.2]，documents-v2（报告）+8.0 [+5.9, +10.2]；locked 通过 — transfer-v4 test accuracy +0.0 [−1.7, +1.8]（双方均为 0.852，边界 −1 pp），服务的 Brier −0.025 [−0.047, −0.007]（0.199 对 0.224）。父模型的 test 读数是 `jaredpalmer/kev-9b@2629c06a` 于 2026-09-30 的族读数（`runs/r27c-9b-parent-*`）。基础设施：spec 中的 `app` 为 `kev-r27`（注册的 `kev` 未指定部署的 app，且首次 locked 启动在读取任何数据前就失败了）。

## 已发布：Kev-9B v2（2026-09-30）

- Hub：v1（`2629c06a`）先打上 `v1` 标签；v2 由 `modal_app.py::release_publish --public --confirm-public jaredpalmer/kev-9b --replace` 从 `/runs/release/kev-9b-r27/checkpoint` 上传，在一个提交（`b5d8c18e`）中完成：adapter 的 sha256 为 `2b2a70cf…`，`head.pt` 为 `8e1dab2c…`（T 2.1936）；模型卡为 `docs/model-cards/kev-9b.md`。`--replace` 丢弃了 v1 的 `train.log`，该文件仍保留在标签处。
- 暂存副本：由 `modal_app.py::release_copy` 从 `/runs/r18-9b/00-trial-0/checkpoint` 复制（adapter 哈希相同）；`head.pt` 的 T 由 `scripts/calibrate_checkpoint.py --temperature ... --reason ...` 设为该轮的池拟合值（它无法列出 round15/joint 的源以重新拟合；`kev.rounds validate` 已将该池与该组的 `trained_on` 做过检查）。
- 验证（`modal_app.py::release_verify`，全新的 HF 缓存，无 token；`runs/rel9-public/`、`scripts/compare_release_rows.py`）：semif-v1 的 252 行中有 252 行、transfer-v4 development 的 764 行中有 764 行的 argmax 与第 18 轮在 T 2.19 下的原始读数相等（最大 |Δp| 分别为 0.0014 与 0.0015；与在另一块 GPU 上 trial 内做出的读数并非逐位精确）；`@v1` 以 T 2.30 加载 v1 并复现其服务的 semif-v1 读数（最大 |Δp| 0.0008，0 次翻转）。
- 数字：`experiments/releases/kev-9b-r27.json` → `runs/release/kev-9b-r27.json`；README 的 Models 行、calibration 与 limits 文本、图表（`scripts/plot_family.py`、`scripts/plot_tweet.py`）、AGENTS.md、声明（901 项已验证）。GitHub release `kev-family`：从 Hub 提交重建的 `kev-9b.tar.gz`（外加 `locked_test.json`），`SHA256SUMS.txt` 已重新生成。
- kev-deploy / kev-finetune 的 `KEV_REF` 引脚未变：v2 是同形状的一个 adapter，由相同代码提供服务。

## 已发布：Kev 1.0（2026-10-01）

Jared 批准发布 PR #206 的包。未训练或重新读取任何内容；步骤为 `docs/releases/kev-1.0.md` 的维护者计划，记录为 `runs/release/kev-1.0.json`。

- **Hub.** 每个 1.0 模型卡作为仅含卡内容的提交中的 `README.md` 上传（其 `parent_commit` 为该提交之前的主分支），然后在该提交上打上注释标签 `v1.0`，因此 `@v1.0` 显示的是 1.0 模型卡（计划步骤 4 的替代方案）。每次上传之前，主分支已有发布权重：0.8B、4B 与 9B 的主分支是权重修订，而 27B 主分支（`ef78cc8a`）与 `28be62e9` 仅在 `README.md` 上不同。每次上传之后，所有其他文件拥有相同的 blob 与 LFS sha256，`README.md` 与仓库卡逐字节匹配，且 `card_data` 能使用该卡的 `base_model` / `base_model_relation` 解析。

  | repo | weights | `v1.0`（卡提交） | adapter / head |
  |---|---|---|---|
  | `kev-0.8b` | `9a45d25e` | `bf75a6a8` | `9b908623…` / `f400bd12…` |
  | `kev-4b` | `139fdd94` | `6cfce5c2` | `90e81735…` / `dd633435…` |
  | `kev-9b` | `b5d8c18e` | `db029f08` | `2b2a70cf…` / `8e1dab2c…` |
  | `kev-27b` | `28be62e9` | `af0e6d55` | 11 个分片未变 / `7968f17b…` |
- **GitHub.** release `kev-1.0`（标签位于 PR #206 的合并提交 `6b719c3` 上）已发布并标记为 Latest。其正文为 `docs/releases/kev-1.0.md` 中维护者计划之上的部分，该计划现已包含 Assets 节。资源来自 `scripts/build_release_assets.py`，第二次构建给出了相同的 `SHA256SUMS.txt`：`kev-0.8b.tar.gz` `0ae144c7…`、`kev-4b.tar.gz` `2e707e2e…`、`kev-9b.tar.gz` `acd13320…`、`SHA256SUMS.txt` `495d104f…`（`runs/release/kev-1.0-{SHA256SUMS.txt,manifest.json}`）。Kev-27B 作为 `jaredpalmer/kev-27b@v1.0` 链接。这些是替换资源。首次上传（`943891a2…`、`6f87da10…`、`90518850…`，校验和 `bc5c520e…`）将每个文件的 mtime 清零，因此 `kev.serve` 将解包后的 checkpoint 的发布日期报为 1969-12-31。PR #209 使构建器打上 2026-10-01 00:00 UTC 的戳（`SOURCE_DATE_EPOCH`），并使 `Checkpoint.release_date` 读取 UTC 并跳过 2000 年之前的 mtime。tarball 于当日重建并替换。其成员逐字节相同；只有 mtime 不同（`runs/release/kev-1.0.json` 的 `github.replaced_assets`）。
- **kev-family**（计划步骤 7）已退役但未删除。其三个 tarball 与 `SHA256SUMS.txt` 在确认其中 adapter 与 head 与 1.0 逐字节相同后被移除。它更名为 "Kev family (superseded by Kev 1.0)"，其正文是指向 `kev-1.0` 的指针，列出被移除资源的哈希，其标签保留。其旧说明位于 `runs/release/kev-family-notes-retired.md`。
- **验证.** 每个 `jaredpalmer/kev-<size>@v1.0` 都通过 `kev.checkpoint` 在无 token、全新缓存下解析。它解析到其卡提交，adapter、head 与 27B 分片哈希匹配，温度分别为 2.35 / 2.41 / 2.19 / 1.32。在一个 2 条记录的冒烟基准（`evals/smoke-v1` development，MPS，fp32）上，来自标签的 0.8B 与 4B 均得 2 / 2，且来自发布的 `kev-0.8b.tar.gz` 给出的 logits 与标签的相同（`runs/release/kev-1.0-verify/`）。解包后的 tarball 服务了一个 System One 请求。这些资源被再次匿名下载且 `shasum -c` 通过。集合列出了全部四个仓库。Space 处于 RUNNING 状态，且 `/decide` 在 Kev-4B 与 Kev-0.8B 上作答。它未重新发布：其 vendored 的 `kev/checkpoint.py` 仅缺少 #200 的 MLX full-weight 路径，而 Space 不使用该路径。
- `KEV_REF` 引脚（71d4829）未变：1.0 的 checkpoint 不需要更新的代码。

## 下一步

目标与开放问题，非已注册轮；每一项在运行前都成为一份 spec 与一个 PLAN 小节。

0. **第 21 轮：以长上下文和扩展数据重新训练全权重。** 已注册："Round 21（已注册）"与 `experiments/rounds/r21.json`；它在启动阶段失败（内存不足，无读数），并以每遍内存上限与更小的训练集重新注册为第 22 轮；第 22 轮读出无候选（"Round 22 result"），而第 23 轮将其 final 向 Kev-27B 混合（"Round 23（已注册）"）。第 21 轮失败点的两个 trainer 后续项不在第 22 轮中：带填充的多状态遍以显式 mask 运行长状态（两个不等长约 19k 状态每步 38.7 s，而一个 32k 状态为 18.7 s），因此将不等长状态打包为 varlen，或按长度分桶的步长，可节省时间；且每个起始都要在每一 rank 上花费约 10 分钟来统计状态 token，各 rank 可以分摊此工作。以下说明是第 21 轮起步时的情形；其注册记录了偏离之处（32k 状态；PR #153 下没有任何配对在 8k token 处设限；sft-v1 的公共源上限为 1,200 条训练记录；calibration / development 仅限于至多 8k token 的状态）。允许重新训练（第 19-20 轮表明事后补救措施无法移动 accuracy 保护阈值）。注册前已决定的事项：
   - 上下文：64k token 为目标，32k 为回退，16k 为最后手段（拟合探测在注册前决定）。
   - 数据：`sft-v1` 扩展为一个新版本。
   - 快照：保留（步数的 0.25 / 0.5 / 0.75，#145），作为报告读取。
   - 校准：第 20 轮的 held-out-datasets 池方法。
   - *（已于 2026-09-27 关闭：scienthoon 已作为 eval 移除，见 "scienthoon removed"；以下两条 scienthoon 项按原样保留。）* scienthoon 的补救遵循第 20 轮的分析（`runs/r20-scienthoon/analysis.md`）。将 scienthoon 与 pooled-externals 的保护阈值重新注册为针对 Kev-27B 单次最佳抽样的对照（Jared 在注册时的决定）：要么对照 LoRA 族，要么将 scienthoon 在不计文本不可知 `priority` 的情况下打分。向数据中加入一个小型开放权重的语气最小对族（同一问题的平静与愤怒措辞，其他领域，英文与韩文，无 scienthoon  paraphrase）。报告平静文本中将 `angry` 误报的情况。该分析反对向 Kev-27B 的答案做 KL anchor，因为其优势是一次种子抽样，而其训练数据无法修复这一点。
   - 可选，约 $6：对未训练的基座在 scienthoon 上做一次 zero-shot 读数，以确定基座更接近 Kev-27B 还是各 arm。
1. **Kev-27B 的 SFT 程序：在广泛数据上做 full-weight SFT，并正确地做 calibration。** 发现 1、5、7 指向此处。注册前需确定的问题：
   - 数据：在以上策略下构建什么样的广泛决策语料（源、规模、开放权重 teacher、针对 JevBench 公共项与我们冻结套件的污染筛查），以及其中多少用来替换或并入 decision-v7 replay。
   - 方法：在当前 LoRA 配方相同的数上做 full-weight SFT，以使方法数据与数据分离（AutoJev 比较将二者混淆）。训练器已存在（`kev.train --full_ft 1`，PR #122；checkpoint 为 51 GB 的 `save_pretrained` bf16 backbone 加 `head.pt`，由相同的 `kev.checkpoint` 路径加载，含融合内核与 CUDA 图）。后续项（PR #125）在训练中加入了共享前缀（每个状态一次，其问题由其派生；与行形式精确一致）、按填充长度平衡的 micro-batch、恢复点（逐位精确延续；full-weight trial 在超时后重试并继续）以及 24 小时 full-weight study。在 Qwen3.8-27B、8 块 H200、记录形状类似 SFT 语料（`experiments/sft-v1-lengths.json`、`runs/sft-probe/sft2-*`）上测得：完整混合（公共 94k + 组件 38k + 合成 60k）为 7.6 记录/秒，一个 epoch 约 7.1 小时、$293，两个约 14.1 小时、$582，这还不包括 trial 内读数；恢复点（约 307 GB）约阻塞训练 23 秒，并在其后约 2.5 分钟内写入。仅合成部分在共享形式下为 7.3 记录/秒，而行形式下为 2.7（相同的平衡批处理）。开放项：发布隔离容差下的 27B 服务路径。
   - 校准：在一个混合 development 池（decision-v7 + hard-v1 + devtools-v1）上拟合服务温度，并以 hard-set calibration 为门槛，而非仅针对简单行（发现 5）。
   - 评估：每个现有的 short-state 确认面板至少已被读取一次，因此该轮需要一个全新的冻结面板；AutoJev 的 head-to-head 套件作为比较；JevBench 的密封半区仍作为外部检查。
   - 27B LoRA skills 路径已在 replay 4,000（第 10 轮）与 10,000（第 17 轮，组 (a)）处未通过外部保护阈值，因此 B1 v2（已发布的 Kev-27B）仍是 27B 基线，且更多 replay 并非补救措施；本程序所加入的数据广度才是。第 17 轮组 (b) 在落地后报告。
2. **除 replay 之外的 9B 补救措施**（发现 4）：一个朝向已发布 Kev-9B 在 replay 记录上的自身服务答案的 KL 项（`kev.anchors` 当前以冻结基座的 zero-shot 答案为目标；这里需要以已发布模型的分布作为目标），或更广的 replay。
3. ~~**发布 documents-v1 与 hard-v1 训练分区**~~ 已于 2026-09-30 完成：两个训练分区（各 23 MB，不在 git 中）位于 `jaredpalmer/kev-suites` 的 `cc4bac803e73112689ec327ffa481c519cbc7a05`，现即 `SUITES_REVISION`，且 `load_split` 会获取并哈希校验它们（hard-v1 `a08ca9c5…`，上传前由 `scripts/build_hard_v1.py` 逐字节重新生成；documents-v1 `2d7e4c43…`，公共领域 CFPB 文本含 teacher 同意的标签）。devtools-v1 的训练分区（8.9 MB）已在 git 中。仍未进入公共镜像：第 4/5 轮的 delta 文件（`evals/round4/*`、`evals/round5/*`，由其构建器重新生成）与 `evals/round6/b1v2/train.jsonl`（在私有 kev-private-train 中）。
4. **Decision Index 提交**，针对 Kev-27B 与当前的 Kev-4B / Kev-0.8B。
5. 较小的开放项：rotation-averaged Choice 已通过其第 4.4 轮的门槛（在 9B 处置换翻转 0.028 → 0.000）并等待产品决策（它会增加延迟）；日期算术在每个规模上仍是最弱族（发现 9）。

## Round 28（已注册）

### Round 28 - 小型族的已发布温度在 held-out 数据集上重新拟合，以及每个规模的经校验上下文长度（事后，无训练；随本 spec 的提交注册，在任何第 28 轮读数之前）

**为何。** Kev-4B（第 10 轮，`r10-skills/00-trial-0`，Hub `139fdd94`，T 2.41）与 Kev-0.8B（第 15 轮，`r15-08b/00-trial-0`，Hub `9a45d25e`，T 2.35）发布的温度拟合于它们 trial 的 decision-v7 development 行。这些行是训练语料的 held-out *项*：第 19 轮的失败模式，`docs/autoresearch.md` §3.4 现已禁止将其用于任何已发布温度（发现 5）。`kev.rounds.temperature` 在这些行上复现了发布值（4B 2.406，0.8B 2.351）。Kev-27B v2（T 1.32）与 Kev-9B v2（T 2.19，第 27 轮的 `9b-r18a`，自 2026-09-30 起为 `jaredpalmer/kev-9b` 主分支，Hub `b5d8c18e`，PR #195）已经发布 held-out 池的拟合值，因此 Kev-9B 在此不是组。其池 T 即其发布 T，其上下文长度在第 29 轮对同一 checkpoint 的读取上测量。argmax 不依赖于 T，因此本轮仅关乎校准。按构造，每个面板上的 accuracy 完全相同，但它仍被报告。

**组**（`experiments/rounds/r28.json`）。`4b-r10` 与 `08b-r15` 为已发布的 checkpoint，每个都以拟合于下述池的温度提供服务。每个组的父模型为同一 checkpoint 在其发布 T 处。引擎以 trial 的 development-rows 拟合来服务父模型，此处即发布 T。双方读取相同的行，因此每个 delta 都是同一 checkpoint 在两种温度下的 logits 的配对比较。

**温度池**（第 20-27 轮的，未变）：transfer-r3 calibration 分区的八个 held-out 源加 transfer-v9 的 `mmlu_pro`，减去 transfer-v4 development 记录，带 90 % bootstrap 区间（`temperature.ci`）。`trained_on` 列出每个 checkpoint 的训练内容：
- Kev-4B：night-2 4B，然后第 8 轮的 documents-v1 delta（2,000 decision-v7 replay），然后第 10 轮的 hard-v1 + devtools-v1 delta（`evals/round10/skills`，4,000 replay）。
- Kev-0.8B：night-2 0.8B，然后第 15 轮的 joint documents + skills delta（6,000 replay）。
- 两个组都列出 `evals/v7/decision-v7`、`evals/documents-v1`、`evals/round10/skills`、`evals/hard-v1` 与 `evals/devtools-v1`。`evals/round15/joint` 是这些的拼接，其 manifest 未列出任何源。
- `evals/night2` 如第 27 轮那样被遗漏。其 manifest 未列出任何源，因此 `validate` 会因其不可列出而拒绝作为训练。其记录是四个合成族（`night2_dates`、`night2_assertion`、`night2_unknowable`、`night2_unknowable_control`），且均不在池中。

`kev.rounds validate` 发现**无池冲突**：每个组 24 个训练源，均未被池化。作为健全性检查，向某组的 `trained_on` 加入 `evals/round3/transfer-r3` 会使其拒绝该轮。

**规则**（池-T 侧减去发布-T 侧，配对 record-clustered bootstrap，2,000 次重采样，seed 0，micro；`drop_ids` 如第 24 与 27 轮）：
1. Primary：池 T 必须在 **breadth-v1 dev + tasksource-heldout-v1 dev pooled** 上严格更好地校准，使用审计后的排除项（breadth 不含 `routerbench`、`cfcolor`、`humicroedit`、`chessbench`；tasksource-heldout 不含第 24 轮私有列表的七个族，`runs/r24-private/tsheld-exclude.json`，sha256 `a72030ab…`）。两个条件：Brier delta 的上界 < 0，**且** ECE（池）< ECE（发布）。
   - 为何由 Brier 承载区间：`kev.rounds` 对两个指标都做 bootstrap。Brier 是适当分数且逐问题可加，因此其 record-clustered bootstrap 是精确统计量，它也是 locked 阶段所读取的内容。
   - ECE 是分箱的（10 个箱）且不可加，因此其重采样差异带有分箱噪声（审计测得每个面板的 ECE 采样标准差为 0.006-0.010）。
   - ECE 的点条件阻止一个朝更好 Brier 但更差可靠性 sharpen 的温度通过。
2. 保护阈值：对每个面板，ECE（池）≤ ECE（发布）+ 0.005：
   - breadth-v1 dev（已审计）；
   - tasksource-heldout-v1 dev（已审计）；
   - transfer-v4 dev，trial 内读数，不含 `emotion`；
   - hard-v1 dev；
   - devtools-v1 dev，不含 `flakeflagger` 与 `commitpackft_type`；
   - documents-v1 dev。
3. 候选：通过的一个组。每个规模只有一个组，因此该组即该规模的候选。

仅报告（可选面板，从不设限）：accuracy（相同）与每个面板上的 Brier；transfer-v9 上的 unknowable 占比；跨全部 14 个源的 breadth；跨全部 24 个族的 tasksource-heldout；ood-v2、agents-ood-v1 与 guardrails-ood-v1 的 accuracy 与 ECE；longdoc-v1 dev 在每个长度桶与两种温度下的 accuracy 与 ECE。按长度面板使用边界 4,096 / 8,192 / 16,384 / 32,768（桶 `under_4k` … `32k_plus` = longdoc 名义上的 4k / 8k / 16k / 32k / 64k）。小型族的 tokenizer 对 longdoc 状态的计数与该套件的 Qwen3.8-27B tokenizer 完全一致（150 条记录上比值为 1.0000）。CUAD ECE 为仅报告项，因为其标签对校准不可靠（审计）。

**经校验的上下文长度**（仅报告，在此注册，不设任何门槛）。该规则由 `scripts/longdoc_report.py --context-margin -0.03`（`validated_context`，有单元测试）从每个规模的 longdoc-v1 development 读数计算：Kev-4B 与 Kev-0.8B 来自本轮，Kev-9B v2 来自第 29 轮对同一 checkpoint 的 `9b-r18a` 读数（或者，若第 29 轮替换了 v2，则来自该 checkpoint 的读数）。
- 统计量：对桶 b ∈ {16k, 32k, 64k}，与 **8k 桶**（状态 6,553-7,618 token：小型族训练所在的 4-8k 桶，`max_state` 7,552）的 CUAD accuracy 差异。它在相同的（目标合同、重复、问题）上配对，每桶约 445 个问题，带 95 % 目标聚类 bootstrap（2,000 次重采样，seed 0）。这正是 longdoc-v1 为之构建的 `cuad_paired_vs_8k` 统计量（#150）。
- 当 b 的区间下界 **≥ −3 pp** 且 b 与 8k 的每条记录都已作答时，b 在容差之内。
- 经校验的上下文长度 = 最大的桶的名义大小，使得该桶及其与 8k 之间的每个桶都在容差之内（16,384 / 32,768 / 65,536；65,536 为服务上限）。若 16k 失败，则为 8,192：即训练长度，而非扩展长度。未读取或部分读取的桶不在容差之内。
- 生成的一半、与 4k 控制的未配对差异、每个桶的 ECE 与每个桶的服务 accuracy 报告在其旁。
- 规模。在 Kev-27B 自身的读数上，配对区间每侧宽 1.5-1.7 pp（按此规则校验至 65,536），因此一个没有下降的模型约有 5 % 的概率未能通过某个桶。小型模型在不同长度间与自身的一致性较低，因此其区间会更宽。该规则随后会偏向 8,192：它低估而非高估。与 4-8k 桶的池化做未配对比较，要达到相同错误率需要约 7 pp 的余量。

**阻碍：在这些规模下长读数会内存不足。** 2026-09-30 族 longdoc-v1 *test* 读数以 `OutOfMemoryError` 失败（卷上的 `/bench/fam-*-longdoctest/failure.json`）：
- Kev-4B、Kev-9B v1 与 Kev-9B v2 在首个 32k 记录处（1,200 条记录中已评 720 条）；
- Kev-0.8B 在首个 64k 记录处（已评 960 条），在 H100 与 H200 上各一次。

Kev-27B 对同一套件的读数完成了，但它们运行的是 bf16 backbone。同一道墙会挡住 agents-ood-v1（373 个 development 状态中的 47 个超过 26k token，最大 51,148）与 guardrails-ood-v1（1,263 个中的 12 个，最大 39,072）。

一个可能但未验证的原因：这些读数以 fp32、head 大小为 256 运行。这排除了 SDPA 的 flash 内核，可能也排除了 memory-efficient 内核，只剩下 math 内核。其 fp32 L × L 分数在 4B 与 9B 于 32k 桶处约需 58 GB（16 heads × 30k² × 4 B），在 0.8B 于 64k 桶处约需 115 GB（8 heads）。这正好落在每个规模失败的位置。无论修复是什么，它都是评估器的改动：它自己的 PR，`kev-verify`，在这些读数之前。

在此之前，longdoc、agents-ood 与 guardrails-ood 读数为阶段 B（如下）并保持未启动。第 28 轮的 verdict 不需要它们（其长面板与 OOD 面板均为仅报告）。没有阶段 B，任何规模都没有经校验的上下文长度。

**确认**（针对其组通过的每个规模，做一次；由已存在的行计算，无新读数）：
- `tests`：breadth-v1 test（不含四个源）ECE（池）< ECE（发布），Brier 与 14 源面板报告。这些行是 2026-09-30 族读数 `runs/fam-4b-breadthtest` 与 `runs/fam-08b-breadthtest`（Hub checkpoint，原始 logits）。
- `locked`：transfer-v4 locked 服务 Brier（池）≤ Brier（发布）+ 0.005，且 accuracy 相同（两个判据，≥ 0 与 ≤ 0）。这些行是发布 locked 读数 `runs/locked/kev-4b-r10-ungated` 与 `kev-08b-r15-ungated`。
- 这些分区已为这些确切的 checkpoint 读取过一次，不再读取。在此注册之前尚未计算的是它们在池 T 下的校准，而池在查看任一组之前就固定了该 T。没有任何已提交记录报告这些 checkpoint 的 breadth-v1 test ECE。
- 然后 `scripts/calibrate_checkpoint.py` 以池模式将池 T 写入发布副本的 `head.pt`（`--rows <r3cal 行>:composition_holdout,emotion,legacy_holdout,mmlu,paws,qnli,sciq,tweet_offensive --rows <v9 行>:mmlu_pro --exclude_rows <transfer 行>`，相同的 `pool_conflicts` 检查）。发布它并将模型卡的服务数字迁移过去需要 Jared 的同意。

**本轮需要的、尚不存在的读数**（合并后的扫描；H100）。每个都是 `modal_app.py::benchmarks` 在其套件超时下的一个作业。`launch-reads --dry-run` 会打印它们，阶段 B 的作业须手工从批中剔除。

| phase | reads | count |
|---|---|---|
| A（现在） | `r28-{4b-r10,08b-r15}-{tsheld,r3cal,ood}` | 6 |
| B（内存修复后） | `r28-{4b-r10,08b-r15}-{longdoc,agentsood,guardood}` | 6 |

它使用的现有读数：breadth-v1 dev `runs/fam-{4b,08b}-breadth`；hard-v1 / devtools-v1 / documents-v1 / transfer-v9 `runs/r10-4b-skills-*` 与 `runs/r15-08b-a-*`；trial 的 trial 内 transfer-v4 读数；为确认用的 `runs/fam-{4b,08b}-breadthtest` 与两个 locked 读数。fam-* 行仅在卷上（`modal volume get kev-runs /bench/fam-4b-breadth runs/`）；其余在研究 checkout 中。预算与下面的第 29 轮共享。

## Round 28 结果（2026-10-01）— 任一规模都无候选；经校验上下文 8,192（0.8B、4B、9B v2）与 65,536（27B v2）

**Verdict**（`runs/r28-readout/round28.json`，在全部阶段 B 面板就位后重读；与 PR #203 中阶段 A 的 read-out 未变）：无候选。Kev-4B 保留 T 2.41，Kev-0.8B 保留 T 2.35。
- `4b-r10`（池 T 2.297 [2.047, 2.520]）未通过两个 primary 条件：Brier −0.0001 [−0.0005, +0.0003]，ECE 0.0252 对 0.0240。
- `08b-r15`（池 T 2.520 [2.194, 2.828]）通过两者（ECE 0.0375 对 0.0484，Brier −0.0020 [−0.0025, −0.0014]）但未通过 hard-v1、devtools-v1 与 documents-v1 的 ECE 保护阈值（分别为 +0.011、+0.007、+0.020，容差为 0.005）。

**仅报告的阶段 B 面板**（池 T 减发布 T，ECE；按构造 accuracy 相同）：

| panel | `4b-r10` ECE pool / shipped, Δ [95 % CI] | `08b-r15` ECE pool / shipped, Δ [95 % CI] |
|---|---|---|
| longdoc-v1 CUAD (2,254 q) | 0.023 / 0.031, −0.008 [−0.012, +0.004] | 0.061 / 0.053, +0.008 [−0.006, +0.016] |
| longdoc-v1 generated (2,400 q) | 0.090 / 0.100, −0.010 [−0.011, −0.009] | 0.143 / 0.131, +0.012 [+0.011, +0.012] |
| agents-ood-v1 (2,084 q) | 0.193 / 0.203, −0.010 [−0.010, −0.010] | 0.103 / 0.097, +0.006 [+0.001, +0.013] |
| guardrails-ood-v1 (4,949 q) | 0.042 / 0.051, −0.009 [−0.013, −0.004] | 0.051 / 0.063, −0.011 [−0.012, −0.007] |

池 T 本会略微帮助 Kev-4B 在每个长面板与 OOD 面板上，并使 Kev-0.8B 双向移动；两者都不改变 verdict，规则已在设限面板上固定了它。Kev-4B 的 agents-ood-v1 ECE（0.20）是它所读任何面板中最差的校准。

**经校验的上下文长度**（仅报告；`runs/r28-readout/context.{json,md}`，来自 `runs/r28-context/report.json`、注册的 `scripts/longdoc_report.py --context-margin -0.03` 命令加上 Kev-27B v2 的第 23 轮读数，以及 `runs/r28-context-served` 用于发布 T 下的 ECE）。与 8k 桶的 CUAD accuracy 差异，在 445-447 个问题上配对，pp [95 % CI]：

| size | read | 16k | 32k | 64k | validated |
|---|---|---|---|---|---|
| Kev-0.8B | `r28-08b-r15-longdoc` | −5.2 [−8.5, −2.1] | −6.0 [−9.5, −2.5] | −7.9 [−11.8, −4.2] | **8,192** |
| Kev-4B | `r28-4b-r10-longdoc` | −1.1 [−3.4, +1.2] | −5.8 [−9.0, −2.8] | −5.2 [−8.2, −2.0] | **8,192** |
| Kev-9B v2 | `r29-9b-r18a-longdoc` | −1.4 [−3.7, +0.9] | −3.6 [−6.4, −0.9] | −5.2 [−7.9, −2.5] | **8,192** |
| Kev-27B v2 | `r23-27b-k-w85-longdoc` | +0.2 [−0.7, +1.2] | −0.2 [−1.2, +0.7] | −1.1 [−2.4, +0.0] | **65,536** |

- Kev-4B 与 Kev-9B v2 在下界处分别以 0.4 与 0.7 pp 错失 16k 容差，点估计接近 −1 pp。注册时预测小型模型的区间会更宽，且规则偏向 8,192，结果正是如此。在 32k 处，三个小型模型都显著低于 8k（每个上界 < 0），因此更宽松的余量也无法支撑更长的声明。
- Kev-0.8B 从 4k 到 8k 已损失 6.8 pp（0.779 → 0.711；未配对，不同合同），在其训练长度之内。
- 这些数值在 Kev 1.0 的模型卡、README 与发布说明中（PR #206，已合并）。

**读数**（阶段 B，H100，`kev-sweepB`）：`r28-{4b-r10,08b-r15}-{longdoc,agentsood,guardood}`。`r28-4b-r10-agentsood` 在第 1 波中丢失（其命令派生了两个作业，而一个分离的 `modal run` 在本地客户端退出后只保留最后一个存活；卷上保留了部分的 `predictions.jsonl`），并以 10,800 s 超时作为 `/bench/r28-4b-r10-agentsood-t10800`（373/373 条记录，61 分钟）单独重读，复制到 `runs/r28-4b-r10-agentsood`。第 1 波的部分结果保留在卷上。agents-ood 与 guardrails-ood 读数的行是私有的（sft-v2 组件的 held-out 记录）；它们的 report 在此处。

## Round 29（已注册）

### Round 29 - 在第 24 轮审计规则下对第 7、9、11、16、18 轮的每个 9B delta 做回顾性筛选（事后，无训练；随本 spec 的提交注册，在任何第 29 轮读数之前）

**直白地说这是什么。** 这是**对已训练且已在 development 数据上读取过的 checkpoint 做事后筛选**，即第 24 轮的 9B 类比。制作这些 checkpoint 的各轮未选出任何 9B 候选（7、9、11、16、18）；第 27 轮后来选出并确认了第 18 轮的组 (a)，它现在即 Kev-9B v2。那些 verdict 仍然成立，此处不重新审视它们。规则即第 24 轮的审计规则，在本提交中、在任何计算之前固定。它不是盲的：若干组的 documents、hard-v1 与 devtools-v1 development 读数在其各轮的 read-out 中，且第 27 轮的表显示了 18a 与 18b。在 11 个中于 development 面板上挑最好的，按构造是乐观的，对此的保护是对 test 分区的确认——本口中除 `9b-r18a` 外的任何 9B checkpoint 都未读取过 test 分区。

**父模型：这些组全部训练自的 Kev-9B，而非 Kev-9B v2。** 每个组都是从 `jaredpalmer/kev-9b` 在 2026-09-30 之前的状态出发的一个 epoch：`night2-9b-du/00-trial-0`，Hub `2629c06a`，现为 `v1` 标签，T 2.30，其 development 行复现了该值（2.297）。Kev-9B v2 即 `9b-r18a` 本身，它是一个组。选择此父模型有两个原因：
- `kev.rounds` 以 trial 的 development-rows 拟合来服务父模型，对于 `r18-9b/00-trial-0` 这是 2.297，而非 v2 的发布 2.19。v2 若无引擎改动，无法作为以发布 T 提供服务的父模型。
- 作为以池 T 提供服务的组，`9b-r18a` 即其发布的 v2：其读数上的池拟合为 2.1936，即写入其 `head.pt` 的值。因此每个组（含 v2）都在相同行上与 v1 比较，且排序将每个组直接对照 v2。

简报要求"父模型 = 已发布的 Kev-9B 在其发布 T 处"。当它被写下时，已发布的 Kev-9B 是 v1。

**组**（全在 `kev-runs` 卷上；无缺失）。第 12 轮的两个 9B skills 组（`r12-skills/00-trial-0`、`01-trial-1`，也在卷上）在本轮注册范围之外。

| arm | checkpoint | delta（从 Kev-9B v1 出发的一个 epoch） | trained on |
|---|---|---|---|
| `9b-r7-s1`、`9b-r7-s2` | `r7-docs/00-trial-0`、`01-trial-1` | documents-v1，replay 2,000，lr 2e-5，seed 1 / 2 | decision-v7、documents-v1 |
| `9b-r9-a`、`-b`、`-c` | `r9-docs/0{0,1,2}-trial-*` | documents-v1；（replay，lr）=（6,000，2e-5）、（2,000，1e-5）、（6,000，1e-5）；seed 3 | decision-v7、documents-v1 |
| `9b-r11-s4`、`9b-r11-s5` | `r11-docs/00-trial-0`、`01-trial-1` | documents-v1，replay 6,000，lr 2e-5，seed 4 / 5 | decision-v7、documents-v1 |
| `9b-r16-lr1e5`、`9b-r16-lr2e5` | `r16-9b/00-trial-0`、`01-trial-1` | hard-v1 + devtools-v1（`round10/skills`），replay 10,000 | decision-v7、round10/skills、hard-v1、devtools-v1 |
| `9b-r18a`（= Kev-9B v2）、`9b-r18b` | `r18-9b/00-trial-0`（lr 2e-5）、`01-trial-1`（lr 1e-5） | documents + skills（`round15/joint`），replay 10,000 | decision-v7、documents-v1、round10/skills、hard-v1、devtools-v1 |

`evals/night2`（v1 自身的 delta）出于第 28 轮所述原因被排除在 `trained_on` 之外。`validate` 对任何组都发现**无池冲突**。

**温度。** 每个组都以第 28 轮的池提供服务：transfer-r3 calibration 的八个源加上 transfer-v9 `mmlu_pro`，减去该组的 transfer-v4 development 记录，带 90 % 区间。父模型保留其发布 2.30。

**规则**（第 24 轮的，除注明外逐字；对照 Kev-9B v1；配对 record-clustered bootstrap，2,000 次重采样，seed 0，micro；`drop_ids`）：
1. Primary：
   - breadth-v1 dev accuracy 下界 > 0，不含 `routerbench`、`cfcolor`、`humicroedit`、`chessbench`；
   - tasksource-heldout-v1 dev accuracy 下界 > 0，不含七个族（同一私有列表）；
   - Kev panel accuracy 下界 ≥ −1 pp：transfer-v4 dev 不含 `emotion`、hard-v1、devtools-v1 不含 `flakeflagger` 与 `commitpackft_type`，以及 documents-v1。
2. 保护阈值：
   - short state（transfer-v4 dev + transfer-r3 test，均不含 `emotion`）：accuracy 下界 ≥ −2 pp、Brier 上界 ≤ +0.02、confident errors 上界 ≤ +1 pp；
   - transfer-v9 上的 unknowable 占比 ≤ 0.05；
   - longdoc CUAD：accuracy 下界 ≥ −2 pp，且 CUAD 16k+ accuracy（组 − 父模型）≥ −2 pp。
3. 校准：breadth、Kev-panel 与 tasksource-heldout 的 ECE ≤ 父模型 + 0.01，使用相同的排除项。
4. 候选：通过且 breadth + tasksource-heldout + Kev-panel accuracy 增益最大的组。

第 24 轮有而本轮去掉的：其 WANLI-v2 与 TypeSafe 面板（两个套件已于 2026-09-30 移除），以及任何 pooled-externals 或 scienthoon 读数。SemIf 为报告项（可选）。同样报告的还有：跨全部 14 个源与跨三个移动源的 breadth、跨全部 24 个族的 tasksource-heldout、单独的 hard-v1、不含 hard-v1 的 Kev panel、longdoc generated、按名义桶的 longdoc，以及 ood-v2 / agents-ood-v1 / guardrails-ood-v1。

**每个结果意味着什么**（在任何读数之前写下）：
- *没有组通过。* 无候选。Kev-9B v2 的发布保持有效，正如第 27 轮注册的那样，且记录该结果（包括 `9b-r18a` 自身的失败，若有，作为参考信息）。
- *`9b-r18a` 为候选。* 审计规则与第 27 轮一致，Kev-9B v2 保持有效。**没有新的确认：** 其 hard-v1、devtools-v1、documents-v1、documents-v2 与 locked test 读数都是第 27 轮的确认，其 breadth-v1 test 已在 2026-09-30 族读数中读取，因此它们都不能再作为确认被读取。
- *另一组 X 为候选。* X 由下述阶段对照 v1 确认。其在相同 test 项上对照 Kev-9B v2 的 accuracy 报告在每个阶段旁（`versus`：v2 的第 27 轮 test 读数与其族 breadth-v1 test 读数；仅 accuracy，不依赖于 T）。用 X 替换 v2 是 Jared 的决定，且仅在 X 通过每个阶段时。

**确认**（仅 X，各读一次；第 24 轮在 9B 上的阶段）：
- `tests`：
  - breadth-v1 test accuracy 下界 > 0（相同的四个源排除；全部 14 源报告）；
  - tasksource-heldout-v1 test 下界 > 0（七个族排除）；
  - pooled hard-v1 + devtools-v1（不含 `flakeflagger` 与 `commitpackft_type`）+ documents-v1 test 下界 ≥ −1 pp；
  - documents-v2 与 longdoc-v1 test（按长度的 CUAD、generated）报告。
  - 父模型 test 读数：`runs/fam-9b-breadthtest` 与第 27 轮的 `runs/r27c-9b-parent-{hardtest,devtest,docs1test,docs2}`。新增：`runs/r29c-9b-parent-{tshtest,longdoctest}`。
- `locked`：transfer-v4 locked accuracy ≥ v1 的 − 1 pp，且服务 Brier ≤ v1 的 + 0.005（`kev-9b-r29-ungated`）。这是第 24 轮的构造：其绝对边界为 Kev-27B 自身的 −1 pp / +0.005。
- 在任何发布之前，做 bf16 服务检查：`modal_app.py::serving --run /runs/<X>/checkpoint --gpu H100 --name serving-9b-r29 --flags=--isolation`，最大 |Δp| ≤ 0.03 且在 280 内 ≤ 1 次翻转。发布温度为池拟合，由 `scripts/calibrate_checkpoint.py` 如第 28 轮那样写入。

**阻碍。** CUAD 保护阈值设限，因此第 29 轮在 9B 的 longdoc-v1 读数能够做出之前无法读出（第 28 轮的阻碍：族 test 读数在首个 32k 记录处内存不足）。规则未被改动以绕过它。将长面板在 9B 处改为仅报告将是重新注册，且是 Jared 的决定，在任何第 29 轮读数之前。

**本轮需要的、尚不存在的读数**（合并后的扫描；H100）：

| phase | reads | count |
|---|---|---|
| A（现在） | 父模型 `r29-P9-{tsheld,ood}`；除 18a 外 10 个组的 `breadth`；全部 11 个组的 `tsheld` 与 `ood`；r7 ×2、r9 ×3、r11 ×2 的 `hard` 与 `devtools`；r7 ×2 与 r9 ×3 的 `r3test`；除 18a / 18b 外 9 个组的 `r3cal` | 2 + 10 + 22 + 14 + 5 + 9 = 62 |
| B（内存修复后） | 父模型与全部 11 个组的 `longdoc`、`agentsood`、`guardood` | 36 |
| confirmation（仅 X ≠ 18a） | `r29c-9b-cand-{breadthtest,tshtest,hardtest,devtest,docs1test,docs2}`、`r29c-9b-parent-tshtest`、locked 读数、服务检查；阶段 B：`r29c-9b-{cand,parent}-longdoctest` | 7 + 1 + 2 = 10，+ 服务检查 |

它使用的现有读数：
- 父模型：`runs/fam-9b-breadth`、`hv1-P9`、`dt1-P9`、`docs1-P9`、`n2-9b-du-v9`、`rc-parent-r3test`、`r5r-P9-semif`、locked 读数；
- 组：它们各轮的 `docs` / `v9` / `semif`（以及 r11、r16、r18 的 `hard` / `devtools` / `r3test`）；第 27 轮的 `r27-9b-r18{a,b}-r3cal`；18a 的 `runs/fam-9bnew-breadth`；每个 trial 的 trial 内 transfer-v4 读数。

它们位于研究 checkout、`/tmp/kev-r27`（fam-9b*，尚未提交）与卷上。

**预算（第 28 与 29 轮合计）。** H100 每容器 $5.675/h（`kev.budget.hourly_rate`）。预期成本根据过去 9B 读数的延迟估算（breadth 约 10 分钟、hard 约 7、tasksource-heldout 约 6、ood 约 6.5、短套件约 4-5，每个含加载）；4B 与 0.8B 更便宜。

| part | reads | expected | admission bound |
|---|---|---|---|
| 阶段 A | 68（6 + 62） | ≈ $40 | $193（68 × $2.84 @ 1,800 s） |
| 阶段 B | 42（6 + 36） | ≈ $115 | $318（14 个 longdoc × $17.03 @ 10,800 s + 28 × $2.84） |
| 第 29 轮确认（若 X ≠ 18a） | 10（现在 8，阶段 B 2）+ 服务检查 | ≈ $30 | ≈ $77 |
| 第 28 轮确认 | 0（现有行） | $0 | $0 |
| **总计** | 120 + 服务检查 | **≈ $185** | 若全部同时运行则为 $588 |

上限为 $300 加 10 % 储备，因此 $270 可针对启动时的计量读数做规划。注册时 Modal 读数为 $4,633.77 计量值（2026-09-30T22:45Z）；当晚上限为 $5,980。

预期总计吻合。各上限无法同时吻合，因此扫描分波启动，每波满足（计量值 − 基线）+ 在途上限 < $270。顺序：阶段 A；第 28 轮的 read-out；内存修复 PR；阶段 B，longdoc 优先；第 29 轮的 read-out；然后确认。一个 9B agents-ood 读数可能超过其默认 1,800 s（Kev-27B 的约需 66 分钟）：用 `--timeout 3600` 单独重启动它，而非提高 spec 的 `read_timeout`，那会使每个 9B 上限翻倍。

## Round 29 结果（2026-10-01）— 无候选；Kev-9B v2 保持有效（读出时缺少十个组的 longdoc 读数）

**Verdict**（`runs/r29-readout/round29.json`、`readout.txt`）：**没有组通过**，因此无候选、不读取确认，且 Kev-9B v2 的发布保持有效，正如第 27 轮注册的那样。read-out 不完整：阶段 B 除 `9b-r18a` 外十个组的 longdoc-v1 读数因预算（如下）在 1,200 条记录中的 750-800 处停止，因此引擎将这些组标记为 `incomplete`。这不能改变 verdict。每个组在已完整的读数上已经未通过 primary 1 的 tasksource-heldout-v1 条件（accuracy 下界 > 0），而缺失的读数只会追加失败：一个组只有在其每个判据都通过时才算通过。

对照 Kev-9B v1（`jaredpalmer/kev-9b@2629c06a`，发布 T 2.30），每个组在池 T 下；accuracy Δ 单位 pp [95 % CI]，配对 record-clustered bootstrap：

| arm | breadth-v1 dev (audited) | tasksource-heldout-v1 dev (audited) | Kev panel | short state | longdoc CUAD | failed criteria |
|---|---|---|---|---|---|---|
| `9b-r7-s1` | +0.9 [+0.2, +1.7] | −0.1 [−1.0, +0.9] | +1.2 [+0.4, +2.1] | −1.0 [−2.0, −0.2] | not read | `1_tasksource_heldout_lower_above_0` |
| `9b-r7-s2` | +0.7 [+0.0, +1.5] | −0.6 [−1.5, +0.4] | +1.9 [+1.1, +2.8] | −0.8 [−1.8, +0.2] | not read | `1_breadth`、`1_tasksource_heldout` |
| `9b-r9-a` | +1.0 [+0.3, +1.8] | −0.8 [−1.7, +0.2] | +1.7 [+0.8, +2.6] | −0.5 [−1.5, +0.4] | not read | `1_tasksource_heldout` |
| `9b-r9-b` | +0.5 [−0.1, +1.1] | −0.1 [−1.0, +0.8] | +1.5 [+0.7, +2.3] | −0.1 [−0.9, +0.6] | not read | `1_breadth`、`1_tasksource_heldout` |
| `9b-r9-c` | +0.6 [−0.0, +1.2] | −0.7 [−1.6, +0.2] | +1.6 [+0.8, +2.4] | −0.5 [−1.4, +0.3] | not read | `1_breadth`、`1_tasksource_heldout` |
| `9b-r11-s4` | +0.3 [−0.4, +1.0] | −0.5 [−1.4, +0.5] | +1.6 [+0.8, +2.4] | −0.7 [−1.5, +0.0] | not read | `1_breadth`、`1_tasksource_heldout`、`3_kev_ece` |
| `9b-r11-s5` | +0.4 [−0.2, +1.2] | −0.8 [−1.8, +0.2] | +1.2 [+0.3, +2.1] | −1.1 [−2.1, −0.1] | not read | `1_breadth`、`1_tasksource_heldout`、`2_short_acc`、`3_kev_ece` |
| `9b-r16-lr1e5` | +0.3 [−0.7, +1.2] | −0.9 [−2.3, +0.5] | +8.7 [+7.4, +10.0] | −0.3 [−1.5, +0.9] | not read | `1_breadth`、`1_tasksource_heldout`、`3_kev_ece` |
| `9b-r16-lr2e5` | +0.6 [−0.4, +1.5] | −0.7 [−2.1, +0.7] | +9.9 [+8.6, +11.2] | −0.1 [−1.3, +1.1] | not read | `1_breadth`、`1_tasksource_heldout`、`3_kev_ece` |
| `9b-r18a`（= v2） | +0.2 [−0.8, +1.2] | +0.6 [−0.8, +2.0] | +12.6 [+11.3, +14.1] | +0.1 [−1.1, +1.2] | +2.5 [+0.8, +4.3] | `1_breadth`、`1_tasksource_heldout` |
| `9b-r18b` | +0.2 [−0.8, +1.2] | −0.3 [−1.6, +1.1] | +10.8 [+9.4, +12.2] | −0.4 [−1.5, +0.8] | not read | `1_breadth`、`1_tasksource_heldout`、`3_kev_ece` |

（`1_breadth` = `1_breadth_lower_above_0`，`1_tasksource_heldout` = `1_tasksource_heldout_lower_above_0`，`2_short_acc` = `2_short_acc_lower_at_least_minus_2pp`，`3_kev_ece` = `3_kev_ece_at_most_parent_plus_0.01`。）

- **它说明了什么。** 第 7-18 轮的十一个 9B delta 中没有一个以可分辨的幅度在 held-out *数据集* 上击败 Kev-9B v1：仅文档的 delta 在 breadth-v1 上换来 +0.5 到 +1.0 pp（其中两个下界高于 0），而在 tasksource-heldout-v1 上损失 0.1-0.9 pp；skills delta（16、18）在训练族 Kev panel 上获得 8.7-12.6 pp，而在两个 held-out 面板上无可测收益。审计规则本也不会选出 v2；v2 是由第 27 轮的规则（带 held-out 保护阈值的训练族面板）选出的，且它在此通过了每个保护阈值与校准判据。
- **Kev-9B v2（`9b-r18a`）对照 v1**，完整：breadth-v1 dev 0.781 对 0.779，tasksource-heldout-v1 dev 0.706 对 0.700（ECE 0.032 对 0.057），Kev panel 0.849 对 0.723，short state 双方均为 0.871，longdoc-v1 CUAD 0.837 对 0.811（+2.5 [+0.8, +4.3]；16k+ 0.810 对 0.792），ood-v2 0.889 对 0.882。其 CUAD 保护阈值通过。
- 注册中"每个结果意味着什么"下的结果：*没有组通过*。记录该结果，包括 v2 自身的 primary 失败，作为参考信息。未确认任何项，也未读取任何 test 分区。

**读数与预算。** 阶段 B 在 H100 上运行（`kev-sweepB`）。已读取并提交：`r29-P9-longdoc` 与 `r29-9b-r18a-longdoc`。已停止：其余十个组的 longdoc 读数，于 16:05Z 以每个分离 `modal run` 一个作业启动。它们于 18:40Z 在 1,200 条记录中的 750-800 处停止，因为工作区读数为 $4,987.19 计量值（九月 $4,682.78 + 十月），而会话的停止线为 $5,100。它们自身剩余的约 2.1 h × 10 × $5.675 ≈ $119 会在没有其他支出的情况下越过该线，且其他会话的作业还以每小时约 $40-90 的速度增加。它们部分结果的 `predictions.jsonl` 保留在卷上。未启动：父模型与全部十一个组的 agents-ood-v1 与 guardrails-ood-v1（24 个读数，按此处测得的 9B 速率约 $180：agents-ood 在 4B 上约每记录 10 秒）。两个面板均为仅报告（`optional`），因此它们的缺失不影响比较的完整性。正式完成 read-out 需要十个 longdoc 读数（从头约 $270，每个约 4.7 小时），且不会改变 verdict。

## Record

每轮或具名研究一行。`rN.json` 为 main 上的 `experiments/rounds/rN.json`（规则即数据；`python -m kev.rounds readout` 复现第 5-20、22、24 轮，见 `tests/test_rounds.py`）；`A:` 为归档标签。Verdict 为注册的产出。

| round / study | date | what | verdict | where |
|---|---|---|---|---|
| Round 4 | 09-22 | 在 27B 之前的十二个廉价杠杆（4.1-4.12） | 采纳：逐工作负载校准报告、配对-CI  incumbent 规则、全分区 MLX parity、OOF audit 字段；长状态是数据问题（4.12）；否定项：4.2、4.5、4.8、4.10、4.11；4.9 未通过其门槛；4.4 通过门槛，服务模式待定 | `A:PLAN.md` "Round 4"、"Round 4 results" |
| Release confirmation | 09-22 | 在第 3 轮 final 面板上对软目标 Kev-9B（`r4-soft`） | 未发布（Brier 边界、WANLI −1.2） | `A:PLAN.md` "Release confirmation"；`runs/rc-verdict` |
| Round 5 | 09-22 | 长状态 + 软目标，所有规模 | 无发布；9B 以 3 个问题之差未过 WANLI | `r5.json`；`runs/r5-verdict`；`A:PLAN.md` "Round 5" |
| Round 6 | 09-23 | 通宵爬山：9B / 4B / 0.8B 上 22 个 delta trial（长状态、软目标变体） | 无候选；MNLI 软目标导致 WANLI 下降 | `r6.json`；`A:PLAN.md` "Round 6"；`A:runs/r6-readout` |
| A1 | 09-23 | 问题侧 LoRA，从零开始，4B × 2、9B、27B | 否定：4B / 9B 损失 3-6 pp 与日期算术；27B 保留两者但损失 MMLU、配对与覆盖；放置保持 `full` | `A:PLAN.md` "Round 6" > A1 |
| A2 | 09-22 | Qwen3.8-27B zero-shot 探测 | 2 / 3 门槛（MMLU-Pro 0.635 < 0.65）；B1 由 Jared 作为记录override授权 | `A:PLAN_27b.md` gating addendum；`runs/probes/qwen38-27b-*` |
| B1 | 09-23 | Kev-27B，v7 配方，1 epoch，3 个 trial | trial A 在配对边界上以 0.15 pp 之差未过，且在一个任务上以 2 个问题之差未过 | `A:PLAN.md` "Round 6" > B1 |
| Round 6 follow-up | 09-23 | Kev-27B，2 epoch，seed 1-2 | 无候选；两个 epoch 毫无收益 | `A:PLAN.md` "Round 6 follow-up" |
| B1 v2 | 09-23/24 | Kev-27B 在 v7 + dates/unknowable + 长状态 + 软目标上 | seed 2 通过每个判据；bf16 服务检查通过；作为 Kev-27B 发布 | `A:PLAN_27b.md` "B1 v2"、"bf16 serving check"；`runs/release/kev-27b-v2.json` |
| documents-v1 / v2 | 09-23 | 真实 CFPB 叙述；teacher 同意的训练、judge-panel + 双重裁定的 eval 标签 | 冻结；抽查 47/50 与 50/50 | `A:PLAN_27b.md` "documents-v1 result"、"documents-v2"；`evals/documents-v{1,2}/manifest.json` |
| Round 7 | 09-23 | documents delta，所有规模 | 无候选：0.8B / 4B 在过小而无法分辨的套件上未过边界，9B / 27B 在 short states 或 externals 上付出代价 | `r7.json`；`A:PLAN.md` "Round 7" |
| Round 8 | 09-24 | documents delta 于 0.8B / 4B，保护阈值按套件大小设定 | **Kev-4B 已确认、已发布**（后被第 10 轮取代） | `r8.json`；`runs/r8-readout`；`runs/release/kev-4b-r8.json` |
| JevBench | 09-24 | 公共项，未变 harness，已发布族 | 报告；Kev-9B hard 0.568 对 Jev 0.741 | `A:PLAN.md` "JevBench"；`runs/jevbench-public` |
| Round 9 | 09-24 | documents 于 9B / 0.8B，更多 replay / 更小步长 | 五个组中无候选 | `r9.json`；`runs/r9-readout` |
| Round 10 | 09-24 | skills delta（hard-v1 + devtools-v1），4B 与 27B | **Kev-4B 已确认、已发布**；27B 未过 scienthoon | `r10.json`；`runs/r10-readout`、`runs/r10-verdict` |
| Round 11 | 09-24 | 第 9 轮的配方，新 seed，池化短面板 | 0.8B documents 已确认（被 15 取代）；无 9B | `r11.json`；`A:runs/r11-verdict` |
| Round 12 | 09-24 | skills delta 于 9B / 0.8B | 0.8B skills 已确认（被 15 取代）；无 9B | `r12.json`；`A:runs/r12-verdict` |
| Round 13 | 09-24 | 在 documents 候选之上的 0.8B skills | 无候选：堆叠侵蚀 | `r13.json`；`runs/r13-readout` |
| Round 14 | 09-24 | 在第 10 轮的 4B 上多 12,000 条 hard-v1 记录 | 无候选：收益递减 | `r14.json`；`A:runs/r14-readout` |
| Round 15 | 09-24 | 0.8B documents + skills 在一个 delta 中 | **Kev-0.8B 已确认、已发布** | `r15.json`；`runs/r15-readout`、`runs/r15-verdict` |
| Round 16 | 09-24 | 9B skills，replay 10,000 | 无候选（documents 代价） | `r16.json`；`A:runs/r16-readout` |
| Round 17 | 09-24 | 27B skills，replay 10,000 | 组 (a) lr 2e-5：无候选（documents、scienthoon）；组 (b) lr 1e-5：**待定** | `r17.json`；`A:PLAN.md` "Round 17" |
| Round 18 | 09-24 | 9B documents + skills，replay 10,000 | 无候选（WANLI-v2、scienthoon） | `r18.json`；`A:runs/r18-readout` |
| AutoJev head-to-head | 09-24 | AutoJev-27B 对 Kev-27B，仅报告 | 见上文 "Against Jev" | `A:runs/autojev-h2h/report.json` |
| Round 19 | 09-25 | 在 `sft-v1` 上对 Qwen3.8-27B 的 full-weight SFT（lr 2e-6、5e-6）+ 在 Kev-27B 自身数据上的 full weights（attribution） | 无候选：两个 SFT 组均未过 scienthoon、WANLI-v2、pooled externals、short-state Brier / confident errors 与两个 ECE 判据（(b) 还有 breadth）；数据带来增益，full weights 带来代价 | `r19.json`；`runs/r19-readout`、`runs/r19-breadth-report`；"Round 19 result" |
| Round 20 | 09-25/26 | 对第 19 轮 finals 的事后处理，无训练：held-out-datasets 温度 + WiSE-FT 插值（α 0.85 / 0.70 / 0.50） | 无候选（6 个中 0 个）：每个组都未过 scienthoon 与 pooled externals；注册的温度在两个 ECE 判据上都通过，直至 α 0.70（组 (a) breadth ECE 0.0085 对 0.0118）；朝向基座时 (a) 的 scienthoon 变差；scienthoon 分析将代价追溯到被读为"angry"的平静投诉，而其参考是六个 LoRA 抽样中最好的一个 | `r20.json`；`runs/r20-readout`、`runs/r20-breadth-report`、`runs/r20-scienthoon`；"Round 20 result" |
| Round 21 | 09-26 | 在 `sft-v2-r21` 上对 Qwen3.8-27B 的 full-weight SFT（32k 状态、扩展数据；lr 2e-6、1e-6） | 启动阶段失败：两个组在步 62 处 GPU 内存不足（一个 98.7k-token 的遍，characters 计划按与其槽位 33-50k-token 遍相同的成本计费），无快照、无读数；约 $135 | `r21.json`；"Round 21 result" |
| Round 22 | 09-26/27 | 第 21 轮的科学与规则应用于 `sft-v2-r22`（145,840 条记录），带 `--pass_tokens_max 40960`，一个组（lr 2e-6），4 个候选（快照 s25 / s50 / s75 + final） | 无候选（4 个中 0 个）：primary 通过并随训练增长（final breadth +1.3、tasksource-heldout +3.8、Kev panel +7.8）；每个候选都未过 scienthoon 与 CUAD ECE 16k+，三个未过 pooled externals，s75 与 final 的 short-state accuracy；calm-called-angry 错误消失，转为漏报 angry；Modal 在 3 次尝试中给了 2 次，final 由手动延续完成 | `r22.json`；`runs/r22-readout`、`runs/r22-breadth-report`、`runs/r22-scienthoon`；"Round 22 result" |
| scienthoon removed | 09-27 | `evals/external/scienthoon-v1` 作为门槛被移除（因其不可靠：饱和的 `queue`、文本不可知的 `priority`、291 个 `angry` 标签中有 15 个与文本矛盾） | 既往 verdict 仍成立；pooled externals = 第 23 轮起的 SemIf + WANLI-v2 + TypeSafe | "scienthoon removed"；`kev.suite.REMOVED_SUITES` |
| Round 24 | 09-27 | 回顾性筛选：将 2026-09-27 审计的套件 verdict 作为一条规则应用于全部 12 个 full-weight 27B checkpoint（第 19、20、22 轮），无训练或新读数 | 候选 `27b-r22-final`（12 个中 2 个通过：它与 `27b-r20a-w85`）；**未确认**：tests 阶段通过（breadth-v1 test +1.5、tasksource-heldout-v1 test +5.3、pooled +8.6；test breadth index 53.7 对 Jev 54.0、Kev-27B 50.2），locked transfer-v4 0.8841 < 0.886（656 中 580，需 582）；CUAD test −1.8；未发布 | `r24.json`；`runs/r24-readout`、`runs/r24-verdict`、`runs/r24-breadth-report`；"Round 24 result"、"Round 24 confirmation" |
| Round 23 | 09-27/28 | 事后，无训练：将第 22 轮的 final 向 Kev-27B 自身权重混合（LoRA 在 fp32 中合并），α 0.85 / 0.70 / 0.50 × {SFT head、blended head}；09-28 在第 24 轮审计规则与确认下重新注册（首次注册基于第 22 轮规则，从未启动） | **`27b-k-w85` 已确认**（6 个中 5 个通过规则；tests 阶段通过；locked transfer-v4 0.8887，656 中 583，边界 582）；于 09-30 作为 Kev-27B v2 发布 | `r23.json`；`runs/r23-readout`、`runs/r23-verdict`；"Round 23 result"、"Round 23 confirmation"、"Released: Kev-27B v2" |
| Release: Kev-27B v2 | 09-30 | 第 23 轮的 `27b-k-w85` 发布到 `jaredpalmer/kev-27b` 主分支（完整 bf16 权重 `d27af6ab…`、head `7968f17b…`、T 1.3195），在一个删除了 v1 adapter 文件的提交中；v1 先打上 `v1-lora` 标签 | **已发布**；匿名 Hub 加载逐行复现第 23 轮的 semif-v1 与 transfer-v4 development 读数；`@v1-lora` 以 T 1.38 加载 v1 | `runs/release/kev-27b-r23-published.json`；`runs/rel27-public/`；"Released: Kev-27B v2" |
| Round 25 | 09-28/29 | 从 Kev-27B（LoRA 已合并）在 `sft-v2-r25`（breadth + b1v2 replay，无长文档族，状态 ≤ 16k）上继续 full-weight SFT，lr 1e-6 / 2e-6，8 个候选（快照 + finals），第 24 轮规则 | 无候选（8 个中 0 个）：每个组都未过 breadth ECE（0.023-0.035 对 0.0176）；lr 1e-6 的 s75 / final 仅未过该项（11/12）；lr 2e-6 还未过 short-state accuracy 与 breadth primary；CUAD accuracy 保持，CUAD ECE 未保持；无一组领先 `27b-k-w85`（仅报告） | `r25.json`；`runs/r25-readout`；"Round 25 result" |
| Round 26 | 09-29 | 第 25 轮的 lr 1e-6 组，tasksource-v1 翻倍（`sft-v2-r26`：sft-v2-r25 + 13,000 条 tasksource-v1 记录，58,515），一个 study，4 个候选，第 24 轮规则 | 无候选（4 个中 0 个）：每个组都未过 breadth ECE（0.020-0.029 对 0.0176）；final 仅未过该项（11/12），快照还另未过 breadth primary，s50 还另未过 short-state accuracy；对照第 25 轮的 lr 1e-6 组，breadth 与 breadth ECE 持平（仅报告）；无一组领先 `27b-k-w85`（仅报告） | `r26.json`；`runs/r26-readout`；"Round 26 result" |
| WANLI and TypeSafe removed | 09-30 | `evals/external/{wanli-v2, wanli-v1, typesafe-v1}` 作为门槛被移除（因其不可靠：WANLI 的四分之一 gold 标签是两个分歧标注者之一；TypeSafe 的 gold 是两个封闭前沿模型的答案均值，split-half r 约 0） | 既往 verdict 仍成立；SemIf 是第 27 轮起唯一的外部读数，仅报告 | "WANLI and TypeSafe removed"；`kev.suite.REMOVED_SUITES` |
| Round 27 | 09-30 | 事后，无训练：第 18 轮的两个 9B documents + skills delta 在 held-out-pool 温度下的审计规则上 | **`9b-r18a` 已确认**（两个组都通过；tests：pooled +18.7、documents-v1 +7.1；locked transfer-v4 +0.0 [−1.7, +1.8]、Brier −0.025）；暂存为 Kev-9B v2，未发布 | `r27.json`；"Round 27 result"；`runs/r27-readout`、`runs/r27-verdict` |
| Release: Kev-9B v2 | 09-30 | 第 27 轮的 `9b-r18a` 发布到 `jaredpalmer/kev-9b` 主分支（`b5d8c18e`、adapter `2b2a70cf…`、T 2.19）；v1 先打上 `v1` 标签 | **已发布**；匿名 Hub 加载复现第 18 轮的读数（argmax 252/252、764/764）；`@v1` 以 T 2.30 加载 v1 | "Released: Kev-9B v2"；`runs/rel9-public/` |
| Round 28 | 09-30 | 事后，无训练：Kev-4B / Kev-0.8B 温度在 held-out 池上重新拟合；每个规模的经校验上下文长度（仅报告） | 任一规模都无候选：`4b-r10` 未过两个 primary（Brier −0.0001 [−0.0005, +0.0003]、ECE 0.0252 对 0.0240）；`08b-r15` 通过两者但未过 hard / devtools / documents 的 ECE 保护阈值；发布 T 2.41 / 2.35 保留；经校验上下文（仅报告）0.8B / 4B / 9B v2 为 8,192，27B v2 为 65,536（10-01 在全部阶段 B 面板就位后重读；verdict 未变） | `r28.json`；`runs/r28-readout`（`context.{json,md}`）；"Round 28 result" |
| Round 29 | 10-01 | 事后，无训练：第 7-18 轮的十一个 9B delta 在第 24 轮审计规则下对照 Kev-9B v1，池 T | **无候选**：每个组都未过 tasksource-heldout-v1 primary（下界 > 0），除 `9b-r7-s1` / `9b-r9-a` 外还都未过 breadth-v1；Kev-9B v2 保持有效。十个组的 longdoc 读数因预算停止（verdict 中性）；agents / guardrails OOD 未读取 | `r29.json`；`runs/r29-readout`；"Round 29 result" |
| Kev 1.0（release candidate） | 09-30 | 四个已发布 checkpoint 作为一个族做版本化：四个的正式模型卡、README 族表、发布说明与资源构建器；无训练、无新读数 | 已打包（PR #206）；经校验上下文 8,192（0.8B、4B、9B）/ 65,536（27B）；基线 Kev 2 已测量对照 | "Kev 1.0 baseline"；`docs/releases/kev-1.0.md`、`docs/releases/kev-1.0-assets.json` |
| Release: Kev 1.0 | 10-01 | 四个 checkpoint 作为一个版本化族发布：每个的仅含卡的 Hub 提交 + 标签 `v1.0`（0.8B `bf75a6a8`、4B `6cfce5c2`、9B `db029f08`、27B `af0e6d55`；权重未变），GitHub release `kev-1.0` 含三个确定性 adapter tarball + `SHA256SUMS.txt`，`kev-family` 退役为指针 | **已发布**；匿名 `@v1.0` 以 T 2.35 / 2.41 / 2.19 / 1.32 加载，哈希匹配，冒烟读数与 tarball logits 与标签的相同，资源重新下载并校验，Space `/decide` 作答 | "Released: Kev 1.0"；`runs/release/kev-1.0.json` |
| breadth-v1 | 09-24 | 跨 Decision Index 五个领域的冻结仅评估面板（14 个 held-out 数据集，每个 150 条记录，锁定 test 未读）；development 基线 | 报告：机会校正指数 Jev 53.3、AutoJev-27B 51.7、Kev-27B 50.2、Kev-4B 40.8（Kev-27B 对 Jev −3.1 [−6.2, +0.1]）；Kev-27B 在检索（SGD、CLINC150）上落后最多 | `evals/breadth-v1/manifest.json`；`runs/breadth-v1-report/report.md` |
| drift-v1 | 09-30 | 为何 Kev-27B v1 的 semif-v1 logits 在其 09-23 读数与 09-30 公共读数之间不同（最大 \|Δp\| 0.032，argmax 相等） | 报告：Modal 镜像中的 #125 causal-conv1d CUDA 内核（替换 48 个 DeltaNet 层中的 transformers PyTorch conv）；无代码漂移（09-23 代码与 `main` 在相同内核上逐位相同），无非确定性；breadth-v1 偏移 acc −0.1 pp、ECE +0.0008、3,075 中翻转 13/3,075，低于每个第 25/26 轮的边际；CUDA 上的 fp32 Qwen3.5 读数带有 fla 的 TF32 点积（p 中约 0.003） | `runs/drift-v1/REPORT.md`；AGENTS.md "What fp32-exact guarantees" |

较早的里程碑，全部在 `A:PLAN.md` 中（括号内为小节名）：

- **v3 协议与匹配的数据-对-容量研究**（2026-09-19 之前；"v3 protocol"、"Status and deferred work"）：容量 0.6B → 4B 转移 +17.5 到 +19.0 pp；组合策略数据 +3.6 到 +5.1 pp；不可变套件、分组拆分、最小对。
- **Overnight-1**（分支 `research/overnight-1`，PR #3；"Overnight autoresearch"）：lr 5e-5 而非 2e-4 是 4B / 8B 的杠杆（+4.7 pp [+0.4, +9.6]）；微调侵蚀基座能力；配置空间已穷尽；研究预览。
- **Toward v0.2**（2026-09-19/20；"Toward v0.2"）：`decision-v7`（随机规则树、序数 Score 族）、Qwen3 族发布、anchoring 并非杠杆；截止日期仍是最具决定性的族。
- **Qwen3.5 port**（2026-09-20；"Qwen3.5 port" §1-§10）：混合 backbone 的行批前向；Kev-9B locked 0.837 对 Kev-8B 0.780（+7.3 pp [+2.8, +11.7]）；族迁向 Qwen3.5；截止日期侵蚀出现在表示中。
- **Night 2**（2026-09-20/21；"Round 2 autoresearch"、"Results"、"Decisions taken"）：dates + unknowable delta 被提升（Kev-9B locked 0.852），温度内置入 `head.pt`、`date_facts` 选择启用、35B-A3B 未发布。
- **Round 3 calibration audit**（2026-09-21/22；"Round 3 autoresearch"）：指标 v2（tie-aware 覆盖、AURC、全统计量 bootstrap）；匹配损失筛查未选出任何项；绑定诊断显示日期差距是减法，而非绑定。
