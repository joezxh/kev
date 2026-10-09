"""病历摘要记录生成器 —— 双尺寸主力轨（完整性判定是规则封闭的，0.8B 也能学）。

标签由 :data:`ELEMENT_SEVERITY` 与 :func:`derive` 派生。核心不变式是 spec guidance 的那组强对应：
``missing_element=none`` 当且仅当六要素齐全；``needs_coder_review`` 当且仅当 ``severity >= 2``；
``coding_confidence`` 完全由 ``severity`` 派生。这三条让标签无法漂移。

摘要正文一律**不进 state** —— 病历全文远超 384 token，state 只承载要素级的结构化摘录，
这与 docs/medical/data-format.md 里病历编码的「两级拆分」是同一个理由。

用法::

    python3 kev/console/generators/gen_record_summary.py --n 787 --out data/rs.jsonl --seed 0
"""
import random
import sys

from common import base_parser, labelled, load_spec, write_records

SCENARIO = "record-summary"

# 六要素 -> 缺失时的严重度。数值本身即标签，不随机。
ELEMENT_SEVERITY = {
    "chief_complaint": 1,
    "presenting_history": 1,
    "examination": 2,
    "diagnosis": 2,
    "medication": 2,
    "plan": 3,
}
ELEMENTS = list(ELEMENT_SEVERITY)

# (系统, 诊断类别, 主诉, 现病史要点, 查体, 诊断列表, 合规用药列表, 计划)
CASES = [
    ("心血管", "cardiac", "反复胸闷 2 个月", "2 个月前起活动后胸闷，休息后缓解，无胸痛",
     "心率 82 bpm，心律齐，未闻及杂音", ["稳定型心绞痛", "高血压 2 级"],
     ["阿司匹林 100 mg qd", "美托洛尔 47.5 mg qd"], "完善冠脉 CTA，评估血运重建指征"),
    ("消化", "gastric", "反复上腹痛 3 个月", "3 个月来上腹隐痛，餐后加重，伴嗳气，无反酸黑便",
     "上腹轻压痛，无反跳痛", ["慢性胃炎", "幽门螺杆菌感染待排"],
     ["雷贝拉唑 20 mg qd", "阿莫西林 1000 mg tid"], "胃镜检查加幽门螺杆菌呼气试验"),
    ("呼吸", "pulmonary", "反复咳嗽咳痰 3 周", "3 周前受凉后出现咳嗽，咳白色黏痰，无发热盗汗",
     "双肺呼吸音粗，未闻及明显干湿啰音", ["社区获得性肺炎待排"],
     ["阿莫西林 1000 mg tid", "氨溴索 30 mg tid"], "胸部 CT 评估感染范围，必要时痰培养"),
    ("神经", "neuro", "反复头晕 2 周", "2 周来间断头晕，与体位相关，无肢体无力，无言语不清",
     "神经系统查体未见明显异常", ["后循环缺血待排", "高血压 1 级"],
     ["氢氯噻嗪 12.5 mg qd"], "头颅 MRI 加 MRA，评估后循环"),
    ("内分泌", "metabolic", "多饮多尿 2 个月", "2 个月来多饮多尿，体重下降约 5 kg，无明显多食",
     "BMI 21.4 kg/m2，甲状腺无肿大", ["2 型糖尿病", "糖尿病肾病待排"],
     ["二甲双胍 500 mg bid"], "空腹及餐后血糖谱，糖化血红蛋白，尿微量白蛋白"),
    ("血液肿瘤", "heme", "乏力伴牙龈出血 1 个月", "1 个月来乏力渐重，伴牙龈出血，无发热，无骨痛",
     "面色苍白，脾肋下 2 cm 可及", ["再生障碍性贫血待排", "急性白血病待排"],
     ["环孢素 100 mg bid"], "骨髓穿刺加免疫分型，血细胞减少原因待查"),
    ("泌尿", "urinary", "反复尿频尿痛 5 天", "5 天来尿频尿急尿痛，排尿末灼热，无血尿",
     "膀胱区轻压痛，肾区叩击痛阴性", ["急性膀胱炎"],
     ["左氧氟沙星 500 mg qd"], "尿常规加尿培养，泌尿系超声"),
    ("骨科", "ortho", "右膝关节肿痛 2 周", "2 周前无明显诱因出现右膝肿痛，步行加重，上下楼梯困难",
     "右膝轻度肿胀，浮髌试验阴性", ["右膝关节积液待排"],
     ["塞来昔布 200 mg bid"], "膝关节超声加 MRI，明确积液性质"),
    ("妇产", "gyn", "月经量增多 3 个月", "3 个月来月经量较前增多约一倍，周期仍规则，无痛经",
     "外阴及阴道无异常出血", ["子宫肌瘤待排", "贫血待查"],
     ["氨甲环酸 500 mg tid", "铁剂"], "妇科超声评估肌瘤大小，纠正贫血"),
    ("儿科", "peds", "发热 3 天", "3 天前发热，最高 39.2 度，伴咳嗽，无呕吐腹泻，精神尚可",
     "咽部充血，双肺呼吸音清", ["急性上呼吸道感染", "发热待查"],
     ["布洛芬 100 mg q4h（按体重）"], "血常规加 CRP，必要时胸片"),
]

