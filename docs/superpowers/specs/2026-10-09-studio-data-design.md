# Studio 控制台 · 第 2 章：数据生成

> 第 7 章中的第 2 章。承接 `docs/pipeline.md` §2.1，覆盖 9 个 stage：plan_size / generate / distill / distill_daemon / make_examples / goldset / goldset_audit / split / precheck。后端契约在 `kev/console/stages/data.py`。

## 入口与导航

`#datasets` 改为 5 个子标签：

| 标签 | 用途 |
|---|---|
| 概览 | 每场景汇总：计划记录数、实际记录数、数据集产物，plan_size 按钮 |
| plan_size | 最近 plan_size 作业结果表 |
| 生成 / 蒸馏 | generate / distill / distill_daemon / make_examples 发起入口（表单区） |
| 切分与预检 | split / precheck / goldset 入口 + 已切分产物浏览 |
| 历史 | 所有 data 类作业时间线 |

## 9 个表单的差异点（来源 `data.py`）

| 阶段 | 关键字段 | 默认值来源 | 关键约束 |
|---|---|---|---|
| `plan_size` | (无字段) | 不可设 | UI 仅一个按钮，点击直接提交 |
| `generate` | n=787, seed=0, data=`data/{scenario}` | `data.py:163-170` | 输出已存在 → 409，`skip_exists_check=1` 可绕过 |
| `distill` | provider_id, category, n=787, model, concurrency=3, examples, n_examples=4, state_dir | `data.py:185-244` | spec 路径必须存在；examples 是 `dataset:{dir}/examples` 路径 |
| `distill_daemon` | 同上 + schedule（必填） | 同上 | 必填 `HH:MM`；跳过目录存在预检；产物 spawn 后立刻注册 |
| `make_examples` | data, n=8, seed=0, out | `data.py:380-400` | 源 JSONL 必填；输出存在 → 409 |
| `goldset` | n=200, seed=0, data, out | `data.py:280-290` | 输出存在 → 409 |
| `goldset_audit` | a, b, out, threshold=0.05 | `data.py:300-320` | 两份独立标注 JSONL |
| `split` | calibration=0.15, development=0.15, seed=0, holdout, data | `data.py:330-340` | 输入 JSONL 必存在；输出目录存在 → 409 |
| `precheck` | data, split ∈ {train,calibration,development}, init_from=`jaredpalmer/kev-0.8b` | `data.py:355-370` | split 必填；输出路径由 `artifacts.resolve` 决定，不手拼 |

## 统一表单组件

所有 18 个 stage 共享一个表单组件（数据驱动，字段定义集中在 `stages.ts` 常量）：

- **顶部 scenario 切换器**（默认来自 URL hash，否则取 `/config` 接口的第一个）
- **字段网格**（桌面两列，窄屏单列）
- **ADVANCED 折叠**：仅 `train` 的 21 项；data 类 stage 字段不多，不折叠
- **提交区**：
  - 主按钮「预览 argv」+ 副按钮「提交」
  - 预览调 `POST /console/api/jobs/preview`（已存在）并把 argv 渲染为代码块
  - 提交 → 422 时把闸门失败明细渲染为红条列表（每条 `id` / `detail` / `actual` / `need`）
- **成功反馈**：跳 `#jobs/<id>`，3 秒后弹 toast「<stage> 已入队，<id>」

## 蒸馏特殊项

`distill` 与 `distill_daemon` 共用表单，顶部一个「守护模式」开关：

- 关闭：表单为 `distill`；提交走一次性蒸馏
- 开启：表单额外显示 `schedule HH:MM`（必填，校验 `^([01]\d|2[0-3]):[0-5]\d$`）+ 「守护模式：进程将持续到手动取消」说明

`provider_id` 是下拉，选项来自 `/console/api/distill-providers`；选中后**仅在 UI 缓存 base_url / model / daily_limit 副本**（后端不返回凭据；凭据规则见第 7 章 §7.7）。

**examples 路径**：下拉 `few-shot 范例` 选项来自 `dataset:{scenario}/examples` 产物 + 「从已标注 JSONL 抽样」链接（跳到 make_examples 表单）。

## plan_size → 概览回灌

- 「+ Plan size」按钮立即提交一个 plan_size 作业
- 作业成功后，事件流里 `system` 标签下出现「plan 落盘成功：data/console/plan-<scenario>.json」或失败原因（已实现）
- 「概览」标签的「计划 vs 实际」表：每行 = 场景，调 `/console/api/artifacts?kind=plan` 与 `?kind=dataset&name=<scenario>/summary` 拼出
- 缺 plan 时显示「请先跑 plan_size」+ 计划按钮；缺 summary 时显示「请先跑 split」

