# 跨领域场景 specs（医疗 / 金融 / 教育 / 科研 / 法律）

本目录是全部领域场景 spec 的统一存放点，按领域分目录，遵循同一套 spec schema 与
两轨制（规则生成轨 / 蒸馏轨），复用 `kev/console/generators/engine.py` 引擎与
`kev/console/distill` 蒸馏流程。schema 设计原则见 `docs/learn/kev-fundamentals.md`：
record（state + questions + 标签）是唯一数据原语，noul/choice/score 三种题型统一指针读出，
温度校准纪律与冻结套件四分区（train/calibration/development/test）不变。

## 〇、目录结构

```
docs/domains/
├── README.md                  ← 本文件：全景清单 + schema + 接入说明
├── medical/specs/             ← 15 个（自 docs/medical/specs 迁入，2026-10-16）
├── finance/specs/
├── education/specs/
├── science/specs/
└── law/specs/
```

`paths.SPECS`（`kev/console/paths.py`）指向 `docs/domains/medical/specs`，控制台种子、
冒烟探针与引擎回退路径不变；其他领域通过 `KEV_ENGINE_SPEC_DIR` 或 DB `spec_path` 接入，
并且五域 61 场景已全部登记进控制台库（见第一节末）。

## 一、场景全景清单

标记：✅ 已配置（spec 已就绪，规则轨已过引擎冒烟）；⏳ 待配置（全景规划，spec 未写）。

### 医疗（medical，15 ✅）

| 场景 | 轨制 | 状态 |
|---|---|---|
| critical-value 危急值复核 | 规则生成 | ✅ |
| triage 分诊 | 规则生成 + 蒸馏 | ✅ |
| diagnosis 初诊鉴别 | 规则生成 + 蒸馏 | ✅ |
| medication-review 用药审查 | 规则生成 + 蒸馏 | ✅ |
| medication 用药指导/医保 | 蒸馏 | ✅ |
| icd-coding ICD 编码 | 蒸馏（直连 LLM） | ✅ |
| nursing-quality 护理质量 | 规则生成 | ✅ |
| record-summary 病历摘要 | 规则生成 + 蒸馏 | ✅ |
| inquiry 问诊追问 | 蒸馏 | ✅ |
| knowledge-qa 知识问答 | 蒸馏 | ✅ |
| follow-up-tier 出院随访分级 | 规则生成 | ✅ |
| infection-report 感染上报分诊 | 规则生成 | ✅ |
| transfusion-review 输血审核 | 规则生成 | ✅ |
| surgical-checklist 手术安全核查 | 蒸馏 | ✅ |
| mdr-report 器械不良事件上报 | 蒸馏 | ✅ |

### 金融（finance，12 ✅）

| 场景 | 轨制 | 状态 |
|---|---|---|
| fin-aml-alert 反洗钱预警复核 | 规则生成 | ✅ |
| fin-credit-doc-review 信贷资料完整性 | 规则生成 | ✅ |
| fin-complaint-triage 投诉分诊 | 蒸馏 | ✅ |
| fin-transaction-anomaly 异常交易识别 | 规则生成 | ✅ |
| fin-kyc-review 客户尽调资料复核 | 规则生成 | ✅ |
| fin-customer-intent 客户意图/情绪分类 | 蒸馏 | ✅ |
| fin-compliance-review 营销文本合规审查 | 蒸馏 | ✅ |
| fin-dispute-classification 交易争议分类 | 蒸馏 | ✅ |
| fin-fraud-claim-review 欺诈理赔复核 | 规则生成 | ✅ |
| fin-underwrite-triage 核保分诊 | 规则生成 | ✅ |
| fin-collection-tier 催收分级 | 规则生成 | ✅ |
| fin-credit-score-explain 征信异议分类 | 蒸馏 | ✅ |

### 教育（education，11 ✅）

| 场景 | 轨制 | 状态 |
|---|---|---|
| edu-early-warning 学业预警 | 规则生成 | ✅ |
| edu-essay-scoring 作文分维评分 | 蒸馏 | ✅ |
| edu-error-diagnosis 错因诊断 | 蒸馏 | ✅ |
| edu-question-classify 试题分类定级 | 规则生成 | ✅ |
| edu-cheating-risk 考试行为异常识别 | 规则生成 | ✅ |
| edu-knowledge-tagging 知识点标注 | 蒸馏 | ✅ |
| edu-material-adapt 教材适配分级 | 蒸馏 | ✅ |
| edu-answer-grading 简答题评分 | 蒸馏 | ✅ |
| edu-lesson-review 教案审查 | 蒸馏 | ✅ |
| edu-iep-review 个别化教育计划复核 | 蒸馏 | ✅ |
| edu-admission-screen 招生材料预检 | 规则生成 | ✅ |

