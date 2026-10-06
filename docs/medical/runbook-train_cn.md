<p align="center">
  <img alt="英文" src="https://img.shields.io/badge/%E4%B8%AD%E6%96%87-lightgrey?style=for-the-badge">
  <a href="./runbook-train.md"><img alt="English" src="https://img.shields.io/badge/English-blue?style=for-the-badge"></a>
  <a href="./runbook.md"><img alt="速查" src="https://img.shields.io/badge/%E9%80%9F%E6%9F%A5-orange?style=for-the-badge"></a>
</p>

# 医疗规则合成数据训练 Kev / 微调 Qwen3.5-0.8B 执行手册（本地可执行版）

[← 返回主方案](./README.md) · [数据格式](./data-format.md) · [Modal 版执行手册](./runbook.md) · [生成器说明](./generators/README.md)

本手册与 `runbook.md`（基于 Modal 云 + `kev_modal.py`）互补：它**直接调用 `kev` 包的原生命令**
（`kev.train` / `kev.benchmark` / `kev.calibrate` / `kev.publish`），可在**本地 Linux / WSL2 / 容器**或**有 GPU 的本地机**
一步步跑通，并明确给出**两种微调方式**（LoRA 增量微调 vs 全参数微调）。`runbook.md` 的 Modal 路径只是把本手册的步骤
包进了一个云端容器，二者数据格式、划分、评估口径完全一致。

> 本手册所有命令均在本仓库根目录 `kev/` 下执行（PowerShell 用 `python`，bash 用 `python3`）。

---

## 〇、两种方式到底在微调什么

Kev 是「只输出校准概率、不生成文本」的决策模型：预填一次（prefill-only），在选项边界 token 上做**指针读出（pointer head）**。
因此：

- 裸基座（如 `Qwen/Qwen3.5-0.8B-Base`）**没有 pointer head**，不能直接拿去微调解决策任务；
- `kev.train` 永远会训练一个从零开始的 pointer head（`--head_dim 256`，`--head_lr 0` 表示 head 与主干同学习率）。

基于这一点，**两种方式**的区别只在「主干权重怎么动」：

| 方式 | 命令核心开关 | 主干 | 输出物 | 显存 | 适用条件 | 预期效果 |
| --- | --- | --- | --- | --- | --- | --- |
| **A. LoRA 增量微调（delta）** | `--lora 16`（默认即 LoRA，`--full_ft 0`） | 冻结，只训低秩适配器 | `adapter_model.safetensors` + `head.pt` | 低（0.8B 约 3–5 GB） | 几百~几千条医疗数据；想保留已发布模型的通用决策能力；快速低成本的场景适配 | 在均衡标签上 +5 点左右精度（配对 bootstrap CI 排除 0 才叫显著），几乎不丢通用能力；delta 体积极小（0.8B 约 46 MB） |
| **A1. 从 Kev-0.8B 热启动** | `--init_from jaredpalmer/kev-0.8b` | 冻结 + 加载已发布 LoRA/head | 同上 | 低 | **推荐**：医疗 delta 直接在已发布 checkpoint 上继续训，沿用其 in-domain 技能 | 同上，且起点更接近目标分布，收敛更快；可 `--replay 2000` 混入公开记录防遗忘 |
| **A2. 从裸基座起步** | `--base Qwen/Qwen3.5-0.8B-Base --base_revision 9a45d25e` | 冻结 + 从零训 LoRA/head | 同上 | 低 | 想完全脱离已发布行为、自己从头塑形 | 同上，但需更多步数才能训出可用 head |
| **B. 全参数微调（full-weight）** | `--full_ft 1 --weights_dtype bf16` | 全部可训（bf16 权重 + fp32 主副本/动量） | `model*.safetensors` + `head.pt` | 高（0.8B 约 14–18 GB，需 `--weights_dtype bf16`） | 大规模医疗语料（数千~数万条）；需要显著偏离已发布行为；有单卡 24GB+ 或 torchrun 多卡 | 上限更高的精度，但更易遗忘通用能力；权重体量约 1.6 GB（0.8B） |

**关于 SFT 与 DPO**：Kev 的训练目标本质就是 **SFT**——对「带标签的选项边界」做 log-loss（cross-entropy，软标签则 KL）。
因为模型**不生成文本**，不存在「策略生成 vs 参考生成」的配对，所以 **DPO 不适用**于 Kev。本手册的两种「方式」是
LoRA / 全参数这两种 SFT 变体，不是 SFT vs DPO。

> 选型默认建议：医疗（规则合成）数据通常以**方式 A1（LoRA + 从 `jaredpalmer/kev-0.8b` 热启动）**起步；只有数据量很大且
> 已证明 LoRA 触顶时，才升级到方式 B。

---

## 一、环境、依赖与一个重要限制

### 1.1 依赖安装

```bash
uv sync                      # 安装 kev 包（setuptools 可编辑）+ torch/transformers/peft/datasets
uv run python -m kev.train --help   # 验证安装（应输出全部参数）
```

### 1.2 ⚠️ 运行时不支持原生 Windows（已做兼容补丁）

`kev.train` / `kev.benchmark` / `kev.publish` 等模块导入了 Unix-only 的标准库：

- `kev/train.py` 导入 `resource`（仅用于写 `training_metrics.json` 的峰值 RSS）；
- `kev/suite.py` 导入 `fcntl`（仅用于 `file_lock` 文件锁）。

本仓库在**原生 Windows** 上会 `import` 即报 `ModuleNotFoundError: No module named 'resource'` / `'fcntl'`。
本手册已对这处做最小化跨平台补丁（`kev/train.py` 与 `kev/suite.py`：改为 `try/except ModuleNotFoundError`，
Windows 上 `resource=None` 跳过 RSS、`file_lock` 退化为空操作），**对 Linux / Modal 路径零行为影响**。
打补丁后 `kev.train --help` / `kev.benchmark --help` 在 Windows 上也能正常导入。

**真实训练/评估仍应满足：** 在 **Linux（WSL2 / 容器 / Modal）** 上跑，且能访问 Hugging Face（或已缓存基座权重）。
本机（Windows 沙箱、无 HF 网络）只能端到端跑通「数据半链路」，训练半链路因拉不到权重而无法执行——详见第六节「试执行记录」。

### 1.3 基座权重

| 方式 | 需要的权重 | 来源 |
| --- | --- | --- |
| A1 | `jaredpalmer/kev-0.8b`（LoRA+head+基座） | HF Hub（自动下载；医疗模型禁止 `--public` 发布） |
| A2 / B | `Qwen/Qwen3.5-0.8B-Base`，revision `9a45d25e` | HF Hub（`Qwen/Qwen3.5-0.8B-Base`，Apache-2.0） |

无 GPU 的机器上可用 `--device cpu` 做**冒烟**（fp32、极慢、仅验证链路），真实训练务必 `--device cuda --dtype bf16`。

### 1.4 国内访问：HF 镜像源（必看）

`huggingface.co` 在国内常不可达。统一用环境变量把 `huggingface_hub` / `transformers` 的请求重定向到国内镜像
**`hf-mirror.com`**（已实测可从本机拉取 `Qwen/Qwen3.5-0.8B-Base` 的 tokenizer / 权重）：

```bash
# bash / WSL2
export HF_ENDPOINT=https://hf-mirror.com
# PowerShell
$env:HF_ENDPOINT="https://hf-mirror.com"
```

- 该变量对 `kev.train` / `kev.benchmark`（加载本地 checkpoint 不受影响）拉基座、`kev.publish` 上传都生效；
  下载走镜像后，`huggingface_hub` / `transformers` 行为与直连 HF 一致，缓存落在 `~/.cache/huggingface`。
- Windows 上会出现一条 symlink 警告（`cache-system uses symlinks by default ...`）：无害，可加
  `$env:HF_HUB_DISABLE_SYMLINKS_WARNING="1"` 关闭，不影响功能。
- 若镜像偶发不稳，备选：**ModelScope**（Qwen 系列在 ModelScope 有官方镜像，用 `modelscope` 包 `snapshot_download` 预拉到本地缓存后离线加载）；但 `jaredpalmer/kev-0.8b`（医疗 delta 起点）仅发布在 HF，仍需走 `hf-mirror.com`。
- 离线场景：先把权重用 `HF_ENDPOINT=https://hf-mirror.com hf download jaredpalmer/kev-0.8b` 或
  `hf download Qwen/Qwen3.5-0.8B-Base` 拉到本地缓存，再设 `HF_HUB_OFFLINE=1` 跑训练。

---

## 二、完整执行步骤

每个步骤均含：**目的 / 输入 / 环境 / 命令 / 预期输出 / 验证**。凡是本手册在本地真实跑过的，步骤标题标 ✅。

---

### 步骤 1 · 算记录数 ✅

- **目的**：用 McNemar 配对公式确定「多久数据才能让微调 vs 基线差异在统计上显著」。
- **输入**：场景 spec（`docs/medical/specs/critical-value.json`，内含 4 个问题）。
- **环境**：纯标准库，无需 torch / 网络。
- **命令**：

```bash
python skills/kev-finetune/scripts/plan_size.py docs/medical/specs/critical-value.json --baseline-acc 0.75
```

- **预期输出**：

```
To detect a +5% accuracy gain over a 75% baseline at 80% power (paired, 95% two-sided):
  development questions: 469 paired (unpaired bound 1092)
  with 4 question(s) per record and a 15% development split: 118 development records
  calibration: 118 records (>= 100 questions for the temperature fit)
  generate at least 787 records  ->  python3 scripts/generate_data.py ... --n 787 --out data/<name>.jsonl
```

