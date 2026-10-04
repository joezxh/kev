<p align="center">
  <a href="./sft-medical_CN.md"><img alt="中文" src="https://img.shields.io/badge/%E4%B8%AD%E6%96%87-orange?style=for-the-badge"></a>
  <a href="./sft-medical.md"><img alt="English" src="https://img.shields.io/badge/English-blue?style=for-the-badge"></a>
</p>

# 医疗决策场景的 Kev 微调方案

[English](./sft-medical.md) · 实现目录：[`medical/`](./medical/README.md) · 上游 skill：[`skills/kev-finetune`](../skills/kev-finetune/SKILL.md) · 蒸馏方案：[`sft-distill_CN.md`](./sft-distill_CN.md)

在五类医疗决策上微调 **Kev-0.8B** 与 **Kev-4B**，得到的是**校准概率**而不是生成文本 —— 覆盖导诊分诊、
危急值复核、用药/医保审核、护理质量管控、病历编码。

Kev 是一个用 log loss 训练的指针读出（pointer-readout）模型，**它一个 token 都不生成**，因此结构上不可能
幻觉出诊断、也不可能通过自由文本泄漏 PHI。这条属性正是它适配医疗场景的根本原因，也是整套方案如此设计的出发点。

---

## 1. 状态：请先读这一节

本落地包**已实现并通过本地验证**。它**不是**一个已训练好的模型，本文任何数字都不描述在你的数据上训练出的模型。
下表是诚实的划分。

### 1.1 已实现且已在本地验证

| 项目 | 证据 |
| --- | --- |
| 四个场景生成器各产出 787 条记录 | `gen_critical_value.py`、`gen_medication_review.py`、`gen_triage.py`、`gen_nursing_quality.py`，`--seed 0` |
| 每条记录都通过上游校验器 | `split_data.py` 报 **0 invalid lines、0 conflicting labels**（护理质控丢弃 3 条重复 state → 784 valid） |
| 无标签跌破 5% 下限 | 四个场景均**无** `labels [...] under 5%` 告警、**无** `never labelled` 告警 |
| 记录数算术正确 | 五个 spec 的 `plan_size.py` 均输出 `generate at least 787 records` |
| 最小对确实最小 | `gen_critical_value.py` 报告构造了 89 对孪生；独立检查产出的 JSONL 找到 86 对**只差一个**字段的记录对，其中 82 对标签翻转 |
| 双尺寸驱动器输出正确命令序列 | 四个场景 `run_matrix.py --dry-run`；正确拒绝 `icd-coding --sizes 8b,4b` 与未知尺寸 |
| 运行名在 Modal 之前就被校验 | `fullmatch` 拒绝 `critical-value-0.8b-v1`（含点号），接受 `critical-value-8b-v1` |
| 金标抽样与分歧审计可用 | `sample` 抽出 200 条且稀有标签有覆盖；`audit` 检出 `is_critical` 12.7% 并返回 exit 1 |
| 测试通过 | 新增 16 项测试通过；连同 `test_skill_scripts.py` 共 34 项通过 |
| 包内链接全部可解析 | `medical/` 内全部相对链接与两个锚点均已验证 |

### 1.2 已实现但**未**验证 —— 无真实环境可用

| 项目 | 缺什么 |
| --- | --- |
| **从未跑过一次训练** | 不存在任何 `result.json`。**因此本文不引用任何关于「在你的数据上训练出的模型」的 accuracy / Brier / ECE / coverage 数字。**下文所有性能数字均为 Kev 官方已发布的公开基准，不是医疗场景结果。 |
| 两条基线均未实测 | `evaluate --run jaredpalmer/kev-0.8b` 与 `--run jaredpalmer/kev-4b` 都没跑过。定容用的 `--baseline-acc 0.75` 是**占位默认值**，不是实测值。 |
| 中文 token 预算未实测 | `kev_modal.py::validate` 从未运行。中文混合语言 state 是否仍控制在 384 state tokens 以内，是**按字符数估算的假设，不是实测结论**。 |
| 没有任何真实数据 | 全部记录均为合成。本仓库不含任何临床数据。 |
| 金标集未经审校 | `make_goldset.py sample` 产出的 200 条是**待审校池**。没有任何临床或药学人员核对并签字。 |
| 蒸馏路径从未执行 | `generate_data.py` 未运行过，只验证了程序化生成路线。 |
| 没有任何部署 | `modal deploy` 从未调用，只验证了命令序列正确。 |
| 廉价 GPU 未验证 | 在 L4/A10G 上训练可能便宜得多，但 skill 只文档化了 H100 的时长。 |

### 1.3 上线前需要领域专家复核

**本包的三张规则表是基于文献的默认值，不是任何一家医院的实际标准。** 它们结构自洽、内部一致，但它们是你
自身规范的**占位替身**：

| 表 | 文件 | 必须由谁替换 |
| --- | --- | --- |
| 危急值阈值、通知时限档位、危急区间 | `gen_critical_value.py` | **你所在检验科**的危急值标准，逐项核对 |
| 药品禁忌、剂量上限、特殊人群 | `gen_medication_review.py` | **你所在药学部**的处方集与规则 |
| 护理质控检查表条目与严重度 | `gen_nursing_quality.py` | **你所在护理部**的检查表 |

改阈值时要改**两处**：生成器的规则表与 spec 的 `guidance`。两者必须一致，否则合成数据与蒸馏数据会悄悄分叉。

---

## 2. 这是什么 · 与 `medical/` 的关系

