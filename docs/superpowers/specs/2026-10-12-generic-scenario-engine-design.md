# 通用场景生成引擎（B2）设计文档

- 日期：2026-10-12
- 状态：§7 的四个未决问题已于 2026-10-12 评审定案（含本轮新发现：D10 catalog、D11 双通道）；**PR1a 已完成**（退出判据与有意遗留见 §5.1），待 PR1b 开工
- 依据：`.superpowers/spike/b2-findings.md`（32 场景矩阵 + 仓库六份 fixture 探针 + 现存质量闸门审计 + simpleeval 能力实测）；
  本轮补充核对：fixture `generator.fields` 键分布统计、`state_key_probe.py`（spec 规则读的 state 键 vs legacy 实际给的 state 键）、
  `gen_triage.py`/`gen_diagnosis.py` 的表面构造与 `derive()`、`kev/api.py:49-55` 的 `render` 展平行为
- 作者：brainstorming + spike 会话产出

---

## 1. 背景与目标

`docs/medical/` 的六份场景 spec 里，真正生成数据的仍是六个手写模块（`gen_critical_value.py` 等）。
`kev.console.generators.engine` 是它们的 spec 驱动替代物：界面（`playground/` 的场景编辑器 + 三条 `generator/*` 路由）
点出一份 JSON spec，引擎按 spec 采样状态、跑规则打标签。

spike 的结论是这条路今天走不通，且**卡点与行业无关**：32 个新场景（金融/教育/科研/法律 × 7 种状态形状）里，
只有「≥6 个带 `normal` 区间 + 单侧 `critical` 的数值字段」这一种形状出得来记录（12/32），其余 20 个在采样阶段
`KeyError: 'normal'`；而出得来的 12 个里，通过仓库现存质量闸门（`tests/test_medical_generators.py:98`：
0 校验问题 + 每标签 ≥5% + 无 0 命中）的是 **0 个**。仓库自己的六份 fixture 同样跑不通：四份崩在同一行，
`critical-value` 出 60/60 条但 `is_critical≡True`，`record-summary` 不是合法 JSON。

本设计的目标：**让 spec 决定「状态长什么样、规则怎么算、标签怎么铺」，加一个新行业场景不改一行 Python。**

### 1.1 目标（可判定）

| # | 目标 | 判据 |
| --- | --- | --- |
| T1 | 八类字段都能采样 | spike 的 enum/bool/text/date/list 五类 20 个场景全部产出满 N 条；catalog 形状（diagnosis/triage 的症状池）不再需要 `normal` |
| T2 | 骨架由 spec 决定 | 任意场景的 `state` 里出现 spec 声明的键，`patient`/`labs` 不再是引擎产出 |
| T3 | 规则算得动 | arith/date/list 场景不再整批落兜底；4 个 arith 场景标签分布正确 |
| T4 | 静默失败归零 | 坏算子、坏键、异常表达式让 CI 红，而不是产出 30 条废数据 |
| T5 | 数据质量达标 | 目标场景通过现存质量闸门（每标签 ≥5%、无 0 命中），且 n=30/300/3000 分布漂移 <5 个百分点 |
| T6 | 自家 fixture 收编 | 六份 fixture 全部由 engine 跑通并通过 T5 判定，且 `render(state)` 与 legacy 产出的表面逐场景对齐（D11 的派生通道是这条成立的前提） |
| T7 | 零 Python | 新增 2 个 spike 里没出现过的场景，只提交 spec JSON 即通过全部闸门 |
| T8 | 存量不回归 | `tests/test_medical_generators.py` 在 PR1a–PR4 期间全绿（legacy 路径不动），且该文件被加进 `ci.yml`（今天不在 CI 上跑，见 §6 缺陷 4） |
| T9 | 标签不泄漏 | 任何场景的 `render(state)` 里都不出现标签属性名或其值（catalog 的 `urgency`/`red_flag`/`needs_test` 等），由 G8 机检 |

### 1.2 非目标

- 不在引擎里调用 LLM 生成状态或标签（标签必须来自规则，这是 0.8B 路线的前提）。
- 不改 `split_data` 的校验契约、不改记录的 `questions` 结构、不改模型编码/服务路径（`kev/model.py`、`kev/api.py` 的 `render` 签名不变）。
- 不做场景编辑器 UI（表单、LLM 起草、逐块接受）——那是界面轨，本设计只把它依赖的后端能力交付到位。
- 不做多场景合并数据集、不做数据增强算子库扩充（`evidence_drop` 语义通用化列为后续）。
- 不允许 spec 引用仓库外语料（D13）：text/enum 的取值只能来自 spec 内联池，保住确定性重放与「spec 是唯一真相源」。
- 不发明模板语言（D11）：state 表面一律用算子表达，规则与表面共用同一个求值器，不允许出现第二套解析。

---

## 2. 关键决策记录

### D1 字段类型：一期做满八类（含嵌套对象与候选项池）

`numeric | enum | bool | text | date | list | object | catalog`。决策：**一次做完**（分期见 PR1a/PR1b），因为六份 fixture 里
`diagnosis`（35 条症状池）、`triage`（58 条症状池）、`nursing-quality`（27 条检查项）本身就落在 catalog 与文本上
——只做前几类无法兑现 T6，而 T6 是唯一守着「生成数据没变坏」的资产。catalog 的完整定义在 D10。

- **兼容**：字段没有 `type` 键 = `numeric`，现有 spec 与 fixture 的数值字段一字不改仍然有效。
- `normal`/`critical` 从「所有字段必填」降级为「仅 `numeric` 有意义」——这是 20/32 场景崩溃的根因
  （`sampler.py:56` → `ops.py:106`）。数值字段的阈值界名不再固定为 `normal/critical`，改通用 `bounds`（D12）。

### D2 记录骨架由 spec 决定

字段声明里带落位路径，`make_record` 按路径写，不再拼 `patient/labs`（`sampler.py:89-95`）：

```json
{"name": "涉案金额", "type": "numeric", "unit": "万元", "decimals": 1,
 "normal": [1, 50], "critical": {"high": [[80, 1e9]]}, "category": "amount",
 "path": ["量刑情节", "涉案金额"]}
```

- 缺省 `path` = 顶层 `[name]`（多数场景不需要嵌套）。
- 引擎注入的辅助键改由 spec 声明：`"aux": {"missing_context": "dropped"}`，医疗场景的
  `ref_ranges_included` 变成一个普通 bool 字段。
- 最小对与 pair 路径同步去 `labs`（`pair.py:34-46`、`engine.py:184`），改用「被翻转字段的 path」。

### D3 记录里直接存 typed value

决策：**状态里存值本身**（float/int/bool/ISO date 字符串/list/dict），不再存 `"65.0 %"`。
这样 `state['负债比'] * 0.4 + state['使用率'] * 0.3 > 70` 这类规则天然可写，日期与列表规则也可写。

派生的三条必须一起做的约束：

1. **单位活在 spec，不活在数据**。渲染层 `kev.api.render` 对 int/float/bool/list/dict 已经能展平成 `key: value` 行，
   因此不需要新契约；但它不知道单位。新增一个 spec-aware 渲染声明 `spec.generator.render_units:
   "off" | "on"`。**缺省 `on`（2026-10-14 由 §5.3 的实测推翻原文的 `off`）**：渲染层补 `20000 元`，
   新场景想省单位要显式写 `off`。理由：已发布表面的默认就是「带单位」，缺省 `on` 让六份医疗 fixture 与
   矩阵里 36 个场景的记录表面**逐字节不变**，PR2a 的 diff 只落在「规则看到的值」上；缺省 `off` 则要靠给旧 spec
   逐个补 `on` 才能不漂表面，那是把「忘了写」变成「静默改掉已训 checkpoint 的 prompt」。**这是 T8 与 D3 之间唯一的桥。**
2. **date 用 ISO 字符串**（JSON 无日期类型）。收益：`kev/api.py::date_facts`（`--date_facts`）的正则已认
   `\d{4}-\d{2}-\d{2}`，时效类场景白拿现成的天数注入。
3. **bool 的渲染形态要固定**。`render(True)` 出 `True`，而 noul 标签集是 `"true"/"false"`。规则里写
   `bool_to_str(...)`（已在 ALLOWED）或在 spec 声明 `display`，二选一，禁止两边都行。

**D3 的两条查证修正**（写这份文档时我对表面的判断有错，实测后更正）：

- 复合显示（`BP 165/98 mmHg, HR 96 bpm, SpO2 94%`）**不是**由结构化字段拼的：它在 legacy 里是整条字符串常量池
  （`gen_triage.py:56`、`gen_diagnosis.py:72`、`gen_critical_value.py:52` 的 `VITALS`/`CONTEXTS`），血压在医疗场景里是个
  text 字段而非两个 numeric 字段。所以 `render_units` 只需做「单值 + 单位后缀」，不需要逐字段 display 模板。
