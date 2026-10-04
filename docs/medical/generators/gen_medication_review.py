"""用药 / 医保合理性审核记录生成器 —— 双尺寸主力场景。

标签由下方说明书规则引擎派生（禁忌、剂量超限、重复用药、特殊人群、适应症不符），标注零漂移。
**权威判据在本文件**，spec 的 guidance 必须与它一致。

日期与疗程字段（days_on_drug、gestation_weeks）由生成器算好后直接给出，模型不做日期运算 ——
这是对 0.8B 日期算术弱项（0.35）的根本性规避。

用法::

    python3 docs/medical/generators/gen_medication_review.py --n 787 --out data/mr.jsonl --seed 0
"""
import random
import sys

from common import base_parser, labelled, load_spec, write_records

SCENARIO = "medication-review"

# 药品 -> (单次上限 mg, 每日上限 mg, 每日下限 mg, 类别)。None 表示不设该项限制。
# 上限取常见说明书口径，实际落地须替换为本院药品说明书数据。
DRUGS = {
    "甲硝唑": (600, 1200, 400, "抗菌药"),
    "头孢曲松": (2000, 4000, 500, "抗菌药"),
    "阿莫西林": (1000, 3000, 750, "抗菌药"),
    "对乙酰氨基酚": (1000, 4000, 500, "解热镇痛"),
    "布洛芬": (400, 1200, 600, "解热镇痛"),
    "阿司匹林": (1000, 3000, 500, "解热镇痛"),
    "华法林": (10, 10, 2.5, "抗凝药"),
    "氯吡格雷": (300, 300, 75, "抗栓药"),
    "二甲双胍": (1000, 2000, 1000, "降糖药"),
    "格列美脲": (4, 6, 2, "降糖药"),
    "氨氯地平": (10, 10, 5, "降压药"),
    "缬沙坦": (320, 320, 160, "降压药"),
    "奥美拉唑": (40, 40, 20, "PPI"),
    "四环素": (500, 1000, 500, "抗菌药"),
    "左氧氟沙星": (500, 500, 500, "抗菌药"),
}

# 特殊人群禁忌：(药名, 人群标签) -> 原因。人群标签取值见 :func:`sample_patient`。
SPECIAL_POPULATION = {
    ("四环素", "child"): "8 岁以下禁用，可致牙齿永久着色",
    ("四环素", "pregnant"): "妊娠期禁用",
    ("左氧氟沙星", "child"): "18 岁以下禁用，影响软骨发育",
    ("左氧氟沙星", "pregnant"): "妊娠期一般禁用，权衡后慎用",
    ("华法林", "pregnant"): "妊娠 6 周后禁用，可致胎儿出血",
    ("华法林", "breastfeeding"): "哺乳期禁用",
    ("阿司匹林", "child_viral"): "儿童病毒感染期禁用，Reye 综合征风险",
    ("布洛芬", "pregnant"): "妊娠晚期禁用，可致动脉导管提前关闭",
    ("格列美脲", "elderly"): "老年患者低血糖风险高，需减量并加强监测",
    ("二甲双胍", "renal"): "eGFR 低于 30 禁用，乳酸酸中毒风险",
    ("阿莫西林", "penicillin_allergy"): "青霉素过敏者禁用",
    ("头孢曲松", "penicillin_allergy"): "青霉素过敏者慎用，存在交叉过敏风险",
    ("缬沙坦", "pregnant"): "妊娠中晚期禁用，胎儿肾毒性",
    ("阿司匹林", "renal"): "肾功能不全者大剂量使用需谨慎",
}

# 适应症 -> 可用药品类别之外的合理搭配，用于派生 indication_mismatch
INDICATIONS = {
    "细菌性阴道炎": "抗菌药", "社区获得性肺炎": "抗菌药", "尿路感染": "抗菌药",
    "高血压": "降压药", "2 型糖尿病": "降糖药", "心房颤动": "抗凝药",
    "冠心病": "抗栓药", "胃溃疡": "PPI", "发热": "解热镇痛", "术后镇痛": "解热镇痛",
}

