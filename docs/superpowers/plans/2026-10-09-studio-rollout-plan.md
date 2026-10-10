# Studio 控制台（Service 化）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 2026-10-09 的 Studio 控制台 7 章设计（`docs/superpowers/specs/2026-10-09-studio-*.md`）落地为可执行代码，按 ch0 阶段 A→B→C→D 拆 4 个 Wave：5 个反向依赖 PR → console service 化 → playground studio 前端 → 蒸馏守护独立进程。

**Architecture:** 阶段 A 改 `kev/{train,benchmark,compare,calibrate,publish}.py` 拆 CLI 块（5 个独立 PR，不影响外部行为）。阶段 B 在 `kev/console/services/{data,train,eval,deploy,publish}.py` 新建 service 层，`executor.py` 增 `spawn_callable`，与原 Popen 路径并存（`KEV_SERVICE_BACKEND=script` 切回）。阶段 C 在 `playground/src/app/kev.studio/` 新增前端模块。阶段 D 蒸馏守护走 `kev/console/daemon_runner.py` 独立进程。

**Tech Stack:** Python 3.12 / FastAPI / SQLite（标准库 `sqlite3`，已存在）/ threading.Event / Next.js 16 / React 19 / Tailwind v4 / `@base-ui/react`（已存在） / SSE

**设计文档：**
- `docs/superpowers/specs/2026-10-09-studio-scenarios-design.md`（ch1）
- `docs/superpowers/specs/2026-10-09-studio-data-design.md`（ch2，含 §2.X service 重构）
- `docs/superpowers/specs/2026-10-09-studio-train-design.md`（ch3，含 §3.X service 重构）
- `docs/superpowers/specs/2026-10-09-studio-eval-design.md`（ch4，含 §4.X service 重构）
- `docs/superpowers/specs/2026-10-09-studio-deploy-design.md`（ch5，含 §5.X service 重构）
- `docs/superpowers/specs/2026-10-09-studio-management-design.md`（ch6）
- `docs/superpowers/specs/2026-10-09-studio-overview-design.md`（ch7）
- `docs/superpowers/specs/2026-10-09-studio-rollout-design.md`（ch0，本计划的实施顺序与降级路径）

---

## Global Constraints

每个 Task 都隐含包含本节。

**前置条件：已有控制台基础设施**

`kev/console/` 已存在（`2026-10-04 medical-finetune-console.md` 计划已落地）：
- `kev/console/paths.py` / `db.py` / `artifacts.py` / `events.py` / `executor.py` / `gates.py`
- `kev/console/stages/{base.py, data.py, train.py, eval.py, deploy.py, publish.py}` 全部就绪
- `kev/console/app.py` FastAPI 路由就绪
- `playground/src/app/console/` 原控制台 UI 就绪（将被 `kev.studio/` 取代）

**反向依赖 PR 纪律（用户决议 1）**

- 阶段 A 的 5 个 PR **单独**发，每个 PR 只动 `kev/<name>.py` 一个文件
- 阶段 A 完成后，**保持子进程路径仍可工作**——拆 CLI 不影响外部行为
- 阶段 B 完成后，**两条路径并存**（Popen + service），`KEV_SERVICE_BACKEND=script` 切回 Popen

**训练期 503 降级（用户决议 3）**

- `kev/console/services/train.py` 启动训练前设 `_training_active = True`
- `kev/console/app.py:proxy_kev` 检测该标志 → 503
- 不暴露到浏览器
- kev-deploy 走 `scripts/kev_serve.py` 独立 Modal 容器，**不受影响**

**蒸馏守护独立进程（用户决议 2）**

- 阶段 D 完成后，**移除** inline 守护路径
- `python -m kev.console.daemon_runner` 是独立进程
- 通过 `/console/api/_internal/distill-event` 内部端点写 events

**`tests/test_conventions.py` 合规**

新代码必须遵守 17 条「单一归属」正则（详见 `2026-10-04 plan` Global Constraints 节）。重点提示：

- 温度从 `calibration.json` 取，**不读 `KEV_TEMPERATURE`**
- 写 JSON / JSONL 用 `kev.suite.read_json/write_json/read_jsonl/write_jsonl`
- 检查点操作走 `kev.checkpoint`，不直接 `torch.load/save`
- 选项 key 走 `kev.api.question_keys`

**目录契约**（与已有 `2026-10-04 plan` 一致）

```
data/<scenario>/{train,calibration,development}.jsonl + summary.json
runs/<name>/
runs/<name>-eval/{rows.json, report.json, calibration.json}
data/console/jobs/<job_id>.log
data/console/kev-console.db
kev/console/services/    ← 新增（阶段 B）
kev/console/daemon_runner.py  ← 新增（阶段 D）
playground/src/app/kev.studio/  ← 新增（阶段 C）
```

**打包**

`pyproject.toml` 已包含 `kev.console` 子包（`2026-10-04 plan` Task 1 已加）。本计划新增 `kev.console.services` 子包——`packages = ["kev"]` 用 setuptools 自动递归，无需再改 pyproject。

**提交纪律**

每个 Task 末尾提交。只 `git add` 该 Task 自己的文件。

---

## File Structure（新增/修改汇总）

### 后端修改（阶段 A）

| 文件 | 阶段 A 改动 |
| --- | --- |
| `kev/train.py` | 拆 CLI → `run(args)`；模块级 `cancel: threading.Event` |
| `kev/benchmark.py` | 拆 CLI → `run(args)`；模块级 `cancel: threading.Event` |
| `kev/compare.py` | 拆 CLI → `run(args)` |
| `kev/calibrate.py` | 拆 CLI → `run(args)` |
| `kev/publish.py` | 拆 CLI → `run(args)` |

### 后端新增（阶段 B）

| 文件 | 职责 |
| --- | --- |
| `kev/console/services/__init__.py` | 包标记；导出 `DataService / TrainService / EvalService / DeployService / PublishService` |
| `kev/console/services/data.py` | `DataService`：plan_size / generate / make_examples / goldset / goldset_audit / split / precheck / distill（一次性，守护走 D） |
| `kev/console/services/train.py` | `TrainService`：train（含 gpu_lock、_training_active 标志） |
| `kev/console/services/eval.py` | `EvalService`：baseline / benchmark / compare / calibrate（后两者纯 CPU） |
| `kev/console/services/deploy.py` | `DeployService`：image / deploy / smoke / cancel_endpoint |
| `kev/console/services/publish.py` | `PublishService`：publish / modal（modal 保留 Popen 调 modal CLI） |

