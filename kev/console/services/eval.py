"""EvalService: in-process wrappers for the 4 eval stages.

Per docs/superpowers/plans/2026-10-09-studio-rollout-plan.md Wave B / Task B-3,
EvalService replaces the baseline/benchmark/compare/calibrate stages' Popen
calls with in-process calls to kev.{benchmark,compare,calibrate}.run(). Two
tiers of work share the service, distinguished by their GPU footprint:

- **GPU eval (baseline, benchmark)**: each acquires the process-wide
  `gpu_lock` (the same lock TrainService uses) so a single-GPU box never has
  training and a benchmark going at the same time. They do not flip the
  process-wide `_training_active` flag (the proxy's 503 gate is train-only —
  eval is a one-shot GPU op, the proxy gate would just look like flaky
  availability to a caller). Plan §B-3 leaves the gate scoped to train.

- **CPU eval (compare, calibrate)**: no lock, no GPU. compare is paired
  bootstrap over already-written report.json files; calibrate is a temperature
  fit on already-written rows.json. They run instantly and can sit alongside
  any GPU service.

Each method follows the same shape as DataService: build a Namespace from
`req.params` (mirroring the stage's `_benchmark_like` / `_compare` /
`_calibrate` builders), call the matching `kev.*.run(args)`, return
`{"returncode": rc}`. The actual `_benchmark_like` is reused where
appropriate (baseline + benchmark share most flags); compare and calibrate
build their own Namespaces since their argument shapes are tiny.
"""
from __future__ import annotations

import argparse
import threading
from typing import Callable

from kev.console.db import Store
from kev.console.stages.base import JobRequest