- `unit: ""` 必须不产生尾随空格（`nursing-quality` 27 个字段的 unit 全为空），否则表面与 legacy 差一个空格，PR4 的对照报告全是噪声。

### D4 规则求值：换求值器 + 扩算子 + fail-loud + 静态校验

实测（`.superpowers/spike/simpleeval_probe.py`、`simpleeval_probe2.py`）给出了 DSL 的真实边界：

| DSL 能力 | 现在的 `SimpleEval` | 换 `EvalWithCompoundTypes` 并注册算子后 |
| --- | --- | --- |
| 生成器/列表/dict 推导（`all(p['e'] > 0 for p in ...)`） | ✗ FeatureNotAvailable | ✓ |
| 集合字面量 `x in {'合同','侵权'}` | ✗ | ✓ |
| `str` 方法（`startswith`、`split`）、三元、切片、链式下标 | ✓ | ✓ |
| `lambda`（`sorted(..., key=lambda ...)`） | ✗ | ✗（改用推导式或算子） |
| 日期相减取 `.days` | ✗（字符串相减 TypeError） | ✗ → 必须走算子 `days_between(a, b)` |

改造四件：

1. 引擎与 `rules.py::RuleEvaluator` 统一改用 `EvalWithCompoundTypes`，算子表 = 通用集
   （`float/int/str/lower/upper/sum/sorted/reversed/count/any/all/min/max/len/abs/round`）+ 派生集
   （`days_between/years_between/contains/matches_regex/near`）+ 现有 20 个医疗算子（不动，避免回归）。
2. **fail-loud**：`engine.py:84-93` 的两处 `except Exception: continue / pass` 改为记
   `(rule_index, rule_id, expr, type(exc), msg)` 后抛 `RuleError`，CLI 非零退出，`generator/validate` 路由原样返回该结构。
   兜底规则（`when: "True"`）命中率超阈值（缺省 0.6）单独告警——这是「静默全落一个标签」的最后一条可见路径。
3. **静态校验**（生成前，不跑采样）：解析每条 `when`/`then` 的 AST，检查①引用的 `state[...]` 键 ∈ spec 声明字段
   ②调用的函数名 ∈ 算子表 ③`then` 的 label 值 ∈ 该 question 的合法标签集（noul → bool/`true|false`，choice → criteria 键，
   score → `[0, len(criteria))` 整数）。现在这三类错误全是运行时静默（fixture 里的 `state_drug`、`issue_type_lookup`、
   `split_any`、`SPECIAL_POPULATION_PAIRS` 在 `engine.py:76` 的 names 表里根本不存在）。
4. **`let` 块**：`spec.generator.let: {"state_drug": "state['药品'][0]"}`，让 fixture 已有的写法有个显式来源，
   而不是靠 names 表里凭空冒出的符号。

### D5 配额相对 n

`plan.py:195-201` 现在把 `quota` 当绝对条数、`share` 弃用（缺失时才 `int(share*1000)`），于是
`critical-value` fixture 的 5×55 在 n=60 时把每条都 steer 成危急样本。改成：

```json
"plan_targets": {"normal_share": 0.35,
                 "by_label": {"driver:risk": {"weight": 0.2}, "urgency:2": {"weight": 0.1}},
                 "by_category": {"renal": {"weight": 0.3, "tier_split": [[0, 0.5], [1, 0.5]]}},
                 "floor": 0.05}
```

- 一切**权重**按 n 归一化；`quota` 保留为「显式绝对条数」逃生口，但与 `weight` 同时出现时静态校验报错。
- 新增 `by_label`：直接对「哪个 question 的哪个标签要占多少」下配额。这是解决 F7（标签不可达）的正解——
  今天只能按 category 驱动「某字段越界」，中间档与第 4 类 driver 无从铺设。
- `floor`：生成后自动按现存闸门判定，并回报「哪个标签差多少条、需要哪条 steer 才够」。

### D6 selectors 真生效

`sampler.py:53`（`randint(2, 5)`）、`:64`（`rng.random() < 0.35`）、`:72`（`min(2, ...)`）三处字面量
改读 `selectors[0]` 的 `min/max/weight_normal/weight_trigger_extra/max_trigger_extra/max_trigger_tier_drift`。
fixture 里这些键早就写好了（`0.35` 与 `2` 就是被抄进代码的那两个值），本项不新增 schema。顺带取消「字段必须 ≥6」的隐性下限。

### D7 spec 单一真相源

新增 `engine.resolve_spec(slug)`，顺序：`KEV_ENGINE_SPEC_DIR` → DB `scenarios.spec_json` 的物化投影
`paths.CONSOLE_SPECS` → `paths.SPECS`（仓库医疗 spec，只读回退）。`engine._load_spec`、`common.load_spec`
（`common.py:33-45`，硬编码 docs 目录）与 `app.py:494-547` 三条路由全部走它。
今天没有任何代码把 env 指向投影，所以 preview 预览的不是用户刚编辑的那份 spec，新场景必然 `FileNotFoundError`
（上一会话的 `.tmp-spike/err.txt` 撞的就是它）。

### D8 最小对按类型翻转

`pair.py` 现在只认「数值字段边界另一侧 + `state['labs']`」。改为按字段类型定义翻转：
numeric→阈值另一侧、enum→另一值、bool→取反、date→窗口两侧、list→增删一个元素、object→改一个子键；
统一断言 `common.changed_fields(record, twin)` 长度恰为 1 且标签确有变化（复用 `common.minimal_pair` 的判定）。

### D9 legacy 双路保留到最后一个 PR

决策：**先只动引擎**，六个 `gen_*.py` 在 PR1a–PR4 期间原样在线，`tests/test_medical_generators.py` 作为
「不许回归」的守卫；全部引擎工作与闸门就绪后，**单独一个 PR** 把六场景迁到 spec、把 byte-for-byte 平价测试
重写为属性断言（标签由规则重算 / 每标签 ≥5% / n 不变性）并删除 legacy 模块。
代价：中间态存在两套语义（PR1a–PR4 的窗口，约 5 个 PR）；收益：任何一步引擎改动都可以拿 legacy 的产出做对照物验证等价，
避免「删掉对照物之后才发现不等价」。

### D10 第八类字段：catalog（候选项池）

写 D1 时我只考虑了「字段有值」的七种形状。查证六份 fixture 的 `generator.fields` 后发现，其中两份的字段**根本没有值可采**：

```json
{"name": "持续胸痛", "category": "cardiovascular", "urgency": 2, "needs_test": true, "red_flag": true, "priority": 0}
```

`diagnosis` 的 35 条、`triage` 的 58 条都是这个形状：`name` 是要出现在文档里的症状文本，其余全是**标签属性**。
采样的语义不是「给字段取个值」，而是「从 N 个带属性的候选里抽 k 个，标签由抽中者的自带属性决定」（legacy 的
`gen_diagnosis.derive()` 干的就是这件）。

```json
{"name": "症状", "type": "catalog", "draw": {"min": 1, "max": 2},
 "surface": {"chief_complaint": "join_by(derived['症状'], 'name', '，') + '，' + pick(rng, TONE)",
             "red_flags": "default_if_empty(join_by(where(derived['症状'], 'red_flag', True), 'name', '、'), '无')"},
 "pool": [ /* 就是今天的 fields 列表 */ ]}
```

规则与 surface 都从 `derived`（派生视图）读属性，从 `state` 读已拼好的表面；引擎把 `derived` 写进记录的 `_meta.derive`。
不做这一类，PR1a 做完前七类仍跑不通 T6（六份里三份靠它）。

### D11 双通道：标签依据走 `_meta.derive`，state 只放表面

这是本轮最大的架构发现。legacy 把两件事分得很开：标签从结构化候选派生，写进 state 的是把结构溶解后的自然语言
（`gen_triage.py:106-116`、`gen_diagnosis.py:144-152`：`chief_complaint = "，".join(s[0] for s in symptoms) + "，" + 语气词`）。
而 fixture 的 spec 规则读的是那份结构化视图（`state['presentations']`、`state['symptoms']`、`state['age']`），
**这些键在 legacy 表面里压根不存在**（见 §6 缺陷 3）。

定案：**两条通道显式分开**。

1. **派生通道**：抽中候选的带属性对象存进记录顶层 `_meta.derive`，不进渲染；规则求值与 surface 求值时引擎把它
   以 `derived` 这个名字暴露给 names 表（所以规则可以写 `any(p['red_flag'] for p in derived['症状'])`）。
   先例：`evals/hard-v1` 的标签来自各 family 的 solver 读 `_meta.facts`，state 是给人看的文本。
   `split_data.check_record`（`skills/kev-finetune/scripts/split_data.py:84`）只要求 `state` + `questions`，额外顶层键合法。