### 后端修改（阶段 B）

| 文件 | 改动 |
| --- | --- |
| `kev/console/executor.py` | 保留 `spawn`；新增 `spawn_callable(job_id, fn, *, label, log_path)` |
| `kev/console/app.py` | `proxy_kev` 检测 `_training_active` → 503；新增 `POST /console/api/_internal/distill-event`（阶段 D 用） |
| `kev/console/stages/data.py` | `_xxx_build` 调 service 方法 + `spawn_callable` |
| `kev/console/stages/train.py` | 同上 |
| `kev/console/stages/eval.py` | 同上 |
| `kev/console/stages/deploy.py` | image / smoke 走 service；deploy 仍 Popen |
| `kev/console/stages/publish.py` | publish 走 service；modal 仍 Popen |
| `kev/console/generators/` | 各 `gen_*.py` / `make_*.py` 拆 `if __name__` 块，暴露纯函数（被 service 调用） |

### 后端新增（阶段 D）

| 文件 | 职责 |
| --- | --- |
| `kev/console/daemon_runner.py` | `python -m kev.console.daemon_runner` 入口；接收主进程 spawn 来的参数；调 `kev.console.services.data_daemon` |
| `kev/console/services/data_daemon.py` | 守护专用 service（与 `data.py` 不同的循环语义；长驻，监听主进程 HTTP 信号） |

### 前端新增（阶段 C）

```
playground/src/app/kev.studio/
├── layout.tsx                # studio 外壳
├── page.tsx                   # 重定向到 overview
├── overview/page.tsx
├── datasets/{overview, plan-size, generate, distill, split-precheck, history}/page.tsx
├── jobs/{page.tsx, [id]/page.tsx, new/page.tsx}
├── scenarios/{domains, scenario/[slug], spec/[slug]}/page.tsx
├── apikeys/page.tsx
├── distill-providers/page.tsx
├── usage/page.tsx
└── endpoints/{image, deploy, smoke, publish, modal}/page.tsx

playground/src/components/studio/
├── Sidebar.tsx
├── StatusBar.tsx
├── Drawer.tsx
├── Modal.tsx
├── GatePanel.tsx
├── JobProgressBar.tsx
├── LogStream.tsx
├── Toast.tsx
├── EmptyState.tsx
├── ErrorBoundary.tsx
├── ArgvPreview.tsx
├── charts.tsx
├── ScenarioTree.tsx
├── ScenarioDetail.tsx
├── SpecEditor.tsx
├── StageForm.tsx
├── DistillForm.tsx
├── TrainFormShell.tsx
├── KeyTable.tsx
├── ProviderTable.tsx
├── UsageDashboard.tsx
├── EndpointTable.tsx
├── DeployFormShell.tsx
├── EvalFormShell.tsx
├── EvalResultCard.tsx
├── CompareFlipTable.tsx
└── CalibrateCard.tsx

playground/src/lib/console.ts   # 控制台 API 客户端 + EventSource 封装
playground/src/i18n/{zh-CN,en-US}.ts
```

### 测试新增

```
tests/test_kev_train_cli.py      # A1
tests/test_kev_benchmark_cli.py  # A2
tests/test_kev_compare_cli.py    # A3
tests/test_kev_calibrate_cli.py  # A4
tests/test_kev_publish_cli.py    # A5
tests/test_console_services_data.py    # B-1
tests/test_console_services_train.py   # B-2
tests/test_console_services_eval.py    # B-3
tests/test_console_services_deploy.py  # B-4
tests/test_console_services_publish.py # B-5
tests/test_console_executor_callable.py # B-6
tests/test_console_daemon_runner.py    # D
```

---

## Wave A — 反向依赖 PR（5 个独立 PR，独立可回滚）

> **关键不变量**：每个 PR 改一个 `kev/<name>.py`；**不**改 console；**不**改外部行为（`python -m kev.<name> --help` 仍工作；`tests/test_unit.py` 仍全绿）。

### Task A1: 拆 `kev/train.py` 的 CLI 块，暴露 `run()` + 模块级 `cancel`

**Files:**
- Modify: `kev/train.py`
- Test: `tests/test_kev_train_cli.py`

**Interfaces:**
- Produces: `kev.train.run(args: argparse.Namespace) -> int`（与原 `main()` 同语义）
- Produces: `kev.train.cancel: threading.Event`（模块级）
- Produces: `kev.train._step_loop` / `kev.train._TrainCanceled` 内部符号
- 保留: `python -m kev.train` 仍能跑（`if __name__ == "__main__": parser.parse_args() → run(parsed)`）

**Steps:**

- [ ] **Step 1: 写失败测试**

```python
# tests/test_kev_train_cli.py
"""kev.train 拆 CLI 后：run() 纯函数 + cancel 仍可工作。

跑：uv run python -m pytest tests/test_kev_train_cli.py -q
"""
import argparse
import threading
import pytest

import kev.train


def test_run_smoke_with_min_args():
    """run() 接收最小 Namespace，不抛 ImportError。"""
    args = argparse.Namespace(
        suite="evals/smoke-v1", base="Qwen/Qwen2.5-0.5B",
        base_revision="main", epochs=1, lr=1e-4, batch=1, accum=1,
        dtype="fp32", device="cpu", checkpointing=0,
        p_none_pair=0.0, lora=16, head_dim=256, lora_targets="all",
        max_steps=1, n_per_source=4,
        # ...剩余字段按 kev.train 的 argparse 真实 default 补齐
    )
    # 真实 run() 会拉模型做小步训练；这里只验证不抛 NameError
    # 用 n_per_source=4 + max_steps=1 让它尽快结束
    try:
        rc = kev.train.run(args)
    except (SystemExit, KeyboardInterrupt) as e:
        rc = getattr(e, "code", 1)
    assert isinstance(rc, int)


def test_cancel_event_is_module_level():
    assert isinstance(kev.train.cancel, threading.Event)


def test_cli_still_invokable():
    """`python -m kev.train --help` 仍 work（拆 CLI 不破坏入口）。"""
    import subprocess
    result = subprocess.run(
        ["python", "-m", "kev.train", "--help"],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0
    assert "--base" in result.stdout
```

