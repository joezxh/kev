<p align="center">
  <a href="./data-format.md"><img alt="中文" src="https://img.shields.io/badge/%E4%B8%AD%E6%96%87-orange?style=for-the-badge"></a>
  <a href="../../skills/kev-finetune/references/data-format_CN.md"><img alt="English" src="https://img.shields.io/badge/English-blue?style=for-the-badge"></a>
</p>

# 医疗 state 数据格式定义

[← 返回主方案](./README.md) · 导航：[执行手册](./runbook.md) · [生成器说明](./generators/README.md) · [skill 格式文档](../../skills/kev-finetune/references/data-format_CN.md)

本文件定义医疗五个场景的 state schema 与 questions 标签体系。**格式定义与模型尺寸无关** —— 0.8B 与 4B 共用同一套 spec 与同一份数据（见[主方案的共享数据架构](./README.md)）。

---

## 一、硬约束：违反即静默丢数据

| 约束 | 数值 | 违反后果 |
| --- | --- | --- |
| state tokens | **≤ 384** | 训练器**静默丢弃**并打印一个数量，不报错 |
| 打包请求（state + 全部问题 + 选项） | ≤ 2048 | 同上 |
| 每个问题分支 | ≤ 1024 | 同上 |

两个尺寸该约束**完全相同**（0.8B 与 4B 均只验证到 8,192 token 上下文，远高于 384），所以格式定义不需要按尺寸分叉。

### 中文阈值陷阱（必读）

`skills/kev-finetune/scripts/split_data.py` 的超长告警阈值是：

```python
STATE_CHARS_WARN = 1400   # ~384 tokens of English; longer states are dropped by the trainer
```

注释自己写明了这是**英文**口径。中文按 Qwen 分词器，384 tokens 大致只对应 380–560 汉字；医疗文本又含大量数字、英文缩写与计量单位，**token 密度偏高**。照搬 1400 字符会让大量记录在训练阶段被静默丢弃，而你只会在 `train.log` 里看到一行 `dropped ...`。

**规则：一律以 `validate` 实测为准，不以字符数估算。**

```bash
# CPU only，无 GPU 成本；两个尺寸各跑一次
modal run skills/kev-finetune/scripts/kev_modal.py::validate --data data/cv --init-from jaredpalmer/kev-0.8b
modal run skills/kev-finetune/scripts/kev_modal.py::validate --data data/cv --init-from jaredpalmer/kev-4b
```

输出里各分区的 `over_limit` 与 `state_tokens.limit` 是权威判据。对象形状 state 的长度按 `split_data.render_length` 口径估算（对象即 `len(json.dumps(value, ensure_ascii=False))`）。

### 本套 spec 的实测余量

下表是 5 个 spec 的 `state_example` 实测值（`key: value` 渲染后字符数 ÷ 1.6，作为中文混合文本的保守 token 估计）：

| spec | JSON 字符 | `key: value` 字符 | 估算 tokens | 对 384 预算 |
| --- | --- | --- | --- | --- |
| `medication-review.json` | 228 | 206 | ~129 | 余量充足 |
| `nursing-quality.json` | 242 | 220 | ~138 | 余量充足 |
| `triage.json` | 262 | 237 | ~148 | 余量充足 |
| `critical-value.json` | 288 | 272 | ~170 | 余量充足 |
| `icd-coding.json` | 382 | 357 | ~223 | 余量最小，仍余约 40% |

`icd-coding` 余量最小（8 个字段），扩字段时优先从它下手。**真实记录长度会浮动**（多症状、多检验项、多诊断），所以 `validate` 是必做步骤而非可选项。

---

## 二、对象形状 state schema

Kev 把对象 state 渲染成 `key: value` 行，**字段名对模型可见** —— 字段名是模型的一部分，必须跨全部记录完全一致，**不可随意改写或缩写**。改字段名等于换了一个任务，训练出的权重不会迁移。

