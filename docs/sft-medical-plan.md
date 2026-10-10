# 医疗垂直行业 Kev 微调落地包（Qwen3.5-0.8B + Qwen3.5-4B 双尺寸）

## 用户需求

基于仓库 `d:/projects/github/kev/skills/kev-finetune`（Kev 决策模型微调 skill），为**医疗垂直行业**整理一份**完整微调落地包**，覆盖：数据采集（已有数据 + 蒸馏）、数据格式定义、微调脚本、执行与后续优化。

**两个模型都要微调**：Qwen3.5-0.8B 与 Qwen3.5-4B 各出一份完整可运行、可部署、可验收的方案，共用同一套数据资产。

用户已确认的四项关键选择：

- **决策场景（5 个，全部纳入）**：导诊分诊 triage、病历编码 ICD、危急值与报告复核、用药/医保合理性审核、护理质量管控
- **数据现状**：基本没有带标签数据，**以蒸馏为主**，开发集也是合成的（用户明确知晓这是风险最高的一档，要求额外人工抽检机制）
- **语言形态**：**中英混合**，state 采用**对象形状**承载结构化字段（症状/检验值/年龄）
- **交付深度**：**全链路落地包** —— 方案文档 + 可运行 spec + Modal 训练编排 + 阈值/覆盖率验收门槛 + 上线与回滚检查清单

## 核心设计决策：数据共享、双尺寸并行

这是本方案相对通用 LLM 微调最重要的结构性优势，也是「两个模型都微调」能低成本成立的前提。

**关键事实**：划分是按 **state 哈希**（`split_data.normalized_state` = casefold + 空白归一）分组的，与模型无关。因此**同一份 `data/<scenario>/{train,calibration,development}.jsonl` 可以直接喂给两个不同尺寸的 init**。

由此得到四条收益：

1. **蒸馏成本只付一次**：627 条记录生成一次，两个模型共用。0.8B 与 4B 共享金标集、共享 dev set。
2. **跨尺寸的 `compare` 是有效的**：`kev_modal.py::compare` 要求两次运行在同一个 `development.jsonl` 上打分 —— 同一份数据天然满足，于是可以**量化** 0.8B vs 4B 的差距，而不是拍脑袋选型。
3. **8 分钟快速闭环**：0.8B 训练约 8 分钟（H100），用它先跑通 spec / guidance / 生成器是否正确；确认无误后用**同一份数据**跑 4B，避免在 15 分钟一轮的 4B 上浪费时间去发现 spec 写错了。
4. **成本分层路由与降级兜底**：两个端点可共存，按风险分层路由；4B 冷启动期间 0.8B 可作 fallback。

### 双尺寸定位（互补，非替代）

| 维度 | Kev-0.8B（`jaredpalmer/kev-0.8b`） | Kev-4B（`jaredpalmer/kev-4b`） |
| --- | --- | --- |
| 基座（已核实） | `Qwen/Qwen3.5-0.8B-Base`（Apache-2.0） | `Qwen/Qwen3.5-4B-Base`（Apache-2.0） |
| Hub 权重修订 | `9a45d25e` | `139fdd94` |
| 发布温度（公开数据拟合值） | 2.35 | 2.41 |
| 已验证上下文 | 8,192 tokens | 8,192 tokens |
| breadth-v1 机会校正指数 | 23.3 | 38.0 |
| transfer-v4 锁定 OOD（acc / brier） | 0.697 / 0.397 | 0.838 / 0.224（card 首列） |
| hard-v1（程序化标签，acc / brier） | 0.665 / 0.460 | 见 card |
| 默认 lr（沿用 init 自身） | **4e-5** | **2e-5** |
| 典型训练时长（400–1000 条） | **~8 分钟** | ~12–15 分钟 |
| 服务 GPU（fine-tune 默认） | `L4` | `L4`（有负载时换 `L40S`） |
| 冷启动（空闲后首请求） | ~40 s | ~35 s |
| 预热模型耗时（6 题） | 23 / 16 ms（新/重复状态） | 42 / 28 ms |
| delta 体积（参考 tarball） | 46 MB | 131 MB |
| 相对 4B 的能力代价（已核实） | 日期算术 0.35、知识 MMLU-Pro 0.230–0.675、工具路由 When2Call 0.133（低于机会水平，禁止用于工具调用路由） | 日期算术 0.65、知识同受基座限制、27B 以下日期算术均是最弱项 |


**选型规则（写入方案）**：

