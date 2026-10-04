# 医疗微调控制台（Kev Console）设计文档

- 日期：2026-10-04
- 状态：待评审
- 作者：brainstorming 会话产出

---

## 1. 背景与目标

`docs/medical/` 已有一套完整、已验证的医疗微调方案：12 步执行手册（`runbook-train_cn.md`）、5 个场景 spec、5 个程序化生成器、LLM 蒸馏轨、金标抽样、token 预检、双尺寸编排驱动器（`run_matrix.py`）。它的问题是**全靠人手工敲命令**：步骤之间靠复制粘贴传递参数，训练过程只能盯终端，跑完之后靠翻 JSON 文件判断是否达到医疗验收门槛。

本设计要在 `playground/`（Next.js 16）上建一个控制台，把这条 12 步管线变成可编排、可监控、可审计的界面，并补齐原手册缺失的三件事：

1. **训练过程的实时可见性**（原手册步骤 8 只有「每 10 步打印一行」）
2. **验收门槛的自动判定**（原手册 §七的表格是人读的，控制台把它变成闸门）
3. **产物血缘**（能回答「这个 checkpoint 的权重来自哪次合成、依据哪张阈值表」）

### 1.1 目标（可判定）

| 目标 | 判据 |
| --- | --- |
| 一次点完 5 个阶段 | 从空目录到 System One 端点在线，全程 UI 操作，参数自动传递 |
| 训练实时可见 | loss 曲线点间隔 ≤ 10 step，SSE 断线可续传 |
| 验收门槛自动化 | G1–G7 逐条判定，不通过时阻断下游并显示差多少 |
| 产物可追溯 | 任一 endpoint 可反查到训练它所用的 train.jsonl 及其生成作业 |
| 核心零改动 | `kev/train.py`、`kev/serve.py`、`kev/benchmark.py` 的 `git diff` 为空 |

### 1.2 非目标

- 不做多用户鉴权、角色、审计日志（见 §12）
- 不做远程 GPU 调度、不做 Modal 作业（`kev.rounds` 已覆盖 Modal 路径）
- 不做可视化流水线画布、不做阈值表编辑器
- 不做 OCR/PHI 自动脱敏（只告警，不自动改写）

---

## 2. 范围：5 个阶段 → 14 种作业

| 阶段 | 作业 kind | 底层命令 | 产物 |
| --- | --- | --- | --- |
| **1 数据蒸馏与合成** | `plan_size` | `skills/kev-finetune/scripts/plan_size.py` | — |
| | `generate` | `docs/medical/generators/gen_<scenario>.py` | `dataset:<sc>` |
| | `distill` | `skills/kev-finetune/scripts/generate_data.py` | `dataset:<sc>/<cat>` |
| | `goldset` | `docs/medical/generators/make_goldset.py` | `dataset:<sc>.gold` |
| | `split` | `skills/kev-finetune/scripts/split_data.py` | `dataset:<sc>/{train,calibration,development}` |
| | `precheck` | `docs/medical/console/precheck.py`（新增） | — |
| **2 模型微调训练** | `train` | `python -m kev.train` | `run:<name>` |
| **3 效果评测评估** | `benchmark` | `python -m kev.benchmark` | `eval:<name>` |
| | `baseline` | `python -m kev.benchmark --run <baseline>` | `eval:<name>-baseline` |
| | `compare` | `python -m kev.compare` | `comparison:<name>` |
| | `calibrate` | `python -m kev.calibrate` | `calibration.json` |
| **4 构建部署镜像** | `image` | `docker build` | `image:<tag>` |
| **5 部署与测试验证** | `deploy` | `python -m kev.serve --port 8008` | `endpoint:8008` |
| | `smoke` | `POST /v1/systemone` | — |

---

## 3. 关键决策记录

### 3.1 澄清问题的答案

| 问题 | 决策 | 理由 |
| --- | --- | --- |
| 训练在哪执行 | **本地 WSL2 / 容器** | `runbook-train_cn.md` §1.2 明确：真实训练必须 Linux+GPU；原生 Windows 缺 `resource`/`fcntl` |
| 进程编排归谁 | **Python 侧** | 复用 `kev/predictors.py:283` 的 `subprocess.Popen` + NDJSON 先例；进程、状态、取消、崩溃恢复与 kev CLI 同环境 |
| 落地范围 | **5 阶段一次设计，接口与目录契约优先** | 契约不一致是全链路返工的主要来源；每段真跑通的成本放到实施期 |
| 状态存储 | **SQLite** | 作业状态机 + 数据集注册表 + 产物路径落表；事务安全、增量更新干净 |
| 安全边界 | **本地单用户、无鉴权** | 只监听 `127.0.0.1`；凭据只从编排服务进程环境变量读；控制台不写入真实患者数据 |

### 3.2 架构方案选型

考察了三个方案：

| 方案 | 描述 | 结论 |
| --- | --- | --- |
| A 薄壳步骤驱动器 | 后端只做「SQLite 作业表 + `run_matrix.steps()` 展开 + SSE」 | **采纳为主体** |
| B Artifact 血缘图 | 一切皆产物与 transition | **采纳为数据模型**（`artifacts` + `lineage` 两表） |
| C Pipeline 定义驱动 + 向导 | 前端定义 pipeline，后端解释执行 | **采纳为首次引导入口** |

选 A 为主体的理由：`run_matrix.steps()` 已经是验证过的步骤驱动器，返回 `(name, argv, env)` 三元组并支持 `--dry-run` / `--start-from`，重造轮子会引入第二套参数语义。

补 B 的理由：医疗场景必须可追溯，而 `run_matrix` 只覆盖编排，不记录「这份数据来自哪次作业」。

补 C 的理由：新用户面对 14 种作业需要引导，但向导不能成为唯一入口（无法中途改参、无法回看历史）。

### 3.3 编排服务整体跑在 WSL2 内

「WSL2 执行」+「Python 侧编排」两个答案合起来推出一个更简单的实现：**编排服务本身跑在 WSL2 内**（与 torch 同环境）。

