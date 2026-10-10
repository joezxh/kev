# Studio 控制台 · 第 3 章：训练

> 第 7 章中的第 3 章。单 stage（`train`）但最复杂：3 种 method（a1 / a2 / b）、21 项 ADVANCED 折叠、3 道闸门（G1/G2/G3）、运行时视图。后端契约在 `kev/console/stages/train.py`；闸门逻辑在 `kev/console/gates.py`。

## 表单与方法切换器

`#jobs`「+ 新建作业」模态选 `train` 打开训练表单。表单顶部一个 segmented control 切 3 种 method：

- **a1（LoRA 热启动，推荐）** — `init_from` = 上一发布版 checkpoint（默认 `jaredpalmer/kev-0.8b`，非 `FOUR_B_ONLY` 场景）
- **a2（LoRA 裸基座）** — `init_from` = 同 base，无 adapter
- **b（全参数）** — `--full_ft 1`、`weights_dtype=bf16`；**只能配 4B 轨**（`FOUR_B_ONLY` 场景在 `data.py:158-160` 拒绝 a1/a2）

切换 method 时表单字段重新拉取默认（来自 `train_stages.methods_for(scenario)`，已实现于 `app.py:285-288`）。

## 字段分区

| 分区 | 字段 | 适用 method |
|---|---|---|
| 基础 | scenario, run_name, method, data, epochs=1, batch=4, accum=2 | 全部 |
| 微调参数 | lr（8b=4e-5 / 4b=2e-5）, lora=16, lora_targets=all | a1 / a2 |
| 全参专属 | full_ft=1, weights_dtype=bf16, shared_prefix=1, length_sort=1, row_budget（仅 1 GPU） | 仅 b |
| 快照 | max_steps, snapshot_fractions, snapshot_dir | 仅 b（`MAX_SNAPSHOTS=8` 硬约束） |
| 校验 | replay=2000（b=0） | 全部 |
| 杂项 | head_dim=256, checkpointing, init_from | 全部 |
| **ADVANCED（折叠）** | anchor, anchor_w, anchor_sources, perm_kl, perm_frac, ord_w, label_smoothing, brier_w, focal_gamma, p_none, p_none_distract, p_distract, p_none_pair, none_pair_max_state, synthetic_repeat, public_frac, train_sources, holdout, pass_tokens_max, snapshot_every_steps, snapshot_hub_repo | 全部 |

## 闸门预检条（关键 UX）

表单上方**永远显示**当前闸门状态，**不阻塞编辑**（点提交时才硬拦）：

```
G1 precheck  ✓  over_limit=0
G2 split     ✓  summary.records=787 == plan.total_records=787
G3 labels    ⚠  invalid_lines=0, label_warnings=2  [查看]
G1+G2+G3 全部通过才能提交
```

- 数据源：`GET /console/api/gates/train?scenario=...&run_name=...&data=...`（已实现 `app.py:664-678`）
- scenario / data / method 变化时**防抖重拉**（500ms）
- 「查看」展开 `label_warnings` 详情（从 `dataset:{dir}/summary` 解析）

## 单 GPU 软锁

后端在 `submit_job` 里已检查（`app.py:491-497`）—— 已有训练在跑就 409。UI 额外做软提示：

- 顶部状态条「GPU 锁 · 占用（作业 abc12345）」（来自 system 组那一行）
- 提交按钮在已有训练在跑时**仍然亮**但点击提示「已有训练在跑，请等待」

## 训练运行时视图（`#jobs/<id>` 训练专属段）

`#jobs/<id>`（已存在，训练作业追加专属段）：

- **顶部进度条**：从日志解析 `step` / `total_steps` / `loss`（用 `kev.plot` 同样的解析逻辑）；实时刷
- **GPU 指标**：allocated MiB / peak（来自 `executor.metrics`）
- **日志区**：SSE 事件流 + 折叠的「完整日志」标签
- **产物链接**：`run:{name}` 卡（路径 `runs/{name}`）+ 训练配置 JSON 折叠 + 训练指标 `training_metrics.json` 折叠

## 前端位置

playground 新增 `playground/src/app/kev.studio/jobs/train/`：

- `new/page.tsx`（训练表单 + method 切换器 + 闸门条 + ADVANCED 折叠）
- `components/TrainFormShell.tsx`（三 method 共享外壳）
- `components/GatePanel.tsx`（闸门条，§4.7 / §5.8 复用）
- 训练运行时视图放在 `kev.studio/jobs/[id]/page.tsx` 的 stage 分支 `if kind === 'train'`
- API 封装在 `playground/src/lib/console.ts`，URL 前缀 `/console/api`

