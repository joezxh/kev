"""诊断建议记录生成器 —— 4B 主力轨（鉴别方向需要语义推断，0.8B 知识不足）。

标签全部由 :data:`FINDINGS` 与 :func:`derive` 的规则派生。注意诊断建议的规则不是阈值而是
**方向优先级仲裁**：多个系统同时有线索时，按「危险信号 > 基础紧急度 > 专科化程度」取胜者，
这正是本场景要教会模型的部分（guidance 里的仲裁规则）。

日期派生字段一律预计算（``days_on_symptom`` 是整数），规避 0.8B 的日期算术弱项。

用法::

    python3 docs/medical/generators/gen_diagnosis.py --n 787 --out data/diag.jsonl --seed 0
"""
import random
import sys

from common import base_parser, labelled, load_spec, write_records

SCENARIO = "diagnosis"

# (线索关键词, 鉴别方向, 基础紧急度, 是否需检查确认, 是否危险信号)
# 危险信号一律覆盖方向规则：urgency 固定 3，且 needs_test 必为 true。
FINDINGS = [
    ("持续胸痛", "cardiovascular", 2, True, True),
    ("胸痛伴放射至左肩背", "cardiovascular", 3, True, True),
    ("心悸", "cardiovascular", 1, True, False),
    ("活动后气促", "cardiovascular", 2, True, False),
    ("下肢水肿", "cardiovascular", 1, True, False),
    ("血压显著升高", "cardiovascular", 2, True, False),
    ("咳嗽咳痰", "respiratory", 1, True, False),
    ("发热伴咳嗽", "respiratory", 1, True, False),
    ("呼吸困难", "respiratory", 2, True, True),
    ("喘憋不能平卧", "respiratory", 3, True, True),
    ("腹痛", "gastrointestinal", 1, True, False),
    ("上腹隐痛餐后加重", "gastrointestinal", 1, True, False),
    ("反酸烧心", "gastrointestinal", 0, False, False),
    ("呕血黑便", "gastrointestinal", 3, True, True),
    ("头痛", "neurologic", 1, True, False),
    ("眩晕", "neurologic", 1, True, False),
    ("肢体麻木无力", "neurologic", 2, True, True),
    ("言语不清", "neurologic", 3, True, True),
    ("意识改变", "neurologic", 3, True, True),
    ("尿频尿急尿痛", "urinary", 0, True, False),
    ("血尿", "urinary", 1, True, False),
    ("肾绞痛", "urinary", 2, True, False),
    ("排尿困难", "urinary", 0, True, False),
    ("多饮多尿", "endocrine", 1, True, False),
    ("体重明显下降", "endocrine", 1, True, False),
    ("怕冷乏力", "endocrine", 0, True, False),
    ("血糖明显升高", "endocrine", 1, True, False),
    ("关节痛", "musculoskeletal", 0, False, False),
    ("腰痛", "musculoskeletal", 0, False, False),
    ("外伤", "musculoskeletal", 1, True, False),
    ("行走困难", "musculoskeletal", 1, False, False),
    ("贫血貌", "hematologic_oncologic", 1, True, False),
    ("淋巴结肿大", "hematologic_oncologic", 1, True, False),
    ("盗汗消瘦", "hematologic_oncologic", 2, True, False),
    ("乏力伴牙龈出血", "hematologic_oncologic", 2, True, True),
]

# 检验值与方向的对应：出现在 labs 里会强化该方向，但不单独决定方向（方向由主诉线索仲裁），
# 存在的意义是让「主诉含糊但检验有指向」这类样本成为可能。
LAB_HINTS = {
    "cardiovascular": {"肌钙蛋白": ["0.9 ng/mL", "4.2 ng/mL"], "NT-proBNP": ["3200 pg/mL", "980 pg/mL"]},
    "respiratory": {"D-二聚体": ["2.8 mg/L FEU", "5.1 mg/L FEU"]},
    "endocrine": {"空腹血糖": ["11.2 mmol/L", "16.4 mmol/L"], "TSH": ["8.2 mIU/L"]},
    "hematologic_oncologic": {"血红蛋白": ["68 g/L", "91 g/L"], "血小板": ["38 ×10^9/L"]},
    "urinary": {"尿白细胞": ["阳性", "++"], "肌酐": ["168 umol/L"]},
    "neurologic": {"头颅 CT": ["未见异常", "未见明显异常"]},
    "gastrointestinal": {"便潜血": ["阳性"], "胃镜": ["慢性非萎缩性胃炎"]},
}

VITALS = ["BP 148/92 mmHg, HR 96 bpm, RR 20 /min, SpO2 94%",
          "BP 132/84 mmHg, HR 76 bpm, RR 16 /min, SpO2 98%",
          "BP 105/65 mmHg, HR 118 bpm, RR 24 /min, SpO2 91%",
          "BP 165/100 mmHg, HR 88 bpm, RR 18 /min, SpO2 96%",
          "BP 92/58 mmHg, HR 132 bpm, RR 26 /min, SpO2 89%"]