# 不相关类别的用药，用于制造「诊断与用药不符」（触发编码员复核）
MISMATCH_DRUGS = ["地高辛 0.25 mg qd", "华法林 2.5 mg qd", "左甲状腺素钠 50 ug qd",
                  "沙丁胺醇吸入 2 喷 q8h", "呋塞米 20 mg qd"]
STAGES = ["入院记录", "首次病程记录", "阶段小结", "出院小结"]

# 上游医师的随手记录：既是真实病历里必有的自由文本，也把状态组合数放大一个量级，
# 否则 10 个病例模板 × 13 个年龄 × 2 个性别 × 4 个阶段只有约 1000 种组合，
# 787 条记录会撞出约 40 条重复 state（split_data 会丢弃它们，白白损失数据）。
NOTES = ["患者自述症状较前无明显变化，一般情况可，饮食睡眠尚可",
         "查房时患者精神状态可，对答切题，未诉特殊不适",
         "今日体温正常，未诉新发不适，继续原方案",
         "患者情绪稳定，家属已充分告知病情及后续注意事项",
         "晨间查房见患者已下床活动，症状未见加重",
         "记录时患者正在睡眠，未唤醒，未见异常",
         "主管医师查房意见：既往史及过敏史已再次核对无误",
         "患者要求明日复查，已口头告知需空腹抽血",
         "经上级医师查房意见，已调整用药并记录于医嘱",
         "自动导入住院时间与住院次数，未做人工修改"]


def derive(missing, mismatch):
    """The four labels, from which element is absent plus whether the drug list contradicts the diagnosis."""
    if mismatch:
        # guidance: 无要素缺失但用药与诊断不符时也要复核，严重度取 2
        return {"missing_element": "none", "needs_coder_review": True, "severity": 2, "coding_confidence": 1}
    if missing is None:
        return {"missing_element": "none", "needs_coder_review": False, "severity": 0, "coding_confidence": 2}
    severity = ELEMENT_SEVERITY[missing]
    return {"missing_element": missing,
            "needs_coder_review": severity >= 2,
            "severity": severity,
            "coding_confidence": 2 if severity == 0 else (0 if severity == 3 else 1)}


def build(rng, target=None):
    """One record. `target` is a missing-element key, "none" for a complete summary, or None."""
    for _ in range(200):
        if target == "mismatch":
            missing, mismatch = None, True
        elif target in (None, "none"):
            missing, mismatch = None, False
        else:
            missing, mismatch = target, False
        _, _, complaint, history, exam, diagnosis, drugs, plan = rng.choice(CASES)
        drugs = list(drugs)
        if mismatch:
            drugs.append(rng.choice(MISMATCH_DRUGS))
        age = rng.choice([3, 9, 17, 26, 34, 41, 52, 58, 63, 67, 71, 78])
        state = {
            "patient": f"{'male' if rng.random() < 0.5 else 'female'} {age}",
            "stage": rng.choice(STAGES),
            "note": rng.choice(NOTES),
            "chief_complaint": "" if missing == "chief_complaint" else complaint,
            "presenting_history": "" if missing == "presenting_history" else history,
            "examination": "" if missing == "examination" else exam,
            "diagnosis": [] if missing == "diagnosis" else diagnosis,
            "medications": [] if missing == "medication" else drugs,
            "plan": "" if missing == "plan" else plan,
            "missing_element": "无" if missing is None else missing,
        }
        return labelled(load_spec(SCENARIO), state, derive(missing, mismatch))
    return None


def plan_targets(n, rng, share=None):
    """标签计划：none + 6 个缺失要素共 7 个选项，各需 >=5%（787 的 5% = 40 条）。

    `none` 与六个缺失要素轮转分配；mismatch 不占选项（它并入 none 标签），但仍要出现足够样本让
    「用药与诊断不符」这条分支被学到，固定给约 10%。`share` 仅为与其余生成器签名对齐而保留。
    """
    keys = ["none"] + ELEMENTS
    plan = []
    for i in range(n):
        if i % 10 == 9:
            plan.append("mismatch")
        else:
            plan.append(keys[(i * 3 // 10) % len(keys)])
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
        print(f"note: {misses} planned targets could not be realized and fell back to a complete summary")
    return 0


if __name__ == "__main__":
    sys.exit(main())