2. **表面通道**：用**算子**写（D11 不发明模板语言）：`join_by(items, attr, sep)`、`where(items, attr, value)`、
   `default_if_empty(x, fallback)`、`pick(rng, pool)`。这些进算子表，与规则共用同一个 `EvalWithCompoundTypes`。

为什么不能让属性直接进 state：`triage` 池里的 `urgency`/`red_flag`、`diagnosis` 的 `needs_test` **就是标签本身**，
而 `kev/api.py:49-55` 的 `render` 会把 list-of-dict 的每个键都展平（`- name: 持续胸痛\n  urgency: 2\n  red_flag: True`）。
属性进 state = 答案印进 prompt，训练数据退化成查表，直接碎掉「标签必须来自规则」这条 0.8B 路线前提。所以光有设计约束不够，
还得有机检闸门（G8）防回归。

### D12 数值阈值：通用 `bounds`，不再是 `normal`/`critical` 两个硬编码名字

`medication-review` 的 15 个字段用的是 `single_max_mg` / `daily_max_mg` / `daily_min_mg` 三个业务界，
`nursing-quality` 干脆 `unit: ""` + `decimals: 0` 披着数值皮。如果引擎只认 `normal`/`critical`，每加一个行业
都要改 `ops.py`。改成：字段声明 `bounds: {"<界名>": [<下>, <上>]}`，引擎不解释语义，只负责存在性与类型检查；
规则与 surface 自己引用界名。`critical`/`normal` 作为 `bounds` 的两个普通键名保留（现有 spec 不变仍然有效）。

### D13 text / enum 语料：只允许 spec 内联池

legacy 已经给了答案：`CONTEXTS`/`VITALS`/`COMORBID`/`CHANNELS`/`DURATIONS`/`TONE` 全是模块内的字符串常量池
（`gen_diagnosis.py:72-82`）。所以 text/enum 字段只需 `values: [...]` 内联池，六份 fixture 就能收编。
**不允许** `corpus` 指向仓库外文件：会碎掉确定性重放，PR CI 的机器上也没那些文件。长文档类新场景（合同条款、
审稿意见）先靠内联池 + 模板拼接；真不够用时另立设计，不在本设计里开口子。

### D14 spike spec 入库：全量 + 精选重写

32 份共 ~48 KB，全量收进 `tests/fixtures/engine-matrix/` 当回归资产（那 20 个崩溃场景的保护只能靠它们）；
另挑 12 份重写为教学样例（去掉我为了跑矩阵随手写的规则、补注释），README 指向重写版。

### D15 list / object 的元素 schema：递归复用同一套八类

`items: {"element": <field-spec>}`，元素本身就是一个普通字段声明（可以带 `type`/`bounds`/`pool`/`path`），另加
`{"min", "max"}` 控元素个数。定案理由：D1/D10 已经把「按类型分派采样」收进一个入口，另立一套 list schema
会得到第二套采样器与第二套校验。这一条没单独过评审，是从 D1 的单一分派原则直接推出来的；若被推翻，
只影响 PR1a 的采样器结构，不影响其他决策。

---

## 3. 引擎改造点与失败模式的对应

| 文件 · 位置 | 今天 | 改成 | 关掉 |
| --- | --- | --- | --- |
| `ops.py:103-141`（`normal_value`/`critical_value`/`realize_tier`） | 每个字段必读 `field["normal"]` | 拆成 `NumericSampler` 的实现，其余类型各一个 `sample(field, rng, spec)` | F1 |
| `sampler.py:38-78` | 一条路径处理所有字段 | 按 `field["type"]` 分派；`selectors` 读 spec；二次越界概率/条数来自 spec | F1/F6 |
| `sampler.py:89-95`（`make_record`） | 拼 `patient/context/labs/...` | 按 `field.path` + `aux` 落位 | F2 |
| `ops._format` / `_parse_value` | 值即 `"6.2 mmol/L"` 字符串 | 记录存 typed value；格式化仅在 `render_units: "on"` 时用于渲染 | F3/D3 |
| `engine.py:76`（names 表） | 四个固定符号 | + 派生量（today/anchor）；`let` 经 §5.3 否证，不做。**PR2b 落定**：`engine._rule_names` 组装，`state` 换 `ops.rule_view`，派生通道由 `derive.extra_names` 提供 | F4 |
| `engine.py:84-93` | `except: continue` / `except: pass` | `RuleError` 抛出，带 rule_id 与表达式。**PR2b 落定**：私有副本删掉，唯一的 `rules.evaluate`——缺键（`ops.MissingEvidence`）= 本条不适用，其余异常 = `RuleError`，`engine.run` 在采样之前先跑 `rules.static_errors` | F4 |
| `ops.py:236-257`（ALLOWED，20 个） | 医疗派生算子，无 `float/sum/sorted` | 通用集 + 派生集 + 原 20 个 | F3/F4 |
| `plan.py:181-201` | `quota` 绝对条数、`share` 弃用 | 权重归一化 + `by_label` + `floor` 判定 | F5/F7 |
| `pair.py:34-46`、`engine.py:184` | 只认 `state["labs"]`、只翻数值 | 按类型翻转 + path 落位 | F2/F8(D8) |
| `common.py:33-45`、`app.py:494-547` | spec 三处真相源 | `resolve_spec(slug)` 单一入口 | 缺陷 2 |
| `sampler.py:38-56`（字段即有值） | 只有「给字段取值」一种采样 | 新增 `catalog` 采样器：从带属性候选池抽 k 个 | F1/D10 |
| `common.py:58-82`（`labelled`） | `record = {state, questions}` | 允许附带 `_meta.derive`（标签依据，不进渲染） | D11 |
| `gen_triage.py:106-116` 的字符串拼接 | 表面组装只存在于 Python 源码里 | `surface` 字段 + `symptom_names`/`join_by`/`default_if_empty` 算子 | D11 |
| `ops.py:106` 的 `field["normal"]` | 界名硬编码 | `bounds` 字典，引擎不解释语义 | D12 |
| `engine.run` 出口 | 打印 warning 后返回 0 | 自动跑现存闸门，不达标非零退出并回报缺口 | F7 |

---

## 4. CI 闸门（硬阻断）

新增 `tests/test_engine_matrix.py`，把 spike 的 32 份 spec 收进 `tests/fixtures/engine-matrix/`（去掉 `matrix.py`
里的猴补丁与绝对路径），逐条断言：

- **G1 形状×领域覆盖**：8 类字段 × 4 个领域至少各 1 个场景，n=120 产出满 N；`split_data.check_record` 0 问题；
  每个标签 ≥5%；无「从未出现」标签；兜底规则命中率 ≤0.6。
- **G2 n 不变性**：同一 spec 在 n = 30 / 300 / 3000 下，每个标签占比漂移 <5 个百分点。
- **G3 fail-loud**：三份故意写坏的 spec（未知算子、未知 state 键、非法 label 值）各让 CI 红，且错误里能读出
  `rule_id` 与原因（防 T4 退化成「跑通了但全落兜底」）。**PR2b 绿**：三份在 `tests/fixtures/engine-broken/`，另
  加一份 `tests/fixtures/engine-empty/`（静态全对但零产出）钉住「空文件不是通过」。
- **G4 零 Python**：2 个新场景（spike 里没出现过的形状，例如「审批链路由 = enum+date+list」）只提交 spec，即通过 G1。
- **G5 自家 fixture**：六份 fixture 由 engine 跑通并通过 G1 判定（record-summary 的非法 JSON 先修），且每个场景的
  `render(state)` 与 legacy 产出对齐（含 `unit: ""` 不产生尾随空格）。
- **G6 骨架**：任一非医疗场景的产出里断言 `'patient' not in state`、`'labs' not in state`。
- **G7 不回归**：`tests/test_medical_generators.py` 全绿，**且该文件已加进 `ci.yml`**（今天 CI 不跑它，所以下面的
  「硬阻断」若不补这条就是空话）；PR5 里以属性断言替代后，该条改成新形态。
- **G8 零泄漏**（T9）：对每份 fixture 与矩阵场景断言：`render(record["state"])` 不包含任何标签属性名
  （`red_flag`/`urgency`/`needs_test`/`severity_default` 等，名单从 spec 的 catalog pool 键集推），且
  `_meta.derive` 里的属性值不作为独立行出现在表面。这条是 D11 的唯一机器护栏。

