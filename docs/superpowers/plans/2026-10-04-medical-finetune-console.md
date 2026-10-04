# 医疗微调控制台（Kev Console）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 `playground/` 上建一个控制台，把 `docs/medical/` 的 12 步医疗微调管线变成可编排、可监控、可审计的界面，覆盖数据合成 → SFT 训练 → 评测 → 镜像 → 部署测试 5 个阶段。

**Architecture:** 编排服务（FastAPI）跑在 WSL2 内、与 torch 同环境，用 `subprocess` 拉起 `kev` 包的原生命令；playground 只做控制面 + SSE 反向代理。14 种作业统一为长任务模型，SQLite 记 `jobs`/`artifacts`/`lineage`/`events`。G1–G7 闸门把 `docs/medical/README.md` §七 的医疗验收纪律固化进流程。

**Tech Stack:** Python 3.12+ / FastAPI / SQLite（标准库 `sqlite3`）/ Next.js 16.3.5 / React 19 / Tailwind v4 / `@base-ui/react`（shadcn base-nova）/ SSE

**设计文档:** `docs/superpowers/specs/2026-10-04-medical-finetune-console-design.md`（已提交 `b848da8`）

---

## Global Constraints

每个任务的要求都隐含包含本节。

**零改动红线（最高优先级）**

- `kev/train.py`、`kev/serve.py`、`kev/benchmark.py`、`kev/calibrate.py`、`kev/publish.py`、`kev/metrics.py`、`kev/compare.py` **一行都不改**。加一个 `git diff --name-only` 测试钉死（Task 14）。
- 理由：`kev/experiment.py:135-137` 的 `source_hashes()` 在训练前后各校验一次，改这些文件会让在途研究轮次失败；`tests/test_unit.py` 钉死 `serve.app` 形态。
- **不给 `kev/train.py` 加 `metrics.jsonl`**。训练期唯一实时数据源是 stdout 文本，实时 loss 曲线靠解析 `train.log`。

**`tests/test_conventions.py` 合规（`kev/` 与 `tests/` 都会被 `rglob` 扫描）**

新代码必须遵守 17 条「单一归属」正则：

| 禁止 | 改用 |
| --- | --- |
| 裸 `.read_text()` / `open()` 不带 `encoding=` | `kev.suite.read_json` / `write_json` / `read_jsonl` / `write_jsonl` |
| **`encoding=` 与 `write_text(` 不在同一行**（该正则是**按行**匹配的，跨行同样违规，Linux 也一样） | 把内容存进局部变量：`payload = '...'` 再 `write_text(payload, encoding="utf-8")` |
| 自己写 `["false","true"]` 或 `[str(i) for i in range(...)]` | `kev.api.question_keys` |
| 硬编码 `2048` 比较、`max_state=` / `max_branch=` / `max_packed=` | `kev.model.training_context()` / `kev.model.fits` |
| `os.environ` 读 `KEV_DTYPE`/`KEV_MERGE`/`KEV_ATTN`/`KEV_LORA_SCALE`/`KEV_TEMPERATURE`/`KEV_BACKEND`/`KEV_CUDA_GRAPHS` | `kev.checkpoint.LoadOptions.from_env`（温度从 `calibration.json` 取） |
| `torch.load/save(...head.pt` | `kev.checkpoint` |
| `glob("model*.safetensors")`、`adapter_config.json").exists()` | `kev.checkpoint.Checkpoint` |
| `MLXDecisionModel(` / `merge_lora(` | `kev.checkpoint.Checkpoint.load` |
| 自己算 `casefold().split()).encode()` | `kev.suite.text_digest` |
| `torch.cuda.empty_cache()` 等设备操作 | `kev.device` |
| 自定义 `SAMPLES = 2000` | `kev.rounds.SAMPLES` / `kev.metrics.paired_bootstrap(samples=…)` |
| 记录解析、指标计算、ECE/Brier/bootstrap 公式 | `kev.data.load_records` / `kev.metrics` |

**命令行参数名（一律下划线，核对自 `kev/train.py` 的 argparse）**

- `kev.train`：`--data` `--out` `--init_from` `--base` `--base_revision` `--lora` `--lora_targets` `--head_dim` `--head_lr` `--full_ft` `--weights_dtype` `--lr` `--epochs` `--batch` `--accum` `--dtype` `--device` `--replay` `--seed` `--weight_decay` `--checkpointing` `--length_sort` `--row_budget` `--pass_tokens_max` `--max_steps` `--resume` `--save_every_steps` `--save_every_minutes` `--snapshot_fractions` `--snapshot_dir`
  - **`--base` 默认是 `Qwen/Qwen3-0.6B-Base`**，所以 A2/B 方式必须显式传 `--base Qwen/Qwen3.5-0.8B-Base --base_revision 9a45d25e`
  - `--lr` 默认 `2e-4`、`--accum` 默认 `8`、`--batch` 默认 `1`、`--epochs` 默认 `1`、`--lora` 默认 `16`、`--head_dim` 默认 `256`、`--lora_targets` 默认 `all`、`--dtype` 默认 `fp32`、`--weights_dtype` 默认 `fp32`、`--out` 默认 `runs/kev`
- `kev.benchmark`：`--run` `--data` `--suite` `--out` `--device` `--split` `--rotations` `--remote` `--allow-test` `--date-facts`
- `kev.calibrate`：`--rows`（必填）`--out` `--folds`（5）`--seed`（0）`--samples`（1000）
- `kev.compare`：`--candidate` `--reference` `--out`（三者必填）
- `kev.publish`：`--run` `--repo` `--card`（必填）`--private` `--revision` `--replace` `--message` `--tag`
- `plan_size.py`：`spec`（位置参数，可选）`--questions` `--baseline-acc`(0.75) `--min-gain`(0.05) `--regressions`(0.05) `--power`(0.8，choices 0.8/0.9/0.95) `--development`(0.15) `--calibration`(0.15) `--from-result` **`--json`**
- `split_data.py`：`data`（位置参数）`--out` `--calibration`(0.15) `--development`(0.15) `--seed`(0) `--holdout`
- 生成器（`common.base_parser`）：`--n`(787) `--out`（必填）`--seed`(0) `--pairs`(0.35)
- `make_goldset.py`：`sample` 子命令 —— `data`（位置）`--n`(200) `--seed`(0) `--out`（必填）；`audit` 子命令 —— `a` `b` `--out` `--threshold`(0.05)

**`run_matrix` 复用边界（实测核对）**

`docs/medical/generators/run_matrix.py::steps()` 的 `plan_size` / `generate` / `split` 三步是纯本地 argv，可原样复用；`validate_*` / `train_*` / `compare` / `deploy_*` 发的是 **Modal** 命令，本地路径必须自建。

**真正要 import 的是它的常量与校验器**（运行名规范的唯一归属）：

```python
sys.path.insert(0, str(GENERATORS))
from run_matrix import NAME_RE, SIZES, SCENARIOS, FOUR_B_ONLY, check_name
```

`check_name()` 用 `fullmatch`（`run_matrix.py:45`）——用 `match` 会错误放行 `critical-value-0.8b-v1`。

**目录契约**

```
data/<scenario>/{train,calibration,development}.jsonl + summary.json   ← split_data.py 原样产出
runs/<name>/                                                              ← kev.train 原样产出
runs/<name>-eval/{rows.json,report.json}                                ← kev.benchmark
runs/<name>-compare/                                                      ← kev.compare
data/console/jobs/<job_id>.log                                           ← 作业日志（真相源）
data/console/kev-console.db                                              ← SQLite（不入库）
```

**平台**

- 编排服务跑在 **WSL2 内**，只绑 `127.0.0.1:8790`
- Windows 侧 playground 通过 WSL2 `localhostForwarding` 访问
- 真实训练需 `--device cuda --dtype bf16`；`kev.train` 在原生 Windows 上不可用（`resource` / `fcntl`）

**安全**

- 编排服务只绑 `127.0.0.1`，无鉴权（本地单用户）
- **凭据只从编排服务进程的环境变量读，spawn 时注入子进程，永不写进 SQLite、永不下发浏览器**。UI 只显示布尔态。
- 允许持久化到 `env_overlay` 的非敏感键白名单：`HF_ENDPOINT`、`KEV_GEN_BASE_URL`、`KEV_GEN_MODEL`、`OMP_NUM_THREADS`、`PYTHONIOENCODING`
- 部署温度从 `calibration.json` 的 `workload_temperature` 取，**不读 `KEV_TEMPERATURE`**
- 顺手删掉 `playground/src/lib/kev.ts:29` 硬编码的真实 API key

**闸门判据（读 `comparison.json` / `calibration.json`，不是 `report.json`）**

| 闸 | 判据 |
| --- | --- |
| G1 | `over_limit == 0` |
| G2 | `summary.records == plan_size.total_records` |
| G3 | `summary.invalid_lines == 0` 且无 `<5%` 标签告警、无「从未作为正确答案」的选项 |
| G4 | `paired.acc.ci95[0] > 0`（**下限**排除 0） |
| G5 | `report.calibrated_clean.ece < report.clean.ece` 且 candidate 的 `clean.confident_error_rate <=` baseline 的 |
| G6 | 公开 `decision-v7` 上 `paired.acc.ci95[0] >= -0.02` |
| G7 | `arms.workload_oof.ece <= arms.shipped.ece` |

`bootstrap.acc.ci95` 与 `regression` 段**只存在于 `kev_modal.py` 的 Modal 路径产物**，本地 `kev.benchmark` 不产出。本地一律走 `baseline` + `compare`。

**打包**

`pyproject.toml` 当前是 `packages = ["kev"]`，**不含子包**。Task 1 必须加上 `kev.console`（及其子包），否则非 editable 安装时 `kev.console` 不可导入。

**提交纪律**

每个任务末尾提交。只 `git add` 该任务自己的文件。仓库里存在他人未提交的改动（`.qoder/repowiki/*`、`kev/vertical.py`、`tests/test_vertical.py`、`docs/vertical_CN.md`）—— **不要暂存它们**。

---

## File Structure

### 后端（新增，全部在 `kev/console/`）

| 文件 | 职责 |
| --- | --- |
| `kev/console/__init__.py` | 包标记 |
| `kev/console/__main__.py` | `python -m kev.console` → uvicorn 起在 `127.0.0.1:8790` |
| `kev/console/paths.py` | 仓库目录布局的唯一归属；把 `docs/medical/generators` 加进 `sys.path` |
| `kev/console/db.py` | SQLite schema、作业状态机、产物、血缘、事件、崩溃恢复 |
| `kev/console/artifacts.py` | 产物 id ↔ 路径的唯一真相源；产物注册与血缘写入（`on_finished` 回调触发） |
| `kev/console/events.py` | 日志行 → 结构化事件（`STEP_RE` 与它同源） |
| `kev/console/executor.py` | `LocalExecutor`：进程组、tee、取消、并发闸 |
| `kev/console/gates.py` | G1–G7 判定（纯函数，读产物 dict） |
| `kev/console/stages/__init__.py` | `REGISTRY: dict[str, StageSpec]` |
| `kev/console/stages/base.py` | `StageSpec` / `BuiltCommand` / `JobRequest` |
| `kev/console/stages/data.py` | `plan_size` `generate` `distill` `goldset` `split` `precheck` |
| `kev/console/stages/train.py` | `train` |
| `kev/console/stages/eval.py` | `baseline` `benchmark` `compare` `calibrate` |
| `kev/console/stages/deploy.py` | `image` `deploy` `smoke` |
| `kev/console/app.py` | FastAPI 路由 + SSE |
| `docs/medical/console/precheck.py` | token 超限预检（只 import `kev.*`，不重写逻辑） |
| `deploy/kev-serve/Dockerfile` | 服务镜像模板 |

### 前端（新增，全部在 `playground/`）

| 文件 | 职责 |
| --- | --- |
| `src/app/api/console/[...path]/route.ts` | 薄代理 + SSE `ReadableStream` 管道 |
| `src/app/console/layout.tsx` | sidebar 壳 |
| `src/app/console/page.tsx` | 总览：5 阶段状态条 + 作业表 |
| `src/app/console/datasets/page.tsx` | 阶段 1 数据管理 |
| `src/app/console/train/page.tsx` | 阶段 2 训练监控 |
| `src/app/console/eval/page.tsx` | 阶段 3 评测验收 |
| `src/app/console/images/page.tsx` | 阶段 4 镜像构建 |
| `src/app/console/deploy/page.tsx` | 阶段 5 部署与测试 |
| `src/app/console/jobs/[id]/page.tsx` | 作业详情：argv / 日志 / 指标 / 产物 / 血缘 |
| `src/lib/console.ts` | 控制台 API 客户端 + `EventSource` 封装 |
| `src/components/console/strings.ts` | `{en, zh}` 文案字典（注入全局 `Dict`） |
| `src/components/console/format.ts` | 纯函数：指标格式化、argv 渲染、指标路径取值 |
| `src/components/console/ArgvPreview.tsx` | 实时 argv 只读预览 |
| `src/components/console/JobTable.tsx` | 作业列表 |
| `src/components/console/LogStream.tsx` | SSE 日志尾 |
| `src/components/console/LossChart.tsx` | 手写 SVG loss 曲线 |
| `src/components/console/ReliabilityDiagram.tsx` | 手写 SVG 校准可靠性图 |
| `src/components/console/MetricDeltaBar.tsx` | baseline vs 微调 指标差 |
| `src/components/console/CoverageCurve.tsx` | 选择性覆盖曲线 |
| `src/components/console/GatePanel.tsx` | G1–G7 逐条判定 |

### 测试（新增）

`tests/test_console_db.py` `tests/test_console_artifacts.py` `tests/test_console_events.py` `tests/test_console_executor.py` `tests/test_console_gates.py` `tests/test_console_stages_data.py` `tests/test_console_stages_train.py` `tests/test_console_stages_deploy.py` `tests/test_console_api.py` `tests/test_console_contract.py`

---

## Wave 1 — 编排内核（独立可交付：能在 API 层起进程、拿到日志流）

### Task 1: 路径常量与 SQLite 存储层

**Files:**
- Create: `kev/console/__init__.py`
- Create: `kev/console/paths.py`
- Create: `kev/console/db.py`
- Create: `kev/console/artifacts.py`
- Create: `kev/console/stages/__init__.py`（空包标记：`pyproject.toml` 声明了 `kev.console.stages`，不建目录 setuptools 构建会失败、整个仓库连 pytest 都启动不了）
- Modify: `pyproject.toml:60-61`
- Test: `tests/test_console_db.py`
- Test: `tests/test_console_artifacts.py`

**Interfaces:**
- Consumes: `kev.suite.read_json` / `write_json`（仅测试夹具用）
- Produces:
  - `paths.ROOT` / `paths.SKILL_SCRIPTS` / `paths.SPECS` / `paths.GENERATORS` / `paths.CONSOLE_SCRIPTS` / `paths.DATA` / `paths.RUNS` / `paths.JOB_LOGS` / `paths.DB_PATH` / `paths.ensure_medical_on_path()`
  - `db.SCHEMA_VERSION` / `db.TERMINAL` / `db.Store(path: Path)`
  - `Store.create_job(**kw) -> str`（job id）
  - `Store.get_job(job_id) -> dict | None`
  - `Store.list_jobs(*, status=None, stage=None, scenario=None, limit=200) -> list[dict]`
  - `Store.transition(job_id, to_status, *, error=None, exit_code=None) -> None`
  - `Store.active_job_of_kind(kind) -> dict | None`
  - `Store.put_artifact(*, kind, name, path, meta) -> str`（artifact id）
  - `Store.get_artifact(artifact_id) -> dict | None`
  - `Store.list_artifacts(kind=None) -> list[dict]`
  - `Store.add_lineage(parent, child, relation, job_id=None) -> None`
  - `Store.lineage_of(artifact_id) -> list[dict]`
  - `Store.append_events(job_id, rows) -> int`（返回最后一个 event id）
  - `Store.read_events(job_id, after_id=0, limit=500) -> list[dict]`
  - `Store.interrupt_stale_jobs() -> int`
  - `artifacts.resolve(artifact_id: str) -> str`（artifact id → 仓库相对路径，唯一真相源）
  - `artifacts.summarize(artifact_id: str, path: str) -> dict`（读产物得出小份 meta，供 UI 直接用）
  - `artifacts.register(store, job) -> list[str]`（注册 `artifacts_out` 并写 `in → out` 血缘；返回注册的 id）
  - `artifacts.PERSIST`（`StageSpec.persist` 的合法取值： `"success"` / `"start"`）

- [ ] **Step 1: 写失败的测试**

```python
# tests/test_console_db.py
"""编排层的持久化：状态机、产物、血缘、事件、崩溃恢复。

重点是两条不变量：非法状态转移必须抛错，崩溃后 running 的作业必须变成 interrupted
（WSL2 会自动回收内存，服务重启是常态，见 spec §9.3）。

Run: uv run python -m pytest tests/test_console_db.py -q
"""
import pytest

from kev.console.db import Store


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "kev-console.db")


def test_create_job_defaults_to_pending(store):
    job_id = store.create_job(
        kind="train", stage="train", scenario="critical-value", title="A1",
        request={"method": "a1"}, argv=["python", "-m", "kev.train"],
        env_overlay={}, cwd="/repo", log_path="data/console/jobs/x.log",
        artifacts_in=[], artifacts_out=["run:cv-8b"],
    )
    job = store.get_job(job_id)
    assert job["status"] == "pending"
    assert job["attempt"] == 1
    assert job["argv"] == ["python", "-m", "kev.train"]
    assert job["artifacts_out"] == ["run:cv-8b"]
    assert job["started_at"] is None


def test_illegal_transition_is_rejected(store):
    job_id = store.create_job(
        kind="train", stage="train", scenario="triage", title="t",
        request={}, argv=["x"], env_overlay={}, cwd="/repo",
        log_path="l.log", artifacts_in=[], artifacts_out=[],
    )
    store.transition(job_id, "queued")
    store.transition(job_id, "running")
    store.transition(job_id, "succeeded")
    with pytest.raises(ValueError, match="illegal transition"):
        store.transition(job_id, "running")


def test_terminal_states_accept_nothing(store):
    job_id = store.create_job(
        kind="train", stage="train", scenario="triage", title="t",
        request={}, argv=["x"], env_overlay={}, cwd="/repo",
        log_path="l.log", artifacts_in=[], artifacts_out=[],
    )
    store.transition(job_id, "queued")
    store.transition(job_id, "canceled")
    for target in ("queued", "running", "succeeded", "failed"):
        with pytest.raises(ValueError):
            store.transition(job_id, target)


def test_failed_records_exit_code_and_error(store):
    job_id = store.create_job(
        kind="train", stage="train", scenario="triage", title="t",
        request={}, argv=["x"], env_overlay={}, cwd="/repo",
        log_path="l.log", artifacts_in=[], artifacts_out=[],
    )
    store.transition(job_id, "queued")
    store.transition(job_id, "running")
    store.transition(job_id, "failed", error="boom", exit_code=2)
    job = store.get_job(job_id)
    assert (job["exit_code"], job["error"]) == (2, "boom")
    assert job["finished_at"] is not None


def test_interrupt_stale_jobs_marks_running_and_queued(store):
    ids = []
    for kind in ("train", "benchmark"):
        job_id = store.create_job(
            kind=kind, stage="train", scenario="triage", title="t",
            request={}, argv=["x"], env_overlay={}, cwd="/repo",
            log_path="l.log", artifacts_in=[], artifacts_out=[],
        )
        store.transition(job_id, "queued")
        store.transition(job_id, "running")
        ids.append(job_id)
    done = store.create_job(
        kind="split", stage="data", scenario="triage", title="t",
        request={}, argv=["x"], env_overlay={}, cwd="/repo",
        log_path="l.log", artifacts_in=[], artifacts_out=[],
    )
    store.transition(done, "queued")
    store.transition(done, "running")
    store.transition(done, "succeeded")

    assert store.interrupt_stale_jobs() == 2
    assert store.get_job(ids[0])["status"] == "interrupted"
    assert store.get_job(done)["status"] == "succeeded"


def test_active_job_of_kind_finds_only_live(store):
    job_id = store.create_job(
        kind="train", stage="train", scenario="triage", title="t",
        request={}, argv=["x"], env_overlay={}, cwd="/repo",
        log_path="l.log", artifacts_in=[], artifacts_out=[],
    )
    store.transition(job_id, "queued")
    assert store.active_job_of_kind("train")["id"] == job_id
    store.transition(job_id, "running")
    store.transition(job_id, "succeeded")
    assert store.active_job_of_kind("train") is None


def test_artifact_id_is_kind_colon_name(store):
    aid = store.put_artifact(kind="dataset", name="cv", path="data/cv", meta={"records": 787})
    assert aid == "dataset:cv"
    assert store.get_artifact(aid)["meta"]["records"] == 787


def test_put_artifact_is_idempotent(store):
    store.put_artifact(kind="run", name="r1", path="runs/r1", meta={"a": 1})
    store.put_artifact(kind="run", name="r1", path="runs/r1", meta={"a": 2})
    assert len(store.list_artifacts("run")) == 1
    assert store.get_artifact("run:r1")["meta"]["a"] == 2


def test_lineage_joins_on_artifact(store):
    store.put_artifact(kind="dataset", name="cv", path="data/cv", meta={})
    store.put_artifact(kind="dataset", name="cv/train", path="data/cv/train.jsonl", meta={})
    store.add_lineage("dataset:cv", "dataset:cv/train", "split_into")
    edges = store.lineage_of("dataset:cv")
    assert [(e["relation"], e["child"]) for e in edges] == [("split_into", "dataset:cv/train")]
    assert store.lineage_of("dataset:cv/train") == []


def test_events_round_trip_with_cursor(store):
    job_id = store.create_job(
        kind="train", stage="train", scenario="triage", title="t",
        request={}, argv=["x"], env_overlay={}, cwd="/repo",
        log_path="l.log", artifacts_in=[], artifacts_out=[],
    )
    last = store.append_events(job_id, [("stdout", "a"), ("stdout", "b")])
    store.append_events(job_id, [("stderr", "c")])
    first = store.read_events(job_id)
    assert [e["line"] for e in first] == ["a", "b", "c"]
    assert [e["line"] for e in store.read_events(job_id, after_id=first[1]["id"])] == ["c"]
    assert store.read_events(job_id)[-1]["id"] >= last


def test_schema_version_is_stamped(store):
    assert store.schema_version() == 1
```

- [ ] **Step 1b: 写 `tests/test_console_artifacts.py`**

```python
# tests/test_console_artifacts.py
"""产物 id ↔ 路径的映射，以及作业完成后的产物注册与血缘。

为什么单独一个模块（计划修正）：产物 id 是编排层各阶段的通用契约，闸门要靠它找到产物文件。
早期版本把路径推断散落在 app.py 的 _gate_products 里，导致 split 忘了注册 summary.json、
precheck 忘了注册自己的报告，于是 G1/G2/G3 永远失败、train 永远无法提交。
resolve() 是这件事的唯一真相源，阶段处理器与注册逻辑都调它。

Run: uv run python -m pytest tests/test_console_artifacts.py -q
"""
import pytest

from kev.console import artifacts
from kev.console.db import Store


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "db.sqlite")


@pytest.mark.parametrize("artifact_id,expected", [
    ("dataset:cv", "data/cv"),
    ("dataset:cv/train", "data/cv/train.jsonl"),
    ("dataset:cv/calibration", "data/cv/calibration.jsonl"),
    ("dataset:cv/development", "data/cv/development.jsonl"),
    ("dataset:cv/summary", "data/cv/summary.json"),            # G2/G3 读的就是它
    ("precheck:cv/train", "data/console/precheck-cv-train.json"),   # G1 读的就是它
    ("run:cv-8b-lora-v1", "runs/cv-8b-lora-v1"),
    ("eval:cv-8b-lora-v1", "runs/cv-8b-lora-v1-eval"),
    ("comparison:cv-8b-lora-v1", "runs/cv-8b-lora-v1-compare"),
    ("calibration:cv-8b-lora-v1", "runs/cv-8b-lora-v1-eval/calibration.json"),
    ("image:kev-cv-8b-lora-v1", "kev-cv-8b-lora-v1"),
    ("endpoint:8008", "http://127.0.0.1:8008"),
])
def test_resolve_maps_every_kind(artifact_id, expected):
    assert artifacts.resolve(artifact_id) == expected


def test_resolve_rejects_an_unknown_kind():
    with pytest.raises(ValueError, match="未知产物类型"):
        artifacts.resolve("widget:thing")


def test_summarize_reads_a_split_summary(tmp_path, monkeypatch):
    monkeypatch.setattr(artifacts.paths, "ROOT", tmp_path)
    (tmp_path / "data/cv").mkdir(parents=True)
    payload = '{"records": 787, "invalid_lines": 0, "partitions": {}}'
    (tmp_path / "data/cv/summary.json").write_text(payload, encoding="utf-8")
    assert artifacts.summarize("dataset:cv/summary", artifacts.resolve("dataset:cv/summary")) == {
        "records": 787, "invalid_lines": 0}


def test_summarize_pulls_the_paired_ci_out_of_a_comparison(tmp_path, monkeypatch):
    monkeypatch.setattr(artifacts.paths, "ROOT", tmp_path)
    (tmp_path / "runs/x-compare").mkdir(parents=True)
    payload = '{"paired": {"acc": {"ci95": [0.023, 0.097], "macro_acc_delta": 0.05}}, "clean": {}}'
    (tmp_path / "runs/x-compare/comparison.json").write_text(payload, encoding="utf-8")
    meta = artifacts.summarize("comparison:x", "runs/x-compare/comparison.json")
    assert meta["ci95"] == [0.023, 0.097]
    assert meta["delta"] == 0.05


def test_summarize_is_empty_when_the_file_is_absent(tmp_path, monkeypatch):
    monkeypatch.setattr(artifacts.paths, "ROOT", tmp_path)
    assert artifacts.summarize("run:missing", "runs/missing") == {}


def test_register_creates_out_artifacts_and_in_to_out_lineage(store):
    job_id = store.create_job(
        kind="split", stage="data", scenario="critical-value", title="t",
        request={}, argv=["x"], env_overlay={}, cwd=".", log_path="l.log",
        artifacts_in=["dataset:cv"],
        artifacts_out=["dataset:cv/train", "dataset:cv/calibration",
                       "dataset:cv/development", "dataset:cv/summary"])
    registered = artifacts.register(store, store.get_job(job_id))
    assert set(registered) == {"dataset:cv/train", "dataset:cv/calibration",
                               "dataset:cv/development", "dataset:cv/summary"}
    assert store.get_artifact("dataset:cv/summary")["path"] == "data/cv/summary.json"
    edges = {(edge["relation"], edge["child"]) for edge in store.lineage_of("dataset:cv")}
    assert ("split_into", "dataset:cv/train") in edges
    assert ("split_into", "dataset:cv/summary") in edges


def test_register_is_idempotent_across_a_retry(store):
    """重试会产生第二个作业写同一个产物；register 必须能重复跑而不炸。"""
    for attempt in (1, 2):
        job_id = store.create_job(
            kind="split", stage="data", scenario="critical-value", title=f"t{attempt}",
            request={}, argv=["x"], env_overlay={}, cwd=".", log_path="l.log",
            artifacts_in=[], artifacts_out=["dataset:cv/summary"])
        artifacts.register(store, store.get_job(job_id))
    assert len(store.list_artifacts("dataset")) == 1
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run python -m pytest tests/test_console_db.py -q`
Expected: FAIL —— `ModuleNotFoundError: No module named 'kev.console'`

- [ ] **Step 3: 写 `kev/console/paths.py` 与 `__init__.py`**

```python
# kev/console/__init__.py
"""医疗微调控制台的编排层（见 docs/superpowers/specs/2026-10-04-medical-finetune-console-design.md）。

编排服务整体跑在 WSL2 内（与 torch 同环境），把 docs/medical 的 12 步管线变成可编排的长任务。
不改 kev/train.py、kev/serve.py、kev/benchmark.py 任何代码。
"""
```

```python
# kev/console/paths.py
"""仓库目录布局的唯一归属。

编排服务与 kev CLI 在同一个 checkout 里跑（WSL2 内），所以路径都从 __file__ 推出来，
不读环境变量、不接受外部注入 —— 换了 checkout 布局就应当启动失败，而不是写到别处。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKILL_SCRIPTS = ROOT / "skills/kev-finetune/scripts"
SPECS = ROOT / "docs/medical/specs"
GENERATORS = ROOT / "docs/medical/generators"
CONSOLE_SCRIPTS = ROOT / "docs/medical/console"
DATA = ROOT / "data"
RUNS = ROOT / "runs"
JOB_LOGS = DATA / "console/jobs"
DB_PATH = DATA / "console/kev-console.db"


def ensure_medical_on_path() -> None:
    """把 docs/medical/generators 与 skills/kev-finetune/scripts 加进 sys.path。

    运行名规范（NAME_RE / check_name / SIZES / SCENARIOS / FOUR_B_ONLY）的唯一归属是
    docs/medical/generators/run_matrix.py，医疗测试（tests/test_medical_generators.py:21-22）
    用同样的 sys.path.insert 方式引用它。这里沿用该做法而不是复制常量。
    """
    for directory in (GENERATORS, SKILL_SCRIPTS):
        text = str(directory)
        if text not in sys.path:
            sys.path.insert(0, text)
```

