"""镜像与部署阶段：image / deploy / smoke。

部署 = 一个**长驻作业**（`kev.serve`）。这正好符合作业模型：启动、停止、日志、
崩溃恢复全部走同一条路径，不需要另写一套生命周期管理。

关键收益：`playground/next.config.ts` 已经有 `/kev/*` -> `http://127.0.0.1:8008`
的 rewrite，所以部署一完成，**现有问答页立刻能打新模型，前端零改动**。

温度**不读 `KEV_TEMPERATURE`** —— `tests/test_conventions.py` 规定它只能经
`kev.checkpoint.LoadOptions.from_env` 读取。部署温度一律由调用方从
`calibration.json` 的 `workload_temperature` 显式传进来。
"""
from __future__ import annotations

import json as _json

from .. import db, paths
from .base import BuiltCommand, Invalid, JobRequest, Persist, StageSpec

SERVE_PORT = 8008                      # 与 playground 的 rewrite / Dockerfile 暴露端口一致
DOCKERFILE = paths.ROOT / "deploy/kev-serve/Dockerfile"
SMOKE_SCRIPT = paths.CONSOLE_SCRIPTS / "smoke.py"


def _python() -> str:
    import sys
    return sys.executable


def _temperature(params: dict) -> str:
    """服务温度必须显式给，且必须来自 calibrate。

    两条硬约束（README §七 / data-format.md §四）：
    - 绝不在 development.jsonl 上拟合温度；温度只从 calibration.json 的
      workload_temperature 取。
    - 均衡训练先验 != 真实临床先验（危急值线上约 1-3%），所以这个值只是「均衡先验下的
      切点」，上线前还要用真实流量重标定。
    """
    value = str(params.get("temperature") or "").strip()
    if not value or value == "0":
        raise Invalid(
            "缺少服务温度。先跑 calibrate，从 calibration.json 的 workload_temperature 取值再部署",
            field="temperature",
            hint="绝不在 development.jsonl 上拟合温度；均衡先验 != 真实临床先验")
    return value


def _image(request: JobRequest) -> BuiltCommand:
    temperature = _temperature(request.params)
    tag = f"kev-{request.run_name}"
    return BuiltCommand(
        argv=["docker", "build", "-t", f"{tag}:{temperature}",
              "-f", str(DOCKERFILE),
              "--build-arg", f"KEV_SERVE_RUN={request.run_name}",
              "--build-arg", f"TEMPERATURE={temperature}",
              str(paths.ROOT / "deploy/kev-serve")],
        cwd=str(paths.ROOT),
        env={"KEV_SERVE_RUN": request.run_name, "TEMPERATURE": temperature},
        artifacts_in=[f"run:{request.run_name}"],
        artifacts_out=[f"image:{tag}"])


image = StageSpec("image", "image", "构建部署镜像", _image, outcome="接着 deploy",
                 service="deploy.image")


def _deploy(request: JobRequest) -> BuiltCommand:
    temperature = _temperature(request.params)
    # 端口可配（默认 8008 不变）：双端点共存时换端口，比手改 rewrite 再部署更直接。
    port = _int_port(request.params)
    if request.params.get("busy_port"):
        raise Invalid(f"端口 {port} 已被占用；先停掉当前端点"
                      "（回滚或取消它的 deploy 作业）", field="port",
                      hint="双端点共存要换端口，并同步改 playground 的 rewrite")
    run = request.params.get("run") or f"runs/{request.run_name}"
    argv = [_python(), "-m", "kev.serve", "--run", run,
            "--port", str(port), "--temperature", temperature]
    return BuiltCommand(argv=argv, cwd=str(paths.ROOT),
                        env={"KEV_SERVE_RUN": request.run_name},
                        artifacts_in=[f"run:{request.run_name}"],
                        artifacts_out=[f"endpoint:{port}"])


def _int_port(params: dict) -> int:
    try:
        port = int(params.get("port") or SERVE_PORT)
    except (TypeError, ValueError):
        raise Invalid(f"端口必须是整数，收到 {params.get('port')!r}", field="port") from None
    if not 1 <= port <= 65535:
        raise Invalid(f"端口必须在 1-65535 内，收到 {port}", field="port")
    return port


# persist=START：kev.serve 是长驻进程，永远不会「自然完成」，产物必须在 spawn 之后
# 立刻注册，否则端点列表永远是空的。
deploy = StageSpec("deploy", "deploy", "启动 System One 端点", _deploy,
                   persist=Persist.START, outcome="接着 smoke；现有问答页（/）已经能打这个端点")


def _smoke(request: JobRequest) -> BuiltCommand:
    base_url = request.params.get("base_url") or f"http://127.0.0.1:{SERVE_PORT}"
    out = f"runs/{request.run_name}-smoke.json"
    argv = [_python(), str(SMOKE_SCRIPT), "--base-url", base_url, "--out", out]
    return BuiltCommand(argv=argv, cwd=str(paths.ROOT),
                        artifacts_in=[f"endpoint:{SERVE_PORT}"],
                        artifacts_out=[f"smoke:{request.run_name}"])


smoke = StageSpec("smoke", "deploy", "冒烟测试（5 场景各 1 例）", _smoke,
                  outcome="看 p 分布与 argmax；别只看分数，形状不对说明权重或字段名有问题",
                  service="deploy.smoke")

DEPLOY_STAGES = (image, deploy, smoke)

# Smoke probes 的真实来源是 `paths.SPECS/*.json` 的 `smoke_probe` 字段。
# Wave B 把旧硬编码 list 改成 DB-projected 入口，但 `Store.list_smoke_probes`
# 还没有实现；这里用一份从 spec 文件直读的快照作为 back-compat 入口，
# 待 DB projection 就绪后切到 store 调用（services/smoke.run_from_db）。
SMOKE_SPEC_DIR = paths.SPECS


def _load_smoke_probes() -> list:
    """从 paths.SPECS/*.json 读 smoke_probe 字段，组成原 list 结构。

    每条形如 {scenario, state, questions, expected_label}：与
    services/smoke.run_from_db 期望的 `probe` 一致。
    """
    out = []
    if not SMOKE_SPEC_DIR.is_dir():
        return out
    for spec_path in sorted(SMOKE_SPEC_DIR.glob("*.json")):
        try:
            data = _json.loads(spec_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        probe = data.get("smoke_probe")
        if not probe:
            continue
        out.append({
            "scenario": spec_path.stem,
            "state": probe.get("state", {}),
            "questions": probe.get("questions", []),
            "expected_label": probe.get("expected_label", {}),
        })
    return out


# 启动时一次性物化（spec 文件通常 ≤ 几十个）。调用方只读不改；新增场景需要重启 master。
SMOKE_PROBES: list = _load_smoke_probes()

__all__ = ["SERVE_PORT", "DOCKERFILE", "SMOKE_SCRIPT",
           "image", "deploy", "smoke", "DEPLOY_STAGES", "SMOKE_PROBES"]
