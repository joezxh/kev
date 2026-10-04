"""G1-G7 闸门：把 docs/medical/README.md §七 的验收门槛变成可执行判定。

纯函数：读产物 dict，输出 Gate 列表。**不碰文件系统、不起进程** —— 调用方负责把产物
读进来（Task 8 的 `_gate_products`）。这样每一道闸都能单独测试。

判据来源（spec §7.1.1 的实测修正，不是推测）：
- G4 的配对 CI 只在 kev.compare 的产物里（`compare.py:44` -> `metrics.paired_bootstrap`），
  而 kev/benchmark.py 的 report.json 只有 `paired_flip`（`benchmark.py:89`），**没有**
  bootstrap 键。所以「增益真实」在单次 benchmark 下根本不可判定。
- G6 的 `regression` 段只存在于 kev_modal.py 的 Modal 产物，本地要在公开 suite 上
  自己 compare 一次。
- G5 的 `calibrated_clean` 由 `kev/benchmark.py:94` 产出（temperature=1.0 下按 knowable
  行重算），`clean.confident_error_rate` 在同一份 report 的 `clean` 块里。
"""
from __future__ import annotations

from dataclasses import dataclass

# 公开数据上的精度下降容忍上限：README §七「回归 ≤ 2 点」。
REGRESSION_TOLERANCE = -0.02


@dataclass(frozen=True)
class Gate:
    """一道闸的判定结果。frozen 是有意的：结论一旦算出就不该被改。"""

    id: str
    ok: bool
    detail: str
    actual: str = ""
    need: str = ""


def _number(value, default=None):
    """只接受真正的 int/float —— bool 是 int 的子类，必须排除（True 不该当 1 用）。"""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default
    return value


def _get(mapping, *keys):
    """按路径取值，任何一层不是 dict 或缺失都返回 None（不抛）。"""
    for key in keys:
        if not isinstance(mapping, dict):
            return None
        mapping = mapping.get(key)
        if mapping is None:
            return None
    return mapping


def _ci95(comparison):
    """取配对 bootstrap 的 acc CI；取不到就返回 None。"""
    value = _get(comparison, "paired", "acc", "ci95")
    if isinstance(value, (list, tuple)) and len(value) == 2:
        return value
    return None


def g1(precheck) -> Gate:
    """state/请求是否全部落在训练上下文内。

    训练器对超限记录是**静默丢弃**（只在 train.log 打一行 `dropped N of M records`），
    所以这一步必须前置。字符数不可信 —— split_data.STATE_CHARS_WARN=1400 是英文口径，
    中文 token 密度更高，一律以 precheck 用真实 tokenizer 的实测为准。
    """
    if not isinstance(precheck, dict):
        return Gate("G1", False, "缺少 precheck 报告；先跑 precheck（token 超限预检）")
    over = _number(precheck.get("over_limit"))
    if over is None:
        return Gate("G1", False, "precheck 报告里没有 over_limit")
    if over == 0:
        return Gate("G1", True, f"{precheck.get('records', '?')} 条记录全部在训练上下文内",
                    actual="0", need="0")
    return Gate("G1", False,
                f"{over} 条记录超出训练上下文，训练器会静默丢弃它们。"
                "缩短 state 字段，不要靠字符数估算（中文 token 密度更高）",
                actual=str(over), need="0")


def g2(summary, plan) -> Gate:
    """划分出的记录数是否与 plan_size 的计划一致。

    不一致几乎总是「生成与划分并行」造成的：split 读到了生成器还没写完的文件
    （runbook §三 记录的 40 条 vs 787 条那次）。
    """
    records = _get(summary, "records")
    planned = _number(_get(plan, "total_records"))
    if records is None or planned is None:
        return Gate("G2", False, "缺少 split 的 summary.json 或 plan_size 的计划")
    if records == planned:
        return Gate("G2", True, f"记录数与计划一致（{records}）",
                    actual=str(records), need=str(planned))
    return Gate("G2", False,
                f"实际 {records} 条，计划 {planned} 条。"
                "生成与划分必须串行：先生成完毕再划分，否则会读到旧文件",
                actual=str(records), need=str(planned))


def g3(summary) -> Gate:
    """无无效行、无标签分布告警。

    `<5%` 的标签与「从未作为正确答案出现」的选项都是 split_data 的告警项
    （data-format.md §四）。不要靠加 --n 稀释 —— 那会让每类都变稀。
    """
    invalid = _number(_get(summary, "invalid_lines"))
    if invalid is None:
        return Gate("G3", False, "缺少 split 的 summary.json 的 invalid_lines")
    if invalid:
        return Gate("G3", False, f"{invalid} 行无效记录被丢弃",
                    actual=str(invalid), need="0")
    warnings = _get(summary, "label_warnings")
    if warnings is None:
        return Gate("G3", False, "缺少 split 的 summary.json 的 label_warnings")
    if warnings:
        listed = "; ".join(str(item) for item in list(warnings)[:5])
        return Gate("G3", False,
                    f"标签分布告警：{listed}。调生成器配额，不要靠加 --n 稀释"
                    "（data-format.md §四）",
                    actual=listed, need="无告警")
    return Gate("G3", True, "无无效行、无标签分布告警", actual="0", need="0")


