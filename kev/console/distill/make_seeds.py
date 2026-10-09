"""种子指令生成器 —— 蒸馏层的入口。

**核心设计：LLM 永不接触标签。** 流水线是反的：规则引擎先采样 state 并算出标签，再把 state 渲染成
种子 instruction 交给 EasyDistill，让百灵只写参考回答。Kev 标签的唯一来源是规则引擎，不经 LLM。

用法::

    python3 kev/console/distill/make_seeds.py --scenario inquiry --n 500 --out-dir data/seeds
    python3 kev/console/distill/make_seeds.py --all --n 500 --out-dir data/seeds

标准库 only，与 kev/console/generators/ 的其余脚本一致。
"""
import argparse
import json
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "generators"))

import gen_diagnosis as dg  # noqa: E402
import gen_medication_review as mr  # noqa: E402
import gen_record_summary as rs  # noqa: E402
import gen_triage as tri  # noqa: E402

# 蒸馏场景 -> (规则引擎模块, 该模块的 spec 名, 是否产出 Kev 轨)
# knowledge-qa 是唯一没有 Kev 轨的场景：Kev 只在预声明选项集上输出概率、不生成任何 token，
# 因此开放式医学问答在结构上无法成为 Kev 任务，只走生成式轨。
SCENARIOS = {
    "inquiry": (tri, "triage", True),
    "medication": (mr, "medication-review", True),
    "diagnosis": (dg, "diagnosis", True),
    "record-summary": (rs, "record-summary", True),
    "knowledge-qa": (None, None, False),
}

SYSTEM_PROMPTS = {
    "inquiry": "你是一位谨慎的临床分诊助手。回答要体现专业分诊逻辑：先识别危险信号，再说明需要补充哪些信息，"
               "最后给出建议就诊科室与紧急程度。回答必须包含「若出现以下情况请立即就医」一类的安全提示。"
               "不做确定性诊断。",
    "medication": "你是一位临床药师。回答要说明该药的适应证、用法用量、注意事项、相互作用与禁忌人群，"
                  "并明确指出是否需要药师复核。不给出超出说明书范围的个体化剂量调整建议。",
    "diagnosis": "你是一位临床医师。回答要给出初步鉴别方向、依据、建议进一步检查与就诊时机，"
                 "并说明当前信息的不确定性。不得给出确定性诊断结论。",
    "record-summary": "你是一位病历质控助手。回答要按主诉、现病史要点、查体、诊断、用药、诊疗计划六要素"
                      "核对摘要，指出缺失项与是否需要编码员复核。不补写病历中不存在的要素。",
    "knowledge-qa": "你是一位医学知识助手。回答要准确、简洁，注明适用范围与时效性，"
                    "并在涉及诊疗决策时提示以临床判断与最新指南为准。不得编造文献或指南出处。",
}

# 种子指令的提问模板：把结构化 state 渲染成一段自然语言提问。
# 只描述事实，不透露任何标签线索 —— 标签是规则引擎的事，LLM 不参与。
ASK = {
    "triage": "以下是一位患者到院分诊台的情况。请判断应该分诊到哪个科室、是否需要立即人工介入、"
              "紧急程度如何，以及是否存在危险信号。\n{state}",
    "medication-review": "以下是一位患者的用药医嘱与背景。请审核该用药是否合规、是否需要药师复核、"
                         "以及存在哪类用药问题。\n{state}",
    "diagnosis": "以下是一位患者首诊时的结构化记录。请给出初步鉴别方向、说明是否需要影像或检验、"
                 "判断紧急程度，并指出是否存在危险信号。\n{state}",
    "record-summary": "以下是一份住院病历的结构化摘录。请核对摘要要素是否完整、是否需要编码员复核、"
                      "缺陷严重程度如何，以及做诊断编码的置信档位。\n{state}",
}


def render_state(state):
    """A state object -> the `key: value` lines Kev itself would render, plus a readable header.

    Uses the same shape Kev uses (kev.api.render flattens objects into `key: value` lines), so the teacher model
    reads the same surface the student model will be trained on. Field names stay verbatim because they are part of
    the model's input contract.
    """
    lines = []
    for key, value in state.items():
        if isinstance(value, dict):
            inner = "，".join(f"{k} {v}" for k, v in value.items())
            lines.append(f"{key}：{inner}")
        elif isinstance(value, list):
            lines.append(f"{key}：" + ("、".join(str(v) for v in value) if value else "无"))
        else:
            lines.append(f"{key}：{value}" if value not in ("", None) else f"{key}：未记录")
    return "\n".join(lines)


def one_record(module, rng, target=None):
    """Call a generator's build() and normalise its return shape.

    `gen_critical_value.build()` returns `(record, handle)`; every other generator returns a bare record. Without
    this normalisation the first scenario wired up would crash.
    """
    built = module.build(rng, target)
    return built[0] if isinstance(built, tuple) else built


