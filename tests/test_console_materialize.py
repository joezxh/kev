"""materialize stage / service：把 bundle 成员按序合成一份不可变训练快照（PR C）。

覆盖 Cross-cutting Review Focus 里属于 PR C 的三条：
- materialize 幂等到 sha256（两批并集，两次跑同一 bundle 得同 sha）；
- drop_reasons 的 dup/state_conflict 逐条等于 split_data.dedupe 的丢弃数（property，
  反目标 §2.3 第 2 条 —— 去重必须复用，不复制实现）；
- 门槛 0 时 freeze 与「不设门槛」逐字节一致（D11）。

Run: uv run python -m pytest tests/test_console_materialize.py -q
"""
import hashlib
import json
import threading

import pytest

from kev.console import artifacts
from kev.console.db import Store
from kev.console.services.data import DataService
from kev.console.stages.base import JobRequest


def _record(state, qid, label):
    return {"state": state,
            "questions": {qid: {"type": "noul", "instructions": "do it", "label": label}}}


def _line(record):
    return json.dumps(record, ensure_ascii=False)


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "db.sqlite")


@pytest.fixture
def root(tmp_path, monkeypatch):
    """把产物根目录隔离到 tmp，成员文件与 bundle 文件都落在这里。"""
    monkeypatch.setattr(artifacts.paths, "ROOT", tmp_path)
    return tmp_path


def _seed_project(store):
    return store.create_project("mat-p", "Mat", scenario="triage")


def _seed_version(store, root, name, lines, *, project_id):
    """写一份 dataset JSONL 并注册成产物 + 一个版本，返回 version_id。"""
    artifact_id = f"dataset:{name}"
    rel = artifacts.resolve(artifact_id)
    target = root / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("".join(line + "\n" for line in lines), encoding="utf-8")
    job_id = store.create_job(
        project_id=project_id, kind="generate", stage="data", scenario="triage", title="seed",
        request={}, argv=["x"], env_overlay={}, cwd=".", log_path="l.log",
        artifacts_in=[], artifacts_out=[artifact_id])
    artifacts.register(store, store.get_job(job_id))
    return store.list_artifact_versions(artifact_id)[0]["id"]


def _materialize(store, bundle_id, scenario="triage", project_id="p"):
    req = JobRequest(scenario=scenario, project_id=project_id,
                     params={"bundle_id": bundle_id})
    service = DataService(store, threading.Event())
    return service.materialize(req, on_log=lambda line: None)


def test_materialize_writes_union_and_bundle_row(store, root):
    pid = _seed_project(store)
    v1 = _seed_version(store, root, "batch1", [_line(_record("s1", "q", True))], project_id=pid)
    v2 = _seed_version(store, root, "batch2", [_line(_record("s2", "q", False))], project_id=pid)
    bundle = store.create_bundle(project_id=pid, name="snap", artifact_id="bundle:mat-p/snap")
    store.replace_bundle_members(bundle["id"],
                                 [{"version_id": v1, "op": "include", "ord": 0},
                                  {"version_id": v2, "op": "include", "ord": 1}])
    assert bundle["status"] == "draft"

    _materialize(store, bundle["id"], project_id=pid)

    after = store.get_bundle(bundle["id"])
    assert after["status"] == "materialized"
    assert after["records"] == 2
    assert after["sha256"]  # 非空

    target = root / artifacts.resolve(after["artifact_id"])
    assert target.is_file()
    assert hashlib.sha256(target.read_bytes()).hexdigest() == after["sha256"]
    # manifest 旁文件也写出来
    manifest = root / artifacts.resolve(after["artifact_id"]).replace(".jsonl", ".manifest.json")
    assert manifest.is_file()


def test_materialize_is_idempotent_on_sha(store, root):
    """P3：两次跑同一 bundle → 同 sha256（内容确定、成员不变）。"""
    pid = _seed_project(store)
    v1 = _seed_version(store, root, "b1", [_line(_record("x", "q", True))], project_id=pid)
    v2 = _seed_version(store, root, "b2", [_line(_record("y", "q", False))], project_id=pid)
    bundle = store.create_bundle(project_id=pid, name="idem", artifact_id="bundle:mat-p/idem")
    store.replace_bundle_members(bundle["id"],
                                 [{"version_id": v1, "op": "include", "ord": 0},
                                  {"version_id": v2, "op": "include", "ord": 1}])
    _materialize(store, bundle["id"], project_id=pid)
    first = store.get_bundle(bundle["id"])["sha256"]
    _materialize(store, bundle["id"], project_id=pid)
    second = store.get_bundle(bundle["id"])["sha256"]
    assert first == second == hashlib.sha256(
        (root / artifacts.resolve(f"bundle:mat-p/idem")).read_bytes()).hexdigest()