IMAGING = ["未做", "胸片未见明显异常", "腹部超声示肝脏回声增粗", "头颅 CT 未见异常",
           "胸部 CT 示双肺纹理增粗", "心脏超声示左室舒张功能减低"]
COMORBID = [["无"], ["高血压 10 年"], ["2 型糖尿病 8 年", "高血压 5 年"], ["慢性阻塞性肺疾病"],
            ["冠心病搭桥术后"], ["肿瘤放化疗中"], ["慢性肾病 3 期"], ["妊娠 28 周"]]
DURATIONS = [("3 天", 3), ("1 周", 7), ("2 周", 14), ("1 个月", 30), ("3 个月", 90)]
TONE = ["有点难受", "想尽快看看", "拖了好几天了", "家里人都很着急", "这种情况要紧吗", "反复发作"]


def derive(presentations, has_imaging_abnormal):
    """The four labels, derived from the presentation lines alone.

    Priority, matching the spec's guidance: any red flag forces urgency 3 (and needs_test true, since a red flag
    still needs a workup); otherwise the most urgent presentation wins, and ties go to the more specialised system by
    table order. `undirected` means the presentations point at two systems with equal urgency and no tie-break.
    """
    red = any(p[4] for p in presentations)
    needs = any(p[3] for p in presentations)
    if red:
        return {"differential_direction": "undirected" if not presentations else _pick(presentations),
                "needs_test": True, "urgency": 3, "red_flag": True}
    urgency = max(p[2] for p in presentations)
    top = [p for p in presentations if p[2] == urgency]
    directions = {p[1] for p in top}
    if len(top) > 1 and len(directions) > 1:
        # 同紧急度且跨系统：按表顺序取最专科化的那个（与 gen_triage 的仲裁一致）
        best = min(top, key=lambda p: FINDINGS.index(p))
        direction, needs_test = best[1], True
    else:
        direction = top[0][1]
        needs_test = needs
    if has_imaging_abnormal and direction == "undirected":
        direction = "undirected"
    if urgency == 0 and not needs_test:
        needs_test = False
    return {"differential_direction": direction, "needs_test": bool(needs_test),
            "urgency": urgency, "red_flag": False}


def _pick(presentations):
    """Red-flag path: still report a direction when the presentations agree, else undirected."""
    directions = {p[1] for p in presentations}
    return presentations[0][1] if len(directions) == 1 else "undirected"


def build(rng, target=None):
    """One diagnosis record. `target` is a differential_direction, "undirected", or None."""
    for _ in range(200):
        pool = [f for f in FINDINGS if target in (None, "undirected") or f[1] == target]
        if not pool:
            return None
        presentations = rng.sample(pool, 2 if (target == "undirected" or rng.random() < 0.3) else 1)
        age = rng.choice([3, 9, 17, 26, 34, 41, 52, 58, 63, 67, 71, 78])
        sex = "male" if rng.random() < 0.5 else "female"
        duration_text, days = rng.choice(DURATIONS)
        imaging = rng.choice(IMAGING)
        imaging_abnormal = imaging not in ("未做", "胸片未见明显异常", "头颅 CT 未见异常")
        labels = derive(presentations, imaging_abnormal)
        if target and target != "undirected" and labels["differential_direction"] != target:
            continue
        if target == "undirected" and labels["differential_direction"] != "undirected":
            continue
        labs = {}
        hinted = rng.choice([f[1] for f in presentations] + [None, None])
        if hinted in LAB_HINTS:
            for name, values in LAB_HINTS[hinted].items():
                if rng.random() < 0.75:
                    labs[name] = rng.choice(values)
        state = {
            "patient": f"{sex} {age}",
            "chief_complaint": "，".join(p[0] for p in presentations) + "，" + rng.choice(TONE),
            "vitals": rng.choice(VITALS),
            "labs": labs or {"血常规": "未见明显异常"},
            "imaging": imaging,
            "comorbidities": rng.choice(COMORBID),
            "duration": f"{duration_text}（已 {days} 天）",
        }
        return labelled(load_spec(SCENARIO), state, labels)
    return None


def plan_targets(n, rng, share=None):
    """标签计划：9 个方向各占配额（每项 >=5% 需 787 的 5% = 40 条），另留 undirected 与无检验指向样本。

    `share` 仅为与其余生成器签名对齐而保留。undirected 刻意只给约 8%：它需要两个同紧急度且跨系统的
    线索同时命中，构造概率低；给多了会导致 realization 失败率上升。
    """
    directions = sorted({f[1] for f in FINDINGS})
    plan = []
    for i in range(n):
        bucket = i % 25
        if bucket < 2:
            plan.append("undirected")   # ~8%
        else:
            plan.append(directions[(i // 2) % len(directions)])
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