两层结构，遵循 `AGENTS.md` 的 "one canonical home" 约定：

| 层 | 路径 | 角色 |
| --- | --- | --- |
| **主题入口** | `docs/sft-medical.md`（本文）+ `docs/sft-medical_CN.md` | 叙述层：为什么这样设计、哪些已验证、哪些没有、上线前还差什么 |
| **实现层** | [`docs/medical/`](./medical/README.md) | 5 个场景 spec、7 个生成器模块、双尺寸驱动器、16 项测试 |

读本文以决定**是否**做与**怎么做**；到 `medical/` 去看**怎么执行**。

---

## 3. 基座选型纠偏 —— 在做任何事之前先读这一节

让这个项目失败最快的方式，就是去微调一个裸基座。

`skills/kev-finetune/SKILL.md` 的 Gotchas 原文：

> `--init-from` must be a Kev checkpoint (Hub id or a run name on the volume); base, LoRA rank and head size
> are read from it. **Do not pass `--base`.**

原因是 **pointer head**（指针读出层）：Kev 在选项边界 token 上做指针读出。裸 Qwen checkpoint 没有这一层，
读出层无从初始化。

| | Kev-0.8B | Kev-4B |
| --- | --- | --- |
| Hub id | `jaredpalmer/kev-0.8b` | `jaredpalmer/kev-4b` |
| 基座 | `Qwen/Qwen3.5-0.8B-Base`（Apache-2.0） | `Qwen/Qwen3.5-4B-Base`（Apache-2.0） |
| 形式 | LoRA adapter + pointer head | LoRA adapter + pointer head |
| 权重修订 | `9a45d25e` | `139fdd94` |
| 发布温度 | 2.35 | 2.41 |

- ✗ `--init-from Qwen/Qwen3.5-0.8B` / `Qwen/Qwen3.5-4B` —— 无 pointer head
- ✓ `--init-from jaredpalmer/kev-0.8b` / `jaredpalmer/kev-4b`
- `kev_modal.py` 的 `DEFAULT_INIT = "jaredpalmer/kev-4b"`，所以 **0.8B 轨必须显式传 `--init-from`**

### 3.1 四层继承

```
Qwen/Qwen3.5-0.8B-Base（冻结）      Qwen/Qwen3.5-4B-Base（冻结）
  └─ jaredpalmer/kev-0.8b              └─ jaredpalmer/kev-4b
     T=2.35（公开数据）                  T=2.41
        └─ <scenario>-8b-v1                 └─ <scenario>-4b-v1
           医疗 delta；head.pt 内含          医疗 delta；head.pt 内含
           为你的数据重拟合的 temperature        为你的数据重拟合的 temperature
```

免费继承的东西：

- `lr=0.0` 时沿用各 init 自身的训练参数 —— **0.8B 是 4e-5，4B 是 2e-5**。`MAX_DELTA_LR = 5e-5` 是硬顶，
  医疗 delta 永远不会比已发布的 delta 训得更热。
- `--replay 2000` 混入公开 `decision-v7` 记录以保住通用能力。
- 一次 `train` 跑完全部：delta 微调 → 在 calibration 切片拟合温度 → **同时在你的 calibration 切片上重拟合
  baseline 的温度**，使零样本对照公平 → 打分 development → 配对 bootstrap → 300 条公开数据遗忘检查。

---

## 4. 双尺寸架构：一份数据，两个模型

**这套设计所依赖的事实：** `split_data.py` 按 **state 哈希**（state 经 casefold 与空白归一后的 sha256）分组
划分。该分组**与模型无关**。因此同一份 `data/<scenario>/{train,calibration,development}.jsonl` 可以直接喂给
两个尺寸的 `--init-from`。

四条推论：

1. **蒸馏成本只付一次。** 一份数据、一份金标、一个 dev set、两个模型。
2. **跨尺寸 `compare` 有效。** 两次运行在同一份 `development.jsonl` 上打分，所以
   `compare --a x-4b-v1 --b x-8b-v1` 给出真实的配对 bootstrap。0.8B 与 4B 的差距从「看法」变成「**度量**」。
3. **8 分钟的反馈闭环。** 0.8B 在 H100 上约 8 分钟。用它先证明 spec 与规则表是对的，再去花 15 分钟一轮的 4B
   成本上发现阈值写错了。
4. **分层路由与兜底。** 两个端点共存：低风险高吞吐判定交 0.8B，高风险语义判定交 4B，阈值各自独立。4B
   冷启动期间可由 0.8B 服务。

### 4.1 两个尺寸互补，不是先后替代

| 维度 | Kev-0.8B | Kev-4B |
| --- | --- | --- |
| 默认 lr（沿用 init） | 4e-5 | 2e-5 |
| 典型训练时长（400–1000 条，H100） | ~8 分钟 | ~12–15 分钟 |
| 服务 GPU（fine-tune 默认） | `L4` | `L4`（有负载时 `L40S`） |
| 空闲后冷启动 | ~40 秒 | ~35 秒 |
| 预热模型耗时（6 题，新/重复状态） | 23 / 16 ms | 42 / 28 ms |
| delta 体积（已发布 tarball 参考） | 46 MB | 131 MB |
| breadth-v1 机会校正指数 | 23.3 | 38.0 |
| transfer-v4 锁定 OOD（acc / Brier） | 0.697 / 0.397 | 0.838 / 0.224 |
| hard-v1 程序化标签（acc / Brier） | 0.665 / 0.460 | 见 model card |
| 已验证上下文 | 8,192 tokens | 8,192 tokens |

