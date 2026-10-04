"""导诊分诊记录生成器 —— 4B 主力轨，0.8B 作为能力不足的对照。

科室归属与急症判定都由 :data:`SYMPTOMS` 与 :func:`decide` 的规则派生。注意导诊是五个场景里
**语义最难穷举**的一个（科室归属规则不像危急值那样有阈值表），所以本生成器只覆盖典型主诉与
刻意构造的多症状优先级冲突；表述多样性由 generate_data.py 蒸馏补充（见 generators/README.md）。

用法::

    python3 docs/medical/generators/gen_triage.py --n 787 --out data/tri.jsonl --seed 0
"""
import random
import sys

from common import base_parser, labelled, load_spec, write_records

SCENARIO = "triage"

# (症状关键词, 科室, 是否红旗, 是否需人工, 基础紧急度)
# 红旗一律覆盖科室规则并强制 emergency；需人工与红旗解耦（存在高危信号但无红旗时 acuity 仍为 2）。
SYMPTOMS = [
    ("胸痛", "cardiology", True, True, 2), ("胸闷", "cardiology", False, False, 1),
    ("心悸", "cardiology", False, False, 1), ("活动后气促", "cardiology", False, True, 2),
    ("下肢水肿", "cardiology", False, False, 1), ("血压很高", "cardiology", False, True, 2),
    ("咳嗽", "respiratory", False, False, 0), ("咳痰", "respiratory", False, False, 0),
    ("气喘", "respiratory", True, True, 2), ("呼吸困难", "respiratory", True, True, 2),
    ("喘不过气", "respiratory", True, True, 2), ("发热", "respiratory", False, False, 0),
    ("腹痛", "gastroenterology", False, False, 1), ("上腹隐痛", "gastroenterology", False, False, 1),
    ("反酸烧心", "gastroenterology", False, False, 0), ("腹泻", "gastroenterology", False, False, 0),
    ("便秘", "gastroenterology", False, False, 0), ("呕血黑便", "gastroenterology", True, True, 2),
    ("头晕", "neurology", False, False, 1), ("头痛", "neurology", False, False, 1),
    ("肢体麻木", "neurology", True, True, 2), ("言语不清", "neurology", True, True, 2),
    ("意识不清", "neurology", True, True, 2), ("晕厥", "neurology", True, True, 2),
    ("喷射性呕吐", "neurology", True, True, 2),
    ("关节痛", "orthopedics", False, False, 0), ("外伤", "orthopedics", False, False, 1),
    ("腰痛", "orthopedics", False, False, 0), ("行走困难", "orthopedics", False, False, 1),
    ("皮疹", "dermatology", False, False, 0), ("瘙痒", "dermatology", False, False, 0),
    ("皮肤红肿", "dermatology", False, False, 0),
    ("尿频尿急", "urology", False, False, 0), ("尿痛", "urology", False, False, 0),
    ("血尿", "urology", False, True, 1), ("肾绞痛", "urology", True, True, 2),
    ("停经", "obstetrics_gynecology", False, False, 0), ("阴道流血", "obstetrics_gynecology", False, True, 1),
    ("孕期不适", "obstetrics_gynecology", False, False, 1), ("产检", "obstetrics_gynecology", False, False, 0),
    ("视物模糊", "ophthalmology", False, False, 1), ("眼红眼痛", "ophthalmology", False, False, 1),
    ("鼻塞流涕", "ent", False, False, 0), ("咽痛", "ent", False, False, 0),
    ("耳鸣", "ent", False, False, 0),
    ("多饮多尿", "endocrinology", False, False, 1), ("体重明显下降", "endocrinology", False, False, 1),
    ("怕冷乏力", "endocrinology", False, False, 0),
    ("发热咳嗽", "respiratory", False, False, 0), ("腹痛腹泻", "gastroenterology", False, False, 0),
    ("乏力纳差", "general_medicine", False, False, 0), ("反复低热待查", "general_medicine", False, False, 1),
    ("常规复诊", "general_medicine", False, False, 0), ("头晕乏力", "general_medicine", False, False, 0),
    ("儿童发热", "pediatrics", False, False, 1), ("小儿呕吐", "pediatrics", False, False, 1),
    ("高热惊厥", "pediatrics", True, True, 2), ("儿童咳嗽", "pediatrics", False, False, 0),
]

# 儿童优先规则：14 岁以下以发热/咳嗽/呕吐/腹泻为主诉时归儿科，除非存在红旗（红旗已强制 emergency）。
PEDIATRIC = ("发热", "咳嗽", "腹泻", "呕吐", "儿童发热", "小儿呕吐", "儿童咳嗽")
VITALS = ["BP 165/98 mmHg, HR 96 bpm, SpO2 94%", "BP 148/92 mmHg, HR 88 bpm, SpO2 97%",
          "BP 132/84 mmHg, HR 76 bpm, SpO2 98%", "BP 118/72 mmHg, HR 72 bpm, SpO2 99%"]
