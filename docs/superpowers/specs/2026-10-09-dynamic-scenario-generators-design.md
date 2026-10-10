# 动态场景生成器：把硬编码 `gen_*.py` / 蒸馏入口 / 路由 / 探针抽成可配置规则引擎

> **For agentic workers:** 配套的 SPEC，与 2026-10-09 的 studio 控制台设计同级。本设计描述**规则层**的全部动态化（生成器 + 蒸馏 + 路由 + 探针 + yaml 模板），不动 train/eval。
>
> **范围（v2，2026-10-09 第二次审稿扩展）**：v1 仅覆盖 5 个 `gen_*.py` + 4 个蒸馏字典；审稿时 `kev.vertical` / `kev.console.stages.deploy.SMOKE_PROBES` / `kev.console.distill.configs/*.yaml` / `kev.console.db::seed_scenarios.labels` 等四处硬编码一并纳入。spec_json 顶层加 4 个新字段：`generator` / `distill` / `routing` / `smoke_probe`。

## 0. 问题陈述

5 个医疗场景（critical-value / diagnosis / medication-review / nursing-quality / record-summary）的 `gen_*.py` 把**领域知识硬编码**进了 Python：

| 文件 | 硬编码内容 |
|---|---|
| `gen_critical_value.py` | `PANELS`/`IMMEDIATE`/`WITHIN_1H`/`CATEGORIES`/`TIER_WINDOWS`/`CATEGORY_TIER_SPLIT`/`decide`/`realize_tier` |
| `gen_diagnosis.py` | `FINDINGS`/`LAB_HINTS`/`PEDIATRIC`/`derive`/`_pick` |
| `gen_medication_review.py` | `DRUGS`/`SPECIAL_POPULATION`/`INDICATIONS`/`ISSUE_PRIORITY`/`evaluate`/`sample_plan` |
| `gen_nursing_quality.py` | `CHECKLIST`/`RISK`/`decide` |
| `gen_triage.py` | `SYMPTOMS`/`PEDIATRIC`/`decide` |

蒸馏层（`kev/console/distill/make_seeds.py`）把**场景路由、system prompt、ASK 模板**也硬编码进了 4 个 Python 字典（`SCENARIOS` / `SYSTEM_PROMPTS` / `ASK` / `SPEC_FOR`），且与 `run_matrix.SCENARIOS` / `gen_*` 三个模块手动保持同步。

编排层（`kev/console/generators/run_matrix.py`）硬编码 `SCENARIOS = sorted(p.stem for p in SPECS.glob("*.json"))` 与 `FOUR_B_ONLY = {"icd-coding"}`，**依赖 `docs/medical/specs/` 目录 glob**——`run_matrix` 因此与文件物理位置耦合，加场景要加文件、改名字要同步改 4 处。

部署探针（`kev/console/stages/deploy.py::SMOKE_PROBES`）硬编码 5 个医疗场景各 1 例冒烟样本，**没有 spec 化的探针**——加场景必须改 `stages/deploy.py` 再发版。

路由层（`kev/vertical.py::_medical` / `_finance` / `_legal` / `_education` / `_support`）硬编码 5 个行业 + 14 个场景的 `Scenario` 实例（`risk` / `human_review` / `evidence_question` / `note`）。**该模块已有 `IndustryRegistry.load(json)` 路径**（`vertical.py:343`），但默认走硬编码 fallback；DB 化后即用上。

蒸馏配置（`kev/console/distill/configs/*.yaml` × 5）是 EasyDistill 框架的输入文件——不能直接消除（框架不读 DB），但 `make_seeds` 可以**自动生成**它们（render Jinja2 模板），现硬编码 yaml 退化为参考模板。

DB 播种（`kev/console/db.py::seed_scenarios::labels`）硬编码 7 个医疗场景的中英 label 作为首次启动的默认值。
后果：

- **加一个场景要改 8+ 处**：写 `gen_*.py` + 登记 `run_matrix.SCENARIOS` + 改 `make_seeds.SCENARIOS` / `SYSTEM_PROMPTS` / `ASK` + 改 `seed_to_kev.SPEC_FOR` + 改 `check_volume.SPEC_FOR` + 改 `stages/deploy.SMOKE_PROBES` + 改 `vertical._medical`（若属医疗行业）+ 写 `configs/<slug>.yaml` + 改 `db.seed_scenarios.labels`。`icd-coding` 已有 spec 但没有生成器（卡在「先写 Python」这步上）。
- **spec 的 `guidance` / `variety` 字段是自由文本**，蒸馏 prompt 与生成器都靠人工读、靠人工转写。
- **5 个 `gen_*.py` 70% 是同一类代码**（sample → decide → label）：阈值表采样、规则仲裁、标签派生、plan_targets 配额、最小对生成。
- **`distill/README.md` 与 `gen_*.py` README 都把"加场景 3 步"写成手写步骤**——这是设计层面对硬编码的承认。

目标：把「**领域规则**」与「**生成机制**」拆开。规则以 JSON 进 DB 持久化（`scenarios.spec_json` 的同级字段 `generator` / `distill` / `routing` / `smoke_probe`），机制是**一个** Python 引擎 + 路由同步器读这份 JSON 跑出与原 `gen_*.py` byte-for-byte 相同的记录、把路由与探针动态化、把 yaml 自动生成。

## 1. 设计目标与非目标

### 目标

1. 加新场景的**唯一编辑点**是 `scenarios.spec_json` 的 4 个新字段：`generator`（规则配置）/ `distill`（蒸馏配置）/ `routing`（kev.vertical 路由参数）/ `smoke_probe`（部署探针）。
2. 同一 spec、同一 seed，**动态化后产物与原 `gen_*.py` 100% byte-for-byte 一致**（用 `critical-value` 第一个迁移做回归门）。
3. 5 个 `gen_*.py` CLI 全部删除，蒸馏入口的 4 个字典全部删除，service / Popen 路径直接调引擎。
4. Jinja2 模板 + 字段绑定替代 `ASK` 字典；用户可在 UI 改 system_prompt 与 ask 模板并保存到 DB。
5. 表达式求值用 `simpleeval`，白名单算子（`min/max/round/any/all/len` + 内置领域算子），无网络，标准库 plus 2 个新依赖。
6. 字段范围、规则、软标签、plan 配额都是**声明式 JSON**，UI 渲染成表单。

### 非目标

- 不改 train / eval / deploy 阶段（**deploy 阶段的 `SMOKE_PROBES` 要改**：见 §3.7，但 stage 与 service 的 argv 编排不动）
- 不改 `kev.console.db` 的场景表 schema（`generator` / `distill` / `routing` / `smoke_probe` 是 `spec_json` 内嵌字段，**不加列**）
- 不动 `evals/` 下的 frozen suite
- 不引入 LLM 协助生成规则（LLM 不接触标签的原则不变）
- 不动 `make_goldset.py` / `precheck.py`（这些脚本只读 `data/*.jsonl` 与 `docs/medical/specs/*.json`，不动它们）
- 不动 studio 控制台前端（`/console/scenarios` 之外的页面），只在该页内新增 Generator Tab
- **kev.vertical 的 `_OVERRIDE` 路径保留**（用户手动 `IndustryRegistry.load(json)` 的能力），但 `_default_registry()` 改为从 DB 派生
- **`vertical.INDUSTRIES` 运行时不可热加载**：本设计范围内，修改 `routing` 字段需要重启 kev-console 服务
- **EasyDistill yaml 仍由 `make_seeds config` 自动生成**；不试图让 EasyDistill 直接读 DB（框架层面约束）

## 2. 架构

### 2.1 数据流