### 科研（science，12 ✅）

| 场景 | 轨制 | 状态 |
|---|---|---|
| sci-reproducibility 可复现性预检 | 规则生成 | ✅ |
| sci-review-triage 审稿意见分诊 | 蒸馏 | ✅ |
| sci-data-quality 实验记录质量 | 蒸馏 | ✅ |
| sci-literature-classify 文献收录预检 | 蒸馏 | ✅ |
| sci-experiment-normalize 实验记录规范化 | 规则生成 | ✅ |
| sci-topic-identification 研究主题识别 | 规则生成 | ✅ |
| sci-data-sharing-review 数据共享合规审查 | 蒸馏 | ✅ |
| sci-grant-triage 基金申请预审分诊 | 蒸馏 | ✅ |
| sci-ethics-review 伦理审查预检 | 蒸馏 | ✅ |
| sci-figure-check 图表规范性检查 | 蒸馏 | ✅ |
| sci-metadata-fair FAIR 元数据评分 | 规则生成 | ✅ |
| sci-software-archive 软件存档合规 | 规则生成 | ✅ |

### 法律（law，11 ✅）

| 场景 | 轨制 | 状态 |
|---|---|---|
| law-contract-clause 合同条款识别 | 蒸馏 | ✅ |
| law-evidence-chain 证据链完整性 | 规则生成 | ✅ |
| law-dispute-focus 争议焦点分诊 | 蒸馏 | ✅ |
| law-contract-risk 风险条款分级 | 规则生成 | ✅ |
| law-compliance-obligation 合规义务分级 | 规则生成 | ✅ |
| law-cause-mapping 案由/法条映射 | 蒸馏 | ✅ |
| law-legal-doc-classify 法律文书分类 | 蒸馏 | ✅ |
| law-ip-infringement 侵权线索初筛 | 蒸馏 | ✅ |
| law-regulation-watch 监管新规影响分级 | 规则生成 | ✅ |
| law-privacy-dsr 个人信息请求分诊 | 蒸馏 | ✅ |
| law-adr-clause 争议解决条款审查 | 蒸馏 | ✅ |

全部场景已按本文件第二节的 schema 补齐（2026-10-16）：规则生成轨场景逐个通过引擎冒烟
（n=400、seed 7，四档全覆盖、0/少量重复状态按全 normal 组合有限接受），蒸馏轨场景的
`_meta.source_yaml` 均指向 `kev/console/distill/configs/` 下已存在的 EasyDistill 配置。

legacy 形态（两轨 schema 定型前的 7 个医疗 spec，无 `generator`/`distill` 块）的轨制按
`kev/console/generators/` 专用脚本与 `kev/console/distill/configs/` yaml 的实际存在性标注：
- **规则生成 + 蒸馏**（triage、diagnosis、medication-review、record-summary）：`gen_<场景>.py`
  专用脚本产出带标签 goldset（规则算标签，引擎定型前的代码形态管线），同时作为
  `make_seeds.py` 蒸馏场景的标签来源（inquiry→triage、medication→medication-review），
  EasyDistill yaml 已存在（diagnosis.yaml、record-summary.yaml、inquiry.yaml、medication.yaml）。
- **纯规则生成**（critical-value、nursing-quality）：有专用脚本、无蒸馏 yaml；critical-value
  是规则引擎的母本（`gen_critical_value.py` 的阈值表为权威判据）。
- **蒸馏（直连 LLM）**（icd-coding）：唯一没有生成器的医疗场景（程序化合成会产出无临床意义
  的记录），走 `skills/kev-finetune/scripts/generate_data.py --category icd_coding` 直连 LLM
  生成带标签记录 + `make_goldset.py` 人工抽检；此路线标签来自 LLM（有漂移风险，靠金标审计
  把关），与 EasyDistill「LLM 永不接触标签」的旁路重建不同，也没有 `_meta.source_yaml`。

### 登记进控制台库（schema v8）

五领域 61 场景已登记进控制台库的 `scenario_domains` / `scenarios` 两张表（schema v7 → v8）。
清单的单一真相源是 `kev/console/scenario_specs.py`：它只按文件存在性派生每个场景的轨制
（`generator` 九件套 / `gen_<slug>.py` / `distill/configs/<slug>.yaml` / `_meta.source_yaml`），
再与本文件第一节的「轨制」列交叉校验（`scenario_specs.audit()`，不一致就不入库）。

v8 给两张表补了五列：