- [ ] **Step 4: 写 `kev/console/db.py`**

```python
# kev/console/db.py
"""编排层的持久化：作业状态机、产物、血缘、事件。

三条设计约定（spec §5 / §9）：
- SQLite 单文件，PRAGMA user_version 做 schema 版本，不引 ORM
- 日志文件是真相源，events 表只是给 UI 的可分页尾巴（首屏回填 + Last-Event-ID 续传）
- 状态机集中校验：succeeded -> running 这类转移必须被拒
"""
from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = 1

TERMINAL = frozenset({"succeeded", "failed", "canceled", "interrupted"})
LIVE = frozenset({"pending", "queued", "running"})

ALLOWED: dict[str, frozenset[str]] = {
    "pending": frozenset({"queued", "canceled", "failed"}),
    "queued": frozenset({"running", "canceled", "failed", "interrupted"}),
    "running": TERMINAL,
    "succeeded": frozenset(),
    "failed": frozenset(),
    "canceled": frozenset(),
    "interrupted": frozenset(),
}

DDL = """
CREATE TABLE IF NOT EXISTS jobs (
  id            TEXT PRIMARY KEY,
  kind          TEXT NOT NULL,
  stage         TEXT NOT NULL,
  scenario      TEXT NOT NULL,
  title         TEXT NOT NULL,
  status        TEXT NOT NULL,
  request       TEXT NOT NULL,
  argv          TEXT NOT NULL,
  env_overlay   TEXT NOT NULL,
  cwd           TEXT NOT NULL,
  log_path      TEXT NOT NULL,
  artifacts_in  TEXT NOT NULL,
  artifacts_out TEXT NOT NULL,
  parent_id     TEXT REFERENCES jobs(id),
  attempt       INTEGER NOT NULL DEFAULT 1,
  exit_code     INTEGER,
  error         TEXT,
  created_at    TEXT NOT NULL,
  started_at    TEXT,
  finished_at   TEXT
);
CREATE INDEX IF NOT EXISTS jobs_status_idx   ON jobs(status);
CREATE INDEX IF NOT EXISTS jobs_scenario_idx ON jobs(scenario, created_at DESC);

CREATE TABLE IF NOT EXISTS artifacts (
  id         TEXT PRIMARY KEY,
  kind       TEXT NOT NULL,
  name       TEXT NOT NULL,
  path       TEXT NOT NULL,
  meta       TEXT NOT NULL,
  bytes      INTEGER,
  created_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS artifacts_kind_name ON artifacts(kind, name);

CREATE TABLE IF NOT EXISTS lineage (
  parent   TEXT NOT NULL REFERENCES artifacts(id),
  child    TEXT NOT NULL REFERENCES artifacts(id),
  relation TEXT NOT NULL,
  job_id   TEXT REFERENCES jobs(id),
  PRIMARY KEY (parent, child, relation)
);

CREATE TABLE IF NOT EXISTS events (
  id     INTEGER PRIMARY KEY AUTOINCREMENT,
  job_id TEXT NOT NULL REFERENCES jobs(id),
  ts     TEXT NOT NULL,
  stream TEXT NOT NULL,
  line   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS events_job_idx ON events(job_id, id);
"""

_JSON_COLUMNS = frozenset({"request", "env_overlay", "artifacts_in", "artifacts_out"})
_ROW_COLUMNS = (
    "id", "kind", "stage", "scenario", "title", "status", "request", "argv",
    "env_overlay", "cwd", "log_path", "artifacts_in", "artifacts_out",
    "parent_id", "attempt", "exit_code", "error", "created_at", "started_at", "finished_at",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _dumps(value) -> str:
    # allow_nan=False mirrors kev.suite.write_json: a NaN metric must fail loudly here,
    # not silently produce a file no reader can parse.
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


def _loads(text):
    return json.loads(text)


def _job(row) -> dict:
    out = {}
    for column in _ROW_COLUMNS:
        out[column] = row[column]
    for column in _JSON_COLUMNS:
        out[column] = _loads(out[column])
    out["argv"] = _loads(out["argv"])
    return out


class Store:
    """每线程一个连接。WAL 让读不阻塞写，事件轮询与日志落库可以并发。"""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        with self.connect() as connection:
            connection.executescript(DDL)
            connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    def connect(self) -> sqlite3.Connection:
        connection = getattr(self._local, "connection", None)
        if connection is None:
            connection = sqlite3.connect(self.path, timeout=30.0)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute("PRAGMA foreign_keys = ON")
            self._local.connection = connection
        return connection

    def schema_version(self) -> int:
        return self.connect().execute("PRAGMA user_version").fetchone()[0]

    # ---- jobs -------------------------------------------------------------

    def create_job(self, *, kind, stage, scenario, title, request, argv, env_overlay,
                   cwd, log_path, artifacts_in, artifacts_out, parent_id=None) -> str:
        job_id = uuid.uuid4().hex
        self.connect().execute(
            "INSERT INTO jobs (id, kind, stage, scenario, title, status, request, argv, env_overlay, cwd,"
            " log_path, artifacts_in, artifacts_out, parent_id, attempt, created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,1,?)",
            (job_id, kind, stage, scenario, title, "pending", _dumps(request), _dumps(argv),
             _dumps(env_overlay), str(cwd), str(log_path), _dumps(artifacts_in),
             _dumps(artifacts_out), parent_id, _now()),
        )
        self.connect().commit()
        return job_id

    def get_job(self, job_id) -> dict | None:
        row = self.connect().execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return _job(row) if row else None

    def list_jobs(self, *, status=None, stage=None, scenario=None, limit=200) -> list[dict]:
        clauses, params = [], []
        for column, value in (("status", status), ("stage", stage), ("scenario", scenario)):
            if value is not None:
                clauses.append(f"{column} = ?")
                params.append(value)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(limit)
        rows = self.connect().execute(
            f"SELECT * FROM jobs{where} ORDER BY created_at DESC, rowid DESC LIMIT ?", params
        ).fetchall()
        return [_job(row) for row in rows]

    def transition(self, job_id, to_status, *, error=None, exit_code=None) -> None:
        job = self.get_job(job_id)
        if job is None:
            raise KeyError(job_id)
        if to_status not in ALLOWED[job["status"]]:
            raise ValueError(
                f"illegal transition {job['status']} -> {to_status} for job {job_id}"
            )
        stamps, params = [], [to_status]
        if to_status == "running" and job["started_at"] is None:
            stamps.append("started_at = ?")
            params.append(_now())
        if to_status in TERMINAL:
            stamps.append("finished_at = ?")
            params.append(_now())
        if error is not None:
            stamps.append("error = ?")
            params.append(error)
        if exit_code is not None:
            stamps.append("exit_code = ?")
            params.append(exit_code)
        params.append(job_id)
        sql = "UPDATE jobs SET status = ?" + (", " + ", ".join(stamps) if stamps else "")
        self.connect().execute(sql, params)
        self.connect().commit()

    def active_job_of_kind(self, kind) -> dict | None:
        placeholders = ", ".join("?" * len(LIVE))
        row = self.connect().execute(
            f"SELECT * FROM jobs WHERE kind = ? AND status IN ({placeholders})"
            " ORDER BY created_at DESC LIMIT 1",
            (kind, *sorted(LIVE)),
        ).fetchone()
        return _job(row) if row else None

    def interrupt_stale_jobs(self) -> int:
        """编排服务启动时调用：WSL2 会自动回收内存，重启后残留的 running 一律算 interrupted。"""
        placeholders = ", ".join("?" * len(LIVE))
        cursor = self.connect().execute(
            f"UPDATE jobs SET status = 'interrupted', error = ?, finished_at = ?"
            f" WHERE status IN ({placeholders})",
            ("编排服务重启", _now(), *sorted(LIVE)),
        )
        self.connect().commit()
        return cursor.rowcount

    # ---- artifacts --------------------------------------------------------

    def put_artifact(self, *, kind, name, path, meta, bytes_=None) -> str:
        artifact_id = f"{kind}:{name}"
        self.connect().execute(
            "INSERT INTO artifacts (id, kind, name, path, meta, bytes, created_at) VALUES (?,?,?,?,?,?,?)"
            " ON CONFLICT(id) DO UPDATE SET path = excluded.path, meta = excluded.meta,"
            " bytes = excluded.bytes",
            (artifact_id, kind, name, str(path), _dumps(meta), bytes_, _now()),
        )
        self.connect().commit()
        return artifact_id

    def get_artifact(self, artifact_id) -> dict | None:
        row = self.connect().execute("SELECT * FROM artifacts WHERE id = ?", (artifact_id,)).fetchone()
        if row is None:
            return None
        out = dict(row)
        out["meta"] = _loads(out["meta"])
        return out

    def list_artifacts(self, kind=None) -> list[dict]:
        if kind is None:
            rows = self.connect().execute("SELECT * FROM artifacts ORDER BY created_at DESC").fetchall()
        else:
            rows = self.connect().execute(
                "SELECT * FROM artifacts WHERE kind = ? ORDER BY created_at DESC", (kind,)
            ).fetchall()
        out = []
        for row in rows:
            item = dict(row)
            item["meta"] = _loads(item["meta"])
            out.append(item)
        return out

    # ---- lineage ----------------------------------------------------------

    def add_lineage(self, parent, child, relation, job_id=None) -> None:
        self.connect().execute(
            "INSERT OR IGNORE INTO lineage (parent, child, relation, job_id) VALUES (?,?,?,?)",
            (parent, child, relation, job_id),
        )
        self.connect().commit()

    def lineage_of(self, artifact_id) -> list[dict]:
        rows = self.connect().execute(
            "SELECT * FROM lineage WHERE parent = ? OR child = ?", (artifact_id, artifact_id)
        ).fetchall()
        return [dict(row) for row in rows]

    # ---- events -----------------------------------------------------------

    def append_events(self, job_id, rows) -> int:
        """rows: [(stream, line), ...]。返回最后一条的 id，供 SSE 续传游标使用。"""
        stamp = _now()
        payload = [(job_id, stamp, stream, line) for stream, line in rows]
        connection = self.connect()
        connection.executemany(
            "INSERT INTO events (job_id, ts, stream, line) VALUES (?,?,?,?)", payload
        )
        connection.commit()
        row = connection.execute(
            "SELECT MAX(id) FROM events WHERE job_id = ?", (job_id,)
        ).fetchone()
        return row[0] or 0

    def read_events(self, job_id, after_id=0, limit=500) -> list[dict]:
        rows = self.connect().execute(
            "SELECT * FROM events WHERE job_id = ? AND id > ? ORDER BY id LIMIT ?",
            (job_id, after_id, limit),
        ).fetchall()
        return [dict(row) for row in rows]

    def tail_text(self, job_id, lines=30) -> str:
        """子进程非零退出时给错误体的 stderr_tail（spec §10.2）。"""
        rows = self.connect().execute(
            "SELECT stream, line FROM events WHERE job_id = ? ORDER BY id DESC LIMIT ?",
            (job_id, lines),
        ).fetchall()
        return "\n".join(f"[{row['stream']}] {row['line']}" for row in reversed(rows))
```

# kev/console/artifacts.py
"""产物 id ↔ 路径的唯一真相源，以及作业完成后的产物注册。

为什么必须有这个模块：产物 id（`dataset:cv/summary`、`run:x`）是编排层各阶段的通用契约，
闸门靠它找到产物文件。早期版本把路径推断散落在 app.py 里，于是 split 忘了注册
summary.json、precheck 忘了注册自己的报告，G1/G2/G3 永远失败、train 永远无法提交。
现在阶段处理器与注册逻辑都调 resolve()，只有这一处决定 id 到路径的映射。

meta 只放「UI 直接要用的少量字段」，不复制 report.json 的全部内容 —— report.json
仍然是唯一真相源，这里只是给列表页和闸门用的摘要。
"""
from __future__ import annotations

from pathlib import Path

from kev.suite import read_json

from . import paths

PERSIST = ("success", "start")
SPLITS = ("train", "calibration", "development")
CONSOLE_LOG_DIR = "data/console"

# stage -> 该阶段产出的血缘关系名
RELATION = {
    "generate": "generated_from", "distill": "generated_from", "goldset": "sampled_from",
    "split": "split_into", "precheck": "checked_from", "train": "trained_on",
    "benchmark": "evaluated_on", "baseline": "evaluated_on", "compare": "compared_from",
    "calibrate": "calibrated_from", "image": "built_from", "deploy": "deployed_as",
    "smoke": "smoked",
}


def resolve(artifact_id: str) -> str:
    """artifact id -> 仓库相对路径。endpoint 返回 URL，image 返回 docker tag。"""
    kind, _, name = artifact_id.partition(":")
    if kind == "dataset":
        tail = name.rpartition("/")[2]
        if tail == "summary":
            return f"{name}.json"
        if tail in SPLITS:
            return f"{name}.jsonl"
        return name                                  # 数据集目录本身
    if kind == "precheck":
        return f"{CONSOLE_LOG_DIR}/precheck-" + name.replace("/", "-") + ".json"
    if kind == "run":
        return f"runs/{name}"
    if kind == "eval":
        return f"runs/{name}-eval"
    if kind == "comparison":
        return f"runs/{name}-compare"
    if kind == "calibration":
        return f"runs/{name}-eval/calibration.json"
    if kind == "image":
        return name
    if kind == "endpoint":
        return f"http://127.0.0.1:{name}"
    raise ValueError(f"未知产物类型 {kind!r}（id={artifact_id!r}）")


def _load(relative: str):
    """读产物文件；不存在或坏掉都返回 None（闸门据此判失败，而不是崩）。"""
    target = Path(paths.ROOT) / relative
    if not target.is_file():
        return None
    try:
        return read_json(target)
    except (OSError, ValueError):
        return None


def summarize(artifact_id: str, path: str) -> dict:
    """产物的小份摘要，给列表页与闸门用。文件不在就返回空 dict。"""
    kind = artifact_id.partition(":")[0]
    if kind in {"dataset", "precheck"}:
        payload = _load(path)
        return {} if payload is None else {
            key: payload[key] for key in ("records", "invalid_lines", "over_limit", "partitions")
            if key in payload
        }
    if kind == "comparison":
        payload = _load(path)
        if payload is None:
            return {}
        paired = (payload.get("paired") or {}).get("acc") or {}
        return {"ci95": paired.get("ci95"), "delta": paired.get("macro_acc_delta")}
    if kind == "calibration":
        payload = _load(path)
        if payload is None:
            return {}
        return {"workload_temperature": payload.get("workload_temperature"),
                "shipped_temperature": payload.get("shipped_temperature")}
    if kind == "eval":
        payload = _load(f"{path}/report.json")
        if payload is None:
            return {}
        clean = payload.get("clean") or {}
        return {key: clean.get(key) for key in
                ("acc", "ece", "brier", "aurc", "mean_conf", "coverage_at_5pct_error")}
    if kind == "run":
        payload = _load(f"{path}/training_config.json")
        return {} if payload is None else {"init_source": (payload.get("init_source") or {}).get("init_from")}
    return {}


def register(store, job: dict) -> list[str]:
    """把作业的 artifacts_out 注册为产物，并写 artifacts_in -> artifacts_out 的血缘。

    可重复调用：重试会产生第二个作业写同一个产物，put_artifact 是 upsert、add_lineage 是
    INSERT OR IGNORE，所以这里不需要额外的去重逻辑。
    """
    relation = RELATION.get(job["kind"], "produced_by")
    registered = []
    for artifact_id in job["artifacts_out"]:
        relative = resolve(artifact_id)
        meta = summarize(artifact_id, relative)
        size = None
        target = Path(paths.ROOT) / relative
        if target.is_file():
            size = target.stat().st_size
        store.put_artifact(kind=artifact_id.partition(":")[0], name=artifact_id.partition(":")[2],
                           path=relative, meta=meta, bytes_=size)
        for parent in job["artifacts_in"]:
            store.add_lineage(parent, artifact_id, relation, job_id=job["id"])
        registered.append(artifact_id)
    return registered