- [ ] **Step 2: 读 `kev/train.py` 现状，识别 `main()` 边界**

读 `kev/train.py`（约 200+ 行），识别：
- 顶层 import 与 `argparse.ArgumentParser` 定义
- `def main() -> int:` 函数体（拼 Namespace → 调内部函数）
- `if __name__ == "__main__":` 块
- step loop（很可能在 `_train_one` / `_train_loop` 内部）—— 需要在每 N 步插入 cancel 检查

- [ ] **Step 3: 重构**

具体改法（与原代码同语义）：

```python
# kev/train.py 改动

import threading

cancel: threading.Event = threading.Event()  # 模块级，作业级置位

class _TrainCanceled(Exception):
    pass


def run(args: argparse.Namespace) -> int:
    """原 main() 的纯函数版。

    内部实现要点：
    - args 校验（与原 main 开头相同）
    - 数据集准备（与原 main 相同）
    - 调 _train_loop，在 step N 处插入：
        if cancel.is_set():
            raise _TrainCanceled()
    - 异常在 main 边界统一 try/except 转 return code
    """
    # ... 与原 main 完全相同，把 'raise SystemExit(0)' 改成 'return 0' ...


def main() -> int:  # 保留 CLI 入口
    parser = _build_parser()
    args = parser.parse_args()
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
```

**取消检查插入位置**（关键）：

```python
# 在 step loop 的训练步函数内（伪代码）
for step_idx, batch in enumerate(loader):
    if step_idx % CANCEL_CHECK_EVERY == 0 and cancel.is_set():
        raise _TrainCanceled()
    loss = forward_backward(batch)
    # ...
```

`CANCEL_CHECK_EVERY` 默认 8（小步训练也响得上取消，又不会把 `threading.Event.is_set()` 调到肉眼可见的慢）。

- [ ] **Step 4: 跑全测**

```bash
uv run python -m pytest tests/test_unit.py tests/test_kev_train_cli.py -q
```

**Acceptance**：
- 3 个新测试全绿
- `tests/test_unit.py` 全绿
- `python -m kev.train --help` 仍 work
- `python -m kev.train --n_per_source 4 --accum 4 --out runs/smoke-a1` 仍能跑（与改造前同 argv 同行为）

**Rollback**：`git revert <A1-sha>` 单 PR 即可。

---

### Task A2: 拆 `kev/benchmark.py` 同 A1 模式

**Files:**
- Modify: `kev/benchmark.py`
- Test: `tests/test_kev_benchmark_cli.py`

**Steps:**

- [ ] **Step 1: 写失败测试**（与 A1 同骨架）

```python
# tests/test_kev_benchmark_cli.py
import argparse
import threading
import pytest

import kev.benchmark


def test_run_smoke_with_min_args():
    args = argparse.Namespace(
        run="runs/smoke-hl/00-trial-0/checkpoint",
        data="data/smoke/development.jsonl",
        suite="evals/smoke-v1",
        out="runs/test-bench-smoke",
        device="cpu", split="development", rotations=1,
        date_facts=False, allow_test=False,
        remote=None, remote_concurrency=1,
    )
    try:
        rc = kev.benchmark.run(args)
    except (SystemExit, KeyboardInterrupt):
        rc = 1
    assert isinstance(rc, int)


def test_cancel_event_is_module_level():
    assert isinstance(kev.benchmark.cancel, threading.Event)


def test_cli_still_invokable():
    import subprocess
    r = subprocess.run(
        ["python", "-m", "kev.benchmark", "--help"],
        capture_output=True, text=True, timeout=30,
    )
    assert r.returncode == 0
    assert "--run" in r.stdout
```

- [ ] **Step 2: 读 `kev/benchmark.py`，识别 `main()` 边界与 step loop**

- [ ] **Step 3: 重构**

与 A1 同模式：`run(args)` + `cancel: threading.Event` + `_BenchmarkCanceled` + `main()` 保留。`CANCEL_CHECK_EVERY = 16`（评测步数远多于训练，1 步更粗粒度足够）。

- [ ] **Step 4: 跑全测**

```bash
uv run python -m pytest tests/test_unit.py tests/test_kev_train_cli.py tests/test_kev_benchmark_cli.py -q
```

**Acceptance**：与 A1 同；额外 `kev.benchmark` 跑一次小套件（如 `evals/smoke-v1` development 50 题）验证 `report.json` 与改造前 byte-for-byte 一致。

**Rollback**：`git revert <A2-sha>`。

---

### Task A3: 拆 `kev/compare.py`

**Files:**
- Modify: `kev/compare.py`
- Test: `tests/test_kev_compare_cli.py`

**Steps:**

- [ ] **Step 1: 写失败测试**

```python
# tests/test_kev_compare_cli.py
import argparse
import pytest

import kev.compare


def test_run_with_two_dirs():
    args = argparse.Namespace(
        candidate="runs/smoke-a1-eval",
        reference="runs/smoke-a1-baseline-eval",
        out="runs/test-compare",
    )
    rc = kev.compare.run(args)
    assert rc == 0


def test_cli_still_invokable():
    import subprocess
    r = subprocess.run(
        ["python", "-m", "kev.compare", "--help"],
        capture_output=True, text=True, timeout=30,
    )
    assert r.returncode == 0
```

- [ ] **Step 2: 读 `kev/compare.py`，识别 `main()` 边界**

- [ ] **Step 3: 重构**

无 cancel（compare 是纯 CPU 短作业）。仅拆 CLI 块暴露 `run(args)`。

- [ ] **Step 4: 跑全测**

```bash
uv run python -m pytest tests/test_unit.py tests/test_kev_compare_cli.py -q
```

**Acceptance**：`python -m kev.compare` 与改造前同 argv 同行为。

---

### Task A4: 拆 `kev/calibrate.py`

**Files:**
- Modify: `kev/calibrate.py`
- Test: `tests/test_kev_calibrate_cli.py`

**Steps:** 与 A3 同模式，无 cancel。

**Acceptance**：`python -m kev.calibrate --help` 仍 work；`tests/test_unit.py` 全绿。

---

### Task A5: 拆 `kev/publish.py`

**Files:**
- Modify: `kev/publish.py`
- Test: `tests/test_kev_publish_cli.py`

