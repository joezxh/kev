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


def _mk_bundle(client, project_id, name="snap"):
    """经 Store 建一个 draft bundle（归属它的项目），返回其 id。"""
    return client.app.state.store.create_bundle(
        project_id=project_id, name=name, artifact_id=f"bundle:cv/{name}")["id"]


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


# ---- bundle 归属（D3 / D4，schema v11）-----------------------------------

def test_submit_declares_bundle_and_reads_back_its_name(client):
    pid = _mk_project(client)
    bundle_id = _mk_bundle(client, pid)
    r = client.post("/console/api/jobs", json={"kind": "plan_size", "scenario": "triage",
        "run_name": "cv-1", "params": {}, "project_id": pid, "bundle_id": bundle_id})
    assert r.status_code == 201, r.text
    created = r.json()
    assert created["bundle_id"] == bundle_id
    assert created["bundle_name"] == "snap"          # 读侧直接带名字（§4.3），前端不必再查
    single = body(client.get(f"/console/api/jobs/{created['id']}"))
    assert single["bundle_id"] == bundle_id and single["bundle_name"] == "snap"


def test_submit_without_bundle_stays_unassigned(client):
    """不带 bundle_id 的提交与今天一致：'' 是未归属，不是某个 bundle。"""
    r = submit(client, "plan_size")
    assert r.status_code == 201, r.text
    assert r.json()["bundle_id"] == ""
    assert r.json()["bundle_name"] is None


def test_submit_rejects_unknown_bundle(client):
    r = client.post("/console/api/jobs", json={"kind": "plan_size", "scenario": "triage",
        "run_name": "cv-1", "params": {}, "project_id": _mk_project(client),
        "bundle_id": "nope"})
    assert r.status_code == 404


def test_submit_rejects_bundle_of_another_project(client):
    other = _mk_project(client, slug="other")
    bundle_id = _mk_bundle(client, other)
    r = client.post("/console/api/jobs", json={"kind": "plan_size", "scenario": "triage",
        "run_name": "cv-1", "params": {}, "project_id": _mk_project(client, slug="mine"),
        "bundle_id": bundle_id})
    assert r.status_code == 400 and r.json()["error"]["field"] == "bundle_id"


def test_jobs_can_be_filtered_by_bundle(client):
    """一个 bundle 多个作业（含同一阶段的多个）都能反查回来（D3 多对一 / D4 快查）。"""
    pid = _mk_project(client)
    bundle_id = _mk_bundle(client, pid)

    def post(name):
        r = client.post("/console/api/jobs", json={"kind": "plan_size", "scenario": "triage",
            "run_name": name, "params": {}, "project_id": pid, "bundle_id": bundle_id})
        assert r.status_code == 201, r.text
        return r.json()["id"]

    mine = {post("cv-1"), post("cv-2")}          # 同一阶段（plan_size）的两个作业
    unassigned = submit(client, "plan_size", project_id=pid).json()["id"]

    rows = body(client.get(f"/console/api/jobs?bundle={bundle_id}"))
    assert {row["id"] for row in rows} == mine
    assert all(row["bundle_name"] == "snap" for row in rows)
    # 不归属任何 bundle 的作业不会出现在任何一个 bundle 的反查里
    assert unassigned not in {row["id"] for row in rows}


def test_retry_carries_the_bundle_over(client):
    """重试是同一件事的第二次尝试（与 template_id 同理），归属跟着走。"""
    store = client.app.state.store
    pid = store.create_project("retry-b", "Retry B", scenario="triage")
    bundle_id = _mk_bundle(client, pid, name="round1")
    first_id = store.create_job(project_id=pid, kind="plan_size", stage="plan",
        scenario="triage", title="t", request={}, argv=["x"], env_overlay={}, cwd=".",
        log_path="l.log", artifacts_in=[], artifacts_out=[], bundle_id=bundle_id)
    store.transition(first_id, "failed", exit_code=1)
    second = body(client.post(f"/console/api/jobs/{first_id}/retry"))
    assert second["attempt"] == 2
    assert second["bundle_id"] == bundle_id and second["bundle_name"] == "round1"


def test_delete_job_cascades_its_data(client, tmp_path, monkeypatch):
    """删作业 = 连同它的日志事件、产物版本与登记行、白名单内的磁盘文件一起删。"""
    from kev.console import paths

    monkeypatch.setattr(paths, "ROOT", tmp_path)
    store = client.app.state.store
    job_id = make_job(store, kind="split", status="succeeded")
    store.append_events(job_id, [("stdout", "line one")])
    target = tmp_path / "data" / "fx-out.jsonl"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text('{"id": 1}\n', encoding="utf-8")
    with store.tx():
        store.put_artifact(kind="dataset", name="fx/out", path="data/fx-out.jsonl",
                           meta={}, bytes_=9, commit=False)
        store.record_artifact_version(artifact_id="dataset:fx/out", job_id=job_id,
                                      path="data/fx-out.jsonl", sha256="x", records=1, bytes=9)

    r = client.delete(f"/console/api/jobs/{job_id}")
    assert r.status_code == 200, r.text
    summary = r.json()
    assert (summary["events"], summary["versions"], summary["artifacts"]) == (1, 1, 1)
    assert (summary["files"], summary["bytes"]) == (1, 9)
    assert store.get_job(job_id) is None
    assert store.read_events(job_id) == []
    assert store.get_artifact("dataset:fx/out") is None
    assert store.list_artifact_versions("dataset:fx/out") == []
    assert not target.exists()
    assert client.delete("/console/api/jobs/nope").status_code == 404