## 关键设计原则

1. **统一 stage 表单组件**：所有 18 个 stage 共享「字段网格 + argv 预览 + 闸门失败条」三件套，差异只在字段定义（数据驱动）
2. **数据驱动**：每个 stage 的字段定义（含 type / default / help / advanced）抽到一份 `stages.ts` 静态常量；后端若改默认，前端通过新增的 `GET /console/api/stages/{kind}/defaults` 端点跟齐（见下文）
3. **后端改动只有 1 个新端点**：`GET /console/api/stages/{kind}/defaults` —— 返回字段名、类型、是否 advanced、help 文本；不带任何业务逻辑

## 新增后端端点

```
GET /console/api/stages/{kind}/defaults
```

返回：

```json
{
  "kind": "generate",
  "fields": [
    {"key": "n", "type": "int", "default": 787, "advanced": false, "help": "记录数"},
    {"key": "seed", "type": "int", "default": 0, "advanced": false, "help": "随机种子"},
    {"key": "data", "type": "str", "default": "data/{scenario}", "advanced": false, "help": "..."},
    {"key": "skip_exists_check", "type": "bool", "default": false, "advanced": true, "help": "..."}
  ],
  "outcome": "接着跑 goldset（可选）与 split",
  "four_b_only": false
}
```

端点读 `REGISTRY[kind]` 内省（无新业务逻辑）。前端在表单挂载时拉取；该端点上线前临时回退到 `stages.ts` 手维护表（可接受）。

## 前端位置

playground 新增 `playground/src/app/kev.studio/datasets/`：

- 5 个子标签对应 `overview/`、`plan-size/`、`generate/`、`distill/`、`split-precheck/`、`history/` 6 个 page
- 共享 `components/StageForm.tsx`（含字段网格 + argv 预览 + 闸门条 + 提交）
- 共享 `components/DistillForm.tsx`（distill / distill_daemon 共用，顶部守护模式开关）
- API 封装在 `playground/src/lib/console.ts`，URL 前缀 `/console/api`

## 2.X Service 层重构 · 数据阶段

**目标**：把 `kev/console/stages/data.py` 9 个 stage 由「拼 argv → spawn 子进程跑脚本」改为「FastAPI 进程内 import 业务函数 → service 同步执行」。**前端的 /jobs/{id}/stream SSE、events 表、metrics buffer 全部保留**。

### Service 接口

集中在新建包 `kev/console/services/data.py`：

```python
class DataService:
    def __init__(self, store: Store, cancel: threading.Event):
        self.store = store
        self.cancel = cancel  # 进程内全局 Event；作业级取消=写作业级标志 + 此 Event

    # console 仓库自有的业务层（kev/console/{generators,precheck,make_examples}）
    def generate(self, req: JobRequest, *, on_log: Callable[[str], None]) -> dict: ...
    def goldset(self, req: JobRequest, *, on_log) -> dict: ...
    def goldset_audit(self, req: JobRequest, *, on_log) -> dict: ...
    def precheck(self, req: JobRequest, *, on_log) -> dict: ...
    def make_examples(self, req: JobRequest, *, on_log) -> dict: ...

    # 走 skill 脚本的 stage（plans_size / distill / distill_daemon / split）仍走
    # 原 Popen 路径调 skills/kev-finetune/scripts/*；不进 service（避免 console 对
    # skill 仓库产生反向依赖；skill 独立发版）。本类**不**为它们提供方法。
```

### 改造点

1. `kev/console/stages/data.py` 的 9 个 `_xxx` 函数中，**仅 4 个**（`_generate` / `_goldset` / `_goldset_audit` / `_precheck` / `_make_examples`）改为直接调对应 service 方法；`_plan_size` / `_distill_build` / `_split` **保持 Popen**（`kev/console/stages/data.py` 与 `kev/console/executor.py` 不动），仍调 skill 脚本
2. `kev/console/executor.py` 的 `spawn` 保留签名，**新增** `spawn_callable(job_id, fn, *, label, log_path)` —— `fn` 是 service 方法 + 闭包（`partial(service.generate, req, on_log=...)`）；不再有 Popen。仅 service 化的 stage 用 `spawn_callable`，其它仍用 `spawn`
3. 每个 service 方法周期性检 `self.cancel.is_set()`（数据阶段秒级完成，无守护循环）
4. 生成 / 蒸馏 / 切分 / 预检的 on_log：原脚本往 stdout 写进度，调 service 后**直接** `events.append(job_id, "stdout", line)` + `metrics.push(parse_step(line))`；events 表与 metrics buffer 是 service 唯一可写点
5. 守护蒸馏：保留循环（service 内 `while not self.cancel.is_set(): ... sleep(60)`），spawn 走 `Persist.START`（产品语义不变）；取消 = `cancel.set()`，service 看到后退出循环