| 表 | 列 | 语义 |
|---|---|---|
| `scenario_domains` | `spec_dir` | 该域由 `docs/domains/<spec_dir>/specs` 供数；空串 = 手工建域，种子不纳管 |
| `scenarios` | `track` | `rule` / `distill` / `both` / `llm`；空 = 未判定 |
| `scenarios` | `generator_kind` | 规则轨的形态：`engine`（generator 九件套）/ `script`（legacy `gen_<slug>.py`） |
| `scenarios` | `distill_yaml` | EasyDistill 配置路径（`kev/console/distill/configs/<slug>.yaml`），蒸馏轨与双轨场景非空 |
| `scenarios` | `origin` | `domains` = 导入脚本登记的行；空 = 库中原有行（标签与 spec 编辑归用户） |

```powershell
uv run python scripts/import_domain_specs.py              # 幂等导入，可反复跑
uv run python scripts/import_domain_specs.py --check      # 只读对账，绝不写库（退出码非 0 = 有 DIFF）
uv run python scripts/import_domain_specs.py --domain medical,law
uv run python scripts/import_domain_specs.py --force      # 以文件覆盖 spec_json，旧内容进 scenario_spec_history
```

- **域按 `spec_dir` 认领既有行**：旧库里手工建的 `research` 域会被 `science` 目录认领，既不插重复域，
  也不重命名用户起的 slug。
- **场景按 slug 全局唯一**：已存在的行只刷派生列（`track` / `generator_kind` / `distill_yaml` + 种子行的
  `spec_path`），不动用户改过的中英文标签、sort、category 与 `spec_json`；重跑不翻倍。
- **spec 内容落 `scenarios.spec_json`（真相源）**：`scripts/gen_console_schema.py` 生成的
  `deploy/console/schema.{sqlite,postgres}.sql` 只带 DDL 与域/场景清单，不再内联 spec 内容；
  `python -m kev.console initdb` 建库后由导入脚本（或 `Store()` 的种子）补齐 `spec_json`。

当前登记结果：5 领域 / 61 场景，轨制分布 `distill` 31 / `rule` 25 / `both` 4 / `llm` 1。

## 二、schema 草案（五个领域逐字段对齐）

```
{
  "name": "<领域前缀>-<场景 slug>",          // med 场景沿用原名（critical-value 等），其余 fin- / edu- / sci- / law-
  "label_zh" / "label_en",                  // （蒸馏轨）显示名
  "domain":  "业务背景 + 法规/标准基线 + 阈值口径声明",
  "state":   "结构化 state 的字段清单与单位约定（中文叙述夹数字）",
  "state_example": { ... },                 // 与 state 描述一致的真实样例
  "questions": {
    "<qid>": {
      "type": "noul" | "choice" | "score",
      "instructions": "...",
      "criteria": {...} | [...]             // choice 用键名字典，score 用 0 起有序档
    }
  },
  "guidance": "判定规则全文（阈值、优先级、软标签、豁免口径）",
  "variety": [ ... ],                       // 覆盖性清单：类别、档位、对照、易错陷阱
  "routing": { risk, human_review, evidence_question, note },
  "smoke_probe": { state, questions, expected_label },

  // ---- 规则生成轨独有 ----
  "generator": {
    "fields":     [ {name, unit, decimals, normal, critical{low/high}, category} ],
    "selectors":  [ {min, max} ],
    "tier_windows": { "0": {...}, "1": {...}, "2": {...} },
    "contexts":   [ ... ],
    "patients":   [ ... ],                  // 注意：键名固定为 patients（历史形状，见扩展点①）
    "rules":      [ {when, then:[{label, value}]} ],   // first-match wins
    "augmentation": { evidence_drop, minimal_pair },
    "plan_targets": { share:{critical}, by_category:{ critical:{quota, tier_split} } },
    "panel_category": { 字段名: 类别 }
  },

  // ---- 蒸馏轨独有 ----
  "_meta": { purpose, kev_track:false, source_yaml },
  "generator": { module:null, engine, notes },
  "distill": { system_prompt{zh,en}, ask_template(Jinja), topics, kev_track:false },

  // ---- 流程级扩展键（引擎不读，供流程与专家使用） ----
  "sampling": { n, notes },
  "few_shot": "...",
  "compliance": [ ... ],
  "acceptance": [ ... ],
  "troubleshooting": [ ... ],
  "expert_review": [ ... ]
}
```