def plan_for(module, n, rng):
    """The generator's own label quota, so seeds carry the same class balance the Kev track needs.

    Signatures differ (`gen_triage.plan_targets` takes no share, the others do), hence the TypeError probe.
    """
    fn = getattr(module, "plan_targets", None)
    if fn is None:
        return [None] * n
    try:
        return fn(n, rng, 0.5)
    except TypeError:
        return fn(n, rng)

def write_jsonl(rows, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return path


def knowledge_qa_records(n, rng):
    """The pure-generative track: open medical questions with no Kev counterpart.

    Built from a knowledge-point table so the topic mix is explicit and reproducible rather than whatever the
    teacher model happens to like. Kev cannot consume these: it only scores pre-declared options.
    """
    topics = [
        ("诊断学", "胸痛与胸闷在鉴别上最关键的五个问诊点是什么？"),
        ("药理学", "华法林与哪些常见药物存在显著相互作用？机制是什么？"),
        ("生理学", "成人静息状态下正常一分钟呼吸频率与潮气量的范围是多少？"),
        ("病理生理", "休克的分期机制与血流动力学特征是什么？"),
        ("内科学", "2 型糖尿病一线用药的选择依据与主要禁忌是什么？"),
        ("外科学", "急性阑尾炎典型McBurney 点压痛的意义与局限是什么？"),
        ("儿科学", "婴幼儿发热的常见病因谱与按年龄的鉴别思路有何不同？"),
        ("妇产科学", "妊娠期高血压疾病与妊娠期糖尿病的诊断标准差异是什么？"),
        ("影像学", "胸片与胸部 CT 在肺结节评估中的分工是什么？"),
        ("检验医学", "血钾危急值与常规参考区间差在哪里，为什么这样设？"),
        ("微生物学", "经验性抗菌治疗中覆盖革兰阴性菌与阳性球菌的常见选择逻辑是什么？"),
        ("免疫学", "自身免疫性肝炎与病毒性肝炎在肝功能上的鉴别要点是什么？"),
    ]
    rows = []
    for i in range(n):
        field, question = topics[i % len(topics)]
        rows.append({"id": f"knowledge-qa-{i:06d}", "scenario": "knowledge-qa", "topic": field,
                     "question": question,
                     "labels": {}, "state": {"topic": field, "question": question}})
    rng.shuffle(rows)
    return rows


def generate(scenario, n, rng):
    """Return (seed_rows, state_rows) for one scenario. `id` is the only join key."""
    module, spec, has_kev = SCENARIOS[scenario]
    if not has_kev:
        state_rows = knowledge_qa_records(n, rng)
        seed_rows = [{"id": r["id"], "instruction": r["state"]["question"],
                      "system": SYSTEM_PROMPTS[scenario]} for r in state_rows]
        return seed_rows, state_rows
    seed_rows, state_rows = [], []
    for target in plan_for(module, n, rng):
        record = one_record(module, rng, target)
        if record is None:
            record = one_record(module, rng, None)
        if record is None:
            continue
        rid = f"{scenario}-{len(seed_rows):06d}"
        seed_rows.append({"id": rid, "instruction": ASK[spec].format(state=render_state(record["state"])),
                          "system": SYSTEM_PROMPTS[scenario]})
        state_rows.append({"id": rid, "scenario": scenario, "state": record["state"],
                           "labels": {qid: q["label"] for qid, q in record["questions"].items()},
                           "soft": {qid: q["target"] for qid, q in record["questions"].items() if "target" in q}})
    return seed_rows, state_rows

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                     formatter_class=argparse.RawDescriptionHelpFormatter,
                                     epilog="场景: " + "、".join(SCENARIOS) + "（--all 跑全部）")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--scenario", choices=sorted(SCENARIOS), help="单个场景")
    group.add_argument("--all", action="store_true", help="全部五个场景")
    parser.add_argument("--n", type=int, default=500, help="每个场景的种子条数（Tier A 建议 500）")
    parser.add_argument("--out-dir", default="data/seeds", help="输出目录")
    parser.add_argument("--seed", type=int, default=0, help="同 seed 复现同一批种子")
    args = parser.parse_args(argv)

    scenarios = sorted(SCENARIOS) if args.all else [args.scenario]
    out = Path(args.out_dir)
    for scenario in scenarios:
        rng = random.Random(args.seed)
        seed_rows, state_rows = generate(scenario, args.n, rng)
        if len(seed_rows) != len(state_rows):
            raise SystemExit(f"{scenario}: seed/state 行数不一致（{len(seed_rows)} vs {len(state_rows)}）")
        write_jsonl(seed_rows, out / f"{scenario}.seed.jsonl")
        write_jsonl(state_rows, out / f"{scenario}.state.jsonl")
        has_kev = SCENARIOS[scenario][2]
        print(f"{scenario}: {len(seed_rows)} seeds -> {out / f'{scenario}.seed.jsonl'}")
        print(f"{scenario}: {len(state_rows)} states -> {out / f'{scenario}.state.jsonl'}"
              f"  (Kev 轨: {'有' if has_kev else '无，纯生成式'})")
    print(f"\nnext: easydistill --config kev/console/distill/configs/{scenarios[0]}.yaml"
          f"   (把 config 里的 dataset 路径指向 {out})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