def g4(comparison) -> Gate:
    """配对 bootstrap 的 CI 下限是否 > 0（README §七「增益真实」）。

    CI 含 0 说明增益不显著。README §八的收益排序第 1 位是「更多更好的数据」——
    改数据不是加量、也不是调超参，这句话要写进提示里，否则用户会去调 lr。
    """
    ci = _ci95(comparison)
    if ci is None:
        return Gate("G4", False,
                    "缺少配对 bootstrap 的 CI；先跑 baseline + benchmark + compare。"
                    "单次 kev.benchmark 判不了增益（它只写 paired_flip，没有 bootstrap）")
    low = _number(ci[0])
    if low is None:
        return Gate("G4", False, "CI 下限不是数字")
    if low > 0:
        return Gate("G4", True, f"CI95 [{low:.4f}, {_number(ci[1], ci[0]):.4f}] 排除 0",
                    actual=f"{low:.4f}", need="> 0")
    return Gate("G4", False,
                f"CI95 下限 {low:.4f} ≤ 0，增益不显著。"
                "这是数据不够或增益太小 —— 更多更好的数据排在收益排序第 1 位，"
                "改数据不是加量、也不是调超参",
                actual=f"{low:.4f}", need="> 0")


def g5(report, comparison) -> Gate:
    """校准必须优于原始，且微调后不能比 baseline 更过度自信。

    0.8B 已知更容易过度自信（发布说明：一次 refit 让它在 documents/skills 家族上
    校准更差并超出注册容差，而 4B 没有改善），所以这一项要比 4B 卡得更严。
    """
    raw = _number(_get(report, "clean", "ece"))
    calibrated = _number(_get(report, "calibrated_clean", "ece"))
    if raw is None or calibrated is None:
        return Gate("G5", False, "report.json 缺少 clean.ece 或 calibrated_clean.ece")
    if calibrated >= raw:
        return Gate("G5", False, f"校准后 ECE {calibrated:.4f} 未优于原始 {raw:.4f}",
                    actual=f"{calibrated:.4f}", need=f"< {raw:.4f}")
    candidate = _number(_get(comparison, "clean", "candidate", "confident_error_rate"))
    reference = _number(_get(comparison, "clean", "reference", "confident_error_rate"))
    if candidate is None or reference is None:
        return Gate("G5", False,
                    "缺少 baseline / candidate 的 confident_error_rate（跑 compare）")
    if candidate > reference:
        return Gate("G5", False,
                    f"微调后 confident_error_rate {candidate:.4f} 高于 baseline {reference:.4f}。"
                    "0.8B 已知更易过度自信，这一项卡得比 4B 更严",
                    actual=f"{candidate:.4f}", need=f"<= {reference:.4f}")
    return Gate("G5", True,
                f"ECE {raw:.4f} -> {calibrated:.4f}，"
                f"confident_error_rate {candidate:.4f} <= {reference:.4f}")


def g6(comparison) -> Gate:
    """公开数据上的精度下降不得超过 2 点（README §七「回归」）。

    超了说明 delta 遗忘了通用能力，对策是降 --lr 减半、保留 --replay 2000、不加 epoch。
    """
    ci = _ci95(comparison)
    if ci is None:
        return Gate("G6", False, "缺少公开数据上的配对 CI；回归检查要在公开 suite 上做一次 compare")
    low = _number(ci[0])
    if low is None:
        return Gate("G6", False, "CI 下限不是数字")
    if low >= REGRESSION_TOLERANCE:
        return Gate("G6", True, f"公开数据 CI95 下限 {low:.4f}，未超过 2 点回退",
                    actual=f"{low:.4f}", need=f">= {REGRESSION_TOLERANCE}")
    return Gate("G6", False,
                f"公开数据精度下降 {abs(low) * 100:.1f} 点，超过 2 点上限。"
                "降 --lr 减半、保留 --replay 2000、不加 epoch",
                actual=f"{low:.4f}", need=f">= {REGRESSION_TOLERANCE}")


def g7(calibration) -> Gate:
    """workload_oof 的 ECE 必须不劣于 shipped（runbook 步骤 10 的验证项）。"""
    oof = _number(_get(calibration, "arms", "workload_oof", "ece"))
    shipped = _number(_get(calibration, "arms", "shipped", "ece"))
    if oof is None or shipped is None:
        return Gate("G7", False, "缺少 calibration.json 的 arms.workload_oof / arms.shipped")
    if oof <= shipped:
        return Gate("G7", True, f"workload_oof ECE {oof:.4f} <= shipped {shipped:.4f}",
                    actual=f"{oof:.4f}", need=f"<= {shipped:.4f}")
    return Gate("G7", False, f"workload_oof ECE {oof:.4f} 差于 shipped {shipped:.4f}",
                actual=f"{oof:.4f}", need=f"<= {shipped:.4f}")


# 每个闸读哪些产物键。BUILDERS 的 lambda 签名因此统一是 (**products)。
_BUILDERS = {
    "G1": lambda p: g1(p.get("precheck")),
    "G2": lambda p: g2(p.get("summary"), p.get("plan")),
    "G3": lambda p: g3(p.get("summary")),
    "G4": lambda p: g4(p.get("comparison")),
    "G5": lambda p: g5(p.get("report"), p.get("comparison")),
    "G6": lambda p: g6(p.get("comparison")),
    "G7": lambda p: g7(p.get("calibration")),
}

# 阶段 -> 该阶段要过的闸。键与 StageSpec.stage 一致。
# train 前的三道是数据质量闸；image/deploy 前的四道是模型质量闸。
# compare/calibrate 自身不设闸（它们是产出闸门证据的作业）。
STAGE_GATES = {
    "train": ["G1", "G2", "G3"],
    "benchmark": [],
    "compare": [],
    "calibrate": [],
    "image": ["G4", "G5", "G6", "G7"],
    "deploy": ["G4", "G5", "G6", "G7"],
}


def evaluate(stage, **products) -> list:
    """判定某阶段关心的闸。未提供的产物让对应闸判失败并说明缺什么，而不是抛异常 ——
    用户在流水线刚起步时点任何按钮都该看到可读的提示，不是 500。"""
    return [_BUILDERS[gate_id](products) for gate_id in STAGE_GATES.get(stage, [])]
