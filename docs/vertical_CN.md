<p align="center">
  <a href="./vertical_CN.md"><img alt="中文" src="https://img.shields.io/badge/%E4%B8%AD%E6%96%87-orange?style=for-the-badge"></a>
  <a href="./vertical.md"><img alt="English" src="https://img.shields.io/badge/English-blue?style=for-the-badge"></a>
</p>

# 多行业分层决策控制系统 · 设计方案 Spec

[English](./vertical.md) · 实现层：[`kev/vertical.py`](../kev/vertical.py) · 测试层：[`tests/test_vertical.py`](../tests/test_vertical.py) · 上层方案：[`sft-medical_CN.md`](./sft-medical_CN.md)

`kev/vertical.py` + `tests/test_vertical.py` 已在本地实现并通过 **44 项测试**（真实 peft 多 adapter 语义已验证）。
本 spec 记录**完整控制平面**（共享基座 + 行业 LoRA 池 + 二输入风险路由 + 部署形态）的设计，供评审与签字，
之后再实现服务层（`/v1/vertical` 端点、Modal 网关、Next.js 控制台）。

写作语言：中文正文（对齐 `docs/sft-medical_CN.md` 的 house style），关键契约与代码引用用英文。

---

## 1. 状态：先读这一节

诚实划分。已验证的事引向代码与测试，未验证的事承认依赖未到的环境。

### 1.1 已实现且已在本地验证

| 项目 | 证据 |
| --- | --- |
| 风险分层表 | `RISK_FLOOR = {"low": "8b", "medium": "8b", "high": "4b", "critical": "4b"}`；5 行业 × 11 场景在 `kev.vertical._medical/_finance/_legal/_education/_support` 内 |
| 路由五规则 | `Router.plan` + `Router.decide`：`unknown > forced > scenario-cutoff > risk-floor > threshold-escalate` |
| 阈值书 | `ThresholdBook.from_results({"<scenario>": {"<size>": result.json}})` 直接构造无常量 `Router`；`Adapter.from_result` 缺 selective 块即拒收 |
| 共享基座 + 多 adapter 池 | `AdapterPool`：unmerged peft（`set_adapter(inference_mode=True)`）swap + per-industry head 切换；骨架权重**未被任何 swap 改写**（`test_the_pool_swaps_adapters_and_heads_without_touching_the_backbone`） |
| 家族隔离 | `IndustryRegistry.families()` 给出 `(base, revision, head_dim, lora)` 元组集合；`AdapterPool` 跨家族构造抛 `AdapterConflict` |
| 升级报告 | `escalation_report(book, rows, industry)` 拆出 `answered` 与 `escalated` 两组的 n / accuracy / share，外加 `recall_of_errors_caught` |
| 失败方向 | 未知场景 / 无阈值 / unmerged 模型 → fail safe 至 4B；`test_a_low_risk_scenario_with_no_measurement_escalates_rather_than_guessing` 锁住这条 |
| 全测试套件 | `tests/test_vertical.py` **44 passed**（CPU 端 peft 真实加载，无 GPU、无网络） |

### 1.2 已实现但**未**验证 —— 没有真实环境可用

| 项目 | 缺什么 |
| --- | --- |
| **任何 Adapter 都没在真实行业数据上训练过** | `kev.vertical.INDUSTRIES.adapters()` 在 `test_the_built_in_registry_has_all_five_industries_and_no_adapters` 中**显式断言为空** —— 这是上线日应有的状态。 |
| **没有 Modal 服务** | `modal_app.py` 的 `vertical_serve` / 网关尚未编写；本文 §7 的部署形态是设计意图，不是已部署形态。 |
| **没有 Web 控制台** | 医生复核队列的 Next.js 页面不存在。 |
| **没有真实路由流量** | 所以 `escalation_report` 的两组数字均为空 —— 没有 dev rows.jsonl 可喂。 |
| **`/v1/vertical` 端点未实现** | 当前 `/v1/systemone` 不读 `industry` / `scenario`；spec §7 的 API 形状尚未编码。 |
| **27B/9B 尚未在池中实测** | `SIZES = ("8b", "4b")` 是当前已发布家族的两个最小尺寸；9B / 27B 的路由语义需在二次评审时确认（详见 §3.3 与 §8）。 |

### 1.3 上线前需要评审的未决项

