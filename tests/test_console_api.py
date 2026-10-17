"""编排服务的 HTTP 面：作业提交、闸门预检、产物血缘、SSE 日志流。

用 TestClient，不起真实服务；真作业只做 preview，不 spawn（deploy 除外 ——
它验证长驻作业的产物注册时机）。

Run: uv run python -m pytest tests/test_console_api.py -q
"""
import itertools

import pytest
from fastapi.testclient import TestClient

from kev.console.app import create_app
from kev.console.db import Store


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(store=Store(tmp_path / "db.sqlite"))) as test_client:
        yield test_client


def body(response):
    return response.json()


_slugs = itertools.count()


def _mk_project(client, slug=None, name="P", scenario="triage"):
    """经 POST /projects 建一个合法项目（scenario 默认取已播种的 triage），返回其 id。"""
    payload = {"slug": slug or f"p{next(_slugs)}", "name": name}
    if scenario:
        payload["scenario"] = scenario
    r = client.post("/console/api/projects", json=payload)
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


def submit(client, kind, **params):
    scenario = params.pop("scenario", "triage")
    run_name = params.pop("run_name", "cv-8b-v1")
    project_id = params.pop("project_id", None) or _mk_project(client, scenario=scenario)
    return client.post("/console/api/jobs", json={
        "kind": kind, "scenario": scenario, "run_name": run_name,
        "project_id": project_id, "params": params})


def make_job(store, kind="train", title="t", status="running"):
    """直接造一个指定状态的作业。

    不要用 `submit()` 造状态 —— 它会真的 spawn 子进程，状态不可控（SSE 那些用例要的是
    确定性的 pending/running/终态）。
    """
    project_id = store.create_project(f"fx{next(_slugs)}", "Fx")
    job_id = store.create_job(
        project_id=project_id,
        kind=kind, stage="train", scenario="triage", title=title,
        request={}, argv=["x"], env_overlay={}, cwd=".", log_path="l.log",
        artifacts_in=[], artifacts_out=[])
    for to_status in dict.fromkeys(("queued", "running", status)):   # 去重，避免 running->running
        if to_status in {"succeeded", "failed", "canceled", "interrupted"}:
            store.transition(job_id, to_status, exit_code=0)
        else:
            store.transition(job_id, to_status)
    return job_id


# ---- config --------------------------------------------------------------

def test_config_never_leaks_credential_values(client, monkeypatch):
    monkeypatch.setenv("KEV_GEN_API_KEYS", "sk-super-secret")
    response = client.get("/console/api/config")
    assert body(response)["credentials"]["KEV_GEN_API_KEYS"] is True
    assert "sk-super-secret" not in response.text
    # 温度只能来自 calibration.json，config 里不该有任何温度来源
    assert "KEV_TEMPERATURE" not in body(response)["credentials"]


def test_scenarios_reports_question_counts(client):
    by_name = {row["name"]: row["questions"]
               for row in body(client.get("/console/api/scenarios"))}
    assert by_name["critical-value"] == 4          # 5 个 spec 都是 4 问题/记录


def test_config_exposes_the_three_training_methods(client):
    methods = body(client.get("/console/api/config"))["methods"]
    assert set(methods) == {"a1", "a2", "b"}
    assert methods["a1"]["init_from"] == "jaredpalmer/kev-0.8b"
    assert methods["b"]["weights_dtype"] == "bf16"


def test_icd_coding_disallows_the_eight_b_methods(client):
    methods = body(client.get("/console/api/config?scenario=icd-coding"))["methods"]
    assert methods["a1"]["allowed"] is False
    assert methods["b"]["allowed"] is True


# ---- 提交与校验 ----------------------------------------------------------

def test_preview_returns_argv_without_spawning(client):
    response = client.post("/console/api/jobs/preview", json={
        "kind": "train", "scenario": "critical-value", "run_name": "cv-8b-v1",
        "params": {"method": "a1"}})
    assert "--init_from" in body(response)["argv"]
    assert client.app.state.executor.live() == set(), "preview 绝不能起进程"


def test_unknown_kind_is_404(client):
    for path in ("/console/api/jobs", "/console/api/jobs/preview"):
        response = client.post(path, json={"kind": "nope", "scenario": "triage",
                                           "run_name": "t", "params": {}})
        assert response.status_code == 404


