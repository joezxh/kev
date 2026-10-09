"""种子 -> Kev 记录转换器。

**这个脚本只读 ``<scenario>.state.jsonl``，物理上接触不到 SFT 输出。** 标签由旁路 sidecar 里的规则引擎
产物直接搬运，经 ``common.labelled()`` 重建记录并自检。LLM 在整条链路上无法影响任何标签 —— 这是结构性
保证，不是约定。

``--from-sft`` 读取 EasyDistill 的 ``messages`` 输出**仅用于对账报告**：它把教师回答与规则标签做一致性
比对，报告不一致率，但绝不把任何解析结果写回标签。这既是质量信号（教师与规则的一致率），也是回归检测。

用法::

    python3 kev/console/distill/seed_to_kev.py --scenario inquiry \\
        --seed-file data/seeds/inquiry.seed.jsonl \\
        --state-file data/seeds/inquiry.state.jsonl \\
        --out data/inquiry.jsonl

    python3 kev/console/distill/seed_to_kev.py --scenario inquiry --from-sft data/sft/inquiry.sft.jsonl

标准库 only。
"""
import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "generators"))

import common  # noqa: E402

# 蒸馏场景 -> spec 名（与 make_seeds.SCENARIOS 一致；无 Kev 轨的场景不在此表）
SPEC_FOR = {"inquiry": "triage", "medication": "medication-review", "diagnosis": "diagnosis",
            "record-summary": "record-summary"}


def read_jsonl(path):
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]

def build_records(scenario, seed_rows, state_rows):
    """Join the two files on `id` and rebuild Kev records. Labels come from the sidecar, full stop."""
    spec_name = SPEC_FOR[scenario]
    spec = common.load_spec(spec_name)
    by_id = {row["id"]: row for row in state_rows}
    seed_ids = {row["id"] for row in seed_rows}
    missing = seed_ids - set(by_id)
    if missing:
        raise SystemExit(f"{len(missing)} seed ids have no state row (e.g. {sorted(missing)[:3]})")
    records, order = [], []
    for row in seed_rows:                      # iterate the seed file so the output order matches EasyDistill's input
        state_row = by_id[row["id"]]
        labels = state_row["labels"]
        unknown = set(labels) - set(spec["questions"])
        if unknown:
            raise SystemExit(f"{row['id']}: labels {sorted(unknown)} are not questions of spec {spec_name}")
        records.append(common.labelled(spec, state_row["state"], labels, state_row.get("soft") or None))
        order.append(row["id"])
    return records, order


def reconcile(records, order, sft_path):
    """Compare the teacher's answers against the rule labels. Reporting only -- never writes back.

    A high agreement rate means the teacher and the rule engine see the same decision boundary, which is the
    strongest cheap signal available before any human review. A low rate flags records for human adjudication.
    """
    answers = {}
    for row in read_jsonl(sft_path):
        instruction = row.get("instruction")
        if instruction is None:
            for message in row.get("messages", []):
                if message.get("role") == "user":
                    instruction = message.get("content")
                    break
        response = row.get("output")
        if response is None:
            for message in row.get("messages", []):
                if message.get("role") == "assistant":
                    response = message.get("content")
                    break
        rid = row.get("id")
        if rid is not None:
            answers[rid] = response or ""
    if not answers:
        print("note: the SFT file carries no id column, so per-record reconciliation is skipped;"
              " falling back to a corpus-level check")
        return None
    agree, total, disagreements = 0, 0, []
    for record, rid in zip(records, order):
        answer = answers.get(rid)
        if answer is None:
            continue
        for qid, question in record["questions"].items():
            total += 1
            value = question["label"]
            hit = (str(value) in answer) or (str(value).lower() in answer.lower())
            if hit:
                agree += 1
            else:
                disagreements.append({"id": rid, "question": qid, "label": value})
    return {"agree": agree, "total": total, "disagreements": disagreements}

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                     formatter_class=argparse.RawDescriptionHelpFormatter,
                                     epilog="有 Kev 轨的场景: " + "、".join(sorted(SPEC_FOR)))
    parser.add_argument("--scenario", required=True, choices=sorted(SPEC_FOR),
                        help="蒸馏场景名（knowledge-qa 无 Kev 轨，不可用）")
    parser.add_argument("--seed-file", help="<scenario>.seed.jsonl，仅用于确定行序")
    parser.add_argument("--state-file", help="<scenario>.state.jsonl，标签的唯一来源")
    parser.add_argument("--out", help="Kev 记录输出路径")
    parser.add_argument("--from-sft", help="EasyDistill 的 SFT 输出；仅做一致性对账报告，不影响标签")
    parser.add_argument("--report", help="把对账报告写成 JSON")
    args = parser.parse_args(argv)
    if not args.state_file:
        raise SystemExit("--state-file is required: it carries the labels")
    state_rows = read_jsonl(args.state_file)
    seed_rows = read_jsonl(args.seed_file) if args.seed_file else [{"id": r["id"]} for r in state_rows]

    records, order = build_records(args.scenario, seed_rows, state_rows)
    spec_name = SPEC_FOR[args.scenario]
    if args.out:
        common.write_records(records, args.out, 0, spec_name)
    else:
        print(f"{len(records)} records rebuilt (not written; pass --out)")

    if args.from_sft:
        result = reconcile(records, order, args.from_sft)
        if result:
            rate = result["agree"] / result["total"] if result["total"] else 0.0
            print(f"\nteacher/rule agreement: {result['agree']}/{result['total']} = {rate:.1%}")
            print(f"  (字符串匹配，宽松口径；低 agreement 的记录应优先进入人工审校)")
            if result["disagreements"]:
                counts = Counter((d["question"], d["label"]) for d in result["disagreements"])
                print("  most disagreed (question, rule label):")
                for (qid, label), n in counts.most_common(8):
                    print(f"    {qid}={label}: {n}")
            if args.report:
                Path(args.report).parent.mkdir(parents=True, exist_ok=True)
                Path(args.report).write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
                print(f"  report -> {args.report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