```
   ┌────────────────────────────────────────────────────────────────────┐
   │  spec_json（DB 持久化，与 spec body 同一行同一 JSON）                │
   │                                                                     │
   │  {                                                                  │
   │    "name": "critical-value",                                        │
   │    "domain": "...",                                                 │
   │    "state": "...",                                                  │
   │    "state_example": {...},                                          │
   │    "questions": {...},                                              │
   │    "guidance": "...",         ← 自然语言，人类可读                  │
   │    "variety": [...],          ← 维度清单，UI 渲染为 checklist        │
   │                                                                     │
   │    "generator": {             ←  本设计新增（动态规则）            │
   │      "fields": [             ←  字段范围表（替代 PANELS/DRUGS/...）│
   │        {"name": "K+", "unit": "mmol/L", "type": "numeric",          │
   │         "decimals": 1, "category": "electrolyte",                   │
   │         "normal": [3.5, 5.3],                                       │
   │         "critical": {"low": [2.8, 3.0], "high": [6.2, 6.5]},         │
   │         "extremes": [6.5, 9.0]   ← critical 之外的极端值，触发立即档 │
   │        }, ...                                                       │
   │      ],                                                            │
   │      "selectors": [         ←  决定每条 record 抽样哪些 field 的策略│
   │        {"min": 3, "max": 6, "weight_normal": 0.7, "weight_trigger": 0.3}│
   │      ],                                                            │
   │      "rules": [             ←  标签派生规则（按 priority 顺序求值） │
   │        {"id": "is_critical",                                      │
   │         "when": "any_outside_critical(state)",                    │
   │         "then": {"label": "is_critical", "value": "true"}},        │
   │        {"id": "is_critical_default",                             │
   │         "when": "true",                                           │
   │         "then": {"label": "is_critical", "value": "false"}},      │
   │        ...                                                         │
   │      ],                                                            │
   │      "augmentation": {      ←  软标签 / 最小对 / 证据缺失            │
   │        "evidence_drop": {                                       │
   │          "rate": 0.08,                                           │
   │          "fields": ["unit", "reference_range"],                  │
   │          "question": "is_critical",                              │
   │          "soft_target": {"true": 0.5, "false": 0.5},             │
   │          "force_label": {"evidence_sufficient": "false"}         │
   │        },                                                        │
   │        "minimal_pair": {                                         │
   │          "rate": 0.35,                                           │
   │          "strategy": "boundary_flip"                             │
   │        }                                                         │
   │      },                                                          │
   │      "plan_targets": {      ←  标签计划配额                          │
   │        "share": {"critical": 0.35, "normal": 0.65},              │
   │        "by_category": {                                         │
   │          "critical": {                                          │
   │            "quota": {                                           │
   │              "renal": 0.30,                                     │
   │              "electrolyte": 0.20,                               │
   │              "glucose_gas": 0.20,                               │
   │              "cbc": 0.15,                                       │
   │              "cardiac_coag": 0.15                               │
   │            },                                                   │
   │            "tier_split": {                                      │
   │              "cbc": [[0, 0.34], [1, 0.33], [2, 0.33]],         │
   │              ...                                               │
   │            }                                                    │
   │          }                                                     │
   │        }                                                       │
   │      }                                                         │
   │    },                                                          │
   │                                                                  │
   │    "distill": {             ←  蒸馏配置（替代 SYSTEM_PROMPTS/ASK）│
   │      "kev_track": true,                                         │
   │      "spec_for_kev": null,   ← null=本 spec；或 "triage" 等      │
   │      "system_prompt": {                                         │
   │        "zh": "你是一位谨慎的临床分诊助手...",                    │
   │        "en": "You are a careful clinical triage assistant..."   │
   │      },                                                         │
   │      "ask_template": "以下是一位患者到院分诊台的情况...\n{state}",│
   │      "topics": [...]   ← 仅 knowledge-qa 场景使用              │
   │    }                                                            │
   │  }                                                              │
   └────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
        ┌──────────────────────────────────────────────────────────┐
        │  kev/console/generators/engine.py  （唯一 Python 引擎）  │
        │  ┌────────────────────────────────────────────────────┐  │
        │  │  BoundarySampler  →  按 fields[i].normal/critical/  │  │
        │  │                     extremes 抽样 state              │  │
        │  ├────────────────────────────────────────────────────┤  │
        │  │  RuleEvaluator     →  按 rules 顺序求值，触发 then  │  │
        │  │                     （simpleeval + 内置算子）        │  │
        │  ├────────────────────────────────────────────────────┤  │
        │  │  Augmentor         →  evidence_drop / minimal_pair   │  │
        │  │  PlanAllocator     →  按 plan_targets 配额分桶      │  │
        │  │  DistillRenderer   →  jinja2 + state 渲染            │  │
        │  └────────────────────────────────────────────────────┘  │
        └──────────────────────────────────────────────────────────┘
```

### 2.2 模块拆分

| 模块 | 路径 | 职责 | 替换的旧文件 |
|---|---|---|---|
| 引擎入口 | `kev/console/generators/engine.py` | `run(scenario_slug, n, out, seed, pairs)`：从 DB 读 spec，调 BoundarySampler+RuleEvaluator+Augmentor，写 JSONL | 5 个 `gen_*.py` |
| 范围采样 | `kev/console/generators/sampler.py` | `BoundarySampler.sample(state_target, rng)`：从 `fields` + `selectors` 构造一条 state | `gen_critical_value.normal_value`/`critical_value`/`crossed` |
| 规则求值 | `kev/console/generators/rules.py` | `RuleEvaluator.evaluate(state) -> labels`：遍历 `rules`，触发首个匹配项的 `then` | `gen_*` 的 `decide`/`derive`/`evaluate` |
| 增强器 | `kev/console/generators/augment.py` | `Augmentor.apply(state, labels, rng) -> (new_state, soft)` | `gen_critical_value.make_record` 的 evidence_drop 分支 |
| 最小对 | `kev/console/generators/pair.py` | `PairBuilder.build(record, handle, rng) -> record\|None` | `gen_critical_value.pair_twin` |
| 配额 | `kev/console/generators/plan.py` | `PlanAllocator.allocate(n, rng) -> list[target]` | `plan_targets` |
| 蒸馏 | `kev/console/distill/render.py` | `DistillRenderer.render(spec, state, lang) -> str` | `make_seeds.SYSTEM_PROMPTS` + `ASK` + `render_state` |
| 蒸馏入口 | `kev/console/distill/make_seeds.py` | 退化为薄壳：扫 DB，过滤 `distill.kev_track`，调 engine + render | 现有 `make_seeds.SCENARIOS`/`SYSTEM_PROMPTS`/`ASK` |
| 蒸馏重建 | `kev/console/distill/seed_to_kev.py` | 退化为薄壳：扫 DB，调 `engine.labelled` 重建 | 现有 `seed_to_kev.SPEC_FOR` |
| 验证算子 | `kev/console/generators/ops.py` | 内置 simpleeval 算子（`any_outside_critical`、`min_tier` 等） | 散落在 5 个 `decide`/`derive` 中的逻辑 |

### 2.3 删除列表（用户选择「彻底删除」）

| 文件 | 状态 | 理由 |
|---|---|---|
| `kev/console/generators/gen_critical_value.py` | **删除** | 被 engine 替代 |
| `kev/console/generators/gen_diagnosis.py` | **删除** | 同上 |
| `kev/console/generators/gen_medication_review.py` | **删除** | 同上 |
| `kev/console/generators/gen_nursing_quality.py` | **删除** | 同上 |
| `kev/console/generators/gen_record_summary.py` | **删除** | 同上 |
| `kev/console/generators/gen_triage.py` | **删除** | 同上 |
| `kev/console/generators/run_matrix.py` | **保留 + 改**：移除 `SCENARIOS`（从 DB 读），保留 `NAME_RE`/`SIZES`/`check_name`/`steps` | 编排骨架仍在 |
| `kev/console/generators/common.py` | **保留 + 改**：移除 `load_spec` 之外的 helpers（搬到新模块） | 通用基础 |
| `kev/console/distill/make_seeds.py` | **保留 + 瘦身**：仅剩 main() 与参数解析 | 薄壳 |
| `kev/console/distill/seed_to_kev.py` | **保留 + 瘦身**：仅剩 main() 与对账 | 薄壳 |
| `kev/console/distill/check_volume.py` | **保留 + 改**：从 DB 读 `SPEC_FOR` | 校验脚本不动 |
| `kev/console/paths.py::ensure_generators_on_path` | **保留 + 验证**：6 个 `gen_*.py` 删除后这条仍要把 `kev/console/generators` 加到 `sys.path`，因为 `engine.py` 也要被发现 | 保持现状 |
| `kev/console/services/data.py` | **改**：`generate()` 直接调 `engine.run()` | 不再 `importlib.import_module("gen_*")` |