### 业务层拆解

原 `kev/console/generators/` 与 `kev/console/stages/` 解耦：原 `gen_<scenario>.py` / `make_goldset.py` / `make_examples.py` / `split_data.py` / `precheck.py` 抽成可 import 的纯函数（拆 `if __name__ == "__main__"` 块），被 service 调用。

### 不动

- 9 个 `StageSpec` 全部保留（preview / outcome / persist 三件套）
- `artifacts.resolve` / `register` 全链路
- 闸门 `gates.py` 全部判据
- `parse_plan_size` 仍然从 stdout 解析（service 改用 `print` 或 logger 写 "generate at least N records" / JSON 行，on_log 一行行喂给 events）

### 依赖新增

- `kev/console/services/__init__.py`（包）
- `kev/console/services/data.py`（8 个 service 方法，`plan_size` 与 `goldset_audit` 同步无 on_log）

### 风险与缓解

- **同步执行阻塞 FastAPI worker**：保持 `kev.serve` 8008 同时承载推理 + 编排（现状）下，训练 / 蒸馏只能在后台线程跑——`executor.spawn_callable` 内部起 `threading.Thread`（现状就是这种模式，但 Popen 改成直接调函数）
- **蒸馏守护永久占住一个 worker**：需 `uvicorn --workers 1`；或蒸馏守护走 `kev.serve` 之外的独立进程 `python -m kev.console.daemon_runner`，通过 HTTP 控制同 DB

### 蒸馏守护：独立进程（用户决议 2）

蒸馏守护**走独立进程** `python -m kev.console.daemon_runner`，不再 inline 同步进 FastAPI 主进程：

- `daemon_runner` 是 `kev.console` 的新入口（与 `python -m kev.console` 独立编排 web 同包，命令是 `python -m kev.console.daemon_runner`）
- 主进程通过 HTTP（`/console/api/distill-daemon/start`）指挥：spawn 守护进程、传 scenario / provider / schedule
- 守护进程**自带 service 层**（独立于主进程的 `DataService`），用 `kev.serve` 同样的 threading.Event 取消机制
- 守护进程产出的 events / 产物注册走**主进程暴露的内部端点**（`/console/api/_internal/distill-event`），不直接写 DB（避免多进程 SQLite 写竞争）
- 一次性蒸馏（`distill` stage）**仍走 inline 同步**——秒级完成，不占 worker
- 主进程崩溃 / 重启时 `daemon_runner` 不受影响（独立进程 + 独立 health check）

`executor.spawn_callable` 在 `distill_daemon` kind 上**不调** service 方法；改为 spawn `daemon_runner` 子进程（这是 console 改造后**唯一仍走 Popen**的 stage，与 §5.X `deploy` / `modal` 同类）

### 服务层包结构调整

```
kev/console/services/
├── __init__.py
├── data.py        # 8 个 service 方法（plan_size / generate / make_examples / goldset / goldset_audit / split / precheck + 1 次性 distill；**不含** distill_daemon）
├── train.py       # train + gpu_lock
├── eval.py        # baseline / benchmark / compare / calibrate
├── deploy.py      # image / deploy (Popen 保留) / smoke / cancel_endpoint
└── publish.py     # publish / modal (Popen 保留)

kev/console/daemon_runner.py   # 蒸馏守护独立进程入口（**新增**）
kev/console/services/data_daemon.py  # 守护进程内用的 service（与 data.py 不同的循环语义）
```

## 已知 / 不在本期

- 蒸馏的 `n` 是"目标总记录数"（不是"新生成数"；已有合法记录计入），前端不展示这行逻辑，进度从作业日志读
- 不在 UI 暴露 `daily_limit` 编辑（随 provider 改，在 §6.3）
- 不做"批量对多个场景跑 plan_size"的并行调度
- 蒸馏守护的 token 用量按日分桶，在用量页展示（见第 6 章）
