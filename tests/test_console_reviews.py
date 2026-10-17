"""record_reviews 场景作用域 + history + review-queue + import（PR D，后端面）。

覆盖 plan §PR D 检查点的六条失败测试（先 RED）：
- test_source_sha_unchanged_after_relabel —— 标注只落覆盖层，源 JSONL 的 sha256 不变（P7/D6）。
- test_scenario_scope_inherits_next_round —— 同场景第二轮命中上轮决定，无需重标（D13）。
- test_empty_scenario_409 —— 项目 scenario=='' 时写决定 → 409（先补场景才能标）。
- test_history_archived_before_overwrite —— 覆盖前归档一条 history，超过 REVIEW_HISTORY_LIMIT 裁剪。
- test_import_unmatched_reported —— reviews.jsonl 逐行落库，按 fingerprint（无则 record_id 反查），回报 unmatched。
- test_queue_skips_decided_including_inherited —— review-queue 默认跳过已决定指纹（含继承）。

Run: uv run python -m pytest tests/test_console_reviews.py -q
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


# ---- P7：标注不改源文件 ------------------------------------------------

def test_source_sha_unchanged_after_relabel(client):
    store = _store(client)
    rec = _record("keepme", "q", True)
    pid = _mk_project(client, "srcp")
    v = _seed_version(client, "src-keep", [rec], pid)
    version = store.get_artifact_version(v)
    target = client.root / version["path"]
    before = hashlib.sha256(target.read_bytes()).hexdigest()
    assert before == version["sha256"]
    store.upsert_record_review(scenario="triage", origin_project_id=pid,
                               fingerprint=_fp(rec), verdict="relabel",
                               patch={"questions": {"q": {"label": False}}})
    after = hashlib.sha256(target.read_bytes()).hexdigest()
    assert after == before  # 源文件逐字节不变
    assert artifacts.integrity(store.get_artifact_version(v)) == "ok"


# ---- D13：场景作用域跨轮继承 ------------------------------------------

def test_scenario_scope_inherits_next_round(client):
    store = _store(client)
    rec = _record("shared", "q", True)
    fp = _fp(rec)
    # 第一轮：项目 A 标 accept。
    pid_a = _mk_project(client, "inh-a")
    store.upsert_record_review(scenario="triage", origin_project_id=pid_a,
                               fingerprint=fp, verdict="accept")
    # 第二轮：另一项目 B（同场景）有同样记录，物化后自动命中上轮决定，计为 inherited。
    pid_b, bundle = _make_bundle(client, "inh-b", "inherit", [rec])
    after = store.get_bundle(bundle["id"])
    assert after["reviewed_records"] == 1
    assert after["reviewed_native"] == 0
    assert after["reviewed_inherited"] == 1
    assert after["review_ratio"] == pytest.approx(1.0)


# ---- 空场景 409 -------------------------------------------------------

def test_empty_scenario_409(client):
    store = _store(client)
    pid = _mk_project(client, "empty-sc")
    store.update_project(pid, scenario="")       # 造一个未绑场景的遗留项目
    r = client.put(f"/console/api/projects/{pid}/reviews/{_fp(_record('s', 'q', True))}",
                   json={"verdict": "accept"})
    assert r.status_code == 409, r.text


# ---- history 覆盖前归档 + 裁剪 ----------------------------------------

def test_history_archived_before_overwrite(client):
    store = _store(client)
    fp = _fp(_record("hist", "q", True))
    rid = store.upsert_record_review(scenario="triage", origin_project_id="p1",
                                     fingerprint=fp, verdict="accept")
    assert store.list_record_review_history(rid) == []        # 首次无历史
    store.upsert_record_review(scenario="triage", origin_project_id="p1",
                               fingerprint=fp, verdict="drop")
    hist = store.list_record_review_history(rid)
    assert len(hist) == 1 and hist[0]["verdict"] == "accept"  # 覆盖前的旧决定归档
    # 连续覆盖到超过 REVIEW_HISTORY_LIMIT → 裁剪到最近 20 条。
    for i in range(store.REVIEW_HISTORY_LIMIT + 5):
        store.upsert_record_review(scenario="triage", origin_project_id="p1",
                                   fingerprint=fp, verdict="accept", note=f"n{i}")
    assert len(store.list_record_review_history(rid)) == store.REVIEW_HISTORY_LIMIT


# ---- import：unmatched 回报 -------------------------------------------

def test_import_unmatched_reported(client):
    rec = _record("imp", "q", True, rid="rec-1")
    pid = _mk_project(client, "impp")
    _seed_version(client, "imp-src", [rec], pid)
    rows = [
        {"fingerprint": _fp(rec), "verdict": "accept"},      # 直接按指纹命中
        {"record_id": "nope", "verdict": "drop"},            # 无指纹、反查不到 → unmatched
    ]
    r = client.post(f"/console/api/projects/{pid}/reviews/import", json={"rows": rows})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["imported"] == 1
    assert len(body["unmatched"]) == 1
    assert body["unmatched"][0]["reason"]


# ---- review-queue：默认跳过已决定（含继承） ---------------------------

def test_queue_skips_decided_including_inherited(client):
    store = _store(client)
    rec_a, rec_b = _record("qa", "q", True), _record("qb", "q", False)
    fp_a, fp_b = _fp(rec_a), _fp(rec_b)
    # 项目 P 物化两条记录的 bundle。
    pid, bundle = _make_bundle(client, "qp", "qn", [rec_a, rec_b])
    # 另一项目（同场景）决定 rec_a → 对 P 是「继承来的已决定」。
    other = _mk_project(client, "qother")
    store.upsert_record_review(scenario="triage", origin_project_id=other,
                               fingerprint=fp_a, verdict="accept")
    q = client.get(f"/console/api/projects/{pid}/review-queue?seed=42")
    assert q.status_code == 200, q.text
    items = q.json()["items"]
    fps = {it["fingerprint"] for it in items}
    assert fp_b in fps and fp_a not in fps                    # 默认跳过已决定（含继承）
    # seed 固定 → 换机器同批：两次同 seed 返回同序。
    q2 = client.get(f"/console/api/projects/{pid}/review-queue?seed=42").json()
    assert [it["fingerprint"] for it in q2["items"]] == [it["fingerprint"] for it in items]
    # include_decided=1 → 已决定的带 existing_verdict 出现。
    qi = client.get(f"/console/api/projects/{pid}/review-queue?seed=42&include_decided=1").json()
    decided = {it["fingerprint"]: it for it in qi["items"]}
    assert fp_a in decided and decided[fp_a]["existing_verdict"] == "accept"