| 项 | 评审要点 | 缺了会怎样 |
| --- | --- | --- |
| 五个行业的 risk 分层 | 临床 / 合规人员需对 `medical/icd-coding`（high）、`support/identity-release`（high）等逐条签字 | 一个高风险场景错标为 `medium` 即可让 0.8B 拿到决策权 |
| `Scenario.escalation_cutoff` 默认值 | 何时不设、由谁设、设多少 | 一个 strict 场景没设 cutoff 会被 router 视为与 fitted 阈值等价 |
| 双端点的"谁先答"语义 | 当 `forced=4b` 而 `decide()` 收到 0.8B probs 时如何记日志（当前 `decide` 在 `size != SMALL` 时不读 confidence） | 审计里漏掉一次「绕过升级」的 0.8B 答案 |
| 9B / 27B 是否进入 SIZES | 路由 ladder 的中间档是否需要 | 一次只升一档的语义会被打破 |

---

## 2. 这是什么 · 与 `kev/vertical.py` 的关系

两层结构，遵循 `AGENTS.md` 的 "one canonical home" 约定：

| 层 | 路径 | 角色 |
| --- | --- | --- |
| **设计 Spec**（本文） | `docs/vertical.md`（EN） + `docs/vertical_CN.md`（CN） | 叙述层：为什么这样设计、哪些已验证、哪些没有、上线前还差什么 |
| **实现层** | [`kev/vertical.py`](../kev/vertical.py) | 注册表、风险路由、阈值书、adapter 池。`import` 自 `kev.serve`（PR2）和 Modal 网关（PR3），`kev.serve` 本身**不动** |
| **测试层** | [`tests/test_vertical.py`](../tests/test_vertical.py) | 44 项测试：风险表、规则、阈值、池（真实 peft 加载）、家族隔离、JSON round-trip |

**两个层之间的契约**：`Router.plan` / `Router.decide` / `Router.route` / `AdapterPool.load|use|restore` 五个调用点。
修改这五个调用点就修改了路由层；其余都是数据（registry.json / ThresholdBook）。

读本文以决定**是否**做与**怎么做**；到 `kev/vertical.py` 去看**怎么执行**。

### 2.1 一个行业 = 一个 adapter + 一个 head + 一个 temperature

这是整套控制平面的基础事实。一个 vertical Kev 部署的"模型"**不是**新模型，而是：

1. **一个已发布 checkpoint**（`jaredpalmer/kev-0.8b` 或 `kev-4b`），其 LoRA 适配器被替换为该行业的 delta。
2. **一个该行业训练出的 pointer head**（写进 `head.pt` 的 `head` 张量字典）。
3. **一个在该行业 calibration 行上拟合的 temperature**（写进 `head.pt["temperature"]`）。

三者一起是 `Adapter`（`kev.vertical.Adapter`）。`temperature` 与 `confidence_cutoff` **不能手工填** —— `Adapter.from_result` 拒绝一个缺 selective 块的 result.json（`test_adapters_take_their_temperature_and_cutoff_from_a_result`）。

---

## 3. 模型组织：共享基座 + 行业 adapter

### 3.1 四层继承

```
Qwen/Qwen3.5-0.8B-Base（冻结）      Qwen/Qwen3.5-4B-Base（冻结）
  └─ jaredpalmer/kev-0.8b              └─ jaredpalmer/kev-4b
     T=2.35（公开数据）                  T=2.41
        └─ <industry>-<scenario>-8b-v1       └─ <industry>-<scenario>-4b-v1
           行业 delta；head.pt                行业 delta；head.pt
           含 T 与 fitted cutoff              含 T 与 fitted cutoff
```

`kev.vertical.Adapter` 的 `name` 是 `<industry>/<scenario>/<size>`，例如 `medical/critical-value/4b`。
同一 size 的多个行业 adapter **共享一个已加载的 backbone**：`kev.checkpoint.Checkpoint.load` 一次，
`PeftModel.load_adapter` N 次。

### 3.2 为什么是 unmerged peft，不是 merged

`AdapterPool.use(key)` 调用 `lm.set_adapter(name, inference_mode=True)`。这条路：

- **不动骨架权重**。`test_the_pool_swaps_adapters_and_heads_without_touching_the_backbone` 在 swap 前后
  对骨架 `named_parameters()` 做 `torch.equal` 比对，全部为真。
- **不动 head**。每个 adapter 自带 head state dict，swap 时一并 `load_state_dict`，并把 `temperature` 写回
  `PointerHead.temperature`。