成本：矩阵子集（每形状 1 个 + G3/G4/G8）进 PR CI，32 份全量 + G2 的 3000 档进夜间。

---

## 5. 分期与合并顺序

| PR | 内容 | 退出条件 |
| --- | --- | --- |
| PR1a ✅ 见 §5.1 | 七类采样器分派（`numeric/enum/bool/text/date/list/object`）+ D12 `bounds` + D2 骨架（`path`/`aux`）+ `resolve_spec`（D7）+ 新建 `tests/test_engine_matrix.py` 并接进 `ci.yml` | T1 的前七类、T2、T8、G6 绿；G1 里 20 个崩溃场景不再崩 |
| PR1b ✅ 见 §5.2 | D10 catalog 采样器 + D11 双通道（`_meta.derive` + `join_by`/`where`/`default_if_empty`/`pick` 算子）+ D15 递归 element schema | T1 满八类、T9；G8 绿；G1 里 diagnosis/triage 形状的场景能产出满 N 且不泄漏 |
| PR2a ✅ 见 §5.4 | D3 typed value + `render_units` 声明 + date 求值视图 + 6 份 fixture 的字面量迁移 | G7 绿；`LEDGER` 从 12 缩到 5（实测出账 7） |
| PR2b ✅ 见 §5.5 | D4 求值器/算子/fail-loud/静态校验（含 `generator/validate` 语义修正、§6 缺陷 9 的沙盒那半）+ G3 三份反例 | T3、T4；arith/date/list 场景标签正确；G3 绿；`LEDGER` 只剩不由求值器负责的一条 |
| PR3 | D5 配额 + `by_label` + D6 selectors + D8 最小对（含 §6 缺陷 5 的 `ops.crossed` 安全侧；catalog 按「换一个候选」翻转）+ 出口接现存闸门 | T5、G1、G2、G4 绿 |
| PR4 | 六 fixture 收编：其中 diagnosis/triage/nursing-quality 三份的规则需按 legacy 表面重写（§6 缺陷 3），legacy 仍在，双路做对照产出差异报告 | T6、G5、G8 在六份 fixture 上绿 |
| PR5 | 迁移六场景到 spec、平价测试改属性断言、删 `gen_*.py` | G7 的新形态绿 |

风险窗口：PR1a–PR4 期间「引擎」与「legacy」两套语义并存，PR4 的对照报告是这个窗口的唯一护栏——
它必须能回答「同一份 spec 下，引擎与 legacy 的标签分布差多少、`render(state)` 差多少」。
PR1a/PR1b 的拆分理由：双通道（D11）动的是记录结构与求值入口，与采样器分派是两个改动面；先合 PR1a 可以
让那 20 个崩溃场景尽早不再崩，而不必等双通道设计落地。
PR2 按 §5.3 的实测拆两半：**PR2a = D3**（typed value + `render_units` + date 求值视图 + spec 字面量迁移），
**PR2b = D4**（统一求值器 + fail-loud + 静态校验 + `generator/validate` + G3）。退出条件不变。探针量出「只换 typed
value」救得回 12 个里的 2 个，而 PR2a 按 C、D 两类补齐修法后实测出账 7 个（§5.4），剩下 5 个才是 PR2b 的 A、B 两类。
PR2b 实测出账其中 4 个，**但 `LEDGER` 没清空**：最后那条（`edu-essay-scoring` 的两个问句）不再是求值器读不到值，
而是 §6 缺陷 8 的分布与一条 spec 从未写下的规则——它们属 PR3，见 §5.5。

### 5.1 PR1a 完成记录（2026-10-12）

判据实测（`.superpowers/spike/_probe_pr1a.py`：`KEV_ENGINE_SPEC_DIR=tests/fixtures/engine-matrix`，32 场景 × n=60）：
`crashed before: 20 still crashing: 0 producing zero: 0` —— 20 个崩在 `KeyError: 'normal'` 的场景全部产出满 60 条。

| 判据 | 证据 |
| --- | --- |
| T1 前七类 | `values.py` 的单一分派入口按 `field["type"]` 取采样器（缺 `type` = `numeric`，六份医疗 spec 一字不改仍有效）；`bounds`（D12）做存在性与类型检查，引擎不解释界名语义 |
| T4 局部 | 十种写坏的字段声明各自 fail-loud：缺 `normal`、空 `values`、`values_ref` 缺失、`date` 无/坏 `range`、`list` 无元素、`object` 无 `fields`、`catalog`（明确报「属 PR1b」）、未知 `type`、坏 `path` |
| T2 骨架 / G6 | 字段 `path` 落位（`law-sentencing` 三层嵌套）+ `generator.aux`（今天只认 `"dropped"`）；矩阵产出的 `state` 断言 `'patient' not in state and 'labs' not in state` |
| D7 | `common.resolve_spec`：env → `paths.CONSOLE_SPECS` → `paths.SPECS`，每目录接受 `<slug>/spec.json` 与 `<slug>.json`；半写坏的投影报 `spec <文件> is not valid JSON` 而不是静默落到下一个源 |
| T8 / G7 | `tests/test_medical_generators.py` + `tests/test_engine_matrix.py` = 66 passed，两个文件都已写进 `ci.yml`（§6 缺陷 4 修掉） |
| 约定闸门 | `label_keys` 改调 `kev.api.question_keys`（不再第二处推导），3 份 console 测试的 `write_text` 改成行基 scanner 看得见的 `encoding=`；`test_conventions.py` 的两条本地转绿（连同缺陷 6 的断言修正，6 个文件 105 passed） |
| 确定性 | 同 seed 两次生成逐字节同文件 |

**PR1a 有意留下的两处不对齐，钉成测试而不是藏起来（`tests/test_engine_matrix.py` 的模块 docstring 同步记录了这段边界：
本文件证明的是引擎不再拒绝这些形状，不是这些数据可训练）：**

1. **12 个场景标签退化**（只有一个标签值有产出，清单即测试里的 `LEDGER`，断言是集合相等）。根因是 F3/F4：值仍带单位
   字符串（`"6.2 mmol/L"`），`SimpleEval` 在 date/arith/list/text 规则上只能落兜底。**属 PR2**——PR2 做完这个集合必须缩小，
   否则测试红，账本不会悄悄漂。
2. **最小对几乎不产出**（§6 缺陷 5）。PR1a 只把「开了 `--pairs` 也不许污染产出」钉成断言，不断言 twin 条数。

### 5.2 PR1b 完成记录（2026-10-12）

判据实测（`.superpowers/spike/_catalog_probe.py`：四份 catalog 场景 × `--n 40 --seed 0 --pairs 0`）：
每份 `rc=0 / n=40 / leaked=[] / no_derive=0`，且标签全部非退化
（`fin-credit-adverse` `risk_grade` 四档 26/7/5/2、`edu-unit-remediation` `plan` 19/12/9、
`sci-incident-triage` `owning_team` 20/11/7/2 且 `acuity` 四档齐全、`law-evidence-weight` `weight` 21/10/9）。
`LEDGER` 一条未增：四份新场景都没有单值标签，所以 PR1a 那本账没被 PR1b 动过。

| 判据 | 证据 |
| --- | --- |
| T1 满八类 | `values.SAMPLERS` 八项，测试直接断言集合相等；矩阵补齐 `catalog` 形状（四领域各 1 份），sidecar 用 `"added": "PR1b"` 标出「晚于 spike、不可能进崩溃计数」的四份，`CRASHED_IN_SPIKE` 仍是 20 |
| D10 采样器 | `values.sample_catalog`：`pool` 非空且每项是对象、`draw` 是对象、`0 <= min <= max`、`max` 钳到池大小、`rng.sample` 不放回、返回候选的浅拷贝（spec 是只读真相源） |
| D11 双通道 | 新模块 `derive.py`（`split`/`pools`/`extra_names`/`operators`/`surfaces`/`attach`），引擎 `run()` 循环第 3-5 步接线：抽中的候选出视图 → `derived` + spec 池名进 names 表 → 表面表达式填回 state → 规则求值 → 记录建好后挂 `_meta.derive`。twin 复用父记录的 draw（最小对演示「一个事实动了」，PR3 才教它换候选） |
| T9 / G8 | `test_a_catalog_label_never_appears_in_the_prompt`，四条同时成立：`set(state)` == 表面键 ∪ 同伴字段名；属性名不得成为 state 的任何一层键（`state_keys` 递归走 dict/list，正是 `render` 展平的键）；`choice` 标签的码值不得出现在 `render(state)`；`_meta.derive` 的每条候选必须逐字节来自池 |
| surface 算子 | 十条 legacy 拼接语句穷举成 10 个函数（§7.1），`ops.ALLOWED` 20 → 29 |
| 零漂移 | `surfaces` 在无 catalog 时于触碰 rng 之前返回；`test_a_spec_without_a_catalog_field_costs_the_run_nothing` 直接比 `rng.random()`；`test_engine_matrix.py` + `test_medical_generators.py` + `test_conventions.py` = 109 passed，含六份医疗 fixture 的逐字节平价 |
| 确定性 | 同 seed 两次生成逐字节同文件（`test_the_same_seed_reproduces_the_same_file` 未改） |

