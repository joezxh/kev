"""评测阶段：baseline / benchmark / compare / calibrate。

**为什么必须有 baseline + compare**（spec §7.1.1，实测核对得出，不是推测）：
- `kev/benchmark.py` 的 report.json 里**没有** bootstrap 键 —— 它写的是 `paired_flip`
  （`benchmark.py:89`，来自 `kev.contrastive`）。
- 配对 bootstrap 的 CI 只能由 `kev.compare` 产出：`comparison.paired.acc` →
  `kev.metrics.paired_bootstrap`，返回 `{ci95: [lo, hi], macro_acc_delta, ...}`
  （`compare.py:44`、`metrics.py:423-426`）。
- `regression` 段只存在于 `kev_modal.py` 的 Modal 产物（`kev/` 全目录零命中）。

所以「增益真实」（G4）与「公开数据回归」（G6）这两道闸，本地一律走
**baseline + benchmark + compare** 三件套；单次 `kev.benchmark` 判不了。

**compare 的硬前提**：两份 report.json 的 `suite_sha256` 必须一致，否则 `compare.py:39-40`
直接 `ValueError`。`--data` 模式下它 = `digest(数据文件)`，而 `kev.suite.digest` 是
**按文件内容**算的 sha256（`suite.py:113-117`）—— 所以不同路径的同一份 development.jsonl
也能配对，但换 suite 就会被拒。控制台把这条提前拦成 `conflict`，而不是让子进程抛。
"""
from __future__ import annotations

from pathlib import Path

from .. import paths
from .base import BuiltCommand, Conflict, Invalid, JobRequest, StageSpec

DEFAULT_BASELINE = "jaredpalmer/kev-0.8b"
PUBLIC_SUITE = "evals/v7/decision-v7"
SPLITS = ("train", "calibration", "development")


def _python() -> str:
    import sys
    return sys.executable


def _partition(request: JobRequest) -> str:
    """要打分的那个分区文件。baseline 与 benchmark **必须**指向同一个文件，
    否则 suite_sha256 不同、compare 拒绝（见模块 docstring）。"""
    data_dir = request.params.get("data") or f"data/{request.scenario}"
    split = request.params.get("split", "development")
    if split not in SPLITS:
        raise Invalid(f"split 必须是 {SPLITS} 之一，收到 {split!r}", field="split")
    return f"{data_dir}/{split}.jsonl"


def suite_hash_mismatch(candidate: str, reference: str) -> str:
    """预检 compare 两侧的 suite_sha256 是否一致；不一致返回可读的原因，一致返回 ""。

    `kev/compare.py:39-40` 会因为不一致直接 `ValueError`。放在这里预检是为了让它变成
    409 conflict + 可读提示，而不是子进程抛出来的裸栈。

    为什么可比：baseline 与 benchmark 跑的是**同一份 development.jsonl**，而
    `--data` 模式下 `report.suite_sha256 = digest(数据文件)`，`kev.suite.digest` 按文件
    **内容**算 sha256（suite.py:113-117）——所以哪怕路径不同，只要内容一致就能配对。
    """
    from kev.suite import read_json

    hashes = []
    for label, directory in (("candidate", candidate), ("reference", reference)):
        report = Path(paths.ROOT) / directory / "report.json"
        if not report.is_file():
            return ""                      # 产物还没生成，交给 compare 自己报错
        try:
            value = read_json(report).get("suite_sha256")
        except (OSError, ValueError):
            return ""
        if not value:
            return ""                      # 同样，缺 hash 时不预判
        hashes.append((label, value))
    if hashes[0][1] != hashes[1][1]:
        return (f"{hashes[0][0]} 的 suite_sha256={hashes[0][1][:12]}… 与 "
                f"{hashes[1][0]} 的 {hashes[1][1][:12]}… 不一致")
    return ""


