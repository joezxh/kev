"""G1-G7 闸门：把 docs/medical/README.md §七 的医疗验收纪律固化成代码。

关键修正（spec §7.1.1，实测核对得出）：G4「增益真实」在单次 kev.benchmark 下不可判定
—— kev/benchmark.py 的 report.json 里没有 bootstrap 键（它写的是 paired_flip，
benchmark.py:89），配对 CI 只能由 kev.compare 产出（compare.py:44 ->
kev.metrics.paired_bootstrap，返回 {ci95: [lo, hi], ...}，metrics.py:423）。
同理 regression 段只存在于 kev_modal.py 的 Modal 产物，本地必须自己在公开 suite 上
做一次 compare。

全部是纯函数：读产物 dict，输出 Gate 列表。不碰文件系统、不起进程。

Run: uv run python -m pytest tests/test_console_gates.py -q
"""
import pytest

from kev.console.gates import STAGE_GATES, evaluate


def ok(gate_id, **products):
    stage = next(s for s, ids in STAGE_GATES.items() if gate_id in ids)
    gates = {g.id: g for g in evaluate(stage, **products)}
    return gates[gate_id]


def report(ece, conf_err, acc=0.8):
    return {"clean": {"ece": ece, "confident_error_rate": conf_err, "acc": acc},
            "calibrated_clean": {"ece": ece - 0.01 if ece else 0.0}}


def comparison(lo, hi, cand_conf=None, ref_conf=None):
    return {"paired": {"acc": {"ci95": [lo, hi], "macro_acc_delta": 0.05}},
            "clean": {"candidate": {"confident_error_rate": cand_conf if cand_conf is not None else 0.01},
                      "reference": {"confident_error_rate": ref_conf if ref_conf is not None else 0.02}}}


def test_gate_map_covers_every_documented_gate():
    # G4-G7 同时属于 image 与 deploy 两个阶段，所以要去重再比
    assert sorted({g for ids in STAGE_GATES.values() for g in ids}) == [
        "G1", "G2", "G3", "G4", "G5", "G6", "G7"]


def test_g1_blocks_when_records_exceed_the_context():
    passed = ok("G1", precheck={"over_limit": 0, "records": 551})
    assert passed.ok is True
    assert passed.need == "0"
    bad = ok("G1", precheck={"over_limit": 3, "records": 551})
    assert bad.ok is False
    assert "3" in bad.actual


def test_g2_requires_the_planned_record_count():
    assert ok("G2", summary={"records": 787}, plan={"total_records": 787}).ok is True
    assert ok("G2", summary={"records": 40}, plan={"total_records": 787}).ok is False


def test_g3_flags_invalid_lines_and_rare_labels():
    assert ok("G3", summary={"invalid_lines": 0, "label_warnings": []}).ok is True
    assert ok("G3", summary={"invalid_lines": 2, "label_warnings": []}).ok is False
    rare = ok("G3", summary={"invalid_lines": 0, "label_warnings": ["option 'x' under 5%"]})
    assert rare.ok is False
    assert "x" in rare.detail


def test_g4_needs_the_ci_lower_bound_above_zero():
    assert ok("G4", comparison=comparison(0.023, 0.097)).ok is True
    straddling = ok("G4", comparison=comparison(-0.01, 0.03))
    assert straddling.ok is False
    assert "更多更好的数据" in straddling.detail


def test_g5_needs_calibration_to_improve_and_confident_errors_to_hold():
    good = ok("G5", report=report(0.10, 0.01), comparison=comparison(0.01, 0.05, 0.01, 0.02))
    assert good.ok is True
    worse = ok("G5", report=report(0.10, 0.05), comparison=comparison(0.01, 0.05, 0.05, 0.02))
    assert worse.ok is False
    assert "0.05" in worse.actual
    # comparison 里没有 clean 块 => 拿不到 confident_error_rate，必须判失败而不是崩
    missing = ok("G5", report=report(0.10, 0.01),
                 comparison={"paired": {"acc": {"ci95": [0.01, 0.05]}}})
    assert missing.ok is False
    assert "compare" in missing.detail


def test_g6_tolerates_two_points_of_regression():
    # G6 读公开套件 compare（comparison_public），与 G4 的 workload compare（comparison）分离，
    # 见 gates.STAGE_GATES 与 app._gate_products。
    assert ok("G6", comparison_public=comparison(0.0, 0.04)).ok is True
    assert ok("G6", comparison_public=comparison(-0.01, 0.02)).ok is True
    too_much = ok("G6", comparison_public=comparison(-0.05, 0.01))
    assert too_much.ok is False
    assert "2" in too_much.detail


def test_g7_compares_the_oof_arm_against_shipped():
    calibration = {"arms": {"workload_oof": {"ece": 0.02}, "shipped": {"ece": 0.05}}}
    assert ok("G7", calibration=calibration).ok is True
    worse = {"arms": {"workload_oof": {"ece": 0.09}, "shipped": {"ece": 0.05}}}
    assert ok("G7", calibration=worse).ok is False


def test_missing_product_is_a_failure_not_a_crash():
    gate = ok("G4")
    assert gate.ok is False
    assert "compare" in gate.detail


@pytest.mark.parametrize("stage", sorted(s for s, ids in STAGE_GATES.items() if ids))
def test_every_stage_gate_survives_no_products_at_all(stage):
    """产物全缺时每道闸都要判失败并给出可读理由，不能抛异常 ——
    否则用户在流水线刚起步时点任何按钮都只会看到 500。"""
    gates = evaluate(stage)
    assert gates, f"{stage} 声明了闸门却返回空列表"
    for gate in gates:
        assert gate.ok is False
        assert gate.detail.strip(), f"{gate.id} 失败时必须说明原因"


@pytest.mark.parametrize("stage", ["benchmark", "compare", "calibrate", "data", "不存在的阶段"])
def test_stages_without_gates_return_empty(stage):
    """产出闸门证据的作业（benchmark/compare/calibrate）与数据阶段本身不设闸 ——
    它们是「生成证据」的一方，不该被自己要产出的证据拦住。"""
    assert evaluate(stage) == []


def test_gate_is_immutable_and_carries_actual_need():
    gate = ok("G2", summary={"records": 40}, plan={"total_records": 787})
    assert (gate.actual, gate.need) == ("40", "787")
    with pytest.raises(Exception):
        gate.ok = True          # 闸门结论一旦算出就不该被改


def test_zero_ece_does_not_produce_a_negative_calibrated_value():
    """report() 里 ece=0 时 calibrated 用 ece - 0.01 会变负数；真实产物里
    calibrated_clean.ece 是重算出来的，不会为负。G5 只需比较，不该被这种
    人工构造的输入带偏 —— 断言它在这种输入下判失败而不是崩。"""
    gate = ok("G5", report={"clean": {"ece": 0.0, "confident_error_rate": 0.01},
                            "calibrated_clean": {"ece": 0.0}},
              comparison=comparison(0.01, 0.05, 0.01, 0.02))
    assert gate.ok is False        # 0.0 不小于 0.0，未改善