- **0.8B 适合**：标签可程序化派生、规则封闭、选项集小、语义靠字段而非推断的任务 —— 危急值阈值判定、护理质控检查表打标、医保目录限制核对。且作为**数据闭环的验证器**与**高吞吐低风险判定层**。
- **0.8B 不适合**（能力限制直接命中医疗场景，必须写进方案的禁用清单）：
- 需要医学知识推断的任务（ICD 编码合理性）→ 知识由基座决定，0.8B 的 MMLU-Pro 低至 0.230
- 依赖日期算术的判断（妊娠周数、疗程天数、有效期）→ 0.8B 在 `deadline` 策略上仅 0.35。**对策：在程序化生成阶段预先算好日期字段，把日期算术从模型任务里拿掉**；`KEV_DATE_FACTS=1` 可作辅助但需实测
- 「是否需要调用外部系统/翻阅指南」这类工具路由决策 → 明确禁止
- **4B 适合**：语义丰富、规则难穷举、表述高度多样的任务 —— 导诊科室归属、病历编码合理性；作为主力上线模型。

**0.8B 的额外风险（与医疗验收门槛直接相关）**：发布说明记载，一次在留出数据集上的 refit 让 0.8B 在其 documents/skills 家族上**校准更差并超出注册容差**，而 4B 没有改善（−0.0001 [−0.0005, +0.0003]）。含义：**0.8B 更容易过度自信**，验收时 `mean_conf` vs `acc`、`confident_error_rate` 两项要比 4B 卡得更严。

## 一、基座选型：必须先纠偏「基于 Qwen3.5-xB」

这是全案最关键的技术前提，方案首节必须明确写出，否则实施方会直接拿裸基座去微调并失败。

**已核实约束**（`skills/kev-finetune/SKILL.md` Gotchas 原文）：`--init-from` must be a Kev checkpoint (Hub id or a run name on the volume); base, LoRA rank and head size are read from it. **Do not pass `--base`.**

**结论**：

- ❌ 不能 `--init-from Qwen/Qwen3.5-0.8B` 或 `Qwen/Qwen3.5-4B`（裸基座无 pointer head，`kev.train` 的读出层无从初始化）
- ✅ 0.8B 轨：`--init-from jaredpalmer/kev-0.8b`；4B 轨：`--init-from jaredpalmer/kev-4b`
- `kev_modal.py` 的 `DEFAULT_INIT = "jaredpalmer/kev-4b"`，**0.8B 轨必须显式传 `--init-from jaredpalmer/kev-0.8b`**

**双尺寸四层继承图**：

```
Qwen/Qwen3.5-0.8B-Base（冻结）          Qwen/Qwen3.5-4B-Base（冻结）
  └─ jaredpalmer/kev-0.8b                 └─ jaredpalmer/kev-4b
     （LoRA + pointer head，T=2.35）          （LoRA + pointer head，T=2.41）
        └─ <scenario>-8b-v1                    └─ <scenario>-4b-v1
           （医疗 delta，head.pt 内含              （医疗 delta，head.pt 内含
            为医疗数据重拟合的 temperature）           为医疗数据重拟合的 temperature）
```

**继承下来的免费收益**：

- `lr=0.0 / batch=0 / accum=0` 时沿用各 init 自身训练参数（0.8B → 4e-5，4B → 2e-5），`MAX_DELTA_LR = 5e-5` 是硬顶 —— 医疗 delta 不会训过已发布 delta 的强度
- `--replay 2000` 默认混入公开 `decision-v7` 记录保通用能力
- 一次 `train` 跑完：delta 微调 → calibration 切片拟合温度 → baseline 与微调模型**各自**在用户 calibration 切片重拟合温度（保证公平零样本对照）→ 打分 development → 配对 bootstrap → 公开数据 300 条回归检查
- **同一份 dev set 上分别 `evaluate --run jaredpalmer/kev-0.8b` 与 `--run jaredpalmer/kev-4b`，即可测出两条基线**，这是双尺寸选型的数据依据（`plan_size.py` 的 `--baseline-acc` 需要实测值，0.8B 基线更弱 → headroom 更大）

**固有安全属性**：Kev 是 pointer-readout（选项边界 token 上的指针读出）+ log loss，**不生成任何 token**。结构上不可能产生幻觉诊断、不会自由生成文本泄漏 PHI，输出只有校准概率 —— 这是医疗安全设计的基调。

## 二、记录数计算：多问题打包是成本杠杆

用 `scripts/plan_size.py` 的 McNemar 配对公式核算（`baseline_acc=0.75`、`min_gain=0.05`、`power=0.8`、`regressions=0.05`、15%/15% 划分）：

配对所需 development 问题数恒为 **469**（非配对保守上界 1092），记录数随「每条记录的问题数」变化：

| 每条记录的问题数 | dev 记录 | calibration 记录 | **总记录数** | train 记录 |
| --- | --- | --- | --- | --- |
| 1 | 469 | 469 | **3127** | 2189 |
| 2 | 235 | 235 | **1567** | 1097 |
| 3 | 157 | 157 | **1047** | 733 |
| 4 | 118 | 118 | **787** | 551 |
| **5** | 94 | 94 | **627** | 439 |


**设计含义**：

