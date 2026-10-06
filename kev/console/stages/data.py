"""数据阶段：plan_size / generate / distill / goldset / split / precheck。

argv 与 `docs/medical/generators/run_matrix.py::steps()` 的**前三步**逐字一致 ——
那三步是纯本地的，可直接复用；后四步（validate/train/compare/deploy）它发的是 Modal
命令，而本设计走本地路径（spec §3.2.1），所以训练/评测/部署各自在 train.py /
eval.py / deploy.py 里自建 argv。

**真正要 import 的是 run_matrix 的常量与校验器** —— 运行名规范的唯一归属：

    from run_matrix import NAME_RE, SIZES, SCENARIOS, FOUR_B_ONLY, check_name

`check_name()` 用 `fullmatch`（run_matrix.py:45），注释里明确说明用 `match` 会错误
放行 `critical-value-0.8b-v1`（点号会一路飘到 Modal 才炸）。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .. import artifacts, paths
from ..paths import SKILL_SCRIPTS, SPECS
from .base import BuiltCommand, Conflict, Invalid, JobRequest, StageSpec

paths.ensure_medical_on_path()
from run_matrix import FOUR_B_ONLY, SCENARIOS as _SCENARIOS, SIZES, check_name  # noqa: E402

SCENARIOS = tuple(_SCENARIOS)
SPLITS = ("train", "calibration", "development")
PLAN_RE = re.compile(r"generate at least (\d+) records")
DEFAULT_INIT = SIZES["8b"][0]          # jaredpalmer/kev-0.8b
MAX_DISTILL_KEYS = 6                    # generate_data.py 的多 key 轮换上限
PLANNED_RECORDS = 787                   # 5 个 spec 都是 4 问题/记录（data-format.md §四）


def _python() -> str:
    import sys
    return sys.executable


def _spec(scenario: str) -> Path:
    if scenario not in SCENARIOS:
        raise Invalid(f"未知场景 {scenario!r}", field="scenario",
                      hint=f"可选：{', '.join(SCENARIOS)}")
    return SPECS / f"{scenario}.json"


def _int(params: dict, key: str, default: int) -> int:
    try:
        return int(params.get(key, default))
    except (TypeError, ValueError):
        raise Invalid(f"{key} 必须是整数，收到 {params.get(key)!r}", field=key) from None


def _float(params: dict, key: str, default: float) -> float:
    try:
        return float(params.get(key, default))
    except (TypeError, ValueError):
        raise Invalid(f"{key} 必须是数字，收到 {params.get(key)!r}", field=key) from None


def dataset_id(data_dir: str) -> str:
    """产物 id 里的数据集名是**相对 data/ 的**。

    `artifacts.resolve` 自己会拼 `DATA_DIR` 前缀（`dataset:cv/summary` ->
    `data/cv/summary.json`），所以这里如果传 `data/cv` 就会解析成 `data/data/cv/...`
    这种双前缀路径 —— 而 `register` 正是靠 resolve 找文件的。

    公开的：app 的闸门预检也要用它把 `data/cv` 转成产物 id。
    """
    name = str(data_dir).replace("\\", "/").strip("/")
    prefix = paths.DATA_REL.strip("/") + "/"
    return name[len(prefix):] if name.startswith(prefix) else name


# 内部别名，保持各阶段处理器里的调用点简短
_dataset_id = dataset_id


def _exists(relative: str, params: dict) -> None:
    """目录不可复用 —— 拒绝而不是自动改名。

    kev.train 与 kev.benchmark.evaluate_records 都是 `mkdir(exist_ok=False)`，
    而旧产物必须永久保留（医疗可审计性）。`params["check_exists"]` 让测试与 UI 的
    「预演」模式能强制检查；真实提交时总是检查。
    """
    if params.get("skip_exists_check"):
        return
    if params.get("check_exists") or (Path(paths.ROOT) / relative).exists():
        raise Conflict(f"{relative} 已存在；换一个名字（例如 -v2）再试",
                       hint="旧产物永久保留，可审计；控制台不替你改名")


# ---- plan_size ---------------------------------------------------------

def _plan_size(request: JobRequest) -> BuiltCommand:
    argv = [_python(), str(SKILL_SCRIPTS / "plan_size.py"), str(_spec(request.scenario)),
            "--baseline-acc", "0.75", "--json"]
    return BuiltCommand(argv=argv, cwd=str(paths.ROOT))


plan_size = StageSpec("plan_size", "data", "算记录数", _plan_size,
                      outcome="把 total_records 填进 generate 的 --n")


def parse_plan_size(stdout: str) -> dict:
    """解析 plan_size 的输出：`--json` 的 JSON，或文本形式的 'generate at least 787 records'。"""
    text = stdout.strip()
    if text.startswith("{"):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
    match = PLAN_RE.search(text)
    return {"total_records": int(match.group(1))} if match else {}


# ---- generate ----------------------------------------------------------

def _generate(request: JobRequest) -> BuiltCommand:
    _spec(request.scenario)          # 先校验场景，否则会拼出 gen_不存在.py 这种鬼命令
    if request.scenario in FOUR_B_ONLY:
        raise Invalid(f"{request.scenario} 只支持 4B 轨（语义难度过高，见 run_matrix.FOUR_B_ONLY）",
                      field="scenario", hint="本阶段只造数据，与尺寸无关；请改跑 generate 的数据侧")
    params = request.params
    data_dir = params.get("data") or f"data/{request.scenario}"
    out = f"{data_dir}.jsonl"
    _exists(out, params)
    module = request.scenario.replace("-", "_")
    argv = [_python(), str(paths.GENERATORS / f"gen_{module}.py"),
            "--n", str(_int(params, "n", PLANNED_RECORDS)), "--out", out,
            "--seed", str(_int(params, "seed", 0))]
    return BuiltCommand(argv=argv, cwd=str(paths.ROOT), artifacts_out=[f"dataset:{_dataset_id(data_dir)}"])


generate = StageSpec("generate", "data", "程序化规则合成", _generate,
                     outcome="接着跑 goldset（可选）与 split")


# ---- distill -----------------------------------------------------------

def _distill_build(request: JobRequest, *, require_schedule: bool = False) -> BuiltCommand:
    _spec(request.scenario)
    params = request.params
    keys = params.get("api_keys") or []
    if len(keys) > MAX_DISTILL_KEYS:
        raise Invalid(f"最多 {MAX_DISTILL_KEYS} 个 key（每日额度轮换用），收到 {len(keys)}",
                      field="api_keys", hint="generate_data.py 按 key 轮换，单 key 有每日上限")
    data_dir = params.get("data") or f"data/{request.scenario}"
    category = params.get("category") or request.scenario
    out = f"{data_dir}/{category}.jsonl"
    # 守护模式长驻、自己管理产出，跳过「目录已存在」预检；一次性蒸馏照旧拒绝覆盖。
    if not require_schedule:
        _exists(out, params)
    schedule = params.get("schedule")
    if require_schedule and not schedule:
        raise Invalid("守护模式必须给 --schedule HH:MM", field="schedule",
                      hint="每天蒸馏到当日份额后睡到本地 HH:MM；靠 cron/Task Scheduler 常驻")
    argv = [_python(), str(SKILL_SCRIPTS / "generate_data.py"),
            "--category", category,
            "--n", str(_int(params, "n", PLANNED_RECORDS)),
            "--model", params.get("model", "Ling-3.0-tiny"),
            "--out", out]
    if params.get("concurrency"):
        argv += ["--concurrency", str(_int(params, "concurrency", 3))]
    if schedule:
        argv += ["--schedule", schedule]
    if params.get("daily_limit"):
        argv += ["--daily-limit", str(_int(params, "daily_limit", 500000))]
    if params.get("state_dir"):
        argv += ["--state-dir", params["state_dir"]]
    env = {}
    if params.get("base_url"):
        env["KEV_GEN_BASE_URL"] = params["base_url"]
    if params.get("model"):
        env["KEV_GEN_MODEL"] = params["model"]
    # 凭据（KEV_GEN_API_KEYS）由执行器在 spawn 时从编排服务进程环境注入，永不落库
    return BuiltCommand(argv=argv, env=env, cwd=str(paths.ROOT),
                        artifacts_out=[f"dataset:{_dataset_id(data_dir)}/{category}"])


def _distill(request: JobRequest) -> BuiltCommand:
    return _distill_build(request, require_schedule=False)


distill = StageSpec("distill", "data", "LLM 蒸馏", _distill,
                    outcome="蒸馏轨只能写 label（不会写软标签 target），"
                            "「证据缺失」类样本仍须靠 generate")


def _distill_daemon(request: JobRequest) -> BuiltCommand:
    # 守护调度：--schedule HH:MM 让进程永不自然退出（睡到次日重置预算），
    # 所以产物在 spawn 后立刻注册（Persist.START），且跳过目录存在预检。
    # 产出文件随时间增长、启动时还不存在，故不声明本地产物（避免注册时空文件报错）。
    built = _distill_build(request, require_schedule=True)
    return BuiltCommand(argv=built.argv, env=built.env, cwd=built.cwd,
                        artifacts_in=built.artifacts_in, artifacts_out=[])


distill_daemon = StageSpec("distill_daemon", "distill", "蒸馏守护（按日配额）",
                           _distill_daemon, persist="start",
                           outcome="长驻蒸馏；取消即杀整棵树（executor 用 taskkill /T）")


# ---- goldset -----------------------------------------------------------

def _goldset(request: JobRequest) -> BuiltCommand:
    _spec(request.scenario)
    params = request.params
    data_dir = params.get("data") or f"data/{request.scenario}"
    out = params.get("out") or f"{data_dir}.gold.jsonl"
    _exists(out, params)
    argv = [_python(), str(paths.GENERATORS / "make_goldset.py"),
            "sample", f"{data_dir}.jsonl",
            "--n", str(_int(params, "n", 200)),
            "--seed", str(_int(params, "seed", 0)),
            "--out", out]
    return BuiltCommand(argv=argv, cwd=str(paths.ROOT),
                        artifacts_out=[f"dataset:{_dataset_id(data_dir)}.gold"])


goldset = StageSpec("goldset", "data", "抽金标", _goldset,
                    outcome="人工审校标签后，用 split --holdout 接入；金标永不进 train")


def _goldset_audit(request: JobRequest) -> BuiltCommand:
    """金标分歧审计：比对两份独立标注（通常是两个不同厂商模型对同一批 state 的标注）。

    make_goldset.py 的 audit 子命令：位置参数 a/b，--threshold 闸门（超阈值 exit 非 0，
    供 CI 拦截）。它是纯本地文件比对，不读本地 checkpoint、不写新数据集，所以
    artifacts_in/out 都为空（诊断作业，不是流水线的一环）。
    """
    params = request.params
    a = params.get("a")
    b = params.get("b")
    if not a:
        raise Invalid("audit 需要第一份标注（a）", field="a",
                      hint="两份独立厂商模型对同一批 state 的标注")
    if not b:
        raise Invalid("audit 需要第二份标注（b）", field="b",
                      hint="与 a 同源不同模型的标注，用于算分歧率")
    argv = [_python(), str(paths.GENERATORS / "make_goldset.py"), "audit", a, b]
    if params.get("out"):
        argv += ["--out", params["out"]]
    argv += ["--threshold", str(_float(params, "threshold", 0.05))]
    return BuiltCommand(argv=argv, cwd=str(paths.ROOT), artifacts_in=[], artifacts_out=[])


goldset_audit = StageSpec("goldset_audit", "goldset_audit", "金标分歧审计", _goldset_audit,
                          outcome="分歧率超阈值则 CI 可拦截；分歧样本优先进人工审校池")


# ---- split -------------------------------------------------------------

def _split(request: JobRequest) -> BuiltCommand:
    _spec(request.scenario)
    params = request.params
    data_dir = params.get("data") or f"data/{request.scenario}"
    _exists(data_dir, params)
    argv = [_python(), str(SKILL_SCRIPTS / "split_data.py"), f"{data_dir}.jsonl",
            "--out", data_dir,
            "--calibration", str(_float(params, "calibration", 0.15)),
            "--development", str(_float(params, "development", 0.15)),
            "--seed", str(_int(params, "seed", 0))]
    if params.get("holdout"):
        argv += ["--holdout", params["holdout"]]
    # summary.json 也要注册：G2/G3 读它判记录数与标签分布，漏了这两道闸永远失败
    name = _dataset_id(data_dir)
    outs = [f"dataset:{name}/summary"] + [f"dataset:{name}/{part}" for part in SPLITS]
    return BuiltCommand(argv=argv, cwd=str(paths.ROOT),
                        artifacts_in=[f"dataset:{name}"], artifacts_out=outs)


split = StageSpec("split", "data", "格式转换与划分", _split,
                  outcome="接着跑 precheck（token 超限预检）")


# ---- precheck ----------------------------------------------------------

def _precheck(request: JobRequest) -> BuiltCommand:
    params = request.params
    data_dir = params.get("data") or f"data/{request.scenario}"
    partition = params.get("split", "train")
    if partition not in SPLITS:
        raise Invalid(f"split 必须是 {SPLITS} 之一，收到 {partition!r}", field="split")
    # 写文件的路径只由 artifacts.resolve 决定。手拼 --out 会和注册 id 各走一套：
    # 作业写完 precheck-data-cv-train.json、G1 却按 id 去读 precheck-cv-train.json，
    # 症状是「缺少 precheck 报告」而不是路径错误 —— 附录 A #11 那次只修了一半。
    artifact_id = f"precheck:{_dataset_id(data_dir)}/{partition}"
    argv = [_python(), str(paths.CONSOLE_SCRIPTS / "precheck.py"),
            "--data", data_dir,
            "--init-from", params.get("init_from", DEFAULT_INIT),
            "--split", partition,
            "--out", artifacts.resolve(artifact_id)]
    return BuiltCommand(argv=argv, cwd=str(paths.ROOT),
                        artifacts_in=[f"dataset:{_dataset_id(data_dir)}/{partition}"],
                        artifacts_out=[artifact_id])


precheck = StageSpec("precheck", "data", "token 超限预检", _precheck,
                     outcome="over_limit 必须为 0 才能训练（闸门 G1）")


DATA_STAGES = (plan_size, generate, distill, distill_daemon, goldset, goldset_audit,
               split, precheck)

__all__ = ["SCENARIOS", "SPLITS", "DEFAULT_INIT", "PLANNED_RECORDS", "MAX_DISTILL_KEYS",
           "plan_size", "generate", "distill", "distill_daemon", "goldset", "goldset_audit",
           "split", "precheck",
           "parse_plan_size", "check_name", "DATA_STAGES"]