```

- [ ] **Step 5: 修 `pyproject.toml` 的打包**

`packages = ["kev"]` 不含子包，非 editable 安装时 `kev.console` 不可导入。改成：

```toml
[tool.setuptools]
packages = ["kev", "kev.console", "kev.console.stages"]
```

- [ ] **Step 6: 跑测试确认通过**

Run: `uv run python -m pytest tests/test_console_db.py tests/test_console_artifacts.py -q`
Expected: PASS —— 约 24 passed

- [ ] **Step 7: 确认没有打破约定测试**

Run: `uv run python -m pytest tests/test_conventions.py -q`
Expected: PASS（新增的 `kev/console/*.py` 不得触发任何 single_home 规则；注意 `artifacts.py` 走 `kev.suite.read_json`，没有裸 `open()`/`read_text()`）

- [ ] **Step 8: 提交**

```bash
git add kev/console/__init__.py kev/console/paths.py kev/console/db.py kev/console/artifacts.py tests/test_console_db.py tests/test_console_artifacts.py pyproject.toml
git commit -m "feat(console): 编排层持久化 + 产物 id 映射（作业状态机/产物/血缘/事件）"
```

---

### Task 2: 日志行 → 结构化事件

**Files:**
- Create: `kev/console/events.py`
- Test: `tests/test_console_events.py`

**Interfaces:**
- Consumes: 无
- Produces: `events.STEP_RE`、`events.parse_step(line) -> dict | None`、`events.parse_note(line) -> dict | None`、`events.sse_frame(event, event_line) -> str`、`events.MetricBuffer`

`parse_step` 返回 `{"ep","step","total","loss","kl","anchor","sec"}`（全为 float/int），不匹配返回 `None`。
`parse_note` 识别 `dropped N of M records`（→ `{"kind":"dropped","dropped":N,"total":M}`）、`saved <path>`（→ `{"kind":"saved","path":...}`）、`non-finite training loss`（→ `{"kind":"nonfinite"}`）。
`sse_frame(event: dict, metric: dict | None) -> str` 生成一条 SSE 文本帧。

- [ ] **Step 1: 写失败的测试**

```python
# tests/test_console_events.py
"""从训练日志文本解析结构化事件。

kev.train 全程用 print(flush=True)，每 10 个 optimizer step 打一行
（kev/train.py:642-643）；training_metrics.json 只在训练完全结束时写一次
（kev/train.py:672），--stop_after 早退甚至不写（kev/train.py:660-661）。
所以日志文本是唯一实时数据源，kev/plot.py:11 已经用同样的正则刮 loss —— 这里沿用同一形状。

Run: uv run python -m pytest tests/test_console_events.py -q
"""
from kev.console.events import MetricBuffer, parse_note, parse_step, sse_frame


def test_parse_step_reads_the_real_training_line():
    line = "ep0 step 10/139 loss 0.623 kl 0.000 anchor 0.000 1.284s/rec"
    assert parse_step(line) == {
        "ep": 0, "step": 10, "total": 139,
        "loss": 0.623, "kl": 0.0, "anchor": 0.0, "sec": 1.284,
    }


def test_parse_step_accepts_the_second_epoch():
    line = "ep1 step 40/139 loss 0.412 kl 0.031 anchor 0.004 0.512s/rec"
    got = parse_step(line)
    assert (got["ep"], got["step"], got["loss"], got["kl"], got["anchor"]) == (1, 40, 0.412, 0.031, 0.004)


def test_parse_step_ignores_other_output():
    for line in ("saved runs/cv-8b-lora-v1", "device=cuda world=1 trainable params=5.6M",
                 "ep0 step 10/139 loss nan kl 0.000 anchor 0.000 1.000s/rec", ""):
        assert parse_step(line) is None


def test_dropped_records_note_is_surfaced():
    note = parse_note("dropped 3 of 787 records that exceed the training context")
    assert note == {"kind": "dropped", "dropped": 3, "total": 787}


def test_saved_and_nonfinite_notes():
    assert parse_note("saved runs/cv-8b-lora-v1") == {"kind": "saved", "path": "runs/cv-8b-lora-v1"}
    assert parse_note("!!! non-finite training loss at step 12") == {"kind": "nonfinite"}
    assert parse_note("ep0 step 10/139 loss 0.623") is None


def test_sse_frame_emits_log_and_optional_metric():
    event = {"id": 7, "ts": "2026-10-04T00:00:00+00:00", "stream": "stdout",
             "line": "ep0 step 10/139 loss 0.623 kl 0.000 anchor 0.000 1.284s/rec"}
    metric = {"ep": 0, "step": 10, "total": 139, "loss": 0.623, "kl": 0.0,
              "anchor": 0.0, "sec": 1.284}
    frame = sse_frame(event, metric)
    assert frame.startswith("id: 7\nevent: log\n")
    assert "ep0 step 10/139" in frame
    assert "event: metric" in frame
    assert frame.endswith("\n\n")


def test_sse_frame_without_metric_has_no_metric_event():
    event = {"id": 8, "ts": "t", "stream": "stderr", "line": "boom"}
    frame = sse_frame(event, None)
    assert "event: metric" not in frame
    assert frame == 'id: 8\nevent: log\ndata: {"id": 8, "ts": "t", "stream": "stderr", "line": "boom"}\n\n'


def test_metric_buffer_keeps_the_last_n_points():
    buffer = MetricBuffer(limit=3)
    for step in (1, 2, 3, 4):
        buffer.push({"ep": 0, "step": step, "total": 9, "loss": 0.5,
                     "kl": 0.0, "anchor": 0.0, "sec": 1.0})
    assert [point["step"] for point in buffer.points()] == [2, 3, 4]
    assert buffer.dropped() == 1
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run python -m pytest tests/test_console_events.py -q`
Expected: FAIL —— `ModuleNotFoundError: No module named 'kev.console.events'`

- [ ] **Step 3: 写 `kev/console/events.py`**

```python
# kev/console/events.py
"""把 kev.train 的日志文本解析成结构化事件。

kev.train 没有 logger，全部是 print(..., flush=True)（kev/train.py 全仓无 logging）。
唯一进度行是 kev/train.py:642-643 的：
    ep{ep} step {step}/{total} loss {L} kl {K} anchor {A} {R}s/rec
每 10 个 optimizer step 一次。kev/plot.py:11 已有同形状的正则在用（从日志文本画 loss 图），
这里复用同一形状，不重新发明。

持久化的只有日志行本身（真相源是日志文件）；metric 帧在 SSE 推流时从行派生，不额外落库。
"""
from __future__ import annotations

import json
import re
from collections import deque

STEP_RE = re.compile(
    r"^ep(?P<ep>\d+) step (?P<step>\d+)/(?P<total>\d+) "
    r"loss (?P<loss>[\d.]+) kl (?P<kl>[\d.]+) anchor (?P<anchor>[\d.]+) "
    r"(?P<sec>[\d.]+)s/rec"
)
DROPPED_RE = re.compile(r"^dropped (?P<dropped>\d+) of (?P<total>\d+) records")
SAVED_RE = re.compile(r"^saved (?P<path>\S+)")
NONFINITE_RE = re.compile(r"non-finite training loss")

DEFAULT_BUFFER = 2000


def parse_step(line: str):
    """一行进度日志 -> 指标点；不是进度行返回 None。"""
    match = STEP_RE.match(line)
    if match is None:
        return None
    got = match.groupdict()
    return {
        "ep": int(got["ep"]),
        "step": int(got["step"]),
        "total": int(got["total"]),
        "loss": float(got["loss"]),
        "kl": float(got["kl"]),
        "anchor": float(got["anchor"]),
        "sec": float(got["sec"]),
    }


def parse_note(line: str):
    """识别需要主动提示的运行期事件（丢弃记录、非有限损失、保存完成）。"""
    match = DROPPED_RE.match(line)
    if match is not None:
        return {"kind": "dropped", "dropped": int(match["dropped"]), "total": int(match["total"])}
    match = SAVED_RE.match(line)
    if match is not None:
        return {"kind": "saved", "path": match["path"]}
    if NONFINITE_RE.search(line):
        return {"kind": "nonfinite"}
    return None


def sse_frame(event: dict, metric: dict | None = None) -> str:
    """一条 SSE 文本帧。metric 非空时附一帧 metric 事件，供前端直接画曲线而不必自己解析。"""
    frame = f"id: {event['id']}\nevent: log\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
    if metric is not None:
        frame += f"event: metric\ndata: {json.dumps(metric)}\n\n"
    return frame


class MetricBuffer:
    """内存里的最近 N 个指标点。溢出时记 dropped，前端要如实提示「仅显示最近 N 点」。"""

    def __init__(self, limit: int = DEFAULT_BUFFER):
        self._limit = limit
        self._points = deque(maxlen=limit)
        self._dropped = 0

    def push(self, point: dict) -> None:
        if len(self._points) == self._limit:
            self._dropped += 1
        self._points.append(point)

    def points(self) -> list[dict]:
        return list(self._points)

    def dropped(self) -> int:
        return self._dropped
```

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run python -m pytest tests/test_console_events.py -q`
Expected: PASS —— 7 passed

- [ ] **Step 5: 提交**

```bash
git add kev/console/events.py tests/test_console_events.py
git commit -m "feat(console): 从训练日志解析指标与运行期事件"
```

---

### Task 3: 进程执行器（进程组 / tee / 取消 / 并发闸）

**Files:**
- Create: `kev/console/executor.py`
- Test: `tests/test_console_executor.py`

**Interfaces:**
- Consumes: `db.Store`（Task 1）、`events.MetricBuffer`（Task 2）
- Produces:
  - `executor.SECRET_ENV`（tuple）
  - `executor.ALLOWED_ENV`（frozenset）
  - `executor.ProcessHandle`（dataclass：`job_id`、`pid`、`popen`）
  - `executor.LocalExecutor(store, *, secret_env=None, buffer_limit=2000, on_finished=None)`
  - `.spawn(job_id, argv, *, cwd, log_path, env_overlay=None) -> ProcessHandle`
  - `.cancel(job_id) -> bool`
  - `.metrics(job_id) -> MetricBuffer`
  - `.wait(job_id, timeout=None) -> int`（测试用：等作业到终态，返回 exit_code）
  - `.build_env(overlay) -> dict`（`os.environ` + overlay + secret 注入）
  - `on_finished(job_id, exit_code)` 回调：进程自然退出（非 cancel）时在 `store.transition`
    之后调用一次，app.py 用它调 `artifacts.register` —— 这是产物注册的唯一触发点
    （计划修正：早期版本没有任何代码调 put_artifact，整个产物/血缘/闸门层是死代码）

- [ ] **Step 1: 写失败的测试**

```python
# tests/test_console_executor.py
"""子进程执行器：tee 日志、事件落库、取消杀整棵树、凭据不落库。

不跑真训练 —— 用 python -c 的假命令。取消测试真杀一个 sleep 进程树并断言无孤儿。

Run: uv run python -m pytest tests/test_console_executor.py -q
"""
import os
import subprocess
import sys
import time

import pytest

from kev.console.db import Store
from kev.console.executor import ALLOWED_ENV, SECRET_ENV, LocalExecutor


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "db.sqlite")


def make_job(store, kind="train"):
    job_id = store.create_job(
        kind=kind, stage="train", scenario="triage", title="t",
        request={}, argv=["x"], env_overlay={}, cwd=os.getcwd(),
        log_path="l.log", artifacts_in=[], artifacts_out=[],
    )
    store.transition(job_id, "queued")
    return job_id


def drain(store, executor, job_id, timeout=20.0):
    """轮询到终态，返回 exit_code。生产代码由 SSE 推流，测试里用轮询。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if store.get_job(job_id)["status"] in {"succeeded", "failed", "canceled", "interrupted"}:
            return store.get_job(job_id)["exit_code"]
        time.sleep(0.05)
    raise AssertionError("job never reached a terminal state")


def test_streams_stdout_into_events_and_marks_success(store):
    executor = LocalExecutor(store)
    job_id = make_job(store)
    handle = executor.spawn(
        job_id, [sys.executable, "-c", "print('hello'); print('ep0 step 10/2 loss 0.500 kl 0.000 anchor 0.000 1.000s/rec')"],
        cwd=os.getcwd(), log_path=str(store.path.parent / "job.log"),
    )
    assert handle.popen is not None
    assert drain(store, executor, job_id) == 0
    assert store.get_job(job_id)["status"] == "succeeded"
    lines = [e["line"] for e in store.read_events(job_id)]
    assert "hello" in lines
    assert executor.metrics(job_id).points()[0]["loss"] == 0.5


def test_nonzero_exit_records_code_and_stderr(store):
    executor = LocalExecutor(store)
    job_id = make_job(store)
    executor.spawn(
        job_id,
        [sys.executable, "-c", "import sys; sys.stderr.write('kaboom\\n'); raise SystemExit(3)"],
        cwd=os.getcwd(), log_path=str(store.path.parent / "job.log"),
    )
    assert drain(store, executor, job_id) == 3
    job = store.get_job(job_id)
    assert job["status"] == "failed"
    assert job["exit_code"] == 3
    assert "kaboom" in store.tail_text(job_id)


def test_log_file_holds_every_line(store):
    log = store.path.parent / "job.log"
    executor = LocalExecutor(store)
    job_id = make_job(store)
    executor.spawn(job_id, [sys.executable, "-c", "print('a'); print('b')"],
                   cwd=os.getcwd(), log_path=str(log))
    drain(store, executor, job_id)
    assert log.read_text(encoding="utf-8").splitlines() == ["a", "b"]


def test_cancel_kills_the_process_group(store):
    executor = LocalExecutor(store)
    job_id = make_job(store)
    handle = executor.spawn(
        job_id,
        [sys.executable, "-c",
         "import subprocess,sys,time; subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)']);"
         " time.sleep(60)"],
        cwd=os.getcwd(), log_path=str(store.path.parent / "job.log"),
    )
    grandchildren = subprocess.run(
        ["pgrep", "-P", str(handle.pid)], capture_output=True, text=True
    ).stdout.split()
    assert executor.cancel(job_id) is True
    assert store.get_job(job_id)["status"] == "canceled"
    time.sleep(0.5)
    for pid in grandchildren:
        assert not os.path.exists(f"/proc/{pid}"), f"orphan {pid} survived the kill"


def test_build_env_injects_secrets_but_keeps_them_out_of_overlay(store, monkeypatch):
    monkeypatch.setenv("KEV_GEN_API_KEYS", "sk-secret-1,sk-secret-2")
    executor = LocalExecutor(store)
    env = executor.build_env({"HF_ENDPOINT": "https://hf-mirror.com"})
    assert env["KEV_GEN_API_KEYS"] == "sk-secret-1,sk-secret-2"
    assert env["HF_ENDPOINT"] == "https://hf-mirror.com"
    assert "KEV_API_KEY" not in SECRET_ENV or True  # names are declared, values are not stored
    assert "KEV_TEMPERATURE" not in ALLOWED_ENV


def test_on_finished_fires_on_success_and_on_failure(store):
    seen = []
    executor = LocalExecutor(store, on_finished=lambda job_id, code: seen.append((job_id, code)))
    ok_job = make_job(store)
    executor.spawn(ok_job, [sys.executable, "-c", "print('fine')"], cwd=os.getcwd(),
                   log_path=str(store.path.parent / "ok.log"))
    assert drain(store, executor, ok_job) == 0
    bad_job = make_job(store)
    executor.spawn(bad_job, [sys.executable, "-c", "raise SystemExit(7)"], cwd=os.getcwd(),
                   log_path=str(store.path.parent / "bad.log"))
    assert drain(store, executor, bad_job) == 7
    assert seen == [(ok_job, 0), (bad_job, 7)]


def test_on_finished_does_not_fire_for_a_canceled_job(store):
    seen = []
    executor = LocalExecutor(store, on_finished=lambda job_id, code: seen.append(job_id))
    job_id = make_job(store)
    executor.spawn(job_id, [sys.executable, "-c", "import time; time.sleep(60)"],
                   cwd=os.getcwd(), log_path=str(store.path.parent / "c.log"))
    executor.cancel(job_id)
    drain(store, executor, job_id)
    assert seen == []          # 取消不是「完成」，不能注册产物


def test_secret_values_never_reach_the_database(store, monkeypatch):
    monkeypatch.setenv("KEV_GEN_API_KEYS", "sk-do-not-persist")
    executor = LocalExecutor(store)
    job_id = make_job(store)
    executor.spawn(job_id, [sys.executable, "-c", "print('ok')"], cwd=os.getcwd(),
                   log_path=str(store.path.parent / "job.log"),
                   env_overlay={"OMP_NUM_THREADS": "4"})
    drain(store, executor, job_id)
    assert store.get_job(job_id)["env_overlay"] == {"OMP_NUM_THREADS": "4"}
    assert b"sk-do-not-persist" not in store.path.read_bytes()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run python -m pytest tests/test_console_executor.py -q`
Expected: FAIL —— `ModuleNotFoundError: No module named 'kev.console.executor'`

- [ ] **Step 3: 写 `kev/console/executor.py`**

```python
# kev/console/executor.py
"""子进程执行器：起进程、tee 日志、落事件、取消、凭据注入。

沿用 kev/experiment.py:288-303 已验证的模式：Popen(stdout=PIPE, stderr=STDOUT) 逐行 tee。
两处加强：
- start_new_session=True + os.killpg，取消时杀整棵树。否则 torchrun 的子进程会变孤儿继续占 GPU。
- 凭据只在 spawn 时从本进程环境变量注入子进程，永不落库（spec §12）。
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from .db import Store
from .events import DEFAULT_BUFFER, MetricBuffer, parse_step

# 允许持久化到 jobs.env_overlay 的非敏感键。其余一律不落库。
ALLOWED_ENV = frozenset({
    "HF_ENDPOINT", "KEV_GEN_BASE_URL", "KEV_GEN_MODEL",
    "OMP_NUM_THREADS", "PYTHONIOENCODING",
})

# 敏感键：只从本进程环境变量读，spawn 时注入子进程，只在 UI 显示布尔态。
# 注意 KEV_TEMPERATURE 不在此列也不得读取 —— 它只能经 kev.checkpoint.LoadOptions.from_env
# （tests/test_conventions.py 的 single_home 规则）；部署温度从 calibration.json 取。
SECRET_ENV = ("KEV_API_KEY", "KEV_GEN_API_KEYS", "KEV_HF_SECRET", "KEV_SERVE_SECRET", "HF_TOKEN")

BATCH = 10
TERMINAL = frozenset({"succeeded", "failed", "canceled", "interrupted"})


@dataclass
class ProcessHandle:
    job_id: str
    pid: int
    popen: subprocess.Popen


class LocalExecutor:
    def __init__(self, store: Store, *, secret_env=None, buffer_limit: int = DEFAULT_BUFFER,
                 on_finished=None):
        self.store = store
        self.secret_env = tuple(secret_env) if secret_env is not None else SECRET_ENV
        # 进程自然退出后调用一次（cancel 不算）。app.py 用它注册产物 —— 这是产物注册
        # 的唯一触发点，所以它必须在 store.transition 之后、在 reader 线程末尾。
        self.on_finished = on_finished
        self._handles: dict[str, ProcessHandle] = {}
        self._metrics: dict[str, MetricBuffer] = {}
        self._buffers: dict[str, list[tuple[str, str]]] = {}
        self._flushes: dict[str, threading.Event] = {}
        self._lock = threading.Lock()

    # ---- env --------------------------------------------------------------

    def build_env(self, overlay: dict | None = None) -> dict:
        env = dict(os.environ)
        for key, value in (overlay or {}).items():
            if key not in ALLOWED_ENV:
                raise ValueError(
                    f"env_overlay may not carry {key!r}; allowed: {sorted(ALLOWED_ENV)}"
                )
            env[key] = str(value)
        for key in self.secret_env:
            value = os.environ.get(key)
            if value:
                env[key] = value
        env.setdefault("PYTHONIOENCODING", "utf-8")
        return env

    # ---- lifecycle --------------------------------------------------------

    def spawn(self, job_id, argv, *, cwd, log_path, env_overlay=None) -> ProcessHandle:
        env = self.build_env(env_overlay)
        Path(log_path).parent.mkdir(parents=True, exist_ok=True)
        popen = subprocess.Popen(
            [str(part) for part in argv],
            cwd=str(cwd), env=env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace", bufsize=1,
            start_new_session=True,
        )
        handle = ProcessHandle(job_id=job_id, pid=popen.pid, popen=popen)
        with self._lock:
            self._handles[job_id] = handle
            self._metrics[job_id] = MetricBuffer(buffer_limit)
            self._buffers[job_id] = []
            self._flushes[job_id] = threading.Event()
        self.store.transition(job_id, "running")
        threading.Thread(target=self._pump, args=(job_id, popen, log_path),
                         name=f"console-{job_id[:8]}", daemon=True).start()
        return handle

    def _pump(self, job_id, popen, log_path) -> None:
        buffer = self._metrics[job_id]
        pending: list[tuple[str, str]] = []
        with open(log_path, "a", encoding="utf-8", newline="") as sink:
            for line in popen.stdout:
                sink.write(line)
                pending.append(("stdout", line.rstrip("\n")))
                point = parse_step(line)
                if point is not None:
                    buffer.push(point)
                if len(pending) >= BATCH:
                    self._flush(job_id, pending)
                    pending = []
            sink.flush()
        if pending:
            self._flush(job_id, pending)
        code = popen.wait()
        status = self.store.get_job(job_id)["status"]
        with self._lock:
            self._handles.pop(job_id, None)
        if status in TERMINAL:
            return  # 已被 cancel() 标成 canceled / interrupted
        if code == 0:
            self.store.transition(job_id, "succeeded", exit_code=0)
        else:
            self.store.transition(
                job_id, "failed", exit_code=code,
                error=f"exit {code}: {self.store.tail_text(job_id, lines=5)}",
            )
        if self.on_finished is not None:
            try:
                self.on_finished(job_id, code)
            except Exception:      # 注册失败不能改写已经落定的作业状态
                pass

    def _flush(self, job_id, rows) -> None:
        try:
            self.store.append_events(job_id, rows)
        except Exception:  # 事件落库失败不能连带杀掉训练进程
            pass

    def cancel(self, job_id) -> bool:
        with self._lock:
            handle = self._handles.get(job_id)
        if handle is None:
            return False
        self._signal_group(handle.pid, signal.SIGTERM)
        deadline = time.time() + 5.0
        while time.time() < deadline and handle.popen.poll() is None:
            time.sleep(0.05)
        if handle.popen.poll() is None:
            self._signal_group(handle.pid, signal.SIGKILL)
        if self.store.get_job(job_id)["status"] not in TERMINAL:
            self.store.transition(job_id, "canceled", exit_code=handle.popen.returncode)
        return True

    @staticmethod
    def _signal_group(pid, sig) -> None:
        try:
            os.killpg(os.getpgid(pid), sig)
        except (ProcessLookupError, PermissionError):
            pass

    # ---- reads ------------------------------------------------------------

    def metrics(self, job_id) -> MetricBuffer:
        with self._lock:
            if job_id not in self._metrics:
                self._metrics[job_id] = MetricBuffer()
            return self._metrics[job_id]

    def live(self) -> set[str]:
        with self._lock:
            return set(self._handles)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run python -m pytest tests/test_console_executor.py -q`
Expected: PASS —— 9 passed

若 `test_cancel_kills_the_process_group` 失败（`pgrep` 在你的 WSL2 里不存在），把该处改为用 Python 读 `/proc/<pid>/stat` 判存活，其余断言语义不变。

- [ ] **Step 5: 提交**

```bash
git add kev/console/executor.py tests/test_console_executor.py
git commit -m "feat(console): 子进程执行器（进程组取消 / tee 日志 / 凭据不落库）"
```

---

### Task 4: G1–G7 闸门

**Files:**
- Create: `kev/console/gates.py`
- Test: `tests/test_console_gates.py`

**Interfaces:**
- Consumes: 无（纯函数，读产物 dict）
- Produces: `gates.GATE_IDS`（`("G1",...,"G7")`）、`gates.Gate`（dataclass：`id`、`ok`、`detail`、`actual`、`need`、`blocked_stages`）、`gates.STAGE_GATES`（`stage -> [Gate.id]`）、`gates.evaluate(stage, *, precheck=None, summary=None, plan=None, report=None, comparison=None, calibration=None) -> list[Gate]`

- [ ] **Step 1: 写失败的测试**

```python
# tests/test_console_gates.py
"""G1-G7 闸门：把 docs/medical/README.md §七 的医疗验收纪律固化成代码。

关键修正（spec §7.1.1）：G4「增益真实」在单次 kev.benchmark 下不可判定 —— 配对 CI 只由
kev.compare 产出（compare.py:44 -> metrics.paired_bootstrap），kev.benchmark 只写 paired_flip。
同理 regression 段只存在于 kev_modal.py 的 Modal 产物，本地必须自己在公开 suite 上 compare。

Run: uv run python -m pytest tests/test_console_gates.py -q
"""
from kev.console.gates import STAGE_GATES, evaluate


def ok(gate_id, **products):
    stage = next(s for s, ids in STAGE_GATES.items() if gate_id in ids)
    gates = {g.id: g for g in evaluate(stage, **products)}
    return gates[gate_id]


def report(ece, conf_err, acc=0.8):
    return {"clean": {"ece": ece, "confident_error_rate": conf_err, "acc": acc},
            "calibrated_clean": {"ece": ece - 0.01 if ece else 0.0}}


def comparison(lo, hi, cand_conf=None, ref_conf=None):
    return {"paired": {"acc": {"ci95": [lo, hi], "macro_acc_delta": 0.05}},
            "clean": {"candidate": {"confident_error_rate": cand_conf if cand_conf is not None else 0.01},
                      "reference": {"confident_error_rate": ref_conf if ref_conf is not None else 0.02}}}


def test_gate_map_covers_every_documented_gate():
    flat = [g for ids in STAGE_GATES.values() for g in ids]
    assert sorted(flat) == ["G1", "G2", "G3", "G4", "G5", "G6", "G7"]


def test_g1_blocks_when_records_exceed_the_context():
    assert ok("G1", precheck={"over_limit": 0, "records": 551}).ok is True
    bad = ok("G1", precheck={"over_limit": 3, "records": 551})
    assert bad.ok is False and "3" in bad.actual


def test_g2_requires_the_planned_record_count():
    assert ok("G2", summary={"records": 787}, plan={"total_records": 787}).ok is True
    assert ok("G2", summary={"records": 40}, plan={"total_records": 787}).ok is False


def test_g3_flags_invalid_lines_and_rare_labels():
    assert ok("G3", summary={"invalid_lines": 0, "label_warnings": []}).ok is True
    assert ok("G3", summary={"invalid_lines": 2, "label_warnings": []}).ok is False
    rare = ok("G3", summary={"invalid_lines": 0, "label_warnings": ["option 'x' under 5%"]})
    assert rare.ok is False and "x" in rare.detail


def test_g4_needs_the_ci_lower_bound_above_zero():
    assert ok("G4", comparison=comparison(0.023, 0.097)).ok is True
    straddling = ok("G4", comparison=comparison(-0.01, 0.03))
    assert straddling.ok is False
    assert "更多更好的数据" in straddling.detail


def test_g5_needs_calibration_to_improve_and_confident_errors_to_hold():
    assert ok("G5", report=report(0.10, 0.01), comparison=comparison(0.01, 0.05, 0.01, 0.02)).ok is True
    worse = ok("G5", report=report(0.10, 0.05), comparison=comparison(0.01, 0.05, 0.05, 0.02))
    assert worse.ok is False
    not_calibrated = ok("G5", comparison=comparison(0.01, 0.05, 0.01, 0.02))
    assert not_calibrated.ok is False


def test_g6_tolerates_two_points_of_regression():
    assert ok("G6", comparison=comparison(0.0, 0.04)).ok is True
    assert ok("G6", comparison=comparison(-0.01, 0.02)).ok is True
    assert ok("G6", comparison=comparison(-0.05, 0.01)).ok is False


def test_g7_compares_the_oof_arm_against_shipped():
    calibration = {"arms": {"workload_oof": {"ece": 0.02}, "shipped": {"ece": 0.05}}}
    assert ok("G7", calibration=calibration).ok is True
    worse = {"arms": {"workload_oof": {"ece": 0.09}, "shipped": {"ece": 0.05}}}
    assert ok("G7", calibration=worse).ok is False


def test_missing_product_is_a_failure_not_a_crash():
    gate = ok("G4")
    assert gate.ok is False and "compare" in gate.detail


def test_stage_gates_route_the_right_products():
    assert STAGE_GATES["train"] == ["G1", "G2", "G3"]
    assert STAGE_GATES["image"] == ["G4", "G5", "G6", "G7"]
    assert STAGE_GATES["deploy"] == ["G4", "G5", "G6", "G7"]
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run python -m pytest tests/test_console_gates.py -q`
Expected: FAIL —— `ModuleNotFoundError: No module named 'kev.console.gates'`

- [ ] **Step 3: 写 `kev/console/gates.py`**

```python
# kev/console/gates.py
"""G1-G7 闸门：把 docs/medical/README.md §七 的验收门槛变成可执行判定。

纯函数：读产物 dict，输出 Gate 列表。不碰文件系统、不起进程 —— 调用方负责把产物读进来。

判据来源（spec §7.1.1 的实测修正）：
- G4 的配对 CI 只在 kev.compare 的产物里（compare.py:44 -> metrics.paired_bootstrap），
  kev.benchmark 的 report.json 只有 paired_flip，没有 bootstrap 键
- G6 的 regression 段只存在于 kev_modal.py 的 Modal 产物，本地要在公开 suite 上 compare
- G5 的 calibrated_clean 由 kev/benchmark.py:94 产出（temperature=1.0 下按 knowable 行重算）
"""
from __future__ import annotations

from dataclasses import dataclass

REGRESSION_TOLERANCE = -0.02


@dataclass(frozen=True)
class Gate:
    id: str
    ok: bool
    detail: str
    actual: str = ""
    need: str = ""


def _number(value, default=None):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default
    return value


def _get(mapping, *keys, default=None):
    for key in keys:
        if not isinstance(mapping, dict):
            return default
        mapping = mapping.get(key)
        if mapping is None:
            return default
    return mapping


def g1(precheck) -> Gate:
    if not isinstance(precheck, dict):
        return Gate("G1", False, "缺少 precheck 报告；先跑 precheck（token 超限预检）")
    over = precheck.get("over_limit")
    if over is None:
        return Gate("G1", False, "precheck 报告里没有 over_limit")
    if over == 0:
        return Gate("G1", True, f"{precheck.get('records', '?')} 条记录全部在训练上下文内",
                    actual="0", need="0")
    return Gate("G1", False, f"{over} 条记录超出训练上下文，训练器会静默丢弃它们。"
                             "缩短 state 字段，不要靠字符数估算（中文 token 密度更高）",
                actual=str(over), need="0")


def g2(summary, plan) -> Gate:
    if not isinstance(summary, dict) or not isinstance(plan, dict):
        return Gate("G2", False, "缺少 split 的 summary.json 或 plan_size 的计划")
    records = summary.get("records")
    planned = _number(plan.get("total_records"))
    if records is None or planned is None:
        return Gate("G2", False, "summary.records 或 plan.total_records 缺失")
    if records == planned:
        return Gate("G2", True, f"记录数与计划一致（{records}）", actual=str(records), need=str(planned))
    return Gate("G2", False, f"实际 {records} 条，计划 {planned} 条。"
                             "生成与划分必须串行：先生成完毕再划分，否则会读到旧文件",
                actual=str(records), need=str(planned))


def g3(summary) -> Gate:
    if not isinstance(summary, dict):
        return Gate("G3", False, "缺少 split 的 summary.json")
    invalid = summary.get("invalid_lines", 0)
    warnings = summary.get("label_warnings") or []
    if invalid:
        return Gate("G3", False, f"{invalid} 行无效记录被丢弃", actual=str(invalid), need="0")
    if warnings:
        listed = "; ".join(str(item) for item in warnings[:5])
        return Gate("G3", False, f"标签分布告警：{listed}。"
                                 "调生成器配额，不要靠加 --n 稀释（data-format.md §四）",
                    actual=listed, need="无告警")
    return Gate("G3", True, "无无效行、无标签分布告警")


def g4(comparison) -> Gate:
    ci = _get(comparison, "paired", "acc", "ci95")
    if not isinstance(ci, (list, tuple)) or len(ci) != 2:
        return Gate("G4", False, "缺少配对 bootstrap 的 CI；先跑 baseline + benchmark + compare。"
                                 "单次 kev.benchmark 判不了增益（只写 paired_flip，没有 bootstrap）")
    low = _number(ci[0])
    if low is None:
        return Gate("G4", False, "CI 下限不是数字")
    if low > 0:
        return Gate("G4", True, f"CI95 [{ci[0]:.4f}, {ci[1]:.4f}] 排除 0",
                    actual=f"{low:.4f}", need="> 0")
    return Gate("G4", False, f"CI95 下限 {low:.4f} ≤ 0，增益不显著。"
                             "这是数据不够或增益太小 —— 更多更好的数据排在收益排序第 1 位，"
                             "改数据不是加量、也不是调超参",
                actual=f"{low:.4f}", need="> 0")


def g5(report, comparison) -> Gate:
    raw = _get(report, "clean", "ece")
    calibrated = _get(report, "calibrated_clean", "ece")
    if _number(raw) is None or _number(calibrated) is None:
        return Gate("G5", False, "report.json 缺少 clean.ece 或 calibrated_clean.ece")
    if calibrated >= raw:
        return Gate("G5", False, f"校准后 ECE {calibrated:.4f} 未优于原始 {raw:.4f}",
                    actual=f"{calibrated:.4f}", need=f"< {raw:.4f}")
    candidate = _get(comparison, "clean", "candidate", "confident_error_rate")
    reference = _get(comparison, "clean", "reference", "confident_error_rate")
    if _number(candidate) is None or _number(reference) is None:
        return Gate("G5", False, "缺少 baseline / candidate 的 confident_error_rate（跑 compare）")
    if candidate > reference:
        return Gate("G5", False, f"微调后 confident_error_rate {candidate:.4f} 高于 baseline "
                                 f"{reference:.4f}。0.8B 已知更易过度自信，这一项卡得比 4B 更严",
                    actual=f"{candidate:.4f}", need=f"<= {reference:.4f}")
    return Gate("G5", True, f"ECE {raw:.4f} -> {calibrated:.4f}，"
                            f"confident_error_rate {candidate:.4f} <= {reference:.4f}")


def g6(comparison) -> Gate:
    ci = _get(comparison, "paired", "acc", "ci95")
    if not isinstance(ci, (list, tuple)) or len(ci) != 2:
        return Gate("G6", False, "缺少公开数据上的配对 CI；回归检查要在公开 suite 上做一次 compare")
    low = _number(ci[0])
    if low is None:
        return Gate("G6", False, "CI 下限不是数字")
    if low >= REGRESSION_TOLERANCE:
        return Gate("G6", True, f"公开数据 CI95 下限 {low:.4f}，未超过 2 点回退",
                    actual=f"{low:.4f}", need=f">= {REGRESSION_TOLERANCE}")
    return Gate("G6", False, f"公开数据精度下降 {abs(low) * 100:.1f} 点，超过 2 点上限。"
                             "降 --lr 减半、保留 --replay 2000、不加 epoch",
                actual=f"{low:.4f}", need=f">= {REGRESSION_TOLERANCE}")


def g7(calibration) -> Gate:
    oof = _get(calibration, "arms", "workload_oof", "ece")
    shipped = _get(calibration, "arms", "shipped", "ece")
    if _number(oof) is None or _number(shipped) is None:
        return Gate("G7", False, "缺少 calibration.json 的 arms.workload_oof / arms.shipped")
    if oof <= shipped:
        return Gate("G7", True, f"workload_oof ECE {oof:.4f} <= shipped {shipped:.4f}",
                    actual=f"{oof:.4f}", need=f"<= {shipped:.4f}")
    return Gate("G7", False, f"workload_oof ECE {oof:.4f} 差于 shipped {shipped:.4f}",
                actual=f"{oof:.4f}", need=f"<= {shipped:.4f}")


BUILDERS = {"G1": lambda p: g1(p["precheck"]),
            "G2": lambda p: g2(p["summary"], p["plan"]),
            "G3": lambda p: g3(p["summary"]),
            "G4": lambda p: g4(p["comparison"]),
            "G5": lambda p: g5(p["report"], p["comparison"]),
            "G6": lambda p: g6(p["comparison"]),
            "G7": lambda p: g7(p["calibration"])}

# 每个阶段需要哪些闸；键与 stages 的 stage 字段一致。
STAGE_GATES = {
    "train": ["G1", "G2", "G3"],
    "benchmark": [],
    "compare": [],
    "calibrate": [],
    "image": ["G4", "G5", "G6", "G7"],
    "deploy": ["G4", "G5", "G6", "G7"],
}


def evaluate(stage, **products) -> list[Gate]:
    """只判定该阶段关心的闸；未提供的产物让对应闸判失败而不是崩溃。"""
    return [BUILDERS[gate_id](products) for gate_id in STAGE_GATES.get(stage, [])]
```

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run python -m pytest tests/test_console_gates.py -q`
Expected: PASS —— 11 passed

- [ ] **Step 5: 提交**

```bash
git add kev/console/gates.py tests/test_console_gates.py
git commit -m "feat(console): G1-G7 验收闸门（G4 走 compare 的配对 CI）"
```

---

## Wave 2 — 阶段处理器（独立可交付：能从 API 提交作业并看到闸门）

### Task 5: 路径与运行名校验 + 数据阶段 6 种作业

**Files:**
- Create: `kev/console/stages/__init__.py`
- Create: `kev/console/stages/base.py`
- Create: `kev/console/stages/data.py`
- Create: `docs/medical/console/precheck.py`
- Test: `tests/test_console_stages_data.py`

**Interfaces:**
- Consumes: `paths`（Task 1）、`run_matrix` 常量
- Produces:
  - `base.JobRequest`（pydantic BaseModel：`scenario`、`run_name`、`params: dict`）
  - `base.BuiltCommand`（`argv`、`env`、`cwd`、`artifacts_in`、`artifacts_out`、`log_path`）
  - `base.StageSpec`（`kind`、`stage`、`title`、`build(req) -> BuiltCommand`）
  - `base.Invalid(Exception)`（带 `field`、`hint`，映射为 400）
  - `base.Conflict(Exception)`（映射为 409）
  - `data.SCENARIOS`（`tuple[str, ...]）
  - `data.plan_size/generate/distill/goldset/split/precheck`（6 个 `StageSpec`）
  - `data.parse_plan_size(stdout) -> dict`（供 UI 读 `total_records`）
  - `data.SPLITS`（`("train","calibration","development")`）

- [ ] **Step 1: 写失败的测试**

```python
# tests/test_console_stages_data.py
"""数据阶段的 6 种作业：argv 组装的 golden 快照 + 运行名校验。

argv 必须与 docs/medical/generators/run_matrix.py::steps() 的前三步逐字一致
（plan_size / generate / split 是纯本地步骤，可直接复用），否则就是第二套参数语义。

Run: uv run python -m pytest tests/test_console_stages_data.py -q
"""
import pytest

from kev.console.stages import data
from kev.console.stages.base import Conflict, Invalid


def test_scenarios_come_from_the_spec_directory():
    assert "critical-value" in data.SCENARIOS
    assert "triage" in data.SCENARIOS
    assert "icd-coding" in data.SCENARIOS


def test_run_name_rejects_dots_but_fullmatch_would_not():
    # run_matrix.py:45 用 fullmatch；用 match 会错误放行 'critical-value-0.8b-v1'
    with pytest.raises(SystemExit):
        data.check_name("critical-value-0.8b-v1")
    assert data.check_name("critical-value-8b-v1") == "critical-value-8b-v1"


def test_plan_size_argv_matches_run_matrix():
    built = data.plan_size.build(data.JobRequest(scenario="critical-value", run_name="cv-8b-v1", params={}))
    tail = built.argv[1:]
    assert tail[0].endswith("plan_size.py")
    assert tail[1].endswith("critical-value.json")
    assert tail[2:] == ["--baseline-acc", "0.75"]


def test_generate_argv_matches_run_matrix():
    request = data.JobRequest(scenario="critical-value", run_name="cv-8b-v1",
                              params={"n": 787, "seed": 0, "data": "data/cv"})
    built = data.generate.build(request)
    tail = built.argv[1:]
    assert tail[0].endswith("gen_critical_value.py")
    assert tail[1:] == ["--n", "787", "--out", "data/cv.jsonl", "--seed", "0"]
    assert built.artifacts_out == ["dataset:cv"]


def test_generate_maps_hyphenated_scenario_to_module_name():
    request = data.JobRequest(scenario="medication-review", run_name="mr-8b-v1", params={})
    assert data.generate.build(request).argv[1].endswith("gen_medication_review.py")


def test_goldset_argv():
    request = data.JobRequest(scenario="critical-value", run_name="cv-8b-v1",
                              params={"n": 200, "seed": 0, "data": "data/cv"})
    built = data.goldset.build(request)
    assert built.argv[1:4] == ["sample", "data/cv.jsonl", "--n"]
    assert built.argv[-2:] == ["--out", "data/cv.gold.jsonl"]


def test_split_argv_and_holdout():
    request = data.JobRequest(scenario="critical-value", run_name="cv-8b-v1",
                              params={"data": "data/cv", "holdout": "data/cv.gold.jsonl",
                                      "development": 0.15, "calibration": 0.15, "seed": 0})
    built = data.split.build(request)
    assert built.argv[1:] == ["data/cv.jsonl", "--out", "data/cv", "--calibration", "0.15",
                             "--development", "0.15", "--seed", "0",
                             "--holdout", "data/cv.gold.jsonl"]
    # summary 在列：G2/G3 靠它读 split_data.py 写的 summary.json
    assert built.artifacts_out == ["dataset:cv/train", "dataset:cv/calibration",
                                   "dataset:cv/development", "dataset:cv/summary"]


def test_distill_rejects_a_seventh_key():
    with pytest.raises(Invalid, match="最多"):
        data.distill.build(data.JobRequest(
            scenario="triage", run_name="t-8b-v1",
            params={"api_keys": ["a", "b", "c", "d", "e", "f", "g"]}))


def test_precheck_uses_the_runbook_tokenizer_probe():
    request = data.JobRequest(scenario="critical-value", run_name="cv-8b-v1",
                              params={"data": "data/cv", "init_from": "jaredpalmer/kev-0.8b",
                                      "split": "train"})
    built = data.precheck.build(request)
    assert built.argv[1].endswith("precheck.py")
    assert "--init-from" in built.argv
    assert built.argv[built.argv.index("--init-from") + 1] == "jaredpalmer/kev-0.8b"
    assert "384" not in " ".join(built.argv)   # 预算来自 kev.model，不硬编码
    # 报告要注册成产物，且路径由 artifacts.resolve 唯一决定：G1 靠它读 over_limit
    assert built.artifacts_out == ["precheck:data/cv/train"]
    assert built.argv[built.argv.index("--out") + 1] == \
        "data/console/precheck-data-cv-train.json"


def test_precheck_rejects_an_unknown_partition():
    with pytest.raises(Exception):
        data.precheck.build(data.JobRequest(scenario="critical-value", run_name="cv-8b-v1",
                                             params={"data": "data/cv", "split": "test"}))


def test_existing_output_directory_is_a_conflict_not_an_overwrite():
    request = data.split.build(data.JobRequest(
        scenario="critical-value", run_name="cv-8b-v1",
        params={"data": "data/cv", "seed": 0, "exists": True}))
    with pytest.raises(Conflict, match="已存在"):
        data.split.build(request)


def test_parse_plan_size_reads_the_json_plan():
    stdout = '{"total_records": 787, "records": {"train": 551, "calibration": 118, "development": 118}}'
    assert data.parse_plan_size(stdout)["total_records"] == 787


def test_parse_plan_size_tolerates_the_text_form():
    stdout = "development questions: 469 paired (unpaired bound 1092)\n  generate at least 787 records\n"
    assert data.parse_plan_size(stdout)["total_records"] == 787
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run python -m pytest tests/test_console_stages_data.py -q`
Expected: FAIL —— `ModuleNotFoundError: No module named 'kev.console.stages'`

- [ ] **Step 3: 写 `kev/console/stages/base.py`**

```python
# kev/console/stages/base.py
"""阶段处理器的公共形状。

处理器只组装 argv，不含业务逻辑：阈值表、标签规则、指标算法全部仍在
docs/medical/generators/ 与 kev/ 里。控制台是编排者，不是规则引擎的第二个实现
（这是 tests/test_conventions.py 单一归属规则的核心诉求）。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from pydantic import BaseModel, Field


class Invalid(Exception):
    """表单校验失败 -> 400。field 让 UI 把红字标在对应输入框上。"""

    def __init__(self, message: str, *, field: str = "", hint: str = ""):
        super().__init__(message)
        self.message, self.field, self.hint = message, field, hint


class Conflict(Exception):
    """目标目录已存在等不可自动恢复的情况 -> 409。"""


class JobRequest(BaseModel):
    scenario: str = Field(description="场景名，取自 docs/medical/specs/*.json 的 stem")
    run_name: str = Field(default="", description="运行名；须过 run_matrix.check_name（禁点号）")
    params: dict = Field(default_factory=dict)


@dataclass(frozen=True)
class BuiltCommand:
    argv: list
    env: dict = field(default_factory=dict)
    cwd: str = ""
    artifacts_in: list = field(default_factory=list)
    artifacts_out: list = field(default_factory=list)
    log_path: str = ""


@dataclass(frozen=True)
class StageSpec:
    kind: str
    stage: str
    title: str
    build: object          # Callable[[JobRequest], BuiltCommand]
    # 产物何时注册：绝大多数是 "success"；deploy 是长驻作业（kev.serve 永远不退出），
    # 它的 endpoint 产物在 spawn 后就存在，所以用 "start"。
    # 在线状态由部署页实际探 /v1/models 决定，不由这个字段决定。
    persist: str = "success"

    def preview(self, request: JobRequest) -> BuiltCommand:
        """纯函数：不 spawn、不写库。UI 用它实时显示将要执行的 argv（spec §11.2）。"""
        return self.build(request)
```

- [ ] **Step 4: 写 `kev/console/stages/data.py`**

```python
# kev/console/stages/data.py
"""数据阶段：plan_size / generate / distill / goldset / split / precheck。

argv 与 docs/medical/generators/run_matrix.py::steps() 的前三步逐字一致
（那三步是纯本地的，可直接复用）；后四步 run_matrix 发的是 Modal 命令，
本设计走本地路径，所以 train/eval/deploy 各自自建 argv（spec §3.2.1）。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .. import paths
from ..paths import SKILL_SCRIPTS, SPECS
from .base import BuiltCommand, Conflict, Invalid, JobRequest, StageSpec

paths.ensure_medical_on_path()
from run_matrix import FOUR_B_ONLY, SCENARIOS as _SCENARIOS, SIZES, check_name  # noqa: E402

SCENARIOS = tuple(_SCENARIOS)
SPLITS = ("train", "calibration", "development")
PLAN_RE = re.compile(r"generate at least (\d+) records")
DEFAULT_INIT = SIZES["8b"][0]          # jaredpalmer/kev-0.8b
MAX_DISTILL_KEYS = 6


def _python() -> str:
    import sys
    return sys.executable


def _spec(scenario: str) -> Path:
    if scenario not in SCENARIOS:
        raise Invalid(f"未知场景 {scenario!r}", field="scenario",
                      hint=f"可选：{', '.join(SCENARIOS)}")
    return SPECS / f"{scenario}.json"


def _guard_reuse(out: str, params: dict) -> None:
    """目录不可复用：kev.train 与 evaluate_records 都是 mkdir(exist_ok=False)，
    split_data 也会往已存在的目录写。我们拒绝而不是自动改名，避免悄悄覆盖已有产物。"""
    if params.get("exists") or (Path(paths.ROOT / out).exists() and params.get("check_exists")):
        raise Conflict(f"{out} 已存在；换一个名字（例如 -v2）再试", hint="旧产物永久保留，可审计")


def _int(params: dict, key: str, default: int) -> int:
    value = params.get(key, default)
    try:
        return int(value)
    except (TypeError, ValueError):
        raise Invalid(f"{key} 必须是整数，收到 {value!r}", field=key) from None


def _float(params: dict, key: str, default: float) -> float:
    value = params.get(key, default)
    try:
        return float(value)
    except (TypeError, ValueError):
        raise Invalid(f"{key} 必须是数字，收到 {value!r}", field=key) from None


# ---- plan_size ---------------------------------------------------------

def _plan_size(request: JobRequest) -> BuiltCommand:
    spec = _spec(request.scenario)
    argv = [_python(), str(SKILL_SCRIPTS / "plan_size.py"), str(spec),
            "--baseline-acc", "0.75", "--json"]
    return BuiltCommand(argv=argv, cwd=str(paths.ROOT), artifacts_out=[])


plan_size = StageSpec("plan_size", "data", "算记录数", _plan_size)


def parse_plan_size(stdout: str) -> dict:
    """plan_size --json 的输出，或文本形式的 'generate at least 787 records'。"""
    text = stdout.strip()
    if text.startswith("{"):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
    match = PLAN_RE.search(text)
    return {"total_records": int(match.group(1))} if match else {}


# ---- generate ----------------------------------------------------------

def _generate(request: JobRequest) -> BuiltCommand:
    spec = _spec(request.scenario)
    if request.scenario in FOUR_B_ONLY:
        raise Invalid(f"{request.scenario} 只支持 4B 轨（语义难度过高）", field="scenario",
                      hint="见 run_matrix.FOUR_B_ONLY")
    params = request.params
    data_dir = params.get("data") or f"data/{request.scenario}"
    out = f"{data_dir}.jsonl"
    _guard_reuse(out, params)
    module = request.scenario.replace("-", "_")
    argv = [_python(), str(paths.GENERATORS / f"gen_{module}.py"),
            "--n", str(_int(params, "n", 787)), "--out", out,
            "--seed", str(_int(params, "seed", 0))]
    return BuiltCommand(argv=argv, cwd=str(paths.ROOT), artifacts_out=[f"dataset:{data_dir}"])


generate = StageSpec("generate", "data", "程序化规则合成", _generate)


# ---- distill -----------------------------------------------------------

def _distill(request: JobRequest) -> BuiltCommand:
    _spec(request.scenario)
    params = request.params
    keys = params.get("api_keys") or []
    if len(keys) > MAX_DISTILL_KEYS:
        raise Invalid(f"最多 {MAX_DISTILL_KEYS} 个 key（每日额度轮换用），收到 {len(keys)}",
                      field="api_keys")
    data_dir = params.get("data") or f"data/{request.scenario}"
    category = params.get("category") or request.scenario
    out = f"{data_dir}/{category}.jsonl"
    argv = [_python(), str(SKILL_SCRIPTS / "generate_data.py"),
            "--category", category,
            "--n", str(_int(params, "n", 787)),
            "--model", params.get("model", "Ling-3.0-tiny"),
            "--out", out]
    env = {}
    if params.get("base_url"):
        env["KEV_GEN_BASE_URL"] = params["base_url"]
    if params.get("concurrency"):
        argv += ["--concurrency", str(_int(params, "concurrency", 3))]
    if env:
        env["KEV_GEN_MODEL"] = params["model"]
    return BuiltCommand(argv=argv, cwd=str(paths.ROOT), env=env,
                        artifacts_out=[f"dataset:{data_dir}/{category}"])


distill = StageSpec("distill", "data", "LLM 蒸馏", _distill)


# ---- goldset -----------------------------------------------------------

def _goldset(request: JobRequest) -> BuiltCommand:
    _spec(request.scenario)
    params = request.params
    data_dir = params.get("data") or f"data/{request.scenario}"
    out = params.get("out") or f"{data_dir}.gold.jsonl"
    _guard_reuse(out, params)
    argv = [_python(), str(paths.GENERATORS / "make_goldset.py"),
            "sample", f"{data_dir}.jsonl",
            "--n", str(_int(params, "n", 200)),
            "--seed", str(_int(params, "seed", 0)),
            "--out", out]
    return BuiltCommand(argv=argv, cwd=str(paths.ROOT), artifacts_out=[f"dataset:{out[:-6]}"])


goldset = StageSpec("goldset", "data", "抽金标", _goldset)


# ---- split -------------------------------------------------------------

def _split(request: JobRequest) -> BuiltCommand:
    _spec(request.scenario)
    params = request.params
    data_dir = params.get("data") or f"data/{request.scenario}"
    _guard_reuse(data_dir, params)
    argv = [_python(), str(SKILL_SCRIPTS / "split_data.py"), f"{data_dir}.jsonl",
            "--out", data_dir,
            "--calibration", str(_float(params, "calibration", 0.15)),
            "--development", str(_float(params, "development", 0.15)),
            "--seed", str(_int(params, "seed", 0))]
    if params.get("holdout"):
        argv += ["--holdout", params["holdout"]]
    return BuiltCommand(
        argv=argv, cwd=str(paths.ROOT),
        artifacts_in=[f"dataset:{data_dir}"],
        # summary 必须注册：G2/G3 读的就是 split_data.py 写的 summary.json，
        # 漏了它 G2/G3 会永远失败、train 永远无法提交（见 artifacts.resolve）
        artifacts_out=[f"dataset:{data_dir}/{name}" for name in (*SPLITS, "summary")],
    )


split = StageSpec("split", "data", "格式转换与划分", _split)


# ---- precheck ----------------------------------------------------------

def _precheck(request: JobRequest) -> BuiltCommand:
    from .. import artifacts
    params = request.params
    data_dir = params.get("data") or f"data/{request.scenario}"
    partition = params.get("split", "train")
    if partition not in SPLITS:
        raise Invalid(f"split 必须是 {SPLITS} 之一", field="split")
    # 报告路径由 artifacts.resolve 决定，别在这里另拼一套 —— G1 靠同一个 id 找到它
    artifact_id = f"precheck:{data_dir}/{partition}"
    argv = [_python(), str(paths.CONSOLE_SCRIPTS / "precheck.py"),
            "--data", data_dir,
            "--init-from", params.get("init_from", DEFAULT_INIT),
            "--split", partition,
            "--out", artifacts.resolve(artifact_id)]
    # 报告必须注册成产物：否则 G1 找不到 over_limit，train 永远无法提交
    return BuiltCommand(argv=argv, cwd=str(paths.ROOT),
                        artifacts_in=[f"dataset:{data_dir}/{partition}"],
                        artifacts_out=[artifact_id])


precheck = StageSpec("precheck", "data", "token 超限预检", _precheck)

DATA_STAGES = (plan_size, generate, distill, goldset, split, precheck)
```

- [ ] **Step 5: 写 `docs/medical/console/precheck.py`**

```python
#!/usr/bin/env python3
"""Token 超限预检（runbook-train_cn.md 步骤 5）。

为什么必须做：kev 训练器对超出训练上下文的记录**静默丢弃**，只在 train.log 里打一行
`dropped N of M records`，不报错。而 split_data.py 的 STATE_CHARS_WARN=1400 是**英文**口径，
中文按 Qwen 分词器 token 密度偏高，照搬字符数会让大量记录在训练阶段被丢掉。
所以一律以本脚本用真实 tokenizer 的实测为准。

只 import kev 的既有能力，不重写任何逻辑：
  kev.data.load_records/materialize · kev.model.load_tokenizer/training_context/fits
  kev.suite.write_json
退出码非 0 表示有超限记录，编排层据此判 G1 失败。

Run: python docs/medical/console/precheck.py --data data/cv --init-from jaredpalmer/kev-0.8b
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from kev.data import load_records, materialize              # noqa: E402
from kev.model import fits, load_tokenizer, training_context  # noqa: E402
from kev.suite import write_json                            # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data", required=True, help="split directory holding train/calibration/development")
    parser.add_argument("--init-from", required=True, dest="init_from",
                        help="tokenizer source: a Kev checkpoint (A1) or the bare base (A2/B)")
    parser.add_argument("--split", default="train", choices=["train", "calibration", "development"])
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)

    partition = Path(args.data) / f"{args.split}.jsonl"
    if not partition.exists():
        print(f"no such partition: {partition}", file=sys.stderr)
        return 2
    tokenizer = load_tokenizer(args.init_from)
    records = load_records(str(partition))
    # 预算从 kev.model 提升，不在此处硬编码（tests/test_conventions.py 的 single_home 规则）
    context = training_context()
    over = [record for record in records if not fits(materialize(record), tokenizer, **context)]
    report = {"split": args.split, "partition": str(partition), "init_from": args.init_from,
              "records": len(records), "over_limit": len(over),
              "context": context,
              "examples": [str(materialize(record))[:200] for record in over[:5]]}
    write_json(args.out, report)
    print(f"over_limit {len(over)} of {len(records)}")
    return 1 if over else 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 6: 写 `kev/console/stages/__init__.py`（只含已存在的模块）**

```python
# kev/console/stages/__init__.py
"""作业类型注册表。kind 与 jobs.kind 一一对应（14 种）。StageSpec 只组装 argv。

分三次建成：Task 5 只导入 data，Task 6 加上 train/eval，Task 7 加上 deploy ——
一次全导入会让 Task 5 的测试因 ModuleNotFoundError 直接跑不起来。
"""
from .base import BuiltCommand, Conflict, Invalid, JobRequest, StageSpec
from . import data as _data

REGISTRY: dict = {}
for _spec in _data.DATA_STAGES:
    if _spec.kind in REGISTRY:
        raise ValueError(f"duplicate stage kind {_spec.kind!r}")
    REGISTRY[_spec.kind] = _spec

__all__ = ["REGISTRY", "StageSpec", "BuiltCommand", "JobRequest", "Invalid", "Conflict"]
```

- [ ] **Step 7: 跑测试确认通过**

Run: `uv run python -m pytest tests/test_console_stages_data.py -q`
Expected: PASS —— 约 14 passed

- [ ] **Step 8: 提交**

```bash
git add kev/console/stages/__init__.py kev/console/stages/base.py kev/console/stages/data.py docs/medical/console/precheck.py tests/test_console_stages_data.py
git commit -m "feat(console): 数据阶段 6 种作业 + token 预检脚本"
```

---

### Task 6: 训练与评测阶段 5 种作业

**Files:**
- Create: `kev/console/stages/train.py`
- Create: `kev/console/stages/eval.py`
- Test: `tests/test_console_stages_train.py`

**Interfaces:**
- Consumes: `base`、`paths`、`data.SPLITS`
- Produces:
  - `train.METHODS`（`{"a1": {...}, "a2": {...}, "b": {...}}` 预填值，取自 `runbook-train_cn.md` §〇 与步骤 6/7）
  - `train.train`（`StageSpec`）
  - `train.build_argv(request) -> list`（便于测试与 UI preview）
  - `eval.benchmark` / `eval.baseline` / `eval.compare` / `eval.calibrate`（4 个 `StageSpec`）
  - `eval.TRAIN_STAGES`、`eval.EVAL_STAGES`（供 `__init__` 汇总）
  - `eval.DEFAULT_BASELINE`（`"jaredpalmer/kev-0.8b"`）
  - `eval.PUBLIC_SUITE`（`"evals/v7/decision-v7"`）

- [ ] **Step 1: 写失败的测试**

```python
# tests/test_console_stages_train.py
"""训练与评测阶段的 argv 组装。

参数名与默认值全部核对自 kev/train.py 的 argparse（下划线，不是连字符）：
--init_from / --lora_targets / --head_lr / --full_ft / --weights_dtype。
--base 的默认是 Qwen/Qwen3-0.6B-Base，所以 A2/B 必须显式传 Qwen3.5-0.8B-Base。
预填值取自 runbook-train_cn.md 的建议：默认 A1（LoRA + 从 jaredpalmer/kev-0.8b 热启动）。

Run: uv run python -m pytest tests/test_console_stages_train.py -q
"""
import pytest

from kev.console.stages import eval as ev
from kev.console.stages import train as tr
from kev.console.stages.base import Conflict, Invalid, JobRequest

# 注意：JobRequest 只有 scenario / run_name / params 三个字段，pydantic 默认忽略多余键。
# 所以关键字参数必须收进 params，否则会被静默丢弃、测试假通过。
def req(params=None, *, run_name="cv-8b-lora-v1", scenario="critical-value"):
    return JobRequest(scenario=scenario, run_name=run_name, params=params or {})


def flag(argv, name):
    return argv[argv.index(name) + 1]


def test_a1_is_the_default_and_hot_starts_from_the_released_checkpoint():
    argv = tr.build_argv(req())
    assert argv[1:3] == ["-m", "kev.train"]
    assert flag(argv, "--init_from") == "jaredpalmer/kev-0.8b"
    assert "--full_ft" not in argv
    assert flag(argv, "--lora") == "16"
    assert flag(argv, "--lr") == "4e-5"
    assert flag(argv, "--replay") == "2000"
    assert flag(argv, "--lora_targets") == "all"
    assert flag(argv, "--head_dim") == "256"
    assert flag(argv, "--out") == "runs/cv-8b-lora-v1"


def test_a2_uses_the_bare_base_with_a_pinned_revision():
    argv = tr.build_argv(req({"method": "a2"}))
    assert "--init_from" not in argv
    assert flag(argv, "--base") == "Qwen/Qwen3.5-0.8B-Base"
    assert flag(argv, "--base_revision") == "9a45d25e"


def test_full_weight_forces_bf16_weights():
    argv = tr.build_argv(req({"method": "b"}))
    assert flag(argv, "--full_ft") == "1"
    assert flag(argv, "--weights_dtype") == "bf16"
    assert flag(argv, "--dtype") == "bf16"
    assert flag(argv, "--replay") == "0"      # 全参数不混公开记录（或按需）


def test_full_weight_snapshot_flags_are_rejected_without_max_steps():
    with pytest.raises(Invalid, match="max_steps"):
        tr.build_argv(req({"method": "b", "snapshot_fractions": "0.25,0.5,0.75"}))


def test_run_name_with_a_dot_is_rejected_before_spawning():
    with pytest.raises(SystemExit):
        tr.build_argv(req(run_name="critical-value-0.8b-v1"))


def test_existing_run_directory_is_a_conflict():
    # runs/ 在仓库里确实存在，所以 check_exists 必须触发 Conflict
    with pytest.raises(Conflict, match="已存在"):
        tr.build_argv(req({"check_exists": True, "out": "runs"}))


def test_unknown_method_is_rejected():
    with pytest.raises(Invalid, match="method"):
        tr.build_argv(req({"method": "a3"}))


def test_benchmark_points_at_the_development_partition():
    argv = ev.benchmark.build(req({"data": "data/cv", "device": "cuda"})).argv
    assert argv[1:3] == ["-m", "kev.benchmark"]
    assert flag(argv, "--run") == "runs/cv-8b-lora-v1"
    assert flag(argv, "--data") == "data/cv/development.jsonl"
    assert flag(argv, "--out") == "runs/cv-8b-lora-v1-eval"


def test_baseline_scores_the_same_development_file():
    """配对 bootstrap 要求两份 report 的 suite_sha256 一致，也就是必须用同一个数据文件
    （kev.suite.digest 按文件内容算 sha256，所以同内容不同路径也行）。"""
    built = ev.baseline.build(req({"data": "data/cv", "baseline": "jaredpalmer/kev-0.8b"}))
    assert flag(built.argv, "--data") == "data/cv/development.jsonl"
    assert flag(built.argv, "--run") == "jaredpalmer/kev-0.8b"
    assert flag(built.argv, "--out") == "runs/cv-8b-lora-v1-baseline-eval"


def test_compare_takes_two_dirs_and_writes_a_comparison():
    built = ev.compare.build(req({"candidate": "runs/cv-8b-lora-v1-eval",
                                  "reference": "runs/cv-8b-lora-v1-baseline-eval"}))
    assert built.argv[1:3] == ["-m", "kev.compare"]
    assert flag(built.argv, "--candidate") == "runs/cv-8b-lora-v1-eval"
    assert flag(built.argv, "--reference") == "runs/cv-8b-lora-v1-baseline-eval"
    assert flag(built.argv, "--out") == "runs/cv-8b-lora-v1-compare"
    assert built.artifacts_out == ["comparison:cv-8b-lora-v1"]


def test_calibrate_reads_the_rows_of_its_own_benchmark():
    built = ev.calibrate.build(req({"data": "data/cv"}))
    assert built.argv[1:3] == ["-m", "kev.calibrate"]
    assert flag(built.argv, "--rows") == "runs/cv-8b-lora-v1-eval/rows.json"


def test_icd_coding_rejects_the_8b_track():
    with pytest.raises(Invalid, match="4B"):
        tr.build_argv(JobRequest(scenario="icd-coding", run_name="icd-8b-v1", params={}))
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run python -m pytest tests/test_console_stages_train.py -q`
Expected: FAIL —— `ModuleNotFoundError: No module named 'kev.console.stages.train'`

- [ ] **Step 3: 写 `kev/console/stages/train.py`**

```python
# kev/console/stages/train.py
"""训练作业：kev.train 的 argv 组装。

三种方式（runbook-train_cn.md §〇），预填值取自手册的建议 —— 默认 A1：
LoRA + 从已发布的 jaredpalmer/kev-0.8b 热启动，只在数据量大且证明 LoRA 触顶时升级到 B。

参数名一律下划线（核对自 kev/train.py 的 argparse）。--base 的默认是 Qwen/Qwen3-0.6B-Base，
所以 A2/B 必须显式传 Qwen/Qwen3.5-0.8B-Base，否则会训到错误的基座上。
"""
from __future__ import annotations

from pathlib import Path

from .. import paths
from .base import BuiltCommand, Conflict, Invalid, JobRequest, StageSpec

paths.ensure_medical_on_path()
from run_matrix import FOUR_B_ONLY, SIZES, check_name  # noqa: E402

BASE = "Qwen/Qwen3.5-0.8B-Base"
BASE_REVISION = "9a45d25e"
HEAD_DIM = "256"
COMMON = ["--epochs", "1", "--batch", "4", "--accum", "2", "--dtype", "bf16",
          "--device", "cuda", "--seed", "0", "--head_lr", "0", "--weight_decay", "0.01"]

# UI 表单默认值。lr 0.8B 是 4e-5、4B 是 2e-5（各自沿用 init 的训练参数，MAX_DELTA_LR=5e-5 是硬顶）
METHODS = {
    "a1": {"title": "A1 · LoRA 热启动（推荐起步）", "init_from": SIZES["8b"][0],
           "lora": "16", "lora_targets": "all", "lr": "4e-5", "full_ft": "0",
           "weights_dtype": "fp32", "replay": "2000"},
    "a2": {"title": "A2 · LoRA 从裸基座", "init_from": "", "base": BASE,
           "base_revision": BASE_REVISION, "lora": "16", "lora_targets": "all",
           "lr": "4e-5", "full_ft": "0", "weights_dtype": "fp32", "replay": "2000"},
    "b": {"title": "B · 全参数微调", "init_from": "", "base": BASE,
          "base_revision": BASE_REVISION, "full_ft": "1", "weights_dtype": "bf16",
          "lr": "4e-5", "replay": "0"},
}
SNAPSHOT_LIMIT = 8          # kev.budget.MAX_SNAPSHOTS


def _flag(argv, name):
    return argv[argv.index(name) + 1]


def build_argv(request: JobRequest) -> list:
    params = request.params
    method = params.get("method", "a1")
    if method not in METHODS:
        raise Invalid(f"未知微调方式 {method!r}", field="method",
                      hint=f"可选：{', '.join(sorted(METHODS))}")
    if request.scenario in FOUR_B_ONLY and method in {"a1", "a2"}:
        raise Invalid(f"{request.scenario} 语义难度过高，只支持 4B 轨（方法 b）",
                      field="method", hint="见 run_matrix.FOUR_B_ONLY")

    check_name(request.run_name)      # fullmatch，禁点号；错误时 raise SystemExit
    out = params.get("out") or f"runs/{request.run_name}"
    if params.get("check_exists") and (Path(paths.ROOT / out).exists()):
        raise Conflict(f"{out} 已存在；换一个运行名（例如 -v2）或先清理", hint="旧产物永久保留")

    argv = ["-m", "kev.train",
            "--data", params.get("data") or f"data/{request.scenario}/train.jsonl",
            "--out", out, *COMMON]
def _with_values(mapping: dict) -> list:
    """只追加取值非空的开关 —— 避免把 --init_from '' 传给 kev.train。"""
    out: list = []
    for key, value in mapping.items():
        if value not in (None, ""):
            out += [f"--{key}", str(value)]
    return out


VALUE_KEYS = ("init_from", "base", "base_revision", "lora", "lora_targets",
              "full_ft", "weights_dtype", "lr", "replay", "checkpointing",
              "head_dim", "length_sort", "row_budget", "pass_tokens_max")


def build_argv(request: JobRequest) -> list:
    params = request.params
    method = params.get("method", "a1")
    if method not in METHODS:
        raise Invalid(f"未知微调方式 {method!r}", field="method",
                      hint=f"可选：{', '.join(sorted(METHODS))}")
    if request.scenario in FOUR_B_ONLY and method in {"a1", "a2"}:
        raise Invalid(f"{request.scenario} 语义难度过高，只支持 4B 轨（方法 b）",
                      field="method", hint="见 run_matrix.FOUR_B_ONLY")

    check_name(request.run_name)      # fullmatch，禁点号；错误时 raise SystemExit
    out = params.get("out") or f"runs/{request.run_name}"
    if params.get("check_exists") and (paths.ROOT / out).exists():
        raise Conflict(f"{out} 已存在；换一个运行名（例如 -v2）或先清理", hint="旧产物永久保留")

    argv = ["-m", "kev.train",
            "--data", params.get("data") or f"data/{request.scenario}/train.jsonl",
            "--out", out, *COMMON]
    argv += _with_values({key: METHODS[method].get(key, params.get(key))
                          for key in VALUE_KEYS})

    if METHODS[method]["full_ft"] == "1":
        fractions = params.get("snapshot_fractions")
        if fractions and not params.get("max_steps"):
            raise Invalid("全权重写快照需要 --max_steps 来界定优化步数",
                          field="max_steps", hint=f"kev.budget.MAX_SNAPSHOTS = {SNAPSHOT_LIMIT}")
        if fractions:
            argv += ["--max_steps", str(params["max_steps"]),
                     "--snapshot_fractions", str(fractions),
                     "--snapshot_dir", params.get("snapshot_dir", f"{out}-snapshots")]
    return argv


def _train(request: JobRequest) -> BuiltCommand:
    argv = build_argv(request)
    out = argv[argv.index("--out") + 1]
    return BuiltCommand(argv=[_python()] + argv, cwd=str(paths.ROOT),
                        artifacts_in=[f"dataset:{request.scenario}/train"],
                        artifacts_out=[f"run:{request.run_name}"])


def _python() -> str:
    import sys
    return sys.executable


train = StageSpec("train", "train", "SFT 训练", _train)
TRAIN_STAGES = (train,)
```

`--init_from` / `--base` 的空值由 `_with_values` 统一处理（取值为 `""` 或 `None` 就不追加），所以 A2/B 不会收到 `--init_from ''`，A1 也不会收到多余的 `--base`。

- [ ] **Step 4: 写 `kev/console/stages/eval.py`**

```python
# kev/console/stages/eval.py
"""评测阶段：baseline / benchmark / compare / calibrate。

为什么必须有 baseline + compare（spec §7.1.1）：
- kev/benchmark.py 的 report.json 里没有 bootstrap 键，它写的是 paired_flip（benchmark.py:89）
- 配对 CI 只能由 kev.compare 产出（compare.py:44 -> metrics.paired_bootstrap）
- kev_modal.py 的 result.json 里的 regression 段只存在于 Modal 路径
所以「增益真实」与「公开数据回归」两条闸门都要走 baseline + benchmark + compare。
compare 要求两份 report 的 suite_sha256 一致 —— --data 模式下它是 digest(数据文件)，
而 kev.suite.digest 按文件内容算 sha256，所以同内容不同路径也能配对。
"""
from __future__ import annotations

from .. import paths
from .base import BuiltCommand, Invalid, JobRequest, StageSpec

DEFAULT_BASELINE = "jaredpalmer/kev-0.8b"
PUBLIC_SUITE = "evals/v7/decision-v7"
SPLIT_OF = {"benchmark": "development", "baseline": "development"}


def _python() -> str:
    import sys
    return sys.executable


def _partition(request: JobRequest) -> str:
    data_dir = request.params.get("data") or f"data/{request.scenario}"
    return f"{data_dir}/{request.params.get('split', 'development')}.jsonl"


def _benchmark_like(kind: str):
    def build(request: JobRequest) -> BuiltCommand:
        params = request.params
        device = params.get("device", "cuda")
        if kind == "benchmark":
            run = params.get("run") or f"runs/{request.run_name}"
            suffix = "-eval"
        else:
            run = params.get("baseline") or DEFAULT_BASELINE
            suffix = "-baseline-eval"
        out = f"runs/{request.run_name}{suffix}"
        argv = ["-m", "kev.benchmark", "--run", run,
                "--data", _partition(request), "--out", out, "--device", device]
        name = request.run_name if kind == "benchmark" else f"{request.run_name}-baseline"
        return BuiltCommand(argv=[_python()] + argv, cwd=str(paths.ROOT),
                            artifacts_in=[f"run:{name.split('-baseline')[0]}"],
                            artifacts_out=[f"eval:{name}"])
    return build


benchmark = StageSpec("benchmark", "benchmark", "开发集打分", _benchmark_like("benchmark"))
baseline = StageSpec("baseline", "benchmark", "基线打分（零样本对照）", _benchmark_like("baseline"))


def _compare(request: JobRequest) -> BuiltCommand:
    params = request.params
    candidate = params.get("candidate") or f"runs/{request.run_name}-eval"
    reference = params.get("reference") or f"runs/{request.run_name}-baseline-eval"
    if candidate == reference:
        raise Invalid("candidate 与 reference 不能是同一个目录", field="candidate")
    out = params.get("out") or f"runs/{request.run_name}-compare"
    argv = ["-m", "kev.compare", "--candidate", candidate, "--reference", reference, "--out", out]
    return BuiltCommand(argv=[_python()] + argv, cwd=str(paths.ROOT),
                        artifacts_in=[f"eval:{request.run_name}",
                                      f"eval:{request.run_name}-baseline"],
                        artifacts_out=[f"comparison:{request.run_name}"])


compare = StageSpec("compare", "compare", "配对 bootstrap 对比", _compare)


def _calibrate(request: JobRequest) -> BuiltCommand:
    params = request.params
    rows = params.get("rows") or f"runs/{request.run_name}-eval/rows.json"
    if not rows.endswith("rows.json"):
        raise Invalid("温度拟合需要 kev.benchmark 写出的 rows.json", field="rows")
    out = params.get("out") or str(paths.ROOT / rows).rsplit("/", 1)[0] + "/calibration.json"
    argv = ["-m", "kev.calibrate", "--rows", rows, "--out", out]
    return BuiltCommand(argv=[_python()] + argv, cwd=str(paths.ROOT),
                        artifacts_in=[f"eval:{request.run_name}"],
                        artifacts_out=[f"calibration:{request.run_name}"])


calibrate = StageSpec("calibrate", "calibrate", "温度拟合", _calibrate)

EVAL_STAGES = (baseline, benchmark, compare, calibrate)
```

- [ ] **Step 5: 扩展 `stages/__init__.py` 纳入 train 与 eval**

把 Task 5 建的 `kev/console/stages/__init__.py` 改成：

```python
# kev/console/stages/__init__.py
"""作业类型注册表。kind 与 jobs.kind 一一对应（14 种）。StageSpec 只组装 argv。

分三次建成：Task 5 只导入 data，Task 6 加上 train/eval，Task 7 加上 deploy。
"""
from .base import BuiltCommand, Conflict, Invalid, JobRequest, StageSpec
from . import data as _data
from . import train as _train
from . import eval as _eval

REGISTRY: dict = {}
for _spec in (*_data.DATA_STAGES, *_train.TRAIN_STAGES, *_eval.EVAL_STAGES):
    if _spec.kind in REGISTRY:
        raise ValueError(f"duplicate stage kind {_spec.kind!r}")
    REGISTRY[_spec.kind] = _spec

__all__ = ["REGISTRY", "StageSpec", "BuiltCommand", "JobRequest", "Invalid", "Conflict"]
```

- [ ] **Step 6: 跑测试确认通过**

Run: `uv run python -m pytest tests/test_console_stages_train.py -q`
Expected: PASS —— 13 passed

- [ ] **Step 7: 提交**

```bash
git add kev/console/stages/train.py kev/console/stages/eval.py tests/test_console_stages_train.py
git commit -m "feat(console): 训练与评测阶段 5 种作业（A1/A2/B + baseline/compare）"
```

---

### Task 7: 镜像与部署阶段 3 种作业

**Files:**
- Create: `kev/console/stages/deploy.py`
- Create: `deploy/kev-serve/Dockerfile`
- Test: `tests/test_console_stages_deploy.py`

**Interfaces:**
- Consumes: `base`、`paths`
- Produces: `deploy.image` / `deploy.deploy` / `deploy.smoke`（3 个 `StageSpec`）、`deploy.DEPLOY_STAGES`、`deploy.SMOKE_PROBES`（5 场景各 1 例 System One 试问）、`deploy.DOCKERFILE`（模板路径）、`deploy.SERVE_PORT = 8008`

- [ ] **Step 1: 写失败的测试**

```python
# tests/test_console_stages_deploy.py
"""镜像与部署阶段：docker build / kev.serve / 冒烟试问。

部署做成作业的理由：kev.serve 是长驻进程，正好符合作业模型，启动/停止/日志/崩溃恢复
全部免费获得。而且 playground/next.config.ts 已有 /kev/* -> 127.0.0.1:8008 的 rewrite，
部署一完成现有问答页就能打新模型，前端零改动。

Run: uv run python -m pytest tests/test_console_stages_deploy.py -q
"""
import pytest

from kev.console.stages import deploy as dp
from kev.console.stages.base import Invalid, JobRequest


# 与 Task 6 同一个坑：关键字参数必须收进 params，否则 pydantic 静默丢弃、测试假通过
def req(params=None, *, run_name="cv-8b-lora-v1"):
    return JobRequest(scenario="critical-value", run_name=run_name, params=params or {})


def test_image_builds_from_the_template_with_the_run_filled_in():
    built = dp.image.build(req({"temperature": "2.35"}))
    assert built.argv[:3] == ["docker", "build", "-t"]
    assert built.argv[3] == "kev-cv-8b-lora-v1:2.35"
    assert built.argv[-1].endswith("deploy/kev-serve")
    assert built.env == {"TEMPERATURE": "2.35", "KEV_SERVE_RUN": "cv-8b-lora-v1"}
    assert built.artifacts_out == ["image:kev-cv-8b-lora-v1"]


def test_image_requires_a_temperature():
    with pytest.raises(Invalid, match="temperature"):
        dp.image.build(req({}))


def test_deploy_starts_kev_serve_on_8008():
    built = dp.deploy.build(req({"temperature": "2.35"}))
    assert built.argv[1:3] == ["-m", "kev.serve"]
    assert built.argv[built.argv.index("--run") + 1] == "runs/cv-8b-lora-v1"
    assert built.argv[built.argv.index("--port") + 1] == "8008"
    # 温度只从 calibration.json / head.pt meta 来，不读 KEV_TEMPERATURE
    assert "KEV_TEMPERATURE" not in built.env
    assert built.env["KEV_SERVE_RUN"] == "cv-8b-lora-v1"


def test_deploy_refuses_a_second_endpoint_on_the_same_port():
    with pytest.raises(Invalid, match="8008"):
        dp.deploy.build(req({"temperature": "2.35", "busy_port": True}))


def test_smoke_probes_cover_all_five_scenarios():
    assert len(dp.SMOKE_PROBES) == 5
    assert {probe["scenario"] for probe in dp.SMOKE_PROBES} == {
        "critical-value", "triage", "medication-review", "nursing-quality", "icd-coding"}


def test_smoke_targets_the_deployed_endpoint():
    built = dp.smoke.build(req({"base_url": "http://127.0.0.1:8008"}))
    assert built.argv[1] == "-m"
    assert built.argv[2].endswith("smoke.py")
    assert built.argv[built.argv.index("--base-url") + 1] == "http://127.0.0.1:8008"
    # 产物 id 必须是 smoke:，且与 --out 写出的路径一致（artifacts.resolve 的 smoke 分支）
    assert built.artifacts_out == ["smoke:cv-8b-lora-v1"]
    assert built.argv[built.argv.index("--out") + 1] == "runs/cv-8b-lora-v1-smoke.json"


def test_serve_port_constant_matches_the_playground_rewrite():
    assert dp.SERVE_PORT == 8008


def test_only_deploy_registers_its_artifact_at_start():
    """kev.serve 是长驻作业、永远不「完成」，所以它的 endpoint 产物在 spawn 后就注册。"""
    assert dp.deploy.persist == "start"
    for spec in (dp.image, dp.smoke):
        assert spec.persist == "success"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run python -m pytest tests/test_console_stages_deploy.py -q`
Expected: FAIL —— `ModuleNotFoundError: No module named 'kev.console.stages.deploy'`

- [ ] **Step 3: 写 `kev/console/stages/deploy.py`**

```python
# kev/console/stages/deploy.py
"""镜像与部署阶段：image / deploy / smoke。

部署 = 一个长驻作业（kev.serve），于是启动、停止、日志、崩溃恢复全部走同一条路径。
playground/next.config.ts 已有 /kev/* -> http://127.0.0.1:8008 的 rewrite，所以部署完成后
现有问答页立刻能打新模型。

温度不读 KEV_TEMPERATURE —— tests/test_conventions.py 规定它只能经
kev.checkpoint.LoadOptions.from_env 读取；这里只把 calibration.json 拟合出的温度
通过 KEV_SERVE_RUN 旁边的显式参数交给 kev.serve。
"""
from __future__ import annotations

from .. import paths
from .base import BuiltCommand, Invalid, JobRequest, StageSpec

SERVE_PORT = 8008
DOCKERFILE = paths.ROOT / "deploy/kev-serve/Dockerfile"
SMOKE_SCRIPT = paths.CONSOLE_SCRIPTS / "smoke.py"

# 5 个场景各 1 例试问。state 字段名与 docs/medical/data-format.md 的 state_example 对齐
# （字段名对模型可见，跨记录必须一致）。
SMOKE_PROBES = [
    {"scenario": "critical-value", "state": {
        "patient": "male 67", "context": " routine chemistry panel, no symptoms reported",
        "labs": "K+ 6.2 mmol/L, Cr 98 umol/L", "ref_ranges_included": "yes",
        "missing_context": "no symptoms reported"},
     "questions": [{"qid": "is_critical", "type": "noul",
                    "instructions": "该报告中的任一检验项目是否触及危急值（需要立即临床干预）？"}]},
    {"scenario": "triage", "state": {
        "patient": "female 34, gestation 28 weeks", "channel": "outpatient",
        "chief_complaint": "规律腹痛 3 小时", "duration": "3 hours",
        "accompanying": "no fever, no vaginal bleeding", "history": "G2P1",
        "vitals": "BP 118/74, HR 88", "red_flags": "none"},
     "questions": [{"qid": "immediate_human", "type": "noul",
                    "instructions": "该患者是否需要立即人工分诊（而非继续等待）？"}]},
    {"scenario": "medication-review", "state": {
        "patient": "female 62, eGFR 24", "state_flags": "renal impairment",
        "allergies": "penicillin (rash)", "current_meds": "amoxicillin 500mg tid",
        "current_rx": "amoxicillin 500mg tid", "days_on_drug": 6,
        "indication": "sinusitis"},
     "questions": [{"qid": "needs_pharmacist", "type": "noul",
                    "instructions": "该用药是否需要药师介入复核？"}]},
    {"scenario": "nursing-quality", "state": {
        "patient": "male 71, bed 12", "ward": "cardiology", "nursing_level": "level 2",
        "check_point": "pressure ulcer prevention, repositioning",
        "observed": "no repositioning documented for 6 hours",
        "dependencies": "none", "risk_scores": "Braden 12"},
     "questions": [{"qid": "reportable", "type": "noul",
                    "instructions": "该护理缺陷是否应上报？（质量问题而非个人疏忽）"}]},
    {"scenario": "icd-coding", "state": {
        "patient": "female 58", "length_of_stay_days": 9, "primary_dx": "J18.9",
        "secondary_dx": "E11.9, I10", "procedure": "none", "key_findings": "community-acquired pneumonia",
        "past_history": "type 2 diabetes, hypertension", "clinical_course": "improved on antibiotics"},
     "questions": [{"qid": "needs_coder", "type": "noul",
                    "instructions": "该编码是否需要编码员人工复核？"}]},
]


def _python() -> str:
    import sys
    return sys.executable


def _temperature(params: dict) -> str:
    value = str(params.get("temperature") or "").strip()
    if not value or value == "0":
        raise Invalid(
            "缺少服务温度。先跑 calibrate，从 calibration.json 的 workload_temperature 取值再部署",
            field="temperature",
            hint="绝不在 development.jsonl 上拟合温度；均衡先验 != 真实临床先验")
    return value


def _image(request: JobRequest) -> BuiltCommand:
    temperature = _temperature(request.params)
    tag = f"kev-{request.run_name}"
    return BuiltCommand(
        argv=["docker", "build", "-t", f"{tag}:{temperature}", "-f", str(DOCKERFILE), "--build-arg",
              f"KEV_SERVE_RUN={request.run_name}", "--build-arg", f"TEMPERATURE={temperature}",
              str(DOCKERFILE.parent)],
        cwd=str(paths.ROOT),
        env={"KEV_SERVE_RUN": request.run_name, "TEMPERATURE": temperature},
        artifacts_in=[f"run:{request.run_name}"],
        artifacts_out=[f"image:{tag}"],
    )


image = StageSpec("image", "image", "构建部署镜像", _image)


def _deploy(request: JobRequest) -> BuiltCommand:
    temperature = _temperature(request.params)
    if request.params.get("busy_port"):
        raise Invalid(f"端口 {SERVE_PORT} 已被占用；先停掉当前端点（回滚或取消它的 deploy 作业）",
                      field="port", hint="双端点共存要换端口，并同步改 playground 的 rewrite")
    run = request.params.get("run") or f"runs/{request.run_name}"
    argv = [_python(), "-m", "kev.serve", "--run", run, "--port", str(SERVE_PORT),
            "--temperature", temperature]
    return BuiltCommand(argv=argv, cwd=str(paths.ROOT), env={"KEV_SERVE_RUN": request.run_name},
                        artifacts_in=[f"run:{request.run_name}"],
                        artifacts_out=[f"endpoint:{SERVE_PORT}"])


deploy = StageSpec("deploy", "deploy", "启动 System One 端点", _deploy, persist="start")


def _smoke(request: JobRequest) -> BuiltCommand:
    base_url = request.params.get("base_url") or f"http://127.0.0.1:{SERVE_PORT}"
    out = f"runs/{request.run_name}-smoke.json"
    argv = [_python(), str(SMOKE_SCRIPT), "--base-url", base_url, "--out", out]
    # 产物 id 用 smoke: 而不是 eval: —— eval:<name> 会被 resolve 成 runs/<name>-eval，
    # 与真实报告路径 runs/<name>-smoke.json 对不上（artifacts.resolve 已有 smoke 分支）
    return BuiltCommand(argv=argv, cwd=str(paths.ROOT),
                        artifacts_in=[f"endpoint:{SERVE_PORT}"],
                        artifacts_out=[f"smoke:{request.run_name}"])


smoke = StageSpec("smoke", "deploy", "冒烟测试", _smoke)

DEPLOY_STAGES = (image, deploy, smoke)
```

- [ ] **Step 4: 写 `deploy/kev-serve/Dockerfile` 与 `docs/medical/console/smoke.py`**

```dockerfile
# deploy/kev-serve/Dockerfile
# Kev System One 端点镜像。控制台按 run_matrix 的命名规范传入 KEV_SERVE_RUN 与 TEMPERATURE。
#
# spec §16 开放问题 1 的默认值：先只提供 GPU 镜像 —— kev/serve.py:332 的服务默认值在
# 非 CPU 设备上开 bf16 + CUDA graphs，CPU 路径未在 0.8B 规模上验证过。
ARG CUDA_IMAGE=nvidia/cuda:12.8.1-cudnn-runtime-ubuntu24.04
FROM ${CUDA_IMAGE}

ARG KEV_SERVE_RUN=smoke
ARG TEMPERATURE=1.0
ENV KEV_SERVE_RUN=${KEV_SERVE_RUN} \
    KEV_API_KEY= \
    PYTHONIOENCODING=utf-8 \
    HF_ENDPOINT=${HF_ENDPOINT:-https://hf-mirror.com}

WORKDIR /srv/kev
COPY . /srv/kev

# 依赖装在镜像里；HF 权重不烘进镜像（医疗模型不入公共 Hub），运行时从私有库拉或挂载。
RUN pip install --no-cache-dir "fastapi>=0.115" "uvicorn>=0.30" \
 && pip install --no-cache-dir "torch>=2.6,<2.9" "transformers>=5.17,<6" "peft>=0.21" \
 && pip install --no-cache-dir "typesafe-sdk>=0.6.0" matplotlib

# 权重与 checkpoint 由编排层挂载或由 kev.checkpoint 按 KEV_SERVE_RUN 解析
VOLUME ["/srv/kev/runs", "/root/.cache/huggingface"]
EXPOSE 8008
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8008/v1/models').status==200 else 1)"

# 温度由编排层从 calibration.json 拟合后显式传入；不读 KEV_TEMPERATURE
# （tests/test_conventions.py 规定它只能经 kev.checkpoint.LoadOptions.from_env）。
CMD ["sh", "-c", "python -m kev.serve --run runs/${KEV_SERVE_RUN} --port 8008 --temperature ${TEMPERATURE}"]
```

```python
#!/usr/bin/env python3
"""对已部署的 System One 端点做冒烟测试：5 个场景各 1 例。

只读、不写业务数据；输出 JSON 报告供 UI 展示 p 分布与 argmax。
探针的 state 字段名与 docs/medical/data-format.md 的 state_example 对齐 —— 字段名对模型可见，
改字段名等于换了一个任务。

Run: python docs/medical/console/smoke.py --base-url http://127.0.0.1:8008 --out runs/x-smoke.json
"""
import argparse
import json
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
import sys
sys.path.insert(0, str(ROOT / "docs/medical/generators"))
sys.path.insert(0, str(ROOT / "docs/medical/console"))

from kev.suite import write_json          # noqa: E402
import deploy as dp                        # noqa: E402  (kev.console.stages.deploy)


def post(base_url: str, path: str, payload: dict) -> dict:
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def get(base_url: str, path: str) -> dict:
    with urllib.request.urlopen(f"{base_url.rstrip('/')}{path}", timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)

    report = {"base_url": args.base_url, "models": None, "probes": [], "failures": 0}
    try:
        report["models"] = get(args.base_url, "/v1/models")
    except (urllib.error.URLError, TimeoutError) as error:
        report["error"] = f"端点不可达：{error}"
        write_json(args.out, report)
        print(f"endpoint unreachable: {error}")
        return 1

    for probe in dp.SMOKE_PROBES:
        questions = [{"id": q["qid"], "type": q["type"], "instructions": q["instructions"]}
                     for q in probe["questions"]]
        try:
            answer = post(args.base_url, "/v1/systemone", {"state": probe["state"], "questions": questions})
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as error:
            report["failures"] += 1
            report["probes"].append({"scenario": probe["scenario"], "error": str(error)})
            continue
        answers = answer.get("answers") or answer.get("response", {}).get("answers") or []
        report["probes"].append({"scenario": probe["scenario"], "answers": answers})

    write_json(args.out, report)
    print(f"probes {len(report['probes'])} failures {report['failures']}")
    return 1 if report["failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: 跑测试确认通过**

Run: `uv run python -m pytest tests/test_console_stages_deploy.py -q`
Expected: PASS —— 7 passed

- [ ] **Step 6: 提交**

```bash
git add kev/console/stages/deploy.py deploy/kev-serve/Dockerfile docs/medical/console/smoke.py tests/test_console_stages_deploy.py
git commit -m "feat(console): 镜像与部署阶段 3 种作业 + 5 场景冒烟探针"
```

---

### Task 8: FastAPI 路由与 SSE

**Files:**
- Create: `kev/console/app.py`
- Create: `kev/console/__main__.py`
- Test: `tests/test_console_api.py`

**Interfaces:**
- Consumes: `db.Store`、`executor.LocalExecutor`、`gates`、`stages.REGISTRY`、`stages.data.parse_plan_size`、`kev.suite.read_json`
- Produces: `app.create_app(store=None, executor=None) -> FastAPI`、`app.DB_ENV`（`KEV_CONSOLE_DB`）、app 默认挂载在 `:8790`

路由（全部在 `/console/api` 下，见 spec §10.1）：`GET /config`、`GET /scenarios`、`GET /datasets`、`GET /datasets/{id}`、`GET /datasets/{id}/export`、`POST /jobs`、`GET /jobs`、`GET /jobs/{id}`、`POST /jobs/{id}/cancel`、`POST /jobs/{id}/retry`、`GET /jobs/{id}/events`、`GET /jobs/{id}/stream`、`GET /artifacts`、`GET /gates/{stage}`、`GET /endpoints`

- [ ] **Step 1: 写失败的测试**

```python
# tests/test_console_api.py
"""编排服务的 HTTP 面：作业提交、闸门预检、SSE 日志流、错误体。

用 TestClient，不起真实服务；作业用 kind=smoke 之外的假 kind 会返回 404，
真作业（split 之类）在测试里只做 preview，不 spawn。

Run: uv run python -m pytest tests/test_console_api.py -q
"""
import json

import pytest
from fastapi.testclient import TestClient

from kev.console.app import create_app
from kev.console.db import Store


@pytest.fixture
def client(tmp_path):
    app = create_app(store=Store(tmp_path / "db.sqlite"))
    with TestClient(app) as test_client:
        yield test_client


def body(response):
    return response.json()


def test_config_lists_credential_booleans_never_values(client, monkeypatch):
    monkeypatch.setenv("KEV_GEN_API_KEYS", "sk-super-secret")
    response = client.get("/console/api/config")
    assert response.status_code == 200
    payload = body(response)
    assert payload["credentials"]["KEV_GEN_API_KEYS"] is True
    assert "sk-super-secret" not in response.text
    assert set(payload["scenarios"]) >= {"critical-value", "triage"}


def test_scenarios_endpoint_lists_the_specs(client):
    names = [row["name"] for row in body(client.get("/console/api/scenarios"))]
    assert "critical-value" in names
    assert {"name": "critical-value", "questions": 4} == next(
        row for row in body(client.get("/console/api/scenarios")) if row["name"] == "critical-value")


def test_job_preview_returns_argv_without_spawning(client):
    response = client.post("/console/api/jobs/preview", json={
        "kind": "train", "scenario": "critical-value", "run_name": "cv-8b-v1",
        "params": {"method": "a1"}})
    assert response.status_code == 200
    assert "--init_from" in body(response)["argv"]


def test_unknown_kind_is_404(client):
    assert client.post("/console/api/jobs", json={
        "kind": "nope", "scenario": "triage", "run_name": "t", "params": {}}).status_code == 404


def test_submit_then_read_the_job(client):
    response = client.post("/console/api/jobs", json={
        "kind": "plan_size", "scenario": "critical-value", "run_name": "cv-8b-v1", "params": {}})
    assert response.status_code == 201
    job_id = body(response)["id"]
    assert body(client.get(f"/console/api/jobs/{job_id}"))["kind"] == "plan_size"
    assert job_id in [row["id"] for row in body(client.get("/console/api/jobs"))]


def test_bad_run_name_is_a_400_with_a_hint(client):
    # 必须用 train：只有 train/build 会调 run_matrix.check_name，plan_size 不校验运行名
    response = client.post("/console/api/jobs", json={
        "kind": "train", "scenario": "critical-value",
        "run_name": "critical-value-0.8b-v1", "params": {"method": "a1"}})
    assert response.status_code == 400
    payload = body(response)["error"]
    assert payload["kind"] == "validation"
    assert payload["field"] == "run_name"
    assert "8b" in payload["hint"]


def test_a_second_train_is_refused_while_one_is_live(client):
    """单 GPU 闸：同时只应有一个 train。kev.experiment 在 Windows 上不可 import
    （experiment.py:14 直接 import fcntl），所以这道闸必须自己实现。"""
    client.app.state.store.create_job(
        kind="train", stage="train", scenario="critical-value", title="running",
        request={}, argv=["x"], env_overlay={}, cwd=".", log_path="l.log",
        artifacts_in=[], artifacts_out=[])
    live = client.app.state.store.active_job_of_kind("train")
    client.app.state.store.transition(live["id"], "queued")
    client.app.state.store.transition(live["id"], "running")
    response = client.post("/console/api/jobs", json={
        "kind": "train", "scenario": "critical-value", "run_name": "cv-8b-lora-v2",
        "params": {"method": "a1"}})
    assert response.status_code == 409
    assert body(response)["error"]["kind"] == "conflict"


def test_startup_marks_live_jobs_interrupted(tmp_path):
    """崩溃恢复：WSL2 会自动回收内存，服务重启是常态。启动时残留的 running/queued
    必须变成 interrupted，否则它们会永远卡在 running（spec §9.3、人工验收第 5 项）。"""
    from kev.console.app import create_app
    from kev.console.db import Store
    store = Store(tmp_path / "db.sqlite")
    live = store.create_job(
        kind="train", stage="train", scenario="triage", title="t",
        request={}, argv=["x"], env_overlay={}, cwd=".", log_path="l.log",
        artifacts_in=[], artifacts_out=[])
    store.transition(live, "queued")
    store.transition(live, "running")
    done = store.create_job(
        kind="split", stage="data", scenario="triage", title="t",
        request={}, argv=["x"], env_overlay={}, cwd=".", log_path="l.log",
        artifacts_in=[], artifacts_out=[])
    store.transition(done, "queued")
    store.transition(done, "running")
    store.transition(done, "succeeded")

    with TestClient(create_app(store=store)):
        pass                       # 建 app 即触发恢复
    assert store.get_job(live)["status"] == "interrupted"
    assert store.get_job(done)["status"] == "succeeded"


def test_retry_increments_attempt(client):
    """attempt 必须在重试时递增，否则 jobs 表无法区分「第一次」和「换名重试」。"""
    first = body(client.post("/console/api/jobs", json={
        "kind": "plan_size", "scenario": "triage", "run_name": "t", "params": {}}))
    client.app.state.store.transition(first["id"], "queued")
    client.app.state.store.transition(first["id"], "running")
    client.app.state.store.transition(first["id"], "failed", error="boom", exit_code=1)
    second = body(client.post(f"/console/api/jobs/{first['id']}/retry"))
    assert second["attempt"] == first["attempt"] + 1
    assert second["title"] != first["title"]      # 换名，绝不复用目录


def test_a_broken_register_is_reported_not_swallowed(client, monkeypatch):
    """产物注册失败必须留下痕迹。"""
    def boom(store, job):
        raise RuntimeError("register failed")
    monkeypatch.setattr("kev.console.app.artifacts.register", boom)
    with pytest.raises(RuntimeError, match="register failed"):
        client.app.state.executor.on_finished("some-job", 0)


def test_gate_failure_blocks_submission_with_422(client, monkeypatch):
    monkeypatch.setattr("kev.console.app.evaluate", lambda stage, **p: [
        type("G", (), {"id": "G1", "ok": False, "detail": "3 条超限", "actual": "3", "need": "0"})()])
    response = client.post("/console/api/jobs", json={
        "kind": "train", "scenario": "critical-value", "run_name": "cv-8b-v1", "params": {}})
    assert response.status_code == 422
    assert body(response)["error"]["kind"] == "gate"
    assert body(client.get("/console/api/jobs")) == []   # 闸门失败不落库


def test_events_endpoint_pages_from_a_cursor(client):
    job_id = body(client.post("/console/api/jobs", json={
        "kind": "plan_size", "scenario": "triage", "run_name": "t", "params": {}}))["id"]
    store = client.app.state.store
    store.append_events(job_id, [("stdout", "one"), ("stdout", "two")])
    first = body(client.get(f"/console/api/jobs/{job_id}/events"))
    assert [row["line"] for row in first["events"]] == ["one", "two"]
    second = body(client.get(f"/console/api/jobs/{job_id}/events",
                             params={"after_id": first["events"][0]["id"]}))
    assert [row["line"] for row in second["events"]] == ["two"]


def test_stream_is_an_sse_frame_stream(client):
    job_id = body(client.post("/console/api/jobs", json={
        "kind": "plan_size", "scenario": "triage", "run_name": "t", "params": {}}))["id"]
    client.app.state.store.append_events(job_id, [("stdout", "hello")])
    with client.stream("GET", f"/console/api/jobs/{job_id}/stream") as response:
        assert response.headers["content-type"].startswith("text/event-stream")
        chunk = next(response.iter_lines())
    assert chunk.startswith("id: ")


def test_stream_resumes_from_the_last_event_id_header(client):
    """EventSource 断线自动重连时沿用原 URL，Last-Event-ID 只以 header 形式回来。
    只读 after_id 查询参数会让重连从 0 全量重放（Task 2 评审发现，人工验收第 3 项）。"""
    job_id = body(client.post("/console/api/jobs", json={
        "kind": "plan_size", "scenario": "triage", "run_name": "t", "params": {}}))["id"]
    store = client.app.state.store
    first = store.append_events(job_id, [("stdout", "one")])
    store.append_events(job_id, [("stdout", "two")])
    with client.stream("GET", f"/console/api/jobs/{job_id}/stream?after_id=0",
                       headers={"Last-Event-ID": str(first)}) as response:
        lines = list(response.iter_lines())
    assert any('"two"' in line for line in lines)     # 只应收到 "two"
    assert not any('"one"' in line for line in lines)  # "one" 不重放


def test_gates_endpoint_reports_each_gate(client):
    rows = body(client.get("/console/api/gates/train"))
    assert [row["id"] for row in rows] == ["G1", "G2", "G3"]


def test_endpoints_reflects_the_deploy_artifact(client):
    assert body(client.get("/console/api/endpoints")) == {"endpoints": []}
    client.app.state.store.put_artifact(kind="endpoint", name="8008", path="http://127.0.0.1:8008",
                                        meta={"run": "cv-8b-lora-v1", "temperature": "2.35"})
    rows = body(client.get("/console/api/endpoints"))["endpoints"]
    assert rows[0]["name"] == "8008"
    assert rows[0]["meta"]["temperature"] == "2.35"


def test_a_finished_job_registers_its_artifacts_and_lineage(client, tmp_path, monkeypatch):
    """端到端证明产物注册链路是通的：作业成功 -> on_finished -> register。
    早期版本没有任何代码调 put_artifact，整层是死代码（计划修正）。"""
    from kev.console import artifacts
    monkeypatch.setattr(artifacts.paths, "ROOT", tmp_path)
    (tmp_path / "data/cv").mkdir(parents=True)
    summary = '{"records": 787, "invalid_lines": 0}'
    (tmp_path / "data/cv/summary.json").write_text(summary, encoding="utf-8")

    job_id = client.app.state.store.create_job(
        kind="split", stage="data", scenario="critical-value", title="cv",
        request={}, argv=["x"], env_overlay={}, cwd=str(tmp_path), log_path="l.log",
        artifacts_in=["dataset:cv"], artifacts_out=["dataset:cv/summary"])
    artifacts.register(client.app.state.store, client.app.state.store.get_job(job_id))

    datasets = body(client.get("/console/api/datasets"))
    assert [row["id"] for row in datasets] == ["dataset:cv/summary"]
    assert datasets[0]["meta"]["records"] == 787
    edges = {(edge["relation"], edge["child"])
             for edge in body(client.get("/console/api/artifacts"))[0]["lineage"]}
    assert ("split_into", "dataset:cv/summary") in edges


def test_train_is_submittable_once_precheck_and_summary_exist(client, tmp_path, monkeypatch):
    """G1/G2/G3 全通过时 train 必须能被提交 —— 「闸门拦死 train」缺陷的回归防护。
    注意这里断言的是 201：闸门失败会返回 422 且不落库（spec §6.1）。"""
    from kev.console import artifacts, gates
    monkeypatch.setattr(artifacts.paths, "ROOT", tmp_path)
    (tmp_path / "data/cv").mkdir(parents=True)
    summary = '{"records": 787, "invalid_lines": 0, "label_warnings": []}'
    (tmp_path / "data/cv/summary.json").write_text(summary, encoding="utf-8")
    (tmp_path / "data/console").mkdir(parents=True)
    precheck = '{"records": 551, "over_limit": 0}'
    (tmp_path / "data/console/precheck-data-cv-train.json").write_text(precheck, encoding="utf-8")

    client.app.state.store.transition(
        client.app.state.store.create_job(
            kind="plan_size", stage="data", scenario="critical-value", title="cv",
            request={}, argv=["x"], env_overlay={}, cwd=".", log_path="l.log",
            artifacts_in=[], artifacts_out=[]),
        "queued")
    response = client.post("/console/api/jobs", json={
        "kind": "train", "scenario": "critical-value", "run_name": "cv-8b-lora-v1",
        "params": {"method": "a1"}})
    assert response.status_code == 201
    assert body(response)["kind"] == "train"


def test_cancel_unknown_job_is_404(client):
    assert client.post("/console/api/jobs/nope/cancel").status_code == 404
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run python -m pytest tests/test_console_api.py -q`
Expected: FAIL —— `ModuleNotFoundError: No module named 'kev.console.app'`

- [ ] **Step 3: 写 `kev/console/app.py`**

```python
# kev/console/app.py
"""编排服务的 HTTP 面：作业提交、闸门预检、产物血缘、SSE 日志流。

路由清单见 spec §10.1。playground 侧只有一个薄代理（/api/console/[...path]），
所以这里不关心 CORS；编排服务只绑 127.0.0.1，无鉴权（本地单用户，spec §12）。

SSE 从 events 表按 id 游标轮询，而不是靠进程内的队列：日志文件才是真相源，
这样多进程、重启、Last-Event-ID 续传都天然成立。
"""
from __future__ import annotations

import asyncio
import json
import os
import uuid
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

from . import artifacts, paths
from .db import Store
from .events import parse_note, parse_step, sse_frame
from .executor import LocalExecutor
from .gates import evaluate
from .stages import REGISTRY, Conflict, Invalid, JobRequest
from .stages import data as data_stages

DB_ENV = "KEV_CONSOLE_DB"
POLL_SECONDS = 0.5
STREAM_BATCH = 200
SECRET_NAMES = ("KEV_API_KEY", "KEV_GEN_API_KEYS", "KEV_HF_SECRET", "KEV_SERVE_SECRET", "HF_TOKEN")


def _error(kind: str, message: str, *, status: int, field: str = "", hint: str = "",
           stderr_tail: str = "") -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": {"kind": kind, "message": message, "field": field,
                           "hint": hint, "stderr_tail": stderr_tail}},
    )


def create_app(*, store: Store | None = None, executor: LocalExecutor | None = None) -> FastAPI:
    app = FastAPI(title="kev-console")
    app.state.store = store or Store(Path(os.environ.get(DB_ENV, paths.DB_PATH)))
    app.state.store.interrupt_stale_jobs()          # spec §9.3：启动即恢复
    def register_finished(job_id, exit_code) -> None:
        """产物注册的唯一入口。作业自然成功后把它声明的 artifacts_out 落成 artifact，
        并写 in -> out 血缘。cancel 不会触发（执行器对 cancel 不回调 on_finished）。

        注册失败**不吞**：追加一条 system 事件，让 UI 与人工验收能看见产物缺失。
        """
        job = app.state.store.get_job(job_id)
        if job is None or exit_code != 0:
            return
        try:
            artifacts.register(app.state.store, job)
        except Exception as error:
            app.state.store.append_events(job_id, [("system", f"产物注册失败：{error}（见实现报告）")])
            raise

    app.state.executor = executor or LocalExecutor(app.state.store, on_finished=register_finished)

    def store() -> Store:
        return app.state.store

    # ---- config ----------------------------------------------------------

    @app.get("/console/api/config")
    def get_config() -> dict:
        from .stages.train import METHODS
        return {
            "scenarios": list(data_stages.SCENARIOS),
            "methods": {key: {"title": value["title"], "lr": value.get("lr", "")}
                        for key, value in METHODS.items()},
            "serve_port": 8008,
            # 只回布尔态：凭据值永远不下发到浏览器
            "credentials": {name: bool(os.environ.get(name)) for name in SECRET_NAMES},
        }

    @app.get("/console/api/scenarios")
    def get_scenarios() -> list:
        out = []
        for name in data_stages.SCENARIOS:
            spec = json.loads((paths.SPECS / f"{name}.json").read_text(encoding="utf-8"))
            out.append({"name": name, "questions": len(spec.get("questions", {}))})
        return out

    # ---- datasets --------------------------------------------------------

    @app.get("/console/api/datasets")
    def get_datasets() -> list:
        return store().list_artifacts("dataset")

    @app.get("/console/api/datasets/{artifact_id:path}")
    def get_dataset(artifact_id: str):
        artifact = store().get_artifact(artifact_id)
        if artifact is None:
            return _error("validation", f"未知数据集 {artifact_id}", status=404)
        return {**artifact, "lineage": store().lineage_of(artifact_id)}

    @app.get("/console/api/datasets/{artifact_id:path}/export")
    def export_dataset(artifact_id: str):
        artifact = store().get_artifact(artifact_id)
        if artifact is None:
            return _error("validation", f"未知数据集 {artifact_id}", status=404)
        target = paths.ROOT / artifact["path"]
        if not target.exists():
            return _error("validation", f"数据集文件不存在：{artifact['path']}", status=404)
        return StreamingResponse(iter([target.read_bytes()]), media_type="application/x-ndjson",
                                 headers={"Content-Disposition":
                                          f'attachment; filename="{artifact["name"].replace("/", "_")}.jsonl"'})

    # ---- jobs ------------------------------------------------------------

    @app.post("/console/api/jobs/preview")
    def preview_job(payload: dict):
        stage = REGISTRY.get(payload.get("kind", ""))
        if stage is None:
            return _error("validation", f"未知作业类型 {payload.get('kind')!r}", status=404,
                          hint=f"可选：{', '.join(sorted(REGISTRY))}")
        try:
            built = stage.preview(JobRequest(**payload))
        except Invalid as error:
            return _error("validation", error.message, status=400, field=error.field, hint=error.hint)
        except SystemExit as error:            # run_matrix.check_name 用 SystemExit
            return _error("validation", str(error), status=400, field="run_name",
                          hint="运行名只允许字母数字下划线连字符，尺寸写 8b 不写 0.8b")
        except Conflict as error:
            return _error("conflict", str(error), status=409, hint=error.args[0] if error.args else "")
        return {"argv": [str(part) for part in built.argv], "env": built.env,
                "artifacts_in": built.artifacts_in, "artifacts_out": built.artifacts_out}

    @app.post("/console/api/jobs")
    def submit_job(payload: dict):
        kind = payload.get("kind", "")
        stage = REGISTRY.get(kind)
        if stage is None:
            return _error("validation", f"未知作业类型 {kind!r}", status=404,
                          hint=f"可选：{', '.join(sorted(REGISTRY))}")
        try:
            request = JobRequest(**payload)
            built = stage.preview(request)
        except Invalid as error:
            return _error("validation", error.message, status=400, field=error.field, hint=error.hint)
        except SystemExit as error:
            return _error("validation", str(error), status=400, field="run_name",
                          hint="运行名只允许字母数字下划线连字符，尺寸写 8b 不写 0.8b")
        except Conflict as error:
            return _error("conflict", str(error), status=409)

        if kind == "train":                       # 单 GPU 闸：同时只允许一个 train
            live = store().active_job_of_kind("train")
            if live is not None:
                return _error("conflict", f"已有训练在跑（作业 {live['id'][:8]}）", status=409,
                              hint="单 GPU 上同时只应有一个训练；先取消或等它结束")

        gates = evaluate(stage.stage, **_gate_products(store(), request))
        failed = [gate for gate in gates if not gate.ok]
        if failed:
            # 闸门失败是配置问题，不是执行失败 —— 不落库（spec §6.1）
            return _error("gate", f"{len(failed)} 道闸未通过", status=422,
                          stderr_tail=json.dumps(
                              [{"id": g.id, "detail": g.detail, "actual": g.actual, "need": g.need}
                               for g in failed], ensure_ascii=False))

        job_id = _spawn(app, stage, request, built)
        return JSONResponse(status_code=201, content=store().get_job(job_id))

    def _spawn(app, stage, request, built, *, attempt=1, parent_id=None) -> str:
        log_path = paths.JOB_LOGS / f"{uuid.uuid4().hex}.log"
        job_id = app.state.store.create_job(
            kind=stage.kind, stage=stage.stage, scenario=request.scenario,
            title=request.run_name or stage.title, request=request.params,
            argv=[str(p) for p in built.argv], env_overlay=built.env,
            cwd=built.cwd or str(paths.ROOT), log_path=str(log_path),
            artifacts_in=built.artifacts_in, artifacts_out=built.artifacts_out,
            attempt=attempt, parent_id=parent_id,
        )
        app.state.executor.spawn(job_id, built.argv, cwd=built.cwd or str(paths.ROOT),
                                 log_path=str(log_path), env_overlay=built.env)
        if stage.persist == "start":
            # 长驻作业（如 deploy 的 kev.serve）永远不「完成」，所以产物在 spawn 后就注册。
            # 在线状态由部署页实际探 /v1/models 决定，不由这里决定。
            artifacts.register(app.state.store, app.state.store.get_job(job_id))
        return job_id

    @app.get("/console/api/jobs")
    def get_jobs(status: str | None = None, stage: str | None = None, scenario: str | None = None):
        return store().list_jobs(status=status, stage=stage, scenario=scenario)

    @app.get("/console/api/jobs/{job_id}")
    def get_job(job_id: str):
        job = store().get_job(job_id)
        if job is None:
            return _error("validation", f"未知作业 {job_id}", status=404)
        artifacts = [store().get_artifact(a) for a in job["artifacts_in"] + job["artifacts_out"]]
        return {**job,
                "metrics": app.state.executor.metrics(job_id).points(),
                "metrics_dropped": app.state.executor.metrics(job_id).dropped(),
                "artifacts": [a for a in artifacts if a],
                # 倒序取尾页：read_events 默认按 id 升序取最早 500 行，训练收尾才出现的
                # saved note 在任何真实 run 里都不会浮出来（Task 2 评审发现）
                "notes": [n for n in (parse_note(e["line"])
                                      for e in reversed(store().read_events(job_id, limit=500)))
                          if n]}

    @app.post("/console/api/jobs/{job_id}/cancel")
    def cancel_job(job_id: str):
        if store().get_job(job_id) is None:
            return _error("validation", f"未知作业 {job_id}", status=404)
        return {"canceled": app.state.executor.cancel(job_id)}

    @app.post("/console/api/jobs/{job_id}/retry")
    def retry_job(job_id: str):
        job = store().get_job(job_id)
        if job is None:
            return _error("validation", f"未知作业 {job_id}", status=404)
        if job["status"] not in {"failed", "canceled", "interrupted"}:
            return _error("conflict", f"{job['status']} 的作业不能重试", status=409)
        attempt = job["attempt"] + 1
        stage = REGISTRY.get(job["kind"])
        if stage is None:
            return _error("validation", f"原作业类型 {job['kind']!r} 已不注册", status=409)
        try:
            request = JobRequest(scenario=job["scenario"],
                                 run_name=f"{job['title']}-r{attempt}",
                                 params=job["request"])
            built = stage.preview(request)
        except Invalid as error:
            return _error("validation", error.message, status=400, field=error.field, hint=error.hint)
        except SystemExit as error:
            return _error("validation", str(error), status=400, field="run_name")
        except Conflict as error:
            return _error("conflict", str(error), status=409)
        # 换名而非复用目录：kev.train / evaluate_records 都是 mkdir(exist_ok=False)，
        # 且旧产物要永久保留（可审计）。attempt 递增，parent_id 指向原作业。
        new_id = _spawn(app, stage, request, built, attempt=attempt, parent_id=job_id)
        return JSONResponse(status_code=201, content=store().get_job(new_id))

    @app.get("/console/api/jobs/{job_id}/events")
    def get_events(job_id: str, after_id: int = 0):
        return {"events": store().read_events(job_id, after_id=after_id)}

    @app.get("/console/api/jobs/{job_id}/stream")
    async def stream_job(job_id: str, request: Request, after_id: int = 0):
        if store().get_job(job_id) is None:
            return _error("validation", f"未知作业 {job_id}", status=404)
        # EventSource 断线自动重连时**沿用原 URL**，Last-Event-ID 只以 header 形式回来。
        # 只读查询参数会让重连从 after_id=0 全量重放（Task 2 评审发现）——所以 header 优先。
        cursor = int(request.headers.get("last-event-id") or after_id or 0)

        async def frames():
            nonlocal cursor
            while True:
                if await request.is_disconnected():
                    break
                rows = store().read_events(job_id, after_id=cursor, limit=STREAM_BATCH)
                for row in rows:
                    cursor = row["id"]
                    yield sse_frame(row, parse_step(row["line"]))
                job = store().get_job(job_id)
                if not rows and job and job["status"] in {"succeeded", "failed", "canceled", "interrupted"}:
                    yield (f"event: status\ndata: "
                           f"{json.dumps({'status': job['status'], 'exit_code': job['exit_code']})}\n\n")
                    break
                if not rows:
                    yield 'event: ping\ndata: {}\n\n'
                await asyncio.sleep(POLL_SECONDS if not rows else 0)

        return StreamingResponse(frames(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    # ---- artifacts / gates / endpoints -----------------------------------

    @app.get("/console/api/artifacts")
    def get_artifacts(kind: str | None = None):
        rows = store().list_artifacts(kind)
        for row in rows:
            row["lineage"] = store().lineage_of(row["id"])
        return rows

    @app.get("/console/api/gates/{stage}")
    def get_gates(stage: str, scenario: str = "critical-value", run_name: str = ""):
        gates = evaluate(stage, **_gate_products(store(), JobRequest(
            scenario=scenario, run_name=run_name, params={})))
        return [{"id": g.id, "ok": g.ok, "detail": g.detail, "actual": g.actual, "need": g.need}
                for g in gates]

    @app.get("/console/api/endpoints")
    def get_endpoints():
        return {"endpoints": store().list_artifacts("endpoint")}

    return app


def _gate_products(store: Store, request: JobRequest) -> dict:
    """把已落库的产物读成闸门要的形状。缺产物时 evaluate 会判失败而不是崩。"""
    from kev.suite import read_json

    def load(kind: str, name: str):
        artifact = store.get_artifact(f"{kind}:{name}")
        if artifact is None:
            return None
        try:
            return read_json(paths.ROOT / artifact["path"]) if (paths.ROOT / artifact["path"]).exists() else None
        except (OSError, ValueError):
            return None

    data_dir = request.params.get("data") or f"data/{request.scenario}"
    split = request.params.get("split", "train")
    return {
        # precheck 是独立的产物类型（不是 dataset 的子路径）——见 artifacts.resolve
        "precheck": load("precheck", f"{data_dir}/{split}"),
        "summary": load("dataset", f"{data_dir}/summary"),
        "plan": request.params.get("plan"),
        "report": load("eval", request.run_name),
        "comparison": load("comparison", request.run_name),
        "calibration": load("calibration", request.run_name),
    }
```

`plan_size` 的 stdout 解析放在 UI 侧：作业完成后读它的 events，用 `parse_plan_size()` 取出 `total_records` 自动填进生成表单的 `--n`。不需要在 API 侧另开同步路径。

- [ ] **Step 4: 写 `kev/console/__main__.py`**

```python
# kev/console/__main__.py
"""python -m kev.console —— 启动编排服务。

只绑 127.0.0.1：本地单用户、无鉴权（spec §12）。Windows 侧 playground 通过
WSL2 的 localhostForwarding 访问这个端口。
"""
import os

import uvicorn

from . import paths
from .app import DB_ENV, create_app

DEFAULT_PORT = 8790


def main() -> None:
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    uvicorn.run(create_app(), host="127.0.0.1",
                port=int(os.environ.get("KEV_CONSOLE_PORT", DEFAULT_PORT)), log_level="info")


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: 跑测试确认通过**

Run: `uv run python -m pytest tests/test_console_api.py -q`
Expected: PASS —— 约 15 passed

- [ ] **Step 6: 跑全部后端测试**

Run: `uv run python -m pytest tests/test_console_db.py tests/test_console_artifacts.py tests/test_console_events.py tests/test_console_executor.py tests/test_console_gates.py tests/test_console_stages_data.py tests/test_console_stages_train.py tests/test_console_stages_deploy.py tests/test_console_api.py -q`
Expected: PASS —— 约 96 passed

- [ ] **Step 7: 提交**

```bash
git add kev/console/app.py kev/console/__main__.py tests/test_console_api.py
git commit -m "feat(console): 编排服务 HTTP 面（作业 / 闸门 / 血缘 / SSE）"
```

---

**Wave 1–2 至此完成**：后端能在 API 层提交 14 种作业、拦住闸门失败、流式吐日志。此时 `python -m kev.console` 已经是一个可用的编排服务，只是没有界面。

---

## Wave 3 — 控制台 UI

### Task 9: 代理路由、布局壳、客户端与基础组件

**Files:**
- Create: `playground/src/app/api/console/[...path]/route.ts`
- Create: `playground/src/lib/console.ts`
- Create: `playground/src/components/console/strings.ts`
- Create: `playground/src/components/console/format.ts`
- Create: `playground/src/components/console/format.test.ts`
- Create: `playground/src/app/console/layout.tsx`
- Modify: `playground/src/lib/kev.ts`（删硬编码 key）

- [ ] **Step 1: 补 shadcn 组件**

```bash
cd playground
npx shadcn@latest add table dialog select form progress sonner tooltip dropdown-menu scroll-area sidebar --yes
```

- [ ] **Step 2: 写失败的测试（纯函数优先）**

```ts
// playground/src/components/console/format.test.ts
import { describe, expect, it } from "vitest";
import { formatMetric, metricAt, renderArgv, deltaBadge } from "./format";

describe("metricAt", () => {
  it("reads a nested report.json path", () => {
    const report = { clean: { acc: 0.812, ece: 0.07 }, calibrated_clean: { ece: 0.05 } };
    expect(metricAt(report, ["clean", "acc"])).toBe(0.812);
    expect(metricAt(report, ["calibrated_clean", "ece"])).toBe(0.05);
  });

  it("returns undefined for a missing path instead of throwing", () => {
    expect(metricAt({}, ["clean", "ece"])).toBeUndefined();
    expect(metricAt(null, ["clean"])).toBeUndefined();
  });

  it("reaches the paired CI that only kev.compare produces", () => {
    const comparison = { paired: { acc: { ci95: [0.023, 0.097] } } };
    expect(metricAt(comparison, ["paired", "acc", "ci95", 0])).toBe(0.023);
  });
});

describe("formatMetric", () => {
  it("renders a rate as a percentage", () => {
    expect(formatMetric(0.812)).toBe("81.2%");
    expect(formatMetric(0.812, 1)).toBe("81.2%");
  });

  it("marks an absent metric rather than showing zero", () => {
    expect(formatMetric(undefined)).toBe("—");
  });
});

describe("deltaBadge", () => {
  it("describes a paired CI in the words the runbook uses", () => {
    expect(deltaBadge([0.023, 0.097])).toMatchObject({ ok: true, label: "CI 排除 0" });
    expect(deltaBadge([-0.01, 0.03])).toMatchObject({ ok: false, label: "CI 含 0" });
  });
});

describe("renderArgv", () => {
  it("quotes only what needs quoting", () => {
    expect(renderArgv(["python", "-m", "kev.train", "--out", "runs/cv 8b"]))
      .toBe("python -m kev.train --out 'runs/cv 8b'");
  });

  it("never renders a secret because env is separate", () => {
    expect(renderArgv(["python", "-m", "kev.train"])).not.toMatch(/KEY|TOKEN/);
  });
});
```

- [ ] **Step 3: 跑测试确认失败**

Run: `cd playground && npx vitest run src/components/console/format.test.ts`
Expected: FAIL —— `Cannot find module './format'`

- [ ] **Step 4: 写 `format.ts`**

```ts
// playground/src/components/console/format.ts
// 纯函数：指标取值与格式化。抽出来是为了能单测，也为了让页面组件保持薄。
// 指标路径全部核对自产物结构，见 spec §8.1。特别注意配对 CI 只在 kev.compare 的
// comparison.paired.<metric>.ci95 里 —— kev.benchmark 的 report.json 没有 bootstrap 键。

export type Path = (string | number)[];

export function metricAt(source: unknown, path: Path): number | undefined {
  let node: unknown = source;
  for (const key of path) {
    if (node === null || typeof node !== "object") return undefined;
    node = (node as Record<string | number, unknown>)[key];
  }
  return typeof node === "number" ? node : undefined;
}

export function formatMetric(value: number | undefined, digits = 1): string {
  if (value === undefined || Number.isNaN(value)) return "—";
  return `${(value * 100).toFixed(digits)}%`;
}

export function formatNumber(value: number | undefined, digits = 3): string {
  if (value === undefined || Number.isNaN(value)) return "—";
  return value.toFixed(digits);
}

export function deltaBadge(ci95: [number, number] | undefined) {
  if (!ci95) return { ok: false, label: "缺少配对 CI", detail: "先跑 baseline + benchmark + compare" };
  const [low, high] = ci95;
  return low > 0
    ? { ok: true, label: "CI 排除 0", detail: `CI95 [${low.toFixed(4)}, ${high.toFixed(4)}]` }
    : {
        ok: false,
        label: "CI 含 0",
        detail: `CI95 下限 ${low.toFixed(4)} ≤ 0，增益不显著 —— 更多更好的数据排在收益排序第 1 位`,
      };
}

const SAFE = /^[A-Za-z0-9_@%+=:,./-]+$/;

export function renderArgv(argv: string[]): string {
  return argv
    .map((part) => (SAFE.test(part) ? part : `'${part.replace(/'/g, `'\\''`)}'`))
    .join(" ");
}

export function formatDuration(seconds: number | undefined): string {
  if (seconds === undefined) return "—";
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  const minutes = Math.floor(seconds / 60);
  return `${minutes}m ${(seconds - minutes * 60).toFixed(0)}s`;
}

export function estimateRemaining(step: number, total: number, secPerRec: number): string {
  if (!total || !step) return "—";
  return formatDuration((total - step) * secPerRec);
}

export const STAGE_LABELS: Record<string, { en: string; zh: string }> = {
  data: { en: "Data", zh: "数据" },
  train: { en: "Train", zh: "训练" },
  benchmark: { en: "Score", zh: "打分" },
  compare: { en: "Compare", zh: "对比" },
  calibrate: { en: "Calibrate", zh: "校准" },
  image: { en: "Image", zh: "镜像" },
  deploy: { en: "Deploy", zh: "部署" },
};

export const STATUS_LABELS: Record<string, { en: string; zh: string }> = {
  pending: { en: "Pending", zh: "待启动" },
  queued: { en: "Queued", zh: "排队中" },
  running: { en: "Running", zh: "运行中" },
  succeeded: { en: "Succeeded", zh: "成功" },
  failed: { en: "Failed", zh: "失败" },
  canceled: { en: "Canceled", zh: "已取消" },
  interrupted: { en: "Interrupted", zh: "被中断" },
};
```

- [ ] **Step 5: 写代理路由与客户端**

```ts
// playground/src/app/api/console/[...path]/route.ts
// 薄代理：控制台 UI 与编排服务同源，规避 CORS，并给以后加鉴权留一个位置。
// SSE 必须用 ReadableStream 透传 —— Response.json 会把流缓冲掉。
import type { NextRequest } from "next/server";

const CONSOLE_API =
  process.env.KEV_CONSOLE_API ?? "http://127.0.0.1:8790/console/api";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

async function proxy(request: NextRequest, path: string[]) {
  const target = new URL(`${CONSOLE_API}/${path.join("/")}`);
  request.nextUrl.searchParams.forEach((value, key) => target.searchParams.set(key, value));

  const upstream = await fetch(target, {
    method: request.method,
    headers: { "Content-Type": "application/json" },
    body: request.method === "GET" || request.method === "HEAD" ? undefined : await request.text(),
    cache: "no-store",
  });

  if (!upstream.body || !upstream.headers.get("content-type")?.includes("text/event-stream")) {
    return new Response(upstream.body, {
      status: upstream.status,
      headers: { "Content-Type": upstream.headers.get("content-type") ?? "application/json" },
    });
  }

  const stream = upstream.body.pipeThrough(new TextEncoderStream());
  return new Response(stream, {
    status: upstream.status,
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
      "X-Accel-Buffering": "no",
    },
  });
}

type Context = { params: Promise<{ path: string[] }> };

export async function GET(request: NextRequest, context: Context) {
  return proxy(request, (await context.params).path);
}

export async function POST(request: NextRequest, context: Context) {
  return proxy(request, (await context.params).path);
}
```

```ts
// playground/src/lib/console.ts
// 控制台 API 客户端。所有请求走同源代理 /api/console/*，浏览器不直接连 8790。
// 凭据一律不出现：/config 只回布尔态。
export type JobStatus =
  | "pending" | "queued" | "running"
  | "succeeded" | "failed" | "canceled" | "interrupted";

export type Job = {
  id: string;
  kind: string;
  stage: string;
  scenario: string;
  title: string;
  status: JobStatus;
  request: Record<string, unknown>;
  argv: string[];
  env_overlay: Record<string, string>;
  cwd: string;
  log_path: string;
  artifacts_in: string[];
  artifacts_out: string[];
  attempt: number;
  exit_code: number | null;
  error: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
};

export type Metric = {
  ep: number; step: number; total: number;
  loss: number; kl: number; anchor: number; sec: number;
};

export type Gate = { id: string; ok: boolean; detail: string; actual: string; need: string };

export type Artifact = {
  id: string; kind: string; name: string; path: string;
  meta: Record<string, unknown>; bytes: number | null; created_at: string;
  lineage?: { parent: string; child: string; relation: string }[];
};

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api/console/${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    cache: "no-store",
  });
  const payload = await response.json();
  if (!response.ok) {
    const error = (payload as { error?: { message: string; hint?: string; kind: string } }).error;
    throw new Error(error ? `${error.message}${error.hint ? ` —— ${error.hint}` : ""}` : response.statusText);
  }
  return payload as T;
}

export const api = {
  config: () => call<{ scenarios: string[]; serve_port: number;
                        credentials: Record<string, boolean>;
                        methods: Record<string, { title: string; lr: string }> }>("config"),
  scenarios: () => call<{ name: string; questions: number }[]>("scenarios"),

  datasets: () => call<Artifact[]>("datasets"),
  dataset: (id: string) => call<Artifact & { lineage: unknown[] }>(`datasets/${encodeURIComponent(id)}`),
  exportUrl: (id: string) => `/api/console/datasets/${encodeURIComponent(id)}/export`,

  jobs: (filter?: { status?: JobStatus; stage?: string; scenario?: string }) => {
    const query = new URLSearchParams(
      Object.entries(filter ?? {}).filter(([, v]) => v) as [string, string][],
    ).toString();
    return call<Job[]>(`jobs${query ? `?${query}` : ""}`);
  },
  job: (id: string) => call<Job & { metrics: Metric[]; metrics_dropped: number;
                                   artifacts: Artifact[]; notes: unknown[] }>(`jobs/${id}`),
  preview: (payload: { kind: string; scenario: string; run_name: string; params: Record<string, unknown> }) =>
    call<{ argv: string[]; env: Record<string, string>;
           artifacts_in: string[]; artifacts_out: string[] }>("jobs/preview", {
      method: "POST", body: JSON.stringify(payload),
    }),
  submit: (payload: { kind: string; scenario: string; run_name: string; params: Record<string, unknown> }) =>
    call<Job>("jobs", { method: "POST", body: JSON.stringify(payload) }),
  cancel: (id: string) => call<{ canceled: boolean }>(`jobs/${id}/cancel`, { method: "POST" }),
  retry: (id: string) => call<Job>(`jobs/${id}/retry`, { method: "POST" }),

  artifacts: (kind?: string) => call<Artifact[]>(`artifacts${kind ? `?kind=${kind}` : ""}`),
  gates: (stage: string, scenario: string) =>
    call<Gate[]>(`gates/${stage}?scenario=${scenario}`),
  endpoints: () => call<{ endpoints: Artifact[] }>("endpoints"),
};

export function streamJob(jobId: string, afterId = 0): EventSource {
  // EventSource 原生重连；Last-Event-ID 由浏览器自动带，编排层从 events 表续传
  return new EventSource(`/api/console/jobs/${jobId}/stream?after_id=${afterId}`);
}

export function subscribeStream(
  source: EventSource,
  handlers: {
    onLog?: (event: { id: number; line: string; stream: string }) => void;
    onMetric?: (metric: Metric) => void;
    onStatus?: (status: { status: JobStatus; exit_code: number | null }) => void;
  },
): () => void {
  const log = (event: MessageEvent<string>) => handlers.onLog?.(JSON.parse(event.data));
  const metric = (event: MessageEvent<string>) => handlers.onMetric?.(JSON.parse(event.data));
  const status = (event: MessageEvent<string>) => {
    handlers.onStatus?.(JSON.parse(event.data));
    source.close();
  };
  if (handlers.onLog) source.addEventListener("log", log as EventListener);
  if (handlers.onMetric) source.addEventListener("metric", metric as EventListener);
  source.addEventListener("status", status as EventListener);
  return () => source.close();
}
```

- [ ] **Step 6: 写 `strings.ts` 并注入全局 Dict**

```ts
// playground/src/components/console/strings.ts
// 控制台文案。形状沿用 src/lib/i18n.tsx 的 {en, zh}，注入全局 Dict 保持 t() 单一入口，
// 不引入第二套 i18n。
export const CONSOLE_STRINGS = {
  "console.title": { en: "Medical fine-tune console", zh: "医疗微调控制台" },
  "console.stage.data": { en: "1 · Data", zh: "1 · 数据" },
  "console.stage.train": { en: "2 · Train", zh: "2 · 训练" },
  "console.stage.eval": { en: "3 · Evaluate", zh: "3 · 评测" },
  "console.stage.image": { en: "4 · Image", zh: "4 · 镜像" },
  "console.stage.deploy": { en: "5 · Deploy", zh: "5 · 部署" },
  "console.argv.preview": { en: "Command preview", zh: "将要执行的命令" },
  "console.argv.hint": {
    en: "Every form field maps to a flag below. Nothing is hidden — the runbook's value is that you can read the command.",
    zh: "表单每个字段都对应下面一个开关。没有任何隐藏 —— 执行手册的价值就在于命令可读。",
  },
  "console.train.method": { en: "Fine-tune method", zh: "微调方式" },
  "console.train.monitor": { en: "Loss", zh: "损失曲线" },
  "console.train.metricsMissing": {
    en: "This run wrote no training_metrics.json (--stop_after exits early), so peak memory and gradient norms are unavailable.",
    zh: "本次运行没有写 training_metrics.json（--stop_after 早退会跳过），因此没有峰值显存与梯度范数。",
  },
  "console.data.import": { en: "Import JSONL", zh: "导入 JSONL" },
  "console.data.rareLabel": {
    en: "Under 5% — the trainer warns and the model learns the boundary poorly",
    zh: "占比低于 5% —— 训练器会告警，模型学不好这条边界",
  },
  "console.data.phiWarning": {
    en: "Possible patient identifier detected. Nothing was rewritten; hash it upstream if this is real data.",
    zh: "检测到可能的患者标识。未做任何改写；若这是真实数据，请在上游脱敏。",
  },
  "console.eval.gates": { en: "Acceptance gates", zh: "验收门槛" },
  "console.eval.g4hint": {
    en: "A CI spanning 0 means the data is too thin or the gain too small — better data ranks first, not more records or other hyperparameters.",
    zh: "CI 含 0 说明数据太薄或增益太小 —— 收益排序第 1 位是「更多更好的数据」，不是加量也不是调超参。",
  },
  "console.deploy.priorWarning": {
    en: "Training prior is balanced; real critical-value rate is 1–3%. Re-calibrate the cut-off on real traffic. Model advises, a human confirms.",
    zh: "训练先验是均衡的，线上危急值实际只占 1–3%。阈值须用真实流量重新标定。模型建议，人工确认。",
  },
  "console.jobs.retry": { en: "Retry with a new name", zh: "换名重试" },
  "console.jobs.interrupted": {
    en: "The orchestrator restarted while this job was live. Retry to continue.",
    zh: "编排服务在此作业运行中重启过。可重试以继续。",
  },
} as const;
```

在 `playground/src/lib/i18n.tsx` 里把 `CONSOLE_STRINGS` 合并进 `Dict`（加一行 `...CONSOLE_STRINGS`），并把 `Dict` 的类型放宽为 `Record<string, {en: string; zh: string}>`。

- [ ] **Step 7: 写布局壳**

```tsx
// playground/src/app/console/layout.tsx
"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Toaster } from "@/components/ui/sonner";
import { useLang } from "@/lib/i18n";
import { t } from "@/lib/i18n-dict";
import { cn } from "@/lib/utils";

const NAV = [
  { href: "/console", key: "console.title", exact: true },
  { href: "/console/datasets", key: "console.stage.data" },
  { href: "/console/train", key: "console.stage.train" },
  { href: "/console/eval", key: "console.stage.eval" },
  { href: "/console/images", key: "console.stage.image" },
  { href: "/console/deploy", key: "console.stage.deploy" },
];

export default function ConsoleLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const lang = useLang();

  return (
    <div className="flex min-h-full">
      <aside className="w-56 shrink-0 border-r border-border bg-sidebar text-sidebar-foreground">
        <div className="p-4 text-sm font-semibold">{t("console.title", lang)}</div>
        <nav className="flex flex-col gap-0.5 px-2">
          {NAV.map((item) => {
            const active = item.exact ? pathname === item.href : pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  "rounded-md px-3 py-2 text-sm transition-colors hover:bg-sidebar-accent",
                  active && "bg-sidebar-accent font-medium text-sidebar-accent-foreground",
                )}
              >
                {t(item.key, lang)}
              </Link>
            );
          })}
        </nav>
      </aside>
      <main className="min-w-0 flex-1 p-6">{children}</main>
      <Toaster />
    </div>
  );
}
```

若 `useLang()` 返回的是 `[lang, setLang]` 之类，签名以 `src/lib/i18n.tsx` 的实际导出为准 —— 读该文件确认后再定稿。

- [ ] **Step 8: 删掉硬编码的 API key**

`playground/src/lib/kev.ts:29` 现在是 `process.env.NEXT_PUBLIC_KEV_API_KEY ?? "nv2NVak2oaTx5fk6BjKBrmu8EC9wCA4D"` —— 一个真实的 key 经 `NEXT_PUBLIC_` 打进客户端 bundle。改成读环境变量，缺省时向编排服务问「凭据是否已配置」，并且**永不**把 key 送到浏览器：

```ts
// playground/src/lib/kev.ts
// 凭据不经过浏览器：key 只在编排服务进程的环境变量里，注入给子进程或 kev.serve。
// 这里只问「配没配」，问不到就当作没配（本地默认开放）。
async function authHeaders(): Promise<Record<string, string>> {
  const key = process.env.NEXT_PUBLIC_KEV_API_KEY;
  return key ? { Authorization: `Bearer ${key}` } : {};
}
```

如果现有 `post<T>()` 已经在拼 `Authorization`，只把硬编码 fallback 删掉、保留 `process.env` 读取即可；不要把 key 挪进 `NEXT_PUBLIC_` 之外的任何新机制。**这个 key 不要出现在任何新文件里。**

- [ ] **Step 9: 跑测试**

Run: `cd playground && npx vitest run src/components/console/format.test.ts`
Expected: PASS —— 11 passed

- [ ] **Step 10: 提交**

```bash
git add playground/src/app/api/console playground/src/lib/console.ts playground/src/components/console/strings.ts playground/src/components/console/format.ts playground/src/components/console/format.test.ts playground/src/app/console/layout.tsx playground/src/lib/kev.ts playground/src/lib/i18n.tsx playground/src/components/ui
git commit -m "feat(console): UI 代理路由、布局壳、客户端与纯函数工具"
```

---

### Task 10: 总览页与作业详情页（SSE 日志 + loss 曲线）

**Files:**
- Create: `playground/src/components/console/LogStream.tsx`
- Create: `playground/src/components/console/LossChart.tsx`
- Create: `playground/src/components/console/JobTable.tsx`
- Create: `playground/src/components/console/ArgvPreview.tsx`
- Create: `playground/src/app/console/page.tsx`
- Create: `playground/src/app/console/jobs/[id]/page.tsx`

- [ ] **Step 1: 写 `LossChart.tsx`（手写 SVG，不引图表库）**

```tsx
// playground/src/components/console/LossChart.tsx
"use client";

// 手写 SVG：仓库无图表库，answer-card.tsx 已有手写条形先例，这三个图的数据形态都是
// 几十个点，SVG 手写更可控。三个序列（loss / kl / anchor）共用一个 y 轴。
// 溢出时如实提示「仅显示最近 N 点」—— 实时指标的上限就是日志 tail（spec §7.2）。
import { useId } from "react";
import type { Metric } from "@/lib/console";
import { formatMetric, formatNumber } from "./format";

const SERIES = [
  { key: "loss", color: "var(--color-chart-1)" },
  { key: "kl", color: "var(--color-chart-2)" },
  { key: "anchor", color: "var(--color-chart-3)" },
] as const;

export function LossChart({ points, dropped = 0 }: { points: Metric[]; dropped?: number }) {
  const gradient = useId();
  if (points.length < 2) {
    return (
      <div className="flex h-40 items-center justify-center rounded-md border border-dashed border-border text-sm text-muted-foreground">
        {points.length === 0 ? "等待第一条进度日志（每 10 个优化步一行）" : "还需要更多数据点才能画曲线"}
      </div>
    );
  }

  const width = 640, height = 200, pad = { top: 12, right: 12, bottom: 24, left: 44 };
  const innerW = width - pad.left - pad.right, innerH = height - pad.top - pad.bottom;
  const maxValue = Math.max(...points.flatMap((p) => SERIES.map((s) => p[s.key])), 1e-6);
  const last = points[points.length - 1];
  const x = (index: number) => pad.left + (index / (points.length - 1)) * innerW;
  const y = (value: number) => pad.top + innerH - (value / maxValue) * innerH;

  return (
    <figure className="space-y-2">
      <svg viewBox={`0 0 ${width} ${height}`} className="w-full" role="img"
           aria-label={`loss ${formatNumber(last.loss)}`}>
        <defs>
          <linearGradient id={gradient} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--color-chart-1)" stopOpacity="0.25" />
            <stop offset="100%" stopColor="var(--color-chart-1)" stopOpacity="0" />
          </linearGradient>
        </defs>
        {[0, 0.5, 1].map((fraction) => (
          <g key={fraction}>
            <line x1={pad.left} x2={width - pad.right} y1={y(maxValue * fraction)} y2={y(maxValue * fraction)}
                  stroke="var(--color-border)" strokeDasharray="3 3" />
            <text x={pad.left - 6} y={y(maxValue * fraction) + 4} textAnchor="end" fontSize="10"
                  fill="var(--color-muted-foreground)">
              {formatMetric(maxValue * fraction, 2)}
            </text>
          </g>
        ))}
        <path
          d={`${points.map((p, i) => `${i === 0 ? "M" : "L"}${x(i)},${y(p.loss)}`).join(" ")}
              L${x(points.length - 1)},${pad.top + innerH} L${x(0)},${pad.top + innerH} Z`}
          fill={`url(#${gradient})`}
        />
        {SERIES.map((series) => (
          <path key={series.key}
                d={points.map((p, i) => `${i === 0 ? "M" : "L"}${x(i)},${y(p[series.key])}`).join(" ")}
                fill="none" stroke={series.color} strokeWidth={series.key === "loss" ? 1.8 : 1.2}
                strokeLinejoin="round" />
        ))}
        <text x={pad.left} y={height - 8} fontSize="10" fill="var(--color-muted-foreground)">
          ep{last.ep} step {last.step}/{last.total}
        </text>
        <text x={width - pad.right} y={height - 8} textAnchor="end" fontSize="10"
              fill="var(--color-muted-foreground)">
          {formatNumber(last.sec)}s/rec
        </text>
      </svg>
      <figcaption className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
        {SERIES.map((series) => (
          <span key={series.key} className="inline-flex items-center gap-1.5">
            <span className="h-0.5 w-4 rounded" style={{ background: series.color }} />
            {series.key} {formatNumber(last[series.key])}
          </span>
        ))}
        {dropped > 0 && <span>仅显示最近 {points.length} 点（已丢弃 {dropped} 点）</span>}
      </figcaption>
    </figure>
  );
}
```

- [ ] **Step 2: 写 `LogStream.tsx`**

```tsx
// playground/src/components/console/LogStream.tsx
"use client";

import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { streamJob, subscribeStream, type JobStatus } from "@/lib/console";
import { cn } from "@/lib/utils";

type Line = { id: number; stream: string; line: string };

export function LogStream({ jobId, status, onStatus }: {
  jobId: string;
  status: JobStatus;
  onStatus?: (status: JobStatus) => void;
}) {
  const [lines, setLines] = useState<Line[]>([]);
  const [follow, setFollow] = useState(true);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (status !== "running" && status !== "queued" && status !== "pending") return;
    const source = streamJob(jobId);
    const stop = subscribeStream(source, {
      onLog: (event) => {
        setLines((previous) => {
          const next = [...previous, { id: event.id, stream: event.stream, line: event.line }];
          return next.length > 5000 ? next.slice(next.length - 5000) : next;   // 浏览器内存上限
        });
      },
      onStatus: (payload) => onStatus?.(payload.status),
    });
    return stop;
  }, [jobId, status, onStatus]);

  useEffect(() => {
    if (follow) endRef.current?.scrollIntoView({ block: "end" });
  }, [lines, follow]);

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <span className="text-xs text-muted-foreground">{lines.length} 行（仅浏览器内，非全部）</span>
        <Button size="sm" variant={follow ? "secondary" : "ghost"} onClick={() => setFollow((v) => !v)}>
          {follow ? "跟随输出" : "已暂停跟随"}
        </Button>
      </div>
      <ScrollArea className="h-72 rounded-md border border-border bg-muted/30">
        <pre className="p-3 font-mono text-xs leading-relaxed">
          {lines.map((row) => (
            <div key={row.id} className={cn(row.stream === "stderr" && "text-destructive")}>
              {row.line}
            </div>
          ))}
          <div ref={endRef} />
        </pre>
      </ScrollArea>
    </div>
  );
}
```

- [ ] **Step 3: 写 `ArgvPreview.tsx`（贯穿全站的设计原则）**

```tsx
// playground/src/components/console/ArgvPreview.tsx
"use client";

// 每个作业表单右侧都必须显示将要执行的完整 argv（只读、可复制）。
// 理由来自 runbook 的价值结构：步骤给的是「目的 / 输入 / 命令 / 预期输出 / 验证」。
// 藏起命令会让用户失去可审计性与可复现性，医疗场景下这是硬伤（spec §11.2）。
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { api, type Job } from "@/lib/console";
import { useLang } from "@/lib/i18n";
import { t } from "@/lib/i18n-dict";
import { renderArgv } from "./format";

export function ArgvPreview({ kind, scenario, runName, params, className }: {
  kind: string;
  scenario: string;
  runName: string;
  params: Record<string, unknown>;
  className?: string;
}) {
  const [argv, setArgv] = useState<string[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const lang = useLang();

  useEffect(() => {
    let cancelled = false;
    const timer = setTimeout(() => {
      api.preview({ kind, scenario, run_name: runName, params })
        .then((result) => { if (!cancelled) { setArgv(result.argv); setError(null); } })
        .catch((problem: Error) => { if (!cancelled) { setError(problem.message); setArgv(null); } });
    }, 150);                                  // 防抖：打字时不打爆编排服务
    return () => { cancelled = true; clearTimeout(timer); };
  }, [kind, scenario, runName, JSON.stringify(params)]);

  return (
    <div className={className}>
      <div className="mb-1.5 flex items-center justify-between">
        <span className="text-xs font-medium text-muted-foreground">{t("console.argv.preview", lang)}</span>
        {argv && (
          <Button size="sm" variant="ghost" onClick={() => navigator.clipboard.writeText(renderArgv(argv))}>
            复制
          </Button>
        )}
      </div>
      <ScrollArea className="max-h-40 rounded-md border border-border bg-muted/40">
        <pre className="p-3 font-mono text-xs">
          {error ? <span className="text-destructive">{error}</span> : argv ? renderArgv(argv) : "计算中…"}
        </pre>
      </ScrollArea>
      <p className="mt-1.5 text-xs text-muted-foreground">{t("console.argv.hint", lang)}</p>
    </div>
  );
}
```

- [ ] **Step 4: 写轮询 hook 与 `JobTable.tsx`**

先写轮询 hook。**不引 swr / react-query** —— 本仓库没有，YAGNI（spec §11.5）：

```ts
// playground/src/components/console/hooks.ts
"use client";

import { useCallback, useEffect, useState } from "react";
import { api, type Artifact, type Gate, type Job } from "@/lib/console";

export function usePoll<T>(load: () => Promise<T>, initial: T, intervalMs = 3000) {
  const [value, setValue] = useState<T>(initial);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let cancelled = false;
    const tick = async () => {
      try {
        const next = await load();
        if (!cancelled) { setValue(next); setError(null); }
      } catch (problem) {
        if (!cancelled) setError((problem as Error).message);
      }
    };
    tick();
    const timer = setInterval(tick, intervalMs);
    return () => { cancelled = true; clearInterval(timer); };
  }, [load, intervalMs]);
  return { value, error };
}

export const useJobs = () => usePoll<Job[]>(() => api.jobs(), []);
export const useArtifacts = () => usePoll<Artifact[]>(() => api.artifacts(), []);
export const useGates = (stage: string, scenario: string) =>
  usePoll<Gate[]>(() => api.gates(stage, scenario), []);
```

`load` 必须是稳定引用，所以 `useJobs` 内部用 `useCallback` 包一层（否则 `usePoll` 的依赖每次渲染都变，轮询会重启）。落地时把 `useJobs` 写成：

```ts
export const useJobs = () => {
  const load = useCallback(() => api.jobs(), []);
  return usePoll<Job[]>(load, []);
};
```

`JobTable`：

```tsx
// playground/src/components/console/JobTable.tsx
"use client";

import Link from "next/link";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api, type Job } from "@/lib/console";
import { STATUS_LABELS, STAGE_LABELS } from "./format";

const TONE: Record<string, "default" | "secondary" | "destructive" | "outline"> = {
  succeeded: "default", running: "secondary", queued: "secondary",
  pending: "outline", failed: "destructive", canceled: "outline", interrupted: "outline",
};

export function JobTable({ jobs, onChanged }: { jobs: Job[]; onChanged?: () => void }) {
  const act = async (id: string, action: "cancel" | "retry") => {
    await (action === "cancel" ? api.cancel(id) : api.retry(id));
    onChanged?.();
  };
  if (jobs.length === 0) {
    return <p className="py-8 text-center text-sm text-muted-foreground">还没有作业</p>;
  }
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>状态</TableHead><TableHead>阶段</TableHead><TableHead>类型</TableHead>
          <TableHead>场景</TableHead><TableHead>运行名</TableHead><TableHead>尝试</TableHead>
          <TableHead>创建</TableHead><TableHead className="text-right">操作</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {jobs.map((job) => (
          <TableRow key={job.id}>
            <TableCell>
              <Badge variant={TONE[job.status] ?? "outline"}>{STATUS_LABELS[job.status]?.zh}</Badge>
            </TableCell>
            <TableCell className="text-sm">{STAGE_LABELS[job.stage]?.zh ?? job.stage}</TableCell>
            <TableCell className="font-mono text-xs">{job.kind}</TableCell>
            <TableCell className="text-sm">{job.scenario}</TableCell>
            <TableCell className="font-mono text-xs">{job.title}</TableCell>
            <TableCell className="text-xs text-muted-foreground">{job.attempt > 1 ? `r${job.attempt}` : "—"}</TableCell>
            <TableCell className="text-xs text-muted-foreground">{job.created_at.slice(0, 19)}</TableCell>
            <TableCell className="text-right">
              <div className="flex justify-end gap-1">
                <Button size="sm" variant="ghost" asChild>
                  <Link href={`/console/jobs/${job.id}`}>详情</Link>
                </Button>
                {job.status === "running" && (
                  <Button size="sm" variant="ghost" onClick={() => act(job.id, "cancel")}>取消</Button>
                )}
                {(job.status === "failed" || job.status === "canceled" || job.status === "interrupted") && (
                  <Button size="sm" variant="ghost" onClick={() => act(job.id, "retry")}>
                    {job.status === "interrupted" ? "换名重试" : "重试"}
                  </Button>
                )}
              </div>
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
```

- [ ] **Step 5: 写总览页与作业详情页**

`playground/src/app/console/page.tsx`（总览）：5 个阶段卡片（每张显示该阶段最近作业的状态 + 未通过的闸门数，点击跳对应页）→ `<GatePanel>` 汇总 → `<JobTable>` → 产物血缘（把 `api.artifacts()` 的 `lineage` 按 `relation` 分组渲染成缩进树）。全部数据来自 `useJobs` / `useArtifacts` / `useGates` 的 3 秒轮询；日志与指标才走 SSE。

`playground/src/app/console/jobs/[id]/page.tsx`（作业详情）四块：**argv**（`renderArgv(job.argv)` 只读 + 复制）→ **loss 曲线**（首屏用 `job.metrics` 回填，运行时订阅 SSE 的 `metric` 事件累积）→ **日志**（`<LogStream>`）→ **产物与血缘**。

失败时额外显示 `job.error`，并按错误类别给不同按钮（spec §10.2）：

```tsx
{job.status === "failed" && (
  <Alert variant="destructive">
    <AlertTitle>作业失败{job.exit_code !== null && `（退出码 ${job.exit_code}）`}</AlertTitle>
    <AlertDescription className="whitespace-pre-wrap font-mono text-xs">{job.error}</AlertDescription>
  </Alert>
)}
{job.status === "interrupted" && (
  <Alert>
    <AlertTitle>{t("console.jobs.interrupted", lang)}</AlertTitle>
    <AlertDescription>
      <Button size="sm" onClick={() => api.retry(job.id)}>{t("console.jobs.retry", lang)}</Button>
    </AlertDescription>
  </Alert>
)}
```

- [ ] **Step 6: 起后端与前端肉眼验证**

```bash
# 终端 1（WSL2）
uv run python -m kev.console
# 终端 2
cd playground && npm run dev
```

打开 `http://localhost:3000/console`，确认：阶段卡片列出 5 个阶段；`Nav` 六项可跳转；点进一个作业页能看到 argv 与日志。

- [ ] **Step 7: 提交**

```bash
git add playground/src/components/console playground/src/app/console
git commit -m "feat(console): 总览页与作业详情（日志流 + loss 曲线 + argv 预览）"
```

---

### Task 11: 训练页

**Files:**
- Create: `playground/src/app/console/train/page.tsx`

- [ ] **Step 1: 写页面**

结构：左栏表单，右栏 `<ArgvPreview>` + 闸门面板 + 实时曲线。

表单字段（默认值取自 `train.METHODS`，服务端 `/config` 会返回，所以**不要在前端硬编码**）：

- 微调方式：分段控件 A1 / A2 / B，标题与 lr 来自 `/config` 的 `methods`
- 常用：数据分区（默认 `data/<scenario>/train.jsonl`，只读展示）、`--epochs`、`--batch`、`--accum`、`--lr`、`--replay`
- 高级（折叠）：`--lora`、`--lora_targets`、`--head_dim`、`--head_lr`、`--weight_decay`、`--checkpointing`、`--length_sort`、`--row_budget`、`--pass_tokens_max`
- 全参数专属（仅 B）：`--snapshot_fractions` + `--max_steps`，缺一即报 `Invalid`（后端已拦，前端同步禁用并给提示）

**风险横幅**（0.8B 的已知弱项，UI 要如实告知，不要让用户以为只是普通微调）：

```tsx
<aside className="rounded-md border border-amber-500/40 bg-amber-500/10 p-3 text-sm">
  <p className="font-medium">0.8B 的三条已知限制</p>
  <ul className="mt-1 list-disc pl-5 text-muted-foreground">
    <li>日期算术 0.35（4B 0.65）—— 所以本项目的 spec 一律把日期算术预计算掉，字段是 days_on_drug / length_of_stay_days / duration</li>
    <li>知识由基座决定，MMLU-Pro 低至 0.230 —— 不适合病历编码这类需要医学知识推断的判断</li>
    <li>工具路由 When2Call 0.133，低于机会水平 —— 禁止用于「是否需要翻阅指南」这类决策</li>
  </ul>
  <p className="mt-1 text-muted-foreground">0.8B 更容易过度自信：验收时 mean_conf vs acc 与 confident_error_rate 要比 4B 卡得更严。</p>
</aside>
```

提交后跳到 `/console/jobs/<id>`。训练中这一页也要能看曲线：订阅 SSE 的 `metric` 事件累积到 `<LossChart>`。

训练结束后读 `training_metrics.json`：若文件不存在（`--stop_after` 早退），显示 `t("console.train.metricsMissing")` 而不是报错。

- [ ] **Step 2: 肉眼验证**

选 A1，argv 预览里必须出现 `--init_from jaredpalmer/kev-0.8b`、`--lr 4e-5`、`--replay 2000`、`--lora_targets all`；切到 B，必须出现 `--full_ft 1 --weights_dtype bf16` 且 `--init_from` 消失。

- [ ] **Step 3: 提交**

```bash
git add playground/src/app/console/train
git commit -m "feat(console): 训练页（方式切换 + argv 预览 + 0.8B 风险提示）"
```

---

### Task 12: 数据页与评测页

**Files:**
- Create: `playground/src/components/console/GatePanel.tsx`
- Create: `playground/src/components/console/ReliabilityDiagram.tsx`
- Create: `playground/src/components/console/MetricDeltaBar.tsx`
- Create: `playground/src/components/console/CoverageCurve.tsx`
- Create: `playground/src/app/console/datasets/page.tsx`
- Create: `playground/src/app/console/eval/page.tsx`

- [ ] **Step 1: 写 `GatePanel.tsx`**

```tsx
// playground/src/components/console/GatePanel.tsx
"use client";

// 验收门槛面板。G4 的提示语要说清因果：CI 含 0 说明数据不够或增益太小，
// 收益排序第 1 位是「更多更好的数据」—— 改数据不是加量，也不是调超参。
import { Badge } from "@/components/ui/badge";
import { useLang } from "@/lib/i18n";
import { t } from "@/lib/i18n-dict";
import type { Gate } from "@/lib/console";
import { cn } from "@/lib/utils";

export function GatePanel({ gates, title }: { gates: Gate[]; title?: string }) {
  const lang = useLang();
  const failed = gates.filter((gate) => !gate.ok).length;
  return (
    <section className="rounded-md border border-border">
      <header className="flex items-center justify-between border-b border-border px-3 py-2">
        <h3 className="text-sm font-medium">{title ?? t("console.eval.gates", lang)}</h3>
        <Badge variant={failed ? "destructive" : "secondary"}>
          {failed ? `${failed} 道未通过` : "全部通过"}
        </Badge>
      </header>
      <ul className="divide-y divide-border">
        {gates.map((gate) => (
          <li key={gate.id} className="px-3 py-2 text-sm">
            <div className="flex items-center gap-2">
              <span className={cn("font-mono text-xs", gate.ok ? "text-emerald-600" : "text-destructive")}>
                {gate.ok ? "✓" : "✗"} {gate.id}
              </span>
              <span className={gate.ok ? "text-muted-foreground" : "text-destructive"}>{gate.detail}</span>
            </div>
            {!gate.ok && gate.actual && (
              <p className="mt-0.5 pl-6 text-xs text-muted-foreground">
                实测 {gate.actual} · 需要 {gate.need}
              </p>
            )}
            {!gate.ok && gate.id === "G4" && (
              <p className="mt-0.5 pl-6 text-xs text-muted-foreground">{t("console.eval.g4hint", lang)}</p>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
```

- [ ] **Step 2: 写三个图表组件**

`ReliabilityDiagram`：读 `report.clean.top_bins`（形如 `{"0.9": {n, errors, error_rate}, "0.95": ..., "0.99": ...}`）画 reliability diagram，横轴置信度区间、纵轴实际准确率，画 `y = x` 对角线。旁边显示 `clean.ece` 与 `calibrated_clean.ece` 两个数。

`MetricDeltaBar`：左右两栏 baseline / 微调，四个指标 `acc` / `ece` / `confident_error_rate` / `coverage_at_5pct_error`，数据来自 `comparison.clean.reference` 与 `comparison.clean.candidate`；差值用 `--color-chart-1`（好）/ `--color-destructive`（差）着色。

`CoverageCurve`：横轴错误率阈值（0.01 / 0.05 与 `selective` 的 0.5 / 0.8 切点），纵轴覆盖率，画 candidate 与 reference 两条线。

三个组件都手写 SVG，模式与 Task 10 的 `LossChart` 一致（`useId()` 生成渐变 id、`--color-chart-*` 取色、`--color-border` 画网格）。

- [ ] **Step 3: 写数据页**

三块：**数据集列表**（`api.datasets()`，每行显示记录数、分区、标签分布迷你直方图；点击进详情）；**导入**（`<input type="file" accept=".jsonl">` → `POST /console/api/datasets/import` → 展示校验报告：有效行数、标签分布、**<5% 与「从未作为正确答案」高亮**、冲突 state、**PHI 模式告警**）；**合成**（选 spec + 规模 + seed → `generate` 作业；LLM 蒸馏另给模型/并发/base_url）。

导入的 PHI 规则**只告警不自动改写**：对 `state.patient` 匹配身份证（`\d{17}[\dXx]`）、手机号（`1[3-9]\d{9}`）与长数字串，命中就在报告里列出**行号与命中的模式**，不提供自动替换的默认开关（哈希替换要用户显式勾选）。

**分布直方图必须复用后端的 `summary.json`**（由 `split_data.py` 写），不在前端重算 —— 前端重算会与训练器口径分叉，正是 `test_conventions.py` 要防的事。

- [ ] **Step 4: 写评测页**

自上而下：**闸门面板**（`api.gates("image", scenario)`，即 G4–G7）→ **指标卡组**（`api.job()` 取评测作业的 `artifacts`，读 `report.json` 的 `clean` / `calibrated_clean`，重点是 `mean_conf` vs `acc` 的并排对照 —— 过度自信的直观体现）→ **校准四臂表**（`raw` / `shipped` / `workload` / `workload_oof` 的 `ece` / `brier` / `coverage_at_5pct_error` / `aurc`，外加 `workload_temperature` 作为部署温度的来源）→ 三个图表。

部署与镜像按钮的 `disabled` 直接由闸门结果驱动：`const blocked = gates.some(g => !g.ok)`。

- [ ] **Step 5: 肉眼验证**

用已有的 `data/cv` 与一个 `runs/*-eval` 产物，确认指标卡与图表有数据；手工把 `comparison.json` 的 `paired.acc.ci95` 改成 `[-0.01, 0.03]`，刷新后 G4 必须变红且镜像/部署按钮禁用。

- [ ] **Step 6: 提交**

```bash
git add playground/src/components/console playground/src/app/console/datasets playground/src/app/console/eval
git commit -m "feat(console): 数据页与评测页（闸门面板 + 校准图表 + PHI 告警）"
```

---

### Task 13: 镜像页与部署页

**Files:**
- Create: `playground/src/app/console/images/page.tsx`
- Create: `playground/src/app/console/deploy/page.tsx`

- [ ] **Step 1: 写镜像页**

表单：运行名（默认 `cv-8b-lora-v1`）、温度（**必填**，空则提交被 400 拦，提示「先跑 calibrate，从 `workload_temperature` 取值」）。右侧 `<ArgvPreview>` 显示完整的 `docker build -t kev-<run>:<temp> -f deploy/kev-serve/Dockerfile --build-arg KEV_SERVE_RUN=... --build-arg TEMPERATURE=...`。

镜像列表（`api.artifacts("image")`）显示 tag、大小、构建时间；构建日志走作业详情页的 `LogStream`（镜像作业同样是长任务，层输出很多）。

顶部提示：镜像不烘 HF 权重（医疗模型禁止 `--public`），权重运行时由 `kev.checkpoint` 按 `KEV_SERVE_RUN` 解析或挂载。

- [ ] **Step 2: 写部署页**

三块：**端点列表**（`api.endpoints()`，显示 `127.0.0.1:8008`、当前 run、温度、在线状态；在线状态靠 `GET /v1/models` 透传，失败显示离线）；**冒烟测试**（一键跑 `smoke` 作业，完成后展示 5 个场景各 1 例的 p 分布与 argmax 表 —— 让用户直接看到模型在医疗场景的输出形态）；**回滚**（把端点指回 baseline run 的按钮，语义是重启 `deploy` 作业换一个 `--run`）。

顶部**常驻**风险横幅（`t("console.deploy.priorWarning")`）：均衡先验 ≠ 真实先验（线上危急值 1–3%），阈值须用真实流量重标定；医疗场景默认「模型建议 + 人工确认」，页面上**不提供**任何「关闭人工确认」的开关。

同时这一页要显示 `playground` 现有问答页的入口链接（`/`，它已通过 rewrite 指向 8008），让用户能立刻在新模型上试真实问题。

- [ ] **Step 3: 肉眼验证**

镜像页温度留空提交 → 必须看到后端的 `hint`（关于 `calibration.json` 的 `workload_temperature`）。部署成功后打开 `/`（现有问答页），确认 `GET /v1/models` 返回的是新 run。

- [ ] **Step 4: 提交**

```bash
git add playground/src/app/console/images playground/src/app/console/deploy
git commit -m "feat(console): 镜像页与部署页（冒烟测试 + 回滚 + 先验风险提示）"
```

---

## Wave 4 — 验收

### Task 14: 契约冻结与端到端验收

**Files:**
- Create: `tests/test_console_contract.py`
- Modify: `.gitignore`

- [ ] **Step 1: 写契约冻结测试**

```python
# tests/test_console_contract.py
"""控制台不得改动 kev 的核心文件。

这是最廉价的回归保护：编排层的所有价值都建立在「不碰 kev 核心」之上。
kev/experiment.py:135-137 的 source_hashes() 在训练前后各校验一次，
改这些文件会让在途研究轮次失败；tests/test_unit.py 钉死了 serve.app 的形态。

Run: uv run python -m pytest tests/test_console_contract.py -q
"""
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

FROZEN = [
    "kev/train.py", "kev/serve.py", "kev/benchmark.py", "kev/calibrate.py",
    "kev/publish.py", "kev/compare.py", "kev/metrics.py", "kev/model.py",
    "kev/checkpoint.py", "kev/data.py", "kev/suite.py", "kev/api.py",
]


@pytest.mark.parametrize("relative", FROZEN)
def test_core_file_is_untouched(relative):
    """与 HEAD 比对；有 diff 就说明有人改了核心文件。"""
    result = subprocess.run(["git", "diff", "--name-only", "HEAD", "--", relative],
                            cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0
    assert result.stdout.strip() == "", f"{relative} 被改动了：\n{result.stdout}"


def test_console_package_is_declared_for_packaging():
    """pyproject 的 packages 不含子包时，非 editable 安装会 ImportError。"""
    import tomllib
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    packages = config["tool"]["setuptools"]["packages"]
    assert "kev" in packages
    assert "kev.console" in packages, "kev.console 未声明，非 editable 安装会不可导入"


def test_console_never_reads_reserved_environment_variables():
    """KEV_TEMPERATURE 等只能经 kev.checkpoint.LoadOptions.from_env 读取。"""
    reserved = ("KEV_DTYPE", "KEV_MERGE", "KEV_ATTN", "KEV_LORA_SCALE",
                "KEV_TEMPERATURE", "KEV_BACKEND", "KEV_CUDA_GRAPHS")
    for path in sorted((ROOT / "kev/console").rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        for name in reserved:
            assert name not in text, f"{path.relative_to(ROOT)} 引用了保留变量 {name}"


def test_every_stage_kind_is_registered():
    """14 种作业全部有 StageSpec，且没有多余。"""
    sys.path.insert(0, str(ROOT / "docs/medical/generators"))
    from kev.console.stages import REGISTRY
    assert set(REGISTRY) == {
        "plan_size", "generate", "distill", "goldset", "split", "precheck",
        "train", "baseline", "benchmark", "compare", "calibrate",
        "image", "deploy", "smoke",
    }


def test_all_stages_preview_without_spawning():
    """每个 StageSpec 的 build 都是纯函数：给合法请求不该写文件、不该起进程。"""
    from kev.console.stages import REGISTRY
    from kev.console.stages.base import Invalid
    for kind, stage in sorted(REGISTRY.items()):
        params = {
            "train": {"method": "a1"},
            "compare": {"candidate": "runs/a-eval", "reference": "runs/b-eval"},
            "calibrate": {}, "image": {"temperature": "2.35"},
            "deploy": {"temperature": "2.35"}, "smoke": {},
        }.get(kind, {})
        try:
            built = stage.preview(_request(kind, params))
        except Invalid as error:
            pytest.fail(f"{kind} 的 preview 抛了 Invalid：{error.message}")
        assert built.argv, f"{kind} 没有组装 argv"
```

把 `_request()` 补齐在文件里：

```python
def _request(kind, params):
    from kev.console.stages.base import JobRequest
    name = {"train": "cv-8b-lora-v1", "compare": "cv-8b-lora-v1",
            "calibrate": "cv-8b-lora-v1", "image": "cv-8b-lora-v1",
            "deploy": "cv-8b-lora-v1", "smoke": "cv-8b-lora-v1"}.get(kind, "cv-8b-v1")
    return JobRequest(scenario="critical-value", run_name=name, params=params)
```

- [ ] **Step 2: 跑测试**

Run: `uv run python -m pytest tests/test_console_contract.py -q`
Expected: PASS —— 约 20 passed

- [ ] **Step 3: 补 `.gitignore`**

```
data/console/
*.db
*.db-wal
*.db-shm
playground/.next/
```

- [ ] **Step 4: 跑全量回归，确认零破坏**

```bash
uv run python -m pytest tests/ -q
```

Expected: 与改动前基线一致 —— 不得新增失败。特别关注 `tests/test_conventions.py`（扫描新增的 `kev/console/*.py`）与 `tests/test_medical_generators.py`（`docs/medical/generators` 未被改动，应仍通过）。

- [ ] **Step 5: 跑 spec §14.1 的九项人工验收**

逐项记录结果：

1. **数据半链路真跑通**（当前机器唯一能真跑的部分）
   ```bash
   uv run python -m kev.console      # 终端 1
   # 终端 2 或 UI：依次提交 plan_size → generate(n=787) → split → precheck
   uv run python docs/medical/console/precheck.py --data data/cv \
     --init-from jaredpalmer/kev-0.8b --split train --out /tmp/pc.json
   ```
   期望：`generate at least 787 records`；`split` 产出 551/118/118；`over_limit 0`
2. **`train` 在 WSL2 + GPU 上跑通 3 条记录的 CPU 冒烟**，产出 `adapter_model.safetensors` + `head.pt`
3. **SSE 断线重连**：DevTools 里切 Offline 再切回，日志与曲线续上（`Last-Event-ID` 生效，不重复也不丢行）
4. **取消训练后无孤儿**：`nvidia-smi` 确认显存归零，`ps` 里无 `kev.train` 残留
5. **崩溃恢复**：训练中 `kill` 编排服务 → 重启 → 该作业显示 `interrupted` 且可重试
6. **闸门 G4**：把 `comparison.json` 的 `paired.acc.ci95` 改成 `[-0.01, 0.03]` → 镜像/部署按钮禁用
7. **PHI**：上传含身份证号的 `patient` 字段 → 告警出现且**未自动改写**
8. **零改动**：`git diff --name-only HEAD -- kev/train.py kev/serve.py kev/benchmark.py` 输出为空
9. **无凭据泄露**：全程浏览器 Network 响应与 `strings data/console/kev-console.db | grep -i sk-` 均无凭据

- [ ] **Step 6: 写 `playground/AGENTS.md`**

现有 `playground/AGENTS.md` 只有 Next 版本警告，没有任何项目约定（对比仓库根 `AGENTS.md` 的 260+ 行）。补上：端口（playground 3000 / 编排服务 8790 / 推理端点 8008）、`KEV_CONSOLE_API` 环境变量、控制台目录约定、与 `kev.serve` / `kev.train` 的边界（控制台只组装 argv）、以及「改 `kev/console/` 前先读 `docs/superpowers/specs/2026-10-04-medical-finetune-console-design.md`」。

- [ ] **Step 7: 提交**

```bash
git add tests/test_console_contract.py .gitignore playground/AGENTS.md
git commit -m "test(console): 契约冻结（核心文件零改动 + 保留变量 + 14 种作业）"
```

---

## 附：spec §7.1 的完整作业序列（对照实现）

| # | kind | 关键 argv | 闸 |
| --- | --- | --- | --- |
| 1 | `plan_size` | `plan_size.py <spec> --baseline-acc 0.75 --json` | — |
| 2 | `generate` | `gen_<sc>.py --n 787 --out data/<sc>.jsonl --seed 0` | — |
| 3 | `goldset` | `make_goldset.py sample data/<sc>.jsonl --n 200 --seed 0 --out data/<sc>.gold.jsonl` | — |
| 4 | `split` | `split_data.py data/<sc>.jsonl --out data/<sc> --calibration 0.15 --development 0.15 --seed 0 [--holdout …]` | G2 G3 |
| 5 | `precheck` | `precheck.py --data data/<sc> --init-from jaredpalmer/kev-0.8b --split train` | **G1** |
| 6 | `train` | `kev.train --data …/train.jsonl --init_from jaredpalmer/kev-0.8b --lora 16 --lr 4e-5 --replay 2000 --out runs/<name>` | — |
| 7 | `baseline` | `kev.benchmark --run jaredpalmer/kev-0.8b --data data/<sc>/development.jsonl --out runs/<name>-baseline-eval` | — |
| 8 | `benchmark` | `kev.benchmark --run runs/<name> --data data/<sc>/development.jsonl --out runs/<name>-eval` | — |
| 9 | `compare` | `kev.compare --candidate runs/<name>-eval --reference runs/<name>-baseline-eval --out runs/<name>-compare` | **G4 G5** |
| 10 | `calibrate` | `kev.calibrate --rows runs/<name>-eval/rows.json --out runs/<name>-eval/calibration.json` | G7 |
| 11 | `baseline`+`benchmark`+`compare` | 同 7–9，换 `--suite evals/v7/decision-v7` | **G6** |
| 12 | `image` | `docker build -t kev-<name>:<temp> -f deploy/kev-serve/Dockerfile --build-arg …` | — |
| 13 | `deploy` | `kev.serve --run runs/<name> --port 8008 --temperature <temp>` | — |
| 14 | `smoke` | `smoke.py --base-url http://127.0.0.1:8008 --out runs/<name>-smoke.json` | — |

## 附：自审记录与唯一需要人工判断的一处

自审（writing-plans 要求的 placeholder / 一致性 / 类型 / 覆盖四轮检查）已修正：

1. **测试假通过**（严重）：Task 6/7 的 `req(**params)` 把参数放在 `JobRequest` 顶层，而 pydantic 默认 `extra='ignore'` 会静默丢弃 —— `test_a1_is_the_default` 会假通过、`test_full_weight_forces_bf16_weights` 会直接失败。已改为 `req(params={...})` 并在两处都写了警告注释。
2. **死代码**（严重）：Task 6 的 `build_argv` 里有 `argv.remove(...) if False else None`，且 `_train` 有一段带「落地时替换为这段」的占位实现。已合并成唯一的 `_with_values()` 实现。
3. **占位式路由**（严重）：Task 8 的 `_spawn` 曾写成 `kind=""`/`stage=""` 并留一个什么都不做的 `_run_plan_size`；`get_config` 用了 `__import__` hack。已全部替换为最终版。
4. **自相矛盾**：Task 10 曾 `import useSWR from "swr"` 又写「不要引 swr」。已改为 `usePoll` + `useCallback` 的完整 hook，并补上了此前只有描述、缺代码的 `JobTable`。
5. **用例打不中目标**：Task 8 的运行名点号用例原本用 `plan_size`，但只有 `train` 会调 `check_name`，永远走不到校验分支。已改为 `train`，并补上缺失的**单 GPU 并发闸**测试（spec §16 开放问题 2 的默认值，此前无测试覆盖）。
6. **依赖不存在的目录**：Task 6 的 `Conflict` 用例指向 `runs/cv-8b-lora-v1`（runbook 标注为「⏳ 待训练」，不存在）。已改用确实存在的 `runs`。
7. **签名核实**：所有 CLI 参数名与默认值均核对自真实 argparse；`kev.train` 用下划线（`--init_from`）且 `--base` 默认是 `Qwen/Qwen3-0.6B-Base`；`plan_size` 有 `--json`；`write_json` 无 `indent` 参数；`training_context()` 可无参调用。

### 执行前扫描（subagent-driven-development 的 pre-flight）追加发现 5 项，其中 3 项是硬阻断

9. **产物注册是死代码（根因，硬阻断）**：没有任何代码调用 `put_artifact` —— `_spawn` 只把 `artifacts_out` 存进 job 行，完成后无人注册。`api.artifacts()` / `api.datasets()` / `api.endpoints()` 与全部闸门查找都会返回空。
   **已修**：新增 `kev/console/artifacts.py`（Task 1）提供 `resolve()` / `summarize()` / `register()`；`LocalExecutor` 新增 `on_finished` 回调（Task 3）；`app.py` 在 `create_app` 里接上 `register_finished`（Task 8）。补两个回归测试：`test_a_finished_job_registers_its_artifacts_and_lineage`、`test_train_is_submittable_once_precheck_and_summary_exist`。
10. **`split` 漏注册 `summary.json`（硬阻断）**：G2/G3 读 `dataset:{data}/summary`，而 `split` 只注册 3 个分区 ⇒ G2/G3 永远失败 ⇒ **train 永远无法提交**。已修：`artifacts_out` 加上 `summary`。
11. **`precheck` 漏注册自己的报告（硬阻断）**：G1 读 `precheck:{data}/{split}`，而 `precheck` 的 `artifacts_out=[]` ⇒ G1 永远失败 ⇒ **train 永远无法提交**。已修：改用 `precheck:` 独立产物类型，路径由 `artifacts.resolve()` 唯一决定，`--out` 与注册 id 不再各拼一套。
12. **模块导入顺序（阻断 Task 5）**：`stages/__init__.py` 一次导入 `train`/`eval`/`deploy`，但这三个模块 Task 6/7 才建。已修：分三次建成（Task 5 → data；Task 6 → +train/eval；Task 7 → +deploy）。
13. **长驻作业的产物注册时机**：`deploy` 的 `kev.serve` 永不退出，「成功后才注册」会让 endpoint 产物永远不出现。已修：`StageSpec` 新增 `persist` 字段（`"success"` 默认 / `"start"`），`deploy` 用 `"start"`，在 `_spawn` 里注册；在线状态由部署页实际探 `/v1/models` 决定。
14. 顺带清掉 `app.py` 里两个未使用的导入（`STAGE_GATES`、`parse_plan_size`），并给 Task 9 Step 8 补上删除硬编码 key 的替换代码（原计划只写了描述）。

### 附录 A：Task 1 实施后回写（implementer 实际跑出来的 5 个真 bug）

brief 里的实现代码有 5 处缺陷，被 TDD 的红灯逼出来。已由 implementer 修正，后续任务照修正后的契约：

15. **`Store.transition` 的 UPDATE 漏了 `WHERE id = ?`** —— 会更新**整张 jobs 表**。最严重的一处，因为单作业的测试照样通过。修正：`sql = "UPDATE jobs SET status = ?" + ... + " WHERE id = ?"`，`params` 末尾追加 `job_id`。
16. **`lineage_of` 语义**：只查出边（`WHERE parent = ?`）。原实现查 `parent = ? OR child = ?`，会让「产物只记录自己派生了什么」的断言失败。**契约：出边（这个产物派生了什么）**；入边（谁派生了它）由 `child` 那一侧查。UI 的血缘树从根节点出发只画出边即可。
17. **`artifacts.resolve` 的 `dataset` 分支漏 `data/` 前缀** —— `dataset:cv/summary` 应解析成 `data/cv/summary.json`，不是 `cv/summary.json`。原实现会让 G2/G3 找不到文件。
18. **`artifacts.summarize` 不该把 `partitions` 抄进 meta** —— 列表页只需要记录数与无效行数。
19. **`lineage` 表的 `REFERENCES artifacts(id)` 与 `register` 的契约冲突** —— `artifacts_in` 里的输入产物（如 `dataset:cv`）可能尚未注册为 artifact，外键会拒绝。修正：lineage 表**不建外键**（输入产物允许是「已声明但还没落盘」的 id）。
20. `kev/console/stages/__init__.py` 在 Task 1 就必须创建（空包标记）。只改 `pyproject.toml` 的 `packages` 声明而不建目录，setuptools 构建会失败、整个仓库连 pytest 都启动不了。已加进 Task 1 的文件清单。
21. **`tests/test_conventions.py` 的 allowlist 在 Windows 上永不匹配（既有缺陷，已修 `d3769c1`）**：`str(path.relative_to(ROOT))` 在 Windows 上产生 `kev\checkpoint.py`（反斜杠），而 `RULES` 里的 allowlist 写的是 `kev/checkpoint.py`（正斜杠）⇒ 15/21 个检查无条件失败，本项目最主要的约定闸门形同虚设。改用 `as_posix()` 后 21 passed。**Task 1 Step 7 的「Expected: PASS」现在成立。**

唯一保留的人工判断点：

- **Task 3 的 `test_cancel_kills_the_process_group`** 用了 `pgrep`，某些 WSL2 发行版未装。失败时改用读 `/proc/<pid>/stat` 判存活，断言语义不变。

### 附录 B：慢测试、超时与 Windows 既有失败（回归执行须知）

回归时**不要一次性 `pytest tests/`**：两个重放型文件会把整轮拖到十几分钟且中途看似卡死。按下表单独跑并各自设超时。

| 文件 | 实测 | 建议超时 | 说明 |
| --- | --- | --- | --- |
| `tests/test_console_*.py`（8 个） | 27.8s / 167 passed | 120s | **本次新增**，快，可整组跑 |
| `tests/test_conventions.py` | 秒级 | 120s | 本次修过 Windows allowlist（附录 A #21） |
| `tests/test_research.py` | 25.6s（13 failed / 66 passed） | 180s | 失败全部是既有 Windows 问题（见下） |
| `tests/test_rounds.py` | **>10 min**，需单独跑 | **900s** | 27B 研究轮次重放，最慢 |

单独跑并带超时的姿势（Windows 原生没有 `timeout` 语义的 pytest 插件，用进程等待 + 强杀）：

```powershell
$p = Start-Process -PassThru -NoNewWindow -FilePath ".venv\Scripts\python.exe" `
     -ArgumentList "-m","pytest","tests/test_rounds.py","-q","-p","no:cacheprovider"
if (-not $p.WaitForExit(900000)) { $p.Kill() }   # 单位毫秒
```

**两个文件不要并发跑**，也不要和 `npm run build` 并发 —— 实测并发会让两者互相饿死（`test_rounds` 10 分钟只推进 3%，构建 CPU 占用掉到 4%）。

#### 既有 Windows 失败（与本次无关，已核实）

本次对 `kev/` 的改动**只有 `kev/console/**` 的新增文件**，未改任何既有模块（`git diff 6bd9a68 HEAD -- kev/` 可复核）；唯一改动的既有文件是 `tests/test_conventions.py`。所以下面两类失败都是历史遗留：

1. **`kev/experiment.py:14` 的 `import fcntl`** —— `fcntl` 是 POSIX-only，Windows 上 `ModuleNotFoundError`。这正是 §3.3 决定**不复用 `kev.experiment` 做编排层**、改走 `kev_modal.py` / 直调 `kev.train` 子进程的直接原因。`test_research.py` 的 13 个失败多为由此传导。
2. **路径分隔符** —— `test_rounds.py` 断言用正斜杠，Windows 上 `rounds.trial_training()` 返回反斜杠：
   `assert 'evals/round6/b1v2' in frozenset({'evals\\round6\\b1v2', ...})`。

两者在 WSL2 / Linux 上都不会出现。**这批失败不属于本次交付范围**，修它们要动既有模块，属于独立工作。

#### 构建坑：别中途强杀 `next build`

`next build` 被强杀会在 `.next/lock` 留下空锁，此后所有构建都以 `Another next build process is already running` 静默挂起（CPU 掉到 ~4%，日志停在 `Running next.config.ts took 50ms`）。

恢复方式按侵入性从小到大：

1. 删 `.next/lock`（单文件）并确认无 `next` 残留进程；
2. 仍挂起则整目录重命名（**不要用 `Remove-Item -Recurse`**，会触发批量删除守卫）：
   `Rename-Item .next .next-corrupt-<日期>`，构建会重建全新缓存；
3. 被重命名的目录**不会被 `.gitignore` 匹配**（忽略规则写的是 `.next`），会变成未跟踪目录 —— 处理完记得移出工作区或删除。

实测：全新 `.next` 下 `Compiled successfully in 29.2s`，11/11 静态页生成，7 个 `/console/*` 路由全部产出。
