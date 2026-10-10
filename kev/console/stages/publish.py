"""发布阶段：把训练产物推到 Hugging Face Hub（kev.publish）。

凭据走 ``HF_TOKEN``（已在 ``executor.SECRET_ENV`` 里，spawn 时注入子进程，
永不落库、不下发浏览器）。``--card`` 是 model card 的 markdown 文件路径，
由表单提供（仓库里有 ``docs/model-cards/*.md`` 作模板）。

一次性上传，进程自然退出后由 on_finished 注册产物 -> ``Persist.SUCCESS``。
Hub 远端不会有本地 ``dataset:/run:`` 产物，所以这里不声明 artifacts_out。
"""
from __future__ import annotations

from .. import paths
from .base import BuiltCommand, Invalid, JobRequest, StageSpec

STAGE = "publish"


def _python() -> str:
    import sys
    return sys.executable


def build(request: JobRequest) -> BuiltCommand:
    params = request.params
    run = params.get("run") or f"runs/{request.run_name}/checkpoint"
    repo = params.get("repo")
    if not repo:
        raise Invalid("缺少目标 repo（如 jaredpalmer/kev-0.8b）", field="repo",
                      hint="Hub repo id；私有仓用 --private 让 ensure_private 先建私有仓")
    card = params.get("card")
    if not card:
        raise Invalid("缺少 model card 的 markdown 路径", field="card",
                      hint="如 docs/model-cards/kev-0.8b.md；kev.publish 必填 --card")
    argv = [_python(), "-m", "kev.publish",
            "--run", run, "--repo", repo, "--card", card]
    if params.get("message"):
        argv += ["--message", str(params["message"])]
    if params.get("private") == "1":
        argv.append("--private")
    if params.get("replace") == "1":
        argv.append("--replace")
    if params.get("tag"):
        argv += ["--tag", str(params["tag"])]
    if params.get("revision"):
        argv += ["--revision", str(params["revision"])]
    return BuiltCommand(argv=argv, cwd=str(paths.ROOT),
                        artifacts_in=[f"run:{request.run_name}"], artifacts_out=[])


publish = StageSpec("publish", STAGE, "发布到 Hub", build,
                    outcome="在 Hub 上确认 repo 状态；远端不可公开（医疗模型）",
                    service="publish.publish")

PUBLISH_STAGES = (publish,)

__all__ = ["STAGE", "build", "publish", "PUBLISH_STAGES"]