### 2.4 新依赖

`pyproject.toml` 增加：

```toml
dependencies = [
    ...
    "jinja2>=3.1",          # 蒸馏 system_prompt / ask_template
    "simpleeval>=1.0",      # 受限表达式求值
]
```

`simpleeval` 取代「自实现 `ast.eval`」的理由：simpleeval 是成熟库（PyPI 上 1.4k+ 项目依赖），默认白名单安全，升级由社区负责；自实现的 `ast` 解析器在「`x.y.z` 三层属性访问 + 白名单方法」场景下要写 ~200 行代码、还要写安全审计，不如 simpleeval 一行 `SimpleEval(functions=ALLOWED_FUNCTIONS)`。

## 3. 核心机制

### 3.1 BoundarySampler

输入：`(spec_json.generator.fields, spec_json.generator.selectors, state_target, rng)`。

`state_target` 来自 `plan_targets` 产出，决定「这条 record 触不触发某档/某类」。例：

```python
state_target = {"category": "electrolyte", "tier": 0}   # 触发立即档
state_target = None                                       # normal
```

抽样流程：

1. **选 triggering field**（仅当 `state_target` 指定了 category/tier）：从 `fields` 里筛 `category==state_target.category` 且 `tier` 可达的 field，按 `extremes` 范围抽值（`realize_tier` 的等价物）。无可达则这条 target 不可实现，返回 `None`。
2. **选 non-triggering fields**：`selectors[0].min..max` 个非触发 field，每个按 `weight_normal` 抽 normal 值。
3. **触发值再校准**：若触发值不在触发档范围，重抽 6 次（保留 `realize_tier` 的「验证胜过算术」原则）。
4. **附加额外触发项**（可选，按 `weight_trigger`）：在剩余 field 中再选 ≤2 个抽 critical 值，但 notify 档不能快于 `state_target.tier`（保留 round-21 的 5% 下限保护）。

输出：一个 `state` dict（field name → string value，渲染时按 `decimals` + `unit` 拼成 `"2.9 mmol/L"`，与现 `format_measurement` 等价）。

**与原 `gen_critical_value` 等价性证明**（这是回归门）：

| 原函数 | 新等价路径 |
|---|---|
| `normal_value(rng, panel)` | `BoundarySampler._sample_normal(field, rng)`（用 `field.normal` 范围，cTn / D-Dimer 单侧特例走 `field.one_sided` 子字段） |
| `critical_value(rng, panel)` | `BoundarySampler._sample_critical(field, rng)`（用 `field.critical.low`/`high`） |
| `crossed(rng, panel)` | `BoundarySampler._sample_crossed(field, rng)`（落在 `critical` 内侧但远离 normal） |
| `realize_tier(rng, panel, tier)` | `BoundarySampler._realize_tier(field, tier, rng)`（在 `tier_split[tier]` 窗口内重抽 + 验证） |
| `format_measurement(panel, value, with_unit)` | `BoundarySampler._format(field, value, with_unit)` |

**byte-for-byte 等价的条件**：seed、`random.Random` 的调用次数与顺序、采样窗口端点四舍五入规则均保持一致。这要求 `BoundarySampler` 内部**完全沿用** `boundary_value(rng, threshold, low, high, side, near, decimals)` 的随机流——即 `common.boundary_value` 不变，只把它从「自由函数」改成接收 `field` 而非散参。

### 3.2 RuleEvaluator

输入：`(spec_json.generator.rules, state)`，输出 `labels: dict[qid, value]`。

求值算法：

```
labels = {}
for rule in rules:
    when = simple_eval(rule.when, names={"state": state, **ops})
    if when:
        for assignment in rule.then:
            labels[assignment.label] = assignment.value
return labels
```

`simpleeval` 表达式允许：
- 变量：`state` / `state.field_name`
- 字面量：数字 / 字符串 / `true` / `false` / `null`
- 运算符：`+ - * / < <= == != >= > and or not in`
- 函数（白名单）：`min / max / round / any / all / len / abs`
- **领域算子**（注册到 simpleeval 的 `functions`）：

| 算子 | 等价原函数 | 用途 |
|---|---|---|
| `any_outside_critical(state)` | `outside(panel, value)` 的批版 | critical-value 的 `is_critical` |
| `min_tier(state)` | `notify_tier(item, value).min` | critical-value 的 `notify_within` |
| `fastest_tier_critical_item(state)` | `decide()` 末尾的 `triggering` 选 | critical-value 的 `critical_item` |
| `tier_priority_arbiter(presentations)` | `derive()` 内的 `best = min(top, key=...)` | diagnosis / triage 的优先级仲裁 |
| `red_flag_wins(presentations)` | `decide()` 的红旗下 emergency | triage / diagnosis |
| `pediatric_short_circuit(symptoms, age)` | `decide()` 的 PEDIATRIC 分支 | triage |
| `any_special_population(drug, flags)` | `evaluate()` 的 `special_population` 命中 | medication |
| `dose_exceeds(drug, dose_per, times_per_day)` | `evaluate()` 的 dose_over | medication |
| `duplicate_category(drug, twin)` | `evaluate()` 的 duplicate | medication |
| `indication_matches(drug, indication)` | `evaluate()` 的 indication_mismatch 取反 | medication |
| `lift_severity(severity, high_dep)` | `decide()` 的 high_dependency 抬档 | nursing |
| `missing_element(missing, mismatch)` | `derive()` 的 ELEMENT_SEVERITY 映射 | record-summary |
| `bool_to_str(b)` | Python `str(b).lower()` 的封装 | noul 题的 label 必是 `"true"`/`"false"` 字符串 |

算子注册在 `kev/console/generators/ops.py`，每个算子**纯函数 + 完整 docstring + 引用原 gen_*.py 源行号**。simpleeval 实例的 `functions` 字段一次性喂这些算子。

### 3.3 Augmentor

输入：`(state, labels, spec_json.generator.augmentation, rng)`，输出 `(state_modified, labels_modified, soft)`。

**调用顺序**：`BoundarySampler` 构造 state → `RuleEvaluator` 派生 labels → `Augmentor` 后置修改（先改 state、再 force labels、最后注入 soft）。后置保证 evidence_drop 后还能复算 labels（如果改的是 unit/reference_range，labels 不变；如果 spec 写了「删 unit 后 evidence_sufficient 必为 false」，force 路径覆盖）。

`evidence_drop`：以 `rate` 概率选一个 `fields` 元素，将 state 里该 field 的 `with_unit=False` 或 `with_refs=False`，**强制** `labels[question]=false`（或 spec 写的 `force_label`），并 `soft[question] = soft_target`。

`minimal_pair`：以 `rate` 概率生成 twin ——
- `strategy=boundary_flip`：用 `BoundarySampler._sample_crossed()` 替换 triggering field，验证 label 翻转
- `strategy=drop_one_field`：随选一个 field 删空，验证 label 翻转（用于 `record-summary` 现有 `ELEMENTS` 列表之外的场景）

### 3.4 PlanAllocator

输入：`(spec_json.generator.plan_targets, n, rng)`，输出 `list[target]`。

通用算法：

1. `share` 决定 `critical` vs `normal` 大盘（`critical=0.35, normal=0.65` 之类）
2. `critical` 内按 `by_category.quota` 分桶（`renal:0.30, electrolyte:0.20, ...`）
3. 每桶内按 `tier_split` 轮转（如 `cbc`：`[[0,0.34], [1,0.33], [2,0.33]]`）
4. 凑够 n 条后 `rng.shuffle(plan)`

`quota` 写法等价于现 `CATEGORY_TIER_SPLIT`：

```python
# 原
CATEGORY_TIER_SPLIT = {"cbc": [(0, 0.34), (1, 0.33), (2, 0.33)], ...}

# 新
"plan_targets": {
  "by_category": {
    "critical": {
      "quota": {"renal": 0.30, ...},
      "tier_split": {"cbc": [[0, 0.34], [1, 0.33], [2, 0.33]], ...}
    }
  }
}
```

