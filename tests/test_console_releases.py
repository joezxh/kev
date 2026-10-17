"""project_releases + gates_snapshot 落库 + lineage API（PR E，后端面）。

覆盖 plan §PR E 检查点的失败测试（先 RED）：
- test_release_snapshot_survives_eval_removal —— gates_snapshot/metrics 服务端现算落库；
  客户端提交的数字被忽略；删掉 eval 产物目录后 release 仍读得出当时判定（P5）。
- test_release_duplicate_name_409 —— 同项目重名 → 409。
- test_release_backchain_to_fingerprint —— release → bundle → members → versions → jobs →
  reviews 一路反查可达（P5）。
- test_lineage_nodes_edges_shape —— GET /projects/{id}/lineage 的 {nodes,edges} 形状 +
  bundle_members 的 composed_of 边（D10）。

Run: uv run python -m pytest tests/test_console_releases.py -q
"""
import json
import shutil
import threading

import pytest
from fastapi.testclient import TestClient

from kev.console import artifacts
from kev.console.app import create_app
from kev.console.db import Store
from kev.console.services.data import DataService
from kev.console.stages.base import JobRequest


def _record(state, qid, label, rid=None):
    rec = {"state": state,
           "questions": {qid: {"type": "noul", "instructions": "do it", "label": label}}}
    if rid is not None:
        rec["id"] = rid
    return rec


def _line(record):
    return json.dumps(record, ensure_ascii=False)


def _fp(record):
    artifacts.paths.ensure_generators_on_path()
    import split_data
    return split_data.record_fingerprint(record)


def _report():
    return {"clean": {"acc": 0.91, "ece": 0.05, "brier": 0.08, "aurc": 0.04,
                      "coverage_at_5pct_error": 0.7, "confident_error_rate": 0.09},
            "calibrated_clean": {"ece": 0.03}}


def _comparison():
    return {"paired": {"acc": {"ci95": [0.05, 0.2], "macro_acc_delta": 0.1}},
            "clean": {"candidate": {"confident_error_rate": 0.03},
                      "reference": {"confident_error_rate": 0.05}}}


def _regression():
    return {"paired": {"acc": {"ci95": [-0.01, 0.1]}}}


def _calibration():
    return {"arms": {"workload_oof": {"ece": 0.02}, "shipped": {"ece": 0.05}}}


@pytest.fixture
def client(tmp_path, monkeypatch):
    store = Store(tmp_path / "db.sqlite")
    monkeypatch.setattr(artifacts.paths, "ROOT", tmp_path)
    with TestClient(create_app(store=store)) as test_client:
        test_client.root = tmp_path
        yield test_client


def _store(client):
    return client.app.state.store


def _mk_project(client, slug, scenario="triage"):
    r = client.post("/console/api/projects",
                    json={"slug": slug, "name": slug.upper(), "scenario": scenario})
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


def _register(client, kind, name, text_body=None, directory=False, payload=None):
    """把一份产物文件写到 artifacts.resolve(kind:name) 处并登记（不经 job，供 release 读数字）。"""
    store = _store(client)
    aid = f"{kind}:{name}"
    rel = artifacts.resolve(aid)
    target = client.root / rel
    if directory:
        target.mkdir(parents=True, exist_ok=True)
        (target / "report.json").write_text(json.dumps(payload), encoding="utf-8")
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        if text_body is not None:
            target.write_text(text_body, encoding="utf-8")
        else:
            target.write_text(json.dumps(payload), encoding="utf-8")
    store.put_artifact(kind=kind, name=name, path=rel,
                       meta=artifacts.summarize(aid, rel))
    return aid


def _seed_eval(client, name):
    return _register(client, "eval", name, directory=True, payload=_report())


def _seed_version(client, name, records, project_id):
    store = _store(client)
    artifact_id = f"dataset:{name}"
    target = client.root / artifacts.resolve(artifact_id)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("".join(_line(r) + "\n" for r in records), encoding="utf-8")
    job_id = store.create_job(
        project_id=project_id, kind="generate", stage="data", scenario="triage", title="s",
        request={}, argv=["x"], env_overlay={}, cwd=".", log_path="l.log",
        artifacts_in=[], artifacts_out=[artifact_id])
    artifacts.register(store, store.get_job(job_id))
    return store.list_artifact_versions(artifact_id)[0]["id"]


def _materialize(client, bundle_id, project_id):
    req = JobRequest(scenario="triage", project_id=project_id, params={"bundle_id": bundle_id})
    DataService(_store(client), threading.Event()).materialize(req, on_log=lambda line: None)