# verdict -> severity 的强对应（spec guidance 要求 severity 0/2/3 分别对应 pass/conditional/reject）
VERDICT_SEVERITY = {"pass": 0, "conditional": 2, "reject": 3}
# 多规则同时命中时 issue_type 的优先级
ISSUE_PRIORITY = ["contraindication", "dose_over", "duplicate", "special_population", "indication_mismatch"]


def sample_patient(rng):
    """年龄性别 + 生理状态标签。日期派生字段（孕周）在这里算好，模型只读结果。"""
    age = rng.choice([2, 5, 11, 17, 26, 34, 41, 52, 58, 63, 67, 71, 74, 79])
    sex = rng.choice(["male", "female"])
    flags = []
    if age < 12:
        flags.append("child")
    if age >= 65:
        flags.append("elderly")
    if sex == "female" and rng.random() < 0.12:
        flags.append("pregnant")
        if rng.random() < 0.35:
            flags.append("breastfeeding")
    elif rng.random() < 0.06:
        flags.append("breastfeeding")
    if rng.random() < 0.08:
        flags.append("renal")
    if rng.random() < 0.04:
        flags.append("child_viral")
    patient = f"{sex} {age}"
    if "pregnant" in flags:
        patient += f", gestation {rng.randint(6, 38)} weeks"
    return patient, flags


def egfr_for(rng, flags):
    """eGFR 数值。肾功能不全时落到 15-29（触发二甲双胍禁忌）。"""
    if "renal" in flags:
        return rng.choice([8, 15, 22, 28])
    return rng.choice([62, 78, 88, 95, 102, 110, 125])


def evaluate(plan):
    """The rule engine. Takes the sampled plan and returns (verdict, issue_types, severity).

    Deterministic and total: the same plan always yields the same verdict, so labels cannot drift. `issue_types` is
    a set because several rules can fire at once; the verdict takes the most serious one.
    """
    drug, dose_per, times_per_day, patient_flags, allergy, indication, twin = plan
    single_max, daily_max, daily_min, category = DRUGS[drug]
    daily = dose_per * times_per_day
    issues = set()

    for flag in patient_flags:
        if (drug, flag) in SPECIAL_POPULATION:
            issues.add("special_population")
    if allergy and drug in ("阿莫西林", "头孢曲松"):
        issues.add("contraindication")
    if twin and DRUGS[twin][3] == category:
        issues.add("duplicate")
    if single_max is not None and dose_per > single_max:
        issues.add("dose_over")
    if daily_max is not None and daily > daily_max:
        issues.add("dose_over")
    if INDICATIONS.get(indication) != category:
        issues.add("indication_mismatch")

    serious = [i for i in ISSUE_PRIORITY if i in issues]
    if not serious:
        return "pass", issues, 0
    top = serious[0]
    verdict = "reject" if top in ("contraindication", "dose_over", "duplicate") else "conditional"
    return verdict, issues, VERDICT_SEVERITY[verdict]


def sample_plan(rng, target=None):
    """Sample a prescription, optionally steered to hit `target` (one of the issue_type keys, or None for clean).

    Steering matters for the same reason as in gen_critical_value: split_data warns when a label falls under 5%, so
    the batch plan decides the labels first and the sampler then finds a prescription that provokes them.
    """
    for _ in range(60):
        drug = rng.choice(list(DRUGS))
        single_max, _, _, category = DRUGS[drug]
        patient, flags = sample_patient(rng)
        allergy = "青霉素（皮疹）" if rng.random() < 0.2 else ""
        # 70% 的处方适应症与药品类别相符，其余刻意错配以产生 indication_mismatch
        pool = [k for k, v in INDICATIONS.items() if v == category] or list(INDICATIONS)
        indication = rng.choice(pool) if rng.random() < 0.7 else rng.choice(list(INDICATIONS))
        times = rng.choice([1, 2, 3])
        mild = target == "mild"
        if target == "dose_over" and single_max:
            dose = rng.randint(int(single_max * 1.05), int(single_max * 1.6))
        elif mild and single_max:
            dose = max(1, int(single_max * 0.15))  # 剂量偏小：无规则命中，仅提示
        elif single_max:
            dose = rng.randint(max(1, int(single_max * 0.3)), int(single_max * 0.95))
        else:
            dose = rng.randint(100, 800)
        # 重复用药：同类别再叠加一种药。由 build 写入 current_meds，规则引擎据类别重叠判定。
        twin = next((d for d, spec in DRUGS.items() if spec[3] == category and d != drug), None)
        plan = (drug, dose, times, flags, allergy, indication, twin if target == "duplicate" else None)
        verdict, issues, severity = evaluate(plan)
        if mild and issues:
            continue  # 轻微偏差必须无规则命中，否则与 severity=1 的定义冲突
        if target is None or target in issues or mild:
            return patient, flags, plan, verdict, issues, (1 if mild else severity)
    return None