def test_stages_endpoint_exposes_registry_metadata(client):
    """操作解析卡的只读元数据：kind -> StageSpec 字段 + gates.STAGE_GATES 归属。

    前端不许自己复制这两样，所以接口必须与注册表逐项一致。
    """
    from kev.console.gates import STAGE_GATES
    from kev.console.stages import REGISTRY

    stages = body(client.get("/console/api/stages"))
    assert set(stages) == set(REGISTRY)
    train = stages["train"]
    assert train["outcome"] == REGISTRY["train"].outcome
    assert train["gates"] == STAGE_GATES["train"] == ["G1", "G2", "G3"]
    # compare/calibrate 自身不设闸（它们是产出闸门证据的作业）
    assert stages["compare"]["gates"] == []


def test_files_content_reads_whitelisted_repo_files(client, tmp_path, monkeypatch):
    """入参路径查看：只读白名单（data/ 与 runs/、文本后缀、不许跳出 ROOT）。"""
    from kev.console import paths

    monkeypatch.setattr(paths, "ROOT", tmp_path)
    target = tmp_path / "data" / "examples.jsonl"
    target.parent.mkdir(parents=True)
    target.write_text('{"id": 1}\n{"id": 2}\n', encoding="utf-8")

    read = body(client.get("/console/api/files/content", params={"path": "data/examples.jsonl"}))
    assert read["content"].count("\n") == 2 and read["truncated"] is False

    # 拒绝：绝对路径、.. 穿越、白名单之外的顶层目录、非文本后缀、不存在的路径
    for path, status in (("/etc/passwd", 400), ("data/../secret.json", 400),
                         ("kev/console/app.py", 400), ("data/w.bin", 415),
                         ("data/nope.jsonl", 404)):
        assert client.get("/console/api/files/content", params={"path": path}).status_code == status, path


def test_submit_then_read_the_job(client):
    created = submit(client, "plan_size", scenario="critical-value")
    assert created.status_code == 201
    job_id = body(created)["id"]
    assert body(client.get(f"/console/api/jobs/{job_id}"))["kind"] == "plan_size"
    assert job_id in [row["id"] for row in body(client.get("/console/api/jobs"))]


def test_bad_run_name_is_a_400_with_a_hint(client):
    """只有 train/build 调 run_matrix.check_name，所以要用 train 才走得到校验分支。"""
    payload = body(submit(client, "train", run_name="critical-value-0.8b-v1",
                          method="a1"))["error"]
    assert payload["kind"] == "validation"
    assert payload["field"] == "run_name"
    assert "8b" in payload["hint"]


def test_missing_temperature_points_at_calibration(client):
    payload = body(submit(client, "image"))["error"]
    assert payload["field"] == "temperature"
    # 提示必须指向 calibration.json 的 workload_temperature，并说明为什么不能就地拟合
    assert "workload_temperature" in payload["message"]
    assert "development.jsonl" in payload["hint"]


def test_gate_failure_is_422_and_stores_nothing(client, monkeypatch):
    from kev.console.gates import Gate

    monkeypatch.setattr("kev.console.app.evaluate", lambda stage, **p: [
        Gate("G1", False, "3 条记录超出训练上下文", "3", "0")])
    response = submit(client, "train", method="a1")
    assert response.status_code == 422
    assert "G1" in body(response)["error"]["stderr_tail"]
    # 闸门失败是配置问题不是执行问题，不该落库
    assert body(client.get("/console/api/jobs")) == []


def test_a_second_train_is_refused_while_one_is_live(client):
    """单 GPU 闸。kev.experiment 在 Windows 上不可 import（experiment.py:14 直接
    import fcntl），所以这道闸必须自己实现。"""
    make_job(client.app.state.store, kind="train", status="running")
    response = submit(client, "train", method="a1", run_name="cv-8b-v2")
    assert response.status_code == 409
    assert body(response)["error"]["kind"] == "conflict"


def test_submit_requires_project(client):
    r = client.post("/console/api/jobs", json={"kind": "train", "scenario": "triage",
        "run_name": "cv-1", "params": {}})
    assert r.status_code == 400 and r.json()["error"]["field"] == "project_id"


def test_submit_unknown_project(client):
    r = client.post("/console/api/jobs", json={"kind": "train", "scenario": "triage",
        "run_name": "cv-1", "params": {}, "project_id": "does-not-exist"})
    assert r.status_code == 404


