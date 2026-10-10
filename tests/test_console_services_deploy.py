"""kev.console.services.deploy: in-process wrappers for image/smoke/cancel_endpoint.

Per the Wave B-4 plan, DeployService covers three of the four deploy
operations: image (docker build, in-process via subprocess.run + spawn_callable),
smoke (5-scenario HTTP probe, in-process), and cancel_endpoint (kill a
running deploy Popen via LocalExecutor.cancel_job). The deploy stage itself
is left on Popen because kev.serve is a long-lived process that the
function-call spawn_callable model can't represent.
"""
from __future__ import annotations

import threading
from pathlib import Path

import pytest

from kev.console.db import Store
from kev.console.services.deploy import DeployService
from kev.console.stages.base import JobRequest


@pytest.fixture
def svc(tmp_path):
    return DeployService(Store(tmp_path / "test.db"), threading.Event())


def _req(params=None) -> JobRequest:
    return JobRequest(scenario="critical-value", run_name="cv-rel",
                      params=params or {"temperature": "1.05"})


# ---- image ------------------------------------------------------------------

def test_image_dispatches_docker_build(monkeypatch, svc, tmp_path):
    """DeployService.image() runs docker build and returns its returncode."""
    import kev.console.services.deploy as svc_mod
    import subprocess

    captured: dict = {}

    class FakeProc:
        returncode = 0
        stdout = "build line 1\nbuild line 2\n"
        stderr = ""

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return FakeProc()

    monkeypatch.setattr(subprocess, "run", fake_run)
    # Pin DOCKERFILE to an existing file in tmp_path so the stage's path
    # resolution doesn't error before we get to the subprocess call.
    monkeypatch.setattr("kev.console.stages.deploy.DOCKERFILE", tmp_path / "Dockerfile")
    (tmp_path / "Dockerfile").write_text("FROM scratch", encoding="utf-8")

    rc = svc.image(_req(), on_log=lambda s: None, on_metric=lambda p: None)
    assert rc == {"returncode": 0}
    cmd = captured["cmd"]
    assert cmd[0] == "docker"
    assert cmd[1] == "build"
    # tag includes temperature
    assert any("cv-rel:1.05" in str(part) for part in cmd)


def test_image_rejects_missing_temperature(svc, tmp_path):
    """image() without a temperature raises Invalid (matches the stage's gate)."""
    from kev.console.stages.base import Invalid
    req = JobRequest(scenario="critical-value", run_name="cv-rel", params={})
    with pytest.raises(Invalid) as excinfo:
        svc.image(req, on_log=lambda s: None, on_metric=lambda p: None)
    assert excinfo.value.field == "temperature"


# ---- smoke ------------------------------------------------------------------

def test_smoke_invokes_smoke_script(monkeypatch, svc, tmp_path):
    """DeployService.smoke() runs smoke.py with --base-url/--out."""
    import kev.console.services.deploy as svc_mod
    import subprocess

    captured: dict = {}

    class FakeProc:
        returncode = 0
        stdout = "probing\n"
        stderr = ""

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return FakeProc()

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.chdir(tmp_path)  # so 'runs/cv-rel-smoke.json' resolves under tmp_path

    rc = svc.smoke(_req(), on_log=lambda s: None, on_metric=lambda p: None)
    assert rc == {"returncode": 0}
    cmd = captured["cmd"]
    assert "--base-url" in cmd
    assert "--out" in cmd
    assert "smoke.json" in cmd[-1]


# ---- cancel_endpoint --------------------------------------------------------

def test_cancel_endpoint_returns_1_when_no_match(tmp_path):
    """No deploy job running on the requested port -> returncode 1."""
    class FakeExecutor:
        def cancel_job(self, jid):
            return True
    store = Store(tmp_path / "test.db")
    svc = DeployService(store, threading.Event(), executor=FakeExecutor())
    rc = svc.cancel_endpoint(_req({"port": "8123"}),
                             on_log=lambda s: None, on_metric=lambda p: None)
    assert rc == {"returncode": 1}


def test_cancel_endpoint_refuses_without_executor():
    """Without a LocalExecutor bound, cancel_endpoint refuses (returncode 2)."""
    svc = DeployService(Store(), threading.Event(), executor=None)
    rc = svc.cancel_endpoint(_req({"port": "8008"}),
                             on_log=lambda s: None, on_metric=lambda p: None)
    assert rc == {"returncode": 2}


def test_cancel_endpoint_cancels_matching_job(tmp_path, monkeypatch):
    """A running deploy job with endpoint:8008 gets canceled."""
    from kev.console.executor import LocalExecutor
    store = Store(tmp_path / "test.db")
    # Insert a fake running deploy job by going through create_job + transition.
    job_id = store.create_job(
        kind="deploy", stage="deploy", scenario="critical-value", title="t",
        request={}, argv=[], env_overlay={},
        cwd=str(tmp_path), log_path=str(tmp_path / "l.log"),
        artifacts_in=[], artifacts_out=["endpoint:8008"],
    )
    store.transition(job_id, "running")
    # LocalExecutor with no live Popen — cancel_job returns False but the
    # loop body still records the lookup. To test the actual cancel path
    # we'd need a real Popen; instead verify the lookup-and-mark logic by
    # stubbing executor.cancel_job.
    class FakeExecutor:
        def __init__(self):
            self.canceled = []
        def cancel_job(self, jid):
            self.canceled.append(jid)
            return True
    fake = FakeExecutor()
    svc = DeployService(store, threading.Event(), executor=fake)
    rc = svc.cancel_endpoint(_req({"port": "8008"}),
                             on_log=lambda s: None, on_metric=lambda p: None)
    assert rc == {"returncode": 0}
    assert fake.canceled == [job_id]