- **无 per-request 四舍五入**。`LoadOptions.merge=True` 走 `W += delta` 路径，对每个 request 重写骨架
  —— 等同于把全量 LoRA 在内存里反复重算，引入 bf16 舍入。
- **代价**：每个 forward 多一次 peft 路由（"哪几个 A·B 矩阵参与"）的簿记。0.8B / 4B 端到端是**带宽受限
  不是 launch 受限**（`runs/serve-*`），多出来的簿记不到 5%。

### 3.3 两个 backbone family 的隔离

`IndustryRegistry.families()` 给出 `(base, base_revision, head_dim, lora)` 元组集合，**一个尺寸 = 一个 family**。
`AdapterPool._check_families` 拒绝跨 family 的注册（`test_the_pool_refuses_a_backbone_the_adapters_were_not_trained_on`）。

含义：

- 0.8B 的 `medical/critical-value` 与 0.8B 的 `finance/fraud-detection` **可以**共享一个 `AdapterPool`。
- 0.8B 的 `medical/critical-value` 与 4B 的 `medical/critical-value` **不能**共享 —— 需要两个加载好的
  backbone、两个 `AdapterPool`。
- 同一部署里既跑 0.8B 又跑 4B 的网关必须持有**两个 pool**（PR3 的 Modal 网关实现），按 `scenario.risk` 路由。

`SIZES = ("8b", "4b")` 是当前已发布家族的两个尺寸；引入 9B / 27B **必须**插在中间（`SIZES` 是一个
顺序而不是集合），不能 append，否则 `RISK_FLOOR["high"] == SIZES[-1]` 静默失效
（`test_the_size_ladder_is_small_to_large`）。

---

## 4. 路由规则

### 4.1 两个输入，一个输出

```
        ┌──────────────────────────┐
        │ Scenario.risk（场景表）   │  ← 可审计、可签字；不读 state
        └──────────┬───────────────┘
                   │ floor
        ┌──────────▼───────────────┐    ┌────────────────────────────┐
        │ Router.plan / decide     │───▶│  Decision(size, escalate)  │
        └──────────┬───────────────┘    └────────────────────────────┘
                   │ threshold
        ┌──────────▼───────────────┐
        │ 0.8B 自身置信度           │  ← 来自 selective development 行
        └──────────────────────────┘
```

- **场景表 risk** 是下限。`high` 永远从 4B 开始；一个高风险场景的 0.8B 答案**永远不被信任**。
- **0.8B 自身置信度**是升级信号。低于阈值 → 同一条记录被送到 4B 重答。

两路输入都 **fail safe**：

| 输入 | 缺失/异常时的行为 | 拒收条件 |
| --- | --- | --- |
| 未知 industry 或 scenario | 直送 4B，reason = `unregistered scenario` | `KeyError` 路径被 `UnknownIndustry` / `UnknownScenario` 取代 |
| `forced` 尺寸不合法 | 抛 `ValueError`，不上线 | `forced` 必须在 `SIZES` 内 |
| `Adapter` 缺 `confidence_cutoff` | 升级至 4B，reason = `no fitted threshold` | `Adapter.from_result` 缺 selective 块即拒收 |
| 路由 ladder 上没有"降级"方向 | 永远只升不降 | 4B 答案永远不被回退到 0.8B |

### 4.2 五个规则，按应用顺序

| # | 规则 | 理由 | 测试 |
| --- | --- | --- | --- |
| 1 | 未知 industry / scenario → 4B + `unregistered scenario` | 4B 兜底比 404 好；caller 看到 reason 即可修正 | `test_unknown_industry_and_scenario_route_to_the_large_model_with_a_reason` |
| 2 | `forced` size 优先（reason = `caller forced a size`） | 复审员用 4B 重新核对、或 caller 只有 1 个尺寸；记录 forced 以示审计 | `test_a_forced_size_overrides_the_table_and_says_it_did` |
| 3 | `Scenario.escalation_cutoff` 覆盖 fitted 阈值 | 临床对某场景有更严的 bar；可设 0.95 替代 0.82 | `test_a_scenario_can_demand_a_stricter_bar_than_its_own_development_set` |
| 4 | `RISK_FLOOR[scenario.risk]`：`high` / `critical` → 4B 起步 | 0.8B 的不确定性不是危急值缺席的证据 | `test_high_risk_scenarios_never_start_on_the_small_model` |
| 5 | `low` / `medium` + 有阈值 → 0.8B 起步；conf < 阈值 → 升级 | 整套成本论：大多数低风险流量 0.8B 一次答完 | `test_low_risk_scenarios_start_small_with_the_fitted_threshold` + `test_unsure_small_answers_escalate_to_the_large_model` |

