# Studio 控制台 · 第 0 章：Service 化实施顺序与降级路径

> 第 7 章之外的全局章，记录用户决议 1：反向依赖 PR 必须先于 console 改造 PR；保留子进程路径作为降级方案。
>
> 本章是**实施计划**而非产品设计——它告诉下一轮"开 Service 化实施计划"的 writer 怎么切 PR。**不是**给用户审的产品形态。

## 决议来源

用户在 2026-10-09 第 2 轮调整时明确：

> 反向依赖 PR——`kev/train.py` 等 5 个核心包改动要单独走 PR，不能与 console 改造混在一起（要保训练子进程路径仍可用作为降级方案）。下一轮开"Service 化实施"计划时，先做这 5 个 PR（最小、可独立回归），再做 console 改造 PR。

## 实施顺序（PR 拆分）

### 阶段 A · 反向依赖 PR（先做，5 个独立 PR）

每个 PR 只改一个核心包的 CLI 拆块，**不动 console**：

| # | PR | 改的包 | 改动最小集 | 验证 |
|---|---|---|---|---|
| A1 | `refactor(kev.train): 拆 CLI 块，暴露 run() + cancel` | `kev/train.py` | `if __name__` 抽出 → `def run(args)`；模块级 `cancel: threading.Event`；step loop 每 N 步检查 | 跑 `uv run python -m kev.train --help`（不传参应仍工作）；跑 `tests/test_unit.py`；手动 spawn 训练用 cancel Event 验证可中断 |
| A2 | `refactor(kev.benchmark): 同上` | `kev/benchmark.py` | 同 A1 模板 | 同 A1 验证集；多一组：`uv run python -m kev.benchmark` 跑一次小套件 |
| A3 | `refactor(kev.compare): 拆 CLI 块` | `kev/compare.py` | 拆 CLI（无 cancel） | `uv run python -m kev.compare`；`tests/test_unit.py` |
| A4 | `refactor(kev.calibrate): 拆 CLI 块` | `kev/calibrate.py` | 拆 CLI（无 cancel） | `uv run python -m kev.calibrate`；`tests/test_unit.py` |
| A5 | `refactor(kev.publish): 拆 CLI 块` | `kev/publish.py` | 拆 CLI（无 cancel） | `uv run python -m kev.publish --help`；`tests/test_unit.py` |

**每个 A1–A5 单独发 PR**（不要合成一个），保证可独立 revert。

### 阶段 B · console service 层（一个 PR）

`kev/console/services/{data,train,eval,deploy,publish}.py` + `kev/console/executor.py` 改造（spawn_callable） + `kev/console/app.py` proxy_kev 加 503 检查。

**关键约束**：
- 阶段 B 完成后**保留**原 `kev/console/stages/{data,train,eval,deploy,publish}.py` 里的 `_xxx_build` 函数与 Popen 调用路径
- `executor.spawn` 保留；`spawn_callable` 新增
- 闸门 / artifacts / events / DB schema **不动**
- 蒸馏守护**不**进入阶段 B；`daemon_runner` 单独走阶段 D

**回滚条件**：
- 阶段 B PR 合并后如发现 service 路径有 bug，立即在 console 加 `KEV_SERVICE_BACKEND=script` 环境变量回退到 Popen 路径
- 阶段 A 的 5 个 PR 即使 B 失败**也不能 revert**——它们是无侵入的纯重构（拆 CLI 不影响外部行为）

### 阶段 C · studio 前端模块（与阶段 B 并行）

playground `kev.studio/` 7 个子模块，与 console service 改造**并行**做（前端只依赖 `/console/api/*` 的 HTTP 契约，契约不变）。

### 阶段 D · 蒸馏守护独立进程（最后做）

`kev/console/daemon_runner.py` + `kev/console/services/data_daemon.py` + `app.py` 新增 `/console/api/_internal/distill-event` 内部端点。

**前置**：
- 阶段 B 落地（一次性 distill 走 inline 同步已可用）
- 守护的产物注册走内部端点的模式需要阶段 B 暴露的 service 包装

**回滚**：守护进程失败时，`executor.spawn_callable` 保留 Popen 调 `daemon_runner` 路径；service 层 inline 守护也保留为 `KEV_DISTILL_DAEMON=script` 回退。

## 降级路径汇总

| 阶段 | 回退环境变量 | 行为 |
|---|---|---|
| A1–A5 失败 | （无回退，因为无外部行为变化） | revert 单个 PR 即可 |
| B 失败 | `KEV_SERVICE_BACKEND=script` | console 走原 Popen + 子进程路径；阶段 A 已合并不影响（拆 CLI 后子进程跑的是同 argv） |
| D 失败 | `KEV_DISTILL_DAEMON=script` | 守护走原 Popen 调 `daemon_runner` 子进程（service 层 inline 守护作为额外备份） |
| 训练 service 抛异常 | （B 阶段的 try/except 已把 job 标 failed） | 无回退；用户重试或回退 B |

## 关键不变量

- 阶段 A 完成后，`kev/console` 子进程路径**必须**仍能跑（保留降级）
- 阶段 B 完成后，`kev/console` service 路径与子进程路径**并存**（环境变量切）
- 阶段 D 完成后，蒸馏守护**只能**走独立进程（移除 inline 守护路径，节省 worker 占用）

## 验证矩阵

| 阶段 | 必跑 | 命令 |
|---|---|---|
| A1–A5 | unit + CLI smoke | `uv run python -m pytest tests/test_unit.py -q && uv run python -m kev.train --help` |
| B | unit + console integration | `uv run python -m pytest tests/test_unit.py tests/test_conventions.py -q`；`python -m kev.console` 起服务，`curl /console/api/scenarios` |
| C | playground lint + typegen | `cd playground && npm ci && npm run lint && npx next typegen && npx tsc --noEmit -p .` |
| D | unit + 多进程 | `python -m kev.console` + `python -m kev.console.daemon_runner`；模拟主进程崩溃，守护不退出 |

## 不在本总章

- 业务功能设计见 ch1–ch7
- §2.X / §3.X / §4.X / §5.X 的 service 接口签名
