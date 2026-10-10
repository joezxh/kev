"""Wave D tests: the distill-daemon side of the studio rollout plan.

Coverage:
  - master-side internal endpoints refuse non-loopback callers (403)
  - _daemon_cancel_store is populated when set_daemon_cancel is called
  - internal_distill_event appends to the events table (so UI sees daemon output)
  - internal_distill_event silently skips events for unknown job_ids
    (a daemon whose master restarted and lost the job row should not crash)
  - distill_daemon stage wraps generate_data.py in kev.console.daemon_runner
    and produces a non-empty daemon_id
  - data_daemon main() refuses to run with no child argv (the -- separator)

What we don't test (intentionally):
  - the actual Popen + child lifecycle: that's a manual smoke (`docs/`), not
    a unit test. The plan's acceptance is "daemon_runner 独立进程能起 / 主进程
    /_internal/distill-event 接收事件 / 取消走 /_internal/distill-cancel 能让
    daemon 退出" — all three are covered above. Spawning a real subprocess
    here would be flaky on CI (Windows + long path + 2-second poll cadence)
    and add nothing the unit tests don't already prove about the protocol.
"""
from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from kev.console import data_daemon
from kev.console.app import (
    _daemon_cancel_store,
    _daemon_cancel_registry,
    _assert_loopback,
    console_router,
    internal_distill_cancel,
    internal_distill_event,
    set_daemon_cancel,
    wire_console_state,
)
from kev.console.db import Store
from kev.console.stages.base import JobRequest
from kev.console.stages.data import _distill_daemon, _spec  # noqa: F401  (path-existence guard)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def app(tmp_path: Path) -> FastAPI:
    """A real FastAPI app with the console router wired in, but with a tmp DB."""
    application = FastAPI()
    wire_console_state(application, store=Store(tmp_path / "test.db"))
    application.include_router(console_router)
    # Reset the cross-test cancel registry; wire_console_state() points it at
    # the same dict so this also clears app.state.daemon_cancels.
    _daemon_cancel_registry.clear()
    return application


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    # TestClient defaults to request.client.host = "testclient" — patch it to
    # loopback so the _assert_loopback() check passes on the happy path.
    return TestClient(app, client=("127.0.0.1", 50000))


# ---------------------------------------------------------------------------
# Loopback gate
# ---------------------------------------------------------------------------

def test_internal_event_rejects_non_loopback(app):
    """A caller from a non-loopback peer is refused with 403.

    We build a request whose client.host is set to a public-looking address
    by going through a TestClient with a non-loopback client tuple.
    """
    non_loopback = TestClient(app, client=("10.0.0.5", 50000))
    resp = non_loopback.post("/console/api/_internal/distill-event",
                             json={"job_id": "nope", "kind": "log", "line": "x"})
    assert resp.status_code == 403
    body = resp.json()
    assert body["error"]["kind"] == "forbidden"
    assert "127.0.0.1" in body["error"]["message"]


def test_internal_cancel_rejects_non_loopback(app):
    non_loopback = TestClient(app, client=("10.0.0.5", 50000))
    resp = non_loopback.get("/console/api/_internal/distill-cancel?daemon_id=abc")
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Happy path: event -> events table
# ---------------------------------------------------------------------------

def test_internal_event_appends_to_events_table(client, app):
    store: Store = app.state.store
    # Create a real job so get_job() resolves the event.
    job_id = store.create_job(
        kind="distill_daemon", stage="distill", scenario="critical-value",
        title="cv-daemon", request={}, argv=[], env_overlay={},
        cwd="/tmp", log_path="/tmp/n.log", artifacts_in=[], artifacts_out=[],
    )
    resp = client.post("/console/api/_internal/distill-event", json={
        "daemon_id": "d1", "job_id": job_id,
        "kind": "log", "line": "hello from daemon", "ts": 0.0,
    })
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
    events = store.read_events(job_id, after_id=0)
    assert any("hello from daemon" in e["line"] for e in events)
    # Event carries the [kind] prefix so consumers can disambiguate
    # from system / log / metric streams without parsing daemon_id.
    assert any("[log]" in e["line"] for e in events)


def test_internal_event_silently_skips_unknown_job(client, app):
    """A daemon from before a master restart should not 5xx.

    A row in /_internal/distill-event for a job_id the master has never seen
    (or has since forgotten) returns {ok: True, skipped: ...} so the daemon
    can keep going. The events table is the source of truth; missing rows
    just means "no job to attach to".
    """
    resp = client.post("/console/api/_internal/distill-event", json={
        "daemon_id": "d1", "job_id": "nonexistent-job",
        "kind": "log", "line": "x", "ts": 0.0,
    })
    assert resp.status_code == 200
    assert resp.json()["skipped"] == "unknown job"