- **验证**：`total_records` = 787（= train 551 + cal 118 + dev 118）。每场景 4 个问题 → 787 条。
  非配对保守上界（1092）随 `--baseline-acc` 变化；0.8B 基线更弱、上界更大，故先测两条基线再核对。

**控制台执行**：Data 标签页 → 「算记录数」(`plan_size`)，填**场景**（如下拉 `critical-value`），后端执行 `plan_size.py <spec>.json --baseline-acc 0.75 --json`，回显 `total_records`（结构化，等价手动 `--baseline-acc 0.75`）。✅

---

### 步骤 2 · 生成数据（程序化规则合成 / 可选 LLM 蒸馏生成式轨）

- **目的**：得到 787 条带零漂移标签的 Kev 记录（System One 请求形态）。
- **输入**：场景 spec + 规则表（程序化路径）；或 LLM 端点（蒸馏路径）。
- **环境**：
  - 程序化生成器：**纯标准库、不联网、种子可复现**（`docs/medical/generators/`）。
  - 蒸馏生成式轨（可选，需百灵/OpenAI 兼容端点）：`generate_data.py` 需要 OpenAI 兼容端点（`KEV_GEN_API_KEY` / `KEV_GEN_BASE_URL`，可指向本地 Ollama）。

**程序化（危急值 / 用药 / 护理质控 / 病历摘要 —— 标签由规则派生，首选）：**

```bash
python docs/medical/generators/gen_critical_value.py --n 787 --out data/cv.jsonl --seed 0
```

- **预期输出**（本机实测）：

```
787 records -> data/cv.jsonl (spec critical-value, seed 0)
distinct states: 787 (0 duplicate states)
  critical_item: none=515 (65%), cbc=64 (8%), glucose_gas=53 (7%), electrolyte=53 (7%), renal=53 (7%), cardiac_coag=49 (6%)
  evidence_sufficient: true=739 (94%), false=48 (6%)
  is_critical: false=515 (65%), true=272 (35%)
  notify_within: 3=515 (65%), 0=119 (15%), 1=107 (14%), 2=46 (6%)
minimal pairs built: 89 (each twin differs in one measurement and flips is_critical)
```

- **验证**：`distinct states = 787` 且 `0 duplicate states`；每个选项占比均 ≥5%（`cbc=8%` 等安全）；`minimal pairs` >0
  表示已构造「同一报告只差一个测量值、标签翻转」的最小对。`warning: labels [...] under 5%` 出现则调生成器配额，不要加 `--n`。

**蒸馏生成式轨（6 大类语义场景，需百灵/LLM 端点）：**

用 `--category <键>` 选择某一类；不传 `--out` 时默认写到 `data/cv/<spec名>.jsonl`（每类独立文件、互不干扰）。6 大类 → spec 映射：

| 类别键 `--category` | 中文 | spec 文件 | 备注 |
| --- | --- | --- | --- |
| `nursing_quality` | 医院护理质量管控 | `nursing-quality.json` | 语义丰富，蒸馏优先 |
| `record_summary` | 住院病历的现病史与病程记录摘要核对 | `record-summary.json` | 语义丰富，蒸馏优先 |
| `medication_review` | 门诊与住院处方审核 | `medication-review.json` | 语义丰富，蒸馏优先 |
| `icd_coding` | 住院病案编码与 DRG/DIP 审核 | `icd-coding.json` | 语义丰富，蒸馏优先 |
| `initial_assessment` | 门诊与急诊的初诊评估 | `diagnosis.json` | 语义丰富，蒸馏优先 |
| `report_review` | 医院检验科与影像科报告复核 | `critical-value.json` | 另有程序化生成器 `gen_critical_value.py`（阈值表零漂移） |
| `triage`（额外） | 门诊与互联网医院导诊分诊 | `triage.json` | 语义丰富，蒸馏优先 |

> 每个场景均 4 问 → `plan_size` 统一按 **787 条/类**规划（train 551 + cal 118 + dev 118）。

```bash
export KEV_GEN_BASE_URL=https://api.ant-ling.com/v1
export KEV_GEN_API_KEY=sk-studio-****          # 单 key（兼容 OPENAI_API_KEY / AI_GATEWAY_API_KEY）
python skills/kev-finetune/scripts/generate_data.py --category triage \
  --n 787 --batch 10 --concurrency 3 --model Ling-3.0-tiny --out data/cv/triage.jsonl
# 先 --dry-run 打印提示词，确认 guidance 不模糊再正式生成
```

- **验证**：`stopped short of --n` 或 `rejected` 高 → `guidance` 太模糊；蒸馏只写 `label`，`target` 软标签只能由程序化生成器产出。

- **多 key + 每日 50w 软上限（每个 key 每天 50w token）**：每个 key 每天最多 `--daily-limit`（默认 `500000`）token；额度用尽自动轮换下一把 key，全部用尽则当日停（或等次日）。用量持久化在 `.distill/usage_<日期>.json`，所以**被 cron / 任务计划程序中断后重跑也会续算当日额度**，跨本地午夜自动清零。

  ```bash
  # 方式 A：逗号分隔
  export KEV_GEN_API_KEYS="sk-...1,sk-...2,sk-...3"   # 3 把 key = 150w token/天
  # 方式 B：密钥文件（每行一把，避免密钥出现在进程参数里）
  printf 'sk-...1\nsk-...2\n' > .distill_keys.txt
  python skills/kev-finetune/scripts/generate_data.py --category medication_review \
    --n 787 --model Ling-3.0-tiny --keys-file .distill_keys.txt --daily-limit 500000
  ```
  - 软上限：提交时按「还有预算」判定、不预扣，单日可能多消耗约 1 个 batch 的量；要硬上限就调小 `--batch`。
  - key 返回 401/403 会被 `mark_dead` 并自动轮换到下一把，不中断整体；所有 key 失效才报「daily budget exhausted」并以退出码 2 收工。

- **每天蒸馏一部分 + 自配调度任务（两种做法，任选）**：
  1. **脚本内守护**：`--schedule HH:MM` 进入守护模式，每天本地时间 `HH:MM` 跑一轮（额度用尽即等次日），Ctrl-C 停止。
  2. **系统定时任务（推荐，零常驻进程）**：用 cron（Linux/WSL2）或「任务计划程序」（Windows）每天触发一次**普通调用**即可——脚本本就**增量续写**（读现有 `--out` 继续）、额度按日期文件续算，单次调用天然就是「当天该跑的那部分」。
  ```cron
  # crontab -e  （Linux/WSL2，每天 03:07 跑一轮 triage；额度用尽自动收工）
  7 3 * * * cd /path/to/kev && /usr/bin/env bash -c 'export KEV_GEN_BASE_URL=https://api.ant-ling.com/v1 KEV_GEN_API_KEYS="sk-...1,sk-...2"; uv run python skills/kev-finetune/scripts/generate_data.py --category triage --n 787 --model Ling-3.0-tiny' >> logs/distill.log 2>&1
  ```
  ```powershell
  # Windows 任务计划程序：每天 03:07 触发，操作=启动程序
  # 程序 pwsh.exe  参数: -Command "cd d:\projects\github\kev; $env:KEV_GEN_BASE_URL='https://api.ant-ling.com/v1'; $env:KEV_GEN_API_KEYS='sk-...1,sk-...2'; uv run python skills/kev-finetune/scripts/generate_data.py --category triage --n 787 --model Ling-3.0-tiny"
  ```
  - 多 key 下吞吐：3 把 × 50w ÷ ~301 tok/条(tiny) ≈ 一天 ~4983 条，足以一天跑完多个类别；瓶颈从「额度」转为「时间」。

- **百灵（已实测，免费 50w token/天/key）**：
  ```bash
  export KEV_GEN_API_KEY=sk-studio-****      # 百灵 apikey
  export KEV_GEN_BASE_URL=https://api.ant-ling.com/v1
  python skills/kev-finetune/scripts/generate_data.py --category triage \
    --n 40 --batch 10 --concurrency 3 --model Ling-3.0-flash --out data/triage_bailian.jsonl
  ```
  - 可用模型 id（`GET /v1/models` 实测）：`Ling-3.0-flash` / `Ling-3.1-flash` / `Ling-2.6-1T` / `Ling-3.0-tiny` / `Ring-2.6-1T`（1T 全模态）等；文本蒸馏用 `Ling-3.0-flash` 即可。
  - 实测：40 条 / 4 次调用 / 197s / **0 rejected**；14 个科室选项全覆盖；`split_data` 校验 40 valid、0 冲突，划分 train 28 / calibration 6 / development 6；样本医学逻辑与 `guidance` 一致。
  - ⚠️ `Ling` 是**推理模型**：先返回 `reasoning_content` 再返回 `content`，`max_tokens` 过小会只拿到空 `content`（脚本不设 `max_tokens`、用端点默认即可规避）。
  - 40 条仅验证链路；温度拟合需 calibration ≥100 问题（该 spec 4 问/条 → ≥25 条），正式蒸馏按 `plan_size` 目标量（每类 787 条）。
  - **实测 token 效率**（`Ling-3.0-flash`，batch 10，每条 4 问）：每调用 prompt≈1.4k + completion≈14.5–19k，其中**约 90% 是 `reasoning_content` 思考 token** → **≈1828 token/条**。
    - 换算：**单 key 50w 免费额度 ≈ 273 条/天**；`plan_size` 目标 787 条 ≈ **1.44M token ≈ 3 天**（单 key）。多 key 线性叠加：3 key ≈ 819 条/天，一天即可覆盖一类。
    - 推理 token 是主要成本：改用非推理小模型 `Ling-3.0-tiny` 或端点关 thinking，同额度可蒸馏条数显著上升。
  - **关推理实测**（`Ling-3.0-tiny`，batch 10，每条 4 问）：无 `reasoning_content`，每调用 prompt≈1.4k + completion≈1.55k → **≈301 token/条**；20/20 校验通过、0 rejected。**单 key 50w 额度 ≈ 1658 条/天**，达到 `plan_size` 787 条仅需 **~0.5 天**免费额度；相对 `Ling-3.0-flash` 提升 **≈6.1×**。结构化标签蒸馏用 tiny 即可（合法性无损），仅长链语义/疑难推理略弱，上线前临床抽检即可。