- 拉起 `kev.train` 就是**普通本地子进程**，不需要在 Windows 上 `spawn('wsl.exe', ...)` 去处理路径转义、shell 引号、stdio 转发
- Windows 侧 playground 通过 WSL2 的 `localhostForwarding` 访问 `127.0.0.1:8790`
- 沿用 `kev/experiment.py:288-303` 已验证的 tee 模式：逐行写 `train.log` 并 `flush()`

### 3.4 部署也做成作业，且复用现有 8008 rewrite

`kev.serve` 是长驻进程，正好符合作业模型：启动/停止/日志/崩溃恢复全部免费获得。

关键收益：`playground/next.config.ts` **已经有** `/kev/*` → `http://127.0.0.1:8008` 的 rewrite。部署一完成，现有问答页（`src/components/playground.tsx`）立刻能打新模型，**前端零改动**。

### 3.5 绝不给 `kev/train.py` 加结构化指标

训练期唯一实时数据源是 stdout 文本（每 10 step 一行）。`training_metrics.json` 只在训练完全结束时写一次（`train.py:672`），`--stop_after` 早退甚至不写。

看起来很自然的做法是在 `train.py:642` 追加一行 `metrics.jsonl`。**不做**，理由：

- `kev/experiment.py:135-137` 的 `source_hashes()` 在训练前后各校验一次，改 `train.py` 会让所有在途研究轮次失败
- `tests/test_conventions.py` 扫描 `kev/`
- 27B 研究轮次的训练行为依赖 trainer 的字节级稳定性

改为复用 `kev/plot.py:11` 已有的 `STEP_RE = r"ep(\d+) step (\d+)/(\d+) loss ([\d.]+)"` 解析 `train.log`。这是仓库既有做法（`plot.py` 本身就是从日志文本刮 loss）。

---

## 4. 架构与进程拓扑

```
Windows 宿主机
├── 浏览器
└── playground (Next.js 16, :3000)          ← 控制台 UI + SSE 反向代理
      │  HTTP /api/console/**  （同源，规避 CORS）
      ▼
WSL2 (Ubuntu)  ── localhostForwarding，Windows 侧直接可达
└── kev-console (FastAPI, :8790)            ← 新增：编排服务（唯一新增后端）
      ├── SQLite  kev-console.db             ← jobs / artifacts / lineage / events
      ├── Executor: LocalExecutor            ← 进程组，killpg 杀整棵树
      ├── Executor: ContainerExecutor        ← docker exec / run
      ├── 阶段处理器 × 12                     ← 只组装 argv，不含业务逻辑
      └── 启动的子进程（每个 = 一个作业）
            ├── plan_size.py / gen_*.py / split_data.py / make_goldset.py
            ├── python -m kev.train
            ├── python -m kev.benchmark / kev.calibrate
            ├── docker build                  → 镜像
            └── python -m kev.serve --port 8008  ← 部署 = 长驻作业
```

**注意编排服务不与推理服务同进程**。`kev/serve.py:228` 的 `app` 是模块级单例，`tests/test_unit.py:223,413` 用 `TestClient(serve.app)` + `monkeypatch.setattr(serve, "server", ...)` 钉死了这个形态，且 `app.state.server` 是单值（一次只能持一个 run）。把编排与推理分开，训练编排的崩溃不会带走推理端点。

### 4.1 目录契约（沿用仓库既有约定）

```
data/<scenario>/{train,calibration,development}.jsonl + summary.json   ← split_data.py 原样产出
runs/<name>/                                                              ← kev.train 原样产出
runs/<name>-eval/{rows.json,report.json,calibration.json}                ← benchmark / calibrate
data/console/jobs/<job_id>.log                                           ← 作业日志（真相源）
kev-console.db                                                           ← SQLite（不入库）
```

`.gitignore` 已忽略 `runs/*`（含 `report.json` / `calibration.json` / `train.log` / `result.json` / `provenance.json` 白名单）。本次需追加忽略 `data/console/`、`*.db`、`playground/.next/`。

---

## 5. 数据模型

### 5.1 SQLite 四张表

```sql
CREATE TABLE jobs (
  id            TEXT PRIMARY KEY,      -- ulid 风格，时间前缀可排序
  kind          TEXT NOT NULL,         -- 14 种之一
  stage         TEXT NOT NULL,         -- data | train | eval | image | deploy
  scenario      TEXT NOT NULL,         -- critical-value | triage | ...
  title         TEXT NOT NULL,
  status        TEXT NOT NULL,         -- pending|queued|running|succeeded|failed|canceled|interrupted
  request       TEXT NOT NULL,         -- JSON:表单原始参数
  argv          TEXT NOT NULL,         -- JSON array
  env_overlay   TEXT NOT NULL,         -- JSON object（仅非敏感白名单）
  cwd           TEXT NOT NULL,
  log_path      TEXT NOT NULL,
  artifacts_in  TEXT NOT NULL,         -- JSON array of artifact id
  artifacts_out TEXT NOT NULL,
  parent_id     TEXT REFERENCES jobs(id),
  attempt       INTEGER NOT NULL DEFAULT 1,
  exit_code     INTEGER,
  error         TEXT,
  created_at    TEXT NOT NULL,
  started_at    TEXT,
  finished_at   TEXT
);
CREATE INDEX jobs_status_idx   ON jobs(status);
CREATE INDEX jobs_scenario_idx ON jobs(scenario, created_at DESC);

CREATE TABLE artifacts (
  id         TEXT PRIMARY KEY,   -- <kind>:<name>，如 dataset:cv / run:cv-8b-lora-v1
  kind       TEXT NOT NULL,      -- dataset | run | eval | comparison | calibration | image | endpoint
  name       TEXT NOT NULL,
  path       TEXT NOT NULL,      -- 相对仓库根；endpoint 则为 URL
  meta       TEXT NOT NULL,      -- JSON：summary.json / 训练配置 / 关键指标 / paired CI
  bytes      INTEGER,
  created_at TEXT NOT NULL
);
CREATE UNIQUE INDEX artifacts_kind_name ON artifacts(kind, name);

CREATE TABLE lineage (
  parent   TEXT NOT NULL REFERENCES artifacts(id),
  child    TEXT NOT NULL REFERENCES artifacts(id),
  relation TEXT NOT NULL,   -- generated_from|split_into|trained_on|evaluated_on
                           -- |compared_from|calibrated_from|built_from|deployed_as
  job_id   TEXT REFERENCES jobs(id),
  PRIMARY KEY (parent, child, relation)
);

CREATE TABLE events (
  id     INTEGER PRIMARY KEY AUTOINCREMENT,
  job_id TEXT NOT NULL REFERENCES jobs(id),
  ts     TEXT NOT NULL,
  stream TEXT NOT NULL,   -- stdout | stderr | system
  line   TEXT NOT NULL
);
CREATE INDEX events_job_idx ON events(job_id, id);
```

