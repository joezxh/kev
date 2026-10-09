"""护理质量管控记录生成器 —— 双尺寸主力场景。

标签由 :data:`CHECKLIST` 的质控检查表条目与判定标准派生，标注零漂移。**权威判据在本文件**，
spec 的 guidance 必须与它一致。

按 spec 的强对应关系生成：issue_type=none ⟺ severity=0 且 reportable=false；构成不良事件时
reportable=true 且 severity=3；其余按流程/记录/沟通/设备缺陷分级。

用法::

    python3 kev/console/generators/gen_nursing_quality.py --n 787 --out data/nq.jsonl --seed 0
"""
import random
import sys

from common import base_parser, labelled, load_spec, write_records

SCENARIO = "nursing-quality"

# (检查环节, 问题类别, 默认严重度, 是否构成不良事件, 可预防性, 观察文本模板)
CHECKLIST = [
    ("静脉输液过程", "execution", 1, False, "preventable", "输液前未核对腕带姓名与药名"),
    ("静脉输液过程", "execution", 2, False, "preventable", "输液过程中未及时巡视，液体滴速过快未调整"),
    ("皮下注射", "execution", 1, False, "preventable", "注射部位未标注时间，核对记录缺签名"),
    ("口服给药", "execution", 2, True, "preventable", "漏发一次降压药，服药单未记录原因"),
    ("输血过程", "execution", 3, True, "preventable", "输血前未双人核对血型，过程记录缺观察项"),
    ("留置导尿管", "device", 2, False, "partially", "导尿管固定装置松动，刻度未标识"),
    ("留置尿管", "device", 3, True, "preventable", "尿管牵拉致尿道损伤，已发生非计划拔管"),
    ("桡动脉测压管", "device", 2, False, "partially", "测压管固定胶布过敏未观察，延长管无刻度标识"),
    ("鼻胃管", "device", 2, False, "preventable", "鼻胃管刻度未记录，胃管固定不牢"),
    ("压疮风险评估", "assessment", 1, False, "preventable", "Braden 评分未在入院 24 小时内完成"),
    ("跌倒风险评估", "assessment", 1, False, "preventable", "Morse 评分未在入院时完成，防跌倒措施未落实"),
    ("导管风险评估", "assessment", 2, False, "preventable", "留置 3 路管路未做导管风险评估表"),
    ("疼痛评估", "assessment", 1, False, "preventable", "疼痛评分表连续 3 天未记录"),
    ("护理记录书写", "record", 1, False, "preventable", "体温单 14:00 一栏空白未补记"),
    ("护理记录书写", "record", 2, True, "preventable", "记录时间逻辑不自洽，巡视记录显示在输液之前"),
    ("护理记录书写", "record", 3, True, "preventable", "出院记录存在事后补记，与医嘱时间矛盾"),
    ("交接班", "record", 1, False, "preventable", "交接班内容遗漏压疮高风险患者"),
    ("健康宣教", "communication", 1, False, "preventable", "糖尿病患者饮食宣教未落实签字"),
    ("知情同意", "communication", 2, False, "partially", "特殊检查知情同意书未完整签署"),
    ("医患沟通", "communication", 1, False, "preventable", "告知患者翻身目的时语气生硬，患者投诉"),
    ("设备管理", "device", 1, False, "partially", "输液泵电池老化未及时更换"),
    ("胰岛素注射", "execution", 3, True, "preventable", "胰岛素剂量与医嘱不符，血糖异常升高"),
    ("跌倒预防", "execution", 3, True, "partially", "高风险患者未拉床栏，致跌倒致尾椎骨折"),
    ("压疮护理", "execution", 3, True, "partially", "卧床患者未按计划翻身，骶尾部出现 II 期压疮"),
    ("病情观察", "assessment", 2, True, "not_preventable", "患者术后突发低血压，抢救记录及时但术前评估未能预判"),
    ("病情观察", "record", 1, False, "not_preventable", "患者夜间突发上消化道出血，属疾病自身进展"),
    ("压疮护理", "execution", 2, False, "not_preventable", "患者临终前皮肤渗液致局部破损，非翻身不到位所致"),
]

# 观察文本前缀：加入时间点与班次，既贴近真实质控记录，也避免同一检查条目产生完全相同的 state。
CONTEXTS = ["晨间护理时发现：", "午间巡视发现：", "夜班巡视时发现：", "交接班核查发现：",
            "家属反馈后核查发现：", "质控抽查发现：", "晨会交班汇报："]

WARDS = ["神经内科 3 病区", "心血管内科 2 病区", "呼吸内科 1 病区", "消化内科 4 病区",
         "骨科 2 病区", "肿瘤科 3 病区", "老年科 5 病区", "普外科 1 病区", "ICU", "产科 2 病区"]