中间插入的关键不变量：

- **不读 state。** `plan(record)` 把 `record` 传进来但**不读**。`test_the_router_never_inspects_the_state`
  用一个"明显该让 0.8B 答"的 state 验证路由器仍把它送到 4B —— 因为 scenario 本身是 `high`。
- **每条记录的所有问题共享一次升级判定。** 升级信号是 `min(max(p) for p in probs)`，一个不确定的问题
  升级整条。`test_one_unsure_question_escalates_the_whole_record` 锁住这条。
- **escalate 仅对 0.8B 生效。** 4B 不会被回退。`test_escalation_only_applies_to_the_small_model` 验证
  即便传 `probs`，4B 的决策也不带 `observed`。

### 4.3 `Decision` 字段语义

```python
@dataclass(frozen=True)
class Decision:
    industry: str
    scenario: str
    size: str                # 当前请求**应该**或**已经**由哪个尺寸答
    reason: str              # audit 串（REASON_*）
    review: bool = True      # 是否需要人工复核
    escalate: bool = False   # 0.8B 答了，但需要 4B 重答
    escalate_to: str | None = None   # 升级目标，仅 escalate=True 时填
    threshold: float | None = None   # 实际生效的阈值（含来源）
    observed: float | None = None    # 0.8B 的最小 max(p)
    base: str | None = None          # 该决策所用 adapter 的基座
    adapter: str | None = None       # 实际生效的 adapter 名
    note: str = ""                   # 自由审计备注
```

读法：

- 来自 `plan()`：没有模型跑过。`size` 是**必须**答的尺寸；`escalate` 仅在 fail-safe 时为 True。
- 来自 `decide()`：0.8B 已答。`size` 是**已经**答的尺寸，`escalate` 决定 gateway 是否再向 `escalate_to`
  重发同一条记录。

`test_decisions_serialise_for_the_audit_log` 锁住字段集合，让日志解析器对重构免疫。

---

## 5. 阈值书

`ThresholdBook` 是 router 与训练管线之间的桥。**模块内没有 0.82、0.86 之类的常量** —— 一切来自
训练 run 的 `result.json`，因此一个阈值可追溯到具体的 development 切片，可被评审独立核对。

### 5.1 从 result.json 到 router

```python
book = ThresholdBook.from_results(
    {"critical-value": {"8b": result_8b, "4b": result_4b}, ...},
    industry="medical",
)
router = book.router(registry)        # 没有任何常数进入 router
```

`Adapter.from_result` 从 result.json 取两样东西：

| 字段 | 来源 | 缺了会怎样 |
| --- | --- | --- |
| `temperature` | `result.json["temperature"]` | 拒收：阈值不可手动填 |
| `confidence_cutoff` | `result.json["development"]["calibrated"]["selective"]["0.8"]["confidence_cutoff"]` | 拒收：0.0 = 全升级、1.0 = 全不升，两者都不是测量 |

`SELECTIVE_FRACTION = "0.8"` 是 `kev.metrics.metrics` 默认扫描的两个值（0.5, 0.8）里高覆盖那一端 —
`test_the_cutoff_prefers_the_calibrated_report` 锁住"已发布 endpoints 的校准报告优先于 raw logits"。

### 5.2 三条来源优先级

`Router.cutoff(scenario, adapter)` 在三处间按序取阈值：

1. **`Scenario.escalation_cutoff`**（scenario 显式设定）—— 仅当更严时用；模块没有路径能放宽它
2. **`Adapter.confidence_cutoff`**（run 自带）—— 默认来源
3. **`Router.thresholds` 字典**（部署级显式覆盖）—— 兜底

`reason` 字段会把来源写进 audit 串，例如 `low confidence on the small model (threshold 0.82 from adapter)`。

### 5.3 上线前必须看的两个数

`escalation_report(book, rows_by_scenario, industry)` 给出每个场景在已打分行上的拆分：