> 上面四行基准是 **Kev 官方已发布的公开数字**，列出来是为了让你能对两个尺寸做量级比较。它们不是医疗场景结果，
> 也不预测两个模型在你的决策上会得多少分。只有你自己跑 `evaluate` 才能知道。

### 4.2 0.8B 的三条禁用项

每一条都是实测能力上限，且直接命中医疗工作：

| 限制 | 实测 | 在本领域的后果 | 对策 |
| --- | --- | --- | --- |
| 日期算术 | `deadline` 家族上 0.35（4B：0.65） | 孕周、疗程天数、有效期 | **生成阶段预计算日期字段** —— 见 §8.4。`KEV_DATE_FACTS=1` 可作辅助，但此处未实测。 |
| 知识由基座决定 | MMLU-Pro 低至 0.230 | ICD 编码合理性需要临床知识 | 该场景**仅 4B** |
| 工具路由 | When2Call 0.133 —— **低于机会水平** | 绝不能让它决定「是否需要去外部系统查一下」 | 在 spec 的 `guidance` 里显式禁止 |

**0.8B 的置信度也更不可靠。** 发布说明记载：一次在留出数据上的 refit 让 0.8B 的校准**在注册容差之外变得更差**，
而 4B 没有改善（Brier 差异 −0.0001 [−0.0005, +0.0003]）。实际含义：0.8B 的 `mean_conf` vs `acc` 与
`confident_error_rate` 两项要比 4B 卡得更严。见 §10。

### 4.3 运行名规范（含一个真实陷阱）

`kev_modal.py` 用 `NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}")` 配合 **`fullmatch`** 校验运行名 ——
只允许字母、数字、连字符、下划线，最长 80 字符。**不允许点号。**

- ✓ `critical-value-8b-v1`、`triage-4b-v2`
- ✗ `critical-value-0.8b-v1` —— **点号会被拒绝**

所以尺寸标识写作 `8b` / `4b`，**永远不用 `0.8b`**。运行名**不可变**：若 `/runs/<name>` 已存在会抛
`FileExistsError`，必须换名重试。`modal run` 因网络错误失败时可能已起容器 —— 重启前先 `modal app list`。

`run_matrix.py` 在本地施加同样的 `fullmatch`，所以坏名字会在生成任何数据之前就失败。

---

## 5. 记录数

定容使用 `plan_size.py` 的 McNemar 配对近似
（`baseline_acc=0.75`、`min_gain=0.05`、`power=0.8`、`regressions=0.05`、15%/15% 划分）。development 所需
**问题数**恒为 **469**；每条 state 上打包的问题越多，记录数越低。

| 每条记录问题数 | 1 | 2 | 3 | **4（本包）** | 5 |
| --- | --- | --- | --- | --- | --- |
| development 记录 | 469 | 235 | 157 | 118 | 94 |
| calibration 记录 | 469 | 235 | 157 | 118 | 94 |
| **总记录数** | 3127 | 1567 | 1047 | **787** | 627 |
| train 记录 | 2189 | 1097 | 733 | 551 | 439 |

本包五个 spec 均为**每条记录 4 个问题**，因此每个场景需要 **787 条**（train 551 / calibration 118 /
development 118），两个尺寸共用。

为什么打包问题是全部经济性所在：一条 state 承载四个决策要 787 条记录；四个各含一个问题的数据集要
4 × 3127 条。正是这一点（而非参数量）让决策模型变得便宜。

两点提醒：

- **非配对**上界确实依赖 `--baseline-acc`：baseline 0.75 → 1092，0.60 → 1468。0.8B 基线更弱 ⇒ 上界更大 ——
  这正是必须先实测两条基线再定容的原因。
- calibration 必须**至少承载 100 个问题**，否则温度拟合与各项分数都不稳定。

关于「量不能省」的上游实测证据：400 条只得到 **+0.6 点、CI ±6 点**（毫无意义），而 1050 条得到
**+5.9 点、CI [+2.3, +9.7]**。纯蒸馏场景下，第一次就把数据集定够，不要指望后续补量。

### 5.1 与原计划的差异

| 项 | 计划 | 实际 | 原因 |
| --- | --- | --- | --- |
| 记录数 | 627（按 5 问题/记录） | **787**（4 问题/记录） | 五个 spec 实测均为 4 个问题，`plan_size.py` 输出 787 |

---

## 6. 五个场景与尺寸分工

| 期次 | 场景 | 尺寸安排 | 理由 |
| --- | --- | --- | --- |
| **一期** | 危急值复核 + 导诊分诊 | 危急值**双轨**；导诊 4B 为主，并跑一次 0.8B 作为能力不足的实证对照 | 危急值标签可完全由规则派生 → 程序化生成给出零漂移标签。双尺寸闭环在这里端到端跑通 |
| **二期** | 用药/医保审核 + 护理质量管控 | **双轨** | 规则明确、选项可控，复用一期验证过的闭环与生成器底座 |
| **三期** | 病历编码 ICD | **仅 4B** | 最难：长文本、大标签空间、罕见组合，且需要临床知识 |

不要一次跑五个场景。纯蒸馏下最糟的失败模式是：跑了三轮才发现闭环本身是坏的，却分不清是数据问题还是
流程问题。

### 6.1 各场景的问题设计