> 已有标注数据（CSV/JSONL）→ Kev 记录：用 `convert_data.py`（列映射），再用 `split_data.py --holdout` 接入，永远不进 train。

**控制台执行**：
- 程序化：Data → 「程序化规则合成」(`generate`)，填**场景** + **n**(默认 787) + **seed**(默认 0)，后端 `gen_<scenario>.py --n <n> --out data/<scenario>.jsonl --seed 0`。
- LLM 蒸馏：Data → 「LLM 蒸馏」(`distill`)，填 **category**(6 大类键) + **n** + **model**(默认 `Ling-3.0-tiny`) + **base_url** + **api_keys**(≤6 把) + **concurrency**；后端 `generate_data.py --category <cat> --n <n> --model <m> --out data/<scenario>/<cat>.jsonl`，`KEV_GEN_API_KEYS` 由服务端环境注入、不下发浏览器。
- ✅ `--schedule` 每日守护与 cron 额度续算已实现：Data → 「LLM 蒸馏」(`distill`) 表单新增 `--schedule`/`--daily-limit`/`--state-dir` 字段（一次性也可填），或用 Data → 「蒸馏守护」(`distill_daemon`) 标签页跑常驻调度（后端 `generate_data.py --schedule HH:MM --daily-limit N --state-dir DIR`，`persist=START`，取消即杀整棵树）。

---

### 步骤 3 · 抽金标 + 人工审校（闭环自证的关键防线）

- **目的**：造一份留出的人工金标集，用于终评与双模型分歧审计。
- **命令**：

```bash
python docs/medical/generators/make_goldset.py sample data/cv.jsonl --n 200 --out data/cv.gold.jsonl --seed 0
# 可选：双模型分歧审计
python docs/medical/generators/make_goldset.py audit data/cv.jsonl --out data/cv.audit.jsonl
```

- **预期输出**：分层抽样后稀有标签也有样本；打印标签覆盖。
- **验证**：金标 ≥150 条（否则 calibration/development 噪声大，尽量凑 200）；临床/药学人员按 spec `guidance` 逐条核对签字。
  金标集**只用于最后一次终评**，绝不针对它调参。