- 每条 state 承载 5 个决策问题 → 627 条即可；承载 1 个问题 → 3127 条。**同一条 state 上多问几个问题，记录需求成比例下降**，这是 Kev 相对生成式微调的核心经济性。
- 5 个场景的 spec 都必须设计成**多问题打包**（共享同一份 state），而不是一问题一数据集。
- **双尺寸不改变记录数**（配对口径下公式只依赖 gain 与 regressions），但**非配对上界依赖 `--baseline-acc`**；0.8B 基线更弱 → 上界更大。因此**双尺寸正式开跑前，必须先各自 `evaluate` 测出两条基线**，再分别核对 `plan_size` 输出。
- calibration 记录数强制 ≥ 100 个问题（`plan_size` 中 `max(100/q, ...)`），温度拟合才稳定。
- 对照 `SKILL.md` 实测教训：400 条只得到 +0.6 点、CI ±6 点（毫无意义）；1050 条得到 +5.9 点、CI [+2.3, +9.7]。**纯蒸馏场景必须一次把量做够，不能靠增量补。**

**成本量级**（预算参考，非精确报价）：蒸馏 627 条用 gpt-4.1-mini 约 $0.16（口径 $0.25/1000 条），最终数据集换 gpt-4.1 / claude-sonnet 数倍 —— **且这笔钱两个尺寸只花一次**。训练：0.8B ~8 min、4B ~12-15 min 于 H100，脚本自行打印 `bound(gpu, timeout)` 上界（`GPU_HOURLY = {H100:3.95, H200:4.54, B200:6.25, A100-80GB:2.50, A100:2.10, L40S:1.95, A10G:1.10, L4:0.80, T4:0.59}`）。服务：两者默认 L4（$0.80/h），`KEV_SERVE_MIN_CONTAINERS=1` 保温热。

**降本方向（标注为需实测）**：`--gpu` 是自由参数且有成本表，0.8B 在 L4/A10G 上训练可能大幅省钱（H100 8min≈$0.53 vs L4 8min≈$0.11），但 skill 只文档化了 H100 的典型时长，**L4 训练需自行验证**（DeltaNet kernel 与 bf16 支持）。

## 三、数据采集体系（四来源 + 医疗垂类特殊设计）

用户选择「基本没有，靠蒸馏」，但原始需求明确写了「已有 + 蒸馏」，因此保留全部四来源并明确各自的定位与优先级。

| 来源 | 医疗定位 | 实现 |
| --- | --- | --- |
| **④ 程序化生成** | **首选**。危急值/用药/医保/护理质控的标签是结构化字段的**确定性函数**；也是 0.8B 轨能成立的前提（0.8B 知识弱，必须靠零漂移标签而非语义推断） | 自建 `generators/*.py`（阈值表 + 规则引擎） |
| **② LLM 蒸馏** | 次选。导诊（科室归属语义丰富、规则难穷举）、病历编码（表述高度多样） | `generate_data.py` + 精雕 `guidance` / `variety` / `state_example` |
| **① 已有数据** | **接口预留 + 终评金标**。当下无标注记录，但一旦有即为最高价值资产 | `convert_data.py`（`--state` 多列成对象、`--map` 重命名、`--score-offset`）；用 `split_data.py --holdout` 接入 |
| **③ 人工按 dry-run 自写** | 风格锚点 + 分歧审计池 | `generate_data.py --dry-run` 打印完整 prompt，人工按批作答（≤100 条） |


### 「已有数据」在医疗垂类的真实形态

医疗垂类一个被低估的事实：**公开规则资源本身就是「已有数据」** —— 危急值标准、药品说明书禁忌/剂量上限、医保目录限制、ICD 编码规范、护理质控检查表。这些是**规则**而非标注记录，但可被程序化引擎消费成**零漂移标签**。方案要显式写出这一层，它是医疗垂类相对通用 LLM 微调的最大结构性优势，也是双尺寸都能受益的原因。

### 纯蒸馏的质量控制闭环（用户数据现状就是这一档，必须写进方案）

纯蒸馏的最大风险是「开发集也是合成的，闭环自证」。四道防线：

1. **人工金标集**：`--holdout` 接入 150–250 条人工审校记录（临床/药学人员按 `guidance` 判定并签字），对半分入 calibration + development，**永不进 train**；`split_data` 会自动剔除与其共享 state 的合成行。终评只跑一次。**两个尺寸共用同一份金标集** —— 这是双尺寸选型可信的前提。
2. **双模型分歧审计**：两个不同厂商模型对同一批 state 独立标注，分歧样本优先进人工审校池；**分歧率作为蒸馏质量的持续监控指标**。
3. **`guidance` 迭代**：`errors.jsonl` 里每一类反复错误都对应 `guidance` 缺的一句话（skill 明文：「Every recurring mistake in `errors.jsonl` is a missing sentence here」）。
4. **稀有标签显式过采样**：`split_data` 会警告「标签占比 < 5%」和「某选项从未作为正确答案出现（模型学不到）」；生成器必须按选项配额采样而非自然分布。

### 程序化生成器设计要点（本案最核心的自研部分）

