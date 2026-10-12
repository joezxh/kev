---
kind: logging_system
name: KEV 日志系统：基于 print/stdout + 文件落盘 + SSE 流式回放
category: logging_system
scope:
    - '**'
source_files:
    - kev/console/__main__.py
    - kev/console/app.py
    - modal_app.py
    - examples/kev_example.py
    - _ms_probe.py
---

## 1. 使用的框架与工具

仓库没有引入 `logging`、`loguru`、`structlog`、`rich` 等第三方日志库。所有可观测输出统一通过 Python 内置的 `print()`（默认 stdout）和 `sys.stderr` 完成，由运行环境负责路由到终端、文件或容器日志。

- **控制台服务**：FastAPI + Uvicorn，启动时显式设置 `uvicorn.run(..., log_level="info")`（`kev/console/__main__.py:89`），其余 FastAPI/Starlette 内部日志走 Uvicorn 默认 handler。
- **Modal 云端训练**：每个 trial 一个 GPU 容器，使用 `PYTHONUNBUFFERED=1`（`modal_app.py:45`）确保 `print()` 实时刷新；日志直接写到 stdout，被 Modal 收集为函数调用日志。
- **编排服务（console）**：作业子进程或内嵌 service callable 的输出全部写入 `paths.JOB_LOGS/<uuid>.log` 文件，再通过 `/console/api/jobs/{id}/stream`（SSE）和 `/console/api/jobs/{id}/log` 暴露给前端。

## 2. 关键文件

| 文件 | 作用 |
|---|---|
| `kev/console/__main__.py` | 控制台入口，设置 `PYTHONIOENCODING=utf-8`，创建 `paths.JOB_LOGS`，以 `log_level="info"` 启动 Uvicorn |
| `kev/console/app.py` | 编排服务 HTTP 面，定义 job 提交、SSE 事件流、job 日志读取、产物注册、usage 记录等核心逻辑 |
| `modal_app.py` | Modal 云端编排，设置 `PYTHONUNBUFFERED=1`，用 `print(..., flush=True)` 输出进度、错误、volume commit 信息 |
| `examples/kev_example.py` | 示例脚本，仅用 `print()` 打印连接状态与决策结果 |
| `_ms_probe.py` | 探测脚本，仅用 `print()` 输出模型加载诊断 |

## 3. 架构与约定

### 3.1 双通道日志：events 表 + 原始 log 文件

`app.py` 文档注释明确区分两个通道：
- **events 表**：结构化事件（note / step / system），供 SSE 回放和 UI 解析（`parse_note`、`parse_step`、`sse_frame`）。
- **log 文件**：作业子进程的完整 stdout/stderr 副本，是“真相源”（`get_job_log` 注释：“SSE 回放的是 events 表；日志文件才是真相源”）。

```text
作业提交 → executor.spawn() / spawn_callable()
         → 子进程 stdout/stderr → paths.JOB_LOGS/<uuid>.log
         → events 表（结构化 note/step/system）→ SSE /events 端点
```

### 3.2 作业执行路径

`_spawn()`（`app.py:227`）根据 stage 是否绑定 service callable 分两条路径：
- **service callable**：通过 `LocalExecutor.spawn_callable(job_id, fn, label, log_path, env_overlay)` 执行，stdout 经 `_CapturingStdout` tee 进同一 log 文件。
- **Popen 子进程**：skill-script 或 distill_daemon wrapper，argv 中注入 `--job-id` 和 `--log-path` 占位符后替换。

两种路径都生成 `log_path = paths.JOB_LOGS / f"{uuid.uuid4().hex}.log"`，并持久化到 store 的 `job.log_path` 字段。

### 3.3 SSE 流式回放

`/console/api/jobs/{job_id}/stream`（`app.py:747`）实现 Server-Sent Events：
- 按 `after_id` 游标轮询 `store.read_events(job_id, after_id, limit=STREAM_BATCH)`（`STREAM_BATCH=200`, `POLL_SECONDS=0.5`）。
- 支持 `Last-Event-ID` header 续传（浏览器 EventSource 重连时自动携带）。
- 空闲时发送 `event: ping\ndata: {}` 心跳，作业终态发送 `event: status` 包含 `status` 和 `exit_code`。
- 返回 `StreamingResponse`，media_type=`text/event-stream`，禁用缓存。

### 3.4 Modal 云端日志

`modal_app.py` 中几乎所有用户可见输出都使用 `print(..., flush=True)`：
- trial 启动：`print(f"[{label}] {torch.cuda.get_device_name(0)} torch {torch.__version__} ...", flush=True)`
- volume watcher：`print(f"[volume] committed ...", flush=True)`
- lease heartbeat 失败：`print(f"!!! [lease] ...", flush=True)`
- mirror 失败：`print(f"!!! [mirror] ...", flush=True)`

容器环境变量强制 `PYTHONUNBUFFERED=1`，保证无缓冲输出。

### 3.5 结构化事件 vs 非结构化文本

events 表中的行由 `parse_note` / `parse_step` 解析，UI 侧渲染结构化片段（如训练指标、步骤名）。非结构化文本则保留在 log 文件中，通过 `/log?tail=N` 拉取尾部（默认 200,000 字符截断）。

## 4. 约定与约束

- **不使用 `logging` 模块**：全仓搜索未发现 `import logging`、`getLogger`、`logger.info` 等模式；所有输出走 `print()` 或 `sys.stderr`。
- **控制台端口保护**：`__main__.py:_refuse_serve_port()` 拒绝把控制台绑到 8008（推理端点端口），否则代理回环导致 `/v1/systemone` 全 404。
- **凭据不出浏览器**：`SECRET_NAMES` 列表（`KEV_API_KEY`、`KEV_GEN_API_KEYS`、`KEV_HF_SECRET`、`KEV_SERVE_SECRET`、`HF_TOKEN`）在 `/console/api/config` 只返回布尔值（`bool(os.environ.get(name))`），明文不下发。
- **SSE 续传依赖 Last-Event-ID header**：代码注释明确指出“EventSource 断线自动重连时沿用原 URL，Last-Event-ID 只以 header 形式回来”，因此必须从 header 而非 query 参数读取 cursor。
- **log 文件是唯一真相源**：`get_job_log` 注释强调“SSE 回放的是 events 表；日志文件才是真相源，终态作业的 result 页用它展示完整日志”。
- **Modal 输出必须 flush**：所有 `print()` 调用带 `flush=True`，配合 `PYTHONUNBUFFERED=1` 避免容器日志丢失。
- **Uvicorn 日志级别固定为 info**：`uvicorn.run(..., log_level="info")`，未提供 CLI 选项覆盖。
- **JOB_LOGS 目录预先创建**：`main()` 中 `paths.JOB_LOGS.mkdir(parents=True, exist_ok=True)`，initdb 也提前创建，确保子进程写入不会因目录缺失失败。
- **stderr 用于异常**：service callable 异常路径 `print(f"service:{method_name} 异常：{error!r}", file=sys.stderr)`，与 stdout 的业务日志分离。

## 5. 结论

该仓库采用极简日志策略：以 `print()` 作为唯一输出 API，由运行环境（终端/Uvicorn/Modal）决定最终去向；编排层通过“结构化 events 表 + 原始 log 文件”的双通道设计，既满足 UI 的结构化展示，又保留完整可审计的原始日志。没有统一的 logger 抽象、日志级别体系或结构化字段 schema——这是研究/实验型仓库的典型取舍。