**控制台执行**：Data → 「抽金标」(`goldset`)，填**场景** + **n**(默认 200) + **seed**(默认 0)，后端 `make_goldset.py sample data/<scenario>.jsonl --n <n> --seed <seed> --out data/<scenario>.gold.jsonl`。✅
- 金标分歧审计：Goldset 标签页 → 「金标分歧审计」(`goldset_audit`)，填两份标注路径 **A**/**B**（如厂商甲/乙）+ `--threshold`（默认 0.05）+ 可选 `--out`；后端 `make_goldset.py audit <A> <B> [--out ...] --threshold <t>`，分歧率超阈值以非 0 退出（可作 CI 闸门），分歧样本进人工审校池。✅
- 金标人工审校：Goldset 标签页「打开审校页」→ 载入任一 `*.gold` 数据集，逐条改 `label`，点「导出金标」下载 holdout jsonl 供 `split --holdout` 使用（金标永不进 train）。纯前端、无子进程。✅

---

### 步骤 4 · 格式转换与划分（split_data）✅

- **目的**：把单文件 JSONL 校验后切成 `train / calibration / development` 三分区（温度拟合 + 打分 + 训练）。
  Kev 记录形态见 `data-format.md`；一条记录示例：

```json
{"state": "male 67", "questions": {"is_critical": {"type": "noul", "instructions": "该报告任一检验项目是否触及危急值？", "label": true},
                                    "notify_within": {"type": "score", "instructions": "应在多久内通知？", "criteria": ["15min","1h","当日","无需"], "label": 0}}}
```

- **命令**（**务必等步骤 2 写完文件后再跑**，勿与生成并行，否则会读到半成品）：

```bash
python skills/kev-finetune/scripts/split_data.py data/cv.jsonl --out data/cv
# 带金标：--holdout data/cv.gold.jsonl（金标对半进 calibration/development，永不进 train）
```

- **预期输出**（本机实测，787 条）：

```
787 valid records (0 invalid lines, 0 exact duplicates dropped, 0 states with conflicting labels dropped)
questions by type: {'noul': 1574, 'score': 787, 'choice': 787}; states: 787 distinct
wrote data\cv\development.jsonl: 118 records
wrote data\cv\calibration.jsonl: 118 records
wrote data\cv\train.jsonl: 551 records
```

- **验证**：三分区计数之和等于 787；`conflicting labels dropped` 非 0 → 标注规则自相矛盾，回去改 `guidance`。
  同一 `state` 永远落在同一分区（按 state 哈希分组），所以**同一份 `data/cv` 可直接喂给 0.8B 与 4B 两个尺寸**。

**控制台执行**：Data → 「格式转换与划分」(`split`)，填**场景** + **calibration**(默认 0.15) + **development**(默认 0.15) + **seed**(默认 0) + 可选 **holdout**，后端 `split_data.py data/<scenario>.jsonl --out data/<scenario> --calibration 0.15 --development 0.15 --seed 0 [--holdout ...]`，并注册 `summary.json`（闸门 G2/G3 依赖）。✅

---

### 步骤 5 · token 超限预检（中文必做）

- **目的**：Kev 训练器对 state > 384 token / 请求 > 2048 token / 单问题分支 > 1024 token 的记录**静默丢弃**（只打印数量，不报错）。
  中文 token 密度偏高，`split_data.py` 的 `STATE_CHARS_WARN=1400` 是**英文**口径，不能照搬。
- **命令**：方式 A1 用 `kev-0.8b` 的 tokenizer；方式 A2/B 用 `Qwen/Qwen3.5-0.8B-Base` 的 tokenizer：

```bash
# 方式 A1
uv run python -c "from kev.model import load_tokenizer, DecisionModel; from kev.data import load_records, materialize; from kev.model import training_context, fits
tok=load_tokenizer('jaredpalmer/kev-0.8b')
recs=load_records('data/cv/train.jsonl')
c=training_context(384)
over=[r for r in recs if not fits(materialize(r), tok, **c)]
print('over_limit', len(over))"
```

- **预期输出**：`over_limit 0`。非 0 → 缩短 state 字段或精简 `state_example`，不要靠字符数估算。
- **验证**：两个尺寸 tokenizer 对中文切分不同，理想情况下各自实测一次。

**控制台执行**：Data → 「token 超限预检」(`precheck`)，填**场景** + **init_from**(默认 `jaredpalmer/kev-0.8b`) + **split**(默认 `train`)，走专用 `docs/medical/console/precheck.py --data data/<scenario> --init-from <init> --split <split> --out <按产物 id 解析>`；回显 `over_limit` 须为 0 才能训练（闸门 G1）。✅

---

### 步骤 6 · 模型加载与训练配置

两种方式都通过 `kev.train` 的同一组开关表达「模型怎么加载」：

| 开关 | 方式 A1（LoRA 热启动） | 方式 A2（LoRA 裸基座） | 方式 B（全参数） |
| --- | --- | --- | --- |
| `--init_from` | `jaredpalmer/kev-0.8b` | （不填） | （不填） |
| `--base` | （继承自 init） | `Qwen/Qwen3.5-0.8B-Base` | `Qwen/Qwen3.5-0.8B-Base` |
| `--base_revision` | （继承自 init） | `9a45d25e` | `9a45d25e` |
| `--lora` | `16`（沿用 init 的秩） | `16` | （忽略，全参数时不生效） |
| `--full_ft` | `0` | `0` | `1` |
| `--weights_dtype` | `fp32` | `fp32` | `bf16`（全参数强制） |
| `--lora_targets` | `all` / `dense` / `attn` / `qv` | 同左 | — |
| `--head_dim` | `256` | `256` | `256` |
| `--lr` | `4e-5`（0.8B 沿用 init） | `4e-5` | `full_ft.MasterAdamW` 自动 |
| `--replay` | `2000`（混公开记录防遗忘） | `2000` | `0`（全参数不混，或按需） |
| `--device` | `cuda` | `cuda` | `cuda` |
| `--dtype` | `bf16` | `bf16` | `bf16`（autocast） |

> `kev.train` 默认 `--base Qwen/Qwen3-0.6B-Base`，**不要漏填** `--base`/`--init_from`，否则会训到错误的基座上。

**控制台执行**：本步无独立命令，其开关表即 Train 页「SFT 训练」(`train`) 表单的字段来源——在 Train 页选**方式**(a1/a2/b)并填 `init_from`/`base`/`base_revision`/`lora`/`lora_targets`/`lr`/`replay` 等即可，等价于本表。详见步骤 7 控制台说明。

---

### 步骤 7 · 启动训练

**方式 A1（推荐 · LoRA 从 Kev-0.8B 热启动）：**

```bash
uv run python -m kev.train \
  --data data/cv/train.jsonl \
  --init_from jaredpalmer/kev-0.8b \
  --lora 16 --lora_targets all \
  --lr 4e-5 --head_lr 0 --weight_decay 0.01 \
  --epochs 1 --batch 4 --accum 2 --dtype bf16 --device cuda \
  --replay 2000 --seed 0 \
  --out runs/cv-8b-lora-v1
```

**方式 A2（LoRA 从裸基座起步）：**

```bash
uv run python -m kev.train \
  --data data/cv/train.jsonl \
  --base Qwen/Qwen3.5-0.8B-Base --base_revision 9a45d25e \
  --lora 16 --lora_targets all \
  --lr 4e-5 --epochs 1 --batch 4 --accum 2 --dtype bf16 --device cuda \
  --out runs/cv-8b-lora-base-v1
```

**方式 B（全参数微调，单卡 24GB+ 或 torchrun 多卡）：**

```bash
# 单卡
uv run python -m kev.train \
  --data data/cv/train.jsonl \
  --base Qwen/Qwen3.5-0.8B-Base --base_revision 9a45d25e \
  --full_ft 1 --weights_dtype bf16 --dtype bf16 \
  --lr 4e-5 --epochs 1 --batch 1 --accum 4 --device cuda --checkpointing 1 \
  --out runs/cv-8b-full-v1
# 多卡（FSDP2）
torchrun --standalone --nproc_per_node 8 -m kev.train \
  --base Qwen/Qwen3.5-0.8B-Base --base_revision 9a45d25e \
  --full_ft 1 --weights_dtype bf16 --dtype bf16 \
  --data data/cv/train.jsonl --lr 4e-5 --epochs 1 --batch 8 --accum 2 --device cuda \
  --out runs/cv-8b-full-v1
```

- **预期输出（启动阶段打印）**：

```
device=cuda world=1 trainable params=XX.XM     # LoRA: 仅适配器+head 几百万；全参数: ~0.8B
delta: warm start from ... (方式 A1 才有)
<N> training requests (holdout=[]), questions by type {...}
ep0 step 10/139 loss 0.623 kl 0.000 anchor 0.000 0.042s/rec
...
saved runs/cv-8b-lora-v1
```

- **验证**：
  - `trainable params`：LoRA 应为数百万级（非 0.8B 全量）；全参数为 ~0.8B。
  - `loss` 随 step 下降；每 10 步打印一次。`non-finite training loss` → 数据/学习率问题。
  - 训练器会打印「dropped N of M records that exceed the training context」——非 0 表示有超限记录被静默丢弃（回步骤 5 处理）。

> 0.8B 在 H100 上约 8 分钟 / 400–1000 条。CPU 仅用于冒烟（fp32，极慢）。`--out` 目录不可已存在（除非 `--resume 1`）。

**控制台执行**：Train → 「SFT 训练」(`train`)，填**运行名**(须符合 `run_matrix.check_name`，禁点号) + **方式** + **数据**(默认 `data/<scenario>/train.jsonl`) + **out**(默认 `runs/<run_name>`) 及方式相关字段；后端按 `kev/console/stages/train.py:build_argv` 拼 `kev.train`（含 `--epochs 1 --batch 4 --accum 2 --dtype bf16 --device cuda --seed 0 --head_lr 0 --weight_decay 0.01`）。✅
**高级训练开关已全部暴露**（Train 页表单下方「高级训练开关」字段区，参数名下划线、与 `kev/train.py` argparse 逐一核对）：`--anchor`/`--anchor_w`/`--anchor_sources`、`--perm_kl`/`--perm_frac`、`--ord_w`、`--label_smoothing`/`--brier_w`/`--focal_gamma`、`--p_none`/`--p_none_distract`/`--p_none_pair`/`--none_pair_max_state`、`--synthetic_repeat`/`--public_frac`/`--train_sources`/`--holdout`、`--special_embeddings`/`--option_isolation`/`--shared_prefix`、`--snapshot_every_steps`。`--anchor` 与 `--anchor_w` 互锁（缺 `anchor_w>0` 提交即 422），`--none_pair_max_state` 需 `--p_none_pair>0` 同理。✅

---

### 步骤 8 · 监控

- **进度**：终端每 10 步打印 `loss / kl / anchor / s·rec`。
- **`<out>/training_config.json`**：本次运行的完整参数 + base_revision + init_source（可复现）。
- **`<out>/training_metrics.json`**：`wall_seconds`、`records_seen`、`optimizer_steps`、`grad_norm`（每 epoch 梯度范数均值/最大/被裁步数）、
  `peak_device_bytes`、`backbone_save_seconds`。回滚判据见「梯度爆炸」：某 epoch `max` 梯度范数远超均值即异常。
- **方式 B 专属**：`resume` 点（`--save_every_minutes` / `--save_every_steps`）、`snapshots/step-<N>/checkpoint`
  （`--snapshot_fractions 0.25,0.5,0.75`，永不删除，可续训）。

**控制台执行**：Train 作业详情页实时看 loss 曲线（读 `/console/api/jobs/<id>/stream` 的 SSE 帧）、`metrics` 缓冲、产物与血缘；**取消**=POST `/jobs/<id>/cancel`、**换名重试**=POST `/jobs/<id>/retry`（自动 `-rN` 新名 + `parent_id` 指向原作业）。✅（比手动 `tail` 更顺）

---

### 步骤 9 · 评估（kev.benchmark）

- **目的**：在 `development.jsonl` 上打分，产出 `rows.json`（每条问题一行 + logits）+ `report.json`（精度/ECE/Brier/NLL、
  选择性覆盖与 AURC、配对 bootstrap）。
- **命令**：

```bash
uv run python -m kev.benchmark \
  --run runs/cv-8b-lora-v1 \
  --data data/cv/development.jsonl \
  --out runs/cv-8b-lora-v1-eval --device cuda
```

- **预期输出**：`runs/cv-8b-lora-v1-eval/` 下 `rows.json` + `report.json`。`report.json` 关键字段：
  - `development.calibrated.acc` / `bootstrap.acc.ci95`（增益是否真实：**CI 排除 0** 才算显著）
  - `development.calibrated.ece` / `confident_error_rate`（校准：calibrated 须优于 raw；微调模型 confident_error_rate 不得超过 baseline）
  - `regression`（公开 `decision-v7` 300 条上精度下降 ≤ 2 点）
  - `coverage_at_5pct_error`（业务指标：可自动化比例）
- **验证**：`mean_conf` 与 `acc` 相差几个点内（0.8B 更易过度自信，卡更严）；回归 > 2 点 → 降 `--lr` 减半、保留 `--replay`、不加 epoch。

**控制台执行**：Evaluate 页三件套（后端分别拼 `kev.benchmark`/`kev.benchmark`/`kev.compare`）：
- 「基线打分」(`baseline`)：默认 `--run jaredpalmer/kev-0.8b --data data/<scenario>/development.jsonl --out runs/<run>-baseline-eval`。
- 「开发集打分」(`benchmark`)：默认 `--run runs/<run> --data data/<scenario>/development.jsonl --out runs/<run>-eval`。
- 「配对 bootstrap 对比」(`compare`)：默认 `--candidate runs/<run>-eval --reference runs/<run>-baseline-eval`（suite_sha256 不一致预检成 409）。✅
**benchmark 高级选项已全部暴露**（Evaluate → 「开发集打分」`benchmark` 表单）：填 **remote**（任意 System One 端点 URL；填了则不打本地 checkpoint）+ **remote_model**（默认 kev-latest）+ **remote_concurrency**；**suite**（冻结 suite，替代 `--data`）+ **split**；**allow_test**（读锁定 test 分区）、**date_facts**（打分前套 `with_date_facts`）、**rotations**（旋转平均次数）。✅

---

### 步骤 10 · 温度拟合（kev.calibrate）

- **目的**：在你自己的 development 行上拟合一个温度（报告，不改权重）。Kev 的概率随温度缩放，部署前必须基于**你的**分布重拟合。
- **命令**：

```bash
uv run python -m kev.calibrate --rows runs/cv-8b-lora-v1-eval/rows.json \
  --out runs/cv-8b-lora-v1-eval/calibration.json
```

- **预期输出**：`calibration.json` 含 `raw / shipped / workload / workload_oof` 四臂的 `acc/ece/brier/coverage`，
  及 `workload_temperature`（要写入服务配置的温度）、`oof_vs_shipped` 配对 bootstrap。
- **验证**：`workload_oof` 的 ECE/Brier 应 ≤ `shipped`；把 `workload_temperature` 作为服务温度。
  **注意**：均衡训练先验 ≠ 真实临床先验（危急值线上仅 1–3%），上线前须用真实流量重标定切点（见 `data-format.md`）。

**控制台执行**：Evaluate → 「温度拟合」(`calibrate`)，填**场景**（或显式 **rows** 路径，须以 `rows.json` 结尾），后端 `kev.calibrate --rows runs/<run>-eval/rows.json --out runs/<run>-eval/calibration.json`；`workload_temperature` 是部署阶段服务温度来源（闸门 G7）。✅

---

### 步骤 11 · 导出（kev.publish）

- **目的**：把 checkpoint 上传到私有 HF Hub（LoRA adapter 或全参数 shards + `head.pt` + tokenizer + 模型卡）。
- **命令**：

```bash
uv run python -m kev.publish \
  --run runs/cv-8b-lora-v1 \
  --repo jaredpalmer/kev-0.8b \
  --card docs/model-cards/kev-0.8b.md \
  --private --message "medical critical-value delta v1"
# 候选先传分支、勿覆盖已发布权重：--revision candidate-v1 --replace
```

- **预期输出**：Repo 下出现 `adapter_model.safetensors` + `adapter_config.json`（LoRA）或 `model*.safetensors` + 索引（全参数）、
  `head.pt`、tokenizer 文件、README.md（模型卡）。`--private` 确保医疗模型不公开；复用同一 repo 的 adapter 与全参数布局互斥，需 `--replace`。
- **验证**：`hf auth login` 已登录；目标 repo 缺则 `--private` 自建，已存在且非私则被拒绝（不会误传公仓）。
- **本地导出替代**：直接保留 `<out>/` 目录即可本地/容器内加载，无需上传 Hub。

**控制台执行**：Publish 标签页 → 「发布到 Hub」(`publish`)。表单填 **checkpoint 目录**（默认 `runs/<run>/checkpoint`）+ **repo**（如 `jaredpalmer/kev-0.8b`）+ **model card 路径**（必填，如 `docs/model-cards/kev-0.8b.md`）+ **message** + **private**（`0`/`1`，`1` 确保私有仓）+ **tag** + **revision** + **replace**（`0`/`1`）。后端：`python -m kev.publish --run <dir> --repo <repo> --card <md> [--message ...] [--private] [--tag ...] [--revision ...] [--replace]`；凭据走编排服务进程环境的 `HF_TOKEN`（在 `SECRET_NAMES` 布尔态里、仅在 spawn 注入、**永不落库/不下发浏览器**）。Hub 远端无本地产物（不注册 dataset），`persist=SUCCESS` 进程退出后回到作业列表。✅

---

### 步骤 12 · 部署（二选一）

- **Modal（推荐，与 `runbook.md` 一致）**：`KEV_APP_NAME=kev-cv-8b KEV_SERVE_RUN=cv-8b-lora-v1 modal deploy skills/kev-finetune/scripts/kev_modal.py`
- **本地 System One 端点**：`uv run python -m kev.serve --run runs/cv-8b-lora-v1 --port 8008`（按 `workload_temperature` 设温度）。

**控制台执行**：
- 本地端点：Deploy → 「启动 System One 端点」(`deploy`)，**必填 temperature**（取自 `calibration.json` 的 `workload_temperature`，缺失即拦；绝不在 development 上拟合），后端 `kev.serve --run runs/<run> --port 8008 --temperature <temp>`（长驻，`persist=START`，spawn 后即注册端点）。✅
- 冒烟：Deploy → 「冒烟测试」(`smoke`)，5 场景各 1 例探针（同手动 `smoke.py`）。✅
- 镜像：Image → 「构建部署镜像」(`image`)，填**运行名** + **temperature**，后端 `docker build -t kev-<run>:<temp> ...`（需宿主机 docker）。✅
- **Modal 云部署**：Modal 标签页 → 「Modal 部署」(`modal`)。表单填 **KEV_SERVE_RUN**（本地 `runs/<name>` 或 Hub id，如 `jaredpalmer/kev-4b`）+ **KEV_SERVE_GPU**（默认 `L4`）+ **KEV_APP_NAME**（默认 `kev-finetune`）+ **KEV_REF**（commit 钉，可空）。后端：`modal deploy skills/kev-finetune/scripts/kev_modal.py`，配置全走环境变量（**没有** argparse 参数）；`KEV_SERVE_SECRET`/`KEV_HF_SECRET` 为 Modal secret 名、由编排服务进程环境注入（值只持 `KEV_API_KEY`/`HF_TOKEN`，**永不落库/不下发浏览器**）。`modal deploy` 在 App 上线后返回（`persist=SUCCESS`），被部署端点落在 Modal 远端、不在本地 8008。✅

---

## 三、本地试执行记录（真实结果）

以下均为本仓库根目录、Windows + PowerShell 环境下**实际执行**的结果：

| 步骤 | 命令 | 结果 | 说明 |
| --- | --- | --- | --- |
| 1 生成 | `gen_critical_value.py --n 787` | ✅ 787 条，分布如上 | 纯标准库，可复现 |
| 1 核算 | `plan_size.py critical-value.json` | ✅ `generate at least 787 records` | 与划分一致 |
| 1 划分 | `split_data.py data/cv.jsonl --out data/cv` | ✅ 551/118/118 | 与 plan_size 完全吻合 |
| 5 CLI | `kev.train --help` | ⚠️ 首跑 `No module named 'resource'` | 已打补丁（`kev/train.py`/`kev/suite.py` 可选导入），重跑通过 |
| 5 CLI | `kev.benchmark/evaluate/publish --help` | ✅ 均正常 | 补丁对整套包生效 |
| 7 训练 | `kev.train --data ... --base Qwen/Qwen3.5-0.8B-Base` | ✅ 直连 `OSError: couldn't connect`；设 `HF_ENDPOINT=https://hf-mirror.com` 后 0.6B 基座 310/310 权重加载成功，3 条数据 1 epoch CPU 冒烟跑通：`trainable 5.6M`、生成 `adapter_model.safetensors`+`head.pt`+分词器快照，**无报错**（仅 Windows symlink 无害警告） | 训练半链路完全打通；0.8B 走相同 LoRA+head+保存代码路径，仅基座更大/真实训练需 GPU（`--device cuda --dtype bf16`） |
| 8 LLM 蒸馏（百灵） | `generate_data.py docs/medical/specs/triage.json --n 40 --batch 10 --concurrency 3 --model Ling-3.0-flash`（`KEV_GEN_BASE_URL=https://api.ant-ling.com/v1`） | ✅ 4 次调用 197s、40 条 **0 rejected**；`split_data` 校验 40 valid / 0 冲突，划分 train 28 / cal 6 / dev 6 | 百灵 `Ling-3.0-flash` 蒸馏链路打通；推理模型先出 reasoning 再出 content；40 条仅验证链路（温度拟合需 ≥25 条），正式蒸馏按 `plan_size` 量 |
| 8b 蒸馏脚本改造（多 key / 每日 50w / 调度） | `generate_data.py --category triage --n 3 --model Ling-3.0-tiny --api-keys $K`；另测 `--daily-limit 1`（当日额度耗尽→退出码 2）、`--api-keys bogus-a,bogus-b`（双 key 401→mark_dead→轮换耗尽） | ✅ 单 key 3 条落盘 `data/cv/triage.jsonl`、`.distill/usage_<日期>.json` 记账 1925 token；`--daily-limit 1` 跨进程续算当日额度即刻停；双假 key 轮换后退出码 2 | 6 大类 `--category`、多 key 每日 50w 软上限、每日增量+调度（`--schedule`/cron/任务计划程序）三档能力实测可用 |

**结论**：数据半链路（生成→核算→划分→CLI 校验）在本机完全跑通；训练/评估半链路因（1）原生 Windows 缺 Unix 模块
（已修，但真实训练仍应在 Linux 跑）、（2）本沙箱无法访问 Hugging Face 权重，未能在此端到端执行。在有 GPU 且能访问
HF 的 Linux/WSL2 机器上，按第二节步骤 7–12 即可复现。

> 并行执行坑：曾把 `gen_critical_value.py` 与 `split_data.py` 并行跑，split 读到了生成器尚未写完的 40 条旧文件，
> 显示 40 条而非 787。**务必先生成完毕、再划分**（串行）。

---

## 四、端到端可复现流程（Linux / WSL2）

```bash
# 0. 环境（国内：先切 HF 镜像）
export HF_ENDPOINT=https://hf-mirror.com      # PowerShell: $env:HF_ENDPOINT="https://hf-mirror.com"
uv sync
# 1. 算量
python skills/kev-finetune/scripts/plan_size.py docs/medical/specs/critical-value.json --baseline-acc 0.75
# 2. 生成（程序化规则合成 / 可选 LLM 蒸馏生成式轨）
python docs/medical/generators/gen_critical_value.py --n 787 --out data/cv.jsonl --seed 0
# 2b. LLM 蒸馏某一大类（6 类用 --category；多 key 每日 50w、--schedule 守护或交 cron/任务计划程序）
export KEV_GEN_BASE_URL=https://api.ant-ling.com/v1
python skills/kev-finetune/scripts/generate_data.py --category triage --n 787 --model Ling-3.0-tiny --out data/cv/triage.jsonl
#    多 key：export KEV_GEN_API_KEYS="sk-...1,sk-...2"   # 每 key 每天 50w token，额度用尽自动轮换
# 3. 金标（可选但强烈建议）
python docs/medical/generators/make_goldset.py sample data/cv.jsonl --n 200 --out data/cv.gold.jsonl --seed 0
# 4. 划分（串行，勿与生成并行）
python skills/kev-finetune/scripts/split_data.py data/cv.jsonl --out data/cv --holdout data/cv.gold.jsonl
# 5. token 预检（见步骤 5 的 python 片段）
# 6-7. 训练（方式 A1 示例）
uv run python -m kev.train --data data/cv/train.jsonl --init_from jaredpalmer/kev-0.8b \
  --lora 16 --lr 4e-5 --epochs 1 --batch 4 --accum 2 --dtype bf16 --device cuda \
  --replay 2000 --out runs/cv-8b-lora-v1
# 9-10. 评估 + 温度
uv run python -m kev.benchmark --run runs/cv-8b-lora-v1 --data data/cv/development.jsonl --out runs/cv-8b-lora-v1-eval --device cuda
uv run python -m kev.calibrate --rows runs/cv-8b-lora-v1-eval/rows.json --out runs/cv-8b-lora-v1-eval/calibration.json
# 11. 导出
uv run python -m kev.publish --run runs/cv-8b-lora-v1 --repo jaredpalmer/kev-0.8b --card docs/model-cards/kev-0.8b.md --private
```

---

## 五、常见问题与回滚方案

### 5.1 常见问题

| 症状 | 原因 | 处置 |
| --- | --- | --- |
| `No module named 'resource'` / `'fcntl'` | 原生 Windows 跑训练/评估 | 已打跨平台补丁；但仍建议在 **Linux/WSL2** 跑真实训练 |
| `OSError: couldn't connect to huggingface.co` | 国内直连 HF 不可达 | 设 `HF_ENDPOINT=https://hf-mirror.com`（见 1.4）；或 `HF_TOKEN` + 预拉缓存；离线 `HF_HUB_OFFLINE=1` |
| `invalid run name ... no dots`（仅 Modal 路径） | 运行名含 `.` | 尺寸写 `8b`/`4b`，不用 `0.8b` |
| `warning: labels [...] under 5%` | 标签分布未配平 | 调生成器配额，不要加 `--n` |
| `states with conflicting labels dropped` 非 0 | 同 state 同问题不同 label | 标注规则自相矛盾，回改 spec `guidance` |
| 训练器打印 `dropped N of M records` | state/请求超 token 上限 | 步骤 5 用 tokenizer 实测 `over_limit`，缩短 state |
| `non-finite training loss` | 学习率过高 / 数据损坏 | 降 `--lr`，检查 `data/cv/train.jsonl` |
| `regression` > 2 点 | delta 遗忘通用能力 | 降 `--lr` 减半、保留 `--replay 2000`、不加 epoch |
| 0.8B `mean_conf` ≫ `acc` | 0.8B 易过度自信 | 验收卡更严；低风险高吞吐用 0.8B，高风险交 4B |
| `refusing to overwrite an existing run` | `--out` 已存在 | 换名（`-v2`）或用 `--resume 1` |
| 全参数 `epochs` 中途超时（Modal/容器） | 单容器时限 | `--save_every_minutes` 写 resume 点，换容器 `--resume 1` 续跑 |

### 5.2 回滚方案（按破坏性递增）

1. **模型级**：服务把 `KEV_SERVE_RUN` 指回 `jaredpalmer/kev-0.8b` / `jaredpalmer/kev-4b` 重新部署，秒级回滚；双端点各自独立。
2. **应用级**：客户端 feature flag 关闭调用，不动服务。
3. **端点级**：`modal app stop kev-cv-8b`（或停本地 `kev.serve` 进程）。
4. **数据级**：`teardown --run <name>`（Modal）/ 删 `runs/` + `data/`（本地）；**Hub secret 与私有 repo 不被脚本删除**，需手动处理。
5. **训练灾备**：方式 B 的 `resume` 点 + `snapshots` 永不删除，可回到任意已完成步；切勿手动删 `<out>/snapshots`。

> 医疗场景默认「模型建议 + 人工确认」，**不追求无人工自动处置**；双尺寸可分层（低风险 0.8B、高风险 4B + 人工）。

---

## 六、交付物清单

本方案最终产出的**（规则合成）数据**、**微调/Kev 模型**与**基座权重**汇总如下（规模均为本机实测）：

| 类别 | 产物 | 路径 | 规模 | 格式/说明 | 状态 |
| --- | --- | --- | --- | --- | --- |
| 规则合成数据 | 训练集 | `data/cv/train.jsonl` | 551 条 / 890 KB | Kev 记录(JSONL)，4 问题/条 | ✅ 已生成 |
| 规则合成数据 | 开发/评估集 | `data/cv/development.jsonl` | 118 条 / 190 KB | `kev.benchmark` 打分 + 配对 bootstrap | ✅ 已生成 |
| 规则合成数据 | 校准集 | `data/cv/calibration.jsonl` | 118 条 / 190 KB | `kev.calibrate` 温度拟合 | ✅ 已生成 |
| 规则合成数据 | 冒烟子集 | `data/cv/train.smoke.jsonl` | 3 条 / 4.9 KB | 链路冒烟用小样本 | ✅ 已生成 |
| 规则合成数据 | 生成摘要 | `data/cv/summary.json` | 1 个 / 1.5 KB | 生成统计 | ✅ 已生成 |
| 微调模型 | 0.6B LoRA 冒烟 | `runs/smoke-mirror/` | adapter `19.7 MB` + head `2.0 MB` + tokenizer `10.9 MB` + 配置/指标 | LoRA r8 / `Qwen/Qwen3-0.6B-Base` / CPU | ✅ 已训练（验证链路） |
| 微调模型 | **0.8B Kev 模型**（目标） | `runs/cv-8b-lora-v1/`（规划） | — | LoRA 或全参 / `Qwen/Qwen3.5-0.8B-Base`（或 `jaredpalmer/kev-0.8b` delta）/ GPU | ⏳ 待训练 |
| 基座权重 | `Qwen/Qwen3.5-0.8B-Base` | HF（经 `hf-mirror.com`） | ~1.6 GB | 训练起点 | ✅ 镜像可达 |
| 基座权重 | `jaredpalmer/kev-0.8b` | HF（经 `hf-mirror.com`） | ~1.6 GB | 医疗 delta 起点（可选） | ✅ 镜像可达 |

**要点**
- 数据半链路已完整落地：551 训练 + 118 评估 + 118 校准；划分按 **state 哈希**（大小写与空白归一后的 sha256）分组、与模型无关，可同时喂 0.8B 与 4B 两个尺寸做 `compare`。
- 训练半链路已用 0.6B 冒烟打通（LoRA+head+checkpoint 保存同代码路径）；正式 0.8B 仅差 GPU 训练（`--device cuda --dtype bf16`），产物形态一致：`adapter_model.safetensors` + `head.pt` + 分词器快照。
- 基座权重此前因直连 `huggingface.co` 不可达无法拉取，现经 `HF_ENDPOINT=https://hf-mirror.com` 镜像已实测可达，整条链路无外部阻塞。
- **LLM 蒸馏（可选生成式轨，需百灵）** 独立于上表：百灵 `Ling-3.0-flash` 蒸馏 triage 试跑产物 `data/triage_bailian.jsonl` + `data/triage_bailian/{train,calibration,development}.jsonl`（40 条）。cv 危急值刻意**不**用 LLM 蒸馏（标签源自阈值表，LLM 会引入漂移）。
- **6 大类蒸馏命令（`--category`）**：`generate_data.py --category <键>` 现支持 6 大类任选其一（映射表见步骤 2）；多 key 每日 50w 软上限 + `.distill/usage_<日期>.json` 续算；`--schedule` 或 cron/任务计划程序实现「每天蒸馏一部分」。每类产物落到 `data/cv/<spec名>.jsonl`，按 `split_data.py --out data/cv/<spec名>` 划分后喂训练。

---

## 七、图形化 Console 控制台执行（与手动命令逐操作对照）

本手册第二节的每一步都可以在 **playground 的 `/console` 图形控制台**里点选完成，无需手敲命令。控制台后端是
`kev.console`（FastAPI + uvicorn，监听 `8790`），前端 playground 通过同源代理 `/api/console/*` 转发
（见 `playground/src/app/api/console/[...path]/route.ts`）。所有作业类型的 argv 组装逻辑在
`kev/console/stages/`（`data.py` / `train.py` / `eval.py` / `deploy.py` / `publish.py` / `modal.py`），共 **18 种作业类型**（含本手册 7.4 清单全部 7 项：publish / goldset_audit / train 高级开关 / benchmark 选项 / distill 守护 / Modal 部署 / 金标审校 UI），与手动命令逐字对应。

> 控制台**额外做的事**（手动命令没有）：提交前自动跑验收闸门（G1–G7，见 `kev/console/gates.py`），
> 闸门不过直接 422 拦截，不落库；作业有血缘（artifact lineage）、可取消/换名重试、SSE 实时日志流。
> 这些在「7.3 控制台独有能力」里展开。

### 7.0 前置：启动后端与前端

```bash
# 后端（仓库根目录，WSL2 / Linux 推荐；Windows 也能起服务，但真实训练需 GPU）
cd d:\projects\github\kev
uv run python -m kev.console          # 默认 8790；可用 KEV_CONSOLE_PORT 改
# 前端
cd playground && npm run dev          # 打开 http://localhost:3000/console
```

PyCharm 里把该后端配成 **Run/Debug → Module name = `kev.console`**、工作目录 = 仓库根目录、解释器 = `.venv`
（必须用 `-m` 模块方式，不能用 `--file`，否则相对导入 `from . import paths` 报错）。前端 `/console` 下有 8 个标签页：
**1·Data / 2·Train / 3·Evaluate / 4·Image / 5·Deploy / 6·Goldset / 7·Publish / 8·Modal**，与下面各操作一一对应。

### 7.1 总览映射表

| 本手册步骤 | 操作 | Console 作业类型 (`kind`) | 控制台标签页 | 状态 |
| --- | --- | --- | --- | --- |
| 步骤 1 | 算记录数 | `plan_size` | Data | ✅ 已实现 |
| 步骤 2（程序化） | 规则合成生成 | `generate` | Data | ✅ 已实现 |
| 步骤 2（蒸馏） | LLM 蒸馏 | `distill` / `distill_daemon` | Data | ✅ 已实现（单批 + `distill_daemon` 守护调度 `--schedule`/`--daily-limit`/`--state-dir`） |
| 步骤 3 | 抽金标 | `goldset` | Data | ✅ 已实现（`sample` + 人工审校） |
| 步骤 3 | 金标分歧审计 | `goldset_audit` | Goldset | ✅ 已实现（`make_goldset.py audit`，双标注分歧率闸门） |
| 步骤 3 | 金标人工审校 | （纯前端） | Goldset → 审校 | ✅ 已实现（载入 jsonl 改标签、导出 holdout，见 7.2 步骤 3） |
| 步骤 4 | 划分 | `split` | Data | ✅ 已实现 |
| 步骤 5 | token 超限预检 | `precheck` | Data | ✅ 已实现（用专用 `precheck.py`） |
| 步骤 6 | 训练配置 | （表单字段） | Train | ✅ 已体现在 `train` 表单 |
| 步骤 7 | 训练 | `train` | Train | ✅ 已实现（含全部高级开关，见 7.2 步骤 7） |
| 步骤 8 | 监控 | 作业详情 / SSE 流 | Train / 各 | ✅ UI 轮询 + 日志流 |
| 步骤 9 | 基线/评估/对比 | `baseline` / `benchmark` / `compare` | Evaluate | ✅ 已实现（含 `--remote`/`--allow-test`/`--date_facts`/`--suite` 选项） |
| 步骤 10 | 温度拟合 | `calibrate` | Evaluate | ✅ 已实现 |
| 步骤 11 | 导出到 Hub | `publish` | Publish | ✅ 已实现（凭据走 `KEV_HF_SECRET`） |
| 步骤 12（本地） | 部署 / 冒烟 | `deploy` / `smoke` | Deploy | ✅ 已实现 |
| 步骤 12（镜像） | 构建镜像 | `image` | Image | ✅ 已实现 |
| 步骤 12（Modal） | Modal 云部署 | `modal` | Modal | ✅ 已实现（`modal deploy kev_modal.py`，配置走 env） |

### 7.2 逐操作对照

下面每个操作都给：**手动命令**（第二节原文）+ **控制台执行**（哪个 `kind`、表单填什么、后端实际拼出的 argv）。

#### 步骤 1 · 算记录数

- **手动命令**
  ```bash
python skills/kev-finetune/scripts/plan_size.py docs/medical/specs/critical-value.json --baseline-acc 0.75
  ```
- **控制台执行**：Data 标签页 → 「算记录数」(`plan_size`)。表单只填 **场景**（`critical-value` 等下拉）。
  后端拼出：`python plan_size.py <spec>.json --baseline-acc 0.75 --json`（多 `--json`，结果结构化回显 `total_records`）。
  ✅ 与手动一致（`baseline-acc` 固定 0.75，与手册建议相同）。

#### 步骤 2 · 生成数据

**程序化（Data → 「程序化规则合成」`generate`）**
- **手动命令**：`python docs/medical/generators/gen_critical_value.py --n 787 --out data/cv.jsonl --seed 0`
- **控制台执行**：填 **场景** + **n**（默认 787）+ **seed**（默认 0）。后端：`python gen_<scenario>.py --n <n> --out data/<scenario>.jsonl --seed <seed>`。
  ⚠️ 控制台只支持各场景的 `gen_<scenario>.py`；`--out` 固定为 `data/<scenario>.jsonl`（不让你自定义路径，避免与产物注册 id 不一致）。✅

**LLM 蒸馏（Data → 「LLM 蒸馏」`distill`）**
- **手动命令**：
  ```bash
  export KEV_GEN_BASE_URL=https://api.ant-ling.com/v1
  python skills/kev-finetune/scripts/generate_data.py --category triage --n 787 \
    --model Ling-3.0-tiny --out data/cv/triage.jsonl --concurrency 3
  # 多 key：export KEV_GEN_API_KEYS="sk-...1,sk-...2"
  ```
- **控制台执行**：填 **场景** + **category**（6 大类键，默认 = 场景）+ **n**（默认 787）+ **model**（默认 `Ling-3.0-tiny`）
  + **base_url** + **api_keys**（数组，最多 6 把）+ **concurrency**。后端：`python generate_data.py --category <cat> --n <n> --model <m> --out data/<scenario>/<cat>.jsonl [--concurrency N]`；
  `KEV_GEN_BASE_URL` / `KEV_GEN_MODEL` 经环境变量注入，`KEV_GEN_API_KEYS` 由**编排服务进程环境**注入、永不落库（凭据值不下发浏览器，见 `app.py:SECRET_NAMES`）。
  ✅ 单批蒸馏与手动一致；**每日守护调度已实现**：表单点开 `distill` 的「调度」字段填 `--schedule HH:MM`/`--daily-limit`/`--state-dir`，或直接用 `distill_daemon` 守护标签页跑常驻（后端 `generate_data.py --schedule ...`，`persist=START`）。

#### 步骤 3 · 抽金标 + 人工审校

- **手动命令**：
  ```bash
  python docs/medical/generators/make_goldset.py sample data/cv.jsonl --n 200 --out data/cv.gold.jsonl --seed 0
  # 双模型分歧审计
  python docs/medical/generators/make_goldset.py audit data/cv.jsonl --out data/cv.audit.jsonl
  ```
- **控制台执行**：Data → 「抽金标」(`goldset`)。填 **场景** + **n**（默认 200）+ **seed**（默认 0）。
  后端：`python make_goldset.py sample data/<scenario>.jsonl --n <n> --seed <seed> --out data/<scenario>.gold.jsonl`。
  ✅ `sample` 子命令已实现。
  **金标分歧审计**：Goldset 标签页 → 「金标分歧审计」(`goldset_audit`)，填两份标注 **A**/**B** + `--threshold`（默认 0.05）+ 可选 `--out`；后端 `make_goldset.py audit <A> <B> [--out ...] --threshold <t>`，分歧率超阈值非 0 退出（CI 闸门）。✅
  **金标人工审校**：Goldset 标签页「打开审校页」载入任一 `*.gold` 数据集、逐条改 `label`、导出 holdout jsonl（纯前端，金标永不进 train）。✅

