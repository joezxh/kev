"""kev.console.executor.spawn_callable: in-process counterpart of spawn().

Per the Wave B-1 plan, the executor gains spawn_callable() so the service layer
(kev.console.services.*) can run a function in-process while still going through
the same log file / events table / terminal-state plumbing that a subprocess
spawn does. This is the entry point for the in-process training/eval/etc.
service refactor (B-2..B-5).
"""
from __future__ import annotations

import threading
import time

import pytest

from kev.console.db import Store
from kev.console.executor import LocalExecutor


@pytest.fixture
def executor(tmp_path):
    store = Store(tmp_path / "test.db")
    return LocalExecutor(store, on_finished=None)


@pytest.fixture
def job(executor):
    return executor.store.create_job(
        kind="test-svc", stage="data", scenario="x", title="t",
        request={}, argv=[], env_overlay={},
        cwd=str(tmp := __import__("pathlib").Path.cwd()),
        log_path=str(tmp / "test-svc.log"),
        artifacts_in=[], artifacts_out=[],
    )


def test_spawn_callable_runs_fn_in_process(executor, job, tmp_path):
    """spawn_callable runs fn() on a background thread; returns its exit code."""
    log_path = tmp_path / "svc.log"
    rc_holder = []

    def fn():
        print("hello from service")
        rc_holder.append(0)
        return 0

    executor.spawn_callable(job, fn, label="service:data.generate", log_path=str(log_path))
    # Wait for the job to reach a terminal state
    deadline = time.time() + 5
    while time.time() < deadline:
        record = executor.store.get_job(job)
        if record and record["status"] in ("succeeded", "failed"):
            break
        time.sleep(0.05)
    assert record["status"] == "succeeded"
    assert record["exit_code"] == 0
    assert rc_holder == [0]
    # Log captured the line; events table has a meta row + the stdout line
    log_text = log_path.read_text(encoding="utf-8")
    assert "hello from service" in log_text


def test_spawn_callable_records_meta_event(executor, job, tmp_path):
    """spawn_callable writes a 'service-call: <label>' row to the events table."""
    executor.spawn_callable(job, lambda: 0, label="service:data.generate",
                            log_path=str(tmp_path / "svc.log"))
    deadline = time.time() + 5
    while time.time() < deadline:
        record = executor.store.get_job(job)
        if record and record["status"] in ("succeeded", "failed"):
            break
        time.sleep(0.05)
    events = executor.store.read_events(job)
    meta_rows = [row for row in events if row.get("stream") == "meta"]
    assert any("service-call: service:data.generate" in row.get("line", "") for row in meta_rows)


def test_spawn_callable_marks_failed_on_nonzero(executor, job, tmp_path):
    """fn() returning non-zero pushes the job to failed with the right exit_code."""
    def fn():
        return 7
    executor.spawn_callable(job, fn, label="x", log_path=str(tmp_path / "svc.log"))
    deadline = time.time() + 5
    while time.time() < deadline:
        record = executor.store.get_job(job)
        if record and record["status"] in ("succeeded", "failed"):
            break
        time.sleep(0.05)
    assert record["status"] == "failed"
    assert record["exit_code"] == 7
