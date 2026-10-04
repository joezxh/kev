<p align="center">
  <a href="./README.md"><img alt="中文" src="https://img.shields.io/badge/%E4%B8%AD%E6%96%87-orange?style=for-the-badge"></a>
  <a href="../../skills/kev-finetune/README_CN.md"><img alt="English" src="https://img.shields.io/badge/English-blue?style=for-the-badge"></a>
</p>

# 医疗垂直行业 Kev 微调落地包

[数据格式 →](./data-format.md) · [执行手册 →](./runbook.md) · [生成器说明 →](./generators/README.md) · [skill 原始文档](../../skills/kev-finetune/SKILL.md) · [主题文档（已验证 / 未验证 / 上线前清单）→](../sft-medical_CN.md) · [蒸馏方案（百灵 + EasyDistill）→](../sft-distill_CN.md)

在医疗垂直行业，用 **Kev-0.8B** 与 **Kev-4B** 两个尺寸微调「不做生成、只输出校准概率」的决策模型，
覆盖导诊分诊、危急值复核、用药/医保审核、护理质量管控、病历编码五类决策。

## 一、先纠偏：「基于 Qwen3.5-xB」到底指什么

这是全案最容易被做错的一步。**不能直接微调裸基座**。

`skills/kev-finetune/SKILL.md` 的 Gotchas 明确写着：

> `--init-from` must be a Kev checkpoint (Hub id or a run name on the volume); base, LoRA rank and head size
> are read from it. **Do not pass `--base`.**

原因是 `kev.train` 需要 **pointer head**（在选项边界 token 上做指针读出），裸基座没有这个读出层。

已核实的基座映射（`docs/model-cards/kev-0.8b_CN.md` / `kev-4b_CN.md` 的 frontmatter）：

| | Kev-0.8B | Kev-4B |
| --- | --- | --- |
| Hub id | `jaredpalmer/kev-0.8b` | `jaredpalmer/kev-4b` |
| 基座 | `Qwen/Qwen3.5-0.8B-Base`（Apache-2.0） | `Qwen/Qwen3.5-4B-Base`（Apache-2.0） |
| 形式 | LoRA adapter + pointer head | LoRA adapter + pointer head |
| 权重修订 | `9a45d25e` | `139fdd94` |
| 发布温度 | 2.35 | 2.41 |

**双尺寸四层继承**：

```
Qwen/Qwen3.5-0.8B-Base（冻结）        Qwen/Qwen3.5-4B-Base（冻结）
  └─ jaredpalmer/kev-0.8b               └─ jaredpalmer/kev-4b
     T=2.35（公开数据拟合）                T=2.41
        └─ <scenario>-8b-v1                 └─ <scenario>-4b-v1
           医疗 delta，head.pt 内含            医疗 delta，head.pt 内含
           为医疗数据重拟合的 temperature         为医疗数据重拟合的 temperature
```

继承下来的三样东西：

- `lr=0.0` 时沿用各 init 自身的训练参数（**0.8B 是 4e-5，4B 是 2e-5**），`MAX_DELTA_LR = 5e-5` 是硬顶。
  0.8B 的默认学习率比 4B 更热，出现回归时两者都要减半但起点不同。
- `--replay 2000` 默认混入公开 `decision-v7` 记录保通用能力。
- 一次 `train` 跑完 delta 微调 → calibration 切片拟合温度 → **baseline 与微调模型各自**在用户 calibration
  切片重拟合温度（公平零样本对照）→ 打分 development → 配对 bootstrap → 公开数据 300 条回归检查。

> **0.8B 轨必须显式传 `--init-from jaredpalmer/kev-0.8b`**：`kev_modal.py` 的 `DEFAULT_INIT` 是 `jaredpalmer/kev-4b`。

## 二、双尺寸共享数据（本方案的核心设计）

**关键事实**：`split_data.py` 按 **state 哈希**（大小写与空白归一后的 sha256）分组划分，**与模型无关**。
所以同一份 `data/<scenario>/{train,calibration,development}.jsonl` 可以直接喂给两个不同尺寸的 init。

四条收益：

1. **蒸馏与标注成本只付一次**，两个模型共用同一份数据与同一份人工金标集。
2. **跨尺寸 `compare` 有效**：两次运行在同一份 `development.jsonl` 上打分，配对 bootstrap 成立 ——
   于是 0.8B 与 4B 的差距可以被**量化**，而不是拍脑袋选型。
3. **8 分钟快速闭环**：0.8B 训练约 8 分钟（H100），先用它跑通 spec / 阈值表 / 生成器是否正确，
   确认无误再用同一份数据跑 4B，避免在 15 分钟一轮的 4B 上浪费时间去发现阈值表写错了。