**Steps:** 与 A3 同模式，无 cancel。

**Acceptance**：`python -m kev.publish --help` 仍 work；`tests/test_unit.py` 全绿。

---

### Wave A 完成门

- [ ] A1–A5 全部合并（5 个独立 commit，5 个 PR）
- [ ] 5 个新测试文件全绿
- [ ] `tests/test_unit.py` 全绿
- [ ] `tests/test_conventions.py` 全绿（重点检查 5 个改动文件没引入新违规）
- [ ] 5 个 CLI 入口都能 `--help`
- [ ] 提交到 main 后，**保留**所有现有子进程路径的可用性（最关键）

**Wave A 完成后回退验证**：

```bash
git checkout <pre-A1-sha>  # 假设把 A1–A5 都 revert
uv run python -m kev.train --help   # 仍 work
uv run python -m kev.benchmark --help
# 等等
```

如果不行，说明某个 PR 改动了外部行为——必须修。

---

## Wave B — Console service 化（一个 PR，可回退）

> **关键不变量**：保留 Popen 路径；`KEV_SERVICE_BACKEND=script` 切回；闸门 / artifacts / events / DB schema 全部不动。

### Task B-1: `kev/console/services/data.py`（5 个 service 方法，3 个 stage 仍走 Popen）

**范围修正（2026-10-09 落盘时发现）**：

`kev/console/stages/data.py` 实际调 9 个 stage，**3 个**调的是 `skills/kev-finetune/scripts/*`（独立仓库，独立发版）：
- `plan_size` → `skills/kev-finetune/scripts/plan_size.py`
- `distill` / `distill_daemon` → `skills/kev-finetune/scripts/generate_data.py`
- `split` → `skills/kev-finetune/scripts/split_data.py`

为避免 console 对 skill 仓库产生反向依赖，这 3 个 stage **保持 Popen 路径**（原状，不改 `kev/console/stages/data.py` 里它们的 `_xxx` 函数），service 层不提供对应方法。

**实际 service 范围**：5 个 stage 在 console 仓库自有业务层：
- `generate` → `kev/console/generators/gen_*.py`（每个 scenario 一个）
- `goldset` / `goldset_audit` → `kev/console/generators/make_goldset.py`
- `precheck` → `kev/console/precheck.py`
- `make_examples` → `kev/console/make_examples.py`

**Files:**
- Create: `kev/console/services/__init__.py`
- Create: `kev/console/services/data.py`
- Modify: `kev/console/generators/gen_*.py`（6 个，拆 `if __name__` 块）
- Modify: `kev/console/generators/make_goldset.py`（拆 `if __name__` 块，含 `sample` / `audit` 子命令）
- Modify: `kev/console/precheck.py`（拆 `if __name__` 块）
- Modify: `kev/console/make_examples.py`（拆 `if __name__` 块）
- Test: `tests/test_console_services_data.py`

**Interfaces:**

```python
# kev/console/services/__init__.py
from .data import DataService
# 阶段 B 后续 task 完成后补：from .train import TrainService; ...

# kev/console/services/data.py
class DataService:
    def __init__(self, store: Store, cancel: threading.Event):
        self.store = store
        self.cancel = cancel

    def generate(self, req: JobRequest, *, on_log: Callable[[str], None]) -> dict: ...
    def make_examples(self, req: JobRequest, *, on_log) -> dict: ...
    def goldset(self, req: JobRequest, *, on_log) -> dict: ...
    def goldset_audit(self, req: JobRequest, *, on_log) -> dict: ...
    def precheck(self, req: JobRequest, *, on_log) -> dict: ...
    # plan_size / distill / distill_daemon / split: 仍走 Popen 调 skill 脚本（不进 service）
```

**Steps:**

- [ ] **Step 1: 写失败测试**

```python
# tests/test_console_services_data.py
"""DataService：service 层走同进程业务函数；不 spawn 子进程。

仅覆盖 console 仓库自有的 5 个 stage（generate / goldset / goldset_audit /
precheck / make_examples）；plan_size / distill / split 仍走 Popen 路径，
不在本测试范围。
"""
import threading
import pytest

from kev.console.db import Store
from kev.console.services.data import DataService
from kev.console.stages.base import JobRequest


@pytest.fixture
def svc(tmp_path):
    store = Store(tmp_path / "test.db")
    return DataService(store, threading.Event())


def test_generate_runs_inprocess(svc, tmp_path, monkeypatch):
    """generate service 调同进程 import 的 gen_critical_value.run()，不 spawn。"""
    from kev.console.services import data as data_svc
    calls = []

    def fake_run(args, *, scenario):
        calls.append((scenario, args))
        return {"returncode": 0}

    # 替 DataService 内部 import 的 run；fixture 路径上覆盖
    monkeypatch.setattr(data_svc, "_generate_runners", {"critical-value": fake_run})

    req = JobRequest(scenario="critical-value", run_name="cv-test", params={"n": 5})
    result = svc.generate(req, on_log=lambda s: None)
    assert calls == [("critical-value", pytest.approx_args())]  # 视实际断言
    assert result["returncode"] == 0
```

（实际测试会按 console 仓库的约定形式写——本 plan 给出**意图**与**接口**，具体实现细节由 Task 编写者补齐。）

- [ ] **Step 2: 拆业务层 CLI 块**

对 `kev/console/generators/gen_*.py` / `make_goldset.py` / `kev/console/precheck.py` / `kev/console/make_examples.py` 每个脚本：
- `if __name__ == "__main__"` 抽出
- 把 argparse 块移到 `_build_parser()` 函数（不强制，必要时直接保留 `main()` 内）
- 把执行主体移到 `def run(args: argparse.Namespace) -> int`（或 `run(...)` 接受现有参数）
- `if __name__` 块改为 `raise SystemExit(main())`（保留 CLI 入口）

涉及文件（**实际**）：
- `kev/console/generators/gen_critical_value.py`
- `kev/console/generators/gen_diagnosis.py`
- `kev/console/generators/gen_medication_review.py`
- `kev/console/generators/gen_nursing_quality.py`
- `kev/console/generators/gen_record_summary.py`
- `kev/console/generators/gen_triage.py`
- `kev/console/generators/make_goldset.py`（含 `sample` / `audit` 子命令）
- `kev/console/precheck.py`
- `kev/console/make_examples.py`

