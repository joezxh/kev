"""kev.console.services.data: in-process wrappers for 5 console-owned stages.

Per the Wave B-1 plan, the DataService covers generate / goldset / goldset_audit /
precheck / make_examples. The 3 skill-script stages (plan_size / distill / split)
keep their Popen path; DataService does not provide methods for them.

Each test is in-process and uses monkeypatch to stub the business function, so
the tests run in seconds and have no GPU / network dependency.
"""
from __future__ import annotations

import argparse
import threading
from pathlib import Path

import pytest

from kev.console.db import Store
from kev.console.services.data import DataService
from kev.console.stages.base import JobRequest


@pytest.fixture
def svc(tmp_path):
    store = Store(tmp_path / "test.db")
    return DataService(store, threading.Event())


def _req(scenario="critical-value", run_name="t", params=None) -> JobRequest:
    return JobRequest(scenario=scenario, run_name=run_name, params=params or {})


# ---- generate ---------------------------------------------------------------

def test_generate_dispatches_to_gen_module(monkeypatch, svc, tmp_path):
    """DataService.generate() dispatches to gen_<scenario>.run() with built argv."""
    import sys
    import types
    # Plant a fake gen_critical_value module in sys.modules so importlib sees it.
    calls = []
    fake = types.ModuleType("gen_critical_value")
    def fake_run(argv):
        calls.append(argv)
        return 0
    fake.run = fake_run
    monkeypatch.setitem(sys.modules, "gen_critical_value", fake)

    logs: list[str] = []
    result = svc.generate(_req(params={"n": 5, "seed": 7}), on_log=logs.append)
    assert result == {"returncode": 0}
    assert calls == [["--n", "5", "--out", "data/critical-value.jsonl", "--seed", "7", "--pairs", "0"]]
    assert logs == []  # fake_run prints nothing


# ---- goldset ----------------------------------------------------------------

def test_goldset_dispatches_to_run_sample(monkeypatch, svc, tmp_path):
    """DataService.goldset() calls make_goldset.run_sample with a built Namespace."""
    from kev.console.generators import make_goldset
    calls = []
    def fake_run_sample(ns):
        calls.append((ns.command, ns.data, ns.n, ns.out))
        return 0
    monkeypatch.setattr(make_goldset, "run_sample", fake_run_sample)

    result = svc.goldset(_req(params={"n": 50, "seed": 1, "out": "data/cv.gold.jsonl"}),
                         on_log=lambda s: None)
    assert result == {"returncode": 0}
    assert calls == [("sample", "data/critical-value.jsonl", 50, "data/cv.gold.jsonl")]


# ---- goldset_audit ----------------------------------------------------------

def test_goldset_audit_dispatches_to_run_audit(monkeypatch, svc):
    """DataService.goldset_audit() calls make_goldset.run_audit with a built Namespace."""
    from kev.console.generators import make_goldset
    calls = []
    def fake_run_audit(ns):
        calls.append((ns.a, ns.b, ns.threshold, ns.out))
        return 0
    monkeypatch.setattr(make_goldset, "run_audit", fake_run_audit)

    result = svc.goldset_audit(_req(params={"a": "x.jsonl", "b": "y.jsonl", "threshold": 0.03}),
                               on_log=lambda s: None)
    assert result == {"returncode": 0}
    assert calls == [("x.jsonl", "y.jsonl", 0.03, "")]


def test_goldset_audit_raises_invalid_when_a_missing(svc):
    """Missing 'a' raises Invalid (the same exception the stage raises)."""
    from kev.console.stages.base import Invalid
    with pytest.raises(Invalid) as excinfo:
        svc.goldset_audit(_req(params={"a": "", "b": "y.jsonl"}), on_log=lambda s: None)
    assert excinfo.value.field == "a"


# ---- precheck ---------------------------------------------------------------

def test_precheck_dispatches_to_precheck_run(monkeypatch, svc, tmp_path):
    """DataService.precheck() calls kev.console.precheck.run with built argv."""
    from kev.console import precheck
    calls = []
    def fake_run(argv):
        calls.append(argv)
        return 0
    monkeypatch.setattr(precheck, "run", fake_run)

    result = svc.precheck(_req(params={"data": "data/cv", "init_from": "jaredpalmer/kev-0.8b",
                                       "split": "calibration"}),
                          on_log=lambda s: None)
    assert result == {"returncode": 0}
    argv = calls[0]
    assert "--data" in argv and "data/cv" in argv
    assert "--split" in argv and "calibration" in argv
    assert "--init-from" in argv and "jaredpalmer/kev-0.8b" in argv


# ---- make_examples ----------------------------------------------------------

def test_make_examples_dispatches_to_make_examples_run(monkeypatch, svc, tmp_path):
    """DataService.make_examples() calls kev.console.make_examples.run with built argv."""
    from kev.console import make_examples
    calls = []
    def fake_run(argv):
        calls.append(argv)
        return 0
    monkeypatch.setattr(make_examples, "run", fake_run)

    result = svc.make_examples(_req(params={"data": "data/critical-value.jsonl", "n": 12, "seed": 3}),
                               on_log=lambda s: None)
    assert result == {"returncode": 0}
    argv = calls[0]
    assert "--data" in argv and "data/critical-value.jsonl" in argv
    assert "--n" in argv and "12" in argv
    assert "--out" in argv and "data/critical-value/examples.jsonl" in argv


def test_make_examples_raises_invalid_when_data_missing(svc):
    from kev.console.stages.base import Invalid
    with pytest.raises(Invalid) as excinfo:
        svc.make_examples(_req(params={"data": ""}), on_log=lambda s: None)
    assert excinfo.value.field == "data"
