"""作业类型注册表：kind -> StageSpec。

14 种作业。`StageSpec.build` 只组装 argv，不含业务逻辑。
`persist` 决定产物何时注册（见 base.Persist）：绝大多数是进程自然退出后，
只有 deploy 是长驻进程、必须在 spawn 后立刻注册。

血缘关系名由 `artifacts.RELATION` 按作业 kind 查 —— 这里**不**再维护一份映射（单一归属）。
"""
from . import data as _data
from . import deploy as _deploy
from . import eval as _eval
from . import modal as _modal
from . import publish as _publish
from . import train as _train
from .base import BuiltCommand, Conflict, Invalid, JobRequest, Persist, StageSpec

REGISTRY = {}
for _spec in (*_data.DATA_STAGES, *_train.TRAIN_STAGES, *_eval.EVAL_STAGES,
              *_deploy.DEPLOY_STAGES, *_publish.PUBLISH_STAGES, *_modal.MODAL_STAGES):
    if _spec.kind in REGISTRY:
        raise ValueError(f"duplicate stage kind {_spec.kind!r}")
    REGISTRY[_spec.kind] = _spec

__all__ = ["REGISTRY", "StageSpec", "BuiltCommand", "JobRequest", "Invalid",
           "Conflict", "Persist"]
