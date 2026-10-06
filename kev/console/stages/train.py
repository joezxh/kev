"""训练作业：kev.train 的 argv 组装。

三种方式（runbook-train_cn.md §〇），预填值取自手册的建议 —— **默认 A1**：
LoRA + 从已发布的 `jaredpalmer/kev-0.8b` 热启动；只在数据量大且已证明 LoRA 触顶时
升级到 B（全参数）。

**参数名一律下划线**（核对自 `kev/train.py` 的 argparse）—— `--init_from` 而不是
`--init-from`。`--base` 的默认是 `Qwen/Qwen3-0.6B-Base`，所以 A2/B 必须显式传
`Qwen/Qwen3.5-0.8B-Base`，否则会训到错误的基座上（runbook 步骤 6 的警告）。

lr 的来由：0.8B 是 4e-5、4B 是 2e-5（各自沿用 init 的训练参数），`MAX_DELTA_LR=5e-5`
是硬顶。所以本模块按 scenario 所属的轨道给默认值，而不是一刀切。
"""
from __future__ import annotations

from pathlib import Path

from .. import paths
from .base import BuiltCommand, Conflict, Invalid, JobRequest, StageSpec

paths.ensure_medical_on_path()
from run_matrix import FOUR_B_ONLY, SIZES, check_name  # noqa: E402

BASE = "Qwen/Qwen3.5-0.8B-Base"
BASE_REVISION = "9a45d25e"
# 0.8B 与 4B 各自的默认 lr（runbook §〇）。0.8B 更热，出现回归时两者都要减半但起点不同。
DEFAULT_LR = {"8b": "4e-5", "4b": "2e-5"}
COMMON = ["--epochs", "1", "--batch", "4", "--accum", "2", "--dtype", "bf16",
          "--device", "cuda", "--seed", "0", "--head_lr", "0", "--weight_decay", "0.01"]
# 可由表单覆盖的开关。init_from/base 的空值由 _with_values 统一剔除。
VALUE_KEYS = ("init_from", "base", "base_revision", "lora", "lora_targets", "full_ft",
              "weights_dtype", "lr", "replay", "checkpointing", "head_dim",
              "length_sort", "row_budget", "pass_tokens_max")
# 高级开关：runbook §七 7.4 项 3。参数名下划线风格已逐一核对 kev/train.py argparse，
# 全部存在（无一缺失）。默认空 -> 不传，沿用 kev.train 的默认值。
ADVANCED_KEYS = (
    "anchor", "anchor_w", "anchor_sources", "perm_kl", "perm_frac", "ord_w",
    "label_smoothing", "brier_w", "focal_gamma", "p_none", "p_none_distract",
    "p_none_pair", "none_pair_max_state", "synthetic_repeat", "public_frac",
    "train_sources", "holdout", "special_embeddings", "option_isolation",
    "shared_prefix", "snapshot_every_steps",
)
SNAPSHOT_LIMIT = 8          # kev.budget.MAX_SNAPSHOTS


def _python() -> str:
    import sys
    return sys.executable


def methods_for(scenario: str) -> dict:
    """该场景可用的三种方式。UI 的默认值来自这里，不要在前端硬编码。"""
    four_b_only = scenario in FOUR_B_ONLY
    return {
        "a1": {"title": "A1 · LoRA 热启动（推荐起步）", "init_from": SIZES["8b"][0],
               "lora": "16", "lora_targets": "all", "lr": DEFAULT_LR["8b"], "head_dim": "256",
               "full_ft": "0", "weights_dtype": "fp32", "replay": "2000",
               "allowed": not four_b_only},
        "a2": {"title": "A2 · LoRA 从裸基座", "init_from": "", "base": BASE,
               "base_revision": BASE_REVISION, "lora": "16", "lora_targets": "all",
               "lr": DEFAULT_LR["8b"], "head_dim": "256", "full_ft": "0",
               "weights_dtype": "fp32", "replay": "2000", "allowed": not four_b_only},
        "b": {"title": "B · 全参数微调（需 24GB+ 或多卡）", "init_from": "", "base": BASE,
              "base_revision": BASE_REVISION, "full_ft": "1", "weights_dtype": "bf16",
              "lr": DEFAULT_LR["8b"], "head_dim": "256", "replay": "0", "allowed": True},
    }


def _with_values(mapping: dict) -> list:
    """只追加取值非空的开关 —— 避免把 `--init_from ''` 传给 kev.train。"""
    out: list = []
    for key, value in mapping.items():
        if value not in (None, ""):
            out += [f"--{key}", str(value)]
    return out