def test_submit_lists_by_project(client):
    pid = _mk_project(client)
    r = client.post("/console/api/jobs", json={"kind": "plan_size", "scenario": "triage",
        "run_name": "cv-1", "params": {}, "project_id": pid})
    assert r.status_code == 201
    listed = client.get(f"/console/api/jobs?project={pid}").json()
    assert [j["id"] for j in listed] == [r.json()["id"]]


def test_create_project_requires_known_scenario(client):
    missing = client.post("/console/api/projects", json={"slug": "s", "name": "S"})
    assert missing.status_code == 400 and missing.json()["error"]["field"] == "scenario"
    unknown = client.post("/console/api/projects",
                          json={"slug": "s", "name": "S", "scenario": "nope"})
    assert unknown.status_code == 400


def test_submit_rejects_scenario_mismatch(client):
    pid = _mk_project(client, slug="mm", scenario="triage")
    r = client.post("/console/api/jobs", json={"kind": "plan_size", "scenario": "critical-value",
        "run_name": "cv-1", "params": {}, "project_id": pid})
    assert r.status_code == 409


def test_submit_rejects_project_without_scenario(client):
    # 遗留项目：scenario == ''（D1 之前建的，场景留空）
    pid = client.app.state.store.create_project("legacy-nos", "Legacy")  # scenario 默认 ''
    r = client.post("/console/api/jobs", json={"kind": "plan_size", "scenario": "triage",
        "run_name": "cv-1", "params": {}, "project_id": pid})
    assert r.status_code == 409


def test_update_project_slug_guard_409(client):
    # D9：项目已有 job/bundle 时改 slug → 409（字段标在 slug 上）；其余列照常可改。
    store = client.app.state.store
    pid = store.create_project("slug-a", "A")
    store.create_job(project_id=pid, kind="train", stage="train", scenario="triage",
        title="t", request={}, argv=["x"], env_overlay={}, cwd=".", log_path="l.log",
        artifacts_in=[], artifacts_out=[])
    r = client.put(f"/console/api/projects/{pid}", json={"slug": "slug-b"})
    assert r.status_code == 409
    assert body(r)["error"]["kind"] == "conflict" and body(r)["error"]["field"] == "slug"
    ok = client.put(f"/console/api/projects/{pid}", json={"goal": "ship"})
    assert ok.status_code == 200 and ok.json()["goal"] == "ship"


def test_project_events_endpoint(client):
    store = client.app.state.store
    pid = store.create_project("a", "A")
    jid = store.create_job(project_id=pid, kind="train", stage="train", scenario="triage",
        title="t", request={}, argv=["x"], env_overlay={}, cwd=".", log_path="l.log",
        artifacts_in=[], artifacts_out=[])
    store.append_events(jid, [("stdout", "hi")])
    r = client.get(f"/console/api/projects/{pid}/events")
    assert r.status_code == 200 and "events" in r.json()
    assert r.json()["events"][0]["line"] == "hi"
    # 项目详情现在带计数/阶段
    s = client.get(f"/console/api/projects/{pid}").json()
    assert s["jobs"] == 1 and s["stages"]["train"] == "pending"
    assert client.get("/console/api/projects/nope/events").status_code == 404
    assert client.get(f"/console/api/projects/{pid}/artifacts").status_code == 200


# ---- 事件与 SSE ----------------------------------------------------------

def test_events_page_from_a_cursor(client):
    job_id = body(submit(client, "plan_size"))["id"]
    store = client.app.state.store
    store.append_events(job_id, [("stdout", "one"), ("stdout", "two")])
    first = body(client.get(f"/console/api/jobs/{job_id}/events"))
    assert [row["line"] for row in first["events"]] == ["one", "two"]
    second = body(client.get(f"/console/api/jobs/{job_id}/events",
                             params={"after_id": first["events"][0]["id"]}))
    assert [row["line"] for row in second["events"]] == ["two"]


def test_stream_is_sse_and_resumes_from_last_event_id_header(client):
    """EventSource 断线重连沿用原 URL，Last-Event-ID 只以 header 回来。只读 after_id
    查询参数会让重连从 0 全量重放（Task 2 评审发现，人工验收第 3 项）。"""
    job_id = body(submit(client, "plan_size"))["id"]
    store = client.app.state.store
    store.append_events(job_id, [("stdout", "before")])
    cursor = store.append_events(job_id, [("stdout", "after")])
    with client.stream("GET", f"/console/api/jobs/{job_id}/stream?after_id=0",
                       headers={"Last-Event-ID": str(cursor)}) as response:
        assert response.headers["content-type"].startswith("text/event-stream")
        lines = list(response.iter_lines())
    assert not any('"before"' in line for line in lines), "断点之前的行不该重放"


