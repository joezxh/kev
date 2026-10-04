"""金标集抽取与双模型分歧审计。

纯蒸馏场景最大的风险是「开发集也是合成的，闭环自证」。本工具提供两道防线：

1. ``sample``  —— 从已生成的数据里**分层抽样**出一批待人工审校的记录（按每个问题的标签分层），
   审校签字后作为金标，用 ``split_data.py --holdout`` 接入：对半分进 calibration 与 development，
   永不进 train。这是终评的唯一依据。
2. ``audit``   —— 比对两份独立标注（通常是两个不同厂商模型对同一批 state 的标注），输出不一致索引与
   分歧率。分歧率可作为蒸馏质量的持续监控指标，分歧样本优先进入人工审校池。

用法::

    python3 docs/medical/generators/make_goldset.py sample data/cv.jsonl --n 200 --out data/cv.gold.jsonl
    python3 docs/medical/generators/make_goldset.py audit data/a.jsonl data/b.jsonl
"""
import argparse
import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

SKILL_SCRIPTS = Path(__file__).resolve().parents[3] / "skills/kev-finetune/scripts"
if str(SKILL_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SKILL_SCRIPTS))
import split_data  # noqa: E402


def read(path):
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def write(records, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return path


def stratum(record):
    """A record's stratification key: the sorted label tuple, so every label combo appears in the sample."""
    return tuple(sorted((qid, split_data.label_key(q)) for qid, q in record["questions"].items()))


def sample(records, n, seed):
    """Stratified sample: round-robin over label combinations, then fill the remainder evenly.

    A plain random sample of a balanced file would work, but stratifying means the审校 batch covers rare label
    combinations (the ones most likely to be wrong) instead of spending all its budget on common ones.
    """
    rng = random.Random(seed)
    buckets = defaultdict(list)
    for record in records:
        buckets[stratum(record)].append(record)
    for bucket in buckets.values():
        rng.shuffle(bucket)
    keys = sorted(buckets)
    rng.shuffle(keys)
    picked, i = [], 0
    while len(picked) < n and any(buckets[k] for k in keys):
        key = keys[i % len(keys)]
        if buckets[key]:
            picked.append(buckets[key].pop())
        i += 1
        if i > n * len(keys) * 2:
            break
    return picked[:n]


def disagreement(a_records, b_records):
    """Index disagreements by normalized state, so the two files may differ in order or in extra fields."""
    def index(records):
        out = {}
        for record in records:
            out[split_data.state_key(record["state"])] = record
        return out

    left, right = index(a_records), index(b_records)
    shared = sorted(set(left) & set(right))
    per_question, rows = Counter(), []
    for key in shared:
        for qid in left[key]["questions"]:
            if qid not in right[key]["questions"]:
                continue
            lk = split_data.label_key(left[key]["questions"][qid])
            rk = split_data.label_key(right[key]["questions"][qid])
            per_question[qid] += 1
            if lk != rk:
                rows.append({"state": left[key]["state"], "question": qid, "a": lk, "b": rk})
    total = sum(per_question.values())
    return rows, per_question, len(shared)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p_sample = sub.add_parser("sample", help="stratified sample for human review")
    p_sample.add_argument("data", help="generated labelled JSONL")
    p_sample.add_argument("--n", type=int, default=200, help="records to sample; 150-250 is the useful range")
    p_sample.add_argument("--seed", type=int, default=0)
    p_sample.add_argument("--out", required=True, help="gold-set JSONL to write (edit labels, then use as --holdout)")

    p_audit = sub.add_parser("audit", help="compare two independent labellings")
    p_audit.add_argument("a", help="first labelled JSONL")
    p_audit.add_argument("b", help="second labelled JSONL")
    p_audit.add_argument("--out", default="", help="optional JSONL for the disagreeing records")
    p_audit.add_argument("--threshold", type=float, default=0.05,
                         help="exit non-zero when the disagreement rate exceeds this, so CI can gate on it")

    args = parser.parse_args(argv)
    if args.command == "sample":
        records = read(args.data)
        picked = sample(records, args.n, args.seed)
        write(picked, args.out)
        print(f"{len(picked)} of {len(records)} records -> {args.out}")
        print("label coverage in the sample:")
        for qid, table in sorted(_table(picked).items()):
            total = sum(table.values())
            print(f"  {qid}: " + ", ".join(f"{k}={v}" for k, v in table.most_common()))
        print("next: have a clinician/pharmacist review each record against the spec's guidance, edit the labels,")
        print("      then: split_data.py <generated>.jsonl --out data/x --holdout <this file>")
        return 0

    rows, per_question, shared = disagreement(read(args.a), read(args.b))
    total = sum(per_question.values())
    print(f"compared {shared} shared states, {total} question labels")
    rates = {}
    for qid, count in sorted(per_question.items()):
        bad = sum(1 for r in rows if r["question"] == qid)
        rates[qid] = bad / count if count else 0.0
        print(f"  {qid}: {bad}/{count} disagree ({rates[qid]:.1%})")
    overall = len(rows) / total if total else 0.0
    print(f"overall disagreement {len(rows)}/{total} = {overall:.1%}")
    if args.out and rows:
        by_state = defaultdict(list)
        for row in rows:
            by_state[split_data.state_key(row["state"])].append(
                {"question": row["question"], "a": row["a"], "b": row["b"]})
        states = {split_data.state_key(r["state"]): r["state"] for r in read(args.a)}
        write([{"state": states[key], "disagreements": value} for key, value in by_state.items()], args.out)
        print(f"{len(by_state)} disagreeing states -> {args.out}")
    # Gate on the worst question, not the overall rate: a 3% average can hide one question at 13%, and in a medical
    # workflow it is the per-question rate that decides whether the labellers can be trusted on that question.
    worst_qid, worst = max(rates.items(), key=lambda kv: kv[1]) if rates else ("", 0.0)
    if worst > args.threshold:
        print(f"warning: question {worst_qid!r} disagrees at {worst:.1%}, over --threshold {args.threshold:.1%}; "
              f"send those to human review", file=sys.stderr)
        return 1
    return 0


def _table(records):
    table = {}
    for record in records:
        for qid, q in record["questions"].items():
            table.setdefault(qid, Counter())[split_data.label_key(q)] += 1
    return table


if __name__ == "__main__":
    sys.exit(main())
