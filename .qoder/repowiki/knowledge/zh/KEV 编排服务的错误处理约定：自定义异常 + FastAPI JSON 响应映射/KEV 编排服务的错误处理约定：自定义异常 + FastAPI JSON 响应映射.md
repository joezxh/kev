---
kind: error_handling
name: KEV 编排服务的错误处理约定：自定义异常 + FastAPI JSON 响应映射
category: error_handling
scope:
    - '**'
source_files:
    - kev/console/app.py
    - kev/console/stages/base.py
    - kev/console/stages/__init__.py
    - kev/console/db.py
    - tests/test_console_stages.py
---

## 1. 总体方案

KEV 仓库的 Python 侧没有统一的 `errors/` 包，也没有第三方异常库。错误处理以**「业务语义异常 + HTTP 层统一映射」**为主，集中在编排服务（FastAPI）中；核心模型/训练/评测模块则直接 raise 标准 Python 异常（`ValueError`、`FileExistsError`、`KeyError`、`RuntimeError`），由调用方自行捕获。

- **HTTP 面**（`kev/console/app.py`）：定义 `_error(kind, message, status, field, hint, stderr_tail)` 返回统一结构的 `JSONResponse`，所有路由通过它或 FastAPI 的 `HTTPException` 返回错误。
- **阶段校验层**（`kev/console/stages/base.py`）：定义两个领域异常 `Invalid`（表单校验失败 → 400，带 `field`/`hint`）和 `Conflict`（目标已存在等不可自动恢复 → 409，带 `hint`），以及 `Persist` 枚举控制产物注册时机。
- **执行器层**（`LocalExecutor` / `_spawn` / `_resolve_service_callable`）：把子进程退出码与 in-process service 调用的异常统一归一为整数 exit code，再由 `register_finished` 决定是否记录 system 事件后重抛。

## 2. 关键文件与位置

| 文件 | 职责 |
|---|---|
| `kev/console/app.py` | FastAPI 路由、`_error`/`_job_error` 映射、SSE 流、上游代理错误（502） |
| `kev/console/stages/base.py` | `Invalid`、`Conflict`、`Persist`、`JobRequest`、`StageSpec` |
| `kev/console/stages/__init__.py` | 阶段注册表，重复 kind 时 `raise ValueError` |
| `kev/console/db.py` | Store 层的 `KeyError` / `FileNotFoundError` / `ValueError("illegal transition ...")` / `RuntimeError("console store not initialized")` |
| `kev/api.py` | TypeSafe SDK 契约（测试断言 422 对应 `TypeSafeUnprocessableEntityError`） |
| `tests/test_console_stages.py` | 断言 `ValueError` 会「打死作业完成回调」——即静默吞掉，作为已知约束 |

## 3. 架构与约定

### 3.1 领域异常 → HTTP 状态码映射

`_job_error`（app.py:64-78）是唯一的集中映射点：

| 异常类型 | HTTP 状态 | 语义 |
|---|---:|---|
| `Invalid` | 400 | 请求参数校验失败，携带 `field` 让前端高亮输入框 |
| `Conflict` | 409 | 资源冲突（如目录已存在），禁止自动改名（医疗可审计要求） |
| `SystemExit` | 400 | 来自 `run_matrix.check_name` 的运行名非法（非 `Invalid` 子类，需单独分支） |
| 其他未识别异常 | 原样 re-raise | 交给 FastAPI 默认 500 处理器 |

### 3.2 统一错误响应体结构

`_error` 返回的 JSON 固定包含：

```json
{"error": {"kind": "validation|conflict|gate|upstream", "message": "...", "field": "...", "hint": "...", "stderr_tail": "..."}}
```

- `kind` 区分错误类别（validation/conflict/gate/upstream），供前端分类展示。
- `field` 指向具体字段，用于 UI 红框标注。
- `hint` 提供面向用户的修复建议。
- `stderr_tail` 仅用于 gate 失败场景，附带闸门明细列表。

