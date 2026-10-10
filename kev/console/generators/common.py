"""Shared base for the medical record generators (kev/console/generators).

Every generator turns a **rule**, not a language model, into a label: sample structured fields, apply the
authoritative threshold table or rule engine, emit a Kev record whose labels cannot drift. That is what makes the
0.8B track viable at all -- its knowledge base is too weak to judge medical semantics, so the supervision has to
arrive already computed.

Lives here: :func:`labelled` (build + self-check one record), :func:`write_records` (deterministic JSONL out plus both
of split_data's label warnings), :func:`boundary_value` (sample near a decision boundary, where the decision
actually lives), :func:`minimal_pair` (same state, one fact changed, label flips), :func:`changed_fields` (assert a
pair is minimal), :func:`load_spec` (so question ids and types can never drift from the generator).

Per-label quotas are **not** here: each generator owns its own :func:`plan_targets` because the quota shape differs
per scenario (a scarce notification tier needs an explicit split table, whereas a choice question just needs a
round-robin over its issue types).

Standard library only, no network, deterministic under a seed -- same conventions as
skills/kev-finetune/scripts. Run: uv run python -m pytest tests/test_medical_generators.py -q
"""
import argparse
import json
import random
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SKILL = ROOT / "skills/kev-finetune"
if str(SKILL / "scripts") not in sys.path:
    sys.path.insert(0, str(SKILL / "scripts"))
import split_data  # noqa: E402

SPECS = ROOT / "docs/medical/specs"

# Share of values deliberately placed close to a threshold. Without this the model only ever sees values far from
# the boundary and learns the shortcut "big number -> critical" instead of the rule.
NEAR_BOUNDARY = 0.45


def load_spec(name):
    """The scenario's own spec, so the generator can never invent a question id or type the spec does not declare."""
    path = SPECS / f"{name}.json"
    if not path.exists():
        raise SystemExit(f"no spec at {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def label_keys(spec, qid):
    """The keys a question's labels must come from (option names / "true"|"false" / level indices as strings)."""
    q = spec["questions"][qid]
    if q["type"] == "noul":
        return ["true", "false"]
    if q["type"] == "choice":
        return list(q["criteria"])
    return [str(i) for i in range(len(q["criteria"]))]


def labelled(spec, state, labels, soft=None):
    """Build one Kev record: a state plus one labelled question per spec question.

    `soft` optionally maps a question id to a `target` dict of non-negative weights, to teach "no evidence, no
    confidence". Raises ValueError rather than emitting a record the trainer would silently drop later, so a broken
    rule surfaces at generation time instead of as invisible data loss.
    """
    soft = soft or {}
    questions = {}
    for qid, q in spec["questions"].items():
        if qid not in labels:
            raise ValueError(f"no label for {qid}")
        entry = {k: v for k, v in q.items() if k in ("type", "instructions", "criteria")}
        entry["label"] = labels[qid]
        if qid in soft:
            entry["target"] = soft[qid]
        problems = split_data.check_question(qid, entry)
        if problems:
            raise ValueError(f"{qid}: {problems[0]}")
        questions[qid] = entry
    record = {"state": state, "questions": questions}
    problems = split_data.check_record(record)
    if problems:
        raise ValueError(f"record rejected: {problems[0]}")
    return record


def label_table(records):
    """{question id: Counter(label key)} across records -- the same view split_data.py prints."""
    counts = {}
    for record in records:
        for qid, q in record["questions"].items():
            counts.setdefault(qid, Counter())[split_data.label_key(q)] += 1
    return counts


def boundary_value(rng, threshold, low, high, side=None, near=NEAR_BOUNDARY, decimals=1):
    """Sample a measurement whose hard cases sit on `threshold`.

    With probability `near` the value comes from a tight band around the threshold, making the record a case the model
    has to get right rather than a trivial one; otherwise uniformly from the plausible range. `side` forces one side
    of the threshold, which is what minimal_pair() needs in order to flip a label.
    """
    if side is None:
        side = rng.random() < 0.5
    band_low, band_high = (threshold, high) if side else (low, threshold)
    span = band_high - band_low
    if span <= 0:
        return round(threshold, decimals)
    if rng.random() < near:
        width = min(span * 0.12, abs(threshold) * 0.03 + 0.02)
        value = rng.uniform(threshold, threshold + width) if side else rng.uniform(threshold - width, threshold)
    else:
        value = rng.uniform(band_low, band_high)
    return round(min(max(value, band_low), band_high), decimals)


def changed_fields(a, b):
    """Field names whose values differ between two object states (used to assert a minimal pair is minimal)."""
    return sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k))


def write_records(records, out, seed, spec_name):
    """Write labelled JSONL and print the same shape of summary split_data.py prints, so the two agree on sight."""
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="\n") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    states = {split_data.state_key(r["state"]) for r in records}
    print(f"{len(records)} records -> {out} (spec {spec_name}, seed {seed})")
    print(f"distinct states: {len(states)} ({len(records) - len(states)} duplicate states)")
    spec = load_spec(spec_name)
    warned = False
    for qid, table in sorted(label_table(records).items()):
        total = sum(table.values())
        print(f"  {qid}: " + ", ".join(f"{k}={v} ({v / total:.0%})" for k, v in table.most_common()))
        rare = [k for k, v in table.items() if v / total < 0.05]
        if rare:
            warned = True
            print(f"  warning: {qid}: {rare} under 5% of {total} records", file=sys.stderr)
        missing = sorted(set(label_keys(spec, qid)) - set(table))
        if missing:
            warned = True
            print(f"  warning: {qid}: no record is ever labelled {missing}; the model cannot learn them", file=sys.stderr)
    print("next: python3 skills/kev-finetune/scripts/split_data.py "
          f"{out} --out {out.with_suffix('')} [--holdout <gold.jsonl>]")
    return warned


def base_parser(description):
    """The CLI every generator shares: --n records, --out path, --seed, plus a couple of scenario-agnostic knobs."""
    parser = argparse.ArgumentParser(description=description, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--n", type=int, default=787, help="records to generate; 787 is the planned size for a "
                                                          "4-question medical spec (docs/medical/data-format.md)")
    parser.add_argument("--out", required=True, help="output labelled JSONL path")
    parser.add_argument("--seed", type=int, default=0, help="seed; the same seed reproduces the same file")
    parser.add_argument("--pairs", type=float, default=0.35, help="share of records that also get a minimal-pair "
                                                                   "twin appended (0 disables)")
    return parser