def test_stream_ends_with_a_status_frame_for_a_finished_job(client):
    job_id = make_job(client.app.state.store, kind="plan_size", status="succeeded")
    with client.stream("GET", f"/console/api/jobs/{job_id}/stream") as response:
        assert any(line == "event: status" for line in response.iter_lines())


# ---- 崩溃恢复与重试 ------------------------------------------------------

def test_startup_marks_live_jobs_interrupted(tmp_path):
    """WSL2 会自动回收内存，服务重启是常态；残留的 running/queued 必须变成 interrupted，
    否则永远卡在 running（spec §9.3、人工验收第 5 项）。"""
    store = Store(tmp_path / "db.sqlite")
    live = make_job(store, kind="train", title="live", status="running")
    done = make_job(store, kind="split", title="done", status="succeeded")

    with TestClient(create_app(store=store)):
        pass                       # 建 app 即触发恢复
    assert store.get_job(live)["status"] == "interrupted"
    assert store.get_job(done)["status"] == "succeeded"


def test_startup_scrubs_legacy_credential_overlays(tmp_path):
    """启动装配要顺手洗掉历史脏行：旧版 distill 把密钥库的 key 当作非敏感 overlay 落过库，
    而 jobs 表对浏览器可读（spec §12）。"""
    store = Store(tmp_path / "db.sqlite")
    project_id = store.create_project("legacy", "Legacy")
    job_id = store.create_job(
        project_id=project_id,
        kind="distill", stage="data", scenario="critical-value", title="legacy",
        request={}, argv=["x"],
        env_overlay={"KEV_GEN_MODEL": "m", "KEV_GEN_API_KEYS": "sk-leaked"},
        cwd=".", log_path="l.log", artifacts_in=[], artifacts_out=[])
    with TestClient(create_app(store=store)):
        pass                       # 建 app 即清洗
    assert store.get_job(job_id)["env_overlay"] == {"KEV_GEN_MODEL": "m"}


def test_a_credential_in_the_env_channel_is_a_400_not_a_500(client, monkeypatch):
    """凭据写错通道必须在**落库之前**拒掉。

    _spawn 里 create_job 先于 executor.spawn：等到 build_env 才抛 ValueError 就是一个 500
    加一条带着明文 key、永不运行的僵尸作业行（真实事故，spec §12）。
    """
    from kev.console.stages import REGISTRY
    from kev.console.stages.base import BuiltCommand, StageSpec

    bad = StageSpec("plan_size", "plan", "坏通道", lambda request: BuiltCommand(
        argv=["x"], env={"KEV_GEN_API_KEYS": "sk-misplaced"}))
    monkeypatch.setitem(REGISTRY, bad.kind, bad)
    response = client.post("/console/api/jobs/preview", json={
        "kind": "plan_size", "scenario": "triage", "run_name": "r1", "params": {}})
    assert response.status_code == 400
    assert "sk-misplaced" not in response.text
    assert "KEV_GEN_API_KEYS" in response.text   # 拒绝理由要点名是哪个键
    assert client.app.state.store.list_jobs() == []


def test_the_secrets_channel_only_accepts_declared_credentials(client, monkeypatch):
    """secrets 只收 SECRET_ENV 里声明过的名字 —— 否则「放进 secrets」就成了绕过白名单
    的后门，什么键都能借着「凭据」名义落进子进程环境。"""
    from kev.console.stages import REGISTRY
    from kev.console.stages.base import BuiltCommand, StageSpec

    bad = StageSpec("plan_size", "plan", "坏通道", lambda request: BuiltCommand(
        argv=["x"], secrets={"KEV_SOMETHING_ELSE": "v"}))
    monkeypatch.setitem(REGISTRY, bad.kind, bad)
    response = client.post("/console/api/jobs/preview", json={
        "kind": "plan_size", "scenario": "triage", "run_name": "r1", "params": {}})
    assert response.status_code == 400
    assert "KEV_SOMETHING_ELSE" in response.text


