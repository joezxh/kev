<p align="center">
  <a href="./sft-distill_CN.md"><img alt="中文" src="https://img.shields.io/badge/%E4%B8%AD%E6%96%87-orange?style=for-the-badge"></a>
  <a href="./sft-distill.md"><img alt="English" src="https://img.shields.io/badge/English-blue?style=for-the-badge"></a>
</p>

# 从蚂蚁百灵蒸馏医疗数据：Kev 训练与医疗 SFT

[English](./sft-distill.md) · 实现目录：[`medical/distill/`](./medical/distill/README.md) ·
操作手册：[`medical/distill_CN.md`](./medical/distill_CN.md) · 上层设计：[`sft-medical_CN.md`](./sft-medical_CN.md)

用**蚂蚁百灵**（云端 Open API）作教师、**EasyDistill 2** 作流水线，产出两类医疗数据：**标签由规则派生的 Kev
决策记录**，以及供医疗助手模型微调的**生成式 SFT 样本**。五个场景、两条轨、每个场景共享同一份 state。

---

## 1. 状态：请先读这一节

| 类别 | 状态 |
| --- | --- |
| **已实现并在本地验证** | 流水线反转、两个新场景、种子双文件契约、转换器、量级检查器、五份 EasyDistill 配置、测试套件 |
| **已实现但未验证** | **从未调用过**百灵 API —— 无凭据、无额度。不存在任何 `messages` 输出。所有 token 数字都是估算，不是实测。 |
| **使用前需复核** | 百灵**未官方声明任何医疗能力**；base URL、定价、免费额度、并发上限**官网均未公布**；上层包的三张规则表仍需领域专家复核；一个上游生成器缺陷会阻塞 SFT 轨（§8） |

**本文不含任何性能结论。** 已验证的是机制，未验证的是教师与算术。

---

## 2. 流水线是故意反着走的

需求是「从百灵蒸馏出 Kev 训练数据」。但上层包**已经能以零 LLM token、零标签漂移**地生成 Kev 记录 ——
六个生成器，各 787 条，全部通过校验。让 LLM 去产这些标签反而会**引入**漂移，与上层包「阈值表是权威判据」
的原则冲突。

所以教师只做它擅长的事：

```
 规则引擎采样 state + 计算标签        零 token、零漂移
          |
          +--> <scenario>.state.jsonl ------> seed_to_kev.py --> Kev 决策记录
          |      旁路 sidecar：标签的唯一来源                      |
          |                                                              +--> 训练 Kev-0.8B / 4B
          +--> state 渲染成 instruction
                 |
                 +--> <scenario>.seed.jsonl --> EasyDistill --> 百灵撰写参考答案
                    |                          -> judge -> filter -> build_sft
                    |                                     |
                    |                     它只能看到 instruction
                    |                                     |
                    +--------------------------> 生成式 SFT 样本 --> 微调医疗助手
```

三条需要明说的推论：

- **标签在结构上就够不到 LLM。** `seed_to_kev.py` 只读 `state.jsonl`，从不打开 SFT 文件。已验证：注入 100%
  蓄意错误的教师答案后，Kev 输出**逐字节相同**（SHA-256 一致）。
- **两轨共享同一份 state**，不存在第二份会漂移的数据。
- **Kev 轨花费 0 LLM token。** 按每条约 2,500 token 计，天真设计下本层 3,148 条 Kev 记录（4 场景 × 787）
  要花约 8M token，这笔钱一分未花。

### 2.1 教师能与不能做的事

| 百灵做 | 百灵不做 |
| --- | --- |
| 写多样的临床叙述 | 判定任何阈值（危急值、剂量、禁忌） |
| 产出参考答案 | 提供任何会成为 Kev `label` 的值 |
| 在裁判阶段打分 | 为医学正确性背书 |

最后一行正是 §11 把人工审校列为强制环节的原因。百灵官网**没有**任何医疗能力声明，
其医学知识是一个未被背书的变量，**能补上这个缺口的是领域专家，不是更好的提示词**。

---

## 3. 教师接入：已核实与未核实