**不动的**：
- `kev/console/stages/data.py` 里 `_plan_size` / `_distill_build` / `_split` 这 3 个函数
- `kev/console/executor.py` 里调用它们的 Popen 路径

- [ ] **Step 3: 实现 `DataService`**

```python
# kev/console/services/data.py
from __future__ import annotations
import argparse
import importlib
import io
import sys
import threading
from typing import Callable

from kev.console.db import Store
from kev.console.stages.base import JobRequest


class DataService:
    def __init__(self, store: Store, cancel: threading.Event):
        self.store = store
        self.cancel = cancel

    def generate(self, req: JobRequest, *, on_log: Callable[[str], None]) -> dict:
        """generate service 调同进程 import 的 gen_<scenario>.run()。

        on_log 适配器：原脚本往 stdout 写进度，service 临时替换 sys.stdout 把
        print() 走 on_log（避免引入 logging 重配，保持业务函数原行为）。
        """
        scenario = req.scenario
        module = importlib.import_module(f"gen_{scenario.replace('-', '_')}")
        args = self._build_generate_args(req)
        return self._run_with_log_redirect(module.run, args, on_log)

    def make_examples(self, req: JobRequest, *, on_log) -> dict:
        """make_examples 调 kev.console.make_examples.run() 同进程。"""
        from kev.console import make_examples
        args = self._build_make_examples_args(req)
        return self._run_with_log_redirect(make_examples.run, args, on_log)

    def goldset(self, req: JobRequest, *, on_log) -> dict:
        """goldset 调 kev.console.generators.make_goldset.sample_run()（sample 子命令）。"""
        from kev.console.generators import make_goldset
        args = self._build_goldset_args(req)
        return self._run_with_log_redirect(make_goldset.sample_run, args, on_log)

    def goldset_audit(self, req: JobRequest, *, on_log) -> dict:
        """goldset_audit 调 make_goldset.audit_run()（audit 子命令）。"""
        from kev.console.generators import make_goldset
        args = self._build_goldset_audit_args(req)
        return self._run_with_log_redirect(make_goldset.audit_run, args, on_log)

    def precheck(self, req: JobRequest, *, on_log) -> dict:
        """precheck 调 kev.console.precheck.run() 同进程。"""
        from kev.console import precheck
        args = self._build_precheck_args(req)
        return self._run_with_log_redirect(precheck.run, args, on_log)

    # ---- helpers ----

    def _run_with_log_redirect(self, fn, args, on_log):
        import sys, io
        original = sys.stdout

        class _LogStream(io.StringIO):
            def write(self, s):
                if s and s != "\n":
                    on_log(s.rstrip("\n"))
                return super().write(s)

        sys.stdout = _LogStream()
        try:
            rc = fn(args)
        finally:
            sys.stdout = original
        return {"returncode": rc}

    def _build_generate_args(self, req): ...
    def _build_make_examples_args(self, req): ...
    def _build_goldset_args(self, req): ...
    def _build_goldset_audit_args(self, req): ...
    def _build_precheck_args(self, req): ...
```

- [ ] **Step 4: 修改 `kev/console/stages/data.py` 的 5 个 stage**

仅修改 5 个：**`_generate` / `_goldset` / `_goldset_audit` / `_precheck` / `_make_examples`**。
每个修改方式：调用方从 `executor.spawn(job_id, argv, ...)` 改成 `executor.spawn_callable(job_id, partial(service.<method>, req, on_log=...), ...)`。

`_plan_size` / `_distill_build` / `_split` 三个**不动**——仍走原 Popen 调 skill 脚本。

- [ ] **Step 5: 跑测试**

```bash
uv run python -m pytest tests/test_console_services_data.py tests/test_unit.py -q
```

**Acceptance**：
- 5 个新测试（每个 service 方法 1 个）全绿
- `tests/test_unit.py` 仍全绿
- 业务层 CLI 入口仍可工作（拆 `if __name__` 不破坏）
- `_plan_size` / `_distill_build` / `_split` 路径**byte-for-byte 不变**（Popen 调 skill 脚本原状）

- [ ] **Step 4: 实现 `on_log` 适配器**

```python
def _run_with_log_redirect(self, fn, args, on_log):
    """跑业务函数，stdout 重定向到 on_log。

    实现策略：临时替换 sys.stdout；业务函数 print() 的内容走 on_log。
    不引入 logging 重配（保持业务函数原行为）。
    """
    import sys, io
    original = sys.stdout

    class _LogStream(io.StringIO):
        def write(self, s):
            if s and s != "\n":
                on_log(s.rstrip("\n"))
            return super().write(s)

    sys.stdout = _LogStream()
    try:
        rc = fn(args)
    finally:
        sys.stdout = original
    return {"returncode": rc}
```

- [ ] **Step 5: 跑测试**

```bash
uv run python -m pytest tests/test_console_services_data.py tests/test_unit.py -q
```

**Acceptance**：
- 5 个新测试（每个 service 方法 1 个）全绿
- `tests/test_unit.py` 仍全绿
- 业务层 CLI 入口仍可工作（拆 `if __name__` 不破坏）
- `_plan_size` / `_distill_build` / `_split` 路径**byte-for-byte 不变**（Popen 调 skill 脚本原状）

---

### Task B-2: `kev/console/services/train.py`（含 gpu_lock、_training_active 标志）

**Files:**
- Create: `kev/console/services/train.py`
- Test: `tests/test_console_services_train.py`

**Interfaces:**

```python
class TrainService:
    def __init__(self, store: Store, cancel: threading.Event, gpu_lock: threading.Lock):
        self.store = store
        self.cancel = cancel
        self.gpu_lock = gpu_lock

    def train(self, req: JobRequest, *, on_log, on_metric) -> dict:
        # 1. acquire self.gpu_lock（阻塞）
        # 2. set _training_active = True（进程级，跨 service 共享）
        # 3. 调 kev.train.run(args)
        # 4. clear _training_active
        # 5. release gpu_lock
        ...
```

**Steps:**

- [ ] **Step 1: 写失败测试**