`diagnosis` 的 round-robin 写法（`bucket = i % 25`）需要引入 `custom_strategy` 子字段：

```json
"plan_targets": {
  "custom": "round_robin",
  "round_robin": {
    "period": 25,                              // 总桶数
    "slots": [                                 // 按 slot index 分桶
      {"slot": [0, 1], "target": "undirected"},
      {"slot": [2, 24], "target": "department_index", "stride": 1}
    ]
  }
}
```

`slots[i].slot = [lo, hi]` 是**闭区间**（`range(lo, hi+1)`），含 lo 与 hi。`target` 是字面字符串（`"undirected"`）或 `department_index`（与 `tier_split` 类似，按字段派生：`(i // 2) % len(departments)`）。引擎内对应一个 `round_robin` 算子，照搬现 `gen_diagnosis.plan_targets` 与 `gen_triage.plan_targets` 的桶分配逻辑。

### 3.5 DistillRenderer

```python
from jinja2 import Environment, BaseLoader

env = Environment(loader=BaseLoader(), autoescape=False)  # LLM prompt 文本不 HTML 转义
system = env.from_string(spec.distill.system_prompt[lang]).render()
ask = env.from_string(spec.distill.ask_template).render(state=render_state(state))
```

`render_state` 沿用现 `make_seeds.render_state`（flat key-value lines），搬进 `kev/console/distill/render.py`。

`topics`（仅 `knowledge-qa`）沿用现 `knowledge_qa_records` 的列表，作为 `distill.topics` JSON 数组。

### 3.6 路由配置（接 `kev.vertical`）

`kev/vertical.py` 的 `_medical()` / `_finance()` / `_legal()` / `_education()` / `_support()` 把 5 个行业 + 14 个场景的 `Scenario` 实例（`risk` / `human_review` / `evidence_question` / `note`）硬编码进了 Python 函数。`vertical` 模块**已经有** `IndustryRegistry.load(json)` 路径把行业 + 场景从 JSON 装载进来（`vertical.py:343`），但目前没有 JSON 文件，所有部署都用 `_default_registry()` 的硬编码 fallback。

动态化方向：

- **spec_json 顶层加 `routing` 块**，承载 `risk` / `human_review` / `evidence_question` / `note`：

  ```json
  "routing": {
    "risk": "high",                       // "low" | "medium" | "high" | "critical"
    "human_review": true,
    "evidence_question": "evidence_sufficient",   // qid；与 spec_json.questions 对应
    "note": "漏报危急值 ≫ 误报：低置信必须升级 4B 并强制转人工，不取 argmax 自动处置。"
  }
  ```

- **`kev/vertical.py::_default_registry()`** 改为「从 DB 读 `scenarios` 表 → 派生 `Scenario(name=slug, industry=scenario.category, risk=routing.risk, ...)` → 装进 `Industry(name=scenario.category)`」。`medical` / `finance` / `legal` / `education` / `support` 五个硬编码 `IndustryRegistry` 构造函数全部删除。
- **`_OVERRIDE` 路径保留**（用户手动 `IndustryRegistry.load(json)` 的能力），但默认来源切换到 DB。
- **新加 `kev/console/services/routing.py::sync_registry()`**：编排服务启动时调一次，把 DB 状态投影到 `vertical.INDUSTRIES` 内存对象；运行时改动 routing 字段需要重启服务（或热加载，**第 1 版不做**）。

### 3.7 部署探针（接 `kev.console.stages.deploy`）

`kev/console/stages/deploy.py::SMOKE_PROBES` 硬编码 5 个医疗场景各 1 例冒烟探针，是部署 `kev.serve` 后用 `/v1/systemone` 打一发验证的标准样本。**这正是 spec_json 里 `state_example` 字段的运行时用途**——但目前 `state_example` 是「spec 文档里的示例」，没有走运行时。

动态化方向：

- **spec_json 顶层加 `smoke_probe` 块**（与 `state_example` 并列，不是替代）：

  ```json
  "smoke_probe": {
    "state": { ... },                    // 与 state_example 一致，但所有字段填满真实值
    "questions": [
      {"qid": "is_critical", "type": "noul",
       "instructions": "该报告中的任一检验项目是否触及危急值（需要立即临床干预）？"}
    ],
    "expected_label": "true"             // 部署后打一发，断言模型答这个；不匹配则部署 fail
  }
  ```

- **`SMOKE_PROBES` 常量删除**，改为 `db.list_smoke_probes() -> list[dict]`：从 `scenarios` 表读所有有 `smoke_probe` 的场景，组装成原 list 形状。
- **`scenarios.spec_json` 的 `smoke_probe` 在 `_backfill_specs` 里从仓库的 `docs/medical/specs/*.json` 同步进来**——这意味着 `docs/medical/specs/critical-value.json` 要补 `smoke_probe` 字段，作为各场景的初始探针。`smoke_probe` 字段不进 `guidance` / `variety` 的人类可读部分，纯运行时。
- **`kev.console.services.deploy` 也走 DB 路径**——service 调 `db.list_smoke_probes()`，Popen 路径调 `python -m kev.console.smoke --from-db`。

### 3.8 蒸馏 YAML 配置（接 `kev/console/distill/configs/*.yaml`）

5 个 `configs/<scenario>.yaml` 是 EasyDistill 框架的输入（`input_file` / `output_dir` / `system_prompt` / `pipeline`），**不能直接消除**——EasyDistill 不读 DB。但 `make_seeds.py` 可以**自动生成**它们（render Jinja2 模板到 `data/seeds/configs/<slug>.yaml`），并提供 `make_seeds config <slug>` 子命令。

动态化方向：

- **新加 `kev/console/distill/configs/template.yaml.j2`**：Jinja2 模板，包含 `job_type` / `backend` / `pipeline` 的固定结构，`system_prompt` / `dataset.input_file` / `dataset.output_dir` 用 `{{ slug }}` / `{{ spec.distill.system_prompt.zh }}` 占位。
- **`make_seeds.py --all` 自动产出 yaml**：与 `.seed.jsonl` / `.state.jsonl` 一起写到 `<out-dir>/configs/<slug>.yaml`。
- **现有 5 个 yaml 保留为参考模板**（不删除，但不再被脚本自动读；`make_seeds README.md` 指向新位置）。
- **`distill.daemon_runner` 读 `<out-dir>/configs/<slug>.yaml` 启动**——这一段是 EasyDistill 的范畴，**不在本设计范围**。

## 4. spec JSON 完整形态（以 critical-value 为例）

> 这是迁移完成后，scenarios.spec_json 的实际内容。不是凭空设计，是把现 `gen_critical_value.py` 的 6 个常量 + 3 个函数 + 1 个配额表**完全**翻译过来。