**G8 从文档措辞收到可判定的形态**（§4 原文的第二句「`_meta.derive` 里的属性值不作为独立行出现在表面」按字面写会假阳性）：
属性值是 `2` / `true` / `0` 这类小整数与布尔，它们在普通 state 文本里合法地大量出现（`"126.0 个"` 含 `2`），
子串断言会把好数据判成泄漏。G8 真正要防的是「答案印进 prompt」，所以实现成两条可判定的：属性名不得成为渲染键，
**标签码值**不得出现在渲染文本里。第二条才是抓到真缺陷的那条（下面第 1 点）。

**PR1b 现场发现的三件事，都钉成了测试：**

1. **第一版 `sci-incident-triage` 自己造了泄漏**：表面里写了一条 `指派线索: attr_of_min(derived['故障信号'], 'priority', 'team')`，
   于是 state 出现 `"infra（按专精顺序）"`，而 `owning_team` 的标签正是 `infra`——答案躺在 prompt 里。legacy
   `gen_triage.py:106-116` 的尺度是「报红旗症状的*名字*，绝不报 urgency，也绝不报 department」，所以删掉该表面键、
   并在测试里补上「`choice` 标签码值不得出现」这一条。教训：「属性名不进 state」不够，「答案不进 state」才是判据。
2. **`sampler` 的同伴字段数是潜在崩溃**：`rng.sample(others, rng.randint(2, 5))` 在字段总数 < 6 的 spec 上必
   `ValueError`，而 catalog 场景天然小（1 池 + 2 同伴）。钳成 `min(rng.randint(2, 5), len(others))`，
   rng 消耗序列一字不变（对既有 32 场景零影响）；副作用正好符合要求——三字段 spec 里池不可避免，每条记录都带 `_meta.derive`。
3. **`state_example` 此前没有任何测试读过**：四份新 fixture 的第一版里有几处真实引擎产出不了的记录（law 的 `证据清单`
   少了 `pick(REMARKS)` 的尾巴、`对方异议焦点` 列了一个 `prejudicial` 不为 3 的项、edu 的 `先修清单` 漏了第二个先修单元、
   sci 保留了刚删掉的键）。
   补了 `test_the_fixtures_documented_example_has_the_keys_a_real_record_has`（键集必须等于真实记录的键集），
   并把四份例子换成引擎真实产出的记录。`state_example` 是给人和 console 预览看的，写错就是教人错的文档。

PR1b 有意留下的、不在本 PR 修的东西：数值字段的钉界与格式化不一致（§6 缺陷 8）、tier 路径上 `ops` 的坏 import
（§6 缺陷 9，PR3 上配额就会天天走那条路）、catalog 场景的最小对（这些 spec 无 `plan_targets` → `state_target` 恒
`None` → pair 规则不触发，测试只断言「开 `--pairs` 也不许丢 draw」这半）。

**回归取证的边界（要说清哪些是本地跑过的）：**与本次改动有依赖关系的四个文件全绿（
`test_engine_matrix.py` + `test_medical_generators.py` + `test_conventions.py` + `test_generators.py` = 122 passed，含六份
医疗 fixture 的逐字节平价）。`ci.yml` 清单里其余的文件本地只做到「收集无错」（`test_hard_v1/devtools_v1/breadth_v1/rounds`，
它们不 `import` 任何 `kev.console` 模块，而本 PR 的 diff 只落在 `kev/console/generators/`、`tests/fixtures/`、`ci.yml` 与本文档）。
本地跑轻文件时撞到的红全部是平台性的、与本 PR 无关：`kev/contrastive.py:28` 的 `%-d`（§6 缺陷 10，
`test_generators.py` 3 条 + `test_research.py` 2 条）、把原生分隔符写进了本该是 URL/逻辑路径的地方（`evals\smoke-v1`、
`round3\decision-r3\train.jsonl` 404）、`ntpath.relative` 跳盘符（`path is on mount 'C:', start on mount 'D:'`）、
以及 Windows 的 torch 没编 libuv（`use_libuv was requested but PyTorch was built without libuv support`）。只有一条不是平台问题：
§6 缺陷 7 的 `opts`。**Linux CI 才是真闸门**，这几类红里只有缺陷 7 会在那里也红。

### 5.3 PR2 开工前的取证（2026-10-14，两个 spike）

D3 与 D4 谁挡在前面，不能靠猜。`.superpowers/spike/_typed_probe.py` 只把 PR2a 要动的两个接缝换掉
（`ops._format` 返 `round(value, decimals)`、`ops._parse_value` 对数字直通），对 36 场景跑 before/after 标签表；
`_rule_probe.py` 再把 `engine._evaluate_rules` 换成一个逐条记下异常的副本，对 12 个里剩下的 10 个场景各跑 40 条，
同时用 `EvalWithCompoundTypes` 重试那条死了的表达式，看「换个求值器」够不够。

**量出来的结论：只换 typed value 救回 12 个里的 2 个**（`fin-default-score` 的 `grade`/`warn`、
`law-overtime-compliance` 的 `compliant`/`gap_band`），其余 10 个仍单值；其余 24 个场景标签数不退化。
所以 D3 不是 F3 的解药，它只是前提——把「为什么还塌」逐条挖出来才是 PR2b 的范围，共五类：

（这个 2 是「只动两个接缝」的下界。PR2a 真正落地时连带做了 C 类的 date 视图与 D 类的字面量迁移，
实测出账 7 个，见 §5.4——差值正是这两类修法有效的证据。）

| 类 | 症状（探针原文） | 修法 | 归属 |
| --- | --- | --- | --- |
| A 缺键 | `KeyError: '今日'`×9、`'内容分'`、`'对比文件'`、`'持仓'`…… | **不是缺陷**：`selectors` 的 `min 3 / max 6` 本就允许一条记录只采到部分字段。缺键必须判为「本条规则不匹配」而不是异常，但它与真写错在今天的静默吞掉里长得一模一样 | PR2b |
| B 推导式 | `FeatureNotAvailable: Sorry, GeneratorExp is not available in this evaluator`（`any(m['mastery'] < 0.5 for m in ...)`） | rule 换 `EvalWithCompoundTypes`（同一探针确认：这些表达式换求值器后直接 OK） | PR2b |
| C 日期算术 | `TypeError: unsupported operand type(s) for -: 'str' and 'str'`（`(state['到期日'] - state['今日']).days <= 3`） | state 仍存 ISO 串（JSON、`date_facts`、最小对相等比较都依赖它），**求值视图**把声明为 `date` 的字段解析成 `datetime.date`；`_date_probe.py` 实测两个求值器都允许 `(a - b).days -> 13` 与 `a.day`，于是不必新增 `days_between` 算子、spec 语法一字不改 | PR2a |
| D 串面字面量 | `state['资产负债率'] > '80 %'`、`state['纯度'] >= '95.0 %'`、`state['凸包距离'] < '0.0100 eV/atom'` | spec 自己写错了比较对象：typed 之后必须写成数字字面量。今天它「碰巧」按字典序成立（`"85.0 %" > "80 %"`），typed 之后反而 `TypeError: '>' not supported between 'int' and 'str'`——这是 PR2a 必须连带迁移 fixture 的原因，否则 PR2a 会让场景更坏 | PR2a |
| E `then` 的字面量 | `NameNotDefined: 'hold' is not defined for expression 'hold'`——**每个场景每条记录都炸一次**，靠 `except Exception: pass` 留下原文才没出事 | fail-loud 若不做区分就会在每个健康场景上哀嚎。定案：`value` 若属于该问的合法标签集（`common.label_keys`）就是字面量、不求值；否则求值，失败即 `RuleError`。**PR2b 把「属于合法标签集」收窄为「单个裸名且是合法标签键」**，因为 `sci-incident-triage` 的 `acuity = '3'` 同时满足「是字面量」与「求值成 int」，粗放的测试会静默改数据（§5.5）。今天的行为逐条不变，但拼错的标签值（`"hld"`）从此会响 | PR2b |

探针顺带否证了 D4 的第 ④ 项：`let` 块要解决的「规则里凭空出现的符号」并不存在——A 类每一个 `KeyError` 的键名都是
**已声明的字段**，只是这条记录没采到它。所以 PR2 不引入 `let`，静态校验改盯「规则引用的字段名必须是声明字段/表面键/池名」
这一条真实的拼写错误面。