```python
{
  "critical-value": {
    "n": 1000, "cutoff": 0.82, "temperature": 2.35,
    "answered":   {"n": 800, "accuracy": 0.94, "share": 0.80},
    "escalated":  {"n": 200, "accuracy": 0.61, "share": 0.20},
    "recall_of_errors_caught": 0.83,
  },
  ...
}
```

两个**必须**的数：

1. **`answered.accuracy`** —— 0.8B 被允许答的那组的准确率。是安全论的核心。
2. **`recall_of_errors_caught`** —— 升级规则把所有错误答中的多少抓出来。1.0 = 不错漏，0.5 = 错过一半。

一个 router **answered.accuracy 高但 recall_of_errors_caught 低** = 危险：0.8B 在它答的那组里准确，
但答的是简单题，错题都漏到 escalated 集外面去。一个 **answered.share 0.95 + recall 0.50** 的部署
基本上没在路由，0.8B 答了所有题，错的也答了。

`test_the_escalation_report_separates_the_answered_set_from_the_escalated_one` 锁住两组的拆分语义。

---

## 6. 数据契约

### 6.1 `registry.json` 字段表

```jsonc
{
  "industries": {
    "medical": {
      "title": "医疗健康 / Healthcare",
      "note": "危急值、用药审核、护理质控的标签可规则派生；病历编码与导诊需要医学知识推断。",
      "scenarios": {
        "critical-value": {
          "risk": "high",                  // low / medium / high / critical
          "human_review": true,            // 答案是否在处置前必须人工看
          "evidence_question": "evidence_sufficient",   // 可选：标识"证据不足"的 question key
          "escalation_cutoff": null,       // 可选：覆盖 fitted 阈值的更严 bar
          "note": "漏报危急值 ≫ 误报：低置信必须升级 4B 并强制转人工，不取 argmax 自动处置。"
        },
        ...
      },
      "adapters": {                       // 训练完才填；当前内置 registry 为空
        "critical-value/8b": { "industry": "medical", "scenario": "critical-value", "size": "8b",
                                "run": "runs/critical-value-8b-v1", "temperature": 2.35,
                                "confidence_cutoff": 0.82, "base": "jaredpalmer/kev-0.8b", ... },
        "critical-value/4b": { ..., "base": "jaredpalmer/kev-4b", ... }
      }
    },
    ...
  }
}
```

字段约束（构造时校验）：

| 字段 | 取值 | 违反 |
| --- | --- | --- |
| `risk` | `low` / `medium` / `high` / `critical` | 抛 `ValueError` |
| `human_review` | bool | 缺省 True（保守） |
| `confidence_cutoff` | `(0, 1]` | 0.0 / 1.5 / -0.1 抛 `ValueError` |
| `temperature` | `> 0` | 0.0 抛 `ValueError` |
| `size` | `SIZES` 子集 | 抛 `ValueError` |
| `base` × `AdapterPool.base` | 必须相等 | `AdapterConflict` |
| duplicate industry / scenario name | 不允许 | 抛 `ValueError` |
| adapter 挂在未声明的 scenario 上 | 不允许 | `UnknownScenario` |

`test_a_registry_cannot_hold_two_industries_or_two_scenarios_of_one_name` 锁住命名空间；JSON round-trip
不丢失字段由 `test_the_registry_round_trips_through_its_json` 锁住。

### 6.2 11 场景 × 5 行业风险分层表

这是上线日评审签字的对象。已由 `kev.vertical._medical/_finance/_legal/_education/_support` 编码，
并被 `test_shipped_scenarios_carry_the_risk_the_medical_package_measured` 表中的 10 项参数化锁住。