设计取舍：

- **`artifacts` 泛化而非按类型分表** —— `meta` 装 `summary.json` / 训练配置 / 关键指标。避免五套 schema 与迁移。
- **`events` 独立于 `log_path`** —— 日志文件是真相源（`plot.py` 照样能读），`events` 是给 UI 的可分页尾巴。
- **不做 `datasets` 专表** —— 数据集就是 `kind=dataset` 的 artifact。
- **版本迁移** 用 `PRAGMA user_version`，单文件 schema，不引 Alembic。

### 5.2 血缘的七条边

```
dataset:cv ──generated_from──▶ （generate 作业）
dataset:cv ──split_into──────▶ dataset:cv/train
dataset:cv ──split_into──────▶ dataset:cv/calibration
dataset:cv ──split_into──────▶ dataset:cv/development
dataset:cv/train ──trained_on──────▶ run:cv-8b-lora-v1

run:cv-8b-lora-v1 ──evaluated_on────▶ eval:cv-dev-v1
run:<baseline>  ──evaluated_on──────▶ eval:cv-dev-v1-baseline
eval:cv-dev-v1         ──compared_from──▶ comparison:cv-dev-v1
eval:cv-dev-v1-baseline ──compared_from──▶ comparison:cv-dev-v1
comparison:cv-dev-v1 ──calibrated_from──▶ calibration:cv-dev-v1
run:cv-8b-lora-v1 ──built_from────────▶ image:kev-cv-8b-v1
run:cv-8b-lora-v1 ──deployed_as───────▶ endpoint:8008
```

这条链让 UI 回答医疗场景的可审计问题：**「这个 checkpoint 的权重来自哪次合成？那份数据依据哪张阈值表？它跟哪个 baseline 在同一份数据上比过？配对 CI 是多少？」**

---

## 6. 作业与阶段处理器

### 6.1 状态机

```
pending ──▶ queued ──▶ running ──┬──▶ succeeded
                                   ├──▶ failed       （子进程非零退出）
                                   ├──▶ canceled     （用户取消，killpg）
                                   └──▶ interrupted  （编排服务重启后发现 pid 已死）
```

合法转移由 `db.transition()` 集中校验，非法转移抛错。`succeeded → running` 这类必须被拒。

**闸门不通过时不创建作业**：`POST /jobs` 先跑该阶段的前置闸（如 `train` 要过 G1/G2/G3），不通过直接返回 `422 gate` 与逐条明细，**不落库**。理由是闸门失败是配置问题，不是执行失败，不该污染作业表与日志。

### 6.2 阶段处理器契约

```python
# kev/console/stages.py
@dataclass(frozen=True)
class BuiltCommand:
    argv: list[str]
    env: dict[str, str]              # 仅非敏感项；敏感项在 spawn 时从进程环境注入
    cwd: str
    artifacts_in: list[str]
    artifacts_out: list[str]         # kind:name，作业成功后注册为 artifact
    log_path: str

@dataclass(frozen=True)
class StageSpec:
    kind: str
    stage: str
    title: str
    request_model: type[BaseModel]   # 表单校验
    build: Callable[[JobRequest], BuiltCommand]

    def preview(self, req: JobRequest) -> BuiltCommand:
        """纯函数，供 UI 实时显示 argv。不 spawn、不写库。"""
```

**处理器只组装 argv，不含业务逻辑。** 阈值表、标签规则、指标算法全部仍在 `docs/medical/generators/` 与 `kev/` 里。控制台是编排者，不是规则引擎的第二个实现 —— 这是 `tests/test_conventions.py` 单一归属规则的核心诉求。

### 6.3 训练方式三选一（`train` 的参数映射）

来自 `runbook-train_cn.md` §〇 与步骤 6/7：

| 开关 | A1 热启动（默认预填） | A2 裸基座 | B 全参数 |
| --- | --- | --- | --- |
| `--init_from` | `jaredpalmer/kev-0.8b` | （不填） | （不填） |
| `--base` | 继承自 init | `Qwen/Qwen3.5-0.8B-Base` | 同 A2 |
| `--base_revision` | 继承 | `9a45d25e` | 同 A2 |
| `--lora` | `16` | `16` | 忽略 |
| `--full_ft` | `0` | `0` | `1` |
| `--weights_dtype` | `fp32` | `fp32` | `bf16` |
| `--lr` | `4e-5` | `4e-5` | `4e-5` |
| `--replay` | `2000` | `2000` | `0` |
| `--head_dim` | `256` | `256` | `256` |
| 其余 | `--lora_targets all --head_lr 0 --weight_decay 0.01 --epochs 1 --batch 4 --accum 2 --dtype bf16 --device cuda --seed 0` | | |

**默认值直接取自 runbook 的建议**（方式 A1 起步，只在数据量大且证明 LoRA 触顶时升级到 B）。

### 6.4 新增脚本 `docs/medical/console/precheck.py`

runbook 步骤 5 是内联 `python -c` 片段，控制台需要可复用的脚本。它**只 import，不重写**：