### 3.1 已核实

| 项 | 值 |
| --- | --- |
| 模型族 | 蚂蚁百灵：Ling（语言）、Ring（推理）、Ming（全模态） |
| API | **OpenAI 兼容**；平台为 Ling Studio |
| 开发者文档 | `https://developer.ant-ling.com/zh-CN/docs`（模型页 `.../docs/models/`） |
| 模型迭代 | Ling-1T / Ring-1T（2025-09/10）→ Ling-2.5-1T（2026-02）→ Ling-2.6-1T（2026-04）→ **Ling-3.0-flash**（2026-07，已开源至 `inclusionAI/Ling-3.0-flash`） |
| 官方定位 | 蚂蚁集团把医疗健康列为重点布局方向之一 |

### 3.2 未核实 —— 花钱之前必须先解决

| 项 | 状态 |
| --- | --- |
| **base URL** | 官网首页未公布。2026-02 第三方博客给出 `https://api.tbox.cn/api/llm/v1`，但官方文档在另一个域名下，**两者未交叉验证**。 |
| **模型 id** | 模型族每 1–2 个月换代。实现时从模型文档页锁定，**不要硬编码**。 |
| **定价** | 官网只说「限时折扣」，未公布每百万 token 价格。 |
| **免费额度 / 并发** | 第三方称约 50 万 tokens/日、并发 1、3 次/分。**未经确认**，下文只用于量级估算。 |
| **医疗能力** | **无任何声明**。 |

正因 base URL 未确认，`medical/distill/configs/*.yaml` 用 `${KEV_GEN_BASE_URL}` 引用，而不是把可能错误的值写死。

### 3.3 云端路径失败时的备选

`Ling-3.0-flash` 已开源。自建 vLLM 并把 EasyDistill 的 `openai` 后端指向 `localhost`，可同时消除额度上限并让
PHI 留在内网。它不是本次选定的路径，但是对冲手段 —— 也是**不经过采购对话就能扩过 Tier A 的唯一选项**。

---

## 4. EasyDistill 2 接入