```json
{
  "name": "critical-value",
  "domain": "医院检验科与影像科报告复核。检验项目包括血钾...",
  "state": "一份已出具的检验或影像报告的结构化摘要...",
  "state_example": { ... },
  "questions": { ... },                // 不动
  "guidance": "危急值是本场景唯一判据：任一项目超出下表上下限即为 is_critical=true...",
  "variety": [ ... ],                  // 不动

  "generator": {
    "fields": [
      {"name": "K+",  "unit": "mmol/L",  "decimals": 1, "category": "electrolyte",
       "normal": [3.5, 5.3], "critical": {"low": [2.8, 3.0], "high": [6.2, 6.5]},
       "extremes": {"low": [1.5, 2.79], "high": [6.5, 9.0]}},
      {"name": "Na+", "unit": "mmol/L",  "decimals": 1, "category": "electrolyte",
       "normal": [137, 147], "critical": {"low": [105.0, 119.9], "high": [160.1, 175.0]}},
      {"name": "GLU", "unit": "mmol/L",  "decimals": 1, "category": "glucose_gas",
       "normal": [3.9, 6.1], "critical": {"low": [1.5, 2.79], "high": [16.7, 30.0]}},
      {"name": "Cr",  "unit": "umol/L",  "decimals": 1, "category": "renal",
       "normal": [44, 106], "critical": {"high": [442.0, 900.0]}},
      {"name": "pH",  "unit": "",         "decimals": 2, "category": "glucose_gas",
       "normal": [7.35, 7.45], "critical": {"low": [6.8, 7.19], "high": [7.61, 7.9]}},
      {"name": "Hb",  "unit": "g/L",      "decimals": 1, "category": "cbc",
       "normal": [115, 175], "critical": {"low": [30.0, 49.9], "high": [200.1, 260.0]}},
      {"name": "PLT", "unit": "x10^9/L",  "decimals": 1, "category": "cbc",
       "normal": [125, 350], "critical": {"low": [5.0, 29.9], "high": [1000.1, 1500.0]}},
      {"name": "WBC", "unit": "x10^9/L",  "decimals": 1, "category": "cbc",
       "normal": [3.5, 9.5], "critical": {"low": [0.3, 1.4], "high": [30.1, 60.0]}},
      {"name": "cTn", "unit": "ng/mL",    "decimals": 3, "category": "cardiac_coag",
       "normal": [0.0, 0.04], "one_sided": "high", "critical": {"high": [0.04, 0.4]}},
      {"name": "D-Dimer", "unit": "mg/L FEU", "decimals": 3, "category": "cardiac_coag",
       "normal": [0.0, 0.5], "one_sided": "high", "critical": {"high": [5.1, 20.0]}}
    ],
    "selectors": [
      {"min": 3, "max": 6, "weight_normal": 1.0, "weight_trigger_extra": 0.35,
       "max_trigger_extra": 2, "max_trigger_tier_drift": 0}
    ],
    "categories": {                        // 派生量：从 fields[].category 反向 group 得出；引擎
                                           // 启动时一次性物化，UI 用来画饼图与 tier_split 配对
      "electrolyte": ["K+", "Na+"],
      "renal": ["Cr"],
      "glucose_gas": ["GLU", "pH"],
      "cbc": ["Hb", "PLT", "WBC"],
      "cardiac_coag": ["cTn", "D-Dimer"]
    },
    "tier_windows": {
      "0": {"K+": [[6.5, 9.0]], "Na+": [[160.1, 175.0], [105.0, 119.9]],
            "pH": [[6.8, 7.19], [7.61, 7.9]], "GLU": [[16.7, 30.0], [1.5, 2.79]],
            "cTn": [[0.04, 0.4]], "Hb": [[30.0, 49.9]]},
      "1": {"K+": [[6.21, 6.5]], "Cr": [[442.1, 900.0]],
            "PLT": [[5.0, 29.9], [1000.1, 1500.0]], "Hb": [[200.1, 260.0]]},
      "2": {"WBC": [[30.1, 60.0], [0.3, 1.4]], "D-Dimer": [[5.1, 20.0]]}
    },
    "contexts": [
      "胸闷 3 天，血压 168/95 mmHg，既往 2 型糖尿病",
      "体检发现血钾升高，无明显不适",
      ...
    ],
    "patients": ["male 67", "female 58", "male 45", "female 72",
                 "female 29", "male 8", "female 66", "male 3"],
    "rules": [
      {"id": "is_critical_true",
       "when": "any_outside_critical(state)",
       "then": [{"label": "is_critical", "value": "true"},
                {"label": "notify_within", "value": "min_tier(state)"},
                {"label": "critical_item", "value": "fastest_tier_critical_item(state)"}]},
      {"id": "is_critical_default",
       "when": "true",
       "then": [{"label": "is_critical", "value": "false"},
                {"label": "notify_within", "value": "3"},
                {"label": "critical_item", "value": "none"}]},
      {"id": "evidence_sufficient",
       "when": "true",
       "then": [{"label": "evidence_sufficient", "value": "bool_to_str(len(state.get('missing_context', [])) == 0)"}]}
    ],
    "augmentation": {
      "evidence_drop": {
        "rate": 0.08,
        "fields": ["unit", "reference_range"],
        "question": "is_critical",
        "soft_target": {"true": 0.5, "false": 0.5},
        "force_label": {"evidence_sufficient": "false"}
      },
      "minimal_pair": {"rate": 0.35, "strategy": "boundary_flip"}
    },
    "plan_targets": {
      "share": {"critical": 0.35, "normal": 0.65},
      "by_category": {
        "critical": {
          "quota": {
            "renal": 0.30, "glucose_gas": 0.20, "electrolyte": 0.20,
            "cardiac_coag": 0.15, "cbc": 0.15
          },
          "tier_split": {
            "renal":         [[1, 1.0]],
            "glucose_gas":   [[0, 1.0]],
            "electrolyte":   [[0, 0.5], [1, 0.5]],
            "cardiac_coag":  [[0, 0.5], [2, 0.5]],
            "cbc":           [[0, 0.34], [1, 0.33], [2, 0.33]]
          }
        }
      }
    }
  },

  "distill": {
    "kev_track": true,
    "spec_for_kev": null,
    "system_prompt": {
      "zh": "你是一位医院检验科与影像科报告复核助手...",
      "en": "You are a hospital lab/imaging report reviewer..."
    },
    "ask_template": "以下是一份已出具的检验报告。请判断是否触及危急值、通知时长、触发项类别与证据充分性。\n{state}",
    "yaml_template": "kev/console/distill/configs/template.yaml.j2"   // 见 §3.8
  },

  "routing": {                              // 见 §3.6（接 kev.vertical）
    "risk": "high",
    "human_review": true,
    "evidence_question": "evidence_sufficient",
    "note": "漏报危急值 ≫ 误报：低置信必须升级 4B 并强制转人工，不取 argmax 自动处置。"
  },

  "smoke_probe": {                          // 见 §3.7（接 stages.deploy）
    "state": {
      "patient": "male 67",
      "context": "routine chemistry panel, no symptoms reported",
      "labs": {"K+": "6.2 mmol/L", "Cr": "98 umol/L"},
      "ref_ranges_included": true,
      "missing_context": []
    },
    "questions": [
      {"qid": "is_critical", "type": "noul",
       "instructions": "该报告中的任一检验项目是否触及危急值（需要立即临床干预）？"}
    ],
    "expected_label": {"is_critical": "true"}
  }
}
```

**等价性保证**：与 `gen_critical_value.py` 共用 `common.boundary_value`（不改）、共用 `common.labelled`（不改）、共用 `common.write_records`（不改）、共用 `common.label_table`（不改）。`BoundarySampler` / `RuleEvaluator` / `Augmentor` / `PlanAllocator` 在每条 record 上产生的随机数流与原 `gen_critical_value.build` + `pair_twin` + `plan_targets` 一致。回归测试用 `seed=0, n=787, pairs=0.35` 在同一 spec 上跑新旧两条路径，diff 两条 JSONL 必须为空。

## 5. UI（playground/src/app/console/scenarios/page.tsx）

### 5.1 新增「Generator」Tab

在现有「域列表 / 场景编辑 / Spec 编辑器」之外加一个 `Generator` Tab（仅当 `selected.type === "scenario"` 时显示），路由 `#generator/<slug>`。

四个子面板：

1. **Fields**：表格
   - 列：`name / unit / decimals / category / normal / critical / extremes / one_sided`
   - 行内编辑，`Add field` 按钮追加新行
   - `normal` / `critical` / `extremes` 接受范围对（两数字输入）
   - 校验：name 唯一、critical 必须严格在 normal 之外

2. **Rules**：可视化
   - 每条 rule 一行：`when` (textarea) → `then` (label-value 表格)
   - 顶部「Add rule」按钮
   - 实时 simpleeval 预览（用当前 state_example 试跑，结果渲染在右侧）
   - 错误标红：未定义变量、算子白名单外的方法

3. **Augmentation & Plan**：表单
   - `evidence_drop`：`rate` 滑杆 + `fields` 多选 + `soft_target` 表
   - `minimal_pair`：`rate` + `strategy` 下拉
   - `plan_targets.share` 折线图
   - `by_category.critical.quota` 饼图（sum 必须 = 1.0）

