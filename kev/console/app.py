"""编排服务的 HTTP 面：作业提交、闸门预检、产物血缘、SSE 日志流。

路由清单见 spec §10.1。playground 侧只有一个薄代理（`/api/console/[...path]`），
所以这里不关心 CORS；编排服务只绑 127.0.0.1、无鉴权（本地单用户，spec §12）。

SSE 从 events 表按 id 游标轮询，而不是靠进程内的队列：日志文件才是真相源，
这样多进程、重启、`Last-Event-ID` 续传都天然成立。

合并形态：所有 `/console/api/*` 路由定义在一个模块级 `console_router`（`APIRouter`）上，
状态经 `request.app.state` 注入（见 `get_store` / `get_executor`）。`create_app()` 只负责
把 store/executor 挂到 `app.state` 再 `include_router(console_router)`——它是 `python -m
kev.console` 独立入口（8790，无模型也能跑编排）用的；同一个 `console_router` 也被
`kev.serve` 直接 `include_router` 进来，于是 8008 上推理面与编排面同在**一个** FastAPI
app 里、同一份 OpenAPI 文档，不再有一个被随手建出来又只拿 `.router` 的幽灵子 app。
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sys
import threading
import time
import uuid
from pathlib import Path

import requests
import sqlalchemy as sa

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse

from . import artifacts, paths, scenario_specs
from . import secret_store as distill_secrets
from .db import Store, set_store
from .events import parse_note, parse_step, sse_frame
from .executor import ALLOWED_ENV, LocalExecutor, SECRET_ENV, scrub_secret_overlays
from .gates import STAGE_GATES, evaluate
from .stages import REGISTRY, Conflict, Invalid, JobRequest
from .stages import data as data_stages
from .stages import eval as eval_stages
from .stages import train as train_stages

DB_ENV = "KEV_CONSOLE_DB"
POLL_SECONDS = 0.5
STREAM_BATCH = 200
# 只回布尔态：凭据值永远不下发到浏览器（spec §12）。名单单一归属 executor.SECRET_ENV：
# 两处各自维护就会出现「一处加了新凭据、另一处仍当它非敏感」的泄露。
SECRET_NAMES = SECRET_ENV

# 代理目标：默认指回本进程（kev.console 被挂进 kev.serve 时，它即自己）。可改成远端端点。
KEV_SERVE_URL = os.environ.get("KEV_SERVE_URL", "http://127.0.0.1:8008")
ADMIN_KEY = os.environ.get("KEV_API_KEY")


def _error(kind: str, message: str, *, status: int, field: str = "", hint: str = "",
           stderr_tail: str = "") -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {
        "kind": kind, "message": message, "field": field, "hint": hint,
        "stderr_tail": stderr_tail}})


def _job_error(error: Exception) -> JSONResponse:
    """把 build 阶段的异常映射成 HTTP 响应。

    `run_matrix.check_name` 用 `raise SystemExit` 表达「运行名非法」（run_matrix.py:47），
    所以必须单独接住 —— 它不是 Invalid 的子类。
    """
    if isinstance(error, Invalid):
        return _error("validation", error.message, status=400,
                      field=error.field, hint=error.hint)
    if isinstance(error, Conflict):
        return _error("conflict", error.message, status=409, hint=error.hint)
    if isinstance(error, SystemExit):
        return _error("validation", str(error), status=400, field="run_name",
                      hint="运行名只允许字母数字下划线连字符，尺寸写 8b 不写 0.8b")
    raise error


def _gate_products(store: Store, request: JobRequest) -> dict:
    """把已落库的产物读成闸门要的形状。

    缺产物时返回 None —— `gates.evaluate` 会判失败并说明缺什么，而不是抛异常。
    """
    from kev.suite import read_json

    def load(kind: str, name: str):
        artifact = store.get_artifact(f"{kind}:{name}")
        if artifact is None:
            return None
        target = Path(paths.ROOT) / artifact["path"]
        if not target.is_file():
            return None
        try:
            return read_json(target)
        except (OSError, ValueError):
            return None

    data_dir = request.params.get("data") or f"data/{request.scenario}"
    name = data_stages.dataset_id(data_dir)
    return {
        "precheck": load("precheck", f"{name}/train"),
        "summary": load("dataset", f"{name}/summary"),
        # plan 证据：优先按 data_dir 推导的 dataset 名（蒸馏链路 data/scenario/category），
        # 回退到场景 slug（plan_size 注册时只知道场景名）。
        "plan": (request.params.get("plan")
                 or load("plan", name) or load("plan", request.scenario)),
        "report": load("eval", request.run_name),
        # G4（workload 增益）与 G6（公开套件回归）证据分离：regression 是
        # compare --public 产出的第二份 comparison，见 gates.STAGE_GATES。
        "comparison": load("comparison", request.run_name),
        "comparison_public": load("regression", request.run_name),
        "calibration": load("calibration", request.run_name),
    }


# ---------------------------------------------------------------------------
# 状态注入：路由在 router 上、与具体 app 解耦，运行时从 request.app.state 取。
# ---------------------------------------------------------------------------

def get_store(request: Request) -> Store:
    return request.app.state.store


def get_executor(request: Request) -> LocalExecutor:
    return request.app.state.executor


def _ep(path: str) -> str:
    tail = path.rstrip("/").split("/")[-1]
    return {"systemone": "systemone", "separate": "separate",
            "permute": "permute", "models": "models"}.get(tail, tail)


def _persist_plan(store: Store, job: dict) -> None:
    """把 plan_size 日志里的计划落盘成 plan 产物文件。

    任何「写不出来」的情况都必须留痕（system 事件）：这次排查的教训就是静默 return
    让作业显示 succeeded 而文件根本不存在，用户无从下手。
    """
    log = Path(job["log_path"])
    if not log.is_file():
        store.append_events(job["id"], [
            ("system", f"plan 落盘失败：日志文件不存在 {log}（plan 产物将缺失）")])
        return
    plan = data_stages.parse_plan_size(log.read_text(encoding="utf-8", errors="replace"))
    if not plan.get("total_records"):
        store.append_events(job["id"], [
            ("system", "plan 落盘失败：日志里没有可解析的 total_records（JSON 可能被调试器"
                       "或其他输出污染，见 parse_plan_size）")])
        return
    target = Path(paths.ROOT) / artifacts.resolve(f"plan:{job['scenario']}")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")


def register_finished(store: Store, job_id: str, exit_code: int) -> None:
    """产物注册的唯一入口（长驻作业除外，它们在 spawn 后立刻注册）。

    注册失败**不吞**：记一条 system 事件后重抛。没有它的话，executor 那边的
    `except Exception: pass` 会让产物缺失完全静默（作业显示 succeeded 而产物不存在）。
    """
    job = store.get_job(job_id)
    if job is None or exit_code != 0:
        return
    if job["kind"] == "plan_size":
        # plan_size.py 只写 stdout：把日志里的计划解析落盘成 plan 产物文件，
        # 否则 artifacts.register 找不到文件、G2 的 plan 证据永远缺失。
        try:
            _persist_plan(store, job)
        except Exception as error:
            store.append_events(
                job_id, [("system", f"计划落盘失败：{error!r}（G2 将无法读到 plan）")])
    try:
        artifacts.register(store, job)
    except Exception as error:
        store.append_events(
            job_id, [("system", f"产物注册失败：{error!r}（重跑该作业即可重新注册）")])
        raise


def _resolve_service_callable(stage, request: JobRequest, store, cancel,
                              gpu_lock=None, executor=None):
    """If stage.service is set, build the in-process callable for it.

    Returns a 2-tuple (fn, label) or None when the stage has no service binding.
    `fn` mirrors a script's exit-code contract (returns int) and prints to
    stdout so _CapturingStdout can tee it into the same log the subprocess path
    would have written. The label is recorded as the events-table "meta" row,
    e.g. "service:data.generate", so readers can tell an in-process call from
    a Popen one without parsing argv.
    """
    method_name = getattr(stage, "service", None)
    if not method_name:
        return None
    from .services import get_service
    kwargs = {}
    if gpu_lock is not None:
        kwargs["gpu_lock"] = gpu_lock
    if executor is not None:
        kwargs["executor"] = executor
    service = get_service(method_name, store=store, cancel=cancel, **kwargs)
    method = getattr(service, method_name.split(".", 1)[1])
    captured: dict = {}

    def _fn() -> int:
        try:
            # TrainService.train takes on_log AND on_metric; DataService methods
            # only take on_log. Probe via inspect so the right kwarg set is
            # passed — keeps the call site agnostic to the method shape.
            import inspect
            sig = inspect.signature(method)
            call_kwargs = {"on_log": lambda line: print(line)}
            if "on_metric" in sig.parameters:
                call_kwargs["on_metric"] = lambda _p: None
            captured["result"] = method(request, **call_kwargs)
        except Exception as error:  # noqa: BLE001 - mirrors subprocess exit codes
            print(f"service:{method_name} 异常：{error!r}", file=sys.stderr)
            return 1
        rc = int(captured["result"].get("returncode", 0))
        return rc

    return _fn, f"service:{method_name}"


def _spawn(store: Store, executor: LocalExecutor, stage, request: JobRequest, built,
          *, attempt=1, parent_id=None, gpu_lock=None, template_id=None) -> str:
    log_path = paths.JOB_LOGS / f"{uuid.uuid4().hex}.log"
    service_binding = _resolve_service_callable(stage, request, store, executor.cancel,
                                                gpu_lock=gpu_lock, executor=executor)
    if service_binding is not None:
        fn, label = service_binding
        job_id = store.create_job(
            project_id=request.project_id,
            kind=stage.kind, stage=stage.stage, scenario=request.scenario,
            title=request.run_name or stage.title, request=request.params,
            argv=[label], env_overlay=built.env,
            cwd=str(paths.ROOT), log_path=str(log_path),
            artifacts_in=built.artifacts_in, artifacts_out=built.artifacts_out,
            attempt=attempt, parent_id=parent_id, template_id=template_id)
        executor.spawn_callable(job_id, fn, label=label, log_path=str(log_path),
                                env_overlay=built.env)
        if stage.persist == "start":
            artifacts.register(store, store.get_job(job_id))
        return job_id

    # Popen path (skill-script stages + distill_daemon daemon_runner wrapper).
    # For distill_daemon: fill in the job_id / log_path placeholders that
    # _distill_daemon couldn't know when it built the wrapped argv.
    argv = [str(part) for part in built.argv]
    if built.daemon_id is not None:
        job_id = store.create_job(
            project_id=request.project_id,
            kind=stage.kind, stage=stage.stage, scenario=request.scenario,
            title=request.run_name or stage.title, request=request.params,
            argv=argv, env_overlay=built.env,
            cwd=built.cwd or str(paths.ROOT), log_path=str(log_path),
            artifacts_in=built.artifacts_in, artifacts_out=built.artifacts_out,
            attempt=attempt, parent_id=parent_id, daemon_id=built.daemon_id,
            template_id=template_id)
        # Backfill placeholder argv values that _distill_daemon left as __placeholder__.
        for i, part in enumerate(argv):
            if part == "__placeholder__":
                if "--job-id" in (argv[i - 1] if i > 0 else ""):
                    argv[i] = job_id
                elif "--log-path" in (argv[i - 1] if i > 0 else ""):
                    argv[i] = str(log_path)
        # Register the per-daemon cancel flag so cancel_job can signal it.
        set_daemon_cancel(built.daemon_id)
    else:
        job_id = store.create_job(
            project_id=request.project_id,
            kind=stage.kind, stage=stage.stage, scenario=request.scenario,
            title=request.run_name or stage.title, request=request.params,
            argv=argv, env_overlay=built.env,
            cwd=built.cwd or str(paths.ROOT), log_path=str(log_path),
            artifacts_in=built.artifacts_in, artifacts_out=built.artifacts_out,
            attempt=attempt, parent_id=parent_id, template_id=template_id)
    executor.spawn(job_id, argv, cwd=built.cwd or str(paths.ROOT),
                   log_path=str(log_path), env_overlay=built.env, secrets=built.secrets)
    if stage.persist == "start":
        # 长驻作业（kev.serve）永远不「完成」，产物必须在 spawn 之后立刻注册，
        # 否则端点列表永远是空的。在线状态由部署页实际探 /v1/models 决定。
        artifacts.register(store, store.get_job(job_id))
    return job_id


def _prepare(store: Store, payload: dict):
    """校验请求并组装命令。返回 (stage, request, built) 或一个 JSONResponse 错误。"""
    kind = payload.get("kind", "")
    stage = REGISTRY.get(kind)
    if stage is None:
        return _error("validation", f"未知作业类型 {kind!r}", status=404,
                      hint=f"可选：{', '.join(sorted(REGISTRY))}")
    try:
        request = JobRequest(**payload)
        built = stage.preview(request)
    except (Invalid, Conflict, SystemExit) as error:
        return _job_error(error)
    # 环境通道必须在落库之前校验：_spawn 里 create_job 先于 executor.spawn，等到
    # build_env 才拒就留下一条带着（可能是凭据）overlay、且永不运行的作业行 + 一个 500。
    misplaced = sorted(key for key in built.env if key not in ALLOWED_ENV)
    if misplaced:
        return _error("validation", f"env 只能带非敏感白名单键，收到 {misplaced}", status=400,
                      field="env", hint=f"允许：{sorted(ALLOWED_ENV)}；凭据请走 secrets 通道")
    leaked = sorted(key for key in built.secrets if key not in SECRET_NAMES)
    if leaked:
        return _error("validation", f"secrets 只能带已声明的凭据键，收到 {leaked}", status=400,
                      field="env", hint=f"允许：{sorted(SECRET_NAMES)}")
    return stage, request, built


def _ingest_distill_usage(store: Store, job_id: str) -> None:
    import json as _json
    from pathlib import Path as _Path
    job = store.get_job(job_id)
    if job is None or job["kind"] not in ("distill", "distill_daemon"):
        return
    # 作业未显式传 state_dir 时，与 _distill_build 的缺省保持一致（paths.DEFAULT_DISTILL_STATE_DIR），
    # 保证用量采集端到端可通（spec §9）。
    state_dir = (job["request"].get("state_dir") or str(paths.DEFAULT_DISTILL_STATE_DIR)).strip()
    if not _Path(state_dir).is_dir():
        return
    provider_id = job["request"].get("provider_id") or ""
    prov = store.get_distill_provider(provider_id) or {}
    model = prov.get("model", "")
    base_url = prov.get("base_url", "")
    for f in sorted(_Path(state_dir).glob("usage_*.json")):
        day = f.stem.split("_")[-1]
        try:
            data = _json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for key, tokens in data.items():
            kh, hint = distill_secrets.mask(key)
            store.upsert_distill_usage(job_id=job_id, provider_id=provider_id, key_hash=kh,
                key_hint=hint, model=model, base_url=base_url, day=day, tokens=int(tokens or 0))


def _do_proxy(store: Store, key_id: str, path: str, headers: dict, query: str, method: str, body):
    upstream = f"{KEV_SERVE_URL}/{path}"
    fwd = {"content-type": headers.get("content-type", "application/json")}
    if ADMIN_KEY:
        fwd["authorization"] = f"Bearer {ADMIN_KEY}"
    started = time.perf_counter()
    try:
        if method == "POST":
            resp = requests.post(upstream, data=body, headers=fwd, params=query, timeout=300)
        else:
            resp = requests.get(upstream, headers=fwd, params=query, timeout=300)
    except requests.RequestException:
        store.record_usage(key_id=key_id, endpoint=_ep(path), method=method,
                          status=502, input_tokens=0, output_tokens=0,
                          latency_ms=round((time.perf_counter() - started) * 1000, 1))
        return _error("upstream", "kev.serve 不可达", status=502)
    dt = round((time.perf_counter() - started) * 1000, 1)
    in_t = out_t = 0
    try:
        usage = resp.json().get("usage") or {}
        in_t = int(usage.get("input_tokens", 0) or 0)
        out_t = int(usage.get("output_tokens", 0) or 0)
    except (ValueError, AttributeError):
        pass
    store.record_usage(key_id=key_id, endpoint=_ep(path), method=method, status=resp.status_code,
                       input_tokens=in_t, output_tokens=out_t, latency_ms=dt)
    return JSONResponse(status_code=resp.status_code, content=resp.json(),
                        headers={"content-type": resp.headers.get("content-type", "application/json")})


# ---------------------------------------------------------------------------
# 路由表（模块级，与 app 解耦；kev.serve 与独立控制台共用同一份）
# ---------------------------------------------------------------------------

console_router = APIRouter()


# ---- config / scenarios ----------------------------------------------

@console_router.get("/console/api/config")
def get_config(scenario: str = "critical-value", store: Store = Depends(get_store)) -> dict:
    # 三种微调方式的默认值只在这里暴露一次，前端不许硬编码
    return {
        "scenarios": store.list_scenario_slugs(),
        "methods": train_stages.methods_for(scenario),
        "serve_port": 8008,
        # 只回布尔态：凭据值永远不下发到浏览器
        "credentials": {name: bool(os.environ.get(name)) for name in SECRET_NAMES},
    }


@console_router.get("/console/api/scenarios")
def get_scenarios(store: Store = Depends(get_store)) -> list:
    out = []
    for slug in store.list_scenario_slugs():
        row = store.get_scenario_by_slug(slug)
        spec_json = row.get("spec_json") if row else None
        if spec_json:
            try:
                spec = json.loads(spec_json)
                questions = len(spec.get("questions", {}))
            except ValueError:
                questions, exists = 0, False
            else:
                exists = True
        else:
            questions, exists = 0, False
        out.append({"name": slug, "questions": questions, "exists": exists})
    return out


# ---- scenario domains & scenarios (two-level, bilingual) -------------

@console_router.get("/console/api/scenario-domains")
def get_scenario_tree(lang: str = "zh", store: Store = Depends(get_store)) -> list:
    return store.list_scenario_tree(lang=lang)


@console_router.post("/console/api/scenario-domains")
def create_domain(payload: dict, store: Store = Depends(get_store)):
    slug = (payload.get("slug") or "").strip()
    label_zh = (payload.get("label_zh") or "").strip()
    label_en = (payload.get("label_en") or "").strip()
    if not slug:
        return _error("validation", "域 slug 必填", status=400, field="slug")
    if not label_zh or not label_en:
        return _error("validation", "中英文标签均必填", status=400, field="label_zh")
    try:
        domain_id = store.create_domain(
            slug=slug, label_zh=label_zh, label_en=label_en, sort=int(payload.get("sort", 0)),
            spec_dir=(payload.get("spec_dir") or "").strip())
    except sa.exc.IntegrityError:
        return _error("conflict", f"域 slug 已存在：{slug}", status=409, field="slug")
    return JSONResponse(status_code=201, content=store.get_domain(domain_id))


@console_router.put("/console/api/scenario-domains/{domain_id}")
def update_domain(domain_id: str, payload: dict, store: Store = Depends(get_store)):
    if store.get_domain(domain_id) is None:
        return _error("validation", f"未知域 {domain_id}", status=404)
    ok = store.update_domain(domain_id, label_zh=payload.get("label_zh"),
                             label_en=payload.get("label_en"), sort=payload.get("sort"),
                             spec_dir=payload.get("spec_dir"))
    return store.get_domain(domain_id) if ok else _error("validation", f"未知域 {domain_id}", status=404)


@console_router.delete("/console/api/scenario-domains/{domain_id}")
def delete_domain(domain_id: str, store: Store = Depends(get_store)):
    if not store.delete_domain(domain_id):
        return _error("validation", f"未知域 {domain_id}", status=404)
    return {"deleted": True}


@console_router.post("/console/api/scenarios")
def create_scenario(payload: dict, store: Store = Depends(get_store)):
    domain_id = (payload.get("domain_id") or "").strip()
    slug = (payload.get("slug") or "").strip()
    label_zh = (payload.get("label_zh") or "").strip()
    label_en = (payload.get("label_en") or "").strip()
    spec_path = (payload.get("spec_path") or "").strip()
    if not domain_id:
        return _error("validation", "所属域必填", status=400, field="domain_id")
    if not slug:
        return _error("validation", "场景 slug 必填", status=400, field="slug")
    if not label_zh or not label_en:
        return _error("validation", "中英文标签均必填", status=400, field="label_zh")
    # spec 内容存数据库（scenarios.spec_json），spec_path 仅作可选参考/生成器回退路径，
    # 不再强制要求本地文件存在。提供了就校验是 .json。
    if spec_path and not str(spec_path).endswith(".json"):
        return _error("validation", "spec_path 必须是 .json 文件", status=400, field="spec_path")
    category = (payload.get("category") or "medical").strip()
    # 轨制由 scenario_specs 派生（docs/domains 的种子场景每次导入重算）；手工场景可以在这儿标，
    # 但只认四个值，写错的 track 会让前端的「规则生成 / 蒸馏」列变成瞎话。留空 = 未判定（合法）。
    track = (payload.get("track") or "").strip()
    if track and track not in scenario_specs.TRACKS:
        return _error("validation", f"track 必须是 {'/'.join(scenario_specs.TRACKS)} 之一（留空 = 未判定）",
                      status=400, field="track")
    try:
        scenario_id = store.create_scenario(
            domain_id=domain_id, slug=slug, label_zh=label_zh, label_en=label_en,
            spec_path=spec_path, category=category, sort=int(payload.get("sort", 0)),
            track=track, generator_kind=(payload.get("generator_kind") or "").strip(),
            distill_yaml=(payload.get("distill_yaml") or "").strip())
    except sa.exc.IntegrityError:
        return _error("conflict", f"场景 slug 已存在：{slug}", status=409, field="slug")
    return JSONResponse(status_code=201, content=store.get_scenario_by_slug(slug))


@console_router.put("/console/api/scenarios/{scenario_id}")
def update_scenario(scenario_id: str, payload: dict, store: Store = Depends(get_store)):
    if store.get_scenario_by_id(scenario_id) is None:
        return _error("validation", f"未知场景 {scenario_id}", status=404)
    # track 传空串是「清空未判定」，合法；只有写了不认识的值才拒。
    if payload.get("track") not in (None, "") and payload["track"] not in scenario_specs.TRACKS:
        return _error("validation", f"track 必须是 {'/'.join(scenario_specs.TRACKS)} 之一（或空串 = 未判定）",
                      status=400, field="track")
    # Step 2 of Task 28: validate routing + smoke_probe sub-fields
    if "routing" in payload and payload["routing"]:
        risk = (payload["routing"] or {}).get("risk")
        if risk not in {"low", "medium", "high", "critical"}:
            raise HTTPException(400, f"routing.risk must be one of low/medium/high/critical, got {risk!r}")
        evidence_q = (payload["routing"] or {}).get("evidence_question", "")
        spec_row = store.get_scenario_by_slug(scenario_id)
        spec = json.loads(spec_row["spec_json"]) if spec_row and spec_row.get("spec_json") else {}
        if evidence_q and evidence_q not in spec.get("questions", {}):
            raise HTTPException(400, f"routing.evidence_question {evidence_q!r} is not a question in the spec")
    if "smoke_probe" in payload and payload["smoke_probe"]:
        spec_row = store.get_scenario_by_slug(scenario_id)
        spec = json.loads(spec_row["spec_json"]) if spec_row and spec_row.get("spec_json") else {}
        for q in payload["smoke_probe"].get("questions", []) or []:
            if q["qid"] not in spec.get("questions", {}):
                raise HTTPException(400, f"smoke_probe.questions[].qid {q['qid']!r} is not a question in the spec")
    ok = store.update_scenario(
        scenario_id, domain_id=payload.get("domain_id"), label_zh=payload.get("label_zh"),
        label_en=payload.get("label_en"), spec_path=payload.get("spec_path"),
        category=payload.get("category"), sort=payload.get("sort"),
        track=payload.get("track"), generator_kind=payload.get("generator_kind"),
        distill_yaml=payload.get("distill_yaml"))
    row = store.get_scenario_by_id(scenario_id)
    return row if ok and row else _error("validation", f"未知场景 {scenario_id}", status=404)


# Step 1 of Task 28: 3 new generator API routes
@console_router.post("/console/api/scenarios/{slug}/generator/preview")
def generator_preview(slug: str, body: dict, store: Store = Depends(get_store)) -> dict:
    from kev.console.generators.engine import run as engine_run
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        engine_run(["--scenario", slug, "--n", "1", "--out", str(tmp_path), "--seed", "0", "--pairs", "0"])
        line = tmp_path.read_text(encoding="utf-8").splitlines()[0]
        return {"record": json.loads(line)}
    finally:
        try:
            tmp_path.unlink()
        except OSError:
            pass


@console_router.post("/console/api/scenarios/{slug}/generator/dry-run")
def generator_dry_run(slug: str, body: dict, store: Store = Depends(get_store)) -> dict:
    n = body.get("n", 100)
    seed = body.get("seed", 0)
    from kev.console.generators.engine import run as engine_run
    from common import label_table as _lt
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        engine_run(["--scenario", slug, "--n", str(n), "--out", str(tmp_path), "--seed", str(seed), "--pairs", "0"])
        rows = [json.loads(line) for line in tmp_path.read_text(encoding="utf-8").splitlines()]
        return {"rows": rows, "label_table": _lt(rows)}
    finally:
        try:
            tmp_path.unlink()
        except OSError:
            pass


@console_router.post("/console/api/scenarios/{slug}/generator/validate")
def generator_validate(slug: str, body: dict, store: Store = Depends(get_store)) -> dict:
    try:
        from kev.console.generators.engine import run as engine_run
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as tmp:
            tmp_path = Path(tmp.name)
        try:
            engine_run(["--scenario", slug, "--n", "1", "--out", str(tmp_path), "--seed", "0", "--pairs", "0"])
            return {"errors": []}
        finally:
            try:
                tmp_path.unlink()
            except OSError:
                pass
    except Exception as e:
        return {"errors": [{"rule_id": "<unknown>", "message": str(e)}]}


@console_router.delete("/console/api/scenarios/{scenario_id}")
def delete_scenario(scenario_id: str, store: Store = Depends(get_store)):
    if not store.delete_scenario(scenario_id):
        return _error("validation", f"未知场景 {scenario_id}", status=404)
    return {"deleted": True}


@console_router.get("/console/api/scenarios/{slug}/spec")
def get_scenario_spec(slug: str, store: Store = Depends(get_store)):
    try:
        content = store.read_spec_file(slug)
    except KeyError:
        return _error("validation", f"未知场景 {slug}", status=404)
    except FileNotFoundError as error:
        return _error("validation", str(error), status=404, field="spec_path",
                      hint="先在控制台为该场景配置有效的 spec_path")
    return {"slug": slug, "content": content}


@console_router.get("/console/api/scenarios/{slug}/spec/history")
def get_spec_history(slug: str, store: Store = Depends(get_store)):
    if store.get_scenario_by_slug(slug) is None:
        return _error("validation", f"未知场景 {slug}", status=404)
    return store.list_spec_history(slug)


@console_router.get("/console/api/scenarios/{slug}/spec/history/{ts}")
def get_spec_history_version(slug: str, ts: str, store: Store = Depends(get_store)):
    if store.get_scenario_by_slug(slug) is None:
        return _error("validation", f"未知场景 {slug}", status=404)
    try:
        content = store.read_spec_history(slug, ts)
    except FileNotFoundError as error:
        return _error("validation", str(error), status=404)
    return {"slug": slug, "ts": ts, "content": content}


@console_router.put("/console/api/scenarios/{slug}/spec")
def put_scenario_spec(slug: str, payload: dict, store: Store = Depends(get_store)):
    content = payload.get("content", "")
    try:
        store.write_spec_file(slug, content)
    except KeyError:
        return _error("validation", f"未知场景 {slug}", status=404)
    except ValueError as error:
        return _error("validation", str(error), status=400, field="content")
    return {"slug": slug, "saved": True}


# ---- datasets ---------------------------------------------------------

@console_router.get("/console/api/datasets")
def get_datasets(store: Store = Depends(get_store)) -> list:
    return store.list_artifacts("dataset")


@console_router.get("/console/api/datasets/{artifact_id:path}")
def get_dataset(artifact_id: str, store: Store = Depends(get_store)):
    artifact = store.get_artifact(artifact_id)
    if artifact is None:
        return _error("validation", f"未知数据集 {artifact_id}", status=404)
    return {**artifact, "lineage": store.lineage_of(artifact_id)}


@console_router.get("/console/api/datasets/{artifact_id:path}/export")
def export_dataset(artifact_id: str, store: Store = Depends(get_store)):
    artifact = store.get_artifact(artifact_id)
    if artifact is None:
        return _error("validation", f"未知数据集 {artifact_id}", status=404)
    target = Path(paths.ROOT) / artifact["path"]
    if not target.is_file():
        return _error("validation", f"数据集文件不存在：{artifact['path']}", status=404)
    return StreamingResponse(iter([target.read_bytes()]), media_type="application/x-ndjson",
                             headers={"Content-Disposition":
                                      f'attachment; filename="{artifact["name"].replace("/", "_")}.jsonl"'})


# ---- artifact versions（不可变版本 / integrity / 预览 / 导出，PR B §4.2）----

@console_router.get("/console/api/artifacts/{artifact_id:path}/versions")
def get_artifact_versions(artifact_id: str, store: Store = Depends(get_store)):
    """产物的版本列表（每项现算 integrity）；未知产物 404，历史无版本返回 []（不 500）。"""
    if store.get_artifact(artifact_id) is None:
        return _error("validation", f"未知产物 {artifact_id}", status=404)
    return [{**v, "integrity": artifacts.integrity(v)} for v in store.list_artifact_versions(artifact_id)]


@console_router.get("/console/api/artifact-versions/{version_id}/records")
def get_artifact_version_records(version_id: str, offset: int = 0, limit: int = 100,
                                 q: str = "", verdict: str = "", store: Store = Depends(get_store)):
    """版本快照的 JSONL 分页预览，逐行带指纹；未知版本 404。"""
    version = store.get_artifact_version(version_id)
    if version is None:
        return _error("validation", f"未知版本 {version_id}", status=404)
    return artifacts.preview_records(version, offset=offset, limit=limit, q=q, verdict=verdict)


@console_router.get("/console/api/artifact-versions/{version_id}/export")
def export_artifact_version(version_id: str, store: Store = Depends(get_store)):
    """导出版本快照指向的文件（文件名策略同 export_dataset）；未知版本或文件缺失 404。"""
    version = store.get_artifact_version(version_id)
    if version is None:
        return _error("validation", f"未知版本 {version_id}", status=404)
    target = Path(paths.ROOT) / version["path"]
    if not target.is_file():
        return _error("validation", f"版本文件不存在：{version['path']}", status=404)
    filename = version["artifact_id"].replace(":", "_").replace("/", "_")
    return StreamingResponse(iter([target.read_bytes()]), media_type="application/x-ndjson",
                             headers={"Content-Disposition":
                                      f'attachment; filename="{filename}.jsonl"'})


# ---- stage param specs + plan + job templates -------------------------

@console_router.get("/console/api/plan/{scenario}")
def get_plan(scenario: str, store: Store = Depends(get_store)):
    """plan_size 产物的 total_records，用于回填 generate --n。

    找不到计划、或计划里缺 total_records（作业未完成/产物已清理），都按 field="n"
    回 404，前端据此在 --n 输入框下提示「先跑 plan_size」，而不是静默失败。
    """
    artifact = store.get_artifact(f"plan:{scenario}")
    if artifact is None:
        return _error("validation", f"尚未生成计划：{scenario}（先跑 plan_size）",
                      status=404, field="n",
                      hint="运行 plan_size 后这里会给出 total_records")
    total = (artifact.get("meta") or {}).get("total_records")
    if total is None:
        return _error("validation", f"计划缺少 total_records：{scenario}",
                      status=404, field="n",
                      hint="plan_size 作业可能尚未完成或产物被清理")
    return {"scenario": scenario, "total_records": int(total), "artifact_id": artifact["id"]}


@console_router.get("/console/api/stage/{kind}/params")
def get_stage_params(kind: str, store: Store = Depends(get_store)):
    """读取某作业类型的提交表单 schema（字段/默认/必填），前端据此动态渲染。"""
    fields, version, source = store.get_stage_params(kind)
    return {"kind": kind, "fields": fields, "version": version, "source": source}


@console_router.put("/console/api/stage/{kind}/params")
def put_stage_params(kind: str, payload: dict, store: Store = Depends(get_store)):
    """改某作业类型的提交表单 schema：版本 +1，旧版本进 stage_param_spec_history。"""
    fields = payload.get("fields")
    if not isinstance(fields, list):
        return _error("validation", "fields 必须是数组", status=400, field="fields")
    saved = store.save_stage_params(kind, fields)
    return {"kind": kind, "fields": saved["fields"], "version": saved["version"], "source": "db"}


@console_router.get("/console/api/stage/{kind}/params/versions")
def get_stage_param_versions(kind: str, store: Store = Depends(get_store)):
    """列出某 kind 的历史版本（每次保存都会归档旧版本）。"""
    return store.list_stage_param_versions(kind)


@console_router.post("/console/api/stage/{kind}/params/rollback")
def post_stage_params_rollback(kind: str, payload: dict, store: Store = Depends(get_store)):
    """回滚到某一历史版本：把该版本 schema 作为新版本写回（版本+1，当前版本先归档）。"""
    version = payload.get("version")
    if not isinstance(version, int) or isinstance(version, bool):
        return _error("validation", "version 必填且为整数", status=400, field="version")
    saved = store.rollback_stage_params(kind, version)
    if saved is None:
        return _error("validation", f"找不到历史版本 {version}", status=404, field="version")
    return {"kind": kind, "fields": saved["fields"], "version": saved["version"], "source": "db"}


@console_router.get("/console/api/job-templates")
def list_job_templates(kind: str | None = None, store: Store = Depends(get_store)):
    """列出命名作业模板；可选按 kind 过滤（如只列 dataset 阶段的模板）。"""
    return store.list_job_templates(kind)


@console_router.post("/console/api/job-templates")
def create_job_template(payload: dict, store: Store = Depends(get_store)):
    kind = (payload.get("kind") or "").strip()
    name = (payload.get("name") or "").strip()
    if not kind:
        return _error("validation", "kind 必填", status=400, field="kind")
    if not name:
        return _error("validation", "模板名必填", status=400, field="name")
    params = payload.get("params")
    if not isinstance(params, dict):
        return _error("validation", "params 必须是对象", status=400, field="params")
    scenario = (payload.get("scenario") or "").strip()
    template_id = store.create_job_template(kind=kind, name=name, scenario=scenario, params=params)
    return store.get_job_template(template_id)


@console_router.put("/console/api/job-templates/{template_id}")
def update_job_template(template_id: str, payload: dict, store: Store = Depends(get_store)):
    if store.get_job_template(template_id) is None:
        return _error("validation", f"未知模板 {template_id}", status=404)
    return store.update_job_template(
        template_id,
        name=(payload.get("name") or "").strip() or None,
        scenario=payload.get("scenario"),
        params=payload.get("params"))


@console_router.delete("/console/api/job-templates/{template_id}")
def delete_job_template(template_id: str, store: Store = Depends(get_store)):
    if not store.delete_job_template(template_id):
        return _error("validation", f"未知模板 {template_id}", status=404)
    return {"deleted": True}


# ---- jobs -------------------------------------------------------------

@console_router.post("/console/api/jobs/preview")
def preview_job(payload: dict, store: Store = Depends(get_store)):
    prepared = _prepare(store, payload)
    if isinstance(prepared, JSONResponse):
        return prepared
    _, _, built = prepared
    return {"argv": [str(part) for part in built.argv], "env": built.env,
            "artifacts_in": built.artifacts_in, "artifacts_out": built.artifacts_out,
            "outcome": REGISTRY[payload["kind"]].outcome}


@console_router.post("/console/api/jobs")
def submit_job(payload: dict, request_: Request, store: Store = Depends(get_store),
               executor: LocalExecutor = Depends(get_executor)):
    prepared = _prepare(store, payload)
    if isinstance(prepared, JSONResponse):
        return prepared
    stage, request, built = prepared

    # 归属项目是提交的硬前提（D14）：缺/空 → 400，幽灵项目（不在 projects 表）→ 404，
    # 绝不能把作业悄悄挂在一个悬空 project_id 上。
    project_id = (payload.get("project_id") or "").strip()
    if not project_id:
        return _error("validation", "project_id 必填", status=400, field="project_id")
    project = store.get_project(project_id)
    if project is None:
        return _error("validation", f"未知项目 {project_id}", status=404)

    # D1：一个项目 = 一个场景的一轮。项目未绑场景（遗留行）先补场景；
    # 作业场景与项目场景不一致则拒绝，绝不允许跨项目串场景。
    if not project["scenario"]:
        return _error("conflict", "项目尚未绑定场景", status=409,
                      hint="先给项目补上场景再提交")
    if request.scenario != project["scenario"]:
        return _error("conflict", f"作业场景 {request.scenario} 与项目场景 {project['scenario']} 不一致",
                      status=409)

    if stage.kind == "train":
        # 单 GPU 闸。kev.experiment 在 Windows 上不可 import（experiment.py:14
        # 直接 import fcntl），所以这道闸必须自己实现。
        live = store.active_job_of_kind("train")
        if live is not None:
            return _error("conflict", f"已有训练在跑（作业 {live['id'][:8]}）", status=409,
                          hint="单 GPU 上同时只应有一个训练；先取消或等它结束")

    if stage.kind == "compare":
        # kev.compare 会因两侧 suite_sha256 不一致直接 ValueError（compare.py:39-40），
        # 预检把它变成可读的 409。
        reason = eval_stages.suite_hash_mismatch(
            built.argv[built.argv.index("--candidate") + 1],
            built.argv[built.argv.index("--reference") + 1])
        if reason:
            return _error("conflict", f"compare 两侧不可比：{reason}", status=409,
                          hint="两侧必须用同一份数据；--data 模式下 suite_sha256 是数据文件的内容哈希")

    failed = [gate for gate in evaluate(stage.stage, **_gate_products(store, request))
              if not gate.ok]
    if failed:
        # 闸门失败是配置问题不是执行问题 —— 不落库（spec §6.1）
        return _error("gate", f"{len(failed)} 道闸未通过", status=422, stderr_tail=json.dumps(
            [{"id": g.id, "detail": g.detail, "actual": g.actual, "need": g.need}
             for g in failed], ensure_ascii=False))

    return JSONResponse(status_code=201, content=store.get_job(
        _spawn(store, executor, stage, request, built,
               gpu_lock=request_.app.state.gpu_lock,
               template_id=payload.get("template_id") or None)))


@console_router.get("/console/api/jobs")
def get_jobs(status: str | None = None, stage: str | None = None,
             scenario: str | None = None, project: str | None = None,
             store: Store = Depends(get_store)) -> list:
    return store.list_jobs(status=status, stage=stage, scenario=scenario, project=project)


@console_router.get("/console/api/jobs/{job_id}")
def get_job(job_id: str, store: Store = Depends(get_store),
            executor: LocalExecutor = Depends(get_executor)):
    job = store.get_job(job_id)
    if job is None:
        return _error("validation", f"未知作业 {job_id}", status=404)
    found = [store.get_artifact(a) for a in job["artifacts_in"] + job["artifacts_out"]]
    buffer = executor.metrics(job_id)
    # 倒序取尾页：read_events 默认按 id 升序取最早 500 行，训练收尾才出现的 saved
    # note 在任何真实 run 里都不会浮出来（Task 2 评审发现）
    return {**job, "metrics": buffer.points(), "metrics_dropped": buffer.dropped(),
            "artifacts": [a for a in found if a],
            "notes": [n for n in (parse_note(e["line"])
                                  for e in reversed(store.read_events(job_id, limit=500)))
                      if n]}


@console_router.post("/console/api/jobs/{job_id}/cancel")
def cancel_job(job_id: str, store: Store = Depends(get_store),
              executor: LocalExecutor = Depends(get_executor)):
    if store.get_job(job_id) is None:
        return _error("validation", f"未知作业 {job_id}", status=404)
    job = store.get_job(job_id)
    # distill_daemon runs as a separate daemon_runner process: in addition
    # to sending SIGTERM to its Popen, set the loopback cancel flag so the
    # daemon_runner can gracefully tear down its inner generate_data.py
    # child (Popen) before exiting. The flag survives a brief blip when the
    # daemon is between polls.
    if job["stage"] == "distill_daemon" and job.get("daemon_id"):
        set_daemon_cancel(job["daemon_id"])
    return {"canceled": executor.cancel_job(job_id)}


@console_router.post("/console/api/jobs/{job_id}/retry")
def retry_job(job_id: str, request_: Request, store: Store = Depends(get_store),
              executor: LocalExecutor = Depends(get_executor)):
    job = store.get_job(job_id)
    if job is None:
        return _error("validation", f"未知作业 {job_id}", status=404)
    if job["status"] not in {"failed", "canceled", "interrupted"}:
        return _error("conflict", f"{job['status']} 的作业不能重试", status=409)
    attempt = job["attempt"] + 1
    # 换名而非复用目录：kev.train / evaluate_records 都是 mkdir(exist_ok=False)，
    # 且旧产物要永久保留（可审计）。attempt 递增、parent_id 指向原作业。
    payload = {"kind": job["kind"], "scenario": job["scenario"],
               "project_id": job["project_id"],
               "run_name": f"{job['title']}-r{attempt}", "params": job["request"]}
    prepared = _prepare(store, payload)
    if isinstance(prepared, JSONResponse):
        return prepared
    stage, request, built = prepared
    return JSONResponse(status_code=201, content=store.get_job(
        _spawn(store, executor, stage, request, built,
               attempt=attempt, parent_id=job_id,
               gpu_lock=request_.app.state.gpu_lock,
               template_id=job.get("template_id"))))


@console_router.get("/console/api/jobs/{job_id}/events")
def get_events(job_id: str, after_id: int = 0, store: Store = Depends(get_store)) -> dict:
    return {"events": store.read_events(job_id, after_id=after_id)}


@console_router.get("/console/api/jobs/{job_id}/stream")
async def stream_job(job_id: str, request: Request, after_id: int = 0,
                     store: Store = Depends(get_store)):
    if store.get_job(job_id) is None:
        return _error("validation", f"未知作业 {job_id}", status=404)
    # EventSource 断线自动重连时**沿用原 URL**，Last-Event-ID 只以 header 形式回来。
    # 只读查询参数会让重连从 after_id=0 全量重放（Task 2 评审发现）—— 所以 header 优先。
    cursor = int(request.headers.get("last-event-id") or after_id or 0)

    async def frames():
        nonlocal cursor
        while True:
            if await request.is_disconnected():
                break
            rows = store.read_events(job_id, after_id=cursor, limit=STREAM_BATCH)
            for row in rows:
                cursor = row["id"]
                yield sse_frame(row, parse_step(row["line"]))
            job = store.get_job(job_id)
            if not rows and job and job["status"] in {
                    "succeeded", "failed", "canceled", "interrupted"}:
                yield ("event: status\ndata: "
                       + json.dumps({"status": job["status"],
                                     "exit_code": job["exit_code"]}) + "\n\n")
                break
            if not rows:
                yield "event: ping\ndata: {}\n\n"
            await asyncio.sleep(POLL_SECONDS if not rows else 0)

    return StreamingResponse(frames(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})


@console_router.get("/console/api/jobs/{job_id}/log")
def get_job_log(job_id: str, tail: int = 200_000,
                store: Store = Depends(get_store)) -> dict:
    """读取 job.log 文件的尾部。

    SSE 回放的是 events 表（UI 跟随输出的来源）；日志**文件**才是真相源，终态作业的
    结果页用它展示完整日志。tail 截尾防止把几百 MB 的训练日志整份塞进响应。
    """
    job = store.get_job(job_id)
    if job is None:
        return _error("validation", f"未知作业 {job_id}", status=404)
    log = Path(job["log_path"])
    if not log.is_file():
        return {"job_id": job_id, "log_path": job["log_path"], "name": log.name,
                "exists": False, "content": "", "truncated": False}
    text = log.read_text(encoding="utf-8", errors="replace")
    truncated = len(text) > tail
    return {"job_id": job_id, "log_path": job["log_path"], "name": log.name,
            "exists": True, "content": text[-tail:] if truncated else text,
            "truncated": truncated}


# ---- artifacts / gates / endpoints ------------------------------------

@console_router.get("/console/api/artifacts")
def get_artifacts(kind: str | None = None, store: Store = Depends(get_store)) -> list:
    rows = store.list_artifacts(kind)
    for row in rows:
        row["lineage"] = store.lineage_of(row["id"])
    return rows


@console_router.get("/console/api/artifacts/{artifact_id:path}/content")
def get_artifact_content(artifact_id: str, tail: int = 200_000,
                         store: Store = Depends(get_store)) -> dict:
    """读取产物文件的文本内容（plan/comparison/calibration 等结果页直接展示用）。"""
    artifact = store.get_artifact(artifact_id)
    if artifact is None:
        return _error("validation", f"未知产物 {artifact_id}", status=404)
    target = Path(paths.ROOT) / artifact["path"]
    if not target.is_file():
        return _error("validation", f"产物文件不存在：{artifact['path']}", status=404)
    try:
        text = target.read_text(encoding="utf-8", errors="replace")
    except (OSError, UnicodeError):
        return _error("validation", f"产物不是可读文本：{artifact['path']}", status=415)
    truncated = len(text) > tail
    return {"id": artifact["id"], "kind": artifact["kind"], "path": artifact["path"],
            "bytes": artifact.get("bytes"), "content": text[-tail:] if truncated else text,
            "truncated": truncated}


# 入参路径查看的文本类型白名单：与产物内容一样只回文本，二进制/权重文件拒读。
FILE_TEXT_SUFFIXES = frozenset({".json", ".jsonl", ".md", ".txt", ".csv", ".yaml", ".yml"})


@console_router.get("/console/api/files/content")
def get_file_content(path: str, tail: int = 200_000) -> dict:
    """读取仓库相对文件（data/ 与 runs/ 之下）的文本内容。

    作业的入参里有一批不是注册产物、而是直接写路径的字段（如 make_examples 的
    --data data/critical-value.jsonl、goldset 的 --out）。产物接口按 id 查、覆盖不到
    它们，所以这里给一条只读白名单：仅限 data/ 与 runs/ 顶层、拒绝绝对路径与 ..、
    解析后必须仍在 ROOT 内、只允许文本后缀 —— 这是本地控制台的查看面，不是通用文件服务。
    """
    norm = path.replace("\\", "/")
    parts = [p for p in norm.split("/") if p not in ("", ".")]
    if norm.startswith("/") or not parts or ".." in parts:
        return _error("validation", f"非法路径：{path}", status=400, field="path")
    if parts[0] not in (paths.DATA_REL, paths.RUNS_REL):
        return _error("validation", f"只允许读取 {paths.DATA_REL}/ 与 {paths.RUNS_REL}/ 下的文件",
                      status=400, field="path")
    if Path(parts[-1]).suffix.lower() not in FILE_TEXT_SUFFIXES:
        return _error("validation", f"不是可读文本文件类型：{path}", status=415, field="path")
    root = Path(paths.ROOT)
    target = root.joinpath(*parts).resolve()
    if not target.is_relative_to(root):   # 符号链接等逃逸的最后防线
        return _error("validation", f"非法路径：{path}", status=400, field="path")
    if not target.is_file():
        return _error("validation", f"文件不存在：{path}", status=404, field="path")
    try:
        text = target.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return _error("validation", f"无法读取文件：{path}", status=415, field="path")
    truncated = len(text) > tail
    return {"path": path, "bytes": target.stat().st_size,
            "content": text[-tail:] if truncated else text, "truncated": truncated}


@console_router.get("/console/api/stages")
def get_stages() -> dict:
    """只读阶段元数据：kind -> {kind, stage, title, outcome, gates}。

    供前端「提交作业」页顶部的操作解析卡使用。全部取自既有结构化真相源
    （stages.REGISTRY 的 StageSpec 与 gates.STAGE_GATES），这里不写任何描述性
    文案 —— 前端不许复制一份闸门归属或 outcome，否则后端一改就会漂移。
    """
    return {spec.kind: {"kind": spec.kind, "stage": spec.stage, "title": spec.title,
                        "outcome": spec.outcome,
                        "gates": list(STAGE_GATES.get(spec.stage, []))}
            for spec in REGISTRY.values()}


@console_router.get("/console/api/gates/{stage}")
def get_gates(stage: str, scenario: str = "critical-value",
              run_name: str = "", data: str = "", store: Store = Depends(get_store)) -> list:
    # data 必须能显式传：阶段表单里有这个字段，用户一旦填了非默认目录，
    # 闸门若仍按 data/<scenario> 推导就永远查不到产物，而症状是「缺少报告」，
    # 看不出是 id 对不上（仓库里现成的 data/cv 就属于这种情况）。
    params = {"data": data} if data else {}
    gates = evaluate(stage, **_gate_products(store, JobRequest(
        scenario=scenario, run_name=run_name, params=params)))
    return [{"id": g.id, "ok": g.ok, "detail": g.detail,
             "actual": g.actual, "need": g.need} for g in gates]


@console_router.get("/console/api/endpoints")
def get_endpoints(store: Store = Depends(get_store)) -> dict:
    return {"endpoints": store.list_artifacts("endpoint")}


# ---- api keys ---------------------------------------------------------

@console_router.post("/console/api/apikeys")
def create_api_key(payload: dict, store: Store = Depends(get_store)):
    name = (payload.get("name") or "").strip()
    if not name:
        return _error("validation", "名称必填", status=400, field="name")
    key_id, meta = store.create_api_key(name)
    return JSONResponse(status_code=201, content={"key": key_id, **meta})


@console_router.get("/console/api/apikeys")
def list_api_keys(all: bool = False, page: int = 1, page_size: int = 20, store: Store = Depends(get_store)):
    # ?all=1 返回全集（首页下拉用）；否则返回分页信封 {items,total,page,page_size}。
    if all:
        return store.list_api_keys(page_size=10 ** 9)[0]
    items, total = store.list_api_keys(page=page, page_size=page_size)
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@console_router.delete("/console/api/apikeys/{key_id}")
def delete_api_key(key_id: str, store: Store = Depends(get_store)):
    if not store.revoke_api_key(key_id):
        return _error("validation", f"未知或已撤销的 key {key_id}", status=404)
    return {"revoked": True}


@console_router.post("/console/api/apikeys/{key_id}/reactivate")
def reactivate_api_key(key_id: str, store: Store = Depends(get_store)):
    if not store.reactivate_api_key(key_id):
        return _error("validation", f"未知或已启用的 key {key_id}", status=404)
    return {"reactivated": True}


# ---- usage -------------------------------------------------------------

@console_router.get("/console/api/usage")
def usage_summary(from_ts: str | None = None, to_ts: str | None = None,
                  store: Store = Depends(get_store)) -> list:
    return store.usage_summary(from_ts, to_ts)


@console_router.get("/console/api/usage/{key_id}")
def usage_timeseries(key_id: str, from_ts: str | None = None, to_ts: str | None = None,
                     store: Store = Depends(get_store)) -> list:
    return store.usage_timeseries(key_id, from_ts, to_ts)


# ---- projects / members / quota / webhooks / billing (ch6) -------------

@console_router.get("/console/api/projects")
def list_projects(store: Store = Depends(get_store)) -> list:
    return store.list_projects()


@console_router.post("/console/api/projects")
def create_project(payload: dict, store: Store = Depends(get_store)):
    slug = (payload.get("slug") or "").strip()
    name = (payload.get("name") or "").strip()
    if not slug:
        return _error("validation", "slug 必填", status=400, field="slug")
    if not name:
        return _error("validation", "名称必填", status=400, field="name")
    # D1：一个项目 = 一个已知场景的一轮；scenario 必填且必须已存在于 scenarios 表。
    scenario = (payload.get("scenario") or "").strip()
    if not scenario:
        return _error("validation", "scenario 必填", status=400, field="scenario",
                      hint="项目必须绑定一个已有场景")
    if not store.scenario_known(scenario):
        return _error("validation", f"未知场景 {scenario}", status=400, field="scenario",
                      hint="场景必须已存在")
    try:
        pid = store.create_project(slug=slug, name=name,
                                   description=(payload.get("description") or "").strip(),
                                   scenario=scenario,
                                   goal=(payload.get("goal") or "").strip())
    except sa.exc.IntegrityError:
        return _error("conflict", f"项目 slug 已存在：{slug}", status=409, field="slug")
    return JSONResponse(status_code=201, content=store.get_project(pid))


@console_router.get("/console/api/projects/{project_id}")
def get_project(project_id: str, store: Store = Depends(get_store)):
    summary = store.project_summary(project_id)
    if summary is None:
        return _error("validation", f"未知项目 {project_id}", status=404)
    return summary


@console_router.get("/console/api/projects/{project_id}/artifacts")
def get_project_artifacts(project_id: str, store: Store = Depends(get_store)):
    if store.get_project(project_id) is None:
        return _error("validation", f"未知项目 {project_id}", status=404)
    return store.list_project_artifacts(project_id)


@console_router.get("/console/api/projects/{project_id}/events")
def get_project_events(project_id: str, after_id: int = 0, store: Store = Depends(get_store)):
    if store.get_project(project_id) is None:
        return _error("validation", f"未知项目 {project_id}", status=404)
    return {"events": store.project_events(project_id, after_id=after_id)}


@console_router.put("/console/api/projects/{project_id}")
def update_project(project_id: str, payload: dict, store: Store = Depends(get_store)):
    if store.get_project(project_id) is None:
        return _error("validation", f"未知项目 {project_id}", status=404)
    try:
        proj = store.update_project(project_id, name=payload.get("name"), slug=payload.get("slug"),
                                    description=payload.get("description"),
                                    scenario=payload.get("scenario"), status=payload.get("status"),
                                    goal=payload.get("goal"), archived_at=payload.get("archived_at"),
                                    freeze_min_records=payload.get("freeze_min_records"),
                                    freeze_min_review_ratio=payload.get("freeze_min_review_ratio"))
    except Conflict as error:  # D9：项目已有 job/bundle 时 slug 不可改
        return _error("conflict", error.message, status=409, field="slug", hint=error.hint)
    return proj or _error("validation", f"未知项目 {project_id}", status=404)


@console_router.delete("/console/api/projects/{project_id}")
def delete_project(project_id: str, store: Store = Depends(get_store)):
    if not store.delete_project(project_id):
        return _error("validation", f"未知项目 {project_id}", status=404)
    return {"deleted": True}


# ---- members -----------------------------------------------------------

_MEMBER_ROLES = ("owner", "admin", "member", "viewer")


@console_router.get("/console/api/projects/{project_id}/members")
def list_members(project_id: str, store: Store = Depends(get_store)) -> list:
    if store.get_project(project_id) is None:
        return _error("validation", f"未知项目 {project_id}", status=404)
    return store.list_members(project_id)


@console_router.post("/console/api/projects/{project_id}/members")
def invite_member(project_id: str, payload: dict, store: Store = Depends(get_store)):
    if store.get_project(project_id) is None:
        return _error("validation", f"未知项目 {project_id}", status=404)
    email = (payload.get("email") or "").strip()
    if not email or "@" not in email:
        return _error("validation", "邮箱必填且需合法", status=400, field="email")
    role = (payload.get("role") or "member")
    if role not in _MEMBER_ROLES:
        return _error("validation", "role 必须是 owner/admin/member/viewer", status=400, field="role")
    mid = store.create_member(project_id=project_id, email=email,
                              name=(payload.get("name") or "").strip(), role=role,
                              status=(payload.get("status") or "invited"))
    return JSONResponse(status_code=201, content=store.get_member(mid))


@console_router.put("/console/api/projects/{project_id}/members/{member_id}")
def update_member(project_id: str, member_id: str, payload: dict,
                  store: Store = Depends(get_store)):
    member = store.get_member(member_id)
    if member is None or member["project_id"] != project_id:
        return _error("validation", f"未知成员 {member_id}", status=404)
    role = payload.get("role")
    if role is not None and role not in _MEMBER_ROLES:
        return _error("validation", "role 必须是 owner/admin/member/viewer", status=400, field="role")
    updated = store.update_member(member_id, role=role, status=payload.get("status"),
                                 name=payload.get("name"))
    return updated or _error("validation", f"未知成员 {member_id}", status=404)


@console_router.delete("/console/api/projects/{project_id}/members/{member_id}")
def remove_member(project_id: str, member_id: str, store: Store = Depends(get_store)):
    member = store.get_member(member_id)
    if member is None or member["project_id"] != project_id:
        return _error("validation", f"未知成员 {member_id}", status=404)
    if not store.delete_member(member_id):
        return _error("validation", f"未知成员 {member_id}", status=404)
    return {"deleted": True}


# ---- quota -------------------------------------------------------------

@console_router.get("/console/api/projects/{project_id}/quota")
def get_quota(project_id: str, store: Store = Depends(get_store)):
    if store.get_project(project_id) is None:
        return _error("validation", f"未知项目 {project_id}", status=404)
    return store.get_quota(project_id)


@console_router.put("/console/api/projects/{project_id}/quota")
def set_quota(project_id: str, payload: dict, store: Store = Depends(get_store)):
    if store.get_project(project_id) is None:
        return _error("validation", f"未知项目 {project_id}", status=404)
    quota = store.set_quota_limits(
        project_id,
        training_hours_limit=Store._quota_num(payload.get("training_hours_limit")),
        gpu_limit=Store._quota_int(payload.get("gpu_limit")),
        api_calls_limit=Store._quota_int(payload.get("api_calls_limit")),
        storage_gb_limit=Store._quota_num(payload.get("storage_gb_limit")))
    return quota


# ---- webhooks ----------------------------------------------------------

@console_router.get("/console/api/projects/{project_id}/webhooks")
def list_webhooks(project_id: str, store: Store = Depends(get_store)) -> list:
    if store.get_project(project_id) is None:
        return _error("validation", f"未知项目 {project_id}", status=404)
    return store.list_webhooks(project_id)


@console_router.post("/console/api/projects/{project_id}/webhooks")
def create_webhook(project_id: str, payload: dict, store: Store = Depends(get_store)):
    if store.get_project(project_id) is None:
        return _error("validation", f"未知项目 {project_id}", status=404)
    url = (payload.get("url") or "").strip()
    if not url:
        return _error("validation", "URL 必填", status=400, field="url")
    events = payload.get("events")
    if isinstance(events, str):
        try:
            events = json.loads(events)
        except ValueError:
            events = []
    if not isinstance(events, list):
        events = []
    wh_id = store.create_webhook(project_id=project_id, url=url, events=events,
                                 secret=(payload.get("secret") or "").strip())
    return JSONResponse(status_code=201, content=store.get_webhook(wh_id))


@console_router.put("/console/api/projects/{project_id}/webhooks/{webhook_id}")
def update_webhook(project_id: str, webhook_id: str, payload: dict,
                   store: Store = Depends(get_store)):
    wh = store.get_webhook(webhook_id)
    if wh is None:
        return _error("validation", f"未知 webhook {webhook_id}", status=404)
    events = payload.get("events")
    if isinstance(events, str):
        try:
            events = json.loads(events)
        except ValueError:
            events = None
    updated = store.update_webhook(webhook_id, url=payload.get("url"), events=events,
                                  secret=payload.get("secret"), active=payload.get("active"))
    return updated or _error("validation", f"未知 webhook {webhook_id}", status=404)


@console_router.delete("/console/api/projects/{project_id}/webhooks/{webhook_id}")
def delete_webhook(project_id: str, webhook_id: str, store: Store = Depends(get_store)):
    if not store.delete_webhook(webhook_id):
        return _error("validation", f"未知 webhook {webhook_id}", status=404)
    return {"deleted": True}


@console_router.post("/console/api/projects/{project_id}/webhooks/{webhook_id}/ping")
def ping_webhook(project_id: str, webhook_id: str, store: Store = Depends(get_store)):
    wh = store.get_webhook(webhook_id)
    if wh is None:
        return _error("validation", f"未知 webhook {webhook_id}", status=404)
    try:
        resp = requests.post(wh["url"], json={"type": "ping", "hook_id": webhook_id}, timeout=10)
        status = resp.status_code
    except requests.RequestException as cause:
        status = 0
    store.record_webhook_delivery(webhook_id, status=status)
    return {"status": status}


# ---- invoices (billing) ------------------------------------------------

@console_router.get("/console/api/projects/{project_id}/invoices")
def list_invoices(project_id: str, period: str | None = None,
                  store: Store = Depends(get_store)) -> list:
    if store.get_project(project_id) is None:
        return _error("validation", f"未知项目 {project_id}", status=404)
    return store.list_invoices(project_id, period)


@console_router.post("/console/api/projects/{project_id}/invoices")
def create_invoice(project_id: str, payload: dict, store: Store = Depends(get_store)):
    if store.get_project(project_id) is None:
        return _error("validation", f"未知项目 {project_id}", status=404)
    period = (payload.get("period") or "").strip()
    if not period:
        return _error("validation", "计费周期必填（如 2026-10）", status=400, field="period")
    try:
        amount = float(payload.get("amount"))
    except (ValueError, TypeError):
        return _error("validation", "金额必须是数字", status=400, field="amount")
    inv_id = store.create_invoice(
        project_id=project_id, period=period, amount=amount,
        currency=(payload.get("currency") or "USD").strip(),
        status=(payload.get("status") or "open").strip(),
        due_at=(payload.get("due_at") or None),
        line_items=payload.get("line_items"))
    return JSONResponse(status_code=201, content=store.get_invoice(inv_id))


# ---- kev proxy ---------------------------------------------------------

async def proxy_kev(path: str, request: Request, store: Store = Depends(get_store)):
    # Inference demotion: while a TrainService.train (or future GPU eval) call
    # is in flight on this process, the single GPU is in use and a concurrent
    # /v1/* call would OOM. 503 + Retry-After so the SDK can back off. The
    # gate reads the module-level Event (set by TrainService.train on entry,
    # cleared in finally) so a long-running train doesn't permanently block
    # the proxy.
    from .services import is_training_active
    if is_training_active():
        return Response(
            status_code=503,
            content=json.dumps({"error": "training_in_progress",
                                "detail": "训练占用 GPU，推理临时不可用；请稍后重试"},
                               ensure_ascii=False),
            media_type="application/json",
            headers={"Retry-After": "30"},
        )
    auth = request.headers.get("authorization", "")
    if not auth.startswith("Bearer "):
        return _error("auth", "缺少 API Key", status=401, hint="Authorization: Bearer <key>")
    key_id = auth[7:].strip()
    # 凭据即 key 的 id：前端从服务端列表拿到 id，选中后原样作为 Bearer 提交；
    # 服务端校验该 id 在 api_keys 中存在且 active 即可用，前端无需持有任何密钥。
    key = store.get_key_by_id(key_id)
    if key is None:
        return _error("auth", "API Key 无效或已撤销", status=401)
    method = request.method
    body = await request.body() if method == "POST" else None
    return await asyncio.to_thread(_do_proxy, store, key["id"], path, dict(request.headers),
                                   str(request.url.query), method, body)


# 同一处理函数同时接 POST/GET；给两个方法不同 operationId，避免 OpenAPI 重复 ID 警告。
console_router.add_api_route("/console/api/kev/{path:path}", proxy_kev, methods=["POST"],
                             operation_id="proxy_kev_post")
console_router.add_api_route("/console/api/kev/{path:path}", proxy_kev, methods=["GET"],
                             operation_id="proxy_kev_get")


# ---- distill providers ------------------------------------------------

@console_router.post("/console/api/distill-providers")
def create_distill_provider(payload: dict, store: Store = Depends(get_store)):
    name = (payload.get("name") or "").strip()
    if not name:
        return _error("validation", "名称必填", status=400, field="name")
    base_url = (payload.get("base_url") or "").strip() or "https://api.openai.com/v1"
    model = (payload.get("model") or "").strip()
    if not model:
        return _error("validation", "模型必填", status=400, field="model")
    keys = [k.strip() for k in (payload.get("keys") or []) if k.strip()]
    if not keys:
        return _error("validation", "至少提供一个 API Key", status=400, field="keys")
    daily_limit = int(payload.get("daily_limit") or 500000)
    meta = store.create_distill_provider(name, base_url, model, daily_limit, keys)
    distill_secrets.put(meta["id"], {"keys": keys, "base_url": base_url,
                                     "model": model, "daily_limit": daily_limit})
    return JSONResponse(status_code=201, content=meta)


@console_router.get("/console/api/distill-providers")
def list_distill_providers(store: Store = Depends(get_store)) -> list:
    return store.list_distill_providers()


@console_router.delete("/console/api/distill-providers/{provider_id}")
def delete_distill_provider(provider_id: str, store: Store = Depends(get_store)):
    if store.get_distill_provider(provider_id) is None:
        return _error("validation", f"未知配置 {provider_id}", status=404)
    store.deactivate_distill_provider(provider_id)
    distill_secrets.remove(provider_id)
    return {"deactivated": True}


@console_router.put("/console/api/distill-providers/{provider_id}")
def update_distill_provider(provider_id: str, payload: dict, store: Store = Depends(get_store)):
    if store.get_distill_provider(provider_id) is None:
        return _error("validation", f"未知配置 {provider_id}", status=404)
    name = (payload.get("name") or "").strip()
    base_url = (payload.get("base_url") or "").strip()
    model = (payload.get("model") or "").strip()
    raw_limit = payload.get("daily_limit")
    daily_limit = int(raw_limit) if str(raw_limit).strip() not in ("", "None") else None
    keys = payload.get("keys")
    keys_list = [k.strip() for k in (keys or []) if str(k).strip()] if isinstance(keys, list) else None
    meta = store.update_distill_provider(provider_id,
                                        name=name or None, base_url=base_url or None,
                                        model=model or None, daily_limit=daily_limit, keys=keys_list)
    # 密钥仅在「提供了新的非空密钥」时替换；否则保留服务端既有密钥。
    if keys_list:
        fresh = store.get_distill_provider(provider_id) or {}
        distill_secrets.put(provider_id, {"keys": keys_list, "base_url": fresh.get("base_url", base_url),
                                         "model": fresh.get("model", model),
                                         "daily_limit": fresh.get("daily_limit", daily_limit)})
    return meta


@console_router.get("/console/api/distill/{job_id}/usage")
def distill_job_usage(job_id: str, from_day: str | None = None, to_day: str | None = None,
                     store: Store = Depends(get_store)):
    if store.get_job(job_id) is None:
        return _error("validation", f"未知作业 {job_id}", status=404)
    _ingest_distill_usage(store, job_id)
    return store.distill_usage_by_job(job_id, from_day, to_day)


@console_router.get("/console/api/distill-usage")
def distill_usage(provider_id: str | None = None, from_day: str | None = None,
                  to_day: str | None = None, store: Store = Depends(get_store)) -> list:
    return store.distill_usage_by_provider(provider_id, from_day, to_day)


@console_router.get("/console/api/distill-usage/totals")
def distill_usage_totals(from_day: str | None = None, to_day: str | None = None,
                         store: Store = Depends(get_store)) -> list:
    return store.distill_usage_totals(from_day, to_day)


# ---------------------------------------------------------------------------
# 内部端点（127.0.0.1 only）— kev.console.daemon_runner 透过这两个端点跟主进程握手。
#
# 协议：
#   - 子守护进程 -> 主：POST /console/api/_internal/distill-event
#                   body: {daemon_id, job_id, kind, line, ts}
#                   主进程把 line 写到 events 表里（与 Popen 路径同一张表），
#                   让 Playground 的 job 日志能直接显示守护进程的输出。
#   - 主 -> 子守护：GET /console/api/_internal/distill-cancel?daemon_id=...
#                   主进程只在收到 cancel_job 请求时调用 set_daemon_cancel。
#                   子守护每 2 秒轮询这个端点（见 data_daemon.CANCEL_POLL_SECONDS）。
#
# 127.0.0.1 限制：_assert_loopback 在每个端点入口检查 request.client.host。
# 守护进程通过 KEV_CONSOLE_BASE_URL（默认 127.0.0.1:8790）连过来。
# ---------------------------------------------------------------------------

_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})


def _assert_loopback(request: Request) -> JSONResponse | None:
    """Return a 403 JSONResponse if the request didn't come from loopback.

    None means "allow". The check is by `request.client.host`, which is the
    immediate peer (so a reverse proxy on a public port can still be
    blocked, unless it's also on 127.0.0.1 — which is the only deployment
    we ship for this).
    """
    host = (request.client.host if request.client else "") or ""
    if host in _LOOPBACK_HOSTS:
        return None
    return _error("forbidden", f"内部端点仅允许 127.0.0.1 访问，来自 {host!r}", status=403)


@console_router.post("/console/api/_internal/distill-event")
def internal_distill_event(payload: dict, request: Request,
                          store: Store = Depends(get_store)) -> dict:
    forbidden = _assert_loopback(request)
    if forbidden is not None:
        return forbidden
    job_id = str(payload.get("job_id") or "").strip()
    if not job_id or store.get_job(job_id) is None:
        # 守护进程在 master 重启后发事件是常见场景：旧 job_id 已不存在。
        # 不报错，守护继续工作（事件流到不存在的 job 是它自己的事）。
        return {"ok": True, "skipped": "unknown job"}
    kind = str(payload.get("kind") or "log")
    line = str(payload.get("line") or "")
    if not line:
        return {"ok": True, "skipped": "empty"}
    # 复用 events 表：append_events 接受 (stream, line) 元组列表。
    # 我们用 "distill" stream 名称而非 "system"，让 UI 端以后可以按颜色区分
    # — 但目前 UI 把所有 stream 一视同仁显示，所以这里只是元数据，不影响行为。
    store.append_events(job_id, [("distill", f"[{kind}] {line}")])
    return {"ok": True}


@console_router.get("/console/api/_internal/distill-cancel")
def internal_distill_cancel(daemon_id: str, request: Request) -> dict:
    forbidden = _assert_loopback(request)
    if forbidden is not None:
        return forbidden
    cancels: dict = request.app.state.daemon_cancels
    return {"canceled": cancels.get(daemon_id, threading.Event()).is_set()}


def set_daemon_cancel(daemon_id: str) -> None:
    """Called by the cancel_job endpoint to flag a daemon for shutdown.

    Stored in app.state.daemon_cancels (a dict[daemon_id, Event]) so multiple
    daemons can be tracked independently. The daemon_runner that owns this
    id polls /distill-cancel every 2s and tears down on the next tick.
    """
    store = _daemon_cancel_store()
    event = store.get(daemon_id)
    if event is None:
        event = threading.Event()
        store[daemon_id] = event
    event.set()


# Single-process cancel registry. wire_console_state() replaces this with
# app.state.daemon_cancels at startup; tests can monkeypatch it directly.
_daemon_cancel_registry: dict[str, threading.Event] = {}


def _daemon_cancel_store() -> dict[str, threading.Event]:
    return _daemon_cancel_registry


# ---------------------------------------------------------------------------
# 状态装配：把 store / executor 挂到 app.state，并跑崩溃恢复。create_app 与
# kev.serve 共用同一份——两者都是「控制台所在的进程」，只是前者是独立入口（8790），
# 后者把 server 也塞进 app.state。
# ---------------------------------------------------------------------------

def wire_console_state(app: FastAPI, *, store: Store | None = None,
                       executor: LocalExecutor | None = None) -> None:
    app.state.store = store or Store()
    # 让 stage 模块（data.py 等）在运行时能解析场景 spec_path。
    set_store(app.state.store)
    # 崩溃恢复：WSL2 会自动回收内存，服务重启是常态。必须在**装配时**调用，而不是放进
    # Store.__init__ —— 后者会让任何只读工具 new 一个 Store 就误杀在途作业。
    app.state.store.interrupt_stale_jobs()
    # 作业表对浏览器可读之前先把历史脏数据洗一遍：旧版 distill 曾把密钥库的
    # KEV_GEN_API_KEYS 当作非敏感 overlay 写进 jobs.env_overlay（现已改走
    # BuiltCommand.secrets）。幂等，没脏数据时零写入。
    scrub_secret_overlays(app.state.store)

    def _on_finished(job_id: str, exit_code: int) -> None:
        # 产物注册失败不吞：register_finished 内部会记 system 事件并（必要时）重抛。
        register_finished(app.state.store, job_id, exit_code)

    app.state.executor = executor or LocalExecutor(app.state.store, on_finished=_on_finished)
    # Process-wide GPU lock. Held while a TrainService.train (or future
    # EvalService baseline/benchmark) call is running; every other GPU
    # service queues on it. Compare/Calibrate services run on CPU and never
    # touch this lock. Without the lock, two concurrent GPU services can
    # OOM the single-GPU box (the failure mode that motivated this in the
    # first place — see plan Wave B / Task B-2 acceptance).
    app.state.gpu_lock = threading.Lock()
    # Per-daemon cancel flags. The master process stores a threading.Event
    # for each running daemon_runner subprocess; the daemon polls its flag
    # via /_internal/distill-cancel and tears its child Popen down on set.
    app.state.daemon_cancels = _daemon_cancel_registry


# ---------------------------------------------------------------------------
# 独立入口（python -m kev.console，8790，无模型也能跑编排）。
# ---------------------------------------------------------------------------

def create_app(*, store: Store | None = None, executor: LocalExecutor | None = None) -> FastAPI:
    app = FastAPI(title="kev-console")
    wire_console_state(app, store=store, executor=executor)
    app.include_router(console_router)
    return app