def _benchmark_like(kind: str):
    def build(request: JobRequest) -> BuiltCommand:
        params = request.params
        device = params.get("device", "cuda")
        if kind == "benchmark":
            # 开发集打分（G4/G5 的证据来源）。runbook §七 7.4 项 4 的高级选项在这里接。
            out = params.get("out") or f"runs/{request.run_name}-eval"
            name = request.run_name
            argv = ["-m", "kev.benchmark", "--out", out, "--device", device]
            if params.get("remote"):
                # 远程打分：对一个 System One 兼容端点打 development 分区，不读本地 checkpoint。
                argv += ["--remote", params["remote"]]
                if params.get("remote_model"):
                    argv += ["--remote-model", params["remote_model"]]
                if params.get("remote_concurrency"):
                    argv += ["--remote-concurrency", str(params["remote_concurrency"])]
                artifacts_in: list = []
            else:
                run = params.get("run") or f"runs/{request.run_name}"
                argv += ["--run", run]
                artifacts_in = [f"run:{request.run_name}"]
            # --data（本地分区文件）与 --suite（冻结 suite）互斥。
            if params.get("suite"):
                argv += ["--suite", params["suite"]]
                if params.get("split"):
                    argv += ["--split", params["split"]]
            else:
                argv += ["--data", _partition(request)]
            if params.get("allow_test") == "1":
                argv.append("--allow-test")          # 读锁定的 test 分区
            if params.get("date_facts") == "1":
                argv.append("--date_facts")          # 打分前对 state 套 with_date_facts
            if params.get("rotations"):
                argv += ["--rotations", str(params["rotations"])]
            return BuiltCommand(argv=[_python()] + argv, cwd=str(paths.ROOT),
                                artifacts_in=artifacts_in, artifacts_out=[f"eval:{name}"])
        # baseline：零样本对照，固定打同一份 development 文件（compare 要靠 suite_sha256 一致）。
        run = params.get("baseline") or DEFAULT_BASELINE
        out = params.get("out") or f"runs/{request.run_name}-baseline-eval"
        name = f"{request.run_name}-baseline"
        argv = ["-m", "kev.benchmark", "--run", run, "--data", _partition(request),
                "--out", out, "--device", device]
        return BuiltCommand(argv=[_python()] + argv, cwd=str(paths.ROOT),
                            artifacts_in=[f"run:{run}"], artifacts_out=[f"eval:{name}"])
    return build


benchmark = StageSpec("benchmark", "benchmark", "开发集打分", _benchmark_like("benchmark"),
                      outcome="接着跑 compare（配对 CI 在这里产生）")
baseline = StageSpec("baseline", "benchmark", "基线打分（零样本对照）",
                     _benchmark_like("baseline"),
                     outcome="与 benchmark 用同一份 development.jsonl，然后 compare")


def _compare(request: JobRequest) -> BuiltCommand:
    params = request.params
    candidate = params.get("candidate") or f"runs/{request.run_name}-eval"
    reference = params.get("reference") or f"runs/{request.run_name}-baseline-eval"
    if candidate == reference:
        raise Invalid("candidate 与 reference 不能是同一个目录", field="candidate",
                      hint="G4 需要真实的两次打分对比")
    out = params.get("out") or f"runs/{request.run_name}-compare"
    argv = ["-m", "kev.compare", "--candidate", candidate, "--reference", reference, "--out", out]
    return BuiltCommand(argv=[_python()] + argv, cwd=str(paths.ROOT),
                        artifacts_in=[f"eval:{request.run_name}", f"eval:{request.run_name}-baseline"],
                        artifacts_out=[f"comparison:{request.run_name}"])


compare = StageSpec("compare", "compare", "配对 bootstrap 对比", _compare,
                    outcome="G4/G5 的证据来源；接着跑 calibrate")


def _calibrate(request: JobRequest) -> BuiltCommand:
    params = request.params
    rows = params.get("rows") or f"runs/{request.run_name}-eval/rows.json"
    if not rows.endswith("rows.json"):
        raise Invalid("温度拟合需要 kev.benchmark 写出的 rows.json", field="rows",
                      hint="kev.calibrate 要求 rows 带 logits + inference_temperature")
    out = params.get("out") or str(Path(rows).parent / "calibration.json")
    argv = ["-m", "kev.calibrate", "--rows", rows, "--out", out]
    return BuiltCommand(argv=[_python()] + argv, cwd=str(paths.ROOT),
                        artifacts_in=[f"eval:{request.run_name}"],
                        artifacts_out=[f"calibration:{request.run_name}"])


calibrate = StageSpec("calibrate", "calibrate", "温度拟合", _calibrate,
                      outcome="workload_temperature 是部署阶段的服务温度来源（G7）")

EVAL_STAGES = (baseline, benchmark, compare, calibrate)

__all__ = ["DEFAULT_BASELINE", "PUBLIC_SUITE", "baseline", "benchmark", "compare",
           "calibrate", "EVAL_STAGES"]