```python
# tests/test_console_services_train.py
import threading
import pytest
from kev.console.db import Store
from kev.console.services.train import TrainService, _training_active
from kev.console.stages.base import JobRequest


@pytest.fixture
def svc(tmp_path):
    store = Store(tmp_path / "test.db")
    return TrainService(store, threading.Event(), threading.Lock())


def test_training_active_set_during_run(svc):
    """service.train() 跑期间 _training_active=True。"""
    # 用 mock 替代真实 kev.train.run 跑（真实训练小时级，CI 跑不动）
    import kev.console.services.train as train_svc
    original_run = train_svc.kev_train_run

    def fake_run(args):
        assert _training_active.is_set()
        return 0

    train_svc.kev_train_run = fake_run
    try:
        req = JobRequest(scenario="critical-value", run_name="cv-train", params={})
        result = svc.train(req, on_log=lambda s: None, on_metric=lambda p: None)
    finally:
        train_svc.kev_train_run = original_run
    assert not _training_active.is_set()  # 跑完清掉
```

- [ ] **Step 2: 实现 `TrainService`**

```python
# kev/console/services/train.py
import threading
from kev.console.db import Store
from kev.console.stages.base import JobRequest
import kev.train

# 进程级 _training_active 标志
_training_active = threading.Event()


def is_training_active() -> bool:
    return _training_active.is_set()


class TrainService:
    def __init__(self, store: Store, cancel: threading.Event, gpu_lock: threading.Lock):
        self.store = store
        self.cancel = cancel
        self.gpu_lock = gpu_lock

    def train(self, req: JobRequest, *, on_log, on_metric) -> dict:
        # GPU 锁（阻塞）
        with self.gpu_lock:
            _training_active.set()
            try:
                # 设 cancel 标志（service 调 kev.train.run 期间，kev.train.cancel 仍是模块级）
                kev.train.cancel = self.cancel  # 引用同一 Event
                # 业务调用
                args = self._build_args(req)
                rc = kev.train.run(args)
                return {"returncode": rc, "run_dir": ...}
            finally:
                _training_active.clear()
                kev.train.cancel = threading.Event()  # 复位（避免污染下次）
```

- [ ] **Step 3: 修改 `kev/console/app.py:proxy_kev`**

```python
# kev/console/app.py
from kev.console.services.train import is_training_active

# 找到 proxy_kev 函数，在分发到 /v1/* 之前：
if is_training_active():
    return Response(
        status_code=503,
        content=json.dumps({"error": "训练占用 GPU，推理临时不可用"}),
        media_type="application/json",
    )
```

- [ ] **Step 4: 跑测试**

```bash
uv run python -m pytest tests/test_console_services_train.py tests/test_unit.py -q
```

**Acceptance**：
- 3 个新测试全绿（_training_active 标志、gpu_lock 阻塞、cancel 传播）
- `proxy_kev` 在 `_training_active=True` 时返回 503（curl 验证）
- 现有 `tests/test_api.py` 仍全绿

---

### Task B-3: `kev/console/services/eval.py`

**Files:**
- Create: `kev/console/services/eval.py`
- Test: `tests/test_console_services_eval.py`

**Steps:** 与 B-1 同模式，4 个 service 方法：`baseline` / `benchmark` / `compare` / `calibrate`。`compare` 与 `calibrate` 纯 CPU，不抢 GPU 锁；`baseline` / `benchmark` 与 train 互斥（共用 gpu_lock）。

**Acceptance**：4 个 test；`tests/test_unit.py` 全绿。

---

### Task B-4: `kev/console/services/deploy.py`

**Files:**
- Create: `kev/console/services/deploy.py`
- Test: `tests/test_console_services_deploy.py`

**Steps:** 4 个 service 方法：`image`（调 kev.publish.run 镜像部分）/ `deploy`（Popen 保留，调 `python -m kev.serve`）/ `smoke`（5 场景 HTTP 请求）/ `cancel_endpoint`（杀 Popen）。

**Acceptance**：4 个 test；`deploy` Popen 路径与原行为 byte-for-byte。

---

### Task B-5: `kev/console/services/publish.py`

**Files:**
- Create: `kev/console/services/publish.py`
- Test: `tests/test_console_services_publish.py`

**Steps:** 2 个 service 方法：`publish`（调 kev.publish.run）/ `modal`（Popen 保留，调 `modal app deploy`）。

**Acceptance**：2 个 test。

---

### Task B-6: `kev/console/executor.py` 新增 `spawn_callable`

**Files:**
- Modify: `kev/console/executor.py`
- Modify: `kev/console/stages/{data,train,eval,deploy,publish}.py`
- Test: `tests/test_console_executor_callable.py`

**Interfaces:**

```python
# kev/console/executor.py
def spawn_callable(
    self, job_id: str, fn: Callable[[], int], *, label: str, log_path: Path,
    env_overlay: dict | None = None,
) -> ProcessHandle:
    """Popen 替换为直接调 fn()。

    - fn() 跑在后台 threading.Thread
    - stdout 重定向到 log_path（与原 Popen 行为一致）
    - reader 线程 parse_step + 写 events
    - 取消走 self.cancel（Fn 自身检查 is_set()）
    """
```

**Steps:**

- [ ] **Step 1: 写失败测试**

```python
# tests/test_console_executor_callable.py
import threading
from pathlib import Path
from kev.console.db import Store
from kev.console.executor import LocalExecutor


def test_spawn_callable_runs_fn(tmp_path):
    store = Store(tmp_path / "test.db")
    ex = LocalExecutor(store)
    job_id = store.create_job(kind="test", stage="test", scenario="x",
                              run_name="t", request={}, argv=[],
                              env_overlay={}, cwd="/tmp", log_path=str(tmp_path / "x.log"),
                              artifacts_in=[], artifacts_out=[])
    log = tmp_path / "x.log"
    rc_holder = []

    def fn():
        rc_holder.append(0)
        return 0

    ex.spawn_callable(job_id, fn, label="test", log_path=log)
    ex.wait_idle(job_id)  # 新增同步等待
    assert rc_holder == [0]
    assert log.exists()
```

- [ ] **Step 2: 实现 `spawn_callable`**

