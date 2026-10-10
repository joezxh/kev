"""DeployService: in-process wrappers for the deploy stages.

Per docs/superpowers/plans/2026-10-09-studio-rollout-plan.md Wave B / Task B-4,
DeployService covers the four deploy-adjacent operations: image (build the
Docker image for a release), deploy (start the System One endpoint), smoke
(probe the live endpoint with 5 scenario questions), and cancel_endpoint
(kill a running endpoint Popen). The plan's split is:

- **image / smoke / cancel_endpoint**: in-process via spawn_callable. Each
  method is a short-lived operation (docker build / HTTP probe / kill
  signal) that can be wrapped in a function call. spawn_callable runs
  the function on a background thread so the FastAPI worker stays
  responsive while the operation completes.

- **deploy**: Popen preserved. `kev.serve` is a long-lived process; it
  must not be modeled as a function that returns an int. The stage's
  `service` field is left as None and the existing spawn() path applies
  unchanged. The product (endpoint:8008) is registered immediately on
  spawn, per `_spawn`'s `persist=START` handling.

image and smoke both build their own subprocess via the standard library
rather than going through the stage's argv list: the service method needs
to return a meaningful returncode to the executor's spawn_callable, which
Popen does naturally when wait()-ed. Tying these to the stage's
`build()` would mean the service has to know the stage's argv shape, and
the in-process path is meant to be independent of that shape.
"""
from __future__ import annotations

import subprocess
import threading
from typing import Callable

from kev.console.db import Store
from kev.console.stages.base import JobRequest


class DeployService:
    def __init__(self, store: Store, cancel: threading.Event,
                 gpu_lock: threading.Lock | None = None,
                 executor: "LocalExecutor | None" = None):
        self.store = store
        self.cancel = cancel
        # gpu_lock is accepted for API parity with the registry helper but
        # deploy work is host-side (no GPU): a deploy doesn't need to wait
        # for training to finish. The inference demotion in proxy_kev is
        # also unaffected — it's tied to _training_active, not to
        # gpu_lock ownership.
        self.gpu_lock = gpu_lock
        # LocalExecutor instance the app holds on app.state.executor. We
        # need it to cancel an endpoint's Popen (LocalExecutor.cancel_job
        # holds the handle map keyed by job_id). Library callers that
        # build DeployService directly without an executor leave it None
        # and cancel_endpoint will refuse to act.
        self.executor = executor

    def image(self, req: JobRequest, *, on_log: Callable[[str], None],
              on_metric: Callable[[dict], None]) -> dict:
        """Build a Docker image for the run, tagged with the served temperature.

        Mirrors the stage's `_image` argv: `docker build -t <tag>:<temperature>
        -f <dockerfile> ...`. Returns the docker build returncode. On
        non-zero, the executor marks the job failed; on zero, an
        `image:<tag>` artifact is registered (per the stage's
        `artifacts_out`).
        """
        from kev.console.stages import deploy as deploy_stage
        temperature = deploy_stage._temperature(req.params)
        tag = f"kev-{req.run_name}"
        cmd = ["docker", "build", "-t", f"{tag}:{temperature}",
               "-f", str(deploy_stage.DOCKERFILE),
               "--build-arg", f"KEV_SERVE_RUN={req.run_name}",
               "--build-arg", f"TEMPERATURE={temperature}",
               str(deploy_stage.paths.ROOT / "deploy/kev-serve")]
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if proc.stdout:
            for line in proc.stdout.splitlines():
                on_log(line)
        if proc.stderr:
            for line in proc.stderr.splitlines():
                on_log(line)
        return {"returncode": proc.returncode}

    def smoke(self, req: JobRequest, *, on_log: Callable[[str], None],
              on_metric: Callable[[dict], None]) -> dict:
        """Run the 5-scenario smoke probe against the live endpoint.

        Implemented as a single subprocess invocation of
        kev/console/scripts/smoke.py with --base-url/--out; the script
        itself does the HTTP probing. The returncode bubbles up the same
        way a Popen-driven stage would surface it.
        """
        import kev.console.services.deploy as _self
        from kev.console.stages import deploy as deploy_stage
        from pathlib import Path
        base_url = req.params.get("base_url") or f"http://127.0.0.1:{deploy_stage.SERVE_PORT}"
        out = f"runs/{req.run_name}-smoke.json"
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        cmd = [deploy_stage._python(), str(deploy_stage.SMOKE_SCRIPT),
               "--base-url", base_url, "--out", out]
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if proc.stdout:
            for line in proc.stdout.splitlines():
                on_log(line)
        if proc.stderr:
            for line in proc.stderr.splitlines():
                on_log(line)
        return {"returncode": proc.returncode}

    def cancel_endpoint(self, req: JobRequest, *, on_log: Callable[[str], None],
                        on_metric: Callable[[dict], None]) -> dict:
        """Kill the Popen serving `req.params['port']` (default 8008).

        Looks up active deploy jobs (kind=deploy) and cancels the first
        one whose artifacts_out includes `endpoint:<port>`. Returns
        `{"returncode": 0}` when at least one endpoint was canceled, 1
        when none matched (the executor's spawn_callable maps nonzero to
        failed).
        """
        port = int(req.params.get("port") or 8008)
        if self.executor is None:
            print("cancel_endpoint: no LocalExecutor bound; refusing", flush=True)
            return {"returncode": 2}
        canceled = 0
        for job in self.store.list_jobs(status="running", limit=200):
            if job.get("kind") != "deploy":
                continue
            if any(str(a) == f"endpoint:{port}" for a in (job.get("artifacts_out") or [])):
                if self.executor.cancel_job(job["id"]):
                    canceled += 1
        return {"returncode": 0 if canceled > 0 else 1}


__all__ = ["DeployService"]