## 3.X Service 层重构 · 训练阶段

**目标**：把 `kev/console/stages/train.py` 由「拼 argv → spawn 子进程跑 kev.train 脚本」改为「FastAPI 进程内 import `kev.train.run` 同步调用」。**SSE / events / metrics buffer 全部保留**。

### Service 接口

新建 `kev/console/services/train.py`：

```python
class TrainService:
    def __init__(self, store: Store, cancel: threading.Event, gpu_lock: threading.Lock):
        self.store = store
        self.cancel = cancel
        self.gpu_lock = gpu_lock

    def train(self, req: JobRequest, *, on_log, on_metric) -> dict:
        # 内部：acquire gpu_lock, args=stage._build_request(req), run(args)
        # on_log / on_metric：把 kev.train 输出与 metrics 写回 events 表
        # 返回：{"run_dir": ..., "training_config": ...}
        ...
```

### 改造点

1. **同进程 import torch / transformers**——`kev.train` 已在同 repo，`from kev.train import run`；意味着 console 进程真的占 GPU 显存
2. **拆 `kev/train.py` CLI 块**：`if __name__ == "__main__"` 抽出；新增 `def run(args: argparse.Namespace) -> int: ...` 纯函数；保留原 argv / 字段语义（service 拼 Namespace 而非 shell 字符串）
3. **GPU 锁**：`executor.spawn_callable` 内 `with self.gpu_lock:` 包裹 service 调用；UI 软提示与后端 409 都保留
4. **取消机制**：`kev.train` 加 `kev.train.cancel: threading.Event` 模块级；训练 step 函数每 N 步检查一次，置位则抛 `TrainCanceled`（**反向依赖，要单独走 PR 改 kev/ 核心包**——本次重构唯一对核心包的侵入）
5. **快照 / resume / snapshot_hub_repo**：`kev.train` 内部已处理（`experiment.SNAPSHOT_FRACTIONS`），service 不感知
6. **`init_from` Hub id 校验**：`kev.checkpoint.resolve` 已能校验；service 失败信息通过 on_log 暴露
7. **FOUR_B_ONLY 校验**：`data.py:158-160` 已有，service 调用前 stage 已抛 Invalid

### 训练与推理同进程的并发

`kev.serve` 8008 同时承载推理 + 编排，训练时会争抢 GPU 显存。**正式机制**（用户决议 3）：

- service 启动训练前设置 `_training_active = True` 进程标志
- `app.py:proxy_kev` 检测该标志，返回 503 `{"error": "训练占用 GPU，推理临时不可用"}`
- 训练完 service 清标志，proxy 自动恢复
- 此耦合写在 `kev/console/services/train.py` 与 `kev/console/app.py` 两处；`_training_active` **不**暴露到浏览器（仅进程内 + `proxy_kev` 内的 `request.app.state._training_active`）
- **只影响**控制台与训练共进程的部署场景；只用推理不开训练的部署（kev-deploy 走 Modal / 独立容器）**不受影响**——`kev-deploy` 走 `kev_serve.py` 不走 console，故 `_training_active` 恒为 False

### 依赖新增

- `kev/console/services/train.py`（一个 service 方法 `train`）
- `kev/console/services/eval.py`（见 §4.X）
- `kev/train.py` 改动：拆 CLI 块、暴露 `run()` + `cancel` Event（**反向依赖**）

### 风险

- 训练数小时级阻塞单 worker 是预期；其余 UI 请求走 FastAPI 默认线程池
- GPU 显存争抢：4B bf16 ≈ 8 GB，Kev-27B 不可能同进程（已有约定 `kev-deploy` 走独立 Modal 容器）；4B 同进程也需 503 降级（机制如上）
- 训练 service 抛异常后，executor 必须把 job 标 failed（不能让 reader 线程吞）——`spawn_callable` 包装层 try/except 推到终态

## 已知 / 不在本期

- 训练中**取消**走 `/jobs/{id}/cancel`（已实现）
- **重试**自动 `run_name-r{attempt}` 改名（已实现 `app.py:558-569`）
- 训练中不能改 method（必须新开一个）
- 训练指标 `grad_norm` / `backbone_save_seconds` / `snapshots` 折叠在"训练配置"下，不做图表
- snapshot_hub_repo 是字段，但上传由 `kev.mirror` 后台负责，UI 仅展示 `snapshot.json["hub"]`