EasyDistill 2 是 [ModelScope](https://github.com/modelscope/easydistill) 的 Apache-2.0 工具包，用于把黑盒教师
转成训练数据。已核实且相关的：

- **后端无关**：`type: openai` 接受任意 OpenAI 兼容端点，百灵就走这个
- **算子可组合**：生成、评估、过滤、改写、平衡、偏好评分
- **每个流水线阶段都是独立 `job_type`**，可从中间 JSONL 断点续跑
- 导出格式直接对接 **LLaMA-Factory** 与 **ms-swift**
- EasyDistill 2 是重写版，**与 1.0 不向后兼容**

所用流水线为 `advanced_instruct_distill`：expand → generate → judge → filter → build_sft。

`instruction_key: instruction` 与种子文件对齐。每份配置都设 `resume: true`，使中断重跑不重复消耗额度。
凭据走环境变量 —— **绝不写入 YAML**。

---

## 5. 数据来源与预处理

### 5.1 种子双文件契约

| 文件 | 字段 | 谁读 |
| --- | --- | --- |
| `<scenario>.seed.jsonl` | `id` / `instruction` / `system` | EasyDistill |
| `<scenario>.state.jsonl` | `id` / `scenario` / `state` / `labels` / `soft` | `seed_to_kev.py` |

**为什么分两个文件。** EasyDistill 文档说明 `id` 是行标识符、`instruction_balance` 会「保留原始字段并新增
`category`」，但**并不保证每个阶段都透传全部未知字段**。把 `state` 与 `labels` 放在流水线触及不到的旁路文件里，
join 就永远不依赖它的字段透传行为。`id` 是唯一 join 键，两文件同序写出。

`instruction` 是结构化 state 渲染成的 `key: value` 行 —— 与 Kev 自身渲染的表面一致 —— 并且
**只陈述事实，绝不透露标签线索**。

### 5.2 预处理链

| 步骤 | 规则 |
| --- | --- |
| **先脱敏** | 姓名、证件号、电话、住院号在**进入任何生成器之前**哈希或替换。生成器与 EasyDistill 只接触已脱敏字段。 |
| **规则引擎采样** | state 与标签由上层包的生成器一并采样，标签天然为真。 |
| **日期字段预计算** | 任何需要日期算术的值（用药天数、孕周）在生成阶段算好并以数字形式携带。这在数据层面规避了 0.8B 的日期算术弱项（0.35）。 |
| **仓库不含 PHI** | spec 与生成器只含 schema 与规则表。`data/` 已 git-ignored（用 `git check-ignore` 验证过）。 |

### 5.3 四来源在蒸馏语境下的重新排序

| 来源 | 角色 | 说明 |
| --- | --- | --- |
| 规则引擎（上层包） | **唯一的标签来源** | 零 token、零漂移 |
| LLM 教师 | 叙述多样性、参考答案、裁判打分 | 唯一的 token 开销 |
| 已有真实数据 | 终评金标集 | 目前没有；接口是 `convert_data.py` |
| 人工撰写 | 风格锚点、分歧样本池 | `generate_data.py --dry-run` 打印提示词 |

---

## 6. 蒸馏策略与流程

```bash
# 1. 种子（零 token）
python3 kev/console/distill/make_seeds.py --all --n 500 --out-dir data/seeds

# 2. SFT 轨（唯一花 token 的一步）
$env:KEV_GEN_API_KEY = "..."; $env:KEV_GEN_BASE_URL = "https://<官方 base URL>/v1"
easydistill --config kev/console/distill/configs/inquiry.yaml

# 3. Kev 轨（零 token；标签不经 LLM）
python3 kev/console/distill/seed_to_kev.py --scenario inquiry \
  --seed-file data/seeds/inquiry.seed.jsonl --state-file data/seeds/inquiry.state.jsonl \
  --out data/inquiry.jsonl

# 4. 教师与规则对账（只报告）
python3 kev/console/distill/seed_to_kev.py --scenario inquiry --from-sft data/sft/inquiry/inquiry.sft.jsonl \
  --report data/inquiry.reconcile.json

# 5. 量级与预算闸门
python3 kev/console/distill/check_volume.py --scenario inquiry --records data/inquiry.jsonl \
  --from-sft data/sft/inquiry/inquiry.sft.jsonl --budget 8000000
```

**按场景串行跑，不要并发跑多个场景。** 云端并发上限低，并发只会换来 429，而 `resume: true` 让串行分批很便宜。

**`--from-sft` 是诊断手段，不是数据通路。** 它把教师回答与规则标签做一致性比对并报告一致率。
一致率低会把记录标记为待人工审校，但**不会改动任何一个标签**。这是结构性的：`build_records()` 遍历
**种子**文件，只从旁路文件读标签。

### 6.1 逐阶段流程

| 阶段 | 发生什么 | 失败处置 |
| --- | --- | --- |
| 种子 | 规则引擎采样 state + 标签；state 渲染成 instruction | 换 `--seed` 重试；某场景返回 `None` 时回退成无引导记录 |
| Expand | EasyDistill 把每条种子扩展成多种表述 | 下调 `num_per_seed`；这是最便宜的阶段，先调它而不是动生成 |
| Generate | 百灵撰写参考答案 | 429 → 退避；`resume: true` 从最后完成的阶段续跑 |
| Judge | LLM 打分 correctness / helpfulness / informativeness / generalization | 阈值过严会**静默清空**数据集 —— 每次都在这一阶段后查行数，而不是等到最后 |
| Filter | 丢弃不达阈值的行 | 对比前后行数；掉超过 50% 说明裁判与 spec 不一致，而不是数据不好 |
| build_sft | 输出 `messages` + `metadata` | — |

**裁判阶段是静默失败点。** 它要读入 response，因此成本大约翻倍；阈值配错会在不报任何错的情况下清空流水线。
每次都要在 `filter` 之后核对行数。

---

## 7. 场景覆盖

| 场景 | Kev 轨 | SFT 轨 | 共享 state |
| --- | --- | --- | --- |
| **问诊 / inquiry** | 复用 `triage` | 医生式问诊对话 | `chief_complaint`、`age`/`sex`、`symptoms`、`duration`、`history`、`vitals` |
| **用药指导 / medication** | 复用 `medication-review` | 适应证、剂量、相互作用、禁忌 | `drug`、`dose`、`route`、`days_on_drug`、`age`、`renal`、`allergies` |
| **诊断建议 / diagnosis** | **新建** `diagnosis` spec | 鉴别诊断、依据、建议检查 | `presenting`、`vitals`、`lab_results`、`imaging`、`comorbidities` |
| **病历摘要 / record-summary** | **新建** `record-summary` spec | 六要素结构化摘要 | `record_text`、`diagnosis`、`medications`、`plan` |
| **医学知识问答 / knowledge-qa** | **无 —— 见下** | 开放式医学问答 | `topic`、`question` |

### 7.1 知识问答为什么没有 Kev 轨

Kev 是指针读出模型：它在**预声明的选项集**上打分，**一个 token 都不生成**。开放式医学问题没有这样的选项集。
强行做成 Kev 任务只能退化成 4 选 1 判断题，把问答轨的价值全部丢掉。所以它是单轨场景，
`check_volume.py` 如实报告这一点而不是报错。

### 7.2 复用把新增面压到最小

五个场景中有两个与上层包已交付的场景**临床同构**，spec 与生成器原样复用：`inquiry` → `triage`、
`medication` → `medication-review`。只有 `diagnosis` 与 `record-summary` 是新增的。
净新增：2 个 spec、2 个生成器、3 个蒸馏脚本、5 份配置。

### 7.3 选项数受 5% 下限约束

`choice` 问题有 `N` 个选项时，每个选项都要至少 5% 概率成为正确答案，这会强制一个至少 `5N%` 的正例率。
`diagnosis` 用 9 个方向（≥45%，轻易满足），`record-summary` 用 7 个（≥35%）。这正是上层包把
`critical_item` 从 10 个选项降到 6 个的算术原因 —— 10 个选项会要求 50% 的危急率，临床上荒谬。

---

## 8. 数据量：预估与保障机制

### 8.1 假设（估算，非实测）

| 假设 | 值 | 依据 |
| --- | --- | --- |
| 每条 SFT 记录 token | ~1,000 | prompt ~250 + completion ~750；中文医疗回答偏长，推理型更长 |
| 裁判开销 | ≈ 生成 ×2.5 | 裁判要读入 response，成本大约翻倍 |
| 免费额度（未确认） | 50 万 tokens/日 | 第三方，2026-02 |
| 请求速率（未确认） | 3 次/分 = 4,320/日 | 第三方 |
| 每条记录调用次数 | ~3 | expand、generate、judge |

### 8.2 算术

| 档位 | 每场景 | 5 场景 | 生成 | 含裁判 | 免费额度下天数 | 请求速率下天数 |
| --- | --- | --- | --- | --- | --- | --- |
| **A 冒烟** | 500 | 2,500 | ~2.5M | **~6.3M** | **~13 天** | ~1.7 天 |
| **B 推荐** | 2,000 | 10,000 | ~10M | **~25M** | **~50 天** | ~6.9 天 |
| **C 全量** | 5,000 | 25,000 | ~25M | **~63M** | **~125 天** | ~17.4 天 |

**token 额度才是紧约束**，不是请求速率 —— Tier B 在额度上比在速率上慢约 7 倍。两个瓶颈必须分开陈述，
否则估算毫无意义。

### 8.3 免费额度只够 Tier A

这是全文最重要的一个数字。Tier B 要么采购付费额度，要么走 §3.3 的自建备选。

**所以 Tier A 被设计成「可计量试点」，而不是用完即弃的冒烟测试。** 跑完后
`metadata.usage.total_tokens` 给出**真实的**每条成本。用那个实测值（而不是本文的估算）重算 Tier B/C 预算，
再去谈付费额度。§8.2 每一行都只需换一个数字即可重算。

### 8.4 量级保障

`check_volume.py` 会提前失败，而不是让稀薄的数据流到训练器：

| 断言 | 阈值 |
| --- | --- |
| 每场景记录数 | `--expect`（默认 787） |
| 每个标签占比 | ≥ 5%（`split_data.py` 自身的下限） |
| 每个选项至少出现过一次作为正确答案 | 否则模型学不到它 |
| 每场景问题数 | ≥ 100，保证温度拟合稳定 |
| token 总量 | 给了 `--budget` 时比对 |
| 教师/规则一致率 | 按问题报告；一致率低则送人工审校 |

Kev 轨被显式断言为 **0 LLM token**，以免日后把两轨的成本混为一谈。

---

## 9. Kev 训练数据格式与要求

每行一个 JSON 对象，System One 请求形状加上每个问题的 `label`：

```json
{"state": {"patient": "male 34", "chief_complaint": "……", "vitals": "……"},
 "questions": {
   "department": {"type": "choice", "instructions": "……", "criteria": {"cardiology": "……"}, "label": "cardiology"},
   "immediate_human": {"type": "noul", "instructions": "……", "label": false},
   "acuity": {"type": "score", "instructions": "……", "criteria": ["…", "…", "…"], "label": 0}}}
```

| 要求 | 值 |
| --- | --- |
| State tokens | **≤ 384** —— 超出会被**训练器静默丢弃** |
| 打包请求 | ≤ 2048 |
| 每题分支 | ≤ 1024 |
| `choice` 标签 | 必须是 `criteria` 的键之一 |
| `noul` 标签 | 必须是 JSON 布尔值 |
| `score` 标签 | `0 .. len(criteria)-1` 的整数 |
| `target`（可选） | 合法键上的非负权重，总和 > 0 |
| 标签下限 | 每个选项 ≥ 5% |

训练前校验：

```bash
python3 skills/kev-finetune/scripts/split_data.py data/inquiry.jsonl
modal run skills/kev-finetune/scripts/kev_modal.py::validate --data data/inquiry --init-from jaredpalmer/kev-0.8b
```

`validate` **每个尺寸各跑一次** —— 各自 tokenizer 不同，而 `split_data.py` 里的
`STATE_CHARS_WARN = 1400` 在源码注释中写的是「~384 tokens of **English**」，对中文偏松。

**均衡先验的坑在这里同样存在。** 均衡的危急值数据集危急率 ≥30%，而真实报告是 1–3%。模型概率条件在均衡先验上，
上线前必须用真实流量重新推导工作阈值。

---

## 10. 医疗微调数据格式与要求

EasyDistill 的标准 SFT 输出，LLaMA-Factory 与 ms-swift 可直接消费：

```json
{
  "messages": [
    {"role": "system", "content": "你是一位临床分诊助手……"},
    {"role": "user", "content": "以下是一位患者到院分诊台的情况……"},
    {"role": "assistant", "content": "……"}
  ],
  "metadata": {
    "source": "teacher_model", "model": "…", "request_id": "…", "backend": "openai",
    "usage": {"completion_tokens": 750, "prompt_tokens": 250, "total_tokens": 1000}
  }
}
```

| 字段 | 要求 |
| --- | --- |
| `messages` | OpenAI/ShareGPT 风格。**恰好一个** `assistant` 轮 —— 那就是训练目标 |
| `messages[].content` | 本方案**不用**多轮对话；每条种子是单轮的 |
| `metadata.model` | **记录教师版本。** 这是唯一能一路留到训练后模型的溯源信息 |
| `metadata.usage.total_tokens` | 真实成本数据的唯一来源，驱动 §8.3 的预算重算 |
| `system` | 每行的系统提示；种子已带场景专属的一份 |

**系统提示是安全相关的，不是装饰。** 每份都编码了一条拒绝边界 —— 不给确定性诊断、不超出处方集调整剂量、
不编造文献出处 —— 外加一条「出现以下情况请立即就医」的指引。放松它，模型就会学会对那些教师自己都被要求
留有余地的问题给出笃定回答。

---

## 11. 质量评估方法

四层，每层抓上一层抓不到的问题。

### 11.1 结构层

`split_data.py` —— 0 invalid lines、0 标签冲突、无 state 超 token 上限。全自动。

### 11.2 分布层

`check_volume.py` —— 记录数、5% 标签下限、选项覆盖、≥100 问题下限。全自动。

### 11.3 教师/规则一致层

`seed_to_kev.py --from-sft` —— 教师独立给出答案，报告按问题的一致率并列出分歧。这是人工审校之前
能拿到的**最强的低成本信号**：一致率低意味着**教师与规则引擎看到的决策边界不同**，而这正是产出「自信但错误」
模型的典型失效模式。与上层包的 `make_goldset.py audit` 配合使用 —— 后者比较两个厂商对同一批 state 的标注，
并以**最差的那一题**为门槛而非平均值。

### 11.4 人工层 —— 强制

| 项 | 负责人 | 是否阻塞 |
| --- | --- | --- |
| 金标集 150–250 条审定 | 临床 / 药学 | 是 —— 唯一真实的度量 |
| 危急值阈值表 | 检验科 | 是 |
| 药品规则表 | 药学部 | 是 |
| 护理质控检查表条目 | 护理部 | 是 |
| §11.3 的分歧记录 | 临床 | 是 |

⚠️ **百灵没有任何官方医疗背书。** 它是一个通用模型的知识，所以专家复核是唯一真实的质量闸门。
跳过这一步产出的数据是内部自洽、外部未验证的 —— 这是最难在事后发现的一类坏数据。

### 11.5 医疗专属红线

- 不编造文献或指南出处
- 不给确定性诊断，只给鉴别方向与不确定性
- 用药建议不超出处方集范围
- 依赖日期的事实以预计算字段给出，绝不让模型自己做算术
- 每条临床回答都带「何时需要紧急就医」的升级路径

---

## 12. 合规与隐私

你选了云端 API，因此结构化字段**会离开内网**。以下几项是阻塞项，不是建议项。

| 项 | 要求 |
| --- | --- |
| 脱敏 | 在**任何生成器运行之前**完成。生成器与 EasyDistill 只接触已脱敏字段。 |
| 数据出域评估 | 确认已脱敏的结构化字段可发送至外部 API；必要时签署数据处理协议 |
| 凭据 | 只走环境变量；`medical/distill/configs/*.yaml` 引用 `${KEV_GEN_API_KEY}`，不含任何密钥（由配置测试断言） |
| 模型发布 | `publish` 默认私有；医疗模型**绝不**传 `--public` |
| 溯源 | `metadata.model` 记录每条样本由哪个教师产出 |
| 仓库卫生 | `data/` 已 git-ignored（用 `git check-ignore` 验证）；spec 与生成器只含 schema 与规则表 |

**备选路径在这里很重要。** 若出域评估不通过，自建 `Ling-3.0-flash`（§3.3）能同时解决合规与额度两个问题。

---

## 13. 阻塞 SFT 轨的上游缺陷

`medical/generators/gen_triage.py` 把「儿童咳嗽」「小儿呕吐」「儿童发热」「高热惊厥」等**儿科关键词作为独立
词条**列在 `SYMPTOMS` 里，而年龄采样横跨 2–78 岁，于是产出临床上不连贯的记录：
**实测 500 条 inquiry 种子中有 34 条（6.8%）**存在，最差一例是 `female 78 | 小儿呕吐 | dept: pediatrics`。

| 轨 | 影响 |
| --- | --- |
| **Kev** | 标签仍自洽（规则仍按表索引决定），模型会学到字面捷径。是现实性问题，不是正确性问题。 |
| **SFT** | 教师被要求对「78 岁 + 小儿呕吐」做推理，会产出困惑的参考答案。**蒸馏前必须修掉。** |

修法是给该词表加年龄护栏（儿科词条仅在 `age < 14` 时可被采样）。这属于 `gen_triage.py` 的**逻辑变更**，
需单独授权；本层不擅自动手。

---

## 14. 已验证 / 未验证

| 已本地验证 | 方式 |
| --- | --- |
| 六个生成器各产 787 条 | `gen_* --n 787 --seed 0` |
| skill 校验器接受 | `split_data.py`：0 invalid、0 conflicting |
| 标签下限达标 | 无 `under 5%`、无 `never labelled` 告警 |
| 定容算术 | `plan_size.py`：每个 spec 均输出 `generate at least 787 records` |
| 种子：5 场景 × 500 | `make_seeds.py --all --n 500` |
| 转换器从旁路重建记录 | 500 条、0 invalid、0 conflicts、0 重复 state |
| **敌意教师下的标签不变性** | 注入 100% 错误答案 → Kev 输出**逐字节相同**（SHA-256 一致）；一致率正确降到 0.5% |
| 量级闸门会响亮失败 | 预算超限与记录数不符均 exit 1 |
| 五份配置是合法 YAML | `yaml.safe_load` + 对 job_type、backend、环境变量凭据、阶段顺序、`resume: true` 的断言 |
| `data/` 已被 git 忽略 | `git check-ignore` exit 0 |

| **未**验证 | 原因 |
| --- | --- |
| 任何一次百灵 API 调用 | 无凭据、无额度。教师从未被调用过。 |
| 任何真实 `messages` 输出 | 同上 |
| 所有 token 数字 | 均为基于上述假设的估算；只有 Tier A 能产出真实数字 |
| base URL、定价、额度、并发 | 百灵未公布；第三方数字未确认 |
| 教师答案的医学质量 | 需要 §11.4 的人工环节，尚未进行 |
| 裁判阈值是否设得合适 | 只有真实跑过之后才能观察 |

---

## 15. 上线前 checklist

- [ ] 从 `developer.ant-ling.com/zh-CN/docs` 确认百灵 base URL 与模型 id
- [ ] 取得定价；**先跑 Tier A**，用其实测的 `usage.total_tokens` 重算预算
- [ ] 完成数据出域评估，或改走自建备选路径
- [ ] 授权并修复 `gen_triage.py` 的儿科词表缺陷（§13）
- [ ] 让检验科、药学部、护理部复核各自规则表
- [ ] 生成种子，并审定 150–250 条金标集
- [ ] 跑 Tier A；在 `filter` 后核对行数；读按问题的教师/规则一致率
- [ ] 依据 Tier A 的实测成本（而非本文估算）决定是否上 Tier B
- [ ] 确认任何 YAML 里都没有凭据，且 `data/` 保持被忽略
- [ ] 确认医疗模型绝不带 `--public` 发布

---

## 16. 文件清单

| 路径 | 角色 |
| --- | --- |
| `docs/sft-distill.md` | 英文主文档 |
| `docs/sft-distill_CN.md` | 本文件：中文完整译本，章节一一对应 |
| `kev/console/distill.md` / `_CN.md` | 命令速查与排错 |
| `kev/console/distill/README.md` | 蒸馏层总览、种子契约、新增场景步骤 |
| `kev/console/distill/make_seeds.py` | 种子生成器，写出双文件 |
| `kev/console/distill/seed_to_kev.py` | 转换器；`--from-sft` 对账 |
| `kev/console/distill/check_volume.py` | 分布与预算闸门 |
| `kev/console/distill/configs/*.yaml` | 五份 EasyDistill 配置 |
| `kev/console/distill/seeds/README.md` | 种子目录说明 |
| `docs/medical/specs/diagnosis.json` | 新增：诊断建议 spec |
| `docs/medical/specs/record-summary.json` | 新增：病历摘要 spec |
| `kev/console/generators/gen_diagnosis.py` | 新增：诊断建议生成器 |
| `kev/console/generators/gen_record_summary.py` | 新增：病历摘要生成器 |
| `tests/test_medical_distill.py` | 种子、转换器、不变性、量级与配置测试 |
| `.gitignore` | 新增 `data/`、`medical-data/` |

`skills/kev-finetune/` 与 `kev/` 库**未被改动**。

---

[English](./sft-distill.md) · 实现目录：[`medical/distill/`](./medical/distill/README.md) ·
上层设计：[`sft-medical_CN.md`](./sft-medical_CN.md)