```python
# docs/medical/console/precheck.py
"""Token 超限预检（runbook-train_cn.md 步骤 5）。

以 tokenizer 实测为准，不以字符数估算：split_data.STATE_CHARS_WARN=1400 是英文口径，
中文 token 密度偏高，照搬会让记录在训练阶段被静默丢弃。
"""
import argparse, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from kev.data import load_records, materialize          # noqa: E402
from kev.model import load_tokenizer, training_context, fits  # noqa: E402
from kev.suite import write_json, read_json             # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--init-from", required=True, dest="init_from")
    ap.add_argument("--split", default="train")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    tok = load_tokenizer(a.init_from)
    recs = load_records(f"{a.data}/{a.split}.jsonl")
    ctx = training_context()          # 预算来自 kev.model，不在此处硬编码
    over = [r for r in recs if not fits(materialize(r), tok, **ctx)]
    report = {"split": a.split, "records": len(recs), "over_limit": len(over)}
    write_json(a.out, report)         # 签名 (path, value, atomic=False)，无 indent
    print(f"over_limit {len(over)}")
    return 1 if over else 0            # 非 0 退出码让编排层直接判 G1 失败
```

用 `training_context()` 而非写死 `384`，是因为 `tests/test_conventions.py` 规定训练上下文只能经 `kev.model` 提升。签名核对：`training_context(max_state=MAX_STATE)`（`model.py:31`）、`fits(rec, *tokenizers, max_state=…, max_branch=…, max_packed=…)`（`model.py:145`）、`load_tokenizer(name, revision=None)`（`model.py:60`）、`write_json(path, value, atomic=False)`（`suite.py:145`）。

---

## 7. 数据流

### 7.1 一次完整跑通的作业序列

以 `critical-value` + 0.8B + 方式 A1 为例：

| # | kind | 参数来源 | 产物 | 闸 |
| --- | --- | --- | --- | --- |
| 1 | `plan_size` | spec | 解析 stdout 得 787 | — |
| 2 | `generate` | **`--n` 自动取 787** | `dataset:cv` | — |
| 3 | `goldset` | 表单 | `dataset:cv.gold` | — |
| 4 | `split` | 上一作业输出 | `dataset:cv/{train,calibration,development}` + `summary.json` | G2 G3 |
| 5 | `precheck` | train 分区 | 报告 | **G1** |
| 6 | `train` | 方式 A1 | `run:cv-8b-lora-v1` | — |
| 7 | `baseline` | **同一个 `development.jsonl`** | `eval:cv-dev-v1-baseline` | — |
| 8 | `benchmark` | **同一个 `development.jsonl`** | `eval:cv-dev-v1` | — |
| 9 | `compare` | **7 与 8 的产物** | `comparison:cv-dev-v1` | **G4 G5** |
| 10 | `calibrate` | **`--rows` 自动接第 8 步** | `calibration.json` | G7 |
| 11 | `baseline` + `benchmark` + `compare`（复用第 7–9 步的三种 kind，只是换 suite） | 公开 `decision-v7` | `comparison:cv-regression-v1` | **G6** |
| 12 | `image` | Dockerfile 模板 + run 路径 | `image:kev-cv-8b-v1` | — |
| 13 | `deploy` | **run 路径 + 第 10 步的温度** | `endpoint:8008` | — |
| 14 | `smoke` | 5 场景试问集 | 报告 | — |

1→2 的 `--n`、8→10 的 `--rows`、12→13 的 run 路径，全部由血缘推导，不需要人手工复制。**这就是"编排"相对于"命令启动器"的价值。**

### 7.1.1 为什么必须有 `baseline` 与 `compare`（自审发现的关键修正）

初稿把 G4 写成「`report.json` 的 `bootstrap.acc.ci95` 排除 0」。**这是错的**，实测核对：

- `kev/benchmark.py` 的产物里**没有** `bootstrap` 键 —— 它写的是 `paired_flip`（`benchmark.py:89`，来自 `kev.contrastive`）
- 配对 bootstrap 的 CI 只能由 `kev.compare` 产出：`result["paired"]["acc"]`（`compare.py:44` → `kev.metrics.paired_bootstrap`）
- `paired_bootstrap` 的返回形状是 `{f"{aggregation}_{metric}_delta", "ci95": [lo, hi], "samples", "groups", "aggregation", "unit", "method"}`（`metrics.py:423-426`）

**所以「增益真实」在单次 `kev.benchmark` 下根本不可判定** —— 它本质上是一次 baseline 对比。同理，`regression` 段只存在于 `kev_modal.py` 的 `result.json`（`kev/` 全目录零命中），本地产物路径必须自己在公开 suite 上做一次 `compare`。

因此新增两个作业类型，闸门判据改为读 `comparison` 产物（§8）。

**`compare` 的硬前提**（`compare.py:39-40`）：两份 `report.json` 的 `suite_sha256` 必须一致，否则直接 `ValueError`。`--data` 模式下 `suite_sha256 = digest(Path(a.data))`，而 `kev.suite.digest`（`suite.py:113-117`）是**按文件内容**算的 sha256 —— 所以 baseline 与 candidate 即使用不同路径的同一份 `development.jsonl`，digest 也一致，配对成立。

⚠️ 但若用 `--suite` 模式，`suite_sha256 = digest(suite/manifest.json)`，换 suite 就会拒绝。这是「可比性」的正确保护，控制台要把它作为 `conflict` 提前拦下，而不是让子进程抛 `ValueError`。

### 7.2 训练监控的数据流

```
kev.train stdout ──pipe──▶ LocalExecutor tee ──┬─▶ data/console/jobs/<id>.log   （真相源）
                                                ├─▶ 批量 INSERT events（每 10 行 flush）
                                                └─▶ STEP_RE 匹配 → 解析
                                                      (ep, step, total, loss, kl, anchor, s_per_rec)
                                                      └─▶ SSE 推送 + 内存 ring buffer（≤2000 点）

浏览器 ──EventSource──▶ /api/console/jobs/<id>/stream
                          首屏从 events 表回填历史，之后走增量
```

关键实现点：

```python
# kev/console/events.py
STEP_RE = re.compile(
    r"ep(?P<ep>\d+) step (?P<step>\d+)/(?P<total>\d+) "
    r"loss (?P<loss>[\d.]+) kl (?P<kl>[\d.]+) anchor (?P<anchor>[\d.]+) "
    r"(?P<sec>[\d.]+)s/rec"
)   # 与 kev/plot.py:11 同源，不重新发明
```

**两个必须容错的真实坑**：