- **标签派生**：标签 = f(结构化字段)，用阈值表 / 规则引擎计算，而非让 LLM 判断 → 标注零漂移，0.8B 也能学
- **最小对构造**（`common.py` 核心能力）：同一 state 只改一个事实使其跨越判定阈值，标签随之翻转。例如血钾 6.2 mmol/L（危急）vs 5.9（正常，其余字段完全相同）。这是 `references/data-generation.md` 明文推荐的做法（Kev 自身的对比式策略数据就是这么构建的），能教会模型**决策究竟取决于哪个字段**，而非学到捷径特征 —— 对 0.8B 尤其重要
- **采样必须跨越边界**：值域采样覆盖阈值两侧且在边界附近加密（`|x - threshold| < δ` 区间加权），否则模型只学会「远离阈值」的平凡特征
- **日期字段预计算**：把妊娠周数、疗程天数、有效期等日期算术在生成阶段就算好，作为结构化字段直接给模型 —— 这是针对 0.8B 日期算术弱项（0.35）的**根本性规避**，而非靠模型硬算
- **确定性可复现**：`random.Random(seed)`，同 seed 同产出，保证「改 guidance 后重跑」能精确归因

## 四、数据格式定义（医疗 state schema）

### 硬约束（违反即静默丢数据）

| 约束 | 数值 | 来源 |
| --- | --- | --- |
| state tokens | **≤ 384** | skill 数据格式文档；超限**训练器静默丢弃并打印数量** |
| 打包请求 | ≤ 2048 | 同上 |
| 每题分支 | ≤ 1024 | 同上 |


**两个尺寸该约束完全相同**（0.8B 与 4B 均只验证到 8,192 token 上下文，远高于 384），因此数据格式定义**不需要按尺寸分叉** —— 这是数据共享的又一处体现。

### 中文场景的阈值陷阱（关键纠偏）

`split_data.py` 的 `STATE_CHARS_WARN = 1400`，源码注释明确写着「~384 tokens of **English**」—— **这个阈值对中文偏松，照搬会导致大量记录被训练器静默丢弃**。

方案要求：

- 一律以 `modal run scripts/kev_modal.py::validate --data <dir> --init-from <size 的 checkpoint>` 的**实测**为准（CPU only，无 GPU 成本，输出各分区 `over_limit` 与 `state_tokens.limit`）；**两个尺寸各跑一次 validate**，确认各自的 tokenizer 下都不过限
- 对象形状 state 的长度按 `len(json.dumps(value, ensure_ascii=False))` 估算（`split_data.render_length` 口径）
- 中文 384 tokens 大致对应 380–560 汉字，但医疗文本含大量数字、英文缩写、计量单位，**token 密度偏高**，须留余量

### 对象形状 state schema（6–10 个字段，字段名短且语义稳定）

Kev 把对象 state 渲染成 `key: value` 行，**字段名对模型可见**，因此字段名是模型的一部分，必须跨记录完全一致、不可随意改写：

```
chief_complaint   主诉（患者原话，1–3 句）
age / sex         年龄、性别
vitals            体温、血压、心率、呼吸、血氧
lab_results       检验值（键为项目短名，值为数值+单位）
imaging           影像所见（1–2 句）
medications       既往用药（列表）
history           过敏史、基础病、手术史（短句）
```

字段数控制在 6–10 个；数值字段用短键名；超长字段（现病史全文）在生成阶段就截断/摘要，不依赖训练器丢弃。

### 5 个场景的 questions 设计要点

| 场景 | type 组合 | 0.8B | 4B | 设计要点 |
| --- | --- | --- | --- | --- |
| **导诊分诊** | choice(科室 10–20) + noul(是否需立即人工) + score(严重度) | ✗ | ✓ 主力 | 科室选项控制在 10–20 个（选项过多会稀释每选项样本量，触发 <5% 警告）；`guidance` 必须写清**多症状共存时的归属优先级**（如「胸痛+呼吸困难优先心内科」） |
| **危急值复核** | noul(是否触及危急值) + score(通知时限 4 级) + choice(依据项目) | ✓ 主力 | ✓ | 标签由阈值表派生；**同时输出「依据项目」字段**；证据被刻意移除的记录用 `target: {"false":0.5,"true":0.5}` 教「无证据即无把握」 |
| **用药/医保审核** | choice(审核结论) + noul(是否需药师复核) + choice(问题类型) | ✓ 主力 | ✓ | 规则来自说明书禁忌/剂量上限/重复用药/特殊人群；`guidance` 写清**多规则命中时的严重度取最高**；日期相关（疗程/有效期）字段预计算 |
| **病历编码 ICD** | choice(编码是否合理，候选集内) + noul(是否需编码员复核) + score(置信档) | ✗ | ✓ 主力 | **不要求模型直接吐 ICD 码**（码空间大、选项爆炸）；降级为「候选集内合理性判定 + 是否需人工」；长病历走两级方案 |
| **护理质量管控** | choice(问题类型) + noul(是否需上报) + score(严重度) | ✓ 主力 | ✓ | 标签来自质控检查表条目与判定标准；样本可从检查表模板程序化合成 |


