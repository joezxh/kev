# Studio 控制台 · 第 4 章：评测

> 第 7 章中的第 4 章。承接 `docs/pipeline.md` §2.3，覆盖 4 个 stage：baseline / benchmark / compare / calibrate，4 道闸门 G4/G5/G6/G7。核心约束：G4 与 G6 来自不同 comparison 产物（L3 已修，`compare --public` 产 `regression:{run}`）。

## 4.1 入口

`#jobs` 「+ 新建作业」选 `baseline` / `benchmark` / `compare` / `calibrate` 进入对应表单。

## 4.2 baseline（零样本对照）

| 字段 | 默认 | 说明 |
|---|---|---|
| run_name | `{run_name}-baseline` | 不可与 `run_name` 同名 |
| baseline | `jaredpalmer/kev-0.8b` | 其它已部署 checkpoint（`/console/api/endpoints` 拉） |
| device | `cuda` | 也可选 `cpu` / `mps` |
| data | `data/{scenario}/development.jsonl` | **UI 已可设**（L2 修复） |
| suite / split / allow_test | — | baseline 默认打 development 分区，不暴露 suite |

提交后产物 `eval:{run}-baseline` → 写 `runs/{run}-baseline-eval/{report,rows}.json`。

## 4.3 benchmark（开发集打分）

| 字段 | 默认 | 说明 |
|---|---|---|
| run | （必填，选 `run:{name}`） | 与 baseline 的 `suite_sha256` 必须一致 |
| device | `cuda` | |
| data | `data/{scenario}/development.jsonl` | |
| suite | （可选，下拉冻结套件 `decision-v7` / `transfer-v4` / `transfer-v9` / `breadth-v1` / `external/ekzhang-mmlupro-v1`） | L2 修复后**已暴露** |
| split | `development` | |
| allow_test | ⚠ 警告提示 | 选 `test` 时**弹确认**「将消费一次性确认读，不可再用」 |
| date_facts | 开关 | 启用 `KEV_DATE_FACTS=1` 预处理 |
| rotations | int | permutation 测试次数 |
| remote / remote_model / remote_concurrency | 三个一组 | 选远端时同时显示 |

提交后产物 `eval:{run}` → 写 `runs/{run}-eval/{report,rows,calibration?}.json`。

**特别 UI**：底部自动显示「是否要同时跑 baseline」提示（如该 run 还没有 baseline 产物），按钮直接拉起 baseline 表单预填 run_name。

## 4.4 compare（配对 bootstrap）

| 字段 | 默认 | 说明 |
|---|---|---|
| candidate | `runs/{run}-eval` | 来自 `run:{name}` |
| reference | `runs/{run}-baseline-eval` | |
| public | 开关 | **打开时**改走 `compare --public` 路径，产物变 `regression:{run}`（G6 证据） |
| candidate_ref / reference_ref | （仅 `public=1` 时显示） | 选 public 套件路径，用于回归读 |

提交前**强制显示**两侧的 `suite_sha256` 摘要（来自两侧 report.json）+ 一致性 ✓/✗；后端在 `submit_job` 已 409（`app.py:498-507`），前端早一步拦。

## 4.5 calibrate（温度拟合）

| 字段 | 默认 | 说明 |
|---|---|---|
| rows | `runs/{run}-eval/rows.json` | 不可改 |
| group_disjoint | 开关 | 打开走 OOF 拟合（默认 on） |

无产物侧配置（calibrate 走的是 `kev.calibrate`），不暴露 cv_folds 等细节（脚本自带合理默认）。

## 4.6 结果可视化（`#jobs/<id>` 评测专属段）

评测类作业详情页（在 §3.5 通用 job 详情基础上）追加：

- **顶部数字卡**（4 列）：accuracy / ECE / Brier / NLL（取自 `report.json` summary）
- **per-question 折叠表**：行 = question_id，列 = `pred / gold / p_top / logit_gap / flip_count`
- **compare 作业专属**：左侧 baseline / 右侧 candidate，**逐行** `flip ✓/✗ / Δlogit` 表格（10 条样例 + 「加载更多」分页）
- **calibrate 作业专属**：
  - 当前温度 T（来自 `calibration.json`）
  - 拟合曲线（`kev.calibrate` 自身用 matplotlib，studio 端不做 matplotlib，复用 SVG 块）
  - 警告：若 `workload_oof.ece > shipped.ece` 则弹黄条「OOF 劣于 in-sample，建议手工温度」