| 场景 | 类型组合 | 尺寸轨 | 设计要点 |
| --- | --- | --- | --- |
| 导诊分诊 | `choice`（科室，14 项）+ `noul`（是否需立即人工）+ `score`（严重度） | 4B 为主 | 14 个科室在 787 条下每项都能过 5% 下限。`guidance` 必须定死**多症状竞争时的优先级**（如胸痛+呼吸困难 → 心内科） |
| 危急值复核 | `noul`（是否危急）+ `score`（通知时限，4 档）+ `choice`（依据项目） | 双轨 | 标签由阈值表派生。被刻意移除关键元素的记录带 50/50 的 `target`，教「无证据即无把握」 |
| 用药/医保审核 | `choice`（审核结论）+ `noul`（是否需药师复核）+ `choice`（问题类型，5 项） | 双轨 | 规则来自处方集：禁忌、剂量上限、重复用药、特殊人群、适应症不符。多规则命中时**严重度取最高** |
| 护理质量管控 | `choice`（问题类型，6 项）+ `noul`（是否需上报）+ `score`（严重度）+ `choice`（可预防性，3 项） | 双轨 | 标签由检查表条目派生。`issue_type=none` ⟺ 严重度 0 且不需上报 |
| 病历编码 | `choice`（候选集内是否合理）+ `noul`（是否需编码员）+ `choice`（证据链缺口） | 仅 4B | **不要求模型直接吐 ICD 码**，而是判定候选集内的合理性并路由给人 |

### 6.2 设计 spec 前必须知道的两条算术约束

1. **`choice` 问题必须有「无发现」选项。** 它在**每条**记录上都会被问到，包括情况并不发生的那些记录。缺了这个
   选项，正常记录会被贴上一个无意义的标签。
2. **`N` 个选项各需 ≥5%，强制一个 `5N%` 的最低正例率。** 10 个选项意味着要 50% 的正例才能均衡。这就是
   `critical_item` 取 6 项（危急率 ≥30%）而不是 10 项的原因。

---

## 7. 数据采集

你目前没有带标签数据，所以主路线是程序化生成与蒸馏。原始需求覆盖了全部四个来源，四个都保留。

| 来源 | 在本方案中的定位 | 实现 |
| --- | --- | --- |
| **④ 程序化生成** | **首选。** 对危急值、用药、医保、护理，标签是结构化字段的确定性函数。这也是 0.8B 轨能成立的前提：0.8B 的基座无法提供医学知识，监督信号必须事先算好 | `medical/generators/gen_*.py` |
| **② LLM 蒸馏** | 次选，用于导诊与病历编码：语义丰富、规则难穷举、表述高度多样 | `generate_data.py` + 精雕 `guidance` / `variety` / `state_example` |
| **① 已有数据** | 留给金标集。将来只要有，它就是你能加进来的最有价值的资产 | `convert_data.py`，再 `split_data.py --holdout` |
| **③ 人工撰写** | 风格锚点 + 分歧样本池 | `generate_data.py --dry-run` 打印完整提示词，按批作答（实用上限约 100 条） |

### 7.1 在医疗领域，公开规则资源**就是**「已有数据」

这个垂直领域有一个被低估的事实：危急值标准、处方集禁忌与剂量上限、医保目录限制、ICD 编码规则、护理检查表
—— 它们是**规则**而非带标签记录，但规则引擎可以把它们消费成**零漂移标签**。这是医疗相对通用 LLM 微调的
结构性优势，也是两个尺寸能共用一份数据的原因。

### 7.2 合成开发集的防线

当 dev set 也是合成的，闭环可能自证、什么也证明不了。四道防线：

1. **人工金标集。** `make_goldset.py sample` 按标签组合**分层抽样** 150–250 条，保证稀有组合也被真正审到。
   临床或药学人员按 spec 的 `guidance` 逐条判定并签字。作为 `--holdout` 接入：对半分进 calibration 与
   development，**永不进 train**，且 `split_data` 会额外丢弃与其共享 state 的合成行。最终评测**只跑一次**。
   两个尺寸共用同一份金标 —— 这是尺寸对比可信的前提。
2. **双模型分歧审计。** 两个厂商模型对同一批 state 独立标注。`make_goldset.py audit` **按问题**报出分歧率，
   并以**最差的那一题**为门槛，而不是平均值 —— 3% 的均值可以藏住某一题 13% 的分歧，而在医疗流程里，决定
   「这个标注者在这一题上是否可信」的是单题分歧率。
3. **`guidance` 迭代。** `errors.jsonl` 里每一类反复错误都对应 `guidance` 缺的一句话 —— 这是上游 skill 明确
   写出的机制。
4. **显式标签配额。** 每个标签 ≥5%，且每个选项都必须有机会作为正确答案出现 —— 否则模型学不到一个它从未见过
   被判为正确的选项。

---

## 8. 程序化生成器

生成器不问模型任何问题。它们采样结构化字段、套用阈值表或规则引擎、写出带标签的 Kev 记录。零标签漂移是这里
唯一重要的事。

```
medical/generators/
├── README.md                  总览与如何新增场景
├── common.py                  共用底座：构造 + 自检、配额、边界采样、最小对
├── gen_critical_value.py      阈值表、通知时限档位、最小对、软标签
├── gen_medication_review.py   处方集规则引擎
├── gen_triage.py              科室优先级仲裁、急症红旗
├── gen_nursing_quality.py     检查表条目与派生严重度
├── make_goldset.py            金标抽样 + 双模型分歧审计
└── run_matrix.py              双尺寸编排器（--dry-run 打印命令序列）
```