### 3.3 Gate 失败的特殊路径

Gate 检查失败不落入 job 生命周期（spec §6.1），直接返回 422，`stderr_tail` 内嵌闸门明细数组（含 `id`/`detail`/`actual`/`need`），前端据此渲染每道闸的期望与实际值对比。

### 3.4 上游代理错误

`_do_proxy` 对 `requests.RequestException` 捕获后记录 usage（status=502）并返回 `kind="upstream"` 的 502 响应，避免上游不可达时抛出未处理异常。

### 3.5 执行期异常归一化

- `_resolve_service_callable` 用 `except Exception as error` 捕获 in-process service 调用异常，打印到 stderr 并返回 exit code 1，与 Popen 子进程行为一致。
- `register_finished` 在产物注册失败时先写一条 `system` 事件再 `raise`，注释明确说明「不能吞」否则 executor 的 `except Exception: pass` 会让作业显示 succeeded 但产物缺失。
- `db.py` 的状态机转换失败抛出 `ValueError(f"illegal transition {row['status']} -> {to_status} for job {job_id}")`，Store API 对外暴露此异常。

### 3.6 静默吞异常的已知约束

`tests/test_console_stages.py:86` 明确断言：stage 的 `build()` 若抛 `ValueError`，会被作业完成回调中的 `except: pass` 静默吞掉，导致作业被标记为成功。这是一个**已知约束**而非 bug——因为 stage 的 `build` 只应组装 argv，不含业务逻辑，业务逻辑在下游脚本中。

## 4. 观察到的约定与约束

- **业务校验抛 `Invalid`，资源冲突抛 `Conflict`**：这两个异常是编排层唯一自定义的领域异常，由 `_job_error` 统一映射到 400/409。
- **运行名非法走 `SystemExit`**：因为 `run_matrix.check_name` 用 `raise SystemExit` 表达非法运行名，`_job_error` 必须单独分支处理，注释说明了来源行号。
- **HTTP 层统一使用 `_error` 或 `HTTPException`**：路由函数不直接构造 `JSONResponse` 表示错误，而是委托给 `_error`，保证响应体结构一致。
- **上游不可达统一 502**：`_do_proxy` 捕获 `requests.RequestException` 后一律返回 502，不区分 DNS/连接超时等细分原因。
- **Gate 失败走 422 + stderr_tail**：区别于普通 validation 400，gate 失败用 422 且附带结构化闸门明细。
- **产物注册失败不得静默**：`register_finished` 注释明确要求「注册失败不吞：记一条 system 事件后重抛」，这是可审计性的硬性约束。
- **Store 层对外抛原生异常**：`KeyError`（未知 id）、`FileNotFoundError`（spec 文件缺失）、`ValueError`（非法状态转换）、`RuntimeError`（store 未初始化），由上层路由捕获并转为 `_error` 响应。
- **无全局异常中间件**：FastAPI 的默认 500 处理器处理未被捕获的异常，项目未注册自定义 exception handler。
- **无 panic/recover 模式**：Python 项目中不存在类似机制，异常传播是主要手段。
- **TypeSafe SDK 契约**：测试断言 422 对应 `TypeSafeUnprocessableEntityError`，表明 SDK 层将 HTTP 422 转换为特定异常类型，而非通用 `HTTPStatusError`。

## 5. 不在本仓库的错误处理

- 模型推理层（`model.py`、`mlx_model.py`）依赖底层 PyTorch/MLX 异常，未做额外封装。
- 训练/评估脚本（`train.py`、`evaluate.py`、`benchmark.py`）直接 `raise ValueError` 表达参数错误，由 CLI 入口或控制台子进程捕获。
- Playground（Next.js 前端）的错误处理属于前端范畴，不在本分析范围内。
- 部署脚本（`deploy/*.sh`、`*.ps1`）使用 shell 退出码，未纳入 Python 错误体系。