规则生成轨的关键约定（引擎硬约束，违反即在冒烟时报错）：
- `fields` ≥ 6 个（sampler 需要触发字段之外至少 5 个补充字段做 `rng.sample`）。
- `tier_windows` 三档（"0" 最急 → "2" 缓办），每档窗口必须与对应字段 `critical` 区间**相交**，
  否则 `realize_tier` 返回 None、该档永远采不出样本；`min_tier` 按声明顺序 first-match。
- `rules.then` 必须覆盖 spec.questions 的**全部 qid**，否则 `labelled()` 抛 `no label for <qid>`。
- score 题 label 是 0 起整数，noul 是 bool，choice 是 criteria 键名字符串；choice 的 criteria
  键集合是 label 白名单。score 统一 4 档（0 立即/最高 → 3 无需处理），与医疗 notify_within 同构。
- state 值在规则求值前被格式化为 `"52.0 万元"` 字符串，`ops._parse_value` 按第一个空格解析。
- 蒸馏轨的 `generator` 必须显式写 `"module": null`。

## 三、关键规则、标签体系与评估指标设计说明

- **统一四问题模式**：每个场景的第 1 问是二元判定（是否触发）、第 2 问是 4 档处置时限
  （score）、第 3 问是触发类别（choice，与 fields.category 一一对应）、第 4 问是证据充分性
  （noul，evidence_drop 软标签的落点）。五个领域与医疗 critical-value 的三件套
  （is_critical/notify_within/critical_item/evidence_sufficient）同构，训练与评估管线零改动。
  蒸馏轨场景允许问题集不同（如 edu-essay-scoring 的分维评分），但 evidence 充分性问题保持。
- **代价不对称原则**：漏报代价高的场景（AML 漏报、学业漏警、漏转律师、漏上报诚信流程）
  验收约束 false negative 而放宽 false positive；重做/上报成本高的场景（科研重测、律师转介）
  反过来约束过报率。
- **贴边未触发对照**：每个规则轨场景的对照样本保留 15-20% 贴边未触发样本
  （如负债率 75-80%、期限 4-10 天），验收单列「贴边子集 true 比例 ≥0.9」。
- **软标签纪律**：evidence_sufficient=false 的记录强制 soft_target（{"true":0.5,"false":0.5}
  或按类别分布），对应 augmentation.evidence_drop（dropped 集合当前支持 unit/reference_range）。
- **验收指标族**：accuracy、ECE、Brier、per-question macro-F1、QWK（有序档位）、AURC/选择性
  覆盖 + isolation/permutation 检查（GATES 容差内）；文本分类蒸馏轨场景另加行为不变性检验
  （语气无关性、立场无关性、双视角一致率）。

## 四、检索来源摘要（2026-10 检索，用于阈值与类目设计，均为示例口径）

- **反洗钱**：《金融机构大额交易和可疑交易报告管理办法》（人民银行令〔2016〕3 号）——现金 ≥5 万、
  非自然人划转 ≥200 万、自然人境内 ≥50 万、跨境 ≥20 万；可疑交易不论金额。
- **个人金融信息**：JR/T 0171-2020（C3/C2/C1 分级）与《征信业务管理办法》（人民银行令〔2021〕
  4 号）——金融 specs 的脱敏与授权约束来源。
- **投诉处理**：《银行业保险业消费投诉处理管理办法》（银保监会令 2020 年 3 号）——15/30 日办结。
- **异常交易监测**：《金融机构反洗钱和反恐怖融资监督管理办法》（人民银行令〔2021〕3 号）的
  风险为本原则——fin-transaction-anomaly 的监测维度来源。
- **作文评分**：Kaggle ASAP / ASAP++ trait 评分传统——edu-essay-scoring 的分维与 QWK 来源。
- **错因类型学**：数学教育研究的 conceptual/procedural 两分——edu-error-diagnosis 六分类基础。
- **审稿意见**：PeerRead v1 与 DISAPERE 意见类型学——sci-review-triage 的分类框架来源。
- **可复现性/数据管理**：FAIR 原则与《科学数据管理办法》——sci-reproducibility、
  sci-data-quality、sci-data-sharing-review 的判据来源。
- **合同条款**：CUAD（510 份合同、41 类专家标注）——law-contract-clause 的类目来源。
- **举证与证据链**：chain of custody 与民诉/仲裁举证期限的一般原则——law-evidence-chain
  的核查表字段来源。

以上资料只用于**设计口径的起步值**，全部阈值与类目映射在各 spec 的 `expert_review` 键中
逐条标注「需专家复核」，不得直接作为生产标准。

## 五、如何接入当前流程（采集 → 蒸馏 → 生成 → split → precheck → train → eval → 验收）

**已经可直接工作的路径：**