**病历编码没有生成器**：它需要真实的 HIS/EMR 结构化摘要与临床知识，程序化合成会产出临床上毫无意义的记录。
该场景走蒸馏 + 人工抽检。

### 8.1 配额先于记录

每个生成器都先规划本批的**标签**（`plan_targets`），再构造能实现这些标签的字段。原因在 `split_data.py`：
它会对标签跌破 5%、以及选项从未作为正确答案出现发出告警。若先采样字段再推导标签，分布就由采样噪声决定了。

### 8.2 最小对教会决策边界

`gen_critical_value.py` 产出的配对，state 只差**一个测量值**且标签翻转 —— 血钾 6.2 mmol/L 对 5.9，其余字段
完全相同。这是 `references/data-generation.md` 推荐的做法，Kev 自身的对比式策略数据也是这样构建的。它教会
模型**决策取决于哪个字段**，而不是学到捷径特征。两种口径都已验证：`gen_critical_value.py` 报告构造了 89 对
孪生；独立检查产出的 JSONL 找到 86 对只差一个字段的记录对，其中 82 对标签翻转。（两个数字不同，是因为检查
脚本按患者、context 与检验键集合分组，并统计每组内所有符合条件的配对。）

`common.minimal_pair()` 是共用守卫：改变了多于一个字段、或没有翻转任何标签的孪生记录会被丢弃而不是写出。

### 8.3 采样必须跨越边界

值从阈值的**两侧**采样，并**在边界附近加密**（`|x - threshold| < δ`）。只在远离边界处采样，模型学到的是
「数值很高」这种平凡特征，而不是真正的切分点。

### 8.4 日期字段预计算 —— 这是 0.8B 的规避手段，不是风格选择

凡是需要日期算术的判定（孕周、疗程天数、用药天数、有效期），生成器**把数字算好并作为字段放进 state**。
模型的任务变成读一个数字，而不是做它实测做不好的算术。`days_on_drug` 以整数形式出现，绝不是
`started` / `prescribed` 日期。

### 8.5 均衡先验 vs 临床先验 —— 上线前必读

`split_data.py` 要求每个标签 ≥5%，所以一份均衡的危急值数据集危急率**至少 30%**。而真实报告中危急值约
**1–3%**。

这是一个真实且有意的错配。它之所以存在，是因为均衡正是让比较有统计意义的前提；但这也意味着
**模型输出的概率是条件在均衡先验上的**，直接用绝对概率设生产阈值会在真实流量上过度报警。上线前必须用
`result.json` 结合真实流量重新推导工作阈值。`data-format.md` 讲具体做法。

---

## 9. 执行

```bash
# 先打印完整命令序列 —— 花钱之前先审阅
python3 docs/medical/generators/run_matrix.py --scenario critical-value --sizes 8b,4b --dry-run

# 执行（fail-fast；用 --start-from <step> 续跑）
python3 docs/medical/generators/run_matrix.py --scenario critical-value --sizes 8b,4b --secret kev-serve-key
```

步骤顺序：`plan_size → 生成 → 划分 → validate ×2 → train(0.8B) → train(4B) → compare → 部署两个端点`。
同一份 `data/<scenario>/` 目录喂给两次 `train` —— 这正是跨尺寸 `compare` 有效的前提。

```bash
S=skills/kev-finetune/scripts

# 0. 在同一份小 dev split 上测两条基线（信任何定容之前先做）
modal run $S/kev_modal.py::evaluate --data data/cv --name base-8b --run jaredpalmer/kev-0.8b
modal run $S/kev_modal.py::evaluate --data data/cv --name base-4b --run jaredpalmer/kev-4b

# 1. 定数据集规模
python3 $S/plan_size.py docs/medical/specs/critical-value.json --baseline-acc 0.75

# 2. 只生成一次
python3 docs/medical/generators/gen_critical_value.py --n 787 --out data/cv.jsonl --seed 0

# 3. 抽金标池 → 人工审校 → 带 --holdout 划分
python3 docs/medical/generators/make_goldset.py sample data/cv.jsonl --n 200 --out data/cv.gold.jsonl
python3 $S/split_data.py data/cv.jsonl --out data/cv --holdout data/cv.gold.jsonl

# 4. 中文 token 预算的 CPU 预检 —— 两个尺寸各一次
modal run $S/kev_modal.py::validate --data data/cv --init-from jaredpalmer/kev-0.8b
modal run $S/kev_modal.py::validate --data data/cv --init-from jaredpalmer/kev-4b

# 5. 同一份数据上训练两个尺寸
modal run $S/kev_modal.py::train --data data/cv --name cv-8b-v1 --init-from jaredpalmer/kev-0.8b
modal run $S/kev_modal.py::train --data data/cv --name cv-4b-v1 --init-from jaredpalmer/kev-4b

# 6. 量化差距
modal run $S/kev_modal.py::compare --a cv-4b-v1 --b cv-8b-v1

# 7. 两个共存端点，各用独立 app 名
modal secret create kev-serve-key KEV_API_KEY=$(openssl rand -hex 24)
KEV_APP_NAME=kev-cv-8b KEV_SERVE_SECRET=kev-serve-key KEV_SERVE_RUN=cv-8b-v1 modal deploy $S/kev_modal.py
KEV_APP_NAME=kev-cv-4b KEV_SERVE_SECRET=kev-serve-key KEV_SERVE_RUN=cv-4b-v1 modal deploy $S/kev_modal.py
```

`medical/runbook.md` 给出每一步的预期输出、怎么读、以及失败怎么办，另附 14 条排错表。

