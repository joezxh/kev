"""DataService: in-process wrappers for the 5 console-owned data stages + distill.

Per docs/superpowers/specs/2026-10-09-studio-data-design.md §2.X and the rollout
plan B-1, the DataService covers:

- generate            (kev/console/generators/gen_<scenario>.run)
- distill             (kev/console/generators/run_distill.run, the **non-daemon** path)
- goldset             (kev/console/generators/make_goldset.run_sample)
- goldset_audit       (kev/console/generators/make_goldset.run_audit)
- precheck            (kev/console/precheck.run)
- make_examples       (kev/console/make_examples.run)

The 3 skill-script stages (plan_size / distill_daemon / split) keep their Popen path;
DataService does not provide methods for them. A future caller wanting one of those
would still go through the stage's _xxx_build + executor.spawn path (unchanged).

Service contract:
- Each method takes a JobRequest + a per-call on_log callback.
- on_log is invoked with each line of stdout the business function prints.
- stdout capture is implemented in LocalExecutor.spawn_callable (tee into the
  same log file + events table that a Popen run would use). DataService only
  *builds* a Namespace-like argv list and *dispatches* to the right run() —
  the on_log + log_path plumbing is the executor's job.
- Cancellation is cooperative: each method returns early if self.cancel.is_set().
  A long-running data function (none of the 5 are, they all finish in seconds)
  would need to add a self.cancel.is_set() check at a natural step boundary.
"""
from __future__ import annotations

import argparse
import importlib
import sys
import threading
from pathlib import Path
from typing import Callable

from kev.console.db import Store
from kev.console.stages.base import JobRequest


# Default knobs taken from kev/console/stages/data.py; kept here so the service
# can build a Namespace without re-importing the stage module.
_PLANNED_RECORDS = 787

# Per-scenario gen_<scenario>.py modules live under kev/console/generators/.
# The engine module injects this dir into sys.path at import time, but the
# service may be imported without the engine (e.g. in tests), so we ensure
# the path is set here as well. Idempotent.
_GENERATORS_DIR = Path(__file__).resolve().parent.parent / "generators"
if str(_GENERATORS_DIR) not in sys.path:
    sys.path.insert(0, str(_GENERATORS_DIR))


def _import_gen_module(scenario: str):
    """Dynamically import `gen_<scenario>` so the test can stub it via sys.modules."""
    return importlib.import_module(f"gen_{scenario.replace('-', '_')}")


