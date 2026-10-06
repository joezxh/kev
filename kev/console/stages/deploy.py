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

from .. import paths
from .base import BuiltCommand, Invalid, JobRequest, Persist, StageSpec

SERVE_PORT = 8008                      # 与 playground 的 rewrite / Dockerfile 暴露端口一致
DOCKERFILE = paths.ROOT / "deploy/kev-serve/Dockerfile"
SMOKE_SCRIPT = paths.CONSOLE_SCRIPTS / "smoke.py"

# 5 个场景各 1 例冒烟探针。state 的字段名与 docs/medical/data-format.md 的
# state_example 严格对齐 —— 字段名对模型可见，跨记录必须一致，改字段名等于换了一个任务。
SMOKE_PROBES = [
    {"scenario": "critical-value", "state": {
        "patient": "male 67", "context": "routine chemistry panel, no symptoms reported",
        "labs": "K+ 6.2 mmol/L, Cr 98 umol/L", "ref_ranges_included": "yes",
        "missing_context": "no symptoms reported"},
     "questions": [{"qid": "is_critical", "type": "noul",
                    "instructions": "该报告中的任一检验项目是否触及危急值（需要立即临床干预）？"}]},
    {"scenario": "triage", "state": {
        "patient": "female 34, gestation 28 weeks", "channel": "outpatient",
        "chief_complaint": "规律腹痛 3 小时", "duration": "3 hours",
        "accompanying": "no fever, no vaginal bleeding", "history": "G2P1",
        "vitals": "BP 118/74, HR 88", "red_flags": "none"},
     "questions": [{"qid": "immediate_human", "type": "noul",
                    "instructions": "该患者是否需要立即人工分诊（而非继续等待）？"}]},
    {"scenario": "medication-review", "state": {
        "patient": "female 62, eGFR 24", "state_flags": "renal impairment",
        "allergies": "penicillin (rash)", "current_meds": "amoxicillin 500mg tid",
        "current_rx": "amoxicillin 500mg tid", "days_on_drug": 6, "indication": "sinusitis"},
     "questions": [{"qid": "needs_pharmacist", "type": "noul",
                    "instructions": "该用药是否需要药师介入复核？"}]},
    {"scenario": "nursing-quality", "state": {
        "patient": "male 71, bed 12", "ward": "cardiology", "nursing_level": "level 2",
        "check_point": "pressure ulcer prevention, repositioning",
        "observed": "no repositioning documented for 6 hours",
        "dependencies": "none", "risk_scores": "Braden 12"},
     "questions": [{"qid": "reportable", "type": "noul",
                    "instructions": "该护理缺陷是否应上报？（质量问题而非个人疏忽）"}]},
    {"scenario": "icd-coding", "state": {
        "patient": "female 58", "length_of_stay_days": 9, "primary_dx": "J18.9",
        "secondary_dx": "E11.9, I10", "procedure": "none",
        "key_findings": "community-acquired pneumonia",
        "past_history": "type 2 diabetes, hypertension",
        "clinical_course": "improved on antibiotics"},
     "questions": [{"qid": "needs_coder", "type": "noul",
                    "instructions": "该编码是否需要编码员人工复核？"}]},
]


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


image = StageSpec("image", "image", "构建部署镜像", _image, outcome="接着 deploy")


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
                  outcome="看 p 分布与 argmax；别只看分数，形状不对说明权重或字段名有问题")

DEPLOY_STAGES = (image, deploy, smoke)

__all__ = ["SERVE_PORT", "DOCKERFILE", "SMOKE_SCRIPT", "SMOKE_PROBES",
           "image", "deploy", "smoke", "DEPLOY_STAGES"]