### 病历编码（最难场景）的专门处理

病历全文远超 384 tokens，**直接塞入必然被丢弃**。两级方案：

1. **字段级结构化抽取**（可选前置步骤，可由现有 HIS/EMR 导出或规则+模型抽取）：主诉、现病史要点、诊断、操作、检验摘要 —— 只把结构化摘要作为 state
2. **在结构化摘要上做编码合理性判断**（choice + noul），而非直接生成编码

罕见组合与长尾：显式过采样 + 必要处用 `target` 软标签表达「证据不足」。**该场景仅走 4B 轨**（需要医学知识，0.8B 的知识基座不足）。

## 五、执行编排与双尺寸矩阵

### 单场景双尺寸命令序列

```
S=skills/kev-finetune/scripts   # 路径按实际调用位置调整

# 0. 先测两条基线（0.8B 与 4B 各一次，同一 dev split）→ 得到各自的 --baseline-acc
python3 $S/plan_size.py docs/medical/specs/critical-value.json --baseline-acc <0.8B 实测>

# 1. CPU 预检：token 超限（纯蒸馏中文场景必做，两个尺寸各一次）
modal run $S/kev_modal.py::validate --data data/cv --init-from jaredpalmer/kev-0.8b
modal run $S/kev_modal.py::validate --data data/cv --init-from jaredpalmer/kev-4b

# 2. 数据生成（程序化优先；LLM 蒸馏补语义多样性）——只做一次，两尺寸共用
python3 kev/console/generators/gen_critical_value.py --n 627 --out data/cv.jsonl --seed 0
# 或：python3 $S/generate_data.py docs/medical/specs/critical-value.json \
#       --n 627 --out data/cv.jsonl --model gpt-4.1-mini --examples data/cv.gold.jsonl

# 3. 划分（挂金标做 holdout，永不进 train）——只做一次
python3 $S/split_data.py data/cv.jsonl --out data/cv --holdout data/cv.gold.jsonl

# 4. 双尺寸训练（同一份 data/cv）——名称不可变，必须带尺寸标识
modal run $S/kev_modal.py::train --data data/cv --name cv-8b-v1 --init-from jaredpalmer/kev-0.8b
modal run $S/kev_modal.py::train --data data/cv --name cv-4b-v1 --init-from jaredpalmer/kev-4b

# 5. 跨尺寸量化对比（同一 dev set，配对 bootstrap 有效）
modal run $S/kev_modal.py::compare --a cv-4b-v1 --b cv-8b-v1

# 6. 双端点共存部署（KEV_APP_NAME + KEV_SERVE_RUN 两组组合，各得一个 URL）
modal secret create kev-serve-key KEV_API_KEY=$(openssl rand -hex 24)
KEV_APP_NAME=kev-cv-8b KEV_SERVE_SECRET=kev-serve-key KEV_SERVE_RUN=cv-8b-v1 modal deploy $S/kev_modal.py
KEV_APP_NAME=kev-cv-4b KEV_SERVE_SECRET=kev-serve-key KEV_SERVE_RUN=cv-4b-v1 modal deploy $S/kev_modal.py
```

### 命名规范（写进 runbook 醒目位置，含具体陷阱）

`kev_modal.py` 的 `NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}")` —— **只允许字母数字、下划线、连字符，不允许点号**。

- ✅ `cv-8b-v1`、`cv-4b-v1`、`triage-8b-v2`
- ❌ `cv-0.8b-v1`（**含点号，会被 `check_name` 拒绝**）

因此尺寸标识统一用 `8b` / `4b`（不用 `0.8b`）。运行名不可变（`/runs/<name>` 已存在会 `FileExistsError`），重试必须换名；`modal run` 因网络错误失败时可能已起容器，先 `modal app list` 确认。

### 其他硬约束

- **绝不在 `development.jsonl` 上拟合温度**，也不反复针对它调参；金标集留到最后一次 `evaluate`
- 校准与阈值**按 checkpoint 而定** —— 0.8B 与 4B 各有各的温度，每次重训都要分别重读两份 `result.json`
- 0.8B 轨的 `lr` 默认走 4e-5，比 4B 轨的 2e-5 更热；出现回归时两者都要「减半」，但起点不同
- 公开 `decision-v7` 回归检查 ≤ 2 accuracy 点，**两个尺寸分别判定**

### 错误代价不对称的安全设计（危急值/用药场景）

漏报危急值 ≫ 误报，因此**不取 argmax 自动处置**，而是：

- noul 问题用**低阈值 + 强制转人工**的 fail-safe 规则（阈值取自各自的 `development.selective["0.5"|"0.8"].confidence_cutoff`）
- 证据不足的记录用 `target` 软标签（`{"false":0.5,"true":0.5}`）教「无证据即无把握」
- 利用 Kev 的固有属性：只输出概率、不生成文本 → 结构上无幻觉诊断、无自由文本外泄
- 人工复核作为最后一道闸，不追求 100% 自动化
- **双尺寸分工即风险分层**：低风险高吞吐判定交 0.8B，高风险语义判定交 4B，两者阈值独立设定

