#!/usr/bin/env python3
"""从已标注 JSONL 抽出均衡的 few-shot 风格范例（generate_data.py --examples 的输入）。

为什么存在：蒸馏的 --examples 需要「真实标注记录」作风格参考（generate_data.build_prompt
把范例原文塞进 prompt），但人工准备 JSONL 门槛高、冷启动时该参数形同虚设。本脚本从已有
合法数据（generate/distill 原始池、goldset、人工标注）按**第一题标签**分层轮询抽样，
保证范例覆盖各标签形态 —— 与 batch_targets 的配额均衡同思路，但不依赖 spec。

Run: python kev/console/make_examples.py --data data/critical-value.jsonl --n 8 --out data/critical-value/examples.jsonl
"""
import argparse
import json
import random
import sys
from collections import deque
from pathlib import Path


def label_of(record: dict) -> str:
    """记录的分层键 = 第一题的标签（bool 归一为 true/false，其余 str）。"""
    questions = record.get("questions") or {}
    if not questions:
        return "?"
    label = next(iter(questions.values())).get("label")
    if isinstance(label, bool):
        return "true" if label else "false"
    return str(label)


def sample_balanced(records: list[dict], n: int, seed: int = 0) -> list[dict]:
    """按标签分层轮询取 n 条：每组内部随机打乱，跨组轮询直到取满或抽干。"""
    groups: dict[str, deque] = {}
    for record in records:
        groups.setdefault(label_of(record), deque()).append(record)
    rng = random.Random(seed)
    for group in groups.values():
        rng.shuffle(group)
    order = sorted(groups)
    picked: list[dict] = []
    while len(picked) < n and any(groups[key] for key in order):
        for key in order:
            if groups[key] and len(picked) < n:
                picked.append(groups[key].popleft())
    return picked


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data", required=True, help="labelled JSONL to sample from")
    parser.add_argument("--n", type=int, default=8, help="examples to write (default 8)")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)

    source = Path(args.data)
    if not source.is_file():
        print(f"no such data file: {source}", file=sys.stderr)
        return 2
    records = [json.loads(line) for line in
               source.read_text(encoding="utf-8").splitlines() if line.strip()]
    picked = sample_balanced(records, max(0, args.n), args.seed)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="\n") as handle:
        for record in picked:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    counts: dict[str, int] = {}
    for record in picked:
        counts[label_of(record)] = counts.get(label_of(record), 0) + 1
    print(f"{len(picked)} examples -> {out} (from {len(records)} records); "
          + ", ".join(f"{key}={value}" for key, value in sorted(counts.items())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