def _resolve_out(request: JobRequest) -> str:
    params = request.params
    out = params.get("out") or f"runs/{request.run_name}"
    if params.get("check_exists") and (Path(paths.ROOT) / out).exists():
        raise Conflict(f"{out} 已存在；换一个运行名（例如 -v2）或先清理",
                       hint="旧产物永久保留，可审计")
    return out


def build_argv(request: JobRequest) -> list:
    """组装 kev.train 的 argv（不含解释器前缀）。测试与 UI preview 都调它。"""
    params = request.params
    methods = methods_for(request.scenario)
    method = params.get("method", "a1")
    if method not in methods:
        raise Invalid(f"未知微调方式 {method!r}", field="method",
                      hint=f"可选：{', '.join(sorted(methods))}")
    if not methods[method]["allowed"]:
        raise Invalid(f"{request.scenario} 语义难度过高，只支持 4B 轨（方法 b）",
                      field="method", hint="见 run_matrix.FOUR_B_ONLY")

    check_name(request.run_name)          # fullmatch，禁点号；错误时 raise SystemExit
    out = _resolve_out(request)

    # 高级开关的互相约束（kev/train.py parse_args 也会校验，这里提前拦成 400 而不是
    # 让子进程跑起来才炸）。只拦最常见的两组，其余交给 kev.train 自身。
    if params.get("anchor") and not _positive(params, "anchor_w"):
        raise Invalid("设了 --anchor 必须同时给 --anchor_w > 0", field="anchor_w",
                      hint="锚定正例权重为 0 等于没设")
    if params.get("none_pair_max_state") and not _positive(params, "p_none_pair"):
        raise Invalid("--none_pair_max_state 需要 --p_none_pair > 0", field="p_none_pair")

    argv = ["-m", "kev.train",
            "--data", params.get("data") or f"data/{request.scenario}/train.jsonl",
            "--out", out, *COMMON]
    defaults = methods[method]
    argv += _with_values({key: defaults.get(key, params.get(key)) for key in VALUE_KEYS})
    # 高级开关：默认空 -> 不传，沿用 kev.train 默认。
    argv += _with_values({key: params.get(key) for key in ADVANCED_KEYS})

    if str(defaults.get("full_ft")) == "1":
        fractions = params.get("snapshot_fractions")
        if fractions and not params.get("max_steps"):
            # 有这个前置校验是因为 kev/budget.py 的 MAX_SNAPSHOTS=8 与 resume 点
            # 占的磁盘都是硬约束，parse 期就该拦住而不是跑起来才炸。
            raise Invalid("全权重写快照需要 --max_steps 来界定优化步数", field="max_steps",
                          hint=f"kev.budget.MAX_SNAPSHOTS = {SNAPSHOT_LIMIT}；"
                               "快照永不删除，磁盘要算清")
        if fractions:
            argv += ["--max_steps", str(_int(params, "max_steps")),
                     "--snapshot_fractions", str(fractions),
                     "--snapshot_dir", params.get("snapshot_dir", f"{out}-snapshots")]
    return argv


def _int(params: dict, key: str) -> int:
    try:
        return int(params[key])
    except (TypeError, ValueError):
        raise Invalid(f"{key} 必须是整数，收到 {params.get(key)!r}", field=key) from None


def _positive(params: dict, key: str) -> bool:
    """高级开关的互相约束里用：取不到或 <= 0 都算「没开」。

    kev/train.py 用 argparse.type=float，空字符串会炸；这里先归一化，避免把表单空值
    当成「0 开启」误判。
    """
    try:
        return float(params.get(key)) > 0
    except (TypeError, ValueError):
        return False


def _train(request: JobRequest) -> BuiltCommand:
    argv = build_argv(request)
    out = argv[argv.index("--out") + 1]
    return BuiltCommand(argv=[_python()] + argv, cwd=str(paths.ROOT),
                        artifacts_in=[f"dataset:{request.scenario}/train"],
                        artifacts_out=[f"run:{request.run_name}"])


train = StageSpec("train", "train", "SFT 训练", _train,
                  outcome="接着跑 baseline + benchmark + compare（闸门 G4 需要配对 CI）")

TRAIN_STAGES = (train,)

__all__ = ["BASE", "BASE_REVISION", "DEFAULT_LR", "SNAPSHOT_LIMIT", "build_argv",
           "methods_for", "train", "check_name", "TRAIN_STAGES"]