1. `training_metrics.json` 只在训练完全结束时写（`train.py:672`），`--stop_after` 早退**根本不写**（`train.py:660-661`）。所以作业成功但文件缺失时标 `metrics_missing`，**不报错**。
2. 实时指标的上限就是日志 tail。断流、进程被杀都没有别的数据源。UI 上要如实写明，不假装有 checkpoint 级指标。

### 7.3 SSE 端点

```
GET /console/api/jobs/{id}/stream        （text/event-stream）
  event: log     data: {"ts":..., "stream":"stdout", "line":"..."}
  event: metric  data: {"ep":0,"step":10,"total":139,"loss":0.623,"kl":0.0,"anchor":0.0}
  event: status  data: {"status":"succeeded","exit_code":0}
  event: ping    data: {"ts":...}                    （每 15s，防中间件断连）
  id: <events.id>                                    （支持 Last-Event-ID 续传）
```

前端 `EventSource` 原生重连 + `Last-Event-ID` 头，服务端从 `events` 表续推。ring buffer 溢出时前端显式提示「仅显示最近 N 点」。

---

## 8. 闸门：把验收门槛写进流程

借鉴 `kev/experiment.py:171-214` 的 `gate_report` 概念。阶段之间设硬闸，不通过就阻断。

| 闸 | 判据（读 `comparison.json` 或 `calibration.json`） | 来源 | 位置 |
| --- | --- | --- | --- |
| **G1** | `over_limit == 0` | 步骤 5 | precheck → train |
| **G2** | `summary.records == plan_size.total_records` | 步骤 4 与步骤 1 吻合 | split → train |
| **G3** | `summary.invalid_lines == 0` 且无 `<5%` 标签告警、无「从未作为正确答案」的选项 | `data-format.md` §六自检清单 | split → train |
| **G4** | `paired.acc.ci95[0] > 0`（**下限**排除 0） | README §七「增益真实」 | compare → image/deploy |
| **G5** | `report.calibrated_clean.ece < report.clean.ece` **且** candidate 的 `clean.confident_error_rate` ≤ baseline 的 | README §七「校准更好」 | compare → image/deploy |
| **G6** | 公开 `decision-v7` 上 `paired.acc.ci95[0] >= -0.02` | README §七「回归」 | compare → deploy |
| **G7** | `arms.workload_oof.ece <= arms.shipped.ece` | 步骤 10 验证 | calibrate → deploy |

G4/G6 不通过时，`image` 与 `deploy` 按钮**直接禁用**并显示差多少。G4 的提示语要说清因果：`ci95[0] <= 0` 说明数据不够或增益太小 —— `README.md` §八的收益排序第 1 条是「更多更好的数据」，**改数据不是加量，也不是调超参**。

`kev.compare` 的输出路径（`compare.py:42-48`）：

```
comparison.clean.candidate.*      # candidate 的 clean 指标块
comparison.clean.reference.*      # baseline 的 clean 指标块
comparison.paired.acc              # {macro_acc_delta, ci95:[lo,hi], samples, groups, aggregation, unit, method}
comparison.paired.nll / .brier    # 同形状
comparison.nll_floor_sensitivity
comparison.none_of_the_above
```

G3 复用 `split_data.py` 的 `warnings_for` / `label_table` 输出结构，不重算标签分布。

### 8.1 指标在产物中的位置（控制台必须知道）

| 指标 | 路径 |
| --- | --- |
| accuracy / ECE / Brier / NLL | `report.clean.*`（及 `report.tasks.<t>.*`、`report.calibrated_clean.*`） |
| AURC | `report.clean.aurc` |
| 选择性覆盖 | `report.clean.coverage_at_5pct_error` / `coverage_at_0_9` / `clean.selective["0.5"|"0.8"].coverage` |
| 过度自信 | `report.clean.mean_conf` vs `report.clean.acc`，及 `clean.confident_error_rate`、`clean.confidence_bias` |
| 校准后 | `report.calibrated_clean.*`（`benchmark.py:94`，temperature=1.0 下由 `knowable` 行重算） |
| permutation | `report.permutation.{n,mean_max_delta,flip_rate}` |
| 配对翻转 | `report.paired_flip.{pairs,flip_rate,both_correct_rate}`（**注意这是 flip 率，不是 CI**） |
| **配对 bootstrap CI** | **只在 `comparison.paired.<metric>.ci95`（由 `kev.compare` 产出）** |
| 校准四臂 | `calibration.arms.{raw,shipped,workload,workload_oof}` |
| 建议温度 | `calibration.workload_temperature` |
| isolation | **不在 report.json**，在研究 trial 的 `result.json.mechanism_checks` + `gates.checks.isolation_and_packing` |
| 环境 | `report.environment`（= `kev.predictors.kernel_environment`） |
| suite 可比性 | `report.suite_sha256`（`--data` 模式 = 数据文件内容的 sha256） |

⚠️ 工作区存在**两套互不兼容的 `result.json`**：`kev/experiment.py` 的研究 trial 版，与 `kev_modal.py` 的云端版（`{temperature, development:{raw,calibrated,per_question}, errors, bootstrap, regression}`）。**runbook 步骤 9 描述的是后者**（`development.calibrated.acc`、`bootstrap.acc.ci95`），而那是 Modal 路径的产物。本设计走本地路径（`kev.benchmark` 直调），产物是前者，判据路径已按上表改写。控制台按工作区显式选择 schema，**不混用**。

---

## 9. 幂等与崩溃恢复

### 9.1 目录不可复用

`kev.train` 与 `kev/benchmark.evaluate_records` 都是 `mkdir(exist_ok=False)`，目录已存在直接报错。

策略：

- spawn 前检查 `out` 路径 —— **已存在则拒绝提交**并提示改用 `-v2`
- **不自动改名**，避免悄悄覆盖已有产物（医疗可审计性要求）
- 重试 = 新作业 + `attempt+1` + 新目录名，旧作业与其产物永久保留

运行名必须过 `fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}")`（复用 `run_matrix.py:25,38-48` 的校验）—— **不允许点号**，所以尺寸写 `8b` 不写 `0.8b`。

### 9.2 进程组