## 六、验收门槛（可判定数字）

| 维度 | 字段 | 判定 | 双尺寸差异 |
| --- | --- | --- | --- |
| 增益真实 | `bootstrap.acc.ci95` | **CI 排除 0** 才算真实增益；CI 含 0 说明数据不够或增益太小（改数据不是加量） | 两尺寸各自判定 |
| 校准更好 | `development.calibrated.ece` / `confident_errors` | calibrated 必须优于 raw；**微调模型 confident_error_rate 不得超过其 baseline** | **0.8B 卡更严**（已知更易过度自信） |
| 诚实 | `mean_conf` vs `acc` | 相差在几个点内；远高于 acc = 过度自信 | 0.8B 重点监控项 |
| 回归 | `regression` 段 | 公开 `decision-v7` 300 条上 accuracy 下降 **≤ 2 点** | 两尺寸分别判定 |
| 业务价值 | `development.calibrated.coverage_at_5pct_error` | 达到业务设定目标 | 危急值场景目标应显著高于普通场景 |
| 事后验证 | `plan_size.py --from-result` | 已显著 / 还需多少条 / 增益太小不值得追量 | 两尺寸分别跑 |
| 温度 | `result.json.temperature` | 只在 calibration 拟合；金标集终评一次 | **两尺寸温度不同，不可互相套用** |
| 选型决策 | `compare --a <4b> --b <8b>` | 配对 bootstrap 差值与 CI，量化 4B 相对 0.8B 是否值得多花的钱 | 差值 CI 含 0 → 选 0.8B 省成本 |


**金标终评**：最终验收必须用留出的那份人工金标文件跑一次 `evaluate --remote <url>`（`KEV_REMOTE_API_KEY`），对 0.8B 与 4B **各跑一次**，确认线上数字与线下一致。

## 七、场景分期路线图（应对纯蒸馏的高风险）

**不能平铺 5 个场景** —— 纯蒸馏下最大失败模式是「闭环未验证就铺开，出问题时无法定位是数据问题还是闭环问题」。

| 期次 | 场景 | 尺寸安排 | 理由 |
| --- | --- | --- | --- |
| **一期** | 危急值复核 + 导诊分诊 | 危急值 **双轨**（0.8B + 4B 都跑，建立双尺寸基线与对比流程）；导诊 **4B 轨**为主，同时跑一次 0.8B 作为「0.8B 能力不足」的实证对照 | 危急值 noul/choice 是 Kev 强项且标签可规则化 → 程序化生成可拿零漂移标签；先在这里把双尺寸闭环（共享数据 → 各自 train → compare → 双端点部署）跑通 |
| **二期** | 用药/医保审核 + 护理质量管控 | **双轨** | 规则明确、选项可控，复用一期验证过的双尺寸闭环与生成器底座 |
| **三期** | 病历编码 ICD | **仅 4B** | 最难（长文本、大标签体系、罕见组合 + 需医学知识），0.8B 不适合；前两期的 token 预算经验与 `guidance` 写法可直接复用 |


跨期复用资产：`common.py`（state 渲染 / 最小对 / 阈值表 / 配额采样 / JSONL 写出）、双尺寸命令矩阵、验收门槛表、金标审计流程。新增场景 = 加一个 spec + 一个 generator 入口，不改 `common.py`。

## 八、上线灰度与回滚

**上线**：影子模式（只记录不生效，与人工结论比对）→ 人工复核（低置信 + 高风险类别强制复核）→ 灰度放量。医疗场景默认「模型建议 + 人工确认」，不建议无人工的自动处置。**双尺寸可分层**：先在低风险判定上放开 0.8B，高风险判定保持 4B + 人工。

**回滚手段**（按破坏性递增）：

1. `KEV_SERVE_RUN` 指回 `jaredpalmer/kev-0.8b` / `jaredpalmer/kev-4b` 并重新 `modal deploy` —— 模型级回滚，秒级；**双端点各自独立回滚，互不影响**（靠不同 `KEV_APP_NAME` 隔离）
2. 客户端 feature flag 关闭调用 —— 应用级回滚，不动服务
3. `modal app stop kev-cv-4b` / `kev-cv-8b` —— 单个端点下线
4. `teardown --run <name> --yes` / `--endpoint` / `--everything [--cache] --yes` —— 数据清理；**Modal secret 永不被脚本删除**，需手动 `modal secret delete`
5. 始终保留两个 baseline 端点作 fallback（空闲部署端点不花钱）

## 九、合规与隐私

