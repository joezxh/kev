"""TrainService: in-process wrapper for the train stage.

Per docs/superpowers/plans/2026-10-09-studio-rollout-plan.md Wave B / Task B-2,
TrainService replaces the train stage's Popen call with an in-process call to
kev.train.run(), so the FastAPI worker on port 8008 (which still also serves
inference) becomes the canonical "is training happening right now" signal.

Two side effects on top of the in-process call:

- **gpu_lock**: a process-wide `threading.Lock()` (passed in by the caller)
  that gates all GPU-touching services. While TrainService holds it, no
  other GPU service may run. EvalService in B-3 will acquire the same lock;
  the eval-on-CPU compare/calibrate services don't.

- **_training_active**: a process-wide `threading.Event()` (module-level).
  Set while a train call is in flight, cleared in `finally`. The /v1/*
  proxy (kev.console.app.proxy_kev) reads it on every request and returns
  503 when it's set — the training is occupying the single GPU and a
  concurrent inference would OOM. See spec ch3 §"训练期 503 降级".

- **cancel propagation**: kev.train reads a module-level `kev.train.cancel`
  Event during its step loop (set by `kev.console.executor.cancel_job`,
  which also does it for service-layer calls). We rebind that Event to
  the LocalExecutor's cancel so a cancel in either place sees the same
  flag, and we restore the previous binding on exit so a later stage that
  imports kev.train doesn't read a leftover set state from this run.
"""
from __future__ import annotations

import argparse
import threading
from typing import Callable

from kev.console.db import Store
from kev.console.stages.base import JobRequest
from kev.console.stages import train as _train_stage

# Process-wide flag read by proxy_kev to demote inference to 503 while a
# train call is in flight. One Event is shared across every TrainService
# instance the process holds, so the answer to "is training happening?" is
# a single read.
_training_active = threading.Event()


def is_training_active() -> bool:
    """True while a TrainService.train call is in flight on this process."""
    return _training_active.is_set()


class TrainService:
    def __init__(self, store: Store, cancel: threading.Event,
                 gpu_lock: threading.Lock):
        self.store = store
        self.cancel = cancel
        self.gpu_lock = gpu_lock

    def train(self, req: JobRequest, *, on_log: Callable[[str], None],
              on_metric: Callable[[dict], None]) -> dict:
        """Run kev.train.run() in-process.

        `on_log` and `on_metric` are accepted for API parity with future
        services (EvalService, DeployService, ...). This implementation does
        not yet wire them through: the executor's spawn_callable installs
        the tee harness around the callable it runs, so stdout capture
        already works the same way it does for a Popen call. Adding a
        second tee here would double-log; readers that want per-step
        metrics should subscribe to the events table the executor already
        maintains.
        """
        # Local imports: kev.train is heavy and CI-side tests mock it. Keep
        # the symbol binding in the function so the test fixture's
        # `monkeypatch.setattr("kev.console.services.train.kev_train_run",
        # ...)` pattern (and similar) sees the live reference.
        import kev.console.services.train as _self
        import kev.train  # noqa: F401 — kept so monkeypatching `kev.train`
                            # itself from tests still hits a live module.

        # 1. Acquire the GPU lock (blocks if another GPU service is running).
        with self.gpu_lock:
            _training_active.set()
            try:
                # 2. Rebind kev.train.cancel to the LocalExecutor's cancel
                #    so `executor.cancel_job(job_id)` (set on the same Event
                #    by /console/api/jobs/{id}/cancel) reaches kev.train's
                #    step loop. Restore the previous binding on exit.
                original_cancel = kev.train.cancel
                kev.train.cancel = self.cancel
                try:
                    argv_dict = self._build_argv(req)
                    args = argparse.Namespace(**argv_dict)
                    rc = _self.kev_train_run(args)
                    return {"returncode": rc, "run_dir": argv_dict.get("out")}
                finally:
                    kev.train.cancel = original_cancel
            finally:
                _training_active.clear()

    def _build_argv(self, req: JobRequest) -> dict:
        """Translate JobRequest.params into the kwarg-style dict kev.train.run
        accepts as `argparse.Namespace(**dict)`.

        The Popen path uses the stage's `build_argv()` which returns a flat
        list with `--flag value` pairs. kev.train.run takes a Namespace, so
        we mirror the same flag/decision logic here and emit a dict that
        Namespace(**dict) consumes. Keeping this in lockstep with the stage
        is a future refactor; for now the union of COMMON + VALUE_KEYS +
        ADVANCED_KEYS covers every flag the train CLI accepts.
        """
        params = req.params
        method = params.get("method", "a1")
        methods = _train_stage.methods_for(req.scenario)
        if method not in methods:
            from kev.console.stages.base import Invalid
            raise Invalid(f"未知微调方式 {method!r}", field="method",
                          hint=f"可选：{', '.join(sorted(methods))}")
        if not methods[method]["allowed"]:
            from kev.console.stages.base import Invalid
            raise Invalid(f"{req.scenario} 语义难度过高，只支持 4B 轨（方法 b）",
                          field="method", hint="见 run_matrix.FOUR_B_ONLY")
        _train_stage.check_name(req.run_name)
        out = _train_stage._resolve_out(req)
        argv: dict = {
            "data": params.get("data") or f"data/{req.scenario}/train.jsonl",
            "out": out,
        }
        for key, value in zip(_train_stage.COMMON[::2], _train_stage.COMMON[1::2]):
            argv[key.lstrip("-")] = value
        defaults = methods[method]
        for key in _train_stage.VALUE_KEYS:
            value = defaults.get(key, params.get(key))
            if value not in (None, ""):
                argv[key] = str(value)
        for key in _train_stage.ADVANCED_KEYS:
            value = params.get(key)
            if value not in (None, ""):
                argv[key] = str(value)
        if str(defaults.get("full_ft")) == "1":
            fractions = params.get("snapshot_fractions")
            if fractions and not params.get("max_steps"):
                from kev.console.stages.base import Invalid
                raise Invalid("全权重写快照需要 --max_steps 来界定优化步数", field="max_steps",
                              hint=f"kev.budget.MAX_SNAPSHOTS = {_train_stage.SNAPSHOT_LIMIT}；"
                                   "快照永不删除，磁盘要算清")
            if fractions:
                argv["max_steps"] = str(_train_stage._int(params, "max_steps"))
                argv["snapshot_fractions"] = str(fractions)
                argv["snapshot_dir"] = params.get("snapshot_dir", f"{out}-snapshots")
        return argv


# Indirection layer for tests: tests monkeypatch
# `kev.console.services.train.kev_train_run` to a fake so we don't actually
# fire up a training run (which is hours-long on a real GPU). The default
# binding is kev.train.run; the service path calls through this name.
def kev_train_run(args: argparse.Namespace) -> int:
    import kev.train
    return kev.train.run(args)


__all__ = ["TrainService", "is_training_active", "_training_active", "kev_train_run"]