| 行业 | 场景 | risk | human_review | 0.8B 轨? | 理由 |
| --- | --- | --- | --- | --- | --- |
| medical | critical-value | **high** | true | 双轨但 0.8B 只在低置信升级后被 4B 覆盖 | 漏报 ≫ 误报；标签可规则派生但漏报不可恢复 |
| medical | medication-review | low | true | ✓ | 规则封闭；0.8B 主力，仍需药师复核 |
| medical | nursing-quality | low | true | ✓ | 检查表逐项可判 |
| medical | triage | **high** | true | 主力 4B，0.8B 作为能力不足的实证对照 | 科室归属语义丰富，0.8B 弱 |
| medical | icd-coding | **high** | true | **仅 4B**（router 拒绝 0.8B 注册） | 长文本 + 大标签空间 + 需医学知识 |
| finance | credit-review | low | true | ✓ | 准入规则可穷举 |
| finance | fraud-detection | **high** | true | 主力 4B | 跨单据推理；命中即人工 |
| finance | aml-alerting | **high** | true | 主力 4B | 名单匹配走规则，可疑交易判定走模型 |
| finance | compliance-check | low | true | ✓ | 检查表逐条对照 |
| legal | contract-review | **high** | true | 主力 4B | 条款语义与上下文强相关；法务终审 |
| legal | clause-classification | low | true | ✓ | 有限标签集 |
| legal | compliance-screening | **high** | true | 主力 4B | 漏检代价高 |
| education | grading | low | false | ✓ | 评分细则封闭 |
| education | knowledge-diagnosis | medium | false | ✓ | 跨题推理；4B 更稳 |
| education | admission-screening | **high** | true | 主力 4B | 取舍不可自动处置 |
| support | ticket-triage | low | false | ✓ | 工单分类、优先级、情绪识别 |
| support | escalation-detection | low | false | ✓ | 选项集小；注 0.8B 工具路由弱（When2Call 0.133） |
| support | identity-release | **high** | true | 主力 4B | 放行错误不可撤回 |

`test_every_industry_declares_at_least_one_low_and_one_high_risk_scenario` 锁住"每个行业至少一个 low + 一个 high"
—— 单层行业是误用，要么永远不升档、要么永远升档。
`test_medical_keeps_human_review_on_every_scenario` 锁住医疗 5 个场景全部 `human_review=True`。

### 6.3 与 `docs/medical/specs/` 的关系

`docs/medical/specs/*.json` 定义**状态 schema 与问题标签体系**（5 场景 × questions）。它**不**包含
`risk` 或 `confidence_cutoff` —— 那些属于控制平面，住在 `registry.json`。

复用模式（其他行业参考用）：

```
docs/
  medical/
    specs/                  ← state schema（已有 5 个）
    generators/             ← 程序化生成器（参考）
  finance/
    specs/                  ← 未来添加：credit-review / fraud-detection / ...
    generators/             ← 未来添加
  ...
  registry.json             ← 风险分层、adapters；本文控制平面的 source of truth
```

行业 spec 与生成器**按 `assets/workload.example.json` 契约另开 PR**（不在本 PR）。

---

## 7. 部署形态

### 7.1 API 形状

继承已有 `/v1/systemone` 的 TypeSafe 契约，并新增请求头与一个轻量端点：

```http
POST /v1/systemone
Headers:
  x-kev-industry: medical
  x-kev-scenario: critical-value
  x-kev-forced-size: 4b                # 可选；audit 显式 forced
  Authorization: Bearer <KEY>          # 部署时可设
Body: <TypeSafe request>               # 与现有 /v1/systemone 相同
Response: <TypeSafe response> + 路由元数据
  {
    "answers": [...],
    "route": {
      "industry": "medical", "scenario": "critical-value",
      "size": "4b", "reason": "low confidence on the small model",
      "escalate": true, "escalate_to": "4b",
      "threshold": 0.82, "observed": 0.61,
      "base": "jaredpalmer/kev-0.8b", "adapter": "medical/critical-value/8b"
    },
    "latency_ms": 312,
    ...
  }
```

- 路由元数据是 response 的**显式部分**而非日志字段 —— 临床人员能在不查日志的情况下从 response 看出
  "这个答案是 0.8B 给的，置信度 0.61，升级到 4B"。
- 不引入新 `Authorization`：复用 `/v1/systemone` 的 bearer 机制。`KEV_API_KEY` 启用时全站鉴权。

### 7.2 端点分层

| 端点 | 角色 | 何时加 |
| --- | --- | --- |
| `POST /v1/systemone`（已存在） | **逐条问**。读 `x-kev-industry` / `x-kev-scenario` 头决定走 router 路径 | PR2：把 router 嵌入 model thread，无需改 endpoint 形状 |
| `POST /v1/vertical`（新） | **批量 + 路由元数据**。N 条 records → 路由计划 + 0.8B answers + 升级清单 | PR3：网关在 Modal 端，SDK 同步消费 |
| `GET /v1/industries`（新） | 列出本部署服务的 industries / scenarios / risk / available sizes | PR3：网关元信息 |

### 7.3 Web 控制台（医生复核队列）

Next.js 应用（与 `playground/` 同底座，但独立路由 `/vertical/console`）：