def _make_bundle(client, slug, name, records):
    """建项目 + 种子版本 + bundle + include + 物化，返回 (project_id, bundle)。"""
    store = _store(client)
    pid = _mk_project(client, slug)
    v = _seed_version(client, f"{name}-src", records, pid)
    r = client.post(f"/console/api/projects/{pid}/bundles", json={"name": name})
    assert r.status_code == 201, r.text
    bundle = r.json()
    mr = client.put(f"/console/api/projects/{pid}/bundles/{name}/members",
                    json=[{"version_id": v, "op": "include", "ord": 0}])
    assert mr.status_code == 200, mr.text
    _materialize(client, bundle["id"], pid)
    return pid, store.get_bundle(bundle["id"])


# ---- snapshot 服务端现算 + 落库后独立于产物文件 ---------------------------

def test_release_snapshot_survives_eval_removal(client):
    store = _store(client)
    pid = _mk_project(client, "rel1")
    ev = _seed_eval(client, "r1")
    cmp_ = _register(client, "comparison", "r1", payload=_comparison())
    reg = _register(client, "regression", "r1", payload=_regression())
    cal = _register(client, "calibration", "r1", payload=_calibration())
    r = client.post(f"/console/api/projects/{pid}/releases", json={
        "name": "v1", "eval_artifact": ev, "comparison_artifact": cmp_,
        "regression_artifact": reg, "calibration_artifact": cal,
        "metrics": {"acc": 999}})          # 客户端提交的数字必须被忽略
    assert r.status_code == 201, r.text
    rel = r.json()
    assert rel["metrics"]["acc"] == pytest.approx(0.91)   # 来自 eval report，不是 999
    snap_ids = {g["id"] for g in rel["gates_snapshot"]}
    assert {"G4", "G5", "G6", "G7"} <= snap_ids
    assert all(set(g) >= {"id", "ok", "detail"} for g in rel["gates_snapshot"])
    # 删掉 eval 产物目录后，release 仍读得出当时落库的判定（P5）
    shutil.rmtree(client.root / artifacts.resolve(ev), ignore_errors=True)
    g = client.get(f"/console/api/projects/{pid}/releases/{rel['id']}")
    assert g.status_code == 200, g.text
    assert {x["id"] for x in g.json()["gates_snapshot"]} == snap_ids
    assert store.get_release(rel["id"])["name"] == "v1"


def test_release_duplicate_name_409(client):
    pid = _mk_project(client, "reldup")
    first = client.post(f"/console/api/projects/{pid}/releases",
                        json={"name": "v1", "eval_artifact": _seed_eval(client, "d1")})
    assert first.status_code == 201, first.text
    dup = client.post(f"/console/api/projects/{pid}/releases",
                      json={"name": "v1", "eval_artifact": _seed_eval(client, "d2")})
    assert dup.status_code == 409, dup.text


# ---- 回溯链：release → bundle → members → versions → jobs → reviews ------

def test_release_backchain_to_fingerprint(client):
    store = _store(client)
    rec = _record("chain", "q", True)
    fp = _fp(rec)
    pid, bundle = _make_bundle(client, "chainp", "chainb", [rec])
    store.upsert_record_review(scenario="triage", origin_project_id=pid, fingerprint=fp,
                               verdict="accept")
    r = client.post(f"/console/api/projects/{pid}/releases",
                    json={"name": "v1", "bundle_id": bundle["id"]})
    assert r.status_code == 201, r.text
    rel = r.json()
    assert rel["bundle_sha256"] == bundle["sha256"]        # 服务端从 bundle 取，非客户端提交
    members = store.get_bundle_members(rel["bundle_id"])
    assert members
    version = store.get_artifact_version(members[0]["version_id"])
    assert version and version["job_id"]
    job = store.get_job(version["job_id"])
    assert job["project_id"] == pid
    overlay = store.record_reviews_by_fingerprint("triage")
    assert fp in overlay and overlay[fp]["verdict"] == "accept"


# ---- lineage 图形状 ------------------------------------------------------

def test_lineage_nodes_edges_shape(client):
    rec = _record("lg", "q", True)
    pid, bundle = _make_bundle(client, "lgp", "lgb", [rec])
    r = client.get(f"/console/api/projects/{pid}/lineage")
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) == {"nodes", "edges"}
    for node in body["nodes"]:
        assert set(node) >= {"id", "kind", "version"}
    for edge in body["edges"]:
        assert set(edge) >= {"parent", "child", "relation"}
    bundle_node = bundle["artifact_id"]
    assert any(e["child"] == bundle_node and e["relation"] == "composed_of"
               for e in body["edges"])
    assert any(n["id"] == bundle_node for n in body["nodes"])