```powershell
# 1. 规则生成轨：KEV_ENGINE_SPEC_DIR 指向对应领域目录
$env:KEV_ENGINE_SPEC_DIR = 'D:\projects\github\kev\docs\domains\finance\specs'
uv run python -m kev.console.generators.engine --scenario fin-aml-alert --out runs/domains/fin-aml-alert --n 2000 --seed 7

# 2. 蒸馏轨：spec 显式路径（resolve_spec 支持任意路径）
uv run python -m kev.console.distill.generate_data --spec docs/domains/finance/specs/fin-complaint-triage.json --n 500 ...
```

生成后的 goldset 抽样 → split（按 state 哈希，0.7/0.15/0.15）→ precheck（G1 token 闸门）→
`kev.train --data <jsonl>` → `kev.benchmark --data` → `kev.compare` 的链路与医疗 spec 完全一致，
无需任何代码改动：record 结构相同（state + questions + _meta），题型相同，预检与训练入口相同。
控制台库的种子已覆盖五领域（`seed_scenarios` 与 `scripts/import_domain_specs.py`，见第一节末）；
`paths.SPECS` 仍只指医疗目录，作为 DB 无行时的回退，旧医疗库的 `spec_path` 由
`scripts/backfill_medical_scenarios.py` 刷新。

**需要适配/扩展的 5 个点（当前按「文档化，不改引擎」处理）：**

1. **sampler 包装形状**：`BoundarySampler.make_record` 把指标硬编码包装为
   `{patient, context, labs, ref_ranges_included, missing_context}`。跨领域 specs 的语义是
   客户/学生/研究/案件 + 指标，落地时需要把 make_record 的键名参数化（约 5 行改动），或在
   下游读取层做键名映射。spec 内 `patients` 键已按现名填写，引擎当前可直接消费。
2. **evidence_drop 的 dropped 集合**：`Augmentor` 只支持 `unit`/`reference_range` 两种丢证
   目标。跨领域复用时建议把 dropped 集合也参数化（当前 specs 均沿用两种值，行为不变）。
3. **specs 自动发现范围（已完成）**：控制台库已登记五领域 61 场景（见第一节末「登记进控制台库」），
   域的 `spec_dir` 与场景的 `spec_path` / `spec_json` 不再局限于医疗，场景下拉可以直接选到其他领域。
   仍待适配的是离线矩阵：`run_matrix.py` 的 `SCENARIOS` 与 `SPECS` 常量仍指医疗名单与旧目录，
   跑其他领域的矩阵仍需显式传 spec 路径或设 `KEV_ENGINE_SPEC_DIR`。
4. **console generate 派发（未适配）**：控制台库登记后，generate 阶段能读到领域 spec 的行，但派发
   仍按 `gen_<module>.py` 拼命令（`stages/data.py::_generate`），只有 6 个 legacy 医疗场景可用；
   引擎侧的 `_load_spec` 也只认 `KEV_ENGINE_SPEC_DIR` / `paths.SPECS`（医疗目录）。规则轨的其他领域
   场景目前走命令行直接调 `kev.console.generators.engine`（见本节开头）。
5. **蒸馏 yaml 登记（已完成）**：蒸馏轨场景在 `kev/console/distill/configs/` 各有一份 EasyDistill 配置
   （把 spec 的 system_prompt 接到生成式 SFT 轨；spec 的 `_meta.source_yaml` 指向对应文件）。与医疗
   蒸馏轨的差异：跨领域场景无规则引擎（`generator.module = null`），种子 state 由
   `skills/kev-finetune/scripts/generate_data.py --spec <spec 路径>` 或控制台采集产出，Kev 决策记录
   由 `seed_to_kev.py` 从旁路 sidecar 重建，标签不来自 LLM。

## 六、需领域专家复核的事项（各 spec 的 `expert_review` 键为完整清单）

- **金融**：大额/可疑交易的金额档与监测维度权重（对照人行 3 号令需按机构业务调整）；KYC
  资料的豁免清单（分散申请、低风险客户简化尽调的边界）；异常交易分级的误报成本口径。
- **教育**：预警信号阈值与学业标准的对应（学校学籍管理规定的口径）；作文分档与评分细则的
  对齐；知识点标注体系的粒度（与教材版本/课标映射）。
- **科研**：可复现性分级与期刊政策的对应；数据共享合规的豁免边界（人类受试者、 dual-use）；
  基金预审的分档与资助机构口径。
- **法律**：风险条款分档与行业标准合同范本的对应；合规义务的处罚档位（各监管条线的罚则
  不同）；案由映射与《民事案件案由规定》版本的对应；所有法律解释口径需执业律师复核。