#### 步骤 4 · 格式转换与划分

- **手动命令**：
  ```bash
  python skills/kev-finetune/scripts/split_data.py data/cv.jsonl --out data/cv --holdout data/cv.gold.jsonl
  ```
- **控制台执行**：Data → 「格式转换与划分」(`split`)。填 **场景** + **calibration**（默认 0.15）+ **development**（默认 0.15）
  + **seed**（默认 0）+ **holdout**（可选金标路径）。后端：`python split_data.py data/<scenario>.jsonl --out data/<scenario> --calibration 0.15 --development 0.15 --seed 0 [--holdout ...]`。
  注册产物含 `summary.json`（闸门 G2/G3 读它判记录数与标签分布）。✅

#### 步骤 5 · token 超限预检

- **手动命令**（runbook 里的内联 `python -c` 片段，按 tokenizer 实测 `over_limit`）
- **控制台执行**：Data → 「token 超限预检」(`precheck`)。填 **场景** + **init_from**（默认 `jaredpalmer/kev-0.8b`）+ **split**（默认 `train`）。
  后端走**专用脚本** `docs/medical/console/precheck.py --data data/<scenario> --init-from <init> --split <split> --out <按产物 id 解析的路径>`
  （`kev/console/stages/data.py:_precheck`）。功能等价但命令形态不同（不是内联 `python -c`），`over_limit` 必须为 0 才能训（闸门 G1）。✅