4. **Distill**：表单
   - `kev_track` 开关
   - `system_prompt.zh` / `.en` textarea
   - `ask_template` textarea + 「Render preview」按钮（用 `state_example` 实时渲染）

所有子面板**共享**一个 `generator_draft` state，顶部固定条「保存 / 丢弃 / 重置」三按钮：
- **保存**：`PUT /console/api/scenarios/{id}` body 含 `generator` 字段（需新加后端路由 / 字段，见 §6.2）
- **丢弃**：rollback 到最近一次保存的版本
- **重置**：从 spec 模板恢复

### 5.2 UI 校验

前端使用 `zod` 模式（项目已有）定义 `GeneratorSchema`，每个子面板挂自己的 `zodResolver`。保存时若后端拒绝，前端把 `errors` 映射到对应子面板的红框。

## 6. 后端契约

### 6.1 现有路由扩展

`PUT /console/api/scenarios/{scenario_id}` 接受 `generator` / `distill` / `routing` / `smoke_probe` 四个字段（同级 `label_zh` / `label_en` / `spec_path` / `category` / `sort`）。`db.update_scenario` 接受这四个字段，存进 `spec_json`（与 spec body 一同版本化）。

- `generator`：§3.1-3.4 描述的规则 + 范围 + 配额配置
- `distill`：§3.5 + §3.8 描述的 system_prompt / ask_template / yaml_template
- `routing`：§3.6 描述的 `risk` / `human_review` / `evidence_question` / `note`
- `smoke_probe`：§3.7 描述的 state + questions + expected_label

**字段级校验**（后端 `db.update_scenario` 接受前）：

- `routing.risk` ∈ `{"low", "medium", "high", "critical"}`（与 `kev.vertical.RISK_LEVELS` 一致）
- `routing.evidence_question`（若非空）必须 ∈ `spec_json.questions` 的 qid
- `smoke_probe.questions[].qid` 必须 ∈ `spec_json.questions` 的 qid
- `smoke_probe.expected_label` 的 value 必须 ∈ `spec_json.questions.<qid>.criteria`（noul: true/false；choice: criteria key；score: 0..len(criteria)-1 的字符串）

### 6.2 新增路由

| Method | Path | 用途 |
|---|---|---|
| `POST` | `/console/api/scenarios/{slug}/generator/preview` | body=`{generator, distill, state_example}` → 返回 `{state: {...}, labels: {...}, soft: {...}}` 单条预览 |
| `POST` | `/console/api/scenarios/{slug}/generator/dry-run` | body=`{n: 100, seed: 0}` → 在内存里跑 engine，返回 `{rows: [...], label_table: {...}, warnings: [...]}`（不写文件） |
| `POST` | `/console/api/scenarios/{slug}/generator/validate` | body=`{generator, distill}` → simpleeval 干跑（用 spec.state_example 作 state），返回 `{errors: [{rule_id, message}]}` |

### 6.3 service 路径

`kev/console/services/data.py::generate` 改为：

```python
def generate(self, req: JobRequest, *, on_log: Callable[[str], None]) -> dict:
    from kev.console.generators.engine import run as engine_run
    args = self._build_generate_args(req)
    rc = engine_run([str(part) for part in args], on_log=on_log)
    return {"returncode": rc}
```

Popen 路径（`kev/console/stages/data.py::_generate`）改为调 `python -m kev.console.generators.engine`：

```python
argv = [_python(), "-m", "kev.console.generators.engine", "--scenario", request.scenario,
        "--n", str(n), "--out", out, "--seed", str(seed), "--pairs", str(pairs)]
```

`python -m kev.console.generators.engine` 是 `engine.run` 的 CLI 包装，参数与现 `gen_*.py::run` 一致（`--scenario` 取代硬编码文件名）。

### 6.4 依赖 `pyproject.toml`

```toml
dependencies = [
    ...,
    "jinja2>=3.1",
    "simpleeval>=1.0",
]
```

## 7. 错误处理

| 失败模式 | 处理 |
|---|---|
| `scenarios.spec_json` 无 `generator` 字段 | service 路径 raise `Invalid("场景 X 缺少 generator 配置", field="scenario", hint="在控制台 Generator 标签里配置")` |
| simpleeval 表达式引用未定义变量 | engine 启动时 dry-run 一遍 `rules` 与 `when` 表达式，捕获 `NameError`，回 `400` |
| 简单 `when` 引用了白名单外的算子 | engine 启动时 `simple_eval` 实例化时 `functions` 已白名单化，调用未注册的算子抛 `AttributeError`，映射为 `Invalid` |
| `plan_targets` 的 `quota` 之和不为 1.0 | UI 校验挡；后端 dry-run 再挡一次（差额超 0.001 报错） |
| `fields` 的 `name` 重复 | UI 与 service 双向校验 |
| `state_target` 在某 field 不可达（无 tier window） | 引擎自动回退到 `normal`（`return None, None` 等价原 `build` 的 fallback） |

## 8. 测试

### 8.1 单元（`tests/test_engine.py`，纯本地、纯 CPU）

每个场景一组 fixture（用 frozen JSON 文件 `tests/fixtures/<scenario>/spec.json` 提供 spec_json 全量）：

| 测试 | 断言 |
|---|---|
| `test_critical_value_byte_for_byte` | engine 输出与 `data/critical-value.jsonl`（committed）byte-equal |
| `test_diagnosis_byte_for_byte` | 同上 |
| `test_medication_review_byte_for_byte` | 同上 |
| `test_nursing_quality_byte_for_byte` | 同上 |
| `test_record_summary_byte_for_byte` | 同上 |
| `test_triage_byte_for_byte` | 同上 |
| `test_engine_no_evaluator_network` | 在断网环境下跑完整 5 个场景 |
| `test_ops_whitelist_enforced` | `simpleeval` 拒绝 `__import__` / `open` / 任意白名单外方法 |
| `test_plan_allocator_quota_sums` | 各场景 `plan_targets` 配额在 ±0.001 内归一 |
| `test_distill_renders_state_example` | Jinja2 模板用 `state_example` 渲染无异常 |
| `test_yaml_template_renders` | `template.yaml.j2` render 5 个场景的 spec.distill + generator 字段，全部产出有效 yaml |

`byte_for_byte` 测试需要 committed 旧产物。`runs/kev-console/golden/{critical-value,diagnosis,...}.jsonl` 是迁移前在 `seed=0, n=787, pairs=0.35` 下的产物，迁移后 commit 到 git 作为黄金样本（生成一次、commit、复用）。

### 8.2 集成（`tests/test_api.py` 扩展）

| 测试 | 断言 |
|---|---|
| `test_generator_dry_run` | `POST /generator/dry-run` 返回 n 条 + label_table 覆盖所有 criteria |
| `test_generator_validate_unknown_op` | 故意写一个 `__import__` 的 when，validate 返 400 |
| `test_scenarios_put_accepts_generator` | `PUT /scenarios/{id}` 接受 `generator` 字段，get_scenario_by_slug 读回一致 |
| `test_scenarios_put_accepts_routing` | `PUT /scenarios/{id}` body 含 `routing.risk="high"` 接受；`routing.risk="bogus"` 拒绝 400 |
| `test_scenarios_put_accepts_smoke_probe` | `PUT /scenarios/{id}` body 含 `smoke_probe.questions[0].qid="is_critical"` 接受；`qid` 不在 `spec_json.questions` 中拒绝 400 |
| `test_routing_sync_matches_hardcoded` | DB 派生 `vertical.INDUSTRIES` 与 `_default_registry()` 在 5 个行业的 scenario 顺序、`Scenario(risk, human_review, evidence_question, note)` 字段逐项相等 |
| `test_smoke_probes_match_hardcoded` | `db.list_smoke_probes()` 返回 5 例与 `stages/deploy.SMOKE_PROBES`（迁移前 committed 的副本）字段逐项相等 |
| `test_yaml_template_render` | `make_seeds config --scenario inquiry --out-dir /tmp/cfg` 产 yaml 与 `kev/console/distill/configs/inquiry.yaml` byte-equal |

### 8.3 手工

