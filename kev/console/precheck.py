#!/usr/bin/env python3
"""Token 超限预检（runbook-train_cn.md 步骤 5）。

为什么必须做：kev 训练器对超出训练上下文的记录**静默丢弃**，只在 train.log 里打一行
`dropped N of M records`，不报错。而 split_data.py 的 STATE_CHARS_WARN=1400 是**英文**口径，
中文按 Qwen 分词器 token 密度偏高，照搬字符数会让大量记录在训练阶段被丢掉。
所以一律以本脚本用真实 tokenizer 的实测为准。

只 import kev 的既有能力，不重写任何逻辑：
  kev.data.load_records/materialize · kev.model.load_tokenizer/training_context/fits
  kev.suite.write_json
退出码非 0 表示有超限记录，编排层据此判 G1 失败。

Run: python kev/console/precheck.py --data data/cv --init-from jaredpalmer/kev-0.8b
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from kev.data import load_records, materialize              # noqa: E402
from kev.model import fits, load_tokenizer, training_context  # noqa: E402
from kev.suite import write_json                            # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data", required=True, help="split directory holding train/calibration/development")
    parser.add_argument("--init-from", required=True, dest="init_from",
                        help="tokenizer source: a Kev checkpoint (A1) or the bare base (A2/B)")
    parser.add_argument("--split", default="train", choices=["train", "calibration", "development"])
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)

    partition = Path(args.data) / f"{args.split}.jsonl"
    if not partition.exists():
        print(f"no such partition: {partition}", file=sys.stderr)
        return 2
    tokenizer = load_tokenizer(args.init_from)
    records = load_records(str(partition))
    # 预算从 kev.model 提升，不在此处硬编码（tests/test_conventions.py 的 single_home 规则）
    context = training_context()
    over = [record for record in records if not fits(materialize(record), tokenizer, **context)]
    report = {"split": args.split, "partition": str(partition), "init_from": args.init_from,
              "records": len(records), "over_limit": len(over),
              "context": context,
              "examples": [str(materialize(record))[:200] for record in over[:5]]}
    write_json(args.out, report)
    print(f"over_limit {len(over)} of {len(records)}")
    return 1 if over else 0


if __name__ == "__main__":
    raise SystemExit(main())