```python
proc = subprocess.Popen(
    argv, cwd=cwd, env=env,
    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    text=True, bufsize=1,
    start_new_session=True,      # 独立进程组
)
# 取消时：
os.killpg(os.getpgid(proc.pid), signal.SIGTERM)   # 5s 后 SIGKILL
```

不设 `start_new_session` 则 `torchrun` 的子进程会变孤儿继续占 GPU。

### 9.3 启动即恢复

WSL2 会自动回收内存，服务重启是常态，所以这不是可选功能：

```sql
-- kev-console.db 打开时立即执行
UPDATE jobs SET status='interrupted', error='编排服务重启', finished_at=?
WHERE status IN ('running','queued');
```

前端对 `interrupted` 显示「续训 / 重试」，对 `failed` 显示「查看错误 / 重试」。

### 9.4 目录占用竞态

`score_trial` 会在评估中途失败时留下 `calibration/`、`development/` 半成品（`experiment.py:248-249` 只能整目录 rmtree 重来）。编排层需在 spawn 前复查目标目录，并把「目录已存在」映射为 `conflict`（409）而非 `executor`（500）。

---

## 10. 错误处理与 API 契约

### 10.1 API 契约

```
GET  /console/api/config                非敏感配置 + 凭据布尔态 + 场景列表
GET  /console/api/scenarios             5 个 spec 元数据（从 docs/medical/specs 读）
── 数据 ──
POST /console/api/datasets/import       上传 JSONL → 校验报告（不落盘，先看再确认）
GET  /console/api/datasets/{id}         详情 + summary + 分区 + 标签分布
GET  /console/api/datasets/{id}/rows    抽样记录（分页）
GET  /console/api/datasets/{id}/export  下载 JSONL（勾选分区）
── 作业 ──
POST /console/api/jobs                  提交作业（kind + params）→ 预检闸门 → 入队
GET  /console/api/jobs                  列表（status / stage / scenario 过滤）
GET  /console/api/jobs/{id}             argv、事件、产物、血缘
POST /console/api/jobs/{id}/cancel      killpg 杀整棵树
POST /console/api/jobs/{id}/retry       attempt+1 + 新目录名
GET  /console/api/jobs/{id}/stream      SSE：日志行 + 指标增量
GET  /console/api/jobs/{id}/events      历史事件分页（首屏回填 / Last-Event-ID 续传）
── 其余 ──
GET  /console/api/artifacts             产物 + 血缘边
GET  /console/api/gates/{stage}         G1–G7 逐条状态
GET  /console/api/endpoints             端点状态 + /v1/models 透传
```

`POST /jobs` 响应体带 `preview_argv`（只读，不 spawn），供 UI 在提交前确认。

### 10.2 统一错误体

```json
{ "error": { "kind": "...", "message": "...", "field": "...", "hint": "...", "stderr_tail": "..." } }
```

| kind | HTTP | 典型场景 | UI 处置 |
| --- | --- | --- | --- |
| `validation` | 400 | 运行名含点号、选项数超限 | 字段级红字 + `hint` 给正确写法 |
| `config` | 400 | Windows 上误启全参数训练 | 提示需 WSL2 + GPU |
| `conflict` | 409 | `--out` 目录已存在 | 拒绝提交，`hint` 建议 `-v2` |
| `gate` | 422 | G1–G7 不通过 | 门槛面板逐条展开，**不是** 500 |
| `executor` | 500 | spawn 失败、killpg 失败 | 可重试 |
| `upstream` | 502 | 子进程非零退出 | **必带 `stderr_tail`（末 30 行）** |

**子进程非零退出必须带 stderr 尾部 30 行** —— `train.log` 可能有数万行，尾部是排错的唯一线索来源。

---

## 11. 前端 UI

### 11.1 路由

```
playground/src/app/console/
├── layout.tsx              sidebar 壳
├── page.tsx                总览（5 阶段状态条 + 作业表 + 血缘 DAG）
├── datasets/page.tsx       阶段 1 · 数据管理
├── train/page.tsx          阶段 2 · 训练监控
├── eval/page.tsx           阶段 3 · 评测验收
├── images/page.tsx         阶段 4 · 镜像构建
├── deploy/page.tsx         阶段 5 · 部署与测试
└── jobs/[id]/page.tsx      作业详情
playground/src/app/api/console/[...path]/route.ts   薄代理 + SSE 管道
playground/src/components/console/                 组件 + strings.ts + format.ts
```

需补的 shadcn 组件：`table` `dialog` `select` `form` `progress` `sonner` `tooltip` `dropdown-menu` `scroll-area`（现有 9 个不含）。`components.json` 已是 `style: "base-nova"`（`@base-ui/react`，**不是 radix**），直接 `shadcn add`。

`globals.css` 里 `--sidebar-*` 8 个 token 与 `--chart-1..5` 已定义但从未被使用 —— 正好是仪表盘要用的。

### 11.2 贯穿全站的设计原则：argv 永远可见

**每个作业表单右侧实时显示将要执行的完整 argv（只读、可复制）**，由 `StageSpec.preview()` 提供。

理由来自 runbook 本身的价值结构 —— 步骤 7 给的是「目的 / 输入 / 命令 / 预期输出 / 验证」。藏起命令会让用户失去可审计性与可复现性，医疗场景下这是硬伤。表单改一个字段，argv 实时重算，用户看得见自己改了什么。

### 11.3 图表：零新依赖，手写 SVG

| 组件 | 用途 | 数据来源 |
| --- | --- | --- |
| `<LossChart>` | loss / kl / anchor 三序列曲线 | 解析 `train.log` |
| `<ReliabilityDiagram>` | 校准可靠性图 | `report.clean.top_bins` + ECE |
| `<MetricDeltaBar>` | baseline vs 微调 指标差 | `comparison.clean.{reference,candidate}` |
| `<CoverageCurve>` | 选择性覆盖 vs 错误率 | `clean.selective` / `coverage_at_5pct_error` |

不引 recharts：仓库无图表库，`answer-card.tsx` 已有手写条形先例，这四个图的数据形态都是几十个点，SVG 手写更可控。