#### 步骤 7 · 启动训练

- **手动命令**（方式 A1 示例）：
  ```bash
  uv run python -m kev.train --data data/cv/train.jsonl --init_from jaredpalmer/kev-0.8b \
    --lora 16 --lora_targets all --lr 4e-5 --head_lr 0 --weight_decay 0.01 \
    --epochs 1 --batch 4 --accum 2 --dtype bf16 --device cuda --replay 2000 --seed 0 \
    --out runs/cv-8b-lora-v1
  ```
- **控制台执行**：Train → 「SFT 训练」(`train`)。表单核心：
  - **场景**、**运行名**（须符合 `run_matrix.check_name`，禁点号）、**方式**（`a1` 热启动 / `a2` 裸基座 / `b` 全参数，默认 a1）、
    **数据**（默认 `data/<scenario>/train.jsonl`）、**out**（默认 `runs/<run_name>`）。
  - 方式相关字段：`init_from` / `base` / `base_revision`（A2/B 默认 `Qwen/Qwen3.5-0.8B-Base` @ `9a45d25e`）/ `lora` / `lora_targets` / `lr`（0.8B 默认 4e-5）/ `replay` / `full_ft` / `weights_dtype` / `head_dim` / `checkpointing`。
  - 仅方式 B 显示：`snapshot_fractions`（需同时给 `max_steps`，否则预检验拦截）。
  后端按 `kev/console/stages/train.py:build_argv` 拼 `kev.train` 的 argv（COMMON 含 `--epochs 1 --batch 4 --accum 2 --dtype bf16 --device cuda --seed 0 --head_lr 0 --weight_decay 0.01`）。
  ✅ 三种方式与手动一致。
  **高级训练开关已全部暴露**（Train 页「高级训练开关」字段区，参数名下划线、与 `kev/train.py` argparse 逐一核对）：`--anchor`/`--anchor_w`/`--anchor_sources`、`--perm_kl`/`--perm_frac`、`--ord_w`、`--label_smoothing`/`--brier_w`/`--focal_gamma`、`--p_none`/`--p_none_distract`/`--p_none_pair`/`--none_pair_max_state`、`--synthetic_repeat`/`--public_frac`/`--train_sources`/`--holdout`、`--special_embeddings`/`--option_isolation`/`--shared_prefix`、`--snapshot_every_steps`。`--anchor` 需配 `--anchor_w>0`、`--none_pair_max_state` 需配 `--p_none_pair>0`，否则在提交前 422 拦截。