class EvalService:
    def __init__(self, store: Store, cancel: threading.Event,
                 gpu_lock: threading.Lock):
        self.store = store
        self.cancel = cancel
        self.gpu_lock = gpu_lock

    # ---- GPU eval (baseline, benchmark) --------------------------------

    def _gpu_eval(self, kind: str, req: JobRequest, *, on_log: Callable[[str], None],
                  on_metric: Callable[[dict], None]) -> dict:
        """Shared body for baseline and benchmark. Acquires gpu_lock; does not
        touch _training_active (that's a train-only flag — see module docstring).
        """
        import kev.console.services.eval as _self
        from kev.console.stages import eval as eval_stage
        from kev.console.stages.eval import _python as _stage_python
        # Local imports so test fixtures that mock kev.console.services.eval.<func>
        # see the live reference, and so the heavy kev.benchmark module isn't
        # loaded on every EvalService construction (only at run time).
        import kev.benchmark

        with self.gpu_lock:
            args = self._build_benchmark_args(kind, req)
            original_cancel = kev.benchmark.cancel
            kev.benchmark.cancel = self.cancel
            try:
                rc = _self.kev_benchmark_run(args)
                return {"returncode": rc}
            finally:
                kev.benchmark.cancel = original_cancel

    def baseline(self, req: JobRequest, *, on_log: Callable[[str], None],
                 on_metric: Callable[[dict], None]) -> dict:
        return self._gpu_eval("baseline", req, on_log=on_log, on_metric=on_metric)

    def benchmark(self, req: JobRequest, *, on_log: Callable[[str], None],
                  on_metric: Callable[[dict], None]) -> dict:
        return self._gpu_eval("benchmark", req, on_log=on_log, on_metric=on_metric)

    def _build_benchmark_args(self, kind: str, req: JobRequest) -> argparse.Namespace:
        """Mirror of stages.eval._benchmark_like; emit a Namespace.

        Why duplicate rather than call the stage's builder: that builder
        returns a flat list with `python -m kev.benchmark` prepended. The
        service path passes a Namespace directly to kev.benchmark.run. The
        rule is the same one used in TrainService: keep the service path
        independent of the stage's argv shape.
        """
        from kev.console.stages import eval as eval_stage
        params = req.params
        device = params.get("device", "cuda")
        fields: dict = {"device": device}
        if kind == "benchmark":
            out = params.get("out") or f"runs/{req.run_name}-eval"
            fields["out"] = out
            if params.get("remote"):
                fields["remote"] = params["remote"]
                if params.get("remote_model"):
                    fields["remote_model"] = params["remote_model"]
                if params.get("remote_concurrency"):
                    fields["remote_concurrency"] = str(params["remote_concurrency"])
            else:
                run = params.get("run") or f"runs/{req.run_name}"
                fields["run"] = run
            if params.get("suite"):
                fields["suite"] = params["suite"]
                if params.get("split"):
                    fields["split"] = params["split"]
            else:
                fields["data"] = eval_stage._partition(req)
            if params.get("allow_test") == "1":
                fields["allow_test"] = True
            if params.get("date_facts") == "1":
                fields["date_facts"] = True
            if params.get("rotations"):
                fields["rotations"] = str(params["rotations"])
        else:  # baseline
            run = params.get("baseline") or eval_stage.DEFAULT_BASELINE
            out = params.get("out") or f"runs/{req.run_name}-baseline-eval"
            fields["run"] = run
            fields["data"] = eval_stage._partition(req)
            fields["out"] = out
        return argparse.Namespace(**fields)

    # ---- CPU eval (compare, calibrate) ---------------------------------

    def compare(self, req: JobRequest, *, on_log: Callable[[str], None],
                on_metric: Callable[[dict], None]) -> dict:
        import kev.console.services.eval as _self
        import kev.compare
        from kev.console.stages import eval as eval_stage
        params = req.params
        public = params.get("public") == "1"
        candidate = params.get("candidate") or f"runs/{req.run_name}-eval"
        reference = params.get("reference") or f"runs/{req.run_name}-baseline-eval"
        if candidate == reference:
            from kev.console.stages.base import Invalid
            raise Invalid("candidate 与 reference 不能是同一个目录", field="candidate",
                          hint="G4 需要真实的两次打分对比")
        out = params.get("out") or (f"runs/{req.run_name}-compare-public" if public
                                    else f"runs/{req.run_name}-compare")
        # Reuse the same precheck the stage uses: incompatible suite_sha256
        # would otherwise blow up inside kev.compare.run as a ValueError.
        reason = eval_stage.suite_hash_mismatch(candidate, reference)
        if reason:
            from kev.console.stages.base import Invalid
            raise Invalid(f"compare 两侧不可比：{reason}", field="candidate",
                          hint="两侧必须用同一份数据；--data 模式下 suite_sha256 是数据文件的内容哈希")
        args = argparse.Namespace(
            candidate=candidate, reference=reference, out=out,
        )
        rc = _self.kev_compare_run(args)
        return {"returncode": rc}

    def calibrate(self, req: JobRequest, *, on_log: Callable[[str], None],
                  on_metric: Callable[[dict], None]) -> dict:
        import kev.console.services.eval as _self
        import kev.calibrate
        from pathlib import Path
        params = req.params
        rows = params.get("rows") or f"runs/{req.run_name}-eval/rows.json"
        if not rows.endswith("rows.json"):
            from kev.console.stages.base import Invalid
            raise Invalid("温度拟合需要 kev.benchmark 写出的 rows.json", field="rows",
                          hint="kev.calibrate 要求 rows 带 logits + inference_temperature")
        out = params.get("out") or str(Path(rows).parent / "calibration.json")
        args = argparse.Namespace(rows=rows, out=out)
        rc = _self.kev_calibrate_run(args)
        return {"returncode": rc}


# Indirection layer for tests: tests monkeypatch
# kev.console.services.eval.{kev_benchmark_run,kev_compare_run,kev_calibrate_run}
# to fakes so we don't actually run a benchmark (which is minutes on a real
# GPU). The default binding is the matching kev.*.run.

def kev_benchmark_run(args: argparse.Namespace) -> int:
    import kev.benchmark
    return kev.benchmark.run(args)


def kev_compare_run(args: argparse.Namespace) -> int:
    import kev.compare
    return kev.compare.run(args)


def kev_calibrate_run(args: argparse.Namespace) -> int:
    import kev.calibrate
    return kev.calibrate.run(args)


__all__ = ["EvalService", "kev_benchmark_run", "kev_compare_run", "kev_calibrate_run"]
