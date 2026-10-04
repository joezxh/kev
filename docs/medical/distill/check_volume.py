"""量级保障与预算核算。

三件事，都是「早失败」而不是「训练完才发现」：

1. **结构与分布断言** —— 每个场景的记录数、每个标签的占比（split_data 的 5% 下限）、每个选项是否
   至少出现过一次作为正确答案。违反即 exit 1。
2. **token 预算** —— ``--budget`` 给出上限；``--from-sft`` 会汇总 EasyDistill 输出里
   ``metadata.usage.total_tokens``，得到**真实**的每条成本，用它替代估算。
3. **Kev 轨与 SFT 轨的账分开算** —— Kev 轨不消耗 LLM token（标签与 state 都来自规则引擎），
   只有 SFT 轨花钱。混在一起算会得出错误的成本结论。

用法::

    python3 docs/medical/distill/check_volume.py --scenario inquiry --records data/inquiry.jsonl
    python3 docs/medical/distill/check_volume.py --all --records-dir data --budget 8000000
    python3 docs/medical/distill/check_volume.py --scenario inquiry --from-sft data/sft/inquiry.sft.jsonl

标准库 only。
"""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "generators"))

import common  # noqa: E402
import split_data  # noqa: E402

SPEC_FOR = {"inquiry": "triage", "medication": "medication-review", "diagnosis": "diagnosis",
            "record-summary": "record-summary"}
SFT_ONLY = {"knowledge-qa"}
LABEL_FLOOR = 0.05      # split_data.py 的告警阈值
MIN_CALIBRATION_QUESTIONS = 100

def read_jsonl(path):
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def check_records(scenario, path, expect=None):
    """Structure and distribution assertions for one scenario's Kev records. Returns (questions, problems)."""
    records = read_jsonl(path)
    spec = common.load_spec(SPEC_FOR[scenario])
    problems = []
    if not records:
        return 0, [f"{scenario}: no records"]
    for n, record in enumerate(records, 1):
        found = split_data.check_record(record)
        if found:
            problems.append(f"{scenario} line {n}: {found[0]}")
            if len(problems) > 20:
                break
    questions = 0
    for qid, table in sorted(common.label_table(records).items()):
        total = sum(table.values())
        questions += total
        rare = sorted(k for k, v in table.items() if v / total < LABEL_FLOOR)
        if rare:
            problems.append(f"{scenario}:{qid} labels under {LABEL_FLOOR:.0%}: {rare}")
        missing = sorted(set(common.label_keys(spec, qid)) - set(table))
        if missing:
            problems.append(f"{scenario}:{qid} never labelled: {missing}")
        print(f"  {qid}: " + ", ".join(f"{k}={v} ({v / total:.0%})" for k, v in table.most_common()))
    if questions < MIN_CALIBRATION_QUESTIONS:
        problems.append(f"{scenario}: only {questions} questions; the temperature fit needs >= {MIN_CALIBRATION_QUESTIONS}")
    if expect and len(records) != expect:
        problems.append(f"{scenario}: {len(records)} records, expected {expect}")
    print(f"  -> {len(records)} records, {questions} questions, "
          f"{len({split_data.state_key(r['state']) for r in records})} distinct states")
    return questions, problems


def sft_tokens(path):
    """Sum metadata.usage.total_tokens across an EasyDistill SFT file. Returns (tokens, rows, per_row)."""
    rows = read_jsonl(path)
    total = 0
    seen = 0
    for row in rows:
        usage = (row.get("metadata") or {}).get("usage") or {}
        if "total_tokens" in usage:
            total += int(usage["total_tokens"])
            seen += 1
    return total, len(rows), (total / seen if seen else 0.0), seen

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--scenario", choices=sorted(SPEC_FOR), help="有 Kev 轨的场景")
    group.add_argument("--all", action="store_true", help="全部有 Kev 轨的场景 + 列出纯 SFT 场景")
    parser.add_argument("--records", help="--scenario 模式下的 Kev 记录路径")
    parser.add_argument("--records-dir", default="data", help="--all 模式下的记录目录")
    parser.add_argument("--expect", type=int, help="每个场景期望的记录数（默认 787）")
    parser.add_argument("--from-sft", action="append", default=[],
                        help="EasyDistill SFT 输出，可重复；用于核算真实 token 成本")
    parser.add_argument("--budget", type=int, help="token 上限；超过则 exit 1")
    args = parser.parse_args(argv)
    expect = args.expect if args.expect is not None else 787

    problems, total_questions = [], 0
    if args.all:
        for scenario in sorted(SPEC_FOR):
            path = Path(args.records_dir) / f"{scenario}.jsonl"
            print(f"\n== {scenario} ({SPEC_FOR[scenario]})")
            if not path.exists():
                problems.append(f"{scenario}: missing {path}")
                continue
            questions, found = check_records(scenario, path, expect)
            total_questions += questions
            problems += found
        for scenario in sorted(SFT_ONLY):
            print(f"\n== {scenario}: 纯生成式场景，无 Kev 轨（Kev 只在预声明选项集上出概率，不生成 token）")
    else:
        if not args.records:
            raise SystemExit("--scenario requires --records")
        print(f"== {args.scenario} ({SPEC_FOR[args.scenario]})")
        total_questions, found = check_records(args.scenario, args.records, expect)
        problems += found

    print("\n== token 账")
    print("  Kev 轨: 0 LLM token（标签与 state 均来自规则引擎，不经 LLM）")
    grand = 0
    for path in args.from_sft:
        if not Path(path).exists():
            problems.append(f"missing SFT file {path}")
            continue
        total, rows, per_row, seen = sft_tokens(path)
        grand += total
        print(f"  {Path(path).name}: {total:,} tokens over {rows:,} rows "
              f"({per_row:,.0f}/row, usage seen on {seen:,} rows)")
    if args.from_sft:
        print(f"  SFT 轨合计: {grand:,} tokens")
    if args.budget is not None:
        if grand > args.budget:
            problems.append(f"token budget exceeded: {grand:,} > {args.budget:,}")
        else:
            print(f"  预算 {args.budget:,}，剩余 {args.budget - grand:,}")

    if problems:
        print("\nFAILED:")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print("\nOK: 分布与预算断言全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
