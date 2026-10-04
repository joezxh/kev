"""编排层的持久化：状态机、产物、血缘、事件、崩溃恢复。

重点是两条不变量：非法状态转移必须抛错，崩溃后 running 的作业必须变成 interrupted
（WSL2 会自动回收内存，服务重启是常态，见 spec §9.3）。

Run: uv run python -m pytest tests/test_console_db.py -q
"""
import pytest

from kev.console.db import Store


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "kev-console.db")


def test_create_job_defaults_to_pending(store):
    job_id = store.create_job(
        kind="train", stage="train", scenario="critical-value", title="A1",
        request={"method": "a1"}, argv=["python", "-m", "kev.train"],
        env_overlay={}, cwd="/repo", log_path="data/console/jobs/x.log",
        artifacts_in=[], artifacts_out=["run:cv-8b"],
    )
    job = store.get_job(job_id)
    assert job["status"] == "pending"
    assert job["attempt"] == 1
    assert job["argv"] == ["python", "-m", "kev.train"]
    assert job["artifacts_out"] == ["run:cv-8b"]
    assert job["started_at"] is None


def test_illegal_transition_is_rejected(store):
    job_id = store.create_job(
        kind="train", stage="train", scenario="triage", title="t",
        request={}, argv=["x"], env_overlay={}, cwd="/repo",
        log_path="l.log", artifacts_in=[], artifacts_out=[],
    )
    store.transition(job_id, "queued")
    store.transition(job_id, "running")
    store.transition(job_id, "succeeded")
    with pytest.raises(ValueError, match="illegal transition"):
        store.transition(job_id, "running")


def test_terminal_states_accept_nothing(store):
    job_id = store.create_job(
        kind="train", stage="train", scenario="triage", title="t",
        request={}, argv=["x"], env_overlay={}, cwd="/repo",
        log_path="l.log", artifacts_in=[], artifacts_out=[],
    )
    store.transition(job_id, "queued")
    store.transition(job_id, "canceled")
    for target in ("queued", "running", "succeeded", "failed"):
        with pytest.raises(ValueError):
            store.transition(job_id, target)


def test_failed_records_exit_code_and_error(store):
    job_id = store.create_job(
        kind="train", stage="train", scenario="triage", title="t",
        request={}, argv=["x"], env_overlay={}, cwd="/repo",
        log_path="l.log", artifacts_in=[], artifacts_out=[],
    )
    store.transition(job_id, "queued")
    store.transition(job_id, "running")
    store.transition(job_id, "failed", error="boom", exit_code=2)
    job = store.get_job(job_id)
    assert (job["exit_code"], job["error"]) == (2, "boom")
    assert job["finished_at"] is not None


def test_interrupt_stale_jobs_marks_running_and_queued(store):
    ids = []
    for kind in ("train", "benchmark"):
        job_id = store.create_job(
            kind=kind, stage="train", scenario="triage", title="t",
            request={}, argv=["x"], env_overlay={}, cwd="/repo",
            log_path="l.log", artifacts_in=[], artifacts_out=[],
        )
        store.transition(job_id, "queued")
        store.transition(job_id, "running")
        ids.append(job_id)
    done = store.create_job(
        kind="split", stage="data", scenario="triage", title="t",
        request={}, argv=["x"], env_overlay={}, cwd="/repo",
        log_path="l.log", artifacts_in=[], artifacts_out=[],
    )
    store.transition(done, "queued")
    store.transition(done, "running")
    store.transition(done, "succeeded")

    assert store.interrupt_stale_jobs() == 2
    assert store.get_job(ids[0])["status"] == "interrupted"
    assert store.get_job(done)["status"] == "succeeded"


def test_active_job_of_kind_finds_only_live(store):
    job_id = store.create_job(
        kind="train", stage="train", scenario="triage", title="t",
        request={}, argv=["x"], env_overlay={}, cwd="/repo",
        log_path="l.log", artifacts_in=[], artifacts_out=[],
    )
    store.transition(job_id, "queued")
    assert store.active_job_of_kind("train")["id"] == job_id
    store.transition(job_id, "running")
    store.transition(job_id, "succeeded")
    assert store.active_job_of_kind("train") is None


def test_artifact_id_is_kind_colon_name(store):
    aid = store.put_artifact(kind="dataset", name="cv", path="data/cv", meta={"records": 787})
    assert aid == "dataset:cv"
    assert store.get_artifact(aid)["meta"]["records"] == 787


def test_put_artifact_is_idempotent(store):
    store.put_artifact(kind="run", name="r1", path="runs/r1", meta={"a": 1})
    store.put_artifact(kind="run", name="r1", path="runs/r1", meta={"a": 2})
    assert len(store.list_artifacts("run")) == 1
    assert store.get_artifact("run:r1")["meta"]["a"] == 2


def test_lineage_joins_on_artifact(store):
    store.put_artifact(kind="dataset", name="cv", path="data/cv", meta={})
    store.put_artifact(kind="dataset", name="cv/train", path="data/cv/train.jsonl", meta={})
    store.add_lineage("dataset:cv", "dataset:cv/train", "split_into")
    edges = store.lineage_of("dataset:cv")
    assert [(e["relation"], e["child"]) for e in edges] == [("split_into", "dataset:cv/train")]
    assert store.lineage_of("dataset:cv/train") == []


def test_events_round_trip_with_cursor(store):
    job_id = store.create_job(
        kind="train", stage="train", scenario="triage", title="t",
        request={}, argv=["x"], env_overlay={}, cwd="/repo",
        log_path="l.log", artifacts_in=[], artifacts_out=[],
    )
    last = store.append_events(job_id, [("stdout", "a"), ("stdout", "b")])
    store.append_events(job_id, [("stderr", "c")])
    first = store.read_events(job_id)
    assert [e["line"] for e in first] == ["a", "b", "c"]
    assert [e["line"] for e in store.read_events(job_id, after_id=first[1]["id"])] == ["c"]
    assert store.read_events(job_id)[-1]["id"] >= last


def test_schema_version_is_stamped(store):
    assert store.schema_version() == 1