迁移顺序：

1. **先迁移 critical-value**（最复杂、最多 round-trip 痕迹、最多 5% 下限保护）。在 `data/critical-value.jsonl` 提交前先 commit 一份 `runs/kev-console/golden/critical-value.jsonl` 作为黄金。
2. 跑 `python -m kev.console.generators.engine --scenario critical-value --n 787 --out /tmp/new.jsonl --seed 0`，`diff data/critical-value.jsonl /tmp/new.jsonl` 必须为空。
3. **其他 4 个场景同样流程**。
4. 6 个全过之后，删除 `gen_*.py` 与 `run_matrix.SCENARIOS` 字典、`make_seeds.SCENARIOS/SYSTEM_PROMPTS/ASK`、`seed_to_kev.SPEC_FOR`。
5. 跑 `pytest tests/test_unit.py tests/test_console_db.py tests/test_engine.py -q` 全绿。

## 9. 文件清单

### 新增

23 个文件：

| 文件 | 行数估计 |
|---|---|
| `kev/console/generators/engine.py` | 80 |
| `kev/console/generators/sampler.py` | 220 |
| `kev/console/generators/rules.py` | 90 |
| `kev/console/generators/augment.py` | 100 |
| `kev/console/generators/pair.py` | 70 |
| `kev/console/generators/plan.py` | 110 |
| `kev/console/generators/ops.py` | 180（5 个场景 × ~10 算子 + docstring） |
| `kev/console/generators/__main__.py` | 30（`python -m` 入口） |
| `kev/console/distill/render.py` | 60 |
| `kev/console/distill/configs/template.yaml.j2` | 80（蒸馏 yaml 模板，§3.8） |
| `kev/console/services/routing.py` | 60（`sync_registry()` 把 DB → `vertical.INDUSTRIES`，§3.6） |
| `kev/console/services/smoke.py` | 40（`list_smoke_probes()` 从 DB 派生，§3.7） |
| `tests/test_engine.py` | 200 |
| `tests/test_routing_sync.py` | 100（`_default_registry` 从 DB 派生后与原硬编码 registry 一致） |
| `tests/test_smoke_probes.py` | 60（`db.list_smoke_probes()` 返回 5 个场景，与原 `SMOKE_PROBES` 一致） |
| `tests/fixtures/critical-value/spec.json` | 420（一份完整 spec_json，含 generator + distill + routing + smoke_probe） |
| `tests/fixtures/diagnosis/spec.json` | 360 |
| `tests/fixtures/medication-review/spec.json` | 360 |
| `tests/fixtures/nursing-quality/spec.json` | 340 |
| `tests/fixtures/record-summary/spec.json` | 340 |
| `tests/fixtures/triage/spec.json` | 360 |
| `runs/kev-console/golden/{6 个}.jsonl` | 现 6 份数据 → commit 一次 |
| `playground/src/app/console/scenarios/GeneratorTab.tsx` | 750（多 2 子面板：Routing / Smoke Probe） |
| `playground/src/app/console/scenarios/GeneratorTab.test.tsx` | 240 |

### 修改

| 文件 | 改动 |
|---|---|
| `pyproject.toml` | `dependencies` 加 `jinja2`, `simpleeval`；`packages` 加 `kev.console.generators`, `kev.console.distill`, `kev.console.services` |
| `kev/console/db.py` | `update_scenario` / `create_scenario` / `write_spec_file` 接受 `generator` / `distill` / `routing` / `smoke_probe` 四个子字段；`_backfill_specs` 同步回填（从 `docs/medical/specs/*.json` 读 `routing` / `smoke_probe` 块）；`seed_scenarios` 删 `labels` 字典，label 派生走 `paths.SPECS/<slug>.json` 的 `name` + 注释首行（"危急值复核记录生成器" → "危急值"）；`db.list_smoke_probes()` 新方法 |
| `kev/console/app.py` | 新增 3 路由（§6.2），`update_scenario` 路由 body schema 加 4 个新字段 + 字段级校验（§6.1） |
| `kev/console/services/data.py` | `generate()` 改调 `engine.run()`；移除 `importlib.import_module` |
| `kev/console/services/deploy.py` | 替换 `SMOKE_PROBES` 引用为 `db.list_smoke_probes()` |
| `kev/console/stages/data.py` | `_generate` argv 改为 `python -m kev.console.generators.engine --scenario ...`；`SMOKE_PROBES` 引用替换 |
| `kev/console/stages/deploy.py` | `SMOKE_PROBES` 常量删除，argv 改为 `python -m kev.console.smoke --from-db`（service 路径同） |
| `kev/console/smoke.py` | 新增 `--from-db` flag：从 `db.list_smoke_probes()` 派生探针 |
| `kev/console/generators/run_matrix.py` | `SCENARIOS`/`FOUR_B_ONLY` 改从 DB 读；`steps()` 的 generate argv 同样改成 `-m engine` |
| `kev/console/generators/common.py` | 仅留 `boundary_value` / `labelled` / `write_records` / `label_table` / `load_spec` / `base_parser` / `label_keys`；删除 `minimal_pair`（被 pair.py 替代） |
| `kev/console/distill/make_seeds.py` | 删除 4 个字典；`generate()` 改读 DB 调 engine + render；新增 `make_seeds config <slug>` 子命令（render yaml 模板到 `<out-dir>/configs/<slug>.yaml`，§3.8） |
| `kev/console/distill/seed_to_kev.py` | 删除 `SPEC_FOR`；`build_records` 改读 DB |
| `kev/console/distill/check_volume.py` | `SPEC_FOR` 改从 DB 读 |
| `kev/vertical.py` | 删除 `_medical` / `_finance` / `_legal` / `_education` / `_support` 5 个硬编码 `Industry` 构造函数；`_default_registry()` 改为 `kev/console/services/routing.py::sync_registry()`；保留 `IndustryRegistry.load(json)` 路径；保留 `Industry` / `Scenario` / `Adapter` / `Router` 等所有数据结构；保留 `_OVERRIDE` 全局变量；保留 `kev_modal.py` 训练与 `kev.serve` 部署的所有协议 |
| `playground/src/app/console/scenarios/page.tsx` | 加 `Generator` Tab（6 子面板：Fields / Rules / Augmentation+Plan / Distill / Routing / Smoke Probe） |
| `playground/src/lib/console.ts` | 加 3 个 API client 方法（preview / dry-run / validate） |
| `playground/AGENTS.md` | 文档加「Generator 标签」一节（怎么用、保存时机、错误处理） |
| `docs/medical/specs/critical-value.json` | **首次提交** 加 `routing` 与 `smoke_probe` 字段（其他 4 个 spec 同理） |
| `docs/medical/specs/{diagnosis,medication-review,nursing-quality,record-summary,triage}.json` | 同上 |
| `kev/console/distill/README.md` | "新增场景 3 步" 改为 "新增场景 1 步：在 `specs/<slug>.json` 补 `generator` / `distill` / `routing` / `smoke_probe` 字段" |
| `kev/console/generators/README.md` | "新增场景 3 步" 同上修改；删 5 个 gen_*.py 的表格行（迁移后不再存在） |

### 删除

| 文件 | 理由 |
|---|---|
| `kev/console/generators/gen_critical_value.py` | engine 替代 |
| `kev/console/generators/gen_diagnosis.py` | 同上 |
| `kev/console/generators/gen_medication_review.py` | 同上 |
| `kev/console/generators/gen_nursing_quality.py` | 同上 |
| `kev/console/generators/gen_record_summary.py` | 同上 |
| `kev/console/generators/gen_triage.py` | 同上 |
| `kev/console/generators/__init__.py` | 空壳，整包靠 `engine` 暴露 |
| `kev/console/distill/__init__.py` | 同上 |
| `kev/console/services/__init__.py` | 同上 |
| `kev/console/services/data.py::generate` 的 `importlib.import_module("gen_*")` 块 | 同上 |
| `kev/console/stages/deploy.py::SMOKE_PROBES` 常量 | `db.list_smoke_probes()` 替代 |
| `kev/vertical.py::_medical` 函数 | `sync_registry()` 从 DB 派生 |
| `kev/vertical.py::_finance` 函数 | 同上 |
| `kev/vertical.py::_legal` 函数 | 同上 |
| `kev/vertical.py::_education` 函数 | 同上 |
| `kev/vertical.py::_support` 函数 | 同上 |
| `kev/console/distill/configs/inquiry.yaml` 等 5 个 yaml | 退化为参考模板，`make_seeds config` 重新生成 |
| `kev/console/db.py::seed_scenarios.labels` 字典 | label 派生走 `paths.SPECS/<slug>.json` 注释首行 |