def test_retry_increments_attempt_and_renames(client):
    """attempt 递增、parent_id 指向原作业、运行名换新（目录不可复用）。"""
    first_id = make_job(client.app.state.store, kind="plan_size", status="failed")
    second = body(client.post(f"/console/api/jobs/{first_id}/retry"))
    assert second["attempt"] == 2
    assert second["parent_id"] == first_id
    assert second["title"] != "t"
    # 未结束的作业不能重试
    assert client.post(f"/console/api/jobs/{second['id']}/retry").status_code == 409


def test_a_broken_register_is_reported_not_swallowed(client, monkeypatch):
    """产物注册失败必须留下痕迹：executor 的 on_finished 是 except: pass，
    app 侧也不记的话，产物缺失就完全静默。"""
    job_id = make_job(client.app.state.store, kind="plan_size", status="succeeded")
    monkeypatch.setattr("kev.console.app.artifacts.register", _boom)
    with pytest.raises(RuntimeError, match="register failed"):
        client.app.state.executor.on_finished(job_id, 0)
    # 重抛之前先记了一条 system 事件，所以排错时看得见
    assert any("产物注册失败" in row["line"]
               for row in client.app.state.store.read_events(job_id, limit=50))


def _boom(store, job):
    raise RuntimeError("register failed")


# ---- 闸门 / 产物 / 端点 --------------------------------------------------

def test_gates_endpoint_lists_each_gate_with_a_readable_reason(client):
    rows = body(client.get("/console/api/gates/train"))
    assert [row["id"] for row in rows] == ["G1", "G2", "G3"]
    assert all(row["ok"] is False and row["detail"] for row in rows)


def test_gates_can_address_a_dataset_that_is_not_named_after_the_scenario(client, tmp_path, monkeypatch):
    """闸门必须能查到**非默认目录**下的产物。

    阶段表单里有 `data` 字段，用户一旦填了 data/cv 之类，闸门若仍按
    data/<scenario> 推导就永远查不到，而症状是「缺少 precheck 报告」——
    看不出是 id 对不上。仓库里现成的 data/cv 正是这种情况。

    把 ROOT 挪到 tmp_path 并自己写产物文件：不依赖仓库里是否存在真实数据。
    """
    from kev.console import paths

    monkeypatch.setattr(paths, "ROOT", tmp_path)
    target = tmp_path / "data/console/precheck-cv-train.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text('{"records": 551, "over_limit": 0}', encoding="utf-8")

    store = client.app.state.store
    store.put_artifact(kind="precheck", name="cv/train", path="data/console/precheck-cv-train.json",
                       meta={"records": 551, "over_limit": 0})
    # 不传 data：按 data/<scenario> 推导，找不到 data/cv 下的产物
    assert body(client.get("/console/api/gates/train"))[0]["ok"] is False
    # 传了 data：应当找到，并且判为通过
    rows = body(client.get("/console/api/gates/train?data=data/cv"))
    assert rows[0]["id"] == "G1" and rows[0]["ok"] is True
    assert "551" in rows[0]["detail"]


def test_deploy_is_blocked_by_the_model_quality_gates(client):
    """deploy 阶段要过 G4-G7（模型质量闸），产物还没生成时必须阻断。"""
    response = submit(client, "deploy", temperature="2.35")
    assert response.status_code == 422
    assert body(response)["error"]["kind"] == "gate"


def test_deploy_registers_its_artifact_at_start_not_at_finish(client, monkeypatch):
    """kev.serve 是长驻进程、永不「完成」，按 SUCCESS 注册的话端点列表永远是空的。"""
    monkeypatch.setattr("kev.console.app.evaluate", lambda stage, **p: [])
    assert submit(client, "deploy", temperature="2.35").status_code == 201
    assert client.app.state.store.get_artifact("endpoint:8008") is not None
    rows = body(client.get("/console/api/endpoints"))["endpoints"]
    assert rows[0]["path"] == "http://127.0.0.1:8008"


def test_dataset_detail_carries_lineage_and_404s_when_unknown(client):
    store = client.app.state.store
    store.put_artifact(kind="dataset", name="cv", path="data/cv", meta={})
    store.put_artifact(kind="dataset", name="cv/train", path="data/cv/train.jsonl", meta={})
    store.add_lineage("dataset:cv", "dataset:cv/train", "split_into")
    detail = body(client.get("/console/api/datasets/dataset:cv"))
    assert detail["lineage"][0]["child"] == "dataset:cv/train"
    assert client.get("/console/api/datasets/dataset:没有").status_code == 404