### 9.1 唯一会静默失败的限制

| 限制 | 数值 |
| --- | --- |
| State tokens | **≤ 384** |
| 打包请求 | ≤ 2048 |
| 每题分支 | ≤ 1024 |

超限记录**会被训练器静默丢弃**，只打印一个数量。更麻烦的是，`split_data.py` 的 `STATE_CHARS_WARN = 1400`
在源码注释里写的是「~384 tokens of **English**」—— 它**对中文偏松**，照搬会悄悄丢数据。中文 384 tokens
约合 380–560 汉字，但医疗文本数字、缩写、计量单位密集，实际更紧。以 `kev_modal.py::validate` 为准，
**每个尺寸跑一次**，因为各自的 tokenizer 不同。

### 9.2 两条不可商量的规则

- **绝不在 `development.jsonl` 上拟合温度**，也不反复针对它调参。金标集只留最后一次 `evaluate`。
- **校准与阈值属于 checkpoint。** 0.8B 与 4B 的温度不同；每次重训都要重读两份 `result.json`。

### 9.3 为不对称错误代价而设计

漏报危急值的代价远高于误报，因此**不要用 argmax 自动处置**：

- `noul` 问题用**低阈值 + 强制转人工**，阈值取自 `development.calibrated.selective["0.5"|"0.8"].confidence_cutoff`
- 证据不足的记录带 `target: {"false": 0.5, "true": 0.5}`，教「无证据即无把握」
- 利用其固有属性：只有概率、没有生成文本 ⇒ 结构上无幻觉诊断、无自由文本 PHI 外泄
- **双尺寸路由即风险分层**：低风险高吞吐交 0.8B，高风险语义交 4B，阈值各自独立
- 人工复核是最后一道闸。不要追求 100% 自动化。

---

## 10. 验收门槛

每一项都是可以查的数字，不是主观判断。

| 维度 | `result.json` 字段 | 通过条件 | 两尺寸差异 |
| --- | --- | --- | --- |
| 增益真实 | `bootstrap.acc.ci95` | **CI 排除 0**。CI 含 0 说明数据太薄或增益太小 —— 改数据，不是加量 | 各自判定 |
| 校准更好 | `development.calibrated.ece`、`confident_errors` | calibrated 优于 raw，且微调模型的 `confident_error_rate` **不得超过其 baseline** | **0.8B 更严** —— 已知更易过度自信 |
| 诚实 | `mean_conf` vs `acc` | 相差在几个点内。远高于 `acc` 即过度自信 —— 通常是 epoch 太多或训练 state 近似重复 | 0.8B 为重点监控 |
| 未遗忘 | `regression` 段 | 300 条公开 `decision-v7` 上 accuracy 下降 **≤ 2 点**。更多说明 delta 漂移 | 各自判定 |
| 业务价值 | `development.calibrated.coverage_at_5pct_error` | 达到你设定的目标。危急值场景的目标应远高于常规场景 | — |
| 事后验证 | `plan_size.py --from-result` | 已显著 / 还需多少条 / 增益太小不值得追 | 各自跑 |
| 温度 | `result.json.temperature` | 只在 calibration 拟合；金标集只评一次 | **两尺寸不同，绝不可互相套用** |
| 尺寸决策 | `compare --a <4b> --b <8b>` | CI 排除 0 → 4B 确实更强、值得多花的钱。CI 含 0 → **选 0.8B** | — |

**金标终评**：用留出的人工金标文件跑 `evaluate --remote <url>`（`KEV_REMOTE_API_KEY`），**每个尺寸各跑一次**，
确认线上数字与离线一致。远程概率按原样采用（不做温度拟合），所以这个比较回答的是「服务给你的东西」vs
「你校准后的模型给你的东西」。

---

## 11. 优化闭环

1. `pull --name <run>` 取回 `result.json`、`errors.jsonl`、`train.log`
2. 读 `errors.jsonl` 的开头 —— 它按置信度排序，所以头几行是模型**最自信的错误**
3. 把每一类反复错误翻译成 spec `guidance` 里缺的那一句话
4. 程序化场景：改阈值表或规则表。导诊与编码：改 `guidance` 与 `variety`，再定向生成记录
5. 重新生成 → 重新划分 → 训练为 `-v2` → `compare --a x-2b-v2 --b x-2b-v1`

按收益排序，来自上游 skill：

1. **更多更好的数据** —— 训练集翻倍通常胜过任何超参数
2. 有 1000+ 条记录、且第 1 个 epoch 末尾 loss 仍在下降时用 `--epochs 2`
3. 降 `--lr`（0.8B 从 4e-5、4B 从 2e-5 各自减半），保留 `--replay 2000`，不加 epoch
4. 数据量大且训练时间要紧时用 `--replay 500`
5. 只有当两轮数据改动都推不动 4B 时，才上 `jaredpalmer/kev-9b`

---

## 12. 上线灰度与回滚

**分阶段上线**：影子模式（只记录，与人工结论比对）→ 人工复核（低置信 + 高风险类别强制复核）→ 灰度放量。
医疗场景的默认形态是「模型建议 + 人工确认」，不建议完全无人工的自动处置。用两个尺寸可以分层：先在低风险
判定上放开 0.8B，高风险判定保持 4B + 人工。

**回滚手段（按破坏性递增）：**

1. 把 `KEV_SERVE_RUN` 指回 `jaredpalmer/kev-0.8b` / `jaredpalmer/kev-4b` 并重新部署 —— 模型级，秒级。
   **两个端点可独立回滚**，靠各自不同的 `KEV_APP_NAME` 隔离