字段数控制在 **6–10 个**。数值字段用短键名（`K+`、`Cr`、`PLT`）以省 token。

### 五个场景的实际字段

| spec | 字段 |
| --- | --- |
| `critical-value.json` | `patient`, `context`, `labs`, `ref_ranges_included`, `missing_context` |
| `triage.json` | `patient`, `channel`, `chief_complaint`, `duration`, `accompanying`, `history`, `vitals`, `red_flags` |
| `medication-review.json` | `patient`, `state_flags`, `allergies`, `current_meds`, `current_rx`, `days_on_drug`, `indication` |
| `nursing-quality.json` | `patient`, `ward`, `nursing_level`, `check_point`, `observed`, `dependencies`, `risk_scores` |
| `icd-coding.json` | `patient`, `length_of_stay_days`, `primary_dx`, `secondary_dx`, `procedure`, `key_findings`, `past_history`, `clinical_course` |

### 通用字段骨架

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `patient` | string | ✔ | `male 67` / `female 34, gestation 28 weeks` —— 年龄性别，孕周与哺乳状态写这里 |
| `chief_complaint` / `context` | string | ✔ | 主诉或临床背景，1–3 句。**患者原话优先**，口语化表达要保留 |
| `duration` / `days_on_drug` | string / int | 视场景 | 时间跨度。**已由生成器算好**，不要求模型做日期运算 |
| `labs` | object | 危急值必填 | 检验项目短名 → 数值+单位 |
| `vitals` | string | 视场景 | 生命体征数值串 |
| `history` / `past_history` | string \| list | 视场景 | 基础病、过敏史、手术史 |
| `medications` / `current_meds` | list | 视场景 | 既往或当前用药 |
| `key_findings` | string \| list | 视场景 | 关键阳性发现 |
| `risk_scores` | string | 护理质控 | 已有风险评分（如 Braden / Morse） |
| `missing_context` | list | 危急值必填 | 被刻意移除的要素，驱动「无证据即无把握」样本 |

### 三条 state 设计规则

1. **不含医生结论。** state 只放「报告/病历里写了什么」，不放「医生怎么判」。否则模型只需复读结论，等于没学。
2. **日期与疗程字段一律预计算**（见下节）。
3. **超长字段在生成阶段截断/摘要**，不依赖训练器兜底丢弃。

---

## 三、日期字段预计算（规避 0.8B 的已知弱项）

发布说明记载，`deadline` 类日期算术策略上 **0.8B 仅 0.35、4B 仅 0.65**（对比 Jev 0.95）—— 日期算术是 27B 以下每个尺寸的最弱项。

**对策：把日期算术从模型任务里彻底拿掉。** 生成阶段算好，模型只读结果。

| 不要这样（模型要算） | 要这样（生成器算好） |
| --- | --- |
| `"started": "2026-03-02", "today": "2026-03-19"` | `"days_on_drug": 17` |
| `"lmp": "2025-11-20"` | `"gestation_weeks": 16` |
| `"admission": "2026-02-01", "discharge": "2026-02-10"` | `"length_of_stay_days": 9` |

本套 spec 已按此设计：`medication-review` 用 `days_on_drug`、`icd-coding` 用 `length_of_stay_days`、`triage` 用 `duration`。`KEV_DATE_FACTS=1` 可作辅助，但**依赖模型算日期的样本在 0.8B 轨上不可靠**，本方案不依赖它。

---

## 四、questions 标签体系

5 个 spec 均为 **4 个问题/记录**，共享同一份 state 文本。实测记录数（`plan_size`，`baseline_acc=0.75`、`min_gain=0.05`、`power=0.8`）：**每场景 787 条**（train 551 / calibration 118 / development 118），development 需 469 个配对问题。

> 配对口径下 469 与 `baseline_acc` 无关；非配对保守上界随基线变化：baseline 0.75 → 1092，baseline 0.60 → 1468。0.8B 基线更弱、上界更大 —— 这正是必须先实测两条基线的原因。