def build(rng, target=None):
    built = sample_plan(rng, target)
    if built is None:
        return None
    patient, flags, plan, verdict, issues, severity = built
    drug, dose, times, _, allergy, indication, twin = plan
    days = rng.choice([1, 3, 5, 7, 10, 14])
    others = [d for d in rng.sample(list(DRUGS), 3) if d != drug]
    if rng.random() < 0.5:
        others = others[:2]  # 单药或两药联用占一半，其余为三药以上
    if twin:
        others.append(twin)
    state = {
        "patient": patient,
        "state_flags": ", ".join(flags) if flags else "none",
        "allergies": allergy or "无已知药物过敏",
        "current_meds": others,
        "current_rx": f"{drug} {dose}mg {'tid' if times == 3 else 'bid' if times == 2 else 'qd'} x {days}天",
        "days_on_drug": rng.choice([1, 3, 5, 7]),
        "indication": indication,
    }
    labels = {
        "verdict": verdict,
        # 与 verdict 独立的高风险信号：妊娠/哺乳/儿童/老年/肝肾异常/多药联用即需药师复核
        "needs_pharmacist": bool({"pregnant", "breastfeeding", "child", "elderly", "renal"} & set(flags))
                              or len(others) >= 3,
        "issue_type": next((i for i in ISSUE_PRIORITY if i in issues), "none"),
        "severity": severity,
    }
    return labelled(load_spec(SCENARIO), state, labels)


def plan_targets(n, rng, defect_share):
    """标签计划：defect_share 的记录带问题，其余为 clean pass。按 issue_type 均匀分配，避免某个标签低于 5%。

    verdict / issue_type / severity 三者由规则引擎联动派生，所以这里只规划 issue_type；
    severity 的 0/2/3 分布由 verdict 决定，无需单独配额。
    """
    keys = [k for k in ISSUE_PRIORITY if k != "indication_mismatch"] + ["indication_mismatch", "mild"]
    defective = int(n * defect_share)
    plan = [None] * (n - defective)
    for i in range(defective):
        plan.append(keys[i % len(keys)])
    rng.shuffle(plan)
    return plan


def main(argv=None):
    parser = base_parser(__doc__.split("\n\n")[0])
    parser.add_argument("--defect-share", type=float, default=0.6,
                        help="share of records carrying a defect; the 6 issue_type options x 5%% floor needs >= 0.3")
    args = parser.parse_args(argv)
    rng = random.Random(args.seed)
    records, misses = [], 0
    for target in plan_targets(args.n, rng, args.defect_share):
        record = build(rng, target)
        if record is None:
            misses += 1
            record = build(rng, None)
        if record is not None:
            records.append(record)
    while len(records) < args.n:  # top up if a target could not be realized
        record = build(rng, None)
        if record is None:
            break
        records.append(record)
    write_records(records[:args.n], args.out, args.seed, SCENARIO)
    if misses:
        print(f"note: {misses} planned targets could not be realized and fell back to a clean prescription")
    return 0


if __name__ == "__main__":
    sys.exit(main())
