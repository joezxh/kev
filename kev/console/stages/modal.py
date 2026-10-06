"""Modal 部署阶段：``modal deploy`` 把 kev_modal.py 推到 Modal 远端。

真实机制（kev_modal.py docstring）：``KEV_SERVE_RUN=<run> modal deploy scripts/kev_modal.py``。
所有控制都走环境变量（bake 进 image），**没有** argparse 参数，所以 argv 里只有
``modal deploy <脚本>``，配置全部放 env。

凭据：Modal SDK 用本地 ``~/.modal.toml`` auth（无环境变量）；容器内需要的
``KEV_SERVE_SECRET`` / ``KEV_HF_SECRET`` 是 Modal secret **名**，已在 executor.SECRET_ENV
里由 spawn 注入（它们只持有 KEV_API_KEY / HF_TOKEN，永不落库）。

``modal deploy`` 在 App 上线后返回退出（不是长驻子进程），所以 ``Persist.SUCCESS``；
被部署的端点在 Modal 远端，不会成为本地 ``endpoint:8008`` 产物 —— 这是与本地
``deploy`` 的已知分叉：它的在线状态要去探 ``KEV_SERVE_RUN`` 对应的 Modal URL。
"""
from __future__ import annotations

from .. import paths
from .base import BuiltCommand, Invalid, JobRequest, StageSpec

STAGE = "modal"
DEFAULT_GPU = "L4"
DEFAULT_APP = "kev-finetune"
SCRIPT = paths.SKILL_SCRIPTS / "kev_modal.py"


def _resolve(request: JobRequest) -> str:
    run = request.params.get("run") or request.run_name
    if not run:
        raise Invalid("缺少要部署的运行名（KEV_SERVE_RUN）", field="run",
                      hint="本地 runs/<name> 或 Hub id（如 jaredpalmer/kev-4b）")
    return run


def build(request: JobRequest) -> BuiltCommand:
    run = _resolve(request)
    gpu = request.params.get("gpu") or DEFAULT_GPU
    app_name = request.params.get("app_name") or DEFAULT_APP
    ref = request.params.get("ref") or ""
    env = {
        "KEV_SERVE_RUN": run,
        "KEV_SERVE_GPU": gpu,
        "KEV_APP_NAME": app_name,
    }
    if ref:
        env["KEV_REF"] = ref
    # KEV_SERVE_SECRET / KEV_HF_SECRET 是 Modal secret 名，由 SECRET_ENV 注入子进程；
    # 这里只放非敏感的部署配置（ALLOWED_ENV 白名单）。
    argv = ["modal", "deploy", str(SCRIPT)]
    return BuiltCommand(argv=argv, cwd=str(paths.ROOT), env=env,
                        artifacts_in=[f"run:{run}"], artifacts_out=[])


modal = StageSpec("modal", STAGE, "Modal 部署", build,
                  outcome="App 上线后返回；在线状态探 Modal URL（非本地 8008）")

MODAL_STAGES = (modal,)

__all__ = ["STAGE", "DEFAULT_GPU", "DEFAULT_APP", "build", "modal", "MODAL_STAGES"]
