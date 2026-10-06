"""编排服务的 HTTP 面：作业提交、闸门预检、产物血缘、SSE 日志流。

路由清单见 spec §10.1。playground 侧只有一个薄代理（`/api/console/[...path]`），
所以这里不关心 CORS；编排服务只绑 127.0.0.1、无鉴权（本地单用户，spec §12）。

SSE 从 events 表按 id 游标轮询，而不是靠进程内的队列：日志文件才是真相源，
这样多进程、重启、`Last-Event-ID` 续传都天然成立。
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import uuid
from pathlib import Path

import requests

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

from . import artifacts, paths
from . import secrets as distill_secrets
from .db import Store
from .events import parse_note, parse_step, sse_frame
from .executor import LocalExecutor
from .gates import evaluate
from .stages import REGISTRY, Conflict, Invalid, JobRequest
from .stages import data as data_stages
from .stages import eval as eval_stages
from .stages import train as train_stages

DB_ENV = "KEV_CONSOLE_DB"
POLL_SECONDS = 0.5
STREAM_BATCH = 200
# 只回布尔态：凭据值永远不下发到浏览器（spec §12）
SECRET_NAMES = ("KEV_API_KEY", "KEV_GEN_API_KEYS", "KEV_HF_SECRET",
                 "KEV_SERVE_SECRET", "HF_TOKEN")


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
        "plan": request.params.get("plan"),
        "report": load("eval", request.run_name),
        "comparison": load("comparison", request.run_name),
        "calibration": load("calibration", request.run_name),
    }


def create_app(*, store: Store | None = None, executor: LocalExecutor | None = None) -> FastAPI:
    app = FastAPI(title="kev-console")
    app.state.store = store or Store(Path(os.environ.get(DB_ENV, paths.DB_PATH)))
    # 崩溃恢复：WSL2 会自动回收内存，服务重启是常态。必须在**建 app 时**调用，而不是放进
    # Store.__init__ —— 后者会让任何只读工具 new 一个 Store 就误杀在途作业。
    app.state.store.interrupt_stale_jobs()

    def register_finished(job_id, exit_code) -> None:
        """产物注册的唯一入口（长驻作业除外，它们在 spawn 后立刻注册）。

        注册失败**不吞**：记一条 system 事件后重抛。没有它的话，executor 那边的
        `except Exception: pass` 会让产物缺失完全静默（作业显示 succeeded 而产物不存在）。
        """
        job = app.state.store.get_job(job_id)
        if job is None or exit_code != 0:
            return
        try:
            artifacts.register(app.state.store, job)
        except Exception as error:
            app.state.store.append_events(
                job_id, [("system", f"产物注册失败：{error!r}（重跑该作业即可重新注册）")])
            raise

    app.state.executor = executor or LocalExecutor(app.state.store,
                                                  on_finished=register_finished)

    def store() -> Store:
        return app.state.store

    def _spawn(stage, request: JobRequest, built, *, attempt=1, parent_id=None) -> str:
        log_path = paths.JOB_LOGS / f"{uuid.uuid4().hex}.log"
        job_id = app.state.store.create_job(
            kind=stage.kind, stage=stage.stage, scenario=request.scenario,
            title=request.run_name or stage.title, request=request.params,
            argv=[str(part) for part in built.argv], env_overlay=built.env,
            cwd=built.cwd or str(paths.ROOT), log_path=str(log_path),
            artifacts_in=built.artifacts_in, artifacts_out=built.artifacts_out,
            attempt=attempt, parent_id=parent_id)
        app.state.executor.spawn(job_id, built.argv, cwd=built.cwd or str(paths.ROOT),
                                 log_path=str(log_path), env_overlay=built.env)
        if stage.persist == "start":
            # 长驻作业（kev.serve）永远不「完成」，产物必须在 spawn 之后立刻注册，
            # 否则端点列表永远是空的。在线状态由部署页实际探 /v1/models 决定。
            artifacts.register(app.state.store, app.state.store.get_job(job_id))
        return job_id

    def _prepare(payload: dict):
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
        return stage, request, built

    # ---- config / scenarios ----------------------------------------------

    @app.get("/console/api/config")
    def get_config(scenario: str = "critical-value") -> dict:
        # 三种微调方式的默认值只在这里暴露一次，前端不许硬编码
        return {
            "scenarios": list(data_stages.SCENARIOS),
            "methods": train_stages.methods_for(scenario),
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

    # ---- datasets ---------------------------------------------------------

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
        target = Path(paths.ROOT) / artifact["path"]
        if not target.is_file():
            return _error("validation", f"数据集文件不存在：{artifact['path']}", status=404)
        return StreamingResponse(iter([target.read_bytes()]), media_type="application/x-ndjson",
                                 headers={"Content-Disposition":
                                          f'attachment; filename="{artifact["name"].replace("/", "_")}.jsonl"'})

    # ---- jobs -------------------------------------------------------------

    @app.post("/console/api/jobs/preview")
    def preview_job(payload: dict):
        prepared = _prepare(payload)
        if isinstance(prepared, JSONResponse):
            return prepared
        _, _, built = prepared
        return {"argv": [str(part) for part in built.argv], "env": built.env,
                "artifacts_in": built.artifacts_in, "artifacts_out": built.artifacts_out,
                "outcome": REGISTRY[payload["kind"]].outcome}

    @app.post("/console/api/jobs")
    def submit_job(payload: dict):
        prepared = _prepare(payload)
        if isinstance(prepared, JSONResponse):
            return prepared
        stage, request, built = prepared

        if stage.kind == "train":
            # 单 GPU 闸。kev.experiment 在 Windows 上不可 import（experiment.py:14
            # 直接 import fcntl），所以这道闸必须自己实现。
            live = store().active_job_of_kind("train")
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

        failed = [gate for gate in evaluate(stage.stage, **_gate_products(store(), request))
                  if not gate.ok]
        if failed:
            # 闸门失败是配置问题不是执行问题 —— 不落库（spec §6.1）
            return _error("gate", f"{len(failed)} 道闸未通过", status=422, stderr_tail=json.dumps(
                [{"id": g.id, "detail": g.detail, "actual": g.actual, "need": g.need}
                 for g in failed], ensure_ascii=False))

        return JSONResponse(status_code=201, content=store().get_job(_spawn(stage, request, built)))

    @app.get("/console/api/jobs")
    def get_jobs(status: str | None = None, stage: str | None = None,
                 scenario: str | None = None) -> list:
        return store().list_jobs(status=status, stage=stage, scenario=scenario)

    @app.get("/console/api/jobs/{job_id}")
    def get_job(job_id: str):
        job = store().get_job(job_id)
        if job is None:
            return _error("validation", f"未知作业 {job_id}", status=404)
        found = [store().get_artifact(a) for a in job["artifacts_in"] + job["artifacts_out"]]
        buffer = app.state.executor.metrics(job_id)
        # 倒序取尾页：read_events 默认按 id 升序取最早 500 行，训练收尾才出现的 saved
        # note 在任何真实 run 里都不会浮出来（Task 2 评审发现）
        return {**job, "metrics": buffer.points(), "metrics_dropped": buffer.dropped(),
                "artifacts": [a for a in found if a],
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
        # 换名而非复用目录：kev.train / evaluate_records 都是 mkdir(exist_ok=False)，
        # 且旧产物要永久保留（可审计）。attempt 递增、parent_id 指向原作业。
        payload = {"kind": job["kind"], "scenario": job["scenario"],
                   "run_name": f"{job['title']}-r{attempt}", "params": job["request"]}
        prepared = _prepare(payload)
        if isinstance(prepared, JSONResponse):
            return prepared
        stage, request, built = prepared
        return JSONResponse(status_code=201, content=store().get_job(
            _spawn(stage, request, built, attempt=attempt, parent_id=job_id)))

    @app.get("/console/api/jobs/{job_id}/events")
    def get_events(job_id: str, after_id: int = 0) -> dict:
        return {"events": store().read_events(job_id, after_id=after_id)}

    @app.get("/console/api/jobs/{job_id}/stream")
    async def stream_job(job_id: str, request: Request, after_id: int = 0):
        if store().get_job(job_id) is None:
            return _error("validation", f"未知作业 {job_id}", status=404)
        # EventSource 断线自动重连时**沿用原 URL**，Last-Event-ID 只以 header 形式回来。
        # 只读查询参数会让重连从 after_id=0 全量重放（Task 2 评审发现）—— 所以 header 优先。
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

    # ---- artifacts / gates / endpoints ------------------------------------

    @app.get("/console/api/artifacts")
    def get_artifacts(kind: str | None = None) -> list:
        rows = store().list_artifacts(kind)
        for row in rows:
            row["lineage"] = store().lineage_of(row["id"])
        return rows

    @app.get("/console/api/gates/{stage}")
    def get_gates(stage: str, scenario: str = "critical-value",
                  run_name: str = "", data: str = "") -> list:
        # data 必须能显式传：阶段表单里有这个字段，用户一旦填了非默认目录，
        # 闸门若仍按 data/<scenario> 推导就永远查不到产物，而症状是「缺少报告」，
        # 看不出是 id 对不上（仓库里现成的 data/cv 就属于这种情况）。
        params = {"data": data} if data else {}
        gates = evaluate(stage, **_gate_products(store(), JobRequest(
            scenario=scenario, run_name=run_name, params=params)))
        return [{"id": g.id, "ok": g.ok, "detail": g.detail,
                 "actual": g.actual, "need": g.need} for g in gates]

    @app.get("/console/api/endpoints")
    def get_endpoints() -> dict:
        return {"endpoints": store().list_artifacts("endpoint")}

    # ---- api keys ---------------------------------------------------------

    KEV_SERVE_URL = os.environ.get("KEV_SERVE_URL", "http://127.0.0.1:8008")
    ADMIN_KEY = os.environ.get("KEV_API_KEY")

    def _sha256(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def _ep(path: str) -> str:
        tail = path.rstrip("/").split("/")[-1]
        return {"systemone": "systemone", "separate": "separate",
                "permute": "permute", "models": "models"}.get(tail, tail)

    @app.post("/console/api/apikeys")
    def create_api_key(payload: dict):
        name = (payload.get("name") or "").strip()
        if not name:
            return _error("validation", "名称必填", status=400, field="name")
        raw, meta = store().create_api_key(name)
        return JSONResponse(status_code=201, content={"key": raw, **meta})

    @app.get("/console/api/apikeys")
    def list_api_keys() -> list:
        return store().list_api_keys()

    @app.delete("/console/api/apikeys/{key_id}")
    def delete_api_key(key_id: str):
        if not store().revoke_api_key(key_id):
            return _error("validation", f"未知或已撤销的 key {key_id}", status=404)
        return {"revoked": True}

    # ---- usage -------------------------------------------------------------

    @app.get("/console/api/usage")
    def usage_summary(from_ts: str | None = None, to_ts: str | None = None) -> list:
        return store().usage_summary(from_ts, to_ts)

    @app.get("/console/api/usage/{key_id}")
    def usage_timeseries(key_id: str, from_ts: str | None = None, to_ts: str | None = None) -> list:
        return store().usage_timeseries(key_id, from_ts, to_ts)

    # ---- kev proxy ---------------------------------------------------------

    def _do_proxy(key_id: str, path: str, headers: dict, query: str, method: str, body):
        import time
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
            store().record_usage(key_id=key_id, endpoint=_ep(path), method=method,
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
        store().record_usage(key_id=key_id, endpoint=_ep(path), method=method, status=resp.status_code,
                             input_tokens=in_t, output_tokens=out_t, latency_ms=dt)
        return JSONResponse(status_code=resp.status_code, content=resp.json(),
                             headers={"content-type": resp.headers.get("content-type", "application/json")})

    async def proxy_kev(path: str, request: Request):
        auth = request.headers.get("authorization", "")
        if not auth.startswith("Bearer "):
            return _error("auth", "缺少 API Key", status=401, hint="Authorization: Bearer <key>")
        key = store().get_key_by_hash(_sha256(auth[7:].strip()))
        if key is None:
            return _error("auth", "API Key 无效或已撤销", status=401)
        method = request.method
        body = await request.body() if method == "POST" else None
        return await asyncio.to_thread(_do_proxy, key["id"], path, dict(request.headers),
                                        str(request.url.query), method, body)

    app.add_api_route("/console/api/kev/{path:path}", proxy_kev, methods=["POST", "GET"])

    # ---- distill providers ------------------------------------------------

    @app.post("/console/api/distill-providers")
    def create_distill_provider(payload: dict):
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
        meta = store().create_distill_provider(name, base_url, model, daily_limit, keys)
        distill_secrets.put(meta["id"], {"keys": keys, "base_url": base_url,
                                         "model": model, "daily_limit": daily_limit})
        return JSONResponse(status_code=201, content=meta)

    @app.get("/console/api/distill-providers")
    def list_distill_providers() -> list:
        return store().list_distill_providers()

    @app.delete("/console/api/distill-providers/{provider_id}")
    def delete_distill_provider(provider_id: str):
        if store().get_distill_provider(provider_id) is None:
            return _error("validation", f"未知配置 {provider_id}", status=404)
        store().deactivate_distill_provider(provider_id)
        distill_secrets.remove(provider_id)
        return {"deactivated": True}

    def _ingest_distill_usage(job_id: str) -> None:
        import json as _json
        from pathlib import Path as _Path
        job = store().get_job(job_id)
        if job is None or job["kind"] not in ("distill", "distill_daemon"):
            return
        # 作业未显式传 state_dir 时，与 _distill_build 的缺省保持一致（paths.DEFAULT_DISTILL_STATE_DIR），
        # 保证用量采集端到端可通（spec §9）。
        state_dir = (job["request"].get("state_dir") or str(paths.DEFAULT_DISTILL_STATE_DIR)).strip()
        if not _Path(state_dir).is_dir():
            return
        provider_id = job["request"].get("provider_id") or ""
        prov = store().get_distill_provider(provider_id) or {}
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
                store().upsert_distill_usage(job_id=job_id, provider_id=provider_id, key_hash=kh,
                    key_hint=hint, model=model, base_url=base_url, day=day, tokens=int(tokens or 0))

    @app.get("/console/api/distill/{job_id}/usage")
    def distill_job_usage(job_id: str, from_day: str | None = None, to_day: str | None = None):
        if store().get_job(job_id) is None:
            return _error("validation", f"未知作业 {job_id}", status=404)
        _ingest_distill_usage(job_id)
        return store().distill_usage_by_job(job_id, from_day, to_day)

    @app.get("/console/api/distill-usage")
    def distill_usage(provider_id: str | None = None, from_day: str | None = None,
                      to_day: str | None = None) -> list:
        return store().distill_usage_by_provider(provider_id, from_day, to_day)

    return app