CHANNELS = ["线下门诊导诊台", "互联网医院线上问诊", "电话预约中心", "自助机引导"]
DURATIONS = ["半天", "1 天", "3 天", "1 周", "2 周", "1 个月", "半年"]
HISTORIES = ["无特殊病史", "高血压 10 年", "2 型糖尿病 8 年", "长期吸烟", "哮喘史",
             "冠心病搭桥术后", "肿瘤放化疗中", "妊娠 28 周", "肾功能不全透析"]


def decide(symptoms, age):
    """The four labels, derived from the symptom table alone.

    Priority order, matching the spec's guidance: any red flag wins and forces emergency; otherwise a patient under 14
    with a pediatric chief complaint goes to pediatrics; otherwise the more urgent / more specialized system wins.
    `acuity` is 2 whenever a human must intervene, 0 only when nothing is urgent, and red_flag implies both.
    """
    red = any(s[2] for s in symptoms)
    human = any(s[3] for s in symptoms)
    if red:
        department, acuity = "emergency", 2
    else:
        acuity = max(s[4] for s in symptoms)
        if age < 14 and any(s[0] in PEDIATRIC for s in symptoms):
            department = "pediatrics"
        else:
            # 排序键：基础紧急度降序，取最专科化的那个系统；同紧急度时按 SYMPTOMS 出现顺序稳定取值。
            best = max(symptoms, key=lambda s: (s[4], -SYMPTOMS.index(s)))
            department, acuity = best[1], max(acuity, best[4])
        if human and acuity < 2:
            acuity = 2
    if acuity == 0:
        human = False  # spec: acuity=0 必须 immediate_human=false
    return {"department": department, "immediate_human": bool(human or red), "acuity": acuity, "red_flag": red}


def build(rng, target=None):
    """One triage record. `target` is a department name, "emergency", or None for whatever comes out.

    Roughly a quarter of the records are built with two symptoms from different systems on purpose, so the model has
    to learn the priority rule instead of a single-system shortcut.
    """
    for _ in range(200):
        n = 2 if (target == "conflict" or rng.random() < 0.25) else 1
        pool = [s for s in SYMPTOMS if target in (None, "conflict") or s[1] == target or (target == "emergency") == s[2]]
        if len(pool) < n:
            continue
        symptoms = rng.sample(pool, n)
        age = rng.choice([2, 6, 11, 17, 26, 34, 41, 52, 58, 63, 67, 71, 78])
        labels = decide(symptoms, age)
        if target and target not in ("conflict",) and labels["department"] != target:
            continue
        state = {
            "patient": f"{'male' if rng.random() < 0.5 else 'female'} {age}",
            "channel": rng.choice(CHANNELS),
            "chief_complaint": "，".join(s[0] for s in symptoms) + "，" + rng.choice(
                ["有点难受", "想尽快看看", "拖了好几天了", "家里人都很着急", "这种情况要紧吗"]),
            "duration": rng.choice(DURATIONS),
            "accompanying": [s[0] for s in symptoms[1:]] or ["无"],
            "history": [rng.choice(HISTORIES)],
            "vitals": rng.choice(VITALS),
            "red_flags": "、".join(s[0] for s in symptoms if s[2]) or "无",
        }
        return labelled(load_spec(SCENARIO), state, labels)
    return None


def plan_targets(n, rng, share=None):
    """标签计划：14 个科室各占一份配额（每科室 >=5% 需要 787 的 5% = 40 条），另加 emergency 与多症状冲突样本。

    显式按科室配额而不是靠症状行数占比，是因为 :func:`build` 的科室归属带有优先级仲裁，行数分布不等于
    最终标签分布 —— 必须先定标签再构造主诉。`share` 仅为与其余生成器的签名对齐而保留，不参与配额计算。
    """
    departments = sorted({s[1] for s in SYMPTOMS})
    plan = []
    for i in range(n):
        bucket = i % 20
        if bucket < 2:
            plan.append("emergency")       # ~10%
        elif bucket < 4:
            plan.append("conflict")        # ~10% 多症状优先级冲突
        else:
            plan.append(departments[(i // 2) % len(departments)])
    rng.shuffle(plan)
    return plan


def main(argv=None):
    parser = base_parser(__doc__.split("\n\n")[0])
    args = parser.parse_args(argv)
    rng = random.Random(args.seed)
    records, misses = [], 0
    for target in plan_targets(args.n, rng):
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
        print(f"note: {misses} planned targets could not be realized and fell back to an unsteered record")
    return 0


if __name__ == "__main__":
    sys.exit(main())