### 5.4 PR2a 完成记录（2026-10-14）

判据实测（`tests/test_engine_matrix.py::test_the_degenerate_ledger_is_what_pr2a_left`，36 场景 × n=60）：
PR1a 留下的 12 个单值问题出账 7 个，`LEDGER` 缩到 5 个（`fin-portfolio-rebalance`、`edu-essay-scoring`、
`edu-knowledge-mastery`、`sci-material-composition`、`law-patent-claims`）；闸门三件套 109 passed，全量 `tests` 绿。
出账的 7 个按问句写进 `PAID_BY_PR2A`，与 `LEDGER` 构成双向断言——塌回去是失败，而不是悄悄把债单写大。

落地形态与 §5.3 的三处对应：

1. **D3 typed value**：`ops.typed_value(field, value)` 是唯一接缝（按字段自己的 `decimals` 取整），采样器第 4 步、
   二次越界、最小对都存数字；`ops._format` 退成纯渲染器，由 `sampler.BoundarySampler.render` 在写记录时调用。
2. **`render_units` 缺省 `on`**：所以六份医疗 fixture 与矩阵 36 场景的**记录表面逐字节不变**——
   `test_a_scenario_with_declared_paths_ships_a_nested_state` 里那句 `isinstance(value, str)` 仍然绿，就是这条
   缺省值正确的活证。`render` 必须**递归**（D15）：嵌套在 `list.items.element` / `object.fields` 里的数值改前也带
   `"unit": ""` 的格式化（`"0.42"`），只看顶层字段会让它们在 PR2a 静默变成 `0.42`；未声明的 surface 键则原样透传，
   否则 `3` 会被渲染成 `"3"`。
3. **C 类不新增算子**：`ops.rule_view(state, fields)` 只在求值名字表里把声明为 `date` 的字段解析成 `datetime.date`，
   记录、JSON、`date_facts`、最小对相等比较继续用 ISO 串，`(a - b).days` 的 spec 语法一字未改。
4. **D 类迁移**：6 份 fixture 把「测量值 vs 自己的单位串」改成数字字面量（`law-contract-breach`、`sci-review-accept`、
   `sci-material-composition`、`sci-target-visibility`、`fin-covenant-text`、`sci-reaction-yield`）。

顺手挖出并修掉一处**真实的 spec 缺陷**（不是为了让测试变绿）：`edu-enrollment-deadline` 的 `缴费完成日` 声明为 `date`，
规则却写 `state['缴费完成日'] == '尚未'`——日期串永远不等于那个哨兵，这条规则从不命中；`state_example` 里该字段本来
就是日期，佐证是写错。改为 `state['缴费完成日'] > state['今日']`，该问随 PR2a 出账。

仍留守的 5 个全部指向 PR2b 的 A、B 两类；`edu-essay-scoring` 疑因还牵动 §6 缺陷 8——三个分量被钉在下界，`>= 7` 因此
不成立，这条要在 PR2b 复核。

### 5.5 PR2b 完成记录（2026-10-14）

判据实测（`tests/test_engine_matrix.py::test_the_degenerate_ledger_is_what_pr2_left`，同样 36 场景 × n=60）：
PR2a 留下的 5 个出账 4 个（`fin-portfolio-rebalance`、`edu-knowledge-mastery`、`sci-material-composition`、
`law-patent-claims`，逐问句写进 `PAID_BY_PR2B`），`LEDGER` 只剩 `edu-essay-scoring` 的两个问句；闸门三件套从 109
passed 到 **120 passed**（新增 11 条求值器/静态校验测试）。因此退出条件按实测定案改述：不是「`LEDGER` 清空」，而是
**「不再有任何场景因规则读不到值而塌缩」**——剩下的那一条读得到值，是数据与 spec 的债。

三个语义定案，对应 §5.3 的 A、B、E 三类：

1. **一个求值器**（B 类）：`rules.evaluate` 用 `EvalWithCompoundTypes`，与 surface 通道同一个。`engine.py` 里的私有副本
   与它的 `_EXTENDED_ALLOWED`（对 `ops.ALLOWED` 的空操作重复——三个医疗算子早已在表里）一起删掉；旧
   `rules.RuleEvaluator` 零调用者（全仓 grep 无引用），也删。自此 spec 能写 `any(m['mastery'] < 0.5 for m in ...)`。
2. **缺键 ≠ 异常，也 ≠ 命中**（A 类）：`ops.EvidenceView.__missing__` 抛 `MissingEvidence(LookupError)`，`when` 或 `then`
   任一处触发都表示「本条不适用，扫下一条」；没有规则适用则返回 `{}`，**引擎丢这条记录而不是用兜底编一个标签**。
   `in` 与 `.get` 保持普通 dict 的答案（spec 有权合法地问「证据在不在」）。`derived` 包成同一个视图（`derive.extra_names`），
   所以目录字段没抽到也是事实而不是 `KeyError`。
3. **字面量测试收窄**（E 类）：只有「`then` 的值是**单个裸名**且该名字是该问合法标签键」才算字面量。这不是保守，
   是必需：`_rules_survey.py` 对 36 份 spec 每一条规则做 ast 全量调查，SYNTAX/STATE/DERIVED/CALL 四类问题 **0 个**、
   NAME 类 75 个全部是 E 类裸名标签——但 `sci-incident-triage` 写的是 `acuity = '3'`，一个 `score` 问句的合法键集里
   正好有 `'3'`，而它今天被 simpleeval 求值成 **int 3**，已发布的记录里也就是 3。所以上一版设计里的「value ∈ label_keys
   就当字面量」会静默把 3 变成 `"3"`——那是改数据，不是修求值器。`ast.parse("3")` 是 `Constant` 不是 `Name`，
   于是收窄后的测试自然放过它；`test_a_numeric_label_string_keeps_being_an_expression` 同时钉住 mini spec 与真实场景
   40 条记录的 `isinstance(label, int)`。拼错的裸名（`pas`）不再是字符串发到评分端，而是 `RuleError`。

静态校验与 G3：`rules.static_errors(spec)`（给人看的消息）与 `rules.static_problems(spec)`（`(rule_id, message)`，给 API）
是同一个检查的两个形状。36 份 shipped spec 全清（`test_every_shipped_spec_survives_the_static_check`）——否则闸门
拒的是库不是坏 spec。三份反例在 `tests/fixtures/engine-broken/`（未知算子、未知 state 键、非法 label 值），
各在**第一条记录被采出之前**被 `engine.run` 以 `RuleError` 拒掉，且消息里能读出 rule id。

`generator/validate` 的语义修正（§6 缺陷 2 的后半，无测试覆盖过的那条路由）：先静态、后生成；`RuleError` 带着自己的
`rule_id` 出去而不是 `<unknown>`；**0 条记录本身是错误**——旧版对空文件返回 `{"errors": []}`，正是 F3 静默塌缩在 API 上
的形态。为此新增 `tests/fixtures/engine-empty/no-rule-matches.json`（名字、键、算子全对，但 `normal [0,100]` 永不
满足 `> 1000` 且无兜底），三条路由测试在 `tests/test_console_api.py`。

§6 缺陷 9 的沙盒那半随本 PR 闭合：`derive.operators` 绑 `pick` 用的是 `functools.partial`，而 partial 把包着的 `Random`
暴露在 `.args` 上，所以 `pick.args[0].seed(0)` 是一个合法表达式、会在运行中把 rng 重置。改成闭包后同一个表达式是
`AttributeError`；`ops.pick` 与 `derive.operators` 的 docstring 本来写的就是「a one-argument closure per record」，
这次是代码追上文档，闸门侧新增一条 `test_pick_reaches_the_random_source_through_the_engine_and_nothing_else` 的断言。

复核 §5.4 挂着的那条，`edu-essay-scoring` **不是求值缺陷**（`_essay_probe.py` 实测）：三个分量 `normal [1, 9]` 的 82 个
三元组里 `(1, 1, 1)` 出现 16 次，n=200 才命中 1 次 `>= 7`，`final_band` 只有 `{'1': 199, '3': 1}`——这是 §6 缺陷 8 把值钉在
下界；而 `plagiarism_flag` 的两条规则都写 `false`，spec 从未写过能举起该旗的规则。两者都归 PR3（分布与 spec 写作），
不归求值器，所以上面的退出条件改述是必要的而不是降标。

