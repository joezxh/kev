"""PublishService: in-process wrapper for the publish stage.

Per docs/superpowers/plans/2026-10-09-studio-rollout-plan.md Wave B / Task B-5,
PublishService replaces the publish stage's Popen call with an in-process
call to kev.publish.run(). The modal stage is left on Popen because
`modal deploy` shells out to a CLI binary that itself manages state on
Modal's side and isn't a function the FastAPI worker can host.

The service method's signature mirrors kev.publish.run(args: Namespace) -> int
via the indirection layer (kev_publish_run) so tests can mock the upload
without actually pushing to a Hub repo (which is a network + credential
operation).
"""
from __future__ import annotations

import argparse
import threading
from typing import Callable

from kev.console.db import Store
from kev.console.stages.base import JobRequest


class PublishService:
    def __init__(self, store: Store, cancel: threading.Event,
                 gpu_lock: threading.Lock | None = None):
        self.store = store
        self.cancel = cancel
        # gpu_lock accepted for API parity with the registry helper but
        # publish work is host-side (uploads files + Hub API calls; no GPU).
        self.gpu_lock = gpu_lock

    def publish(self, req: JobRequest, *, on_log: Callable[[str], None],
                on_metric: Callable[[dict], None]) -> dict:
        """Build a Namespace from req.params and call kev.publish.run."""
        import kev.console.services.publish as _self
        from kev.console.stages import publish as publish_stage
        params = req.params
        run = params.get("run") or f"runs/{req.run_name}/checkpoint"
        repo = params.get("repo")
        if not repo:
            from kev.console.stages.base import Invalid
            raise Invalid("缺少目标 repo（如 jaredpalmer/kev-0.8b）", field="repo",
                          hint="Hub repo id；私有仓用 --private 让 ensure_private 先建私有仓")
        card = params.get("card")
        if not card:
            from kev.console.stages.base import Invalid
            raise Invalid("缺少 model card 的 markdown 路径", field="card",
                          hint="如 docs/model-cards/kev-0.8b.md；kev.publish 必填 --card")
        fields: dict = {"run": run, "repo": repo, "card": card}
        if params.get("message"):
            fields["message"] = str(params["message"])
        if params.get("private") == "1":
            fields["private"] = True
        if params.get("replace") == "1":
            fields["replace"] = True
        if params.get("tag"):
            fields["tag"] = str(params["tag"])
        if params.get("revision"):
            fields["revision"] = str(params["revision"])
        args = argparse.Namespace(**fields)
        rc = _self.kev_publish_run(args)
        return {"returncode": rc}


def kev_publish_run(args: argparse.Namespace) -> int:
    import kev.publish
    return kev.publish.run(args)


__all__ = ["PublishService", "kev_publish_run"]
