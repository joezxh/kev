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


@pytest.fixture
def project_id(store):
    # create_job 从 Task 2 起强制 project_id；各测试共用这一个项目。
    return store.create_project("fx", "Fx")


def test_create_job_defaults_to_pending(store, project_id):
    job_id = store.create_job(
        project_id=project_id,
        kind="train", stage="train", scenario="critical-value", title="A1",
        request={"method": "a1"}, argv=["python", "-m", "kev.train"],
        env_overlay={}, cwd="/repo", log_path="data/console/jobs/x.log",
        artifacts_in=[], artifacts_out=["run:cv-8b"],
    )
    job = store.get_job(job_id)
    assert job["status"] == "pending"
    assert job["attempt"] == 1
    assert job["project_id"] == project_id
    assert job["argv"] == ["python", "-m", "kev.train"]
    assert job["artifacts_out"] == ["run:cv-8b"]
    assert job["started_at"] is None


def test_create_job_requires_project_id(store):
    pid = store.create_project("p", "P")
    with pytest.raises(TypeError):  # 缺关键字参数
        store.create_job(kind="train", stage="train", scenario="triage", title="t",
            request={}, argv=["x"], env_overlay={}, cwd=".", log_path="l.log",
            artifacts_in=[], artifacts_out=[])
    with pytest.raises(ValueError):  # 空哨兵不是项目
        store.create_job(project_id="", kind="train", stage="train", scenario="triage",
            title="t", request={}, argv=["x"], env_overlay={}, cwd=".", log_path="l.log",
            artifacts_in=[], artifacts_out=[])
    job_id = store.create_job(project_id=pid, kind="train", stage="train",
        scenario="triage", title="t", request={}, argv=["x"], env_overlay={}, cwd=".",
        log_path="l.log", artifacts_in=[], artifacts_out=[])
    assert store.get_job(job_id)["project_id"] == pid


def test_create_project_persists_scenario(store):
    pid = store.create_project("cv-2026-10", "CV Oct", scenario="critical-value", goal="ship")
    p = store.get_project(pid)
    assert p["scenario"] == "critical-value" and p["goal"] == "ship"
    assert p["status"] == "active" and p["freeze_min_records"] == 300


def test_scenario_known(store):
    assert store.scenario_known("triage") is True
    assert store.scenario_known("nope") is False


def test_project_reads_are_scoped(store):
    a, b = store.create_project("a", "A"), store.create_project("b", "B")
    common = dict(kind="train", stage="train", scenario="triage", title="t",
        request={}, argv=["x"], env_overlay={}, cwd=".", log_path="l.log", artifacts_in=[])
    ja = store.create_job(project_id=a, artifacts_out=["dataset:a/train"], **common)
    store.create_job(project_id=b, artifacts_out=["dataset:b/train"], **common)
    store.put_artifact(kind="dataset", name="a/train", path="data/a/train.jsonl", meta={})
    store.append_events(ja, [("stdout", "hello")])

    summary = store.project_summary(a)
    assert summary["jobs"] == 1 and summary["stages"]["train"]
    assert summary["artifacts"] == 1
    assert store.project_events(a) and not store.project_events(b)
    arts = store.list_project_artifacts(a)   # 只有 a 的产物解得到
    assert [x["id"] for x in arts] == ["dataset:a/train"]
    assert store.project_summary("nope") is None


def test_list_jobs_filters_by_project(store):
    a, b = store.create_project("a", "A"), store.create_project("b", "B")

    def kw(pid, title):
        return dict(project_id=pid, kind="train", stage="train", scenario="triage",
            title=title, request={}, argv=["x"], env_overlay={}, cwd=".",
            log_path="l.log", artifacts_in=[], artifacts_out=[])

    store.create_job(**kw(a, "a1"))
    store.create_job(**kw(b, "b1"))
    assert {j["title"] for j in store.list_jobs(project=a)} == {"a1"}
    assert store.list_jobs(project=a) and all(
        j["project_id"] == a for j in store.list_jobs(project=a))


