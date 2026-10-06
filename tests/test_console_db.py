"""编排层的持久化：状态机、产物、血缘、事件、崩溃恢复。

重点是两条不变量：非法状态转移必须抛错，崩溃后 running 的作业必须变成 interrupted
（WSL2 会自动回收内存，服务重启是常态，见 spec §9.3）。

Run: uv run python -m pytest tests/test_console_db.py -q
"""
import threading

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


def test_two_threads_racing_from_running_admit_exactly_one(store, monkeypatch):
    """reader 线程标 succeeded 与请求线程标 canceled 必须只有一个成功（Task 3 的 on_finished / cancel）。

    读-改-写的 transition 有一个窗口：SELECT 校验通过之后、UPDATE 落库之前，另一个线程可以把状态改掉，
    于是两个线程都读到 running、都通过校验，后写者赢 —— 已取消的作业最终是 succeeded，error 也会被冲掉。
    下面用 monkeypatch 把第一个读者挂住、强制第二个读者挤进这个窗口，所以红是确定性的，不靠线程调度运气。
    """
    job_id = store.create_job(
        kind="train", stage="train", scenario="triage", title="t",
        request={}, argv=["x"], env_overlay={}, cwd="/repo",
        log_path="l.log", artifacts_in=[], artifacts_out=[],
    )
    store.transition(job_id, "queued")
    store.transition(job_id, "running")

    armed = threading.Event()
    release = threading.Event()
    readers = []
    read_job = Store.get_job

    def instrumented(self, target):
        job = read_job(self, target)
        if not armed.is_set():
            return job
        readers.append(job["status"])
        if len(readers) == 1:
            release.wait(timeout=10)      # 让第二个读者先进来
        else:
            release.set()
        return job

    monkeypatch.setattr(Store, "get_job", instrumented)
    armed.set()

    start = threading.Barrier(2)
    outcomes = []

    def push(status):
        start.wait()
        try:
            store.transition(job_id, status)
        except ValueError:
            outcomes.append("rejected")
        else:
            outcomes.append("accepted")

    threads = [threading.Thread(target=push, args=(status,))
               for status in ("succeeded", "canceled")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=15)
    armed.clear()

    assert sorted(outcomes) == ["accepted", "rejected"], f"两个线程都通过了校验：{outcomes}"
    assert store.get_job(job_id)["status"] in {"succeeded", "canceled"}


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


def test_pending_also_accepts_interrupted(store):
    """恢复路径把 pending（还没排队就被重启打断）也算 LIVE，状态机必须承认同一件事。

    interrupt_stale_jobs() 是一条直接 SQL，会把 pending 改成 interrupted；如果 ALLOWED 不收这条边，
    库里就躺着状态机自称造不出来的状态，而将来任何代码对 pending 作业调
    transition(..., "interrupted") 都会拿到 illegal transition。
    """
    stale = store.create_job(
        kind="split", stage="data", scenario="triage", title="t",
        request={}, argv=["x"], env_overlay={}, cwd="/repo",
        log_path="l.log", artifacts_in=[], artifacts_out=[],
    )
    store.transition(stale, "interrupted", error="编排服务重启")
    assert store.get_job(stale)["status"] == "interrupted"

    queued = store.create_job(
        kind="train", stage="train", scenario="triage", title="t",
        request={}, argv=["x"], env_overlay={}, cwd="/repo",
        log_path="l.log", artifacts_in=[], artifacts_out=[],
    )
    assert store.interrupt_stale_jobs() == 1
    assert store.get_job(queued)["status"] == "interrupted"


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


def test_create_job_accepts_attempt_and_parent_for_retry(store):
    """重试要换名 + attempt 递增 + parent_id 指向原作业，三者一起才有可审计的重试链。"""
    first = store.create_job(
        kind="train", stage="train", scenario="critical-value", title="cv-8b-lora-v1",
        request={}, argv=["x"], env_overlay={}, cwd="/repo",
        log_path="l.log", artifacts_in=[], artifacts_out=[])
    second = store.create_job(
        kind="train", stage="train", scenario="critical-value", title="cv-8b-lora-v1-r2",
        request={}, argv=["x"], env_overlay={}, cwd="/repo",
        log_path="l.log", artifacts_in=[], artifacts_out=[],
        attempt=2, parent_id=first)
    assert store.get_job(first)["attempt"] == 1
    assert store.get_job(first)["parent_id"] is None
    retried = store.get_job(second)
    assert retried["attempt"] == 2
    assert retried["parent_id"] == first


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
    # 游标必须精确等于本次写入的最后一行，而不是「>= 它」。append_events 的返回值是 SSE 的续传位点，
    # 拿大了就静默跳过一段日志，拿小了就重复推。
    assert store.read_events(job_id)[-1]["id"] == last
    store.append_events(job_id, [("stderr", "c")])
    first = store.read_events(job_id)
    assert [e["line"] for e in first] == ["a", "b", "c"]
    assert [e["line"] for e in store.read_events(job_id, after_id=first[1]["id"])] == ["c"]


def test_append_events_with_no_rows_reports_no_new_cursor(store):
    """空批次返回 0（=「没有新增」），不能返回该作业已有的最大 id。

    调用方拿返回值当续传位点：空批次把游标顶到当前末尾，等于告诉 SSE「日志到这里为止」，
    而这一批明明什么都没写。
    """
    job_id = store.create_job(
        kind="train", stage="train", scenario="triage", title="t",
        request={}, argv=["x"], env_overlay={}, cwd="/repo",
        log_path="l.log", artifacts_in=[], artifacts_out=[],
    )
    store.append_events(job_id, [("stdout", "a")])
    assert store.append_events(job_id, []) == 0
    assert [e["line"] for e in store.read_events(job_id)] == ["a"]


def test_schema_version_is_stamped(store):
    assert store.schema_version() == 2