### 11.4 各阶段页面要点

**阶段 1 · 数据**
- 数据集列表 + 记录数 / 分区 / 标签分布
- 导入：上传 JSONL → 结构校验（走 `kev.data.load_records`）→ 标签分布直方图（**<5% 与「从未作为正确答案」高亮**）→ 冲突 state 检测（复用 `split_data` 的 `state_key` / `check_record`）
- **PHI 兜底**：对 `patient` 等字段做占位符 / 身份证 / 手机号模式检测，**只告警不自动改写**，提供「哈希替换」可选项
- 导出：勾选分区 → 下载 JSONL
- 合成：选 spec（5 场景）+ 规模 + seed → `generate`；LLM 蒸馏轨另给模型 / 并发 / 每日额度（`KEV_GEN_API_KEYS` 多 key 轮换、`.distill/usage_<日期>.json` 记账）

**阶段 2 · 训练**
- 方式切换卡片 A1 / A2 / B，**默认预填 A1 + `jaredpalmer/kev-0.8b`**
- 常用参数滑杆 / 分段控件，高级参数折叠
- 实时：loss 曲线 + `step/total` + `s/rec` + 预计剩余 + 日志尾（自动滚到底，可暂停跟随）
- 结束：`grad_norm` 均值 / 最大 / 裁剪步数（梯度爆炸判据）、`peak_device_bytes`、墙钟时间
- **风险提示横幅**：0.8B 日期算术 0.35、工具路由 When2Call 0.133 低于机会水平；0.8B 更容易过度自信，验收卡更严

**阶段 3 · 评测**
- 指标卡组：acc / ECE / Brier / NLL / AURC / `coverage_at_5pct_error` / `mean_conf` vs `acc`
- 校准四臂表：raw / shipped / workload / workload_oof + 建议温度
- **验收门槛面板**：G4–G7 逐条 ✓/✗，不通过显示「差多少」与建议动作
- 对比：`kev.compare` 跨尺寸 / 跨版本配对 bootstrap

**阶段 4 · 镜像**
- Dockerfile 模板两套：CPU 推理版、`kev.serve` 服务版；run 路径与温度由血缘填入
- 构建日志流、镜像列表、层大小

**阶段 5 · 部署**
- 端点列表：在线 / 离线、当前 run、温度（显示 `workload_temperature`）
- **冒烟测试**：内置 5 场景各 1 例 System One 试问，一键跑完显示 p 分布与 argmax
- 回滚：指向 baseline run（模型级回滚，秒级）
- **顶部常驻风险横幅**：均衡先验 ≠ 真实先验（危急值线上 1–3%），阈值须用真实流量重标定；医疗场景默认「模型建议 + 人工确认」

### 11.5 状态与 i18n

- 数据获取：`EventSource`（日志与指标增量）+ 轻量轮询（作业列表）。**不引 zustand / react-query** —— YAGNI。
- 文案：集中在 `playground/src/components/console/strings.ts`，形状沿用现有 `{en, zh}`，**注入全局 `Dict` 保持 `t()` 单一入口**，不引入第二套 i18n。
- 现有 `src/lib/kev.ts:29` 硬编码了一个真实 API key 且经 `NEXT_PUBLIC_` 暴露到客户端 —— **本次一并删除**，改为从 `/console/api/config` 取布尔态。

---

## 12. 安全与合规

| 类别 | 处理 |
| --- | --- |
| `KEV_GEN_API_KEYS` / `KEV_API_KEY` / `HF_TOKEN` / `KEV_SERVE_SECRET` | **只从编排服务进程的环境变量读**，spawn 时注入子进程，**永不写进 SQLite、永不下发浏览器**。UI 只显示「已配置 / 未配置」布尔态 |
| `HF_ENDPOINT` / `KEV_GEN_BASE_URL` / `KEV_GEN_MODEL` / `OMP_NUM_THREADS` | 可持久化在 `env_overlay`，非敏感 |
| 监听地址 | 编排服务只绑 `127.0.0.1`；playground 走同源代理，浏览器不发跨域请求 |
| PHI | 控制台不写入真实患者数据。导入时对 `patient` 等字段做模式检测，**只告警不自动改写**，脱敏在进入生成器之前完成 |
| 模型发布 | 医疗模型**禁止** `--public`。`kev.publish` 的 `--private` 是硬约束，控制台不提供公开选项 |
| 部署安全 | 部署页常驻提示「模型建议 + 人工确认」，不提供无人工的自动处置开关 |

**注意**：`KEV_TEMPERATURE` 不得由控制台直接读环境变量 —— `tests/test_conventions.py` 规定它只能经 `kev.checkpoint.LoadOptions.from_env` 读取。部署温度一律从 `calibration.json` 的 `workload_temperature` 或 `head.pt` meta 取。

---

## 13. 仓库约定合规清单

`tests/test_conventions.py` 会 `rglob` 扫描 `kev/`、`scripts/`、`space/`、`tests/`、`modal_app.py`，17 条「单一归属」正则对新代码同样生效。`kev/console/` 必须遵守：

| 规则 | 约束 |
| --- | --- |
| 文本 IO | 一律走 `kev.suite.read_json/write_json/read_jsonl/write_jsonl`，或显式 `encoding="utf-8"`。**禁止**裸 `.read_text()` / `open()` |
| 记录加载 | 走 `kev.data.load_records/materialize`，不自己解析 JSONL |
| 选项键空间 | 走 `kev.api.question_keys`，**禁止**自己写 `["false","true"]` |
| 训练上下文 | 走 `kev.model.training_context/fits`，**禁止**硬编码 `2048` / `max_state=` |
| 状态哈希 | 走 `kev.suite.text_digest`，**禁止**自己 `casefold().split()).encode()` |
| checkpoint | 走 `kev.checkpoint`，**禁止** `glob("model*.safetensors")` 或 `adapter_config.json").exists()` |
| 环境变量 | **禁止**读 `KEV_DTYPE/MERGE/ATTN/LORA_SCALE/TEMPERATURE/BACKEND/CUDA_GRAPHS` |
| 设备操作 | **禁止** `torch.cuda.empty_cache()` 等，走 `kev.device` |
| 指标 | 走 `kev.metrics`，不重算 ECE/Brier/bootstrap |
| JSON 写 | 沿用 `kev.suite.write_json` 的 `allow_nan=False` 语义；NaN 指标必须在写库前归一 |