## 10. 不在范围内

- 不改 train/eval/deploy/publish 的 stage 与 service
- 不改 `kev/console/app.py` 的现有路由（只新增 3 个）
- 不改 `evals/` 下任何 frozen suite
- 不动 `split_data.py` / `make_goldset.py` 的算法（它们读 `data/*.jsonl`，与生成器解耦）
- 不引入 LLM 辅助生成规则（LLM 不接触标签的原则不变）
- 不做跨域（医疗之外）的多 domain 适配 — generator 是医疗专用的，但 schema 不耦合；非医疗场景后续单独提需求
- 不做 per-question 粒度的 dry-run 调试器（仅 state 级 preview）
- 不做 generator config 的 export/import 工具（UI 复制粘贴 spec_json 即可）

## 11. 风险与缓解

| 风险 | 概率 | 影响 | 缓解 |
|---|---|---|---|
| byte-for-byte 不一致 | 中 | 高（生成器失去「零漂移」保证） | 8.1 黄金测试 + §4 的「共用 boundary_value / labelled」保证 |
| simpleeval 性能（n=787 × 6+ ops × 4 规则） | 低 | 低（<1s/record） | 性能测试，必要时换回 `ast` |
| spec_json 行过大（critical-value 估计 ~12 KB，加 routing+smoke_probe 后 ~15 KB） | 中 | 中（DB 写慢、UI 渲染慢） | critical-value 估算基于现 5 个 gen_*.py 的代码体量（fields=10 + tier_windows=3 tier × 4-6 fields + rules=3 + plan_targets 共 ~150 行 JSON）反推 ±20%。拆分 `generator` 为独立列（`generator_json`），与 `spec_json` 同版本化 — 见 §12 备选 |
| UI 子面板太多，单屏装不下 | 中 | 低 | 折叠面板 + 「Expand all」 |
| 删除 6 个 gen_*.py 后 run_matrix/服务集成某处漏改 | 中 | 高（CI 红） | 阶段 A 完成后跑完整 pipeline（generate → split → train smoke → eval） |
| knowledge-qa 的 `topics` 列表硬编码 12 条 | 低 | 低 | 仍走 DB（`distill.topics`），与 make_seeds 现有逻辑等价 |
| `kev.vertical._default_registry()` 改从 DB 派生后，原 `medical` 行业的 5 个 `Scenario` 与 hardcoded 不完全一致（顺序 / `note` 文案差） | 中 | 中（5 个部署的行为可能漂移） | `tests/test_routing_sync.py` 锁住 DB 派生 registry 与原 hardcoded registry 顺序、文案一致；迁移期间仍允许 `_OVERRIDE` 用 JSON 覆盖 |
| `SMOKE_PROBES` 从 DB 派生后，每个 spec 必须有 `smoke_probe` 字段——首次迁移要补 6 份 spec | 中 | 低（漏一个 spec 则 deploy 阶段 `KevError: scenario X missing smoke_probe`） | `_backfill_specs` 同步回填：从 `stages/deploy.py` 原硬编码的 5 例直接拷到 `docs/medical/specs/*.json`；icd-coding 第一次迁移不要求有 `smoke_probe`（先标缺，跑 deploy 时跳过） |
| `template.yaml.j2` 渲染出的 yaml 与原 5 份 yaml 不一致（pipeline 顺序 / 字段名） | 低 | 中（distill 行为漂移） | `make_seeds config --scenario inquiry --diff /configs/inquiry.yaml` 模式：渲染后与原 yaml diff，仅在 diff 为空时退出 0 |
| `kev.vertical` 启动时调 `sync_registry()` 阻塞主线程（DB IO） | 低 | 低 | 编排服务启动一次即可，< 100ms；后续 routing 变更需要重启服务（已声明在非目标中） |

## 12. 备选方案（被否，但留档）

### A. `generator_json` 独立列

若 `spec_json` 体积大到影响 UI 性能（critical-value 估计 12 KB，包含 5 个 categories × 多 tier 的 tier_windows），可拆为：

```sql
ALTER TABLE scenarios ADD COLUMN generator_json TEXT;
```

`spec_json` 仅含 spec body；`generator_json` 含 `generator` + `distill`。两个 JSON 各自版本化（`scenario_generator_history` 复刻 `scenario_spec_history` 的 20 版清理逻辑）。代价：DB migration 增加 1 个表 + 1 个迁移函数、UI 要分两次保存、`db.write_spec_file` 要扩。**本设计先不拆，等 UI 实测加载 >100ms 再做**。

### B. 规则用 JSON Logic 而非 simpleeval

`json-logic-py` 是 JSON Logic 标准的 Python 实现。优点是纯 JSON、UI 直接渲染。缺点是「min/max/any/all」都要查表写规则，跨场景的复用比 simpleeval 难，且没有现成算子市场。**simpleeval 允许写一行 `any_outside_critical(state)`，JSON Logic 要写成 `{"reduce": [{"var": "fields"}, {"==": [{"call": "outside", ...}]}]}`**。simpleeval 胜在表达力。

### C. 把 `generator` 拆成单独 Python 子包

每个场景一个 `gen_<slug>.py` 写「fields / rules」，引擎仅做 driver。**用户已选「彻底删除 6 个 gen_*.py」**，否决。

## 13. 后续（out of scope）

- **跨域模板**：把 generator 抽到金融、法律领域（spec name + category 切换）
- **Generator 模板市场**：社区贡献 generator 配置
- **自动回归门**：CI 在每个 PR 跑 `engine --n 787 --seed 0` 黄金对比

## 14. 验收

本设计被认为完成的标准：

- [ ] §6.4 依赖加进 `pyproject.toml`
- [ ] §9「新增」列表 23 个文件全部存在
- [ ] §9「删除」列表 18 个文件 / 函数 / 常量全部不存在
- [ ] §8.1 6 个 `test_*_byte_for_byte` 全绿
- [ ] §8.2 3 个 API 测试全绿
- [ ] §8.2 增 2 个：`test_routing_sync`（DB 派生 registry = 原 hardcoded）、`test_smoke_probes`（`db.list_smoke_probes()` 返回 5 例 = 原 `SMOKE_PROBES`）
- [ ] `python -m kev.console.generators.engine --scenario critical-value --n 787 --out /tmp/x.jsonl --seed 0` 与 `data/critical-value.jsonl` diff 为空
- [ ] playground UI 在 `/console/scenarios#generator/critical-value` 渲染、编辑、保存 6 子面板（Fields / Rules / Augmentation+Plan / Distill / Routing / Smoke Probe）工作
- [ ] 蒸馏路径 `python -m kev.console.distill.make_seeds --all --n 500 --out-dir /tmp/seeds` 产 5 份 `*.seed.jsonl` + `*.state.jsonl` + 5 份 `configs/<slug>.yaml`，与 `data/seeds/` 既有产物 diff 仅在 system_prompt 文案
- [ ] `python -m kev.console.distill.make_seeds config --scenario inquiry --out-dir /tmp/cfg` 产 yaml 与 `kev/console/distill/configs/inquiry.yaml` diff 为空
- [ ] `python -m kev.console.smoke --from-db --scenario critical-value` 跑出与原 `stages/deploy.SMOKE_PROBES[0]` 同样的 state + questions
- [ ] `kev.vertical.INDUSTRIES`（启动后）与原 `_default_registry()` 顺序、`Scenario(risk, human_review, evidence_question, note)` 一致
- [ ] 6 份 `docs/medical/specs/*.json` 都补了 `routing` 与 `smoke_probe` 字段