| spec | 问题 | type | 选项数 | 0.8B | 4B |
| --- | --- | --- | --- | --- | --- |
| `critical-value` | `is_critical` | noul | 2 | ✔ 主力 | ✔ |
| | `notify_within` | score | 4 | ✔ 主力 | ✔ |
| | `critical_item` | choice | 6 | ✔ 主力 | ✔ |
| | `evidence_sufficient` | noul | 2 | ✔ 主力 | ✔ |
| `triage` | `department` | choice | 14 | ✗ 对照 | ✔ 主力 |
| | `immediate_human` | noul | 2 | ✗ 对照 | ✔ 主力 |
| | `acuity` | score | 3 | ✗ 对照 | ✔ 主力 |
| | `red_flag` | noul | 2 | ✗ 对照 | ✔ 主力 |
| `medication-review` | `verdict` | choice | 3 | ✔ 主力 | ✔ |
| | `needs_pharmacist` | noul | 2 | ✔ 主力 | ✔ |
| | `issue_type` | choice | 6 | ✔ 主力 | ✔ |
| | `severity` | score | 4 | ✔ 主力 | ✔ |
| `nursing-quality` | `issue_type` | choice | 6 | ✔ 主力 | ✔ |
| | `reportable` | noul | 2 | ✔ 主力 | ✔ |
| | `severity` | score | 4 | ✔ 主力 | ✔ |
| | `preventable` | choice | 3 | ✔ 主力 | ✔ |
| `icd-coding` | `coding_reasonable` | choice | 3 | ✗ | ✔ 主力 |
| | `needs_coder` | noul | 2 | ✗ | ✔ 主力 |
| | `evidence_gap` | choice | 6 | ✗ | ✔ 主力 |
| | `confidence_tier` | score | 3 | ✗ | ✔ 主力 |

**选项数与 `<5%` 告警的关系**：`split_data.py` 会对占比低于 5% 的标签告警，对**从未作为正确答案出现**的选项告警（模型学不到）。787 条记录下每个选项平均约 79 条，选项最多的 `triage.department`（14 项）也有约 56 条 —— 均安全。但**选项数是成本杠杆**：`triage.department` 若扩到 30 个科室，每项只剩约 26 条，接近告警线，且 0.8B 在 30 分类上会更吃力。科室请控制在 **10–20 个**。

### 两条容易踩的算术约束

**(1) 每个 choice 问题都要有「无问题」选项。** 所有问题在每条记录上都会被问到，包括没有该问题的记录。若 `critical_item` 只有 10 个危急项目而没有 `none`，正常报告就被迫贴上一个无意义标签 —— 模型学到的是噪声。给每个 choice 加一档「无 / 不适用」，让正常记录有正确的答案。

**(2) 选项数决定了该问题的最小正例率。** `N` 个选项各需 ≥5%，正例率就至少是 `5N%`。`critical_item` 收成 6 项（`none` + 5 个临床类别）意味着危急样本至少要占 30%。这是**均衡要求与临床真实发生率（约 1–3%）的直接冲突**，处理方式见下节。

### 均衡先验与真实先验的错配（上线前必读）

`split_data.py` 要求每个选项至少 5%，所以训练集是**均衡**的；而临床线上危急值只占约 1–3% 的报告。两者错配的后果是：**模型输出的概率是条件在这个均衡先验上的**，直接按绝对概率设阈值会在真实流量上过度报警。

应对（写进上线清单，不可省略）：

1. 训练/校准保持均衡（这是 skill 的硬要求，也是学得到边界的前提）。
2. `result.json` 里的 `selective.confidence_cutoff` 是**均衡先验下**的切点，直接拿来用会偏保守。
3. **上线前用真实流量重新标定阈值**：影子模式跑一段真实报告，比较模型分数与人工结论的实际阳性率，再据此移动切点。`coverage_at_5pct_error` 作为业务指标也要在真实分布上重算。
4. 若真实阳性率极低，可考虑先用 0.8B 全量筛 + 4B 复核的两级架构（见主方案的雙尺寸路由），把漏报风险压住。