4. **成本分层路由与降级兜底**：两个端点共存，按风险分层；4B 冷启动期间 0.8B 可作 fallback。

### 两个尺寸不是替代关系

| 维度 | Kev-0.8B | Kev-4B |
| --- | --- | --- |
| 典型训练时长（400–1000 条，H100） | **~8 分钟** | ~12–15 分钟 |
| 默认 lr | 4e-5 | 2e-5 |
| 服务 GPU（fine-tune 默认） | `L4` | `L4`（有负载时 `L40S`） |
| 冷启动（空闲后首请求） | ~40 s | ~35 s |
| 预热模型耗时（6 题，新/重复状态） | 23 / 16 ms | 42 / 28 ms |
| delta 体积（参考 tarball） | 46 MB | 131 MB |
| breadth-v1 机会校正指数 | 23.3 | 38.0 |

**0.8B 的三条禁用项**（能力代价直接命中医疗场景，已核实）：

- **日期算术 0.35**（4B 0.65，27B 以下最弱项）→ 对策见[数据格式的日期预计算](./data-format.md#三日期字段预计算规避-08b-的已知弱项)
- **知识由基座决定**，MMLU-Pro 低至 0.230 → 不适合需要医学知识推断的病历编码
- **工具路由 When2Call 0.133，低于机会水平** → 禁止用于「是否需要调用外部系统/翻阅指南」这类决策

**0.8B 的额外校准风险**：发布说明记载，一次在留出数据集上的 refit 让 0.8B 在其 documents/skills 家族上
**校准更差并超出注册容差**，而 4B 没有改善（Brier 差异 −0.0001 [−0.0005, +0.0003]）。含义是
**0.8B 更容易过度自信**，验收时 `mean_conf` vs `acc`、`confident_error_rate` 两项要比 4B 卡得更严。

### 选型规则

| 尺寸 | 适用 | 场景 |
| --- | --- | --- |
| **0.8B 主力** | 标签可规则派生、规则封闭、选项集小、语义靠字段而非推断 | 危急值复核、用药/医保审核、护理质量管控 |
| **4B 主力** | 语义丰富、规则难穷举、表述高度多样 | 导诊分诊、病历编码 |

## 三、场景分期：不能平铺 5 个场景

纯蒸馏下最大的失败模式是「闭环还没验证就铺开，出问题时无法定位是数据问题还是闭环问题」。

| 期次 | 场景 | 尺寸安排 | 理由 |
| --- | --- | --- | --- |
| **一期** | 危急值复核 + 导诊分诊 | 危急值**双轨**（建立双尺寸基线与对比流程）；导诊**4B 为主**，同时跑一次 0.8B 作为「0.8B 能力不足」的实证对照 | 危急值标签可完全规则化 → 程序化生成可拿零漂移标签；先在这里把双尺寸闭环（共享数据 → 各自 train → compare → 双端点部署）跑通 |
| **二期** | 用药/医保审核 + 护理质量管控 | **双轨** | 规则明确、选项可控，复用一期验证过的闭环与生成器底座 |
| **三期** | 病历编码 ICD | **仅 4B** | 最难（长文本、大标签体系、罕见组合 + 需医学知识）；前两期的 token 预算经验与 `guidance` 写法可直接复用 |

`run_matrix.py` 内置了这条护栏：`icd-coding` 传 `--sizes 8b,4b` 会被直接拒绝。

## 四、记录数：多问题打包是成本杠杆

用 `plan_size.py` 的 McNemar 配对公式核算（`baseline_acc=0.75`、`min_gain=0.05`、`power=0.8`、
`regressions=0.05`、15%/15% 划分）—— 配对所需 development 问题数恒为 **469**：

| 每条记录的问题数 | dev 记录 | calibration 记录 | **总记录数** | train 记录 |
| --- | --- | --- | --- | --- |
| 1 | 469 | 469 | **3127** | 2189 |
| 2 | 235 | 235 | **1567** | 1097 |
| 3 | 157 | 157 | **1047** | 733 |
| 4 | 118 | 118 | **787** | 551 |
| 5 | 94 | 94 | **627** | 439 |

**本方案的 5 个 spec 都是 4 个问题/记录，因此每个场景 787 条**（train 551 / calibration 118 / development 118），
两个尺寸共用。

- **同一条 state 上多问几个问题，记录需求成比例下降** —— 这是 Kev 相对生成式微调的核心经济性，
  也是 5 个 spec 都设计成多问题打包（共享同一份 state）而不是一问题一数据集的原因。
- **双尺寸不改变记录数**（配对口径下公式只依赖 gain 与 regressions）。但**非配对保守上界依赖
  `--baseline-acc`**：baseline 0.75 → 1092，baseline 0.60 → 1468。0.8B 基线更弱、上界更大 ——
  这正是必须先实测两条基线、再分别核对 `plan_size` 的原因。
- calibration 记录数强制 ≥ 100 个问题（`plan_size` 中 `max(100/q, ...)`），温度拟合才稳定。
- 对照 `SKILL.md` 实测教训：400 条只得到 +0.6 点、CI ±6 点（毫无意义）；1050 条得到 +5.9 点、CI [+2.3, +9.7]。
  **纯蒸馏必须一次把量做够，不能靠增量补。**

**成本量级**（预算参考，非精确报价）：蒸馏 787 条用 gpt-4.1-mini 约 $0.20（口径 $0.25/1000 条），
最终数据集换 gpt-4.1 / claude-sonnet 数倍 —— **且这笔钱两个尺寸只花一次**。训练由脚本自行打印
`bound(gpu, timeout)` 上界（`GPU_HOURLY` 表：H100 3.95/h、L4 0.80/h、A10G 1.10/h…）。

> **降本方向（需实测）**：`--gpu` 是自由参数且有成本表，0.8B 在 L4/A10G 上训练可能大幅省钱
> （H100 8min ≈ $0.53 vs L4 8min ≈ $0.11），但 skill 只文档化了 H100 的典型时长，**L4 训练需自行验证**
> （DeltaNet kernel 与 bf16 支持）。

## 五、数据采集：四来源与纯蒸馏的质量闭环

用户当前**没有带标签数据**，所以主路线是蒸馏 + 程序化生成。但「已有数据」在医疗垂类有一个被低估的形态。

| 来源 | 医疗定位 | 实现 |
| --- | --- | --- |
| **④ 程序化生成** | **首选**。危急值/用药/医保/护理质控的标签是结构化字段的**确定性函数**；也是 0.8B 轨能成立的前提（0.8B 知识弱，必须靠零漂移标签而非语义推断） | [`generators/`](./generators/README.md) 的阈值表与规则引擎 |
| **② LLM 蒸馏** | 次选。导诊（科室归属语义丰富、规则难穷举）、病历编码（表述高度多样） | `generate_data.py` + 精雕 `guidance`/`variety`/`state_example` |
| **① 已有数据** | **接口预留 + 终评金标**。当下无标注记录，但一旦有即为最高价值资产 | `convert_data.py`；用 `split_data.py --holdout` 接入 |
| **③ 人工按 dry-run 自写** | 风格锚点 + 分歧审计池 | `generate_data.py --dry-run` 打印完整 prompt，人工按批作答（≤100 条） |

### 「已有数据」在医疗垂类的真实形态

**公开规则资源本身就是「已有数据」**：危急值标准、药品说明书禁忌/剂量上限、医保目录限制、ICD 编码规范、
护理质控检查表。这些是**规则**而非标注记录，但可被程序化引擎消费成**零漂移标签**。
这是医疗垂类相对通用 LLM 微调最大的结构性优势，也是双尺寸都能受益的原因。

### 纯蒸馏的四道防线

开发集也是合成的 ⇒ 闭环自证风险。四道防线：

1. **人工金标集**（`make_goldset.py sample` 分层抽 150–250 条，临床/药学人员按 `guidance` 判定签字），
   用 `split_data.py --holdout` 接入：对半分进 calibration 与 development，**永不进 train**，
   同时自动剔除与其共享 state 的合成行。**终评只跑一次。两个尺寸共用同一份金标集** ——
   这是双尺寸选型可信的前提。
2. **双模型分歧审计**（`make_goldset.py audit`）：两个厂商模型对同一批 state 独立标注，
   按**单题**分歧率设门槛（不看总体：3% 的平均可以藏住某一题 13% 的分歧）。分歧样本优先进人工审校池。
3. **`guidance` 迭代**：`errors.jsonl` 里每一类反复错误都对应 `guidance` 缺的一句话。
4. **稀有标签显式配额**：每个标签 ≥5%，且每个选项都要有机会作为正确答案出现。

## 六、执行编排

完整命令序列见[执行手册](./runbook.md)，或用编排驱动器一次跑完：

```bash
# 打印将执行的完整命令序列（先审阅再花钱）
python3 docs/medical/generators/run_matrix.py --scenario critical-value --sizes 8b,4b --dry-run

# 实际执行（fail-fast，中断后可用 --start-from <step> 续跑）
python3 docs/medical/generators/run_matrix.py --scenario critical-value --sizes 8b,4b --secret kev-serve-key
```

它按顺序执行 `plan_size → 生成 → 划分 → validate×2 → train(0.8B) → train(4B) → compare → 双端点部署`。
**同一份 `data/<scenario>/` 被两个尺寸共用**，这正是 `compare --a x-4b-v1 --b x-8b-v1` 有效的前提。

### 运行名规范（含一个真实陷阱）

`kev_modal.py` 的 `NAME` 是 `[A-Za-z0-9][A-Za-z0-9_-]{0,79}`，用 `fullmatch` 校验，
**不允许点号**，且 `/runs/<name>` 已存在会直接报错（名字不可变）。

- ✅ `critical-value-8b-v1`、`triage-4b-v2`
- ❌ `critical-value-0.8b-v1`（**含点号，会被 `check_name` 拒绝**）

所以尺寸标识统一写 `8b` / `4b`。`run_matrix.py` 在启动前就校验并用 `fullmatch`，
避免跑到 Modal 才报错（用 `match` 会错误地放行 `critical-value-0.8b-v1`，因为它匹配上了 `critical-value-` 前缀）。

### 两条不可违背的硬约束

- **绝不在 `development.jsonl` 上拟合温度**，也不反复针对它调参；金标集留到最后一次 `evaluate`。
- 校准与阈值**按 checkpoint 而定** —— 0.8B 与 4B 各有各的温度，每次重训都要分别重读两份 `result.json`。

### 错误代价不对称的安全设计

漏报危急值 ≫ 误报，因此**不取 argmax 自动处置**：

- noul 问题用**低阈值 + 强制转人工**的 fail-safe 规则，阈值取自各自的
  `development.calibrated.selective["0.5"|"0.8"].confidence_cutoff`
- 证据不足的记录用 `target` 软标签（`{"false":0.5,"true":0.5}`）教「无证据即无把握」
- **利用 Kev 的固有属性**：只输出概率、不生成 token ⇒ 结构上无幻觉诊断、无自由文本外泄 PHI
- **双尺寸分工即风险分层**：低风险高吞吐判定交 0.8B，高风险语义判定交 4B，阈值独立设定
- 人工复核作为最后一道闸，不追求 100% 自动化

## 七、验收门槛：可判定的数字

| 维度 | `result.json` 字段 | 判定 | 双尺寸差异 |
| --- | --- | --- | --- |
| 增益真实 | `bootstrap.acc.ci95` | **CI 排除 0** 才算真实增益；CI 含 0 说明数据不够或增益太小（改数据不是加量） | 两尺寸各自判定 |
| 校准更好 | `development.calibrated.ece` / `confident_errors` | calibrated 必须优于 raw；**微调模型 confident_error_rate 不得超过其 baseline** | **0.8B 卡更严**（已知更易过度自信） |
| 诚实 | `mean_conf` vs `acc` | 相差在几个点内；远高于 acc = 过度自信 | 0.8B 重点监控项 |
| 回归 | `regression` 段 | 公开 `decision-v7` 300 条上 accuracy 下降 **≤ 2 点** | 两尺寸分别判定 |
| 业务价值 | `development.calibrated.coverage_at_5pct_error` | 达到业务设定目标 | 危急值场景目标应显著高于普通场景 |
| 事后验证 | `plan_size.py --from-result` | 已显著 / 还需多少条 / 增益太小不值得追量 | 两尺寸分别跑 |
| 选型决策 | `compare --a <4b> --b <8b>` | 配对 bootstrap 差值与 CI，量化 4B 相对 8b 是否值得多花的钱 | 差值 CI 含 0 → 选 8b 省成本 |
| 温度 | `result.json.temperature` | 只在 calibration 拟合；金标集终评一次 | **两尺寸温度不同，不可互相套用** |

**金标终评**：最终验收用留出的人工金标文件跑 `evaluate --remote <url>`（`KEV_REMOTE_API_KEY`），
对 0.8B 与 4B **各跑一次**，确认线上数字与线下一致。

> **均衡先验 vs 真实先验**：`split_data.py` 要求每个标签 ≥5%，所以训练集是均衡的；而临床线上危急值
> 只占约 1–3% 的报告。**模型输出的概率条件在这个均衡先验上**，直接按绝对概率设阈值会在真实流量上过度报警。
> 上线前必须用真实流量重新标定阈值（详见[数据格式的均衡先验错配](./data-format.md#均衡先验与真实先验的错配上线前必读)）。

## 八、后续优化闭环

1. `pull --name <run>` 拿回 `result.json`、`errors.jsonl`、`train.log`
2. 读 `errors.jsonl` 前 20 行（最有把握的错误）—— `split_data.py` 已按置信度排序
3. 把每一类反复错误翻译成 spec `guidance` 里缺的那一句话
4. 程序化场景：改阈值表 / 规则表；导诊与编码：改 `guidance` + `variety` 后用 `generate_data.py` 定向补数据
5. 重新生成 → 重新划分 → 作为 `x-v2` 训练 → `compare --a x-v2 --b x-v1`

**收益排序**（`hill-climbing.md` 的结论）：

1. **更多更好的数据** —— 翻倍训练集通常胜过任何超参数
2. `--epochs 2`（1000+ 条且第 1 个 epoch 末尾 loss 仍在下降时）
3. 降 `--lr`（0.8B 从 4e-5、4B 从 2e-5 各自减半）、保留 `--replay 2000`、不加 epoch
4. `--replay 500`（数据量大且训练时间要紧时）
5. 数据推不动 4B 才考虑 `jaredpalmer/kev-9b`

## 九、上线灰度与回滚

**上线**：影子模式（只记录不生效，与人工结论比对）→ 人工复核（低置信 + 高风险类别强制复核）→ 灰度放量。
医疗场景默认「模型建议 + 人工确认」，不建议无人工的自动处置。**双尺寸可分层**：先在低风险判定上放开
0.8B，高风险判定保持 4B + 人工。

**回滚手段**（按破坏性递增）：

1. `KEV_SERVE_RUN` 指回 `jaredpalmer/kev-0.8b` / `jaredpalmer/kev-4b` 并重新 `modal deploy` —— 模型级回滚，秒级；
   **双端点各自独立回滚，互不影响**（靠不同 `KEV_APP_NAME` 隔离）
2. 客户端 feature flag 关闭调用 —— 应用级回滚，不动服务
3. `modal app stop kev-<scenario>-8b` / `-4b` —— 单个端点下线
4. `teardown --run <name> --yes` / `--endpoint` / `--everything [--cache] --yes` —— 数据清理；
   **Modal secret 永不被脚本删除**，需手动 `modal secret delete`
5. 始终保留两个 baseline 端点作 fallback（空闲部署端点不花钱）

## 十、合规与隐私

- **PHI 脱敏**：姓名/证件/电话/住院号 → 哈希或占位符，且脱敏在**进入生成器之前**完成
- **数据不出域**：`KEV_GEN_BASE_URL` 可指向本地 Ollama（`http://localhost:11434/v1`）实现蒸馏不出内网；
  否则需评估是否允许把**已脱敏的结构化字段**送到外部 API
- **模型永不公开**：`publish` 默认私有，医疗模型**禁止** `--public`；优先用 Modal volume 承载 checkpoint
- **凭据**：key 存 Modal secret（`KEV_SERVE_SECRET` / `KEV_HF_SECRET`），不写入仓库
- **数据留存**：delta 体积参考 tarball 量级（0.8B 46 MB / 4B 131 MB），`teardown` 三档差异见执行手册
- **spec 与生成器只含 schema 与规则表，不含任何真实患者数据**；真实/金标数据落在 `data/`（git-ignored）

## 十一、目录

```
docs/medical/
├── README.md               本文件：总入口与方案
├── data-format.md          医疗 state schema、questions 标签体系、token 预算、均衡先验错配
├── runbook.md              命令速查 + 排错（Modal 云路径）
├── runbook-train.md        本地可执行版：LoRA vs 全参数两种微调方式端到端手册（含试执行记录）
├── specs/                  5 个场景 workload spec（两尺寸共用，尺寸无关）
│   ├── critical-value.json      危急值复核（双轨主力）
│   ├── medication-review.json   用药/医保审核（双轨主力）
│   ├── nursing-quality.json     护理质量管控（双轨主力）
│   ├── triage.json              导诊分诊（4B 主力）
│   └── icd-coding.json          病历编码（仅 4B）
└── generators/
    ├── README.md            生成器总览与扩展指南
    ├── common.py            共用底座（尺寸无关）
    ├── gen_critical_value.py / gen_medication_review.py / gen_triage.py / gen_nursing_quality.py
    ├── make_goldset.py      金标抽样 + 双模型分歧审计
    └── run_matrix.py        双尺寸编排驱动器（--dry-run 打印命令序列）
```

**不修改 `skills/kev-finetune/` 任何文件** —— 该目录有 `skills-lock.json` 打包边界，
且 `tests/test_skill_scripts.py` 依赖其既有结构。医疗侧全部通过 spec + 外部生成器适配。