- **主界面**：pending review 列表，按 industry / scenario 过滤，显示 state 前 200 字符、问题、4B 答案、
  0.8B 答案（若有）、路由 reason。
- **决策动作**：Approve / Override / Escalate to senior，三类写回审计表。
- **回看**：同一 record 的所有历史决策与人工标注的 diff。
- **过滤器**：`only-escalated` / `only-conflict` / `only-low-confidence`，对应 §5.3 的三种警戒场景。

PR4 单独交付。控制台**不**直接调模型；只调内部 `decisions` API（与 gateway 同一容器内）。

### 7.4 Modal 云端执行（用户选项 B）

部署拓扑：

```
[Next.js console]                [TypeSafe SDK]              [curl / Postman]
       │                              │                              │
       │ HTTPS                        │ HTTPS                        │ HTTPS
       ▼                              ▼                              ▼
   ┌──────────────────────────────────────────────────────────────────────┐
   │  Modal gateway container (kev-modal-vertical, app name isolated)     │
   │  - /v1/systemone + x-kev-* 头解析                                   │
   │  - 调 kev.vertical.Router.plan/decide                                │
   │  - 调 kev.vertical.ThresholdBook（从 result.json 池化）              │
   │  - 持有 2 个 kev.vertical.AdapterPool（0.8B + 4B）                  │
   └─────────────┬────────────────────────────────────┬─────────────────┘
                 │ invoke                             │ invoke
                 ▼                                    ▼
        ┌────────────────────┐                ┌────────────────────┐
        │ kev.serve.Server   │                │ kev.serve.Server   │
        │ jaredpalmer/kev-8b │                │ jaredpalmer/kev-4b │
        │ kev-0.8b (LoRA)    │                │ kev-4b (LoRA)      │
        │ 64 concurrent      │                │ 64 concurrent      │
        │ CUDA graphs        │                │ CUDA graphs        │
        └────────────────────┘                └────────────────────┘
```

每个容器一个 `Router` 实例 + 两个 `AdapterPool`（按 `families()` 决定）。`KEV_FLASH=1` 启用 Modal
的 `experimental.http_server`；两个 Server 通过 `kev.vertical.AdapterPool.use(key)` 切换 adapter，
**不**重启容器、**不**重写骨架权重（`test_the_pool_swaps_adapters_and_heads_without_touching_the_backbone`）。

隔离：`KEV_APP_NAME=kev-vertical-<env>`，`worker_environment` 传播 app/GPU/secret 设置（防 Modal
依赖计数启动失败）；secret 值仍由 Modal Secrets 管。

---

## 8. 里程碑与风险

四个 PR，每个有验收门槛与回滚手段。

| PR | 范围 | 验收门槛 | 回滚 |
| --- | --- | --- | --- |
| **PR1：本 spec + 已完成** | `kev/vertical.py` + `tests/test_vertical.py` + `docs/vertical*.md` | 44 测试绿；`test_conventions.py` 不被破坏；`docs/vertical_CN.md` / `vertical.md` 包内链接可解析 | 不动 `kev.serve` / `kev.api`；spec 落进 git 即为里程碑 |
| **PR2：`/v1/systemone` 接入 router** | `kev.serve.Server` 启动时构造 `Router`（从 `kev.vertical.industries()`），读 `x-kev-industry` / `x-kev-scenario` 头；model thread 在 answer 前调 `Router.decide`，根据 `Decision.size` 选 `AdapterPool` | 新增 API 测试：`POST /v1/systemone` 不带头 → 走默认 4B（fail safe）；带 unknown industry → 4B + reason；带 known low-risk scenario → 0.8B 一次；低置信 → 4B 升级 | 改回 `kev.serve` 不读 router 的 commit；老 endpoint 行为不变 |
| **PR3：Modal 网关 + 双尺寸路由** | `modal_app.vertical_serve`：两个 `kev.serve.Server`（0.8B + 4B）、`/v1/vertical` 端点、批量路由、bearer 鉴权、`KEV_APP_NAME=kev-vertical-<env>` 隔离 | 64 客户端下 p50 延迟 < 350 ms（与 `runs/grouping-4b-h100` 的 4B 单一基线相当）；fp32 parity 测试通过；`scripts/serving_bench.py --flags=--isolation` 不退化 | `modal app rollback` 退到上一版本；`/v1/systemone` 单尺寸路径保留 |
| **PR4：Web 控制台** | Next.js 路由 `/vertical/console`：pending review 列表、Approve/Override/Escalate、过滤器、回看 | E2E：从 console Approve 一条后，gateway 的下一次同 record 请求回显人工标注；Console 与 gateway 鉴权共享 | console 独立部署，回滚不影响 gateway |