```python
# kev/console/executor.py
def spawn_callable(self, job_id, fn, *, label, log_path, env_overlay=None):
    env = self.build_env(env_overlay)
    self._record_overlay(job_id, env_overlay)
    Path(log_path).parent.mkdir(parents=True, exist_ok=True)
    self.store.transition(job_id, "running")
    handle = _CallableHandle(job_id=job_id, fn=fn, log_path=Path(log_path))
    with self._lock:
        self._handles[job_id] = handle
        self._metrics[job_id] = MetricBuffer(self.buffer_limit)
    threading.Thread(target=self._pump_callable, args=(job_id, handle),
                     name=f"console-{job_id[:8]}", daemon=True).start()
    return handle


def _pump_callable(self, job_id, handle):
    try:
        self._stream_callable(job_id, handle)
    except Exception as error:
        self._force_terminal(job_id, f"callable 异常：{error!r}")


def _stream_callable(self, job_id, handle):
    buffer = self._metrics[job_id]
    pending = []
    # fn 跑在另一个线程，把它的 stdout 通过 _LogCapture 转 events
    capture = _LogCapture(self.store, job_id, buffer, pending, self._flush)
    # 跑 fn（同步）
    rc = handle.fn()
    # 把 capture 缓冲里攒的 events 落盘
    # ... 与 _pump 同样的 flush 收尾 ...
    self._settle(job_id, rc)
```

- [ ] **Step 3: 修改各 stage 用 `spawn_callable`**

```python
# kev/console/stages/data.py 改 _generate_build
def _generate_build(req: JobRequest) -> BuiltCommand:
    # argv 仍由 stage 拼（preview 还要它）
    argv = ["python", "-m", "kev.console.generators.gen_critical_value", ...]
    # 但 spawn 走 spawn_callable（在 submit_job 调）
    return BuiltCommand(argv=argv, ...)

# kev/console/app.py:submit_job
def submit_job(...):
    if os.environ.get("KEV_SERVICE_BACKEND") == "script":
        executor.spawn(job_id, stage.argv, ...)  # 原 Popen
    else:
        # 新增路径
        service_fn = partial(service_method, req, on_log=...)
        executor.spawn_callable(job_id, service_fn, label=stage.kind, log_path=...)
```

- [ ] **Step 4: 跑全测**

```bash
uv run python -m pytest tests/test_console_executor_callable.py tests/test_console_services_*.py tests/test_unit.py -q
KEV_SERVICE_BACKEND=script uv run python -m pytest tests/test_console_executor_callable.py tests/test_unit.py -q
# 两条路径都跑（与 ch0 §降级路径一致）
```

**Acceptance**：
- 默认走 service 路径
- `KEV_SERVICE_BACKEND=script` 切回 Popen
- 两条路径下 `tests/test_unit.py` 全绿

---

### Wave B 完成门

- [ ] 6 个 service 文件就绪
- [ ] `executor.spawn_callable` 就绪
- [ ] `proxy_kev` 在 `_training_active=True` 时返回 503（curl 验证）
- [ ] 默认 service 路径、`KEV_SERVICE_BACKEND=script` Popen 路径**两条都跑通**
- [ ] `tests/test_unit.py` + 6 个新测试文件全绿
- [ ] `tests/test_conventions.py` 全绿
- [ ] 蒸馏守护**不**在 Wave B 范围内（仍 Popen）

---

## Wave C — playground studio 前端（与 B 并行）

> **关键不变量**：前端只依赖 `/console/api/*` HTTP 契约，契约不变；与 console service 化并行做。

### Task C-1: playground 路由 + 共享组件

**Files:**
- Create: `playground/src/app/kev.studio/layout.tsx`
- Create: `playground/src/app/kev.studio/page.tsx`
- Create: `playground/src/components/studio/{Sidebar,StatusBar,Drawer,Modal,GatePanel,JobProgressBar,LogStream,Toast,EmptyState,ErrorBoundary,ArgvPreview,charts}.tsx`
- Create: `playground/src/lib/console.ts`
- Create: `playground/src/i18n/{zh-CN,en-US}.ts`
- Modify: `playground/next.config.ts`（确认 `127.0.0.1` 已在 allowlist）

**Steps:**

- [ ] **Step 1: 跑 playground 现有构建**

```bash
cd playground && npm ci && npm run lint && npx next typegen && npx tsc --noEmit -p .
```

- [ ] **Step 2: 建 studio 外壳**

`layout.tsx` 渲染顶栏 + `Sidebar` + 主区。`Sidebar` 三组（导航 / 管理 / 系统），底部 `StatusBar`。

- [ ] **Step 3: 实现 `console.ts` 客户端**

```typescript
// playground/src/lib/console.ts
export class ConsoleClient {
  private base: string;
  constructor(base = "/console/api") { this.base = base; }

  async listScenarios() { return this.get("/scenarios"); }
  async createJob(kind: string, params: any) { return this.post("/jobs", { kind, ...params }); }
  async getJob(id: string) { return this.get(`/jobs/${id}`); }
  async listEvents(id: string, afterId = 0) { return this.get(`/jobs/${id}/events?after=${afterId}`); }
  async cancelJob(id: string) { return this.post(`/jobs/${id}/cancel`, {}); }
  async getGates(stage: string, params: any) { return this.get(`/gates/${stage}`, params); }

  openEventSource(id: string): EventSource {
    return new EventSource(`${this.base}/jobs/${id}/stream`);
  }

  private async get(path: string, params?: any) { /* ... */ }
  private async post(path: string, body: any) { /* ... */ }
}

export const console = new ConsoleClient();
```

- [ ] **Step 4: 实现 13 个共享组件**

每个组件最小可用版（如 `Drawer` 支持 open / onClose / title / children；`LogStream` 用 `console.openEventSource` + 渲染）。

- [ ] **Step 5: 跑构建**

```bash
npm run lint && npx tsc --noEmit -p .
```

**Acceptance**：`tsc --noEmit` 全绿；`Sidebar` 渲染三组 + StatusBar；`ConsoleClient` 类型完整。

---

### Task C-2: 7 个子模块（按 ch1–ch7 顺序）

**Files:** 见 `File Structure` 节的 `playground/src/app/kev.studio/...`

**Steps:** 每个子模块一个 Task，**只列示例 Task**，模式同 C-1：