### `guidance` 是首要质量杠杆

`guidance` 承载标注规则，每个 spec 都写明三件事，缺一不可：

1. **判定规则的精确口径**（阈值表、优先级顺序、联动约束）
2. **边界情形如何裁决**（多项目同时危急取最快档；多规则命中取最高严重度）
3. **不可推断的边界**（不得凭常识补全病历、不得凭科室反推红旗）

`errors.jsonl` 里每一类反复出现的错误，都对应 `guidance` 缺的一句话 —— 这是 skill 明文给出的机制，也是迭代主抓手。

> **一致性要求**：程序化生成器的阈值表是**权威判据**，`guidance` 里的阈值必须与它逐项一致。改阈值时两处都要改，否则合成数据与 LLM 蒸馏数据的标签会悄悄分叉。`generators/README.md` 说明以哪一处为准。

### 软标签 `target` 的正确用法

用于**证据被刻意移除**的记录，教模型「没有证据就没有把握」：

```json
"is_critical": {
  "type": "noul",
  "instructions": "该报告中的任一检验项目是否触及危急值（需要立即临床干预）？",
  "label": true,
  "target": {"true": 0.5, "false": 0.5}
}
```

`split_data.check_question` 的校验规则：`target` 的键必须落在该问题的合法键空间内（noul 为 `true`/`false`，choice 为选项名，score 为字符串形式的等级下标），值必须非负且总和 > 0。

> **两条数据生产路径的能力差异**：`generate_data.py`（LLM 蒸馏）**只会写 `label`**；只有程序化生成器能产出 `target`。因此「证据缺失」类样本必须由生成器产出，不能靠蒸馏。

---

## 五、病历编码的两级拆分

病历全文远超 384 tokens，**直接塞入必然被丢弃**。本场景采用两级方案：

**一级：字段级结构化抽取**（前置步骤，可由现有 HIS/EMR 直接导出，或用规则+模型抽取）

抽取字段：主诉、现病史要点、入院诊断、诊断依据（检验/影像阳性发现）、手术操作、既往史、住院天数。

**二级：在结构化摘要上做编码合理性判断**，而非直接生成编码。

为什么不要求模型直接吐 ICD 码：码空间数千、选项爆炸，每一项都不可能达到 5% 均衡，模型对没见过的码一律学不到。降级为「候选集内合理性判定 + 是否需人工」后，`choice` 只剩 3 个选项，标签可均衡。

罕见组合与长尾：显式过采样；证据确实不足时用 `insufficient_record` + `confidence_tier=2` **显式表达不确定**，而不是硬猜一个答案 —— 这是本场景最重要的安全设计。

---

## 六、提交前自检清单

生成数据后、划分前逐项确认：

- [ ] `python3 skills/kev-finetune/scripts/split_data.py <file>.jsonl`（不带 `--out`，仅校验）输出 **0 problems**
- [ ] 每个问题的标签分布**无 `<5%` 告警**，且**无「从未作为正确答案出现」的选项**
- [ ] 无 `states with conflicting labels dropped`（若有，说明标注规则自相矛盾，回去改 `guidance`）
- [ ] `validate --init-from jaredpalmer/kev-0.8b` 与 `--init-from jaredpalmer/kev-4b` 的各分区 `over_limit` 均为 0
- [ ] 抽查 10 条：`state` 里没有任何字段泄露了答案（不含医生结论、不含 label 的同义改写）
- [ ] 抽查最小对：同一对记录**只差一个字段**且 label 确实翻转
- [ ] `target` 软标签样本的键落在合法键空间内
- [ ] 字段名与 spec 的 `state_example` **完全一致**（改过字段名就必须重训，不能沿用旧权重）

---

[← 返回主方案](./README.md) · [执行手册](./runbook.md) · [生成器说明](./generators/README.md)