- **PHI 脱敏**：姓名/证件/电话/住院号 → 哈希或占位符，且脱敏在**进入生成器之前**完成（生成器只接触已脱敏字段）
- **数据不出域**：`KEV_GEN_BASE_URL` 可指向本地 Ollama（`http://localhost:11434/v1`）实现蒸馏不出内网；否则需评估是否允许把结构化字段送到外部 API
- **模型永不公开**：`publish` 默认私有（`--public` 才公开），医疗模型**禁止** `--public`；优先用 Modal volume 承载 checkpoint
- **凭据**：key 存 Modal secret（`KEV_SERVE_SECRET` / `KEV_HF_SECRET`），不写入仓库
- **数据留存**：delta 体积参考 tarball 量级（0.8B 46 MB / 4B 131 MB），`teardown` 三档差异要在 runbook 写清
- spec 只含 schema 与规则表，**不含任何真实患者数据**

## 十、技术栈与目录

**技术栈**：JSON spec（严格遵循 `assets/workload.example.json` schema）+ Python 3 标准库生成器与编排脚本（零第三方依赖，与 skill 脚本的 stdlib-only 约定一致）+ pytest 离线测试 + Modal 托管训练/服务。**不引入任何新框架或依赖**。

**放置位置**：放 `docs/medical/`，**不污染 `skills/`**。理由：(a) `skills/` 有 `skills-lock.json` 打包边界；(b) `tests/test_skill_scripts.py` 依赖 `skills/kev-finetune/` 既有结构，零改动最安全；(c) `AGENTS.md` 强调 "one canonical home"，`docs/` 是研究文档的既有归属。

**双语取舍**：主文档以中文为主（受众是国内医疗信息化团队），沿用仓库 `*_CN.md` 徽章惯例但不额外产出英文版 —— spec 与生成器本身语言无关。

### 目录结构

```
kev/
├── docs/
│   └── medical/
│       ├── README.md                    # [NEW] 主方案（中文，总入口）。含中英切换徽章 + 文档导航。章节：① 双尺寸
│       │                                #   定位与基座纠偏（四层继承图 + 为何不能 --base + 0.8B 禁用清单）② 双尺寸
│       │                                #   共享数据架构（一份数据喂两个 init + compare 跨尺寸有效 + 命名规范）
│       │                                #   ③ 5 场景分期路线图（每期标注尺寸安排）④ 记录数核算表 ⑤ 数据采集体系
│       │                                #   （四来源 + 公开规则资源作为「已有数据」+ 纯蒸馏四道防线）⑥ 执行编排
│       │                                #   （双尺寸命令序列）⑦ 后续优化闭环 ⑧ 验收门槛表（含双尺寸差异列）
│       │                                #   ⑨ 上线灰度与回滚（双端点独立回滚）⑩ 合规与隐私
│       ├── data-format.md               # [NEW] 医疗数据格式定义。① token 硬约束（384/2048/1024，两尺寸相同）
│       │                                #   与中文阈值陷阱（STATE_CHARS_WARN=1400 是英文口径，须用 validate 实测）
│       │                                #   ② 对象形状 state schema（6-10 字段表 + 字段名对模型可见故须一致）
│       │                                #   ③ 5 场景 questions 逐一定义（含每场景 0.8B/4B 适用性标注）④ 软标签
│       │                                #   target 用法 ⑤ 病历编码两级拆分 ⑥ 日期字段预计算（规避 0.8B 弱项）
│       │                                #   ⑦ 提交前自检清单
│       ├── runbook.md                   # [NEW] 命令速查手册。覆盖：双基线 evaluate → plan_size（两尺寸）→ 程序化
│       │                                #   生成/蒸馏 → split_data(--holdout) → validate（两尺寸各一次）→ train
│       │                                #   （0.8B + 4B）→ pull → compare（跨尺寸 + 跨轮次）→ deploy（双 APP_NAME）
│       │                                #   → evaluate --remote 金标终评（两尺寸各一次）→ teardown 三档。每步：
│       │                                #   可复制命令 + 预期输出 + 判读要点 + 失败处置。排错：name 已存在、
│       │                                #   名字含点号、network error 残留容器、中文 state 超 384 token、
│       │                                #   rejected 计数异常、分布不均衡、0.8B 过度自信
│       ├── specs/                       # [NEW] 5 个场景 spec，**两尺寸共用**（schema 对齐 assets/workload.example.json）
│       │   ├── triage.json               #   导诊分诊：choice(科室 10-20) + noul(立即人工) + score(严重度)
│       │   ├── critical-value.json       #   危急值：noul(是否危急) + score(通知时限 4 级) + choice(依据项目)
│       │   ├── medication-review.json    #   用药/医保：choice(结论) + noul(药师复核) + choice(问题类型)
│       │   ├── icd-coding.json           #   病历编码（仅 4B）：choice(候选集内合理性) + noul(编码员复核)
│       │   └── nursing-quality.json     #   护理质控：choice(问题类型) + noul(是否上报) + score(严重度)
│       ├── generators/
│       │   ├── README.md                # [NEW] 生成器总览。共用底座工具、新增场景 3 步、确定性 seed 约定、
│       │   │                            #   与 generate_data.py 分工、**两尺寸共用同一份生成数据**的说明
│       │   ├── common.py                # [NEW] 共用底座（尺寸无关）。state 对象渲染 `key: value`；阈值表常量集中
│       │   │                            #   （便于临床专家 review）；minimal_pair() 最小对构造；边界加权采样；
│       │   │                            #   按选项配额采样保证每标签 ≥5%；日期字段预计算；带标签 JSONL 写出
│       │   │                            #   （ensure_ascii=False）；用 split_data.check_question 做输出前自检。stdlib
│       │   ├── gen_critical_value.py     # [NEW] 危急值（双尺寸主力）。采样检验项目与值域（血钾、肌酐、血糖、血气等），
│       │   │                            #   按阈值表派生 is_critical + 通知时限 + 依据项目；批量最小对
│       │   ├── gen_medication_review.py  # [NEW] 用药/医保（双尺寸主力）。采样药品/剂量/年龄/肾功能等，按说明书规则
│       │   │                            #   派生结论与问题类型；多规则命中取最高严重度；疗程/有效期字段预计算
│       │   ├── gen_triage.py            # [NEW] 导诊（4B 主力 + 0.8B 对照）。采样症状组合 → 科室映射，刻意构造多症状
│       │   │                            #   优先级冲突样本；派生是否需立即人工与严重度
│       │   ├── gen_nursing_quality.py   # [NEW] 护理质控（双尺寸主力）。按质控检查表条目与判定标准合成
│       │   ├── make_goldset.py          # [NEW] 金标集与双模型分歧审计。分层抽样输出人工审校池（--sample/--seed/
│       │   │                            #   --out）；两份独立标注结果的一致性比对，输出分歧索引与分歧率
│       │   └── run_matrix.py            # [NEW] 双尺寸编排驱动器。`--scenario <name> --sizes 8b,4b [--dry-run]
│       │                                #   [--start-from <step>]`：按 plan_size → 生成 → split → validate×2 →
│       │                                #   train(0.8B) → train(4B) → compare → 双端点 deploy 顺序执行，fail-fast，
│       │                                #   校验运行名合规（拦截点号）；--dry-run 只打印将执行的命令序列
│       │                                #   （供人审阅与 CI 校验）。stdlib only
│       └── ...
└── tests/
    └── test_medical_generators.py       # [NEW] stdlib only、no network（对齐 test_skill_scripts.py 约定）。覆盖：
                                         #   阈值两侧标签正确翻转、最小对只差一个字段、边界加权采样确实落在阈值附近、
                                         #   每选项占比 ≥5%、生成记录通过 check_question、spec 与生成器 question id/type
                                         #   一致、seed 确定性、**运行名合规（拒绝 0.8b 含点号，接受 8b/4b）**、
                                         #   **run_matrix --dry-run 输出的命令序列完整且参数合法**