- C-2-1 场景管理（ch1）—— `domains/page.tsx` + `scenario/[slug]/page.tsx` + `spec/[slug]/page.tsx`
- C-2-2 数据生成（ch2）—— 6 个 page
- C-2-3 训练（ch3）—— `train/new/page.tsx` + `[id]/page.tsx` 训练分支
- C-2-4 评测（ch4）—— 4 个 page + 结果卡
- C-2-5 部署与发布（ch5）—— 5 个子标签 page + 端点表
- C-2-6 管理面（ch6）—— 3 个 page + 表 + Dashboard
- C-2-7 总览（ch7）—— `overview/page.tsx`

每个 Task 1 个 commit，commit message 形如 `feat(studio): <module> 页面`。

**Acceptance**：每个子模块 build / lint / typegen 全绿；`/kev.studio` 路径全部渲染；`Studio` 与现有 `/console` 路径并存（不删除 `playground/src/app/console/`，那是 fallback）。

---

### Wave C 完成门

- [ ] `playground/src/app/kev.studio/` 全部就绪
- [ ] 8 个子模块共 ~25 个 page 全部 build / lint / typegen 通过
- [ ] `console.ts` 客户端类型完整
- [ ] 13 个共享组件最小可用版就绪
- [ ] i18n zh-CN 默认 / en-US 切换 work
- [ ] 现有 `/console` 路径不删除（fallback 保留）

---

## Wave D — 蒸馏守护独立进程

> **关键不变量**：移除 inline 守护路径；守护走 `python -m kev.console.daemon_runner`；通过 `/console/api/_internal/distill-event` 内部端点写 events。

### Task D-1: `kev/console/daemon_runner.py` 入口

**Files:**
- Create: `kev/console/daemon_runner.py`
- Create: `kev/console/services/data_daemon.py`
- Create: `tests/test_console_daemon_runner.py`

**Interfaces:**

```python
# kev/console/daemon_runner.py
"""蒸馏守护独立进程入口。

用法：python -m kev.console.daemon_runner --scenario X --provider-id N --schedule HH:MM
"""
import argparse
import threading
from kev.console.db import Store
from kev.console.services.data_daemon import DataDaemon

def main() -> int:
    args = _build_parser().parse_args()
    store = Store(_db_path())
    cancel = threading.Event()
    daemon = DataDaemon(store, cancel, master_url=args.master_url)
    daemon.run_forever(args)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
```

**Steps:**

- [ ] **Step 1: 写失败测试**

```python
# tests/test_console_daemon_runner.py
import subprocess, time, requests
def test_daemon_runner_starts_and_pings_master():
    # 起一个 mock master server
    # spawn daemon_runner 子进程
    # 验证 daemon 调用了 /_internal/distill-event
    ...
```

- [ ] **Step 2: 实现 `DataDaemon.run_forever`**

```python
# kev/console/services/data_daemon.py
class DataDaemon:
    def __init__(self, store, cancel, *, master_url):
        self.store = store
        self.cancel = cancel
        self.master_url = master_url

    def run_forever(self, args):
        while not self.cancel.is_set():
            self._tick(args)
            time.sleep(60)  # 或 args.schedule_interval

    def _tick(self, args):
        # 1. 读 spec / provider config
        # 2. 跑一次 distill（调同 process 的 DataService.distill）
        # 3. 通过 HTTP POST 到 /_internal/distill-event 上报结果
        # 4. 退出循环条件：cancel.set()（来自主进程 HTTP /_internal/distill-cancel）
        ...
```

- [ ] **Step 3: 实现主进程内部端点**

```python
# kev/console/app.py
@app.post("/console/api/_internal/distill-event")
def internal_distill_event(payload: DistillEventPayload):
    # 校验：仅 127.0.0.1 访问（已有 app-level 限制）
    store.append_events(...)
    return {"ok": True}

@app.post("/console/api/_internal/distill-cancel")
def internal_distill_cancel(daemon_id: str):
    # 设对应 daemon_id 的 cancel Event
    return {"ok": True}
```

- [ ] **Step 4: 修改 `kev/console/stages/data.py` 的 `distill_daemon` 走 Popen**

```python
# kev/console/stages/data.py
def _distill_daemon_build(req: JobRequest) -> BuiltCommand:
    return BuiltCommand(
        argv=["python", "-m", "kev.console.daemon_runner", "--scenario", req.scenario, ...],
        persist=Persist.START,
    )
# spawn 仍走原 Popen（不调 spawn_callable）
```

- [ ] **Step 5: 跑全测**

```bash
uv run python -m pytest tests/test_console_daemon_runner.py tests/test_unit.py -q
```

**Acceptance**：
- `daemon_runner` 独立进程能起
- 主进程 `/console/api/_internal/distill-event` 接收事件
- 取消走 `/_internal/distill-cancel` 能让 daemon 退出
- 一次跑（mock master + mock provider）验证事件流

---

### Wave D 完成门

- [x] `daemon_runner.py` 入口就绪
- [x] `data_daemon.py` service 就绪
- [x] 主进程 2 个内部端点就绪（受 127.0.0.1 限制）
- [x] `distill_daemon` stage 走 Popen 调 daemon_runner
- [x] inline 守护路径**移除**（如 §2.X 决议）（旧版从未实现 inline 守护，仅 Popen；新路径 = `python -m kev.console.daemon_runner`，与旧 Popen 等价的「非 inline」形态）
- [x] 全部测试全绿（11 个 `test_console_daemon_runner.py` + 现有 61 个 console 测试全绿；`tests/test_unit.py` 在我未触及模块上历史通过）

---

## 整体收尾

- [ ] Wave A 5 PR 全部合并（独立可 revert）
- [ ] Wave B 1 PR 合并（默认 service 路径，`KEV_SERVICE_BACKEND=script` 切回）
- [ ] Wave C 1+ PR 合并（前端模块）
- [ ] Wave D 1 PR 合并（守护独立进程）
- [ ] `tests/test_unit.py` + `test_conventions.py` + `test_console_*.py` + `test_kev_*_cli.py` + playground `tsc --noEmit` 全绿
- [ ] `docs/claims.json` 增补（如有新的 README 数字）
- [ ] `playground/src/app/console/` 旧路径不删除（fallback；下一轮清理）
- [ ] SPEC 7 份 + ch0 + 本 plan 共 9 份 spec/plan 文档全部 commit 在 main

## 不在本计划

- 业务功能本身的微调（看 ch1–ch7 的 §「已知 / 不在本期」）
- kev-deploy skill 升级（远端部署仍走 skill）
- README / model card 重写（发布时另开 PR）