另：`docs/claims.json` + `scripts/verify_claims.py` 会逐字校验**已登记**的字符串。控制台文档若引用实测数字，要么进 `claims.json` 登记来源，要么避免写成可被误读为「已验证结论」的形式。

---

## 14. 测试策略

| 层 | 覆盖 | 手法 |
| --- | --- | --- |
| 单元 | SQLite 迁移；状态机合法转移（`succeeded→running` 必须被拒） | 直接调 `db.transition()` |
| 单元 | 14 种 kind 的 argv 组装 | 每 kind 一条 **golden argv 快照**，与 `runbook-train_cn.md` 逐字比对 |
| 闸门 | G1–G7 各一条通过 + 一条不通过 | fixture 造 `report.json` / `summary.json` 样本 |
| 执行器 | tee、退出码、取消 | 假命令 `python -c "print(...)"` / `sleep`，**不跑真训练**；取消测试真杀进程树并断言无孤儿 |
| **契约冻结** | `kev/train.py`、`kev/serve.py`、`kev/benchmark.py` 零改动 | `git diff --name-only` 断言 —— 最廉价的回归保护 |
| 前端 | argv 预览、SSE 解析、指标格式化 | 抽纯函数到 `console/format.ts`，最小 vitest |
| 端到端 | 见下方人工清单 | 冒烟 |

**不写「跑真训练」的测试** —— `kev.train` CPU 冒烟要拉权重、分钟级。改为 argv 快照 + 人工冒烟。

### 14.1 人工验收清单

1. **数据半链路真跑通**（当前机器唯一能真跑的部分，runbook §三已验证过）：`plan_size → generate 787 → split 551/118/118 → precheck over_limit=0`
2. `train` 在 WSL2 + GPU 上跑通 3 条记录的 CPU 冒烟，产出 `adapter_model.safetensors` + `head.pt`
3. SSE：断网重连后日志与曲线续上（`Last-Event-ID` 生效）
4. 取消训练后 `nvidia-smi` 确认**无孤儿进程**
5. 崩溃恢复：训练中 `kill` 编排服务 → 重启 → 该作业显示 `interrupted` 且可重试
6. 闸门 G4：人为造一个 `paired.acc.ci95 = [-0.01, 0.03]` 的 `comparison.json` → `image`/`deploy` 按钮禁用
7. PHI：上传含身份证号的 `patient` 字段 → 告警出现且不自动改写
8. `git diff --name-only` 确认 `kev/train.py`、`kev/serve.py`、`kev/benchmark.py` 为空
9. 全程无任何凭据出现在浏览器 Network 响应或 SQLite 里

---

## 15. 主要风险

| 风险 | 严重度 | 缓解 |
| --- | --- | --- |
| **误以为单次 `benchmark` 能判定「增益真实」** | 高 | G4/G6 必须经 `baseline` + `compare`；`compare` 的 `suite_sha256` 一致性由编排层提前拦为 `conflict`（§7.1.1） |
| `evaluate_records` / `kev.train` 的 `mkdir(exist_ok=False)` 与编排层写状态冲突 | 高 | §9.1 拒绝复用目录 + §9.4 spawn 前复查 |
| NaN 指标让 `kev.suite.write_json`（`allow_nan=False`）在写文件时崩 | 高 | 写库前归一 NaN/Inf；`upstream` 错误体带 stderr_tail |
| 训练期无结构化指标出口 | 中 | 接受此上限，UI 如实说明；不改 `train.py`（§3.5） |
| WSL2 自动回收内存导致服务频繁重启 | 中 | §9.3 启动即恢复是必需功能，不是可选 |
| 两套 `result.json` schema 混用 | 中 | 按工作区显式选择，§8.1 列出两条路径 |
| 0.8B 过度自信导致线上过度报警 | 中（业务） | 均衡先验 ≠ 真实先验横幅 + G5 卡更严 + 部署页常驻人工确认提示 |
| 取消训练后 `torchrun` 变孤儿占 GPU | 中 | `start_new_session=True` + `killpg` |
| 医疗数据合规 | 高（业务） | §12 全部约束；控制台不写入真实患者数据 |

---

## 16. 开放问题（均不阻塞实施，各带默认值）

1. **Docker 镜像的运行时形态**：CPU 推理镜像（`kev.serve` + torch CPU）体积大且慢，是否改为 MLX/ONNX 或只提供 GPU 镜像？
   **默认**：先只提供 GPU 镜像（`nvidia/cuda` + `kev.serve`），CPU 镜像列为可选模板。理由：`kev/serve.py:332` 的服务默认值在非 CPU 设备上开 bf16 + CUDA graphs，CPU 路径未在 0.8B 规模上验证过。
2. **作业并发上限**：单 GPU 场景下同时只应有一个 `train`。`kev.experiment.study_lock()` 只有一个 flock，没有真正的队列。
   **默认**：编排层加一道 SQLite 事务闸 —— `kind='train'` 且 `status IN ('pending','queued','running')` 的作业存在时拒绝提交第二个（返回 `conflict`）。`train` 之外的其他 kind 不限流。`kev.experiment` 在 Windows 上不可 import（`experiment.py:14` 直接 `import fcntl`），所以这道闸必须自己实现。
3. **`distill` 轨的调度**：`generate_data.py` 支持 `--schedule` 与每日额度续算。
   **默认**：控制台只做单次触发，调度交给 cron / 任务计划程序。理由：控制台进程本身在 WSL2 里会被回收，做常驻调度不可靠。
4. **多场景并行**：5 个场景的数据集与训练是否支持同时编排？
   **默认**：支持 —— 血缘模型天然按 `(scenario, kind, name)` 命名，天然可并行。闸门按 **`scenario` 维度**判定（G4 的 CI 只对本 scenario 的 development 集成立），而非全局。`compare` 仍显式选择两个 run，不做跨 scenario 自动比较。