顺手的行为等价清理（自查发现，不是为了让测试变绿）：`sampler.py` 的二次越界块与 `ops.realize_tier` 在值 typed 化之后
仍在做 `_format(..., with_unit=False)` → `_parse_value` 的往返，现在直接用数值与 `min_tier`；复跑三件套 120 passed
证明行为逐字节不变。取证同时确认了两件事：`docs/medical/specs` 的 10 份 spec **没有 generator 块**（0 rules / 0 fields），
所以引擎的活 spec 只有 36 份矩阵；本 PR 的静态校验因此只能在这些真实文本上调，而不能靠构造反例。

闸门口径（写给下一轮，免得有人拿本地噪声当事故）：本任务的回归以三件套为准（`test_engine_matrix.py` + `test_medical_generators.py`
+ `test_conventions.py`，PR2b = 120 passed），外加 `tests/test_console_api.py`（30 passed，`generator/validate` 那三条只能在这里跑，
因为 `ci.yml` 不含 console 测试）。另：`tests/test_unit.py` 在这台 Windows 上有 **14 条与本设计无关的预存红**（lease / publish /
resume / FSDP2 / release assets）——已核：该文件与它测的 `kev/rounds.py`、`budget.py`、`publish.py`、`train.py`、`full_ft.py`、
`checkpoint.py`、`modal_app.py` **全部在 HEAD**（`git status` 对它们为空），例证是 `_lease` 返回 `None` 的 POSIX 风格路径
`s/00-trial-0/attempt.json`。同 §6 缺陷 10 一类：`ci.yml` 只跑 ubuntu，所以这些从来没人见过。它们不是本 PR 的回归，
也不属任何 PR；要动它得先有一个 Windows 友好的路径约定，那是另一件事。

### 5.6 PR1a–PR2b 的落地形态（2026-10-14，写下来免得下一轮重新猜）

四个阶段是**在同一个工作树里原地覆盖**完成的，一个中间态都没提交过：PR2b 删掉了 PR1b 接线的 `engine._evaluate_rules`，
PR2a 改了 PR1a 的采样返回形状，`tests/test_engine_matrix.py` 的 `LEDGER` 从 12 条改写成 5 条再改成 1 条。git 里唯一的基线
是 pre-PR1a（`main`）。所以本设计里的 PR1a/PR1b/PR2a/PR2b 是**开发阶段**，不是四个可重建的提交——按阶段拆 PR 需要手工重造
四个从未存在过的文件态，产出的 diff 与任何一次真实跑过的闸门都不对应。落地因此按**子系统**切成四个 stacked PR：

| PR | 内容 | 为什么这一刀可以绿 |
| --- | --- | --- |
| 1 设计文档 | 本文件 | 无代码依赖；四阶段的判据与取证就在 §5.1–§5.5，阶段叙事由文档承载而不是靠 git history |
| 2 数据资产 | `tests/fixtures/engine-matrix/`（36 份活 spec + sidecar）、`engine-broken/`（G3 三份反例）、`engine-empty/`（零产出那份）、`record-summary/spec.json` 的 `True`→`true`（缺陷 1） | 纯 JSON，此时还没有读者 |
| 3 引擎 | `kev/console/generators/`（含新模块 `values.py`、`derive.py`）、`tests/test_engine_matrix.py`、`tests/test_medical_generators.py` 的 kev_track 那条（缺陷 6，**PR1a 自己写的修法**）、`ci.yml`（缺陷 4：两个生成器测试文件进 CI） | HEAD 的 `app.py` 不 import `rules`，路由在引擎换掉求值器之后仍然是合法调用方，所以引擎可以单独成一个提交 |
| 4 路由 | `kev/console/app.py::generator_validate` + `tests/test_console_api.py` 的 `# ---- generator/validate` 小节与 `Path` import | 那三条测试的被测对象就是这个路由；`ci.yml` 不含 console 测试，所以它们是本地闸门而非 CI 闸门 |

PR 3 与 PR 4 之间是 **hunk 级**分离（`git apply --cached` 只打我们那几个 hunk）：`app.py` 工作树里 +239 行只有 `generator_validate` 的
三个 hunk 是本任务的，`test_console_api.py` +120 行只有两处。留在工作区不进提交的都是并行会话的
（`db.py`、`executor.py`、`stages/*`、`stage_params.py`、`test_console_{contract,executor,distill_routes,goldset_distill,services_publish}.py`
——包括那几个 `encoding=` 行，它们挂在**他们新增**的 `write_text` 上，不是本任务的约定闸门修法）。

---

## 6. 顺带修的仓库缺陷（1、4 已随 PR1a 修掉，2 与 9 的后半已随 PR2b 修掉，新发现 5–10）

1. `tests/fixtures/record-summary/spec.json:167` 写的是 Python `True`，该文件不是合法 JSON，任何加载即抛
   （本轮实测：`Expecting value: line 167 column 52`）。**PR1a 已修**（改 `true`）。
2. spec 三处真相源（DB `spec_json` → `data/console/specs/` 投影 → `docs/medical/specs/`），引擎与三条
   `generator/*` 路由只认第三处，因此 UI 里编辑后的 spec 从不被预览；`generator/validate`（`app.py:531-547`）
   跑 `--n 1`、把异常压成 `{rule_id: "<unknown>"}`、0 产出仍返回 `{"errors": []}`。
   PR1a 的 `resolve_spec` 覆盖第 2 条的前半，`validate` 的语义修正随 PR2 的 fail-loud 一起做。**PR2b 已修**：先静态后
   生成、`RuleError` 带着 `rule_id` 出去、空产出本身是错误，三条路由测试见 §5.5。
3. **三份 fixture 的 spec 是愿望写作**（本轮新发现，不是顺手修的小缺陷，而是 PR4 的工作量本体）：它们的规则
   读的 state 键在 legacy 表面里不存在。逐一核过：`diagnosis` 读 `state['presentations']`（legacy 给的是
   `chief_complaint/vitals/labs/imaging/comorbidities/duration`）；`triage` 读 `state['age']` 与 `state['symptoms']`
   （legacy 把年龄融进 `patient: "male 58"`、把症状融进 `chief_complaint/accompanying/red_flags` 文本）；
   `nursing-quality` 读 `state['check_point']`（legacy 给的是 `observed`）。只有 `medication-review`（`state_flags`）
   与 `critical-value`（不读 state）对得上。不处理这一条，T6 的「表面与 legacy 对齐」不可能成立。
4. **console/generators 全系测试不在 CI 上跑**：`ci.yml:18` 只列了 12 个文件，`test_medical_generators.py` 与其
   它 console 测试均不在内；`engine.py:53` 注释里引用的 `tests/test_engine.py` 在本 checkout 不存在，
   即 spec 驱动引擎今天 **零测试覆盖**。所以上面的「硬 CI 阻断」必须连带把新测试文件写进 `ci.yml`（PR1a 就做），
   否则 G1–G8 只是本地习惯。**PR1a 已修**（两个生成器测试文件都已在 `ci.yml`）。
5. **`ops.crossed` 算不出安全侧，因而最小对几乎不产出**（PR1a 写测试时实测）。安全侧窗口从 `normal` 区间反推，
   于是 `critical.low` 写哨兵 `-1e9` 时永远翻不出临界区，上界哨兵 `1e9` 也只有约 25% 命中：矩阵里 99 个带 `critical`
   的数值字段只有 52 个可翻，`law-sentencing`（seed 3、`--pairs 0.9`）40 条中 targets 9 / coin 9 / trigger 9 而 twin 只 1 条。
   属 D8 的工作量本体（「按类型翻转」必须先把「另一侧」算对），PR3 修；PR1a 不假装它已好，测试只断言高侧数值字段
   能翻与非 numeric 字段返回 `None`。
6. **`test_medical_generators.py:70` 的「每份 spec ≥3 问」在 main 上本来就是红的**（正因缺陷 4，从没人在 CI 见过）：
   `medication.json` 只有 2 问且 `distill.kev_track: false`，开放式问答与蒸馏轨场景本无多头部可喂。
   PR1a 把断言收到 Kev 轨（`(spec.get("distill") or {}).get("kev_track", True)`），而不是改数据凑测试。
7. **`python -m kev.benchmark` 在 main 上跑不了任何非 `--remote` 任务**（PR1a 做回归取证时撞到的，与本设计无关）：
   `fc4a17e`（#231、device probe fail-closed）把 `opts = LoadOptions.from_env()` 留在了 `main()`，而 `run()`
   （`kev/benchmark.py:247`）仍然引用它 → 每次 `NameError: name 'opts' is not defined`，`tests/test_device.py` 的两个
   benchmark 用例（`test_benchmark_skips_the_probe_for_cpu_and_remote`、`test_benchmark_probes_the_dtype_it_will_load`，
   两个都在 `ci.yml` 的文件清单里）因此已经是红的，且与平台无关：`opts` 是在实参求值阶段炸的，测试就算
   monkeypatch 了 `benchmark.LocalPredictor` 也到不了那个被替换的函数。**定案：本设计不碰它**，另开一个 fix PR（一行：把 `opts` 存进 args 或传进 `run()`），
   连同 PR1a 之后任何依赖 benchmark 的验证都得等它先合。