## 4.7 闸门预检条（与 train 同款）

`#jobs` 评测类 stage 顶部同样显示 G4-G7 状态：

- G4：`comparison:{run}` CI95 下限 `> 0`
- G5：`eval:{run}.calibrated_clean.ece < clean.ece`
- G6：`regression:{run}` CI95 下限 `>= -0.02`（`REGRESSION_TOLERANCE`，已实现）
- G7：`calibration:{run}.workload_oof.ece <= shipped.ece`

G6 必须先跑一次 `compare --public` 才有产物。状态条直接调用 `GET /console/api/gates/{stage}` 拉。

## 4.8 前端位置

新增 playground 模块 `playground/src/app/kev.studio/jobs/eval/`：

- `baseline/page.tsx`、`benchmark/page.tsx`、`compare/page.tsx`、`calibrate/page.tsx`
- 共享组件 `components/EvalFormShell.tsx`（4 列数字卡 + 字段网格 + 闸门条 + 提交）
- 详情页追加组件 `components/EvalResultCard.tsx`、`components/CompareFlipTable.tsx`、`components/CalibrateCard.tsx`
- 现有 `playground/src/lib/kev.ts` 的 `presets` 不动；studio 模块自管 state

API 调用统一封装在 `playground/src/lib/console.ts`（沿用 §1–§3 的封装），URL 前缀 `/console/api`。

## 4.X Service 层重构 · 评测阶段

**目标**：把 `kev/console/stages/eval.py` 4 个 stage 由「拼 argv → spawn 子进程」改为「FastAPI 进程内 import 业务函数 → service 同步调用」。

### Service 接口

新建 `kev/console/services/eval.py`：

```python
class EvalService:
    def __init__(self, store: Store, cancel: threading.Event, gpu_lock: threading.Lock):
        ...

    def baseline(self, req: JobRequest, *, on_log, on_metric) -> dict: ...
    def benchmark(self, req: JobRequest, *, on_log, on_metric) -> dict: ...
    def compare(self, req: JobRequest, *, on_log) -> dict: ...
    def calibrate(self, req: JobRequest, *, on_log) -> dict: ...
```

### 改造点

1. **`baseline` / `benchmark`**：内部调 `kev.benchmark.run(parsed_args)`；拆 `kev/benchmark.py` 的 CLI 块（与 train 同模式）
2. **`compare`**：内部调 `kev.compare.run(...)`；`suite_hash_mismatch` 预检从 `eval_stages` 抽到 service
3. **`calibrate`**：内部调 `kev.calibrate.run(...)`；同样拆 CLI
4. **GPU 锁**：`baseline` / `benchmark` 抢同一把锁（与 train 互斥）
5. **取消**：`kev.benchmark` 内部 step loop 加 `cancel` 检查（与 train 同模式，**反向依赖 PR 同样要改 kev/ 核心包**）
6. **`compare` / `calibrate` 是纯 CPU**：不抢 GPU 锁，可与 train 并发

### 依赖新增

- `kev/console/services/eval.py`（4 个 service 方法）
- `kev/benchmark.py` / `kev/compare.py` / `kev/calibrate.py` 拆 CLI 块、暴露 `run()` + `cancel` Event

### 不动

- `kev/compare` 的配对 bootstrap 算法 / `kev/metrics.py` 全部
- `kev/calibrate` 的 OOF / 拟合曲线
- G4-G7 闸门判据

### 风险

- 评测同样占显存（4B bf16），与 train 互斥缓解已写在 §3.X
- `compare` / `calibrate` 短作业（数分钟）不阻塞 UI

## 4.9 已知 / 不在本期

- 不做 calibration curve 图表（只显示数字 + bootstrap CI）
- 不做 selective-coverage / AURC 图表
- 不在 UI 改 `rotation` / `permutation` 高级参数
- `calibrate` 的 OOF folds 默认 4（前缀与 `kev.calibrate` 一致），不暴露