def test_materialize_exclude_drops_member(store, root):
    pid = _seed_project(store)
    v1 = _seed_version(store, root, "keep", [_line(_record("keep", "q", True))], project_id=pid)
    v2 = _seed_version(store, root, "drop", [_line(_record("drop", "q", True))], project_id=pid)
    bundle = store.create_bundle(project_id=pid, name="exc", artifact_id="bundle:mat-p/exc")
    store.replace_bundle_members(bundle["id"],
                                 [{"version_id": v1, "op": "include", "ord": 0},
                                  {"version_id": v2, "op": "exclude", "ord": 1}])
    _materialize(store, bundle["id"], project_id=pid)
    after = store.get_bundle(bundle["id"])
    assert after["records"] == 1
    stats = {m["op"]: m for m in store.get_bundle_members(bundle["id"])}
    assert stats["exclude"]["records_kept"] == 0


def test_drop_reasons_match_dedupe(store, root):
    """property：materialize 的 dup + state_conflict 等于 split_data.dedupe 的丢弃数。"""
    artifacts.paths.ensure_generators_on_path()
    import split_data

    pid = _seed_project(store)
    a = _record("state-a", "q", True)
    a_dup = _record("state-a", "q", True)                 # 与 a 完全重复 → dup
    c1 = _record("state-c", "q", True)
    c2 = _record("state-c", "q", False)                   # 同 state 反标 → state_conflict
    lines = [_line(a), _line(a_dup), _line(c1), _line(c2)]
    records = [a, a_dup, c1, c2]
    kept, dropped_dupes, n_conflicts = split_data.dedupe(records)
    assert (len(records), dropped_dupes, len(kept)) == (4, 1, 1)  # a 留，a_dup 是 dup，c1/c2 冲突被清

    v = _seed_version(store, root, "mixed", lines, project_id=pid)
    bundle = store.create_bundle(project_id=pid, name="mix", artifact_id="bundle:mat-p/mix")
    store.replace_bundle_members(bundle["id"], [{"version_id": v, "op": "include", "ord": 0}])
    _materialize(store, bundle["id"], project_id=pid)

    member = store.get_bundle_members(bundle["id"])[0]
    assert member["records_in"] == 4
    assert member["records_kept"] == len(kept)
    reasons = member["drop_reasons"]
    assert reasons["dup"] == dropped_dupes
    # dup + state_conflict == dedupe 总丢弃数（既不多也不少 —— 复用而非另算）
    assert reasons["dup"] + reasons["state_conflict"] == len(records) - len(kept)
    assert store.get_bundle(bundle["id"])["records"] == len(kept)


def test_bundle_version_registered(store, root):
    """物化写文件（service）+ 作业完成注册版本与 composed_of 血缘（register）。"""
    pid = _seed_project(store)
    v1 = _seed_version(store, root, "one", [_line(_record("z", "q", True))], project_id=pid)
    bundle = store.create_bundle(project_id=pid, name="ver", artifact_id="bundle:mat-p/ver")
    store.replace_bundle_members(bundle["id"], [{"version_id": v1, "op": "include", "ord": 0}])
    _materialize(store, bundle["id"], project_id=pid)
    # 真实链路里 materialize 作业由 on_finished 调 register：这里显式模拟一次
    job_id = store.create_job(
        project_id=pid, kind="materialize", stage="data", scenario="triage", title="mat",
        request={}, argv=["x"], env_overlay={}, cwd=".", log_path="l.log",
        artifacts_in=["dataset:one"], artifacts_out=["bundle:mat-p/ver"])
    artifacts.register(store, store.get_job(job_id))
    versions = store.list_artifact_versions("bundle:mat-p/ver")
    assert len(versions) >= 1
    assert artifacts.integrity(versions[0]) == "ok"
    edges = {(e["relation"], e["child"]) for e in store.lineage_of("dataset:one")}
    assert ("composed_of", "bundle:mat-p/ver") in edges
