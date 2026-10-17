"""add_usage 配额真写（PR F，后端面）。

覆盖 plan §PR F 检查点的失败测试（先 RED）：
- test_add_usage_accumulates —— 单条 UPDATE 落三列，字节→GB、秒→小时、调用整型累加；
  无 quota 行时补全 0 再累加；空 project_id（legacy）不写。
- test_register_bumps_storage_used —— artifacts.register 登记单文件版本后项目
  storage_gb_used > 0（§4.6-2：今天三列无任何写入者）。
- test_train_success_bumps_hours —— train 作业成功后 register_finished 按
  finished_at - started_at 落 training_hours_used > 0。

Run: uv run python -m pytest tests/test_console_quota.py -q
"""
import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from kev.console import artifacts
from kev.console.app import create_app, register_finished
from kev.console.db import Store


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


def test_add_usage_accumulates(client):
    store = _store(client)
    pid = _mk_project(client, "quota-accum")

    # 无 quota 行时先补全 0 再累加：一次落 1 GiB / 3600 s / 5 次调用。
    store.add_usage(pid, storage_bytes=1024 ** 3, training_seconds=3600, api_calls=5)
    q = store.get_quota(pid)
    assert q["storage_gb_used"] == pytest.approx(1.0)
    assert q["training_hours_used"] == pytest.approx(1.0)
    assert q["api_calls_used"] == 5

    # 第二次累加不覆盖、不重置上一列。
    store.add_usage(pid, storage_bytes=2 * 1024 ** 3, api_calls=3)
    q = store.get_quota(pid)
    assert q["storage_gb_used"] == pytest.approx(3.0)
    assert q["training_hours_used"] == pytest.approx(1.0)
    assert q["api_calls_used"] == 8

    # 空 project_id（legacy 作业）不落任何一列。
    assert store.add_usage("", storage_bytes=1024 ** 3) is None


def test_register_bumps_storage_used(client):
    store = _store(client)
    pid = _mk_project(client, "quota-reg")

    artifact_id = "dataset:reg-src"
    target = client.root / artifacts.resolve(artifact_id)
    target.parent.mkdir(parents=True, exist_ok=True)
    records = [{"state": "s", "questions": {"q": {"type": "noul", "instructions": "i",
                                                   "label": "a"}}} for _ in range(20)]
    target.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records),
                      encoding="utf-8")
    size = target.stat().st_size
    assert size > 0

    job_id = store.create_job(
        project_id=pid, kind="generate", stage="data", scenario="triage", title="g",
        request={}, argv=["x"], env_overlay={}, cwd=".", log_path="l.log",
        artifacts_in=[], artifacts_out=[artifact_id])
    artifacts.register(store, store.get_job(job_id))

    q = store.get_quota(pid)
    assert q["storage_gb_used"] == pytest.approx(size / (1024 ** 3))


def test_train_success_bumps_hours(client):
    store = _store(client)
    pid = _mk_project(client, "quota-train")

    job_id = store.create_job(
        project_id=pid, kind="train", stage="train", scenario="triage", title="t",
        request={}, argv=["x"], env_overlay={}, cwd=".", log_path="l.log",
        artifacts_in=[], artifacts_out=[])
    store.transition(job_id, "running")
    # 回溯 started_at 到两小时前，让 finished_at - started_at ≈ 2h（timespec=seconds 粒度内）。
    back = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat(timespec="seconds")
    store._conn().execute(text("UPDATE jobs SET started_at=:s WHERE id=:id"),
                          {"s": back, "id": job_id})
    store.transition(job_id, "succeeded", exit_code=0)

    register_finished(store, job_id, 0)

    q = store.get_quota(pid)
    assert 1.9 <= q["training_hours_used"] <= 2.1


def test_train_failure_adds_nothing(client):
    store = _store(client)
    pid = _mk_project(client, "quota-train-fail")

    job_id = store.create_job(
        project_id=pid, kind="train", stage="train", scenario="triage", title="t",
        request={}, argv=["x"], env_overlay={}, cwd=".", log_path="l.log",
        artifacts_in=[], artifacts_out=[])
    store.transition(job_id, "running")
    store.transition(job_id, "failed", exit_code=1)

    register_finished(store, job_id, 1)

    q = store.get_quota(pid)
    assert q["training_hours_used"] == 0.0