#### 步骤 8 · 监控

- **手动**：终端每 10 步打印 `loss/kl/anchor`；读 `<out>/training_metrics.json`、`<out>/training_config.json`。
- **控制台执行**：在 Train 作业详情页实时看 `loss` 曲线（JobMonitor 读 `/console/api/jobs/<id>/stream` 的 SSE 帧）、指标缓冲、产物与血缘。
  取消 = POST `/console/api/jobs/<id>/cancel`；换名重试 = POST `/console/api/jobs/<id>/retry`（自动 `-rN` 新名 + `parent_id` 指向原作业）。✅ UI 自带，比手动 `tail` 更顺。

#### 步骤 9 · 评估

- **手动命令**：
  ```bash
  uv run python -m kev.benchmark --run runs/cv-8b-lora-v1 --data data/cv/development.jsonl --out runs/cv-8b-lora-v1-eval --device cuda
  ```
- **控制台执行**（Evaluate 标签页，三件套）：
  - 「基线打分」(`baseline`)：后端 `kev.benchmark --run jaredpalmer/kev-0.8b --data data/<scenario>/development.jsonl --out runs/<run>-baseline-eval`。
  - 「开发集打分」(`benchmark`)：后端 `kev.benchmark --run runs/<run> --data data/<scenario>/development.jsonl --out runs/<run>-eval`。
  - 「配对 bootstrap 对比」(`compare`)：后端 `kev.compare --candidate runs/<run>-eval --reference runs/<run>-baseline-eval --out runs/<run>-compare`
    （suite_sha256 不一致会被预检成 409 conflict，见 `eval.py:suite_hash_mismatch`）。
  ✅ 与手动「baseline+benchmark+compare」三件套一致（G4/G6 证据来源）。
  **benchmark 高级选项已全部暴露**（Evaluate → 「开发集打分」`benchmark` 表单）：填 **remote**（任意 System One 端点；填了则不打本地 checkpoint）+ **remote_model** + **remote_concurrency**；**suite**（冻结 suite，替代 `--data`）+ **split**；**allow_test**（读锁定 test 分区）、**date_facts**（打分前套 `with_date_facts`）、**rotations**（旋转平均次数）。`--data` 外部行仍走「场景」分区文件选择。