2. 客户端 feature flag 关闭调用 —— 应用级，不动服务
3. `modal app stop kev-<scenario>-8b` / `-4b` —— 单独下线一个端点
4. `teardown --run <name> --yes` / `--endpoint` / `--everything [--cache] --yes` —— 清理数据。
   **Modal secret 永不被脚本删除**，需手动 `modal secret delete`
5. 始终保留两个 baseline 端点作兜底 —— 空闲的已部署端点不花钱

---

## 13. 合规与隐私

- **生成前先脱敏。** 姓名、证件号、电话、住院号做哈希或替换，且这一步发生在记录进入生成器**之前** ——
  生成器只会接触已脱敏字段。
- **必须时把数据留在内网。** 把 `KEV_GEN_BASE_URL` 指向本地 Ollama（`http://localhost:11434/v1`），
  蒸馏就不出内网；否则需评估已脱敏的结构化字段是否可以送到外部 API。
- **医疗模型永不公开。** `publish` 默认私有，**不要传 `--public`**。优先把 checkpoint 留在 Modal volume 上。
- **凭据放 Modal secret**（`KEV_SERVE_SECRET` / `KEV_HF_SECRET`），不进仓库。
- **数据留存**：delta 体积很小（按 tarball 参考，0.8B 约 0.1 GB、4B 约 0.3 GB）；`teardown` 的三档差异见
  执行手册。
- **spec 与生成器只含 schema 与规则表 —— 不含任何患者数据。** 真实与金标数据落在 git-ignored 的 `data/`。

---

## 14. 逐项区分已验证与未验证

最重要的一节，在此完整重述一遍，好让任何人不必从全文推断。

### 14.1 已在本地验证

| 检查项 | 命令 | 结果 |
| --- | --- | --- |
| 四个生成器产出数据 | `gen_*.py --n 787 --seed 0` | 各 787 条记录 |
| 上游校验器接受 | `split_data.py <file>` | 0 invalid lines、0 conflicting labels（护理质控丢弃 3 条重复后 784 valid） |
| 标签下限达标 | `split_data.py` 告警 | 无 `under 5%`、无 `never labelled` |
| 定容算术 | `plan_size.py <spec>` | 五个 spec 均输出 `generate at least 787 records` |
| 最小对 | `gen_critical_value.py` 输出 + 检查产出的 JSONL | 构造 89 对孪生；86 对只差一个字段，其中 82 对标签翻转 |
| 双尺寸命令序列 | `run_matrix.py --dry-run` | 四个场景正确；拒绝 `icd-coding --sizes 8b,4b`；拒绝 `27b` |
| 运行名校验 | `check_name` | 拒绝 `critical-value-0.8b-v1`；接受 `critical-value-8b-v1`、`triage_4b-v2` |
| 金标抽样 | `make_goldset.py sample` | 787 中抽 200，稀有标签有覆盖 |
| 分歧审计 | `make_goldset.py audit` | 逐题分歧率；按最差题设门槛；`is_critical` 12.7% 时 exit 1 |
| 测试 | `pytest tests/test_medical_generators.py` | 16 passed；连同 `test_skill_scripts.py` 共 34 passed |
| 链接与锚点 | `medical/` 链接检查 | 全部可解析 |
| Lint | `read_lints` | 0 条问题 |

### 14.2 未验证 —— 无真实环境

| 项目 | 为何重要 |
| --- | --- |
| **完全没跑过训练** | 不存在任何 `result.json`，因此本文不含任何关于「在你的数据上训练出的模型」的实测 accuracy / Brier / ECE / coverage |
| **基线未实测** | `--baseline-acc 0.75` 是占位值。实测两条基线后应重跑定容 |
| **中文 token 预算未实测** | `validate` 从未运行。在它跑过之前，静默丢数据的风险仍然存在 |
| **无真实数据** | 全部合成；本仓库不含临床数据 |
| **金标集未审校** | 200 条是待审校池，不是签字过的金标集 |
| **蒸馏路径未执行** | `generate_data.py` 从未运行 |
| **部署未执行** | `modal deploy` 从未调用 |
| **病历编码无数据** | 只有 spec；无生成器、无记录 |
| **廉价 GPU 训练未测试** | L4/A10G 的省钱可能性合理，但未验证 |

**关于更广的测试套件。** 在 Windows 开发机上，完整 unit 套件报 110 个失败与 6 个收集错误。根因是
`kev/suite.py` 导入了 Unix 专有的 `fcntl`。`git status` 确认 `kev/` 与既有测试**未被本次工作修改**，所以这些
是平台性既有问题，不是本次引入的回归。医疗包自身的测试是绿的。

### 14.3 实现与原计划的差异

| 项 | 计划 | 实际 | 原因 |
| --- | --- | --- | --- |
| 记录数 | 627 | **787** | spec 实测为 4 问题/记录，不是 5 |
| `critical_item` 选项数 | 10 | **6** | `N` 个选项各 ≥5% 强制 `5N%` 正例率；10 项需要 50% 危急率 |
| `quota_labels` 辅助函数 | 提供 | **已删除** | 各场景配额形状不同，统一函数反而成了死代码 |
| 均衡先验告警 | 无 | **新增为 §8.5** | 均衡与临床先验的错配必须在上线前说明 |
| `critical_value.build` 返回 | 一条记录 | `(记录, handle)`，`pair_twin` 独立 | 让「按目标标签构造」与「构造最小对」可独立测试 |