8. **数值字段约一半被钉在正常区间下界，且格式化不一致**（PR1b 写 catalog fixture 时实测）：
   `values.sample_numeric` 把 `threshold` 传成 `normal[0]`，于是 `common.boundary_value` 在 `side=False` 时 `span=0`
   → 直接返回 `round(threshold, decimals)`。40 条里 `fin-credit-adverse` 的 `近90天审批查询` 有 19 条是 `"0 次"`、
   `law-evidence-weight` 的 `举证期限剩余` 有 18 条是 `"15 天"`。更刺眼的是 `threshold` 取自 JSON 整数时返回 `int`、
   其余返回 `float`，**同一个字段**会在 state 里同时出现 `"0 个"` 与 `"160.0 个"`。继承自 `ops.normal_value`
   （HEAD 上就是这条），不是 PR1b 引入的；而 legacy `gen_critical_value.py:104` 用的是 `rng.uniform(nlow, nhigh)`
   当阈值，所以这同时是 PR4 对照报告会看见的「引擎与 legacy 的表面差」。修法（阈值取区间内随机点 + 格式化归一）
   **定案留给 PR3**：PR2a 只把值改成 typed，没有动这条分布，也没有动 `int` 阈值经 `_format` 输出 `"0 个"` 而浮点输出
   `"160.0 个"` 的不一致（`round(0, 1)` 仍是 `int`）。改它会移动 `LEDGER`，把 F3 的信号淹在分布变更里。
   **PR2b 复核已确认它是活的**：`edu-essay-scoring` 是 `LEDGER` 在 PR2b 之后唯一的留守，而它的 `final_band` 就欠在这条上
   （82 个三元组里 `(1,1,1)` 出现 16 次，n=200 才命中 1 次 `>= 7`），见 §5.5。
9. **tier 路径上三个 `ops` 函数的 import 是坏的**：`ops.normal_value`/`critical_value`/`crossed` 都写
   `from common import boundary_value`（绝对导入），只有当 `kev/console/generators` 目录本身在 `sys.path` 上才成立——
   `engine.py:28-30` 恰好把它插进去了，所以引擎路径能用、把 `kev` 当库 `import` 时会 `ModuleNotFoundError`。
   今天矩阵里没有任何 spec 触发它（`plan_targets: {}` → `state_target` 恒为 `None` → sampler 第 4 步不执行），
   PR3 上配额就会天天走这条路。**定案：PR3 修**（改成 `from . import common`），PR1b 只记录。
   同一项探针还确认了 §7.1 第三问的沙盒边界：simpleeval 1.0.8 拒绝 `__` 与 `func_` 前缀的属性访问（所以
   `__globals__` 不可达），但普通属性可达：`pick.args` 能拆到引擎绑进去的 `Random` 对象。PR2 重写求值器时
   应该把算子表包成不可拆的对象（或直接交给 `RuleEvaluator`），本 PR 不假装它不存在。**这一半已随 PR2b 闭合**
   （`derive.operators` 的 `pick` 改成闭包，§5.5）；前半（tier 路径的绝对导入）仍等 PR3。
10. **`kev/contrastive.py:28` 的 `_day` 用的是 glibc 专有的 `%-d`**，在 Windows 上 `strftime` 直接
    `ValueError: Invalid format string`，于是 `test_generators.py` 三条与 `test_research.py` 两条本地必红（PR1b 跑回归时撞到）。
    与本设计无关，也不属任何 PR：`ci.yml` 只跑 ubuntu，所以它在 CI 上从未暴露。修法是一行（`%-d` → 平台无关的去零写法），
    但改它会改动 contrastive 的产出文本，该随它自己的 fix PR 走，不夹进引擎重构。

---

## 7. 评审四个未决问题的结论

本节原为「留给评审的未决问题」，2026-10-12 评审后已全部定案，保留原问题作为记录：

| 原问题 | 结论 | 依据 |
| --- | --- | --- |
| `render_units` 是渲染时补单位还是逐字段 display 模板？ | **补单位后缀**，display 模板砍掉 | 复合显示不存在于任何 typed 字段：血压在 legacy 里是 `VITALS`/`CONTEXTS` 整条字符串池（D3 修正） |
| `object`/`list` 元素语义由谁定？ | 递归复用同一套八类 schema（`items.element`） | D15（从 D1 单一分派原则推出，未单独评审） |
| text 语料从哪里来？ | **只允许 spec 内联池**，禁止 `corpus` 外部引用 | D13（legacy 已经全用内联池，且仓库要确定性重放） |
| 32 份 spike spec 是否原样入库？ | **全量入库 + 另挑 12 份重写为教学样例** | D14 |
| （评审中新增）字段类型是否够用？ | 不够，**扩为八类，新增 catalog** | D10：`diagnosis`/`triage`/`nursing-quality` 三份的字段没有值可采 |
| （评审中新增）catalog 的属性（= 标签依据）放哪里？ | `_meta.derive` 派生通道，**绝不进 state** | D11 + T9 + G8：进 state 就是答案印进 prompt |
| （评审中新增）数值阈值界名只有 `normal`/`critical` 够吗？ | 不够，改通用 `bounds` | D12：`medication-review` 用 `single_max_mg`/`daily_max_mg`/`daily_min_mg` |
| （评审中新增）state 表面怎么拼？ | 算子，不发明模板语言 | D11 + §1.2 非目标 |

### 7.1 本次评审未能覆盖、需 PR 阶段现场定的事（PR1b 已全部定案）

本节原为三条「写 PR1b 时现场再定」，2026-10-12 随 PR1b 定案，保留原问题作为记录；第四条是同一批现场新增的：

| 原问题 | 定案 | 依据 |
| --- | --- | --- |
| surface 算子的完整名单（上面只列了四个） | **10 个函数**：`join_by`（主诉拼接）、`pluck`（`s[0] for s`）、`rest`（`symptoms[1:]`）、`where`（`if s[2]`）、`default_if_empty`（`or "无"` / `or ["无"]` / `labs or {}`）、`max_attr`（`max(p[2])`）、`min_attr`、`attr_of_max`（`best = max(..., key=)` 后取属性）、`attr_of_min`（`min(top, key=priority)` 的专精仲裁）、`pick`（`rng.choice(TONE)`）；`ops.ALLOWED` 20 → 29 | 把 `gen_triage.py:106-116` 与 `gen_diagnosis.py:144-152` 的拼接语句逐条穷举成需求，一个语句一个算子，不预设「四个够了」 |
| `_meta.derive` 在新场景里的默认命名 | **统一 `derive`**，内容由 spec 的 catalog 字段名索引（`record["_meta"]["derive"][字段名] = 候选列表`），不按场景分叉键名 | `split_data.check_record` 只要求 `state` + `questions`，所以 `_meta` 合法附带；`evals/hard-v1` 已有同形先例（标签来自 `_meta.facts`，state 是给人看的散文）；而 legacy 那些每场景一套键名的字段正是 §6 缺陷 3 的病根 |
| `pick(rng, pool)` 怎么在算子表里拿 rng | **引擎按记录注入**：`derive.operators(rng)` 返回 `{**ALLOWED, "pick": 闭包}`，spec 只写 `pick(TONE)` | 不能把 `Random` 放进 names 表：名字是可调用对象，spec 就能 `rng.seed(0)` / `rng.shuffle(...)` 静默毁掉重放。两条路都到不了解释器（simpleeval 拦 `__`/`func_` 属性），而残留的 `pick.args` 跳跃（PR1b 当时用的 `functools.partial` 把 rng 暴露在 `.args` 上）**已随 PR2b 闭合**：改成闭包后同一个表达式是 `AttributeError`（§6 缺陷 9、§5.5） |
| （PR1b 现场新增）surface 与 rule 用同一个求值器吗？ | **PR1b 不用，PR2b 改成同一个**：两条通道都走 `EvalWithCompoundTypes` | PR1b 的定案理由仍成立：回退值就是字面量（`default_if_empty(..., ['无'])`），而 `SimpleEval` 在它**真正求值的那一刻**拒绝 list/dict 字面量与推导式——`'' or ['无']` 只在抽空的那一条记录上炸，39 条正常、第 40 个洞。当时不换 rule 是为了不一次动两个行为面；PR2b 换了，代价正如预见：矩阵里五个场景的规则从「死代码」变成会命中，`LEDGER` 跟着缩（§5.5） |
