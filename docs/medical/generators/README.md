# 医疗记录生成器

[← 返回主方案](../README.md) · 导航：[数据格式](../data-format.md) · [执行手册](../runbook.md)

这些脚本**不用大模型判断，只用规则算标签**：采样结构化字段 → 套阈值表 / 规则引擎 → 写出带标签的 Kev 记录。
标注零漂移是这里唯一重要的事 —— 0.8B 的基座知识不足以判断医疗语义，监督信号必须事先算好。

标准库 only、无网络、`--seed` 决定性可复现，与 `skills/kev-finetune/scripts` 的约定一致。

| 文件 | 场景 | 尺寸轨 | 说明 |
| --- | --- | --- | --- |
| `common.py` | 共用底座 | — | 记录构造与自检、配额采样、边界加权采样、最小对、阈值表复核 |
| `gen_critical_value.py` | 危急值复核 | 双轨主力 | 阈值表 + 通知时限 + 最小对 + 证据缺失软标签 |
| `gen_medication_review.py` | 用药/医保审核 | 双轨主力 | 说明书规则引擎（禁忌/超量/重复/特殊人群/适应症） |
| `gen_triage.py` | 导诊分诊 | 4B 主力 | 科室归属优先级 + 急症红旗；含刻意构造的多症状冲突样本 |
| `gen_nursing_quality.py` | 护理质量管控 | 双轨主力 | 质控检查表条目 + 严重度/可预防性派生 |
| `make_goldset.py` | 金标与审计 | — | 分层抽样待人工审校；比对两份独立标注并给出分歧率 |
| `run_matrix.py` | 双尺寸编排 | — | 一个场景一份数据两个模型；`--dry-run` 打印完整命令序列 |

`icd-coding`（病历编码）**没有生成器**，只有 spec：它需要真实 HIS/EMR 结构化摘要与临床知识，
程序化合成会产出 clinically meaningless 的记录。该场景走 `generate_data.py` 蒸馏 + 人工抽检。

## 用法

```bash
# 单场景生成（787 条是 4 问题的规划规模，见 ../data-format.md）
python3 docs/medical/generators/gen_critical_value.py --n 787 --out data/cv.jsonl --seed 0

# 校验（0 problems 才继续）
python3 skills/kev-finetune/scripts/split_data.py data/cv.jsonl

# 双尺寸全链路（生成 → 划分 → validate×2 → train×2 → compare → 双端点部署）
python3 docs/medical/generators/run_matrix.py --scenario critical-value --sizes 8b,4b --dry-run
```

## 三条设计约定

**1. 标签计划先于数据构造。** 每个生成器先按配额规划本批的标签（`plan_targets`），再构造能实现该标签的
字段。原因是 `split_data.py` 会对占比低于 5% 的标签、以及从未作为正确答案出现的选项告警 —— 先采样字段
再算标签，分布就由采样噪声决定，无法保证。

**2. 阈值表是权威判据，spec 的 `guidance` 必须与之一致。** 危急值阈值、用药规则、检查表条目都写在生成器里，
改阈值时**两处都要改**，否则合成数据与蒸馏数据的标签会悄悄分叉。危急值生成器采样后还会用 `notify_tier()`
复核，阈值改动不会静默产生错标。

**3. 稀缺标签需要显式配额。** 若某档位只有一两个项目能实现（如「当日内」只有 WBC 与 D-Dimer），
均匀分配会让它落到 5% 以下 —— `CATEGORY_TIER_SPLIT` 就是为此存在的显式数据。

## 新增一个场景：3 步

1. 在 `../specs/<name>.json` 写 spec（字段与 `skills/kev-finetune/assets/workload.example.json` 完全一致）。
2. 在本目录建 `gen_<name>.py`：定义规则表 → 写 `decide()` 派生标签 → 写 `plan_targets()` 规划配额 →
   写 `build()` 组装记录（用 `common.labelled` 自检）。
3. 在 `run_matrix.py` 的 `FOUR_B_ONLY`（若该场景只支持 4B）登记，并跑
   `pytest tests/test_medical_generators.py`。

不需要改 `common.py`。

## 与 `generate_data.py`（蒸馏）的分工

| | 程序化生成器 | `generate_data.py` 蒸馏 |
| --- | --- | --- |
| 标签来源 | 规则表，零漂移 | LLM 判断，有漂移风险 |
| 适用 | 阈值/规则封闭的任务：危急值、用药、护理质控 | 语义丰富、规则难穷举：导诊、病历编码 |
| 软标签 `target` | ✔ 可产出 | ✘ 只会写 `label` |
| 成本 | 免费、离线、秒级 | 约 $0.25/1000 条（gpt-4.1-mini） |
| 表述多样性 | 低（字段模板化） | 高 |

**两者互补**：程序化保证标签正确，蒸馏补表述多样性。典型做法是先用生成器产出标签骨架，
再把其中的 state 文本交给 LLM 改写（保持标签不变）。

## 纯蒸馏的质量防线

用户当前没有带标签数据，开发集也是合成的 —— 这是闭环自证的风险点。三道防线：

1. `make_goldset.py sample` 分层抽 150–250 条人工审校，签字后用 `split_data.py --holdout` 接入
   （对半分进 calibration 与 development，永不进 train）。**终评只跑一次。**
2. `make_goldset.py audit` 比对两个厂商模型对同一批 state 的标注，按**单题**分歧率设门槛
   （不看总体 —— 3% 的平均可以藏住某一题 13% 的分歧）。
3. `errors.jsonl` 人工复盘：每一类反复错误都对应 spec `guidance` 里缺的一句话。

---

[← 返回主方案](../README.md) · [数据格式](../data-format.md) · [执行手册](../runbook.md)