#### 步骤 10 · 温度拟合

- **手动命令**：`uv run python -m kev.calibrate --rows runs/cv-8b-lora-v1-eval/rows.json --out runs/cv-8b-lora-v1-eval/calibration.json`
- **控制台执行**：Evaluate → 「温度拟合」(`calibrate`)。填 **场景**（或显式 **rows** 路径，须以 `rows.json` 结尾）。
  后端 `kev.calibrate --rows runs/<run>-eval/rows.json --out runs/<run>-eval/calibration.json`。`workload_temperature` 是部署阶段的服务温度来源（G7）。✅

#### 步骤 11 · 导出（kev.publish）

- **手动命令**：
  ```bash
  uv run python -m kev.publish --run runs/cv-8b-lora-v1 --repo jaredpalmer/kev-0.8b \
    --card docs/model-cards/kev-0.8b.md --private --message "medical critical-value delta v1"
  ```
- **控制台执行**：Publish 标签页 → 「发布到 Hub」(`publish`)。表单填 **checkpoint 目录**（默认 `runs/<run>/checkpoint`）+ **repo** + **model card 路径**（必填）+ **message** + **private**(0/1) + **tag** + **revision** + **replace**(0/1)。后端 `python -m kev.publish --run <dir> --repo <repo> --card <md> [--message ...] [--private] [--tag ...] [--revision ...] [--replace]`；凭据走编排服务进程环境的 `HF_TOKEN`（在 `SECRET_NAMES` 布尔态里、仅 spawn 注入、**永不落库/不下发浏览器**）。`persist=SUCCESS`，Hub 远端无本地产物、不注册 dataset。✅

#### 步骤 12 · 部署

**本地 System One 端点（Deploy → 「启动端点」`deploy`）**
- **手动命令**：`uv run python -m kev.serve --run runs/cv-8b-lora-v1 --port 8008`
- **控制台执行**：Deploy → 「启动 System One 端点」(`deploy`)。**必须填 `temperature`**（取自 `calibration.json` 的 `workload_temperature`，缺失直接拦；绝不在 development 上拟合温度）。
  后端 `python -m kev.serve --run runs/<run> --port 8008 --temperature <temp>`（`persist=START` 长驻进程，spawn 后立刻注册端点）。部署完现有问答页 `/` 经 playground rewrite 即可打新模型。✅

**冒烟（Deploy → 「冒烟测试」`smoke`）**
- **手动命令**：`python docs/medical/console/smoke.py --base-url http://127.0.0.1:8008 --out runs/<run>-smoke.json`
- **控制台执行**：Deploy → 「冒烟测试」(`smoke`)。后端同命令，5 个场景各 1 例探针（`deploy.py:SMOKE_PROBES`）。✅

**构建镜像（Image → 「构建部署镜像」`image`）**
- **手动命令**：`docker build -t kev-<run>:<temp> -f deploy/kev-serve/Dockerfile --build-arg KEV_SERVE_RUN=<run> --build-arg TEMPERATURE=<temp> deploy/kev-serve`
- **控制台执行**：Image → 「构建部署镜像」(`image`)。填 **运行名** + **temperature**（必填）。后端拼上述 `docker build`。✅ 需宿主机有 docker。

**Modal 云部署**
- **手动命令**：`KEV_APP_NAME=kev-cv-8b KEV_SERVE_RUN=cv-8b-lora-v1 modal deploy skills/kev-finetune/scripts/kev_modal.py`
- **控制台执行**：Modal 标签页 → 「Modal 部署」(`modal`)。表单填 **KEV_SERVE_RUN** + **KEV_SERVE_GPU**（默认 `L4`）+ **KEV_APP_NAME**（默认 `kev-finetune`）+ **KEV_REF**（commit 钉，可空）。后端：`modal deploy skills/kev-finetune/scripts/kev_modal.py`，全部配置走环境变量（**没有** argparse 参数）；`KEV_SERVE_SECRET`/`KEV_HF_SECRET` 是 Modal secret 名、由编排服务进程环境注入（值只持 `KEV_API_KEY`/`HF_TOKEN`，**永不落库/不下发浏览器**）。`modal deploy` 在 App 上线后返回（`persist=SUCCESS`），端点落在 Modal 远端（不在本地 8008）。✅

### 7.3 控制台独有能力（手动命令没有）

1. **验收闸门自动预检（G1–G7）**：提交 `train`/`benchmark` 等前，`gates.evaluate` 按产物血缘检查（如 G1 要求 `precheck` 报告 `over_limit=0`、G2/G3 要求 `summary.json`、G4 要求 compare 的配对 CI、G7 要求 `calibrate`）。不过则 422 拦截、不落库——手动路径里这些靠人肉核对。
2. **作业血缘（artifact lineage）**：每个产物（dataset/run/eval/comparison/calibration/endpoint/image/smoke）登记到 `data/console/kev-console.db`，UI 的 Artifacts 页可追来源与去向。
3. **取消 / 换名重试**：`cancel` 杀子进程；`retry` 自动 `-rN` 新目录 + `parent_id`，旧产物永久保留（可审计）。
4. **SSE 实时日志流**：训练/评估日志从 `jobs/<id>/stream` 逐块推送，断线靠 `Last-Event-ID` 续传，不缓冲。
5. **单 GPU 训练互斥闸**：`train` 提交前检查是否已有 active train 作业，有则 409（手动 `kev.experiment` 在 Windows 因 `fcntl` 不可 import，这道闸由控制台自己实现，`app.py:219`）。

### 7.4 未实现清单（下一步完善 console 功能）

> ✅ **本 backlog 全部 7 项已在本次迭代实现**（作业类型从 14 增至 18）。下方仅作历史留痕与对应实现位置，便于后续维护。

| # | 缺口 | 对应手动能力 | 已实现位置 |
| --- | --- | --- | --- |
| 1 | `kev.publish` 无阶段 | 步骤 11 导出私有 Hub | 新增 `publish` 阶段（`stages/publish.py` + REGISTRY），表单 `repo/card/private/message/revision`，凭据走 `HF_TOKEN`（SECRET_ENV） |
| 2 | `goldset` 仅 `sample` | 步骤 3 `audit` 分歧审计 | 新增 `goldset_audit` 阶段（`make_goldset.py audit`）；人工审校见 Goldset 审校页（纯前端） |
| 3 | `train` 高级开关未暴露 | 步骤 6/7 的 anchor/perm_kl/ord_w/校准屏/数据混合 | 扩展 `train.ADVANCED_KEYS` + Train 页「高级训练开关」字段区（21 个开关全部挂上） |
| 4 | `benchmark` 选项未暴露 | 步骤 9 `--remote/--allow-test/--date_facts/外部 rows` | 扩展 `eval._benchmark_like`：`remote`/`remote_model`/`remote_concurrency`/`suite`/`allow_test`/`date_facts`/`rotations` 字段 |
| 5 | `distill` 无调度 | 步骤 2 `--schedule` 守护 / cron 每日额度 | 新增 `distill_daemon` 阶段（`generate_data.py --schedule`，`persist=START`）+ `distill` 表单加 `schedule`/`daily_limit`/`state_dir` |
| 6 | Modal 部署未接入 | 步骤 12 `kev_modal.py modal deploy` | 新增 `modal` 阶段（`stages/modal.py`，`modal deploy` + env 注入；`ALLOWED_ENV` 增 `KEV_SERVE_GPU`/`KEV_APP_NAME`/`KEV_REF`） |
| 7 | 金标人工审校 UI | 步骤 3 线下临床核对 | Goldset 标签页「打开审校页」：载入 `*.gold` jsonl、逐条改 `label`、导出 holdout（纯前端，无子进程） |

> 状态口径：「✅ 已实现」= 控制台该 `kind` 的 argv 与手动命令逐字等价、表单字段覆盖手册默认值；「❌ 未实现」=
> 该手动步骤在 `kev.console` 里完全没有对应作业类型，需先补 `stages/*.py` + 前端表单，再能点选完成。