def test_illegal_transition_is_rejected(store, project_id):
    job_id = store.create_job(
        project_id=project_id,
        kind="train", stage="train", scenario="triage", title="t",
        request={}, argv=["x"], env_overlay={}, cwd="/repo",
        log_path="l.log", artifacts_in=[], artifacts_out=[],
    )
    store.transition(job_id, "queued")
    store.transition(job_id, "running")
    store.transition(job_id, "succeeded")
    with pytest.raises(ValueError, match="illegal transition"):
        store.transition(job_id, "running")


def test_two_threads_racing_from_running_admit_exactly_one(store, project_id, monkeypatch):
    """reader 线程标 succeeded 与请求线程标 canceled 必须只有一个成功（Task 3 的 on_finished / cancel）。

    读-改-写的 transition 有一个窗口：SELECT 校验通过之后、UPDATE 落库之前，另一个线程可以把状态改掉，
    于是两个线程都读到 running、都通过校验，后写者赢 —— 已取消的作业最终是 succeeded，error 也会被冲掉。
    下面用 monkeypatch 把第一个读者挂住、强制第二个读者挤进这个窗口，所以红是确定性的，不靠线程调度运气。
    """
    job_id = store.create_job(
        project_id=project_id,
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


def test_terminal_states_accept_nothing(store, project_id):
    job_id = store.create_job(
        project_id=project_id,
        kind="train", stage="train", scenario="triage", title="t",
        request={}, argv=["x"], env_overlay={}, cwd="/repo",
        log_path="l.log", artifacts_in=[], artifacts_out=[],
    )
    store.transition(job_id, "queued")
    store.transition(job_id, "canceled")
    for target in ("queued", "running", "succeeded", "failed"):
        with pytest.raises(ValueError):
            store.transition(job_id, target)


def test_failed_records_exit_code_and_error(store, project_id):
    job_id = store.create_job(
        project_id=project_id,
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


def test_interrupt_stale_jobs_marks_running_and_queued(store, project_id):
    ids = []
    for kind in ("train", "benchmark"):
        job_id = store.create_job(
            project_id=project_id,
            kind=kind, stage="train", scenario="triage", title="t",
            request={}, argv=["x"], env_overlay={}, cwd="/repo",
            log_path="l.log", artifacts_in=[], artifacts_out=[],
        )
        store.transition(job_id, "queued")
        store.transition(job_id, "running")
        ids.append(job_id)
    done = store.create_job(
        project_id=project_id,
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


def test_pending_also_accepts_interrupted(store, project_id):
    """恢复路径把 pending（还没排队就被重启打断）也算 LIVE，状态机必须承认同一件事。

    interrupt_stale_jobs() 是一条直接 SQL，会把 pending 改成 interrupted；如果 ALLOWED 不收这条边，
    库里就躺着状态机自称造不出来的状态，而将来任何代码对 pending 作业调
    transition(..., "interrupted") 都会拿到 illegal transition。
    """
    stale = store.create_job(
        project_id=project_id,
        kind="split", stage="data", scenario="triage", title="t",
        request={}, argv=["x"], env_overlay={}, cwd="/repo",
        log_path="l.log", artifacts_in=[], artifacts_out=[],
    )
    store.transition(stale, "interrupted", error="编排服务重启")
    assert store.get_job(stale)["status"] == "interrupted"

    queued = store.create_job(
        project_id=project_id,
        kind="train", stage="train", scenario="triage", title="t",
        request={}, argv=["x"], env_overlay={}, cwd="/repo",
        log_path="l.log", artifacts_in=[], artifacts_out=[],
    )
    assert store.interrupt_stale_jobs() == 1
    assert store.get_job(queued)["status"] == "interrupted"


def test_active_job_of_kind_finds_only_live(store, project_id):
    job_id = store.create_job(
        project_id=project_id,
        kind="train", stage="train", scenario="triage", title="t",
        request={}, argv=["x"], env_overlay={}, cwd="/repo",
        log_path="l.log", artifacts_in=[], artifacts_out=[],
    )
    store.transition(job_id, "queued")
    assert store.active_job_of_kind("train")["id"] == job_id
    store.transition(job_id, "running")
    store.transition(job_id, "succeeded")
    assert store.active_job_of_kind("train") is None


def test_create_job_accepts_attempt_and_parent_for_retry(store, project_id):
    """重试要换名 + attempt 递增 + parent_id 指向原作业，三者一起才有可审计的重试链。"""
    first = store.create_job(
        project_id=project_id,
        kind="train", stage="train", scenario="critical-value", title="cv-8b-lora-v1",
        request={}, argv=["x"], env_overlay={}, cwd="/repo",
        log_path="l.log", artifacts_in=[], artifacts_out=[])
    second = store.create_job(
        project_id=project_id,
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


def test_events_round_trip_with_cursor(store, project_id):
    job_id = store.create_job(
        project_id=project_id,
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


def test_append_events_with_no_rows_reports_no_new_cursor(store, project_id):
    """空批次返回 0（=「没有新增」），不能返回该作业已有的最大 id。

    调用方拿返回值当续传位点：空批次把游标顶到当前末尾，等于告诉 SSE「日志到这里为止」，
    而这一批明明什么都没写。
    """
    job_id = store.create_job(
        project_id=project_id,
        kind="train", stage="train", scenario="triage", title="t",
        request={}, argv=["x"], env_overlay={}, cwd="/repo",
        log_path="l.log", artifacts_in=[], artifacts_out=[],
    )
    store.append_events(job_id, [("stdout", "a")])
    assert store.append_events(job_id, []) == 0
    assert [e["line"] for e in store.read_events(job_id)] == ["a"]


def test_schema_version_is_stamped(store):
    # v7 upgrades projects to the pipeline root: jobs.project_id + project
    # status/scenario/goal/archived_at/freeze_* (§4.1).
    # v8 registers every docs/domains spec: scenario_domains.spec_dir + scenarios'
    # track/generator_kind/distill_yaml/origin (kev/console/scenario_specs.py).
    # v9 lands the data-curation tables: artifact_versions / bundles /
    # bundle_members / record_reviews / record_review_history / project_releases
    # (Project Hub v7 实现计划 PR A，设计稿 §4.2-§4.5)。
    # v10 adds scenarios.distill_yaml_content: the editable distill YAML body
    # (DB is the editing source of truth; falls back to the repo file).
    assert store.schema_version() == 10


def test_schema_v7_adds_project_columns(store):
    assert store._column_exists("jobs", "project_id")
    for col in ("status", "scenario", "goal", "archived_at",
                "freeze_min_records", "freeze_min_review_ratio"):
        assert store._column_exists("projects", col)


def test_store_reopens_idempotently(tmp_path):
    path = tmp_path / "kev-console.db"
    first = Store(path)
    version = first.schema_version()
    second = Store(path)
    assert second.schema_version() == version == 10


# ---- schema v9：数据策展新表（Project Hub PR A） ---------------------------

V9_TABLES = ("artifact_versions", "bundles", "bundle_members",
             "record_reviews", "record_review_history", "project_releases")


def test_schema_v9_adds_curation_tables(store):
    assert store.schema_version() == 10
    for table in V9_TABLES:
        assert store._table_exists(table)


def test_idempotent_v9(tmp_path):
    # v9 全是新表（无列可 ALTER）：同一库跑两次 Store() 无变化，fresh 与升级收敛到同一形状。
    path = tmp_path / "kev-console.db"
    first = Store(path)
    assert first.schema_version() == 10
    second = Store(path)
    assert second.schema_version() == 10
    for table in V9_TABLES:
        assert second._table_exists(table)


def test_schema_v10_adds_distill_yaml_content(store):
    # v10 给 scenarios 加可编辑的 distill yaml 内容列（DB 为编辑真相源，回退读仓库文件）。
    assert store.schema_version() == 10
    assert store._column_exists("scenarios", "distill_yaml_content")


def _insert_v9_rows(store, pid):
    """PR A 不建 bundle/review 的 Store 方法（读写行为在 PR B-E 填），用裸 SQL 造行，
    这里只验 schema 形状与 delete_project 级联。"""
    from sqlalchemy import text
    ts = "2026-10-17T00:00:00+00:00"
    job_id = store.create_job(project_id=pid, kind="materialize", stage="data",
        scenario="triage", title="t", request={}, argv=["x"], env_overlay={}, cwd=".",
        log_path="l.log", artifacts_in=[], artifacts_out=[])
    conn = store._conn()
    conn.execute(text(
        "INSERT INTO artifact_versions (id, artifact_id, seq, job_id, path, sha256, meta, created_at)"
        " VALUES ('v1', 'dataset:cv/train', 1, :job, 'data/cv/train.jsonl', 'ab', '{}', :ts)"),
        {"job": job_id, "ts": ts})
    conn.execute(text(
        "INSERT INTO bundles (id, project_id, name, artifact_id, status, created_at, updated_at)"
        " VALUES ('b1', :pid, 'snap', 'bundle:cv/snap', 'draft', :ts, :ts)"),
        {"pid": pid, "ts": ts})
    conn.execute(text(
        "INSERT INTO bundle_members (bundle_id, version_id, op, ord) VALUES ('b1', 'v1', 'include', 0)"))
    conn.execute(text(
        "INSERT INTO project_releases (id, project_id, name, created_at) VALUES ('r1', :pid, 'rel', :ts)"),
        {"pid": pid, "ts": ts})
    conn.execute(text(
        "INSERT INTO record_reviews (id, scenario, origin_project_id, fingerprint, verdict, created_at, updated_at)"
        " VALUES ('rev1', 'triage', :pid, 'fp', 'accept', :ts, :ts)"),
        {"pid": pid, "ts": ts})


def test_delete_project_cascade_preserves_reviews(store):
    # §4.5 级联清单 + D13 例外：bundles/bundle_members/project_releases 随项目删；
    # record_reviews **不删行**（作用域是场景，删项目不能把下一轮要继承的决定一起删掉），
    # 只把 origin_project_id 置 ''（「来源已删」）；artifact_versions 是产物侧证据（D3），不清空。
    from sqlalchemy import text
    pid = store.create_project("cv1", "CV1")
    _insert_v9_rows(store, pid)
    assert store.delete_project(pid)
    conn = store._conn()
    for table in ("bundles", "bundle_members", "project_releases"):
        assert conn.execute(text(f"SELECT 1 FROM {table}")).fetchall() == []
    row = conn.execute(text(
        "SELECT origin_project_id FROM record_reviews WHERE id='rev1'")).mappings().fetchone()
    assert row is not None and row["origin_project_id"] == ""
    assert conn.execute(text("SELECT 1 FROM artifact_versions")).fetchall()


def test_slug_guard_rejects_when_project_has_job(store):
    # D9：项目下已有任何 job 或 bundle 时拒改 slug（bundle 路径里带 slug，
    # 改了就把已登记的 path 指向不存在的目录，integrity 全体 missing）。
    from kev.console.stages.base import Conflict
    pid = store.create_project("cv-2026-10", "CV")
    assert store.update_project(pid, slug="cv-2026-11")["slug"] == "cv-2026-11"  # 空项目可改
    store.create_job(project_id=pid, kind="train", stage="train", scenario="triage",
        title="t", request={}, argv=["x"], env_overlay={}, cwd=".", log_path="l.log",
        artifacts_in=[], artifacts_out=[])
    with pytest.raises(Conflict):
        store.update_project(pid, slug="cv-2026-12")
    assert store.update_project(pid, goal="ship")["goal"] == "ship"  # 其他列不受守卫影响
    # slug 传当前值不是「改」，不触发守卫
    assert store.update_project(pid, slug="cv-2026-11")["slug"] == "cv-2026-11"


def test_slug_guard_rejects_when_project_has_bundle(store):
    from kev.console.stages.base import Conflict
    from sqlalchemy import text
    ts = "2026-10-17T00:00:00+00:00"
    pid = store.create_project("cvb", "CVB")
    store._conn().execute(text(
        "INSERT INTO bundles (id, project_id, name, artifact_id, status, created_at, updated_at)"
        " VALUES ('b1', :pid, 'snap', 'bundle:cvb/snap', 'draft', :ts, :ts)"),
        {"pid": pid, "ts": ts})
    with pytest.raises(Conflict):
        store.update_project(pid, slug="renamed")
