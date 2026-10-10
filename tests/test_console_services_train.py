"""kev.console.services.train: in-process TrainService + 503 inference demotion.

Per the Wave B-2 plan, TrainService replaces the train stage's Popen call with
an in-process kev.train.run() call. Two side effects on top of the in-process
call: a process-wide gpu_lock so concurrent GPU services queue, and a
_training_active Event that the /v1/* proxy reads to demote inference to 503
while training is in flight (single-GPU box, no concurrent inference).

The run itself is mockable via kev.console.services.train.kev_train_run so
these tests don't actually launch a training (which is hours-long on a real
GPU). The actual kev.train.run binding is exercised by the kev/ test_unit
suite; the only thing these tests cover is the service-shape and the proxy
gate.
"""
from __future__ import annotations

import argparse
import threading
import time

import pytest

from kev.console.db import Store
from kev.console.services.train import (TrainService, _training_active,
                                        is_training_active, kev_train_run)
from kev.console.stages.base import JobRequest


@pytest.fixture
def svc(tmp_path):
    return TrainService(Store(tmp_path / "test.db"),
                        threading.Event(), threading.Lock())


def _req(params=None) -> JobRequest:
    return JobRequest(scenario="critical-value", run_name="cv-train",
                      params=params or {})


# ---- _training_active flag --------------------------------------------------

def test_training_active_set_during_run(monkeypatch, svc):
    """_training_active is True while service.train() is in flight, False after."""
    seen: dict = {}

    def fake_run(args):
        seen["active"] = is_training_active()
        return 0

    monkeypatch.setattr("kev.console.services.train.kev_train_run", fake_run)
    assert not is_training_active()
    rc = svc.train(_req(), on_log=lambda s: None, on_metric=lambda p: None)
    assert rc["returncode"] == 0
    assert seen["active"] is True
    assert not is_training_active()


def test_training_active_cleared_on_exception(monkeypatch, svc):
    """An exception inside kev.train.run still clears _training_active (finally)."""
    def fake_run(args):
        raise RuntimeError("training failed")
    monkeypatch.setattr("kev.console.services.train.kev_train_run", fake_run)
    assert not is_training_active()
    with pytest.raises(RuntimeError):
        svc.train(_req(), on_log=lambda s: None, on_metric=lambda p: None)
    assert not is_training_active()


# ---- gpu_lock ---------------------------------------------------------------

def test_gpu_lock_blocks_concurrent_train_calls(tmp_path):
    """Two service instances sharing one gpu_lock serialize their train calls."""
    store = Store(tmp_path / "test.db")
    lock = threading.Lock()
    svc_a = TrainService(store, threading.Event(), lock)
    svc_b = TrainService(store, threading.Event(), lock)

    order: list = []
    barrier = threading.Event()

    def slow_run(args):
        order.append("start")
        barrier.wait(timeout=2)
        order.append("end")
        return 0

    import kev.console.services.train as svc_mod
    svc_mod.kev_train_run = slow_run

    t_a = threading.Thread(target=svc_a.train,
                           args=(_req(),), kwargs={"on_log": lambda s: None, "on_metric": lambda p: None})
    t_a.start()
    # Give A a moment to acquire the lock
    time.sleep(0.05)
    t_b = threading.Thread(target=svc_b.train,
                           args=(_req(),), kwargs={"on_log": lambda s: None, "on_metric": lambda p: None})
    t_b.start()
    # B cannot have started yet because A holds the lock
    time.sleep(0.05)
    assert order == ["start"]
    barrier.set()
    t_a.join(timeout=2)
    t_b.join(timeout=2)
    assert order == ["start", "end", "start", "end"]


# ---- cancel propagation -----------------------------------------------------

def test_cancel_event_propagates_to_kev_train(monkeypatch, svc):
    """Service-level cancel (LocalExecutor's cancel) is what kev.train.cancel sees."""
    captured: dict = {}

    def fake_run(args):
        # The service should have rebound kev.train.cancel to svc.cancel.
        import kev.train
        captured["cancel"] = kev.train.cancel
        return 0

    monkeypatch.setattr("kev.console.services.train.kev_train_run", fake_run)
    svc.cancel.set()
    svc.train(_req(), on_log=lambda s: None, on_metric=lambda p: None)
    assert captured["cancel"] is svc.cancel
    assert captured["cancel"].is_set()


def test_kev_train_cancel_restored_after_run(monkeypatch, svc):
    """kev.train.cancel is reset to its prior binding (or fresh Event) on exit."""
    import kev.train

    original = kev.train.cancel
    try:
        # Replace the module-level cancel with a known Event so we can verify
        # the service restores it (or substitutes a fresh one) after the run.
        sentinel = threading.Event()
        kev.train.cancel = sentinel

        monkeypatch.setattr("kev.console.services.train.kev_train_run", lambda a: 0)
        svc.train(_req(), on_log=lambda s: None, on_metric=lambda p: None)
        # After the call, the service must have restored the prior binding,
        # not leaked svc.cancel into the module's namespace for the next run.
        assert kev.train.cancel is sentinel
    finally:
        kev.train.cancel = original


# ---- proxy_kev 503 gate -----------------------------------------------------

def test_proxy_kev_returns_503_when_training_active(monkeypatch):
    """The /v1/* proxy demotes inference to 503 while _training_active is set."""
    from fastapi.testclient import TestClient
    from kev.console.app import create_app, wire_console_state

    app = create_app()
    wire_console_state(app)
    client = TestClient(app)

    # Set the flag, then make a request and assert 503.
    _training_active.set()
    try:
        resp = client.post("/console/api/kev/v1/systemone",
                           headers={"Authorization": "Bearer fake"},
                           json={"questions": []})
        assert resp.status_code == 503
        body = resp.json()
        assert body["error"] == "training_in_progress"
        assert resp.headers.get("Retry-After") == "30"
    finally:
        _training_active.clear()