```

## 关键实现注意事项

- **零改动上游**：不修改 `skills/kev-finetune/` 任何文件。医疗侧全部通过 spec + 外部生成器 + 外部编排脚本适配。
- **输出即校验**：生成器写出前统一走 `split_data.check_question`，与蒸馏路径共用同一套校验；`run_matrix.py` 额外用 `kev_modal.py::check_name` 的同一正则校验运行名。
- **确定性**：全部生成器与 `run_matrix.py` 用 `random.Random(seed)`，同 seed 同产出。
- **性能**：生成器纯本地 O(n) 采样，无网络无 GPU；蒸馏是唯一网络瓶颈，靠 `--concurrency 4` 与「边到边追加可续跑」控制。
- **数据不入仓**：spec 与生成器只含 schema 与规则表，不含任何真实患者数据；真实/金标数据落在 `data/`（git-ignored）。
- **验证命令**：
- `uv run python -m pytest tests/test_medical_generators.py -q`
- 全量 unit 套件不回归（`uv run --extra serve python -m pytest tests/test_unit.py ... tests/test_skill_scripts.py tests/test_medical_generators.py -q`）
- 端到端 dry-run：生成 50 条 → `split_data.py` 仅校验（不落盘分区）确认 0 problems → `plan_size.py` 核对记录数与方案表格一致 → `run_matrix.py --dry-run` 核对双尺寸命令序列

## 工作项分解

1. **medical-specs-format** —— `docs/medical/data-format.md` + `specs/` 下 5 个场景 workload.json（尺寸无关，两轨共用）
2. **medical-generators** —— `generators/` 共用底座 + 五个场景生成器 + 金标审计 + 双尺寸编排驱动器 `run_matrix.py`
3. **medical-tests** —— `tests/test_medical_generators.py`（含运行名合规与 `run_matrix --dry-run` 校验）并接入 CI unit job
4. **medical-main-plan** —— `docs/medical/README.md` 主方案（含双尺寸章节）
5. **medical-runbook** —— `docs/medical/runbook.md` 双尺寸命令速查与排错
6. **verify-end-to-end** —— 端到端 dry-run 验证生成数据、split 校验、plan_size 数字、双尺寸命令序列与全量单测无回归