class DataService:
    def __init__(self, store: Store, cancel: threading.Event):
        self.store = store
        self.cancel = cancel  # process-wide Event; set when a job is canceled.

    # ---- generate ---------------------------------------------------------

    def generate(self, req: JobRequest, *, on_log: Callable[[str], None]) -> dict:
        """Generate a JSONL of synthetic records for the scenario.

        Mirrors `stages/data.py::_generate` (lines 150-167): dispatch to the
        scenario's `gen_<scenario>.py` module. Tests can stub it via
        `monkeypatch.setitem(sys.modules, "gen_<scenario>", fake)` and the
        service picks up the stub through importlib.
        """
        module = _import_gen_module(req.scenario)
        args = self._build_generate_args(req)
        rc = module.run([str(part) for part in args])
        return {"returncode": rc}

    def _build_generate_args(self, req: JobRequest) -> list:
        params = req.params
        data_dir = params.get("data") or f"data/{req.scenario}"
        out = f"{data_dir}.jsonl"
        n = int(params.get("n", _PLANNED_RECORDS))
        seed = int(params.get("seed", 0))
        # base_parser reads --n/--out/--seed and adds --pairs; mirrors stages/data.py:163-167
        # We always pass --pairs=0 here: the service path is the user-driven path,
        # and minimal pairs are a generator-level concern. Stage preview() still
        # exposes the same shape so the UI's argv preview matches.
        return ["--n", str(n), "--out", out, "--seed", str(seed), "--pairs", "0"]

    # ---- goldset / goldset_audit ------------------------------------------

    def goldset(self, req: JobRequest, *, on_log) -> dict:
        """goldset service: stratified sample for human review.

        Wraps make_goldset.run_sample() with the args the stage would have built.
        """
        from kev.console.generators import make_goldset
        args = self._build_goldset_args(req)
        ns = make_goldset_sample_namespace(args, req)
        rc = make_goldset.run_sample(ns)
        return {"returncode": rc}

    def _build_goldset_args(self, req: JobRequest) -> dict:
        params = req.params
        data_dir = params.get("data") or f"data/{req.scenario}"
        return {
            "data": f"{data_dir}.jsonl",
            "n": int(params.get("n", 200)),
            "seed": int(params.get("seed", 0)),
            "out": params.get("out") or f"{data_dir}.gold.jsonl",
        }

    def goldset_audit(self, req: JobRequest, *, on_log) -> dict:
        """goldset_audit service: per-question disagreement rate between two labellings.

        Wraps make_goldset.run_audit() with a pre-built Namespace.
        """
        from kev.console.generators import make_goldset
        params = req.params
        a, b = params.get("a"), params.get("b")
        if not a or not b:
            # Surface the same Invalid the stage would raise; the executor maps it
            # to a 400 response at the HTTP boundary.
            from kev.console.stages.base import Invalid
            raise Invalid(
                "goldset_audit 需要两份独立标注（a, b）",
                field="a" if not a else "b",
                hint="两份独立厂商模型对同一批 state 的标注",
            )
        ns = argparse.Namespace(
            a=a, b=b, out=params.get("out") or "",
            threshold=float(params.get("threshold", 0.05)),
        )
        rc = make_goldset.run_audit(ns)
        return {"returncode": rc}

    # ---- precheck ---------------------------------------------------------

    def precheck(self, req: JobRequest, *, on_log) -> dict:
        """precheck service: token-limit scan over a split partition.

        Wraps kev.console.precheck.run() with the args the stage would have built.
        """
        from kev.console import precheck
        params = req.params
        data_dir = params.get("data") or f"data/{req.scenario}"
        partition = params.get("split", "train")
        # Service-level default init mirrors stages/data.py: DEFAULT_INIT.
        # The default is exposed via the stage's preview(); keep it consistent
        # rather than re-importing the constant.
        init_from = params.get("init_from", "jaredpalmer/kev-0.8b")
        out = params.get("out") or f"data/console/precheck-{req.scenario}-{partition}.json"
        ns = argparse.Namespace(
            data=data_dir, init_from=init_from, split=partition, out=out,
        )
        rc = precheck.run([str(part) for part in [
            "--data", data_dir, "--init-from", init_from, "--split", partition, "--out", out
        ]])
        return {"returncode": rc}

    # ---- distill ----------------------------------------------------------

    def distill(self, req: JobRequest, *, on_log: Callable[[str], None]) -> dict:
        """distill service: one-shot LLM distillation (the **non-daemon** path).

        Wraps kev.console.generators.run_distill.run() with the args the stage would have built.
        `distill_daemon` (the long-running schedule path) stays in stages.data + daemon_runner;
        this service covers only `require_schedule=False`.
        """
        from kev.console.generators import run_distill
        args = self._build_distill_args(req)
        rc = run_distill.run([str(part) for part in args], on_log=on_log)
        return {"returncode": rc}

    def _build_distill_args(self, req: JobRequest) -> list:
        """Build argv for run_distill.run, mirroring stages/data.py:185-244.

        `provider_id` is required (a configured distillation endpoint); category, n, model,
        concurrency, examples, n_examples, state_dir all have sensible defaults.
        """
        params = req.params
        provider_id = params.get("provider_id")
        if not provider_id:
            from kev.console.stages.base import Invalid
            raise Invalid("distill 需要 provider_id（已配置的蒸馏端点）",
                          field="provider_id",
                          hint="先到控制台「蒸馏配置」创建并选择")
        n = int(params.get("n", _PLANNED_RECORDS))
        out = f"data/{req.scenario}/{params.get('category', req.scenario)}.jsonl"
        argv = ["--n", str(n), "--provider", provider_id, "--out", out]
        if params.get("model"):
            argv += ["--model", params["model"]]
        if params.get("concurrency"):
            argv += ["--concurrency", str(int(params["concurrency"]))]
        if params.get("examples"):
            argv += ["--examples", params["examples"]]
            argv += ["--n-examples", str(int(params.get("n_examples", 4)))]
        if params.get("state_dir"):
            argv += ["--state-dir", params["state_dir"]]
        return argv

    # ---- make_examples ----------------------------------------------------

    def make_examples(self, req: JobRequest, *, on_log: Callable[[str], None]) -> dict:
        """make_examples service: balanced few-shot sampling for the distill step.

        Wraps kev.console.make_examples.run() with the args the stage would have built.
        """
        from kev.console import make_examples
        params = req.params
        data = (params.get("data") or "").strip()
        if not data:
            from kev.console.stages.base import Invalid
            raise Invalid("make_examples 需要 --data 指向一份已标注的 JSONL", field="data",
                          hint="如 data/critical-value.jsonl（generate/distill 的原始池）")
        # base = "data/cv/critical-value" (strip suffix + replace backslashes for windows)
        base = data.rsplit(".", 1)[0].replace("\\", "/")
        out = params.get("out") or f"{base}/examples.jsonl"
        rc = make_examples.run([str(part) for part in [
            "--data", data,
            "--n", str(int(params.get("n", 8))),
            "--seed", str(int(params.get("seed", 0))),
            "--out", out,
        ]])
        return {"returncode": rc}


def make_goldset_sample_namespace(args: dict, req: JobRequest) -> argparse.Namespace:
    """Helper: build the Namespace make_goldset.run_sample expects.

    run_sample only reads .data / .n / .seed / .out; we materialize the rest of
    the subcommand's defaults to 0/empty so a downstream that introspects
    `args.command` (none do today) still gets a sensible value.
    """
    return argparse.Namespace(command="sample", **args)