### 8.1 跨 PR 的不变约束

- **永远不动 `kev.serve` 的 `probs_one` 路径**。`AdapterPool.use` 是其唯一新增的回调点。
- **永远不写 router 常量**。任何阈值改动必须经过 `Adapter.from_result`（`test_adapters_take_their_temperature_and_cutoff_from_a_result`）。
- **永远不读 state 做路由**。`plan(record)` 拿 record 但不读；`test_the_router_never_inspects_the_state` 锁住。
- **永远只升不降**。4B 答案不回退到 0.8B（`test_escalation_only_applies_to_the_small_model`）。
- **永远 fail safe**。未知 / 无阈值 / unmerged → 4B；无降级路径（`test_a_low_risk_scenario_with_no_measurement_escalates_rather_than_guessing`）。

### 8.2 与现有规则 / 学到的教训的一致性

- 与 `docs/sft-medical_CN.md` 一致：医疗 5 场景 risk 分层在 `test_shipped_scenarios_carry_the_risk_the_medical_package_measured`
  中由 10 项参数化锁住，重新分层会让该测试失败。
- 与 `AGENTS.md` 的 "one canonical home" 一致：`kev.vertical` 是 router / registry / pool 的唯一归属；
  `test_conventions.py` 不被破坏意味着无第二处实现。
- 与 "fp32-exact" 一致：路由不影响 logits，§5.3 的两组数字来自 `kev.benchmark` 的标准 rows.json，不引入新度量。
- 与 `KEV_DATE_FACTS=1` 兼容：路由头不读 state，故日期预处理无需与 router 协调。
- 与 `kev.rounds.pool_conflicts` 一致：router 的阈值与 `kev.rounds` 的温度池互不干涉 —— 路由是 serving 期
  决策，温度池是评测期门控，两者关注的是不同的"哪条 development 行允许用来做什么"。

### 8.3 风险登记

| 风险 | 概率 | 影响 | 缓解 |
| --- | --- | --- | --- |
| 一个 0.8B adapter 的 head 被错误地换给 4B 请求 | 低 | 高（不同温度） | `test_the_pool_swaps_adapters_and_heads_without_touching_the_backbone` 锁 head 与温度一起切；`Pool.use` 在 `key not loaded` 时抛 `UnknownScenario` |
| 路由层未来引入对 state 的读 | 中 | 高（破坏审计） | `test_the_router_never_inspects_the_state` 是显式 fail；新 PR 必过此测试 |
| 9B / 27B 加入 SIZES 后 `RISK_FLOOR["high"]` 含义改变 | 中 | 中 | SIZES 是有序 tuple，append 而非 insert 在 `test_the_size_ladder_is_small_to_large` 中被显式禁止 |
| 行业 spec 与控制平面 spec 漂移 | 中 | 中（两表签名不一致） | `docs/medical/specs/*.json` 只存 schema；risk 永远只来自 `registry.json`；CI 加 link check |
| Modal 网关与 `kev.serve` 的 CUDA graphs 行为差异 | 低 | 中 | `AdapterPool` 不动 `kev.serve`；CUDA graphs 仍由 `kev.serve` 自己管；fp32 parity 走 `scripts/serving_bench.py` |
| `/v1/vertical` 批量端点被误用为全量重答 4B | 中 | 中（成本） | 路由元数据是 response 显式字段；`escalate` 为 false 时 SDK 不应再发 |

---

## 验收

- `docs/vertical_CN.md` / `docs/vertical.md` 落地，包内链接可解析。
- `tests/test_vertical.py` **44 项通过**；`tests/test_conventions.py` 不被破坏（已确认）。
- 决策规则表可被不读 Python 的评审独立核对 —— §4.2 的五规则 + §4.3 的 Decision 字段表完整覆盖 plan/decide 的全部
  输出。
- 与 `docs/sft-medical_CN.md` 的尺寸表、风险分层一致；5 行业 × 11 场景的 risk 分层由 44 项测试锁住。
- 不引入新代码；本 PR 是 spec 评审里程碑，PR2 / PR3 / PR4 另开。