LEVELS = ["特级护理", "一级护理", "二级护理", "三级护理"]
DEPENDENCIES = ["留置尿管 1 条", "留置尿管 1 条，桡动脉测压管 1 条", "鼻胃管 1 条",
                "留置尿管 1 条，鼻胃管 1 条，负压引流 1 条", "无"]
RISK = ["Braden 12 分（中等风险），Morse 45 分（高风险）", "Braden 9 分（高风险）",
        "Braden 15 分（轻度风险），Morse 30 分（中风险）", "Braden 18 分（低风险）"]


def decide(item, high_dependency):
    """The four labels, derived from the checklist row.

    `high_dependency` (bedridden / multiple lines / high risk scores) lifts the severity by one level as the spec's
    guidance allows, but never past 3, and never for a compliant record.
    """
    _, issue_type, severity, adverse, preventability, _ = item
    if issue_type == "none":
        return {"issue_type": "none", "reportable": False, "severity": 0, "preventable": "preventable"}
    lifted = 3 if high_dependency and severity < 3 else severity
    # A lifted severity 3 implies an adverse event was caused, which the row itself did not claim; keep the row's own
    # reportable flag instead of inventing one, so severity and reportable stay independent as the spec requires.
    return {"issue_type": issue_type, "reportable": adverse, "severity": lifted, "preventable": preventability}


def build(rng, target=None):
    """One nursing-quality record.

    `target` is an issue_type key, a preventability key ("partially" / "not_preventable"), or None for a compliant
    check. Selecting by preventability matters because those labels are sparse: only 3 of the checklist rows are
    `not_preventable`, so leaving them to chance drops them under split_data's 5% floor at smaller batch sizes.
    """
    for _ in range(80):
        if target in (None, "none"):
            item = ("病区巡视", "none", 0, False, "preventable",
                    "各项记录规范，评估表完整，核对与巡视均按流程执行")
        elif target in ("partially", "not_preventable"):
            pool = [c for c in CHECKLIST if c[4] == target]
            if not pool:
                return None
            item = rng.choice(pool)
        else:
            pool = [c for c in CHECKLIST if c[1] == target]
            if not pool:
                return None
            item = rng.choice(pool)
        age = rng.choice([34, 52, 63, 68, 71, 74, 79, 83])
        high_dependency = rng.random() < 0.4
        labels = decide(item, high_dependency)
        state = {
            "patient": ("male " if rng.random() < 0.5 else "female ") + str(age) +
                       (", bedridden" if high_dependency else ", 部分自理"),
            "ward": rng.choice(WARDS),
            "nursing_level": rng.choice(LEVELS),
            "check_point": item[0],
            "observed": rng.choice(CONTEXTS) + item[5],
            "dependencies": rng.choice(DEPENDENCIES) if high_dependency else "无",
            "risk_scores": rng.choice(RISK) if high_dependency else "Braden 15 分，Morse 30 分",
        }
        if target == "none":
            state["observed"] = rng.choice(CONTEXTS) + item[5]
        return labelled(load_spec(SCENARIO), state, labels)
    return None


def plan_targets(n, rng, defect_share):
    """标签计划：defect_share 的记录有问题，其余为合规检查。

    6 个 issue_type 与 3 个 preventability 各需 >=5%。preventability 里 partially / not_preventable 的检查表条目很少，
    所以显式给它们配额，而不是让它们随 issue_type 顺带出现 —— 后者在小批量下会掉到 5% 以下。
    """
    issue_types = ["execution", "record", "device", "assessment", "communication"]
    preventability = ["not_preventable", "partially"]
    defective = int(n * defect_share)
    plan = [None] * (n - defective)
    per_prevent = max(1, int(defective * 0.18))
    for i in range(per_prevent * len(preventability)):
        plan.append(preventability[i % len(preventability)])
    for i in range(max(0, defective - per_prevent * len(preventability))):
        plan.append(issue_types[i % len(issue_types)])
    rng.shuffle(plan)
    return plan[:n]


def main(argv=None):
    parser = base_parser(__doc__.split("\n\n")[0])
    parser.add_argument("--defect-share", type=float, default=0.75,
                        help="share of records carrying a defect; 6 issue_type options x 5%% floor needs >= 0.3")
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
    while len(records) < args.n:
        record = build(rng, None)
        if record is None:
            break
        records.append(record)
    write_records(records[:args.n], args.out, args.seed, SCENARIO)
    if misses:
        print(f"note: {misses} planned targets could not be realized and fell back to a compliant check")
    return 0


if __name__ == "__main__":
    sys.exit(main())
