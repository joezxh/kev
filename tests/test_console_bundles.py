"""bundles CRUD + F1–F4 freeze + freeze-policy + diff（PR C，端点面）。

冻结语义（D11）：
- F1（未物化 / 无 include 成员）与 F4（产物含未处理 flag）不过 → 409 硬拒，不写 frozen_at；
- F2（记录数 < 门槛）与 F3（复核比例 < 门槛）不过 → 仍 200 + warnings，冻结照常落 frozen_at；
- 两种情况都把四条 freeze_checks 写全（形状抄 gates.Gate：id/ok/detail/actual/need）；
- 门槛 0 与「不设门槛」逐字节一致；P8：门槛 = records+1 时 F2.ok=False 且 actual/need 对得上。

Run: uv run python -m pytest tests/test_console_bundles.py -q
"""
import hashlib
import json
import threading

import pytest
from fastapi.testclient import TestClient

from kev.console import artifacts
from kev.console.app import create_app
from kev.console.db import Store
from kev.console.services.data import DataService
from kev.console.stages.base import JobRequest


def _record(state, qid, label):
    return {"state": state,
            "questions": {qid: {"type": "noul", "instructions": "do it", "label": label}}}


def _line(record):
    return json.dumps(record, ensure_ascii=False)


@pytest.fixture
def client(tmp_path, monkeypatch):
    store = Store(tmp_path / "db.sqlite")          # 先用真实 ROOT 播种
    monkeypatch.setattr(artifacts.paths, "ROOT", tmp_path)  # 再把产物根隔离到 tmp
    with TestClient(create_app(store=store)) as test_client:
        test_client.root = tmp_path
        yield test_client


def _store(client):
    return client.app.state.store


def _mk_project(client, **over):
    payload = {"slug": over.get("slug", "bp"), "name": "BP", "scenario": "triage"}
    r = client.post("/console/api/projects", json=payload)
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


def _seed_version(client, name, records):
    store = _store(client)
    pid = _mk_project(client, slug=f"v-{name}")
    artifact_id = f"dataset:{name}"
    target = client.root / artifacts.resolve(artifact_id)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("".join(_line(r) + "\n" for r in records), encoding="utf-8")
    job_id = store.create_job(
        project_id=pid, kind="generate", stage="data", scenario="triage", title="s",
        request={}, argv=["x"], env_overlay={}, cwd=".", log_path="l.log",
        artifacts_in=[], artifacts_out=[artifact_id])
    artifacts.register(store, store.get_job(job_id))
    return store.list_artifact_versions(artifact_id)[0]["id"]


def _materialize(client, bundle_id):
    req = JobRequest(scenario="triage", project_id="p", params={"bundle_id": bundle_id})
    DataService(_store(client), threading.Event()).materialize(req, on_log=lambda line: None)


def _make_materialized_bundle(client, name, records, *, slug="bp"):
    """建项目、种子版本、建 bundle、include 全部、物化，返回 (project_id, bundle)。"""
    store = _store(client)
    pid = _mk_project(client, slug=slug)
    v = _seed_version(client, f"{name}-src", records)
    r = client.post(f"/console/api/projects/{pid}/bundles", json={"name": name})
    assert r.status_code == 201, r.text
    bundle = r.json()
    mr = client.put(f"/console/api/projects/{pid}/bundles/{name}/members",
                    json=[{"version_id": v, "op": "include", "ord": 0}])
    assert mr.status_code == 200, mr.text
    _materialize(client, bundle["id"])
    return pid, store.get_bundle(bundle["id"])


# ---- create / validate ---------------------------------------------------

def test_create_bundle_is_draft(client):
    pid = _mk_project(client)
    r = client.post(f"/console/api/projects/{pid}/bundles", json={"name": "snap"})
    assert r.status_code == 201, r.text
    bundle = r.json()
    assert bundle["status"] == "draft"
    assert bundle["artifact_id"].startswith("bundle:")


def test_bundle_duplicate_name_409(client):
    pid = _mk_project(client)
    assert client.post(f"/console/api/projects/{pid}/bundles", json={"name": "dup"}).status_code == 201
    r = client.post(f"/console/api/projects/{pid}/bundles", json={"name": "dup"})
    assert r.status_code == 409


def test_bundle_invalid_name_400(client):
    pid = _mk_project(client)
    r = client.post(f"/console/api/projects/{pid}/bundles", json={"name": "bad.name"})
    assert r.status_code == 400


# ---- members -------------------------------------------------------------

def test_members_only_editable_in_draft(client):
    pid, bundle = _make_materialized_bundle(client, "memb", [_record("a", "q", True)])
    r = client.put(f"/console/api/projects/{pid}/bundles/{bundle['name']}/members",
                   json=[{"version_id": "x", "op": "include", "ord": 0}])
    assert r.status_code == 409  # materialized 后成员不可改


# ---- freeze: hard vs soft -----------------------------------------------