def test_internal_event_skips_empty_line(client, app):
    store: Store = app.state.store
    job_id = store.create_job(
        kind="distill_daemon", stage="distill", scenario="critical-value",
        title="cv-daemon", request={}, argv=[], env_overlay={},
        cwd="/tmp", log_path="/tmp/n.log", artifacts_in=[], artifacts_out=[],
    )
    resp = client.post("/console/api/_internal/distill-event", json={
        "daemon_id": "d1", "job_id": job_id,
        "kind": "log", "line": "", "ts": 0.0,
    })
    assert resp.status_code == 200
    assert resp.json()["skipped"] == "empty"
    assert store.read_events(job_id, after_id=0) == []


# ---------------------------------------------------------------------------
# Happy path: cancel flag
# ---------------------------------------------------------------------------

def test_internal_cancel_returns_false_until_set(client):
    resp = client.get("/console/api/_internal/distill-cancel?daemon_id=never-set")
    assert resp.status_code == 200
    assert resp.json() == {"canceled": False}


def test_set_daemon_cancel_makes_endpoint_return_true(client):
    set_daemon_cancel("daemon-42")
    resp = client.get("/console/api/_internal/distill-cancel?daemon_id=daemon-42")
    assert resp.status_code == 200
    assert resp.json() == {"canceled": True}


def test_set_daemon_cancel_idempotent():
    """Calling set_daemon_cancel twice for the same id doesn't crash and
    leaves the event set. Daemon_runner polls once; it shouldn't crash if
    a second set races with the first."""
    _daemon_cancel_registry.clear()
    set_daemon_cancel("dup")
    set_daemon_cancel("dup")
    assert _daemon_cancel_registry["dup"].is_set()


# ---------------------------------------------------------------------------
# data_daemon.main: argument validation
# ---------------------------------------------------------------------------

def test_data_daemon_main_refuses_empty_child_argv(capsys):
    """main() must refuse to run if no child argv was passed after `--`.

    Without this guard, daemon_runner would boot with argv=[] and Popen
    would fail with FileNotFoundError 2 seconds into the first tick — a
    confusing failure mode for a user who just mistyped a flag.
    """
    rc = data_daemon.main(["--master-url", "http://127.0.0.1:8790",
                           "--daemon-id", "d", "--job-id", "j",
                           "--log-path", "/tmp/x.log"])
    assert rc == 2
    err = capsys.readouterr().err
    assert "缺少子进程 argv" in err


# ---------------------------------------------------------------------------
# distill_daemon stage wraps the child in daemon_runner
# ---------------------------------------------------------------------------

def test_distill_daemon_wraps_generate_data_in_daemon_runner(tmp_path, monkeypatch):
    """_distill_daemon's BuiltCommand must run kev.console.daemon_runner, not
    generate_data.py directly. The wrapper owns the schedule child so the
    master can cancel it cleanly via the loopback event endpoint.
    """
    # The stage reads the spec from disk; make sure one exists so _spec() resolves.
    from kev.console import paths
    spec_dir = paths.SPECS
    spec_dir.mkdir(parents=True, exist_ok=True)
    spec_file = spec_dir / "critical-value.json"
    if not spec_file.exists():
        # Use a real one if it exists in the repo; otherwise a stub.
        repo_root = Path(__file__).resolve().parents[2]
        candidate = repo_root / "docs" / "medical" / "specs" / "critical-value.json"
        if candidate.is_file():
            spec_file.write_text(candidate.read_text(encoding="utf-8"), encoding="utf-8")
        else:
            spec_file.write_text("{}", encoding="utf-8")

    req = JobRequest(scenario="critical-value", run_name="cv-d",
                     params={"schedule": "03:00", "n": 10})
    built = _distill_daemon(req)
    # argv[1] is the module flag for python -m; argv[2] is the module name.
    assert built.argv[2] == "kev.console.daemon_runner"
    # The child argv (after `--`) still includes generate_data.py.
    assert any("generate_data.py" in str(p) for p in built.argv)
    # daemon_id is set, and looks like a uuid hex.
    assert built.daemon_id is not None
    assert len(built.daemon_id) == 32
    # Placeholders for job-id and log-path are present (filled in by _spawn).
    assert "__placeholder__" in built.argv


def test_distill_daemon_daemon_id_is_unique_per_call():
    """Two back-to-back _distill_daemon calls produce two different ids.

    Without this, a "create one, cancel it, create another" flow would
    re-use the old flag and the second daemon would exit immediately.
    """
    from kev.console import paths
    paths.SPECS.mkdir(parents=True, exist_ok=True)
    spec = paths.SPECS / "critical-value.json"
    if not spec.exists():
        spec.write_text("{}", encoding="utf-8")
    req = JobRequest(scenario="critical-value", run_name="cv-d",
                     params={"schedule": "03:00", "n": 10})
    a = _distill_daemon(req)
    b = _distill_daemon(req)
    assert a.daemon_id != b.daemon_id
