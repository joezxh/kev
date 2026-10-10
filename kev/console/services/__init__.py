"""Service layer for kev.console stages (Wave B of the studio rollout plan).

The service layer wraps the console-owned business functions so the stage handlers
(stages/data.py etc.) can call them in-process instead of spawning a subprocess.
Stages whose business code lives in a different repo (e.g. skills/kev-finetune/
scripts/* for plan_size / distill / split) keep their Popen path and are not in
this package.

See docs/superpowers/plans/2026-10-09-studio-rollout-plan.md, Wave B for the
full design; spec ch2..ch5 have the per-stage service shape.
"""
from __future__ import annotations

import threading

from .data import DataService
from .train import TrainService, is_training_active
from .eval import EvalService
from .deploy import DeployService
from .publish import PublishService


# Service registry: "package.method" -> (module, attribute).
# Adding a new service (eval/deploy/publish in later Wave B steps) is a
# one-line edit here. The lookup is by the dotted suffix that stages advertise
# in `StageSpec.service` (e.g. "data.generate"). Dispatch is then a one-arg
# getattr on a per-process service instance built here.
_REGISTRY: dict[str, type] = {
    "data.generate": DataService,
    "data.goldset": DataService,
    "data.goldset_audit": DataService,
    "data.precheck": DataService,
    "data.make_examples": DataService,
    "data.distill": DataService,
    "train.train": TrainService,
    "eval.baseline": EvalService,
    "eval.benchmark": EvalService,
    "eval.compare": EvalService,
    "eval.calibrate": EvalService,
    "deploy.image": DeployService,
    "deploy.smoke": DeployService,
    "deploy.cancel_endpoint": DeployService,
    "publish.publish": PublishService,
}


def get_service(method_name: str, *, store, cancel: threading.Event,
                gpu_lock: threading.Lock | None = None,
                executor=None):
    """Return an instance of the service that owns `method_name`.

    `method_name` is the dotted form stages store in `StageSpec.service`
    ("<package>.<method>"). The instance is freshly constructed per call —
    services are stateless except for the store/cancel refs they were built
    with, so a new instance is cheaper than remembering a shared one and
    matches the per-request lifetime of the executor's callables.

    GPU services (TrainService, EvalService) accept an additional
    `gpu_lock`; DeployService accepts the LocalExecutor (for
    cancel_endpoint to find the live Popen handle); CPU services ignore
    both. The caller (kev.console.app) keeps one process-wide lock and
    one executor and hands them in unconditionally.
    """
    cls = _REGISTRY.get(method_name)
    if cls is None:
        raise KeyError(f"no service registered for {method_name!r}")
    if cls in (TrainService, EvalService):
        if gpu_lock is None:
            raise ValueError(f"{cls.__name__} requires gpu_lock")
        return cls(store=store, cancel=cancel, gpu_lock=gpu_lock)
    if cls is DeployService:
        return cls(store=store, cancel=cancel, gpu_lock=gpu_lock, executor=executor)
    return cls(store=store, cancel=cancel)


__all__ = ["DataService", "TrainService", "EvalService", "DeployService",
           "PublishService", "is_training_active", "get_service"]