---

## 15. 上线前 checklist

以下每一项都需要真实环境、真实的人或真实机构，都无法在本仓库内完成。

### 15.1 账户与准备

- [ ] Python 3.10+ 与 [`uv`](https://docs.astral.sh/uv/)
- [ ] Modal 账户：`uvx modal setup`
- [ ] 可选，蒸馏用：一个 OpenAI 兼容的 API key；先决定已脱敏的结构化字段是否可以出内网，或自建本地
      Ollama 并把 `KEV_GEN_BASE_URL` 指向它
- [ ] 可选：Hugging Face token，**仅当**你打算做私有发布

### 15.2 规则表 —— 领域复核，阻塞项

- [ ] **检验科**：复核 `gen_critical_value.py` 中每一个阈值、通知时限档位与危急区间
- [ ] **药学部**：复核 `gen_medication_review.py` 中每一条药品规则
- [ ] **护理部**：复核 `gen_nursing_quality.py` 中每一条检查表条目与严重度
- [ ] 每一处修改都要同时更新**生成器规则表**与 spec 的 `guidance`

### 15.3 数据

- [ ] 由临床或药学人员审定 200 条金标池，记录签字人与时间
- [ ] 确认金标集**除**最后一次终评外不作他用
- [ ] 确认脱敏发生在生成之前，且没有任何患者数据进入仓库

### 15.4 度量

- [ ] 实测两条基线：`evaluate --run jaredpalmer/kev-0.8b` 与 `--run jaredpalmer/kev-4b`
- [ ] 用各自实测的 baseline 重跑 `plan_size.py`；若上界差异显著则调整记录数
- [ ] 对**两个尺寸**都跑 `validate`，确认每个分区 `over_limit: 0`
- [ ] 训练两个尺寸；读 `bootstrap.acc.ci95`，确认 CI 排除 0
- [ ] 确认 calibrated 优于 raw，且 0.8B 的 `confident_error_rate` 不超过其 baseline
- [ ] 确认**每个尺寸**的公开数据回归都在 2 个 accuracy 点以内
- [ ] 读**每个尺寸**的 `development.calibrated.selective` 截断点 —— 两者不可互换
- [ ] 跑 `compare --a <4b> --b <8b>`；若 CI 含 0，选 0.8B

### 15.5 上线

- [ ] 先上影子模式：只记录预测并与人工结论比对，不生效
- [ ] 用**真实流量**重新推导工作阈值，而不是用均衡先验下的概率（§8.5）
- [ ] 确认每个 `noul` 问题都有「低阈值 + 强制转人工」规则
- [ ] 确认两个端点使用不同的 `KEV_APP_NAME`，因而可独立回滚
- [ ] 在真正需要之前，先实际演练一次回滚到 baseline
- [ ] 确认已设置 `KEV_SERVE_SECRET`：不设则端点公开，URL 就是唯一秘密
- [ ] 确认任何医疗模型都不会带 `--public` 发布

---

## 16. 文件清单

| 路径 | 行数 / 体积 | 角色 |
| --- | --- | --- |
| `docs/sft-medical_CN.md` | 本文件 | 中文完整译本 |
| `docs/sft-medical.md` | 平行 | 英文主文档 |
| `docs/medical/README.md` | 20,330 B | 中文实现层入口：完整设计叙述 |
| `docs/medical/data-format.md` | 14,551 B | State schema、标签体系、token 预算、均衡先验错配 |
| `docs/medical/runbook.md` | 10,577 B | 11 步命令速查与 14 条排错表 |
| `docs/medical/specs/critical-value.json` | 4,734 B | 危急值 spec |
| `docs/medical/specs/medication-review.json` | 5,302 B | 用药/医保审核 spec |
| `docs/medical/specs/nursing-quality.json` | 5,408 B | 护理质控 spec |
| `docs/medical/specs/triage.json` | 5,085 B | 导诊分诊 spec |
| `docs/medical/specs/icd-coding.json` | 5,842 B | 病历编码 spec（仅 4B） |
| `docs/medical/generators/README.md` | 5,276 B | 生成器总览与如何新增场景 |
| `docs/medical/generators/common.py` | 9,089 B | 共用底座，尺寸无关 |
| `docs/medical/generators/gen_critical_value.py` | 18,152 B | 危急值生成器 |
| `docs/medical/generators/gen_medication_review.py` | 11,507 B | 用药审核生成器 |
| `docs/medical/generators/gen_nursing_quality.py` | 9,895 B | 护理质控生成器 |
| `docs/medical/generators/gen_triage.py` | 9,364 B | 导诊生成器 |
| `docs/medical/generators/make_goldset.py` | 7,619 B | 金标抽样与分歧审计 |
| `docs/medical/generators/run_matrix.py` | 7,461 B | 双尺寸编排器 |
| `tests/test_medical_generators.py` | 16 项测试 | 生成器、spec 与编排器测试 |
| `.github/workflows/ci.yml` | 一行 | 已加入 CI unit job |

**`skills/kev-finetune/` 下没有任何文件被修改。** 该目录有 `skills-lock.json` 打包边界，且
`tests/test_skill_scripts.py` 依赖其结构。医疗侧完全通过 spec 与外部生成器适配。

---

[English](./sft-medical.md) · 实现：[`medical/`](./medical/README.md) · 上游 skill：
[`skills/kev-finetune`](../skills/kev-finetune/SKILL.md)
