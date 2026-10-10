"""kev.console.services.eval: in-process wrappers for the 4 eval stages.

Per the Wave B-3 plan, EvalService covers baseline / benchmark / compare /
calibrate. Two tiers share the service: GPU eval (baseline, benchmark) which
acquires gpu_lock so it never runs concurrently with training; CPU eval
(compare, calibrate) which never touches the GPU and runs as fast as a few
file reads.

Like the other service tests, we mock the kev.*.run calls via the
indirection layer (kev.console.services.eval.{kev_benchmark_run,...}) so the
suite stays seconds-fast and has no GPU / model dependency.
"""
from __future__ import annotations

import argparse
import threading
import time

import pytest

from kev.console.db import Store
from kev.console.services.eval import (EvalService, kev_benchmark_run,
                                        kev_compare_run, kev_calibrate_run)
from kev.console.stages.base import JobRequest


@pytest.fixture
def svc(tmp_path):
    return EvalService(Store(tmp_path / "test.db"),
                       threading.Event(), threading.Lock())


def _req(params=None, *, kind="benchmark", run_name="cv") -> JobRequest:
    return JobRequest(scenario="critical-value", run_name=run_name,
                      params=params or {})


# ---- GPU eval (baseline, benchmark) -----------------------------------------

def test_benchmark_dispatches_to_benchmark_run(monkeypatch, svc, tmp_path):
    """EvalService.benchmark() builds a Namespace and calls kev.benchmark.run."""
    captured: dict = {}

    def fake_run(args):
        captured["ns"] = args
        return 0

    monkeypatch.setattr("kev.console.services.eval.kev_benchmark_run", fake_run)
    rc = svc.benchmark(_req({"run": "runs/cv", "out": "runs/cv-eval",
                             "data": "data/cv", "split": "development"}),
                       on_log=lambda s: None, on_metric=lambda p: None)
    assert rc == {"returncode": 0}
    ns = captured["ns"]
    assert ns.run == "runs/cv"
    assert ns.out == "runs/cv-eval"
    assert ns.data == "data/cv/development.jsonl"


def test_baseline_uses_default_baseline_run(monkeypatch, svc, tmp_path):
    """EvalService.baseline() falls back to DEFAULT_BASELINE when none given."""
    from kev.console.stages import eval as eval_stage
    captured: dict = {}

    def fake_run(args):
        captured["ns"] = args
        return 0

    monkeypatch.setattr("kev.console.services.eval.kev_benchmark_run", fake_run)
    rc = svc.baseline(_req({"data": "data/cv/development.jsonl"}),
                      on_log=lambda s: None, on_metric=lambda p: None)
    assert rc == {"returncode": 0}
    assert captured["ns"].run == eval_stage.DEFAULT_BASELINE


def test_gpu_eval_serializes_with_train(tmp_path):
    """Two GPU eval calls (or one eval + one train) sharing gpu_lock serialize."""
    lock = threading.Lock()
    store = Store(tmp_path / "test.db")
    svc_a = EvalService(store, threading.Event(), lock)
    svc_b = EvalService(store, threading.Event(), lock)

    order: list = []
    barrier = threading.Event()

    def slow_run(args):
        order.append("start")
        barrier.wait(timeout=2)
        order.append("end")
        return 0

    import kev.console.services.eval as svc_mod
    svc_mod.kev_benchmark_run = slow_run

    t_a = threading.Thread(target=svc_a.benchmark,
                           args=(_req(),),
                           kwargs={"on_log": lambda s: None, "on_metric": lambda p: None})
    t_a.start()
    time.sleep(0.05)
    t_b = threading.Thread(target=svc_b.baseline,
                           args=(_req(),),
                           kwargs={"on_log": lambda s: None, "on_metric": lambda p: None})
    t_b.start()
    time.sleep(0.05)
    assert order == ["start"]   # A holds the lock; B is queued
    barrier.set()
    t_a.join(timeout=2)
    t_b.join(timeout=2)
    assert order == ["start", "end", "start", "end"]


# ---- CPU eval (compare, calibrate) ------------------------------------------

def test_compare_dispatches_to_compare_run(monkeypatch, svc, tmp_path):
    """EvalService.compare() builds a Namespace and calls kev.compare.run."""
    captured: dict = {}

    def fake_run(args):
        captured["ns"] = args
        return 0

    monkeypatch.setattr("kev.console.services.eval.kev_compare_run", fake_run)
    rc = svc.compare(_req(run_name="cv",
                          params={"candidate": "runs/x-eval",
                                  "reference": "runs/x-baseline-eval"}),
                     on_log=lambda s: None, on_metric=lambda p: None)
    assert rc == {"returncode": 0}
    ns = captured["ns"]
    assert ns.candidate == "runs/x-eval"
    assert ns.reference == "runs/x-baseline-eval"
    assert ns.out.endswith("-compare")


def test_compare_rejects_same_candidate_and_reference(svc, tmp_path):
    """Same path on both sides raises Invalid (matches the stage's gate)."""
    from kev.console.stages.base import Invalid
    with pytest.raises(Invalid):
        svc.compare(_req({"candidate": "runs/x", "reference": "runs/x"}),
                    on_log=lambda s: None, on_metric=lambda p: None)


def test_calibrate_dispatches_to_calibrate_run(monkeypatch, svc, tmp_path):
    """EvalService.calibrate() defaults rows to <run>-eval/rows.json."""
    captured: dict = {}

    def fake_run(args):
        captured["ns"] = args
        return 0

    monkeypatch.setattr("kev.console.services.eval.kev_calibrate_run", fake_run)
    rc = svc.calibrate(_req(),
                       on_log=lambda s: None, on_metric=lambda p: None)
    assert rc == {"returncode": 0}
    ns = captured["ns"]
    assert ns.rows == "runs/cv-eval/rows.json"
    assert ns.out.endswith("calibration.json")


def test_calibrate_rejects_non_rows_path(svc, tmp_path):
    """rows not ending in rows.json is rejected (matches the stage's gate)."""
    from kev.console.stages.base import Invalid
    with pytest.raises(Invalid) as excinfo:
        svc.calibrate(_req({"rows": "runs/x/something-else.json"}),
                      on_log=lambda s: None, on_metric=lambda p: None)
    assert excinfo.value.field == "rows"