def test_delete_refuses_a_live_job(client):
    """进行中的作业不许删：先取消、等进终态，否则子进程还在往已被级联的行里写。"""
    job_id = make_job(client.app.state.store, status="running")
    r = client.delete(f"/console/api/jobs/{job_id}")
    assert r.status_code == 409 and body(r)["error"]["kind"] == "conflict"
    assert client.app.state.store.get_job(job_id) is not None


def test_delete_refuses_when_versions_are_bundle_members(client):
    """bundle 是冻结证据链：成员版本被引用时删作业必须硬拒，不许悄悄拆散它。"""
    store = client.app.state.store
    pid = store.create_project("bnd", "Bnd", scenario="triage")
    job_id = make_job(store, status="succeeded")
    with store.tx():
        vid = store.record_artifact_version(artifact_id="dataset:fx/out", job_id=job_id,
                                            path="data/fx-out.jsonl", sha256="x", records=1, bytes=1)
    store.replace_bundle_members(_mk_bundle(client, pid), [{"version_id": vid, "op": "add", "ord": 0}])
    r = client.delete(f"/console/api/jobs/{job_id}")
    assert r.status_code == 409 and "bundle" in body(r)["error"]["message"]
    assert store.get_job(job_id) is not None


def test_delete_keeps_data_still_referenced_by_other_jobs(client, tmp_path, monkeypatch):
    """另一作业仍引用同一产物时，登记行与文件原地保留（只会误留，不会误删）。"""
    from kev.console import paths

    monkeypatch.setattr(paths, "ROOT", tmp_path)
    store = client.app.state.store
    pid = store.create_project("shr", "Shr", scenario="triage")

    def mk() -> str:
        jid = store.create_job(project_id=pid, kind="split", stage="data", scenario="triage",
            title="t", request={}, argv=["x"], env_overlay={}, cwd=".", log_path="l.log",
            artifacts_in=[], artifacts_out=["dataset:fx/out"])
        store.transition(jid, "queued")
        store.transition(jid, "running")
        store.transition(jid, "succeeded", exit_code=0)
        return jid

    first, second = mk(), mk()
    target = tmp_path / "data" / "fx-out.jsonl"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text('{"id": 1}\n', encoding="utf-8")
    with store.tx():
        store.put_artifact(kind="dataset", name="fx/out", path="data/fx-out.jsonl",
                           meta={}, bytes_=9, commit=False)
        store.record_artifact_version(artifact_id="dataset:fx/out", job_id=first,
                                      path="data/fx-out.jsonl", sha256="x", records=1, bytes=9)

    r = client.delete(f"/console/api/jobs/{first}")
    assert r.status_code == 200, r.text
    summary = r.json()
    assert summary["versions"] == 1 and summary["artifacts"] == 0 and summary["files"] == 0
    assert store.get_job(second) is not None
    assert store.get_artifact("dataset:fx/out") is not None
    assert target.exists()


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


# ---- PR B: artifact versions 端点 -----------------------------------------

def _seed_version(client, tmp_path, monkeypatch, *, artifact="dataset:cv/train", lines=(
        '{"state": "s", "questions": {"q": {"type": "noul", "instructions": "i", "label": true}}}',)):
    """经 register 落一条真实版本（写文件 + 建项目/作业），返回 (version_id, artifact_id)。"""
    from kev.console import artifacts
    monkeypatch.setattr(artifacts.paths, "ROOT", tmp_path)
    store = client.app.state.store
    rel = artifacts.resolve(artifact)
    target = tmp_path / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("".join(line + "\n" for line in lines), encoding="utf-8")
    project_id = store.create_project("vproj", "V", scenario="triage")
    job_id = store.create_job(
        project_id=project_id, kind="split", stage="data", scenario="triage", title="v",
        request={}, argv=["x"], env_overlay={}, cwd=".", log_path="l.log",
        artifacts_in=[], artifacts_out=[artifact])
    artifacts.register(store, store.get_job(job_id))
    version = store.list_artifact_versions(artifact)[0]
    return version["id"], artifact


def test_versions_endpoint_ok_drift_and_unknown(client, tmp_path, monkeypatch):
    vid, artifact = _seed_version(client, tmp_path, monkeypatch)
    rows = body(client.get(f"/console/api/artifacts/{artifact}/versions"))
    assert len(rows) == 1 and rows[0]["id"] == vid and rows[0]["integrity"] == "ok"
    # 手改快照指向的文件 → 读时复核判为 drift
    (tmp_path / "data" / "cv" / "train.jsonl").write_text('{"changed": true}\n', encoding="utf-8")
    assert body(client.get(f"/console/api/artifacts/{artifact}/versions"))[0]["integrity"] == "drift"
    assert client.get("/console/api/artifacts/dataset:没有/versions").status_code == 404


def test_versions_history_without_versions_returns_empty_not_500(client):
    store = client.app.state.store
    store.put_artifact(kind="dataset", name="cv/legacy", path="data/cv/legacy.jsonl", meta={})
    rows = body(client.get("/console/api/artifacts/dataset:cv/legacy/versions"))
    assert rows == []


def test_version_records_and_export_endpoints(client, tmp_path, monkeypatch):
    vid, _ = _seed_version(client, tmp_path, monkeypatch)
    page = body(client.get(f"/console/api/artifact-versions/{vid}/records?limit=1"))
    assert page["total"] == 1 and len(page["records"]) == 1
    assert len(page["records"][0]["fingerprint"]) == 64
    assert client.get(f"/console/api/artifact-versions/nope/records").status_code == 404
    exported = client.get(f"/console/api/artifact-versions/{vid}/export")
    assert exported.status_code == 200 and exported.text.strip().count("\n") + 1 == 1
    assert client.get(f"/console/api/artifact-versions/nope/export").status_code == 404