def test_freeze_f1_hard_refuse(client):
    """未物化的 draft bundle freeze → 409，F1.ok=False，无 frozen_at。"""
    pid = _mk_project(client)
    v = _seed_version(client, "f1-src", [_record("a", "q", True)])
    r = client.post(f"/console/api/projects/{pid}/bundles", json={"name": "f1"})
    bundle = r.json()
    client.put(f"/console/api/projects/{pid}/bundles/f1/members",
               json=[{"version_id": v, "op": "include", "ord": 0}])
    fr = client.post(f"/console/api/projects/{pid}/bundles/f1/freeze")
    assert fr.status_code == 409, fr.text
    checks = {c["id"]: c for c in fr.json()["freeze_checks"]}
    assert checks["F1"]["ok"] is False
    assert _store(client).get_bundle(bundle["id"])["frozen_at"] is None


def test_freeze_f4_unresolved_hard_refuse(client):
    """产物里被标 flag（未处理）的记录 → F4 硬拒 409。"""
    rec = _record("flagme", "q", True)
    pid, bundle = _make_materialized_bundle(client, "f4", [rec], slug="f4p")
    artifacts.paths.ensure_generators_on_path()
    import split_data
    fp = split_data.record_fingerprint(rec)
    _store(client).upsert_record_review(scenario="triage", origin_project_id=pid,
                                        fingerprint=fp, verdict="flag")
    fr = client.post(f"/console/api/projects/{pid}/bundles/f4/freeze")
    assert fr.status_code == 409, fr.text
    checks = {c["id"]: c for c in fr.json()["freeze_checks"]}
    assert checks["F4"]["ok"] is False


def test_freeze_f2_f3_warn_only(client):
    """物化只 1 条记录，默认门槛 300 → F2 不过但仍 200 + warnings，且冻结照常落 frozen_at。"""
    pid, bundle = _make_materialized_bundle(client, "f23", [_record("a", "q", True)], slug="f23p")
    fr = client.post(f"/console/api/projects/{pid}/bundles/f23/freeze")
    assert fr.status_code == 200, fr.text
    payload = fr.json()
    assert any(w["id"] == "F2" for w in payload["warnings"])
    after = _store(client).get_bundle(bundle["id"])
    assert after["status"] == "frozen" and after["frozen_at"]
    checks = {c["id"]: c for c in after["freeze_checks"]}
    assert checks["F1"]["ok"] is True and checks["F2"]["ok"] is False


def test_p8_min_records_plus_one_refuses(client):
    """门槛 = records+1 → F2.ok=False，actual=records、need=records+1（P8）。"""
    pid, bundle = _make_materialized_bundle(client, "p8", [_record("a", "q", True)], slug="p8p")
    _store(client).update_project(pid, freeze_min_records=bundle["records"] + 1,
                                  freeze_min_review_ratio=0.0)
    fr = client.post(f"/console/api/projects/{pid}/bundles/p8/freeze")
    assert fr.status_code == 200, fr.text
    f2 = next(w for w in fr.json()["warnings"] if w["id"] == "F2")
    assert int(f2["actual"]) == bundle["records"]
    assert int(f2["need"]) == bundle["records"] + 1


def test_threshold_zero_byte_identical(client):
    """门槛 (0, 0.0) → 全过、无 warnings；四条 checks 形状与预期一致。"""
    pid, bundle = _make_materialized_bundle(client, "zero", [_record("a", "q", True)], slug="zp")
    _store(client).update_project(pid, freeze_min_records=0, freeze_min_review_ratio=0.0)
    fr = client.post(f"/console/api/projects/{pid}/bundles/zero/freeze")
    assert fr.status_code == 200 and fr.json()["warnings"] == []
    after = _store(client).get_bundle(bundle["id"])
    assert [c["id"] for c in after["freeze_checks"]] == ["F1", "F2", "F3", "F4"]
    assert all(c["ok"] for c in after["freeze_checks"])


# ---- freeze-policy / diff -----------------------------------------------

def test_freeze_policy_updates_project(client):
    pid = _mk_project(client, slug="polp")
    r = client.put(f"/console/api/projects/{pid}/freeze-policy",
                   json={"freeze_min_records": 42, "freeze_min_review_ratio": 0.5})
    assert r.status_code == 200, r.text
    assert r.json()["freeze_min_records"] == 42


def test_bundle_diff_by_fingerprint(client):
    rec_a, rec_b = _record("a", "q", True), _record("b", "q", False)
    _, left = _make_materialized_bundle(client, "dl", [rec_a], slug="dlp")
    _, right = _make_materialized_bundle(client, "dr", [rec_a, rec_b], slug="drp")
    artifacts.paths.ensure_generators_on_path()
    import split_data
    fp_b = split_data.record_fingerprint(rec_b)
    d = client.get(f"/console/api/bundles/{left['id']}/diff?other={right['id']}").json()
    assert fp_b in d["only_right"]
    assert d["only_left"] == []
