"""The single spec-driven generator engine.

Spec §2.2. This is the only Python module that orchestrates generation. All it does on the CLI path is:
  1. Parse args: --scenario, --n, --out, --seed, --pairs, --gate.
  2. Resolve the scenario's spec through `resolve_spec` (one truth source, design doc D7).
  3. Instantiate BoundarySampler + Augmentor + PairBuilder + PlanAllocator.
  4. Loop: allocate a target, sample a state, split the derive channel off it (D10/D11), build the surfaces, evaluate
     the rules against what the state is allowed to show, apply augmentation, optionally build a minimal pair.
  5. Build a Kev record via common.labelled, hang the label basis on it as `_meta.derive`, write via
     common.write_records.
  6. Judge the finished file against the gates that already existed in `write_records`' warnings (design doc D5's
     `floor`, §3's exit row): the same numbers, now also a non-zero exit code when the spec asked to be held to them.

Step 4 is PR1b's (the derive channel) plus PR3's: a `by_label` target is realised by bounded re-drawing, because nothing
in the sampler knows which field has to cross for `final_band` to come out 3 — the spec's own rules are the only
authority on that, so the engine asks them (design doc D5).
"""
from __future__ import annotations

import math
import random
import sys
from collections import Counter
from typing import Any, Dict, List, NamedTuple, Optional

from .augment import Augmentor
from .common import resolve_spec
from . import derive
from .engine_cli import build_parser
from .pair import PairBuilder, fact_keys
from .plan import LabelTarget, PlanAllocator, PlanError, StateTarget
from .sampler import BoundarySampler
from . import common as _common
from . import ops
from . import rules
from . import values


def _rule_names(state: dict, fields: List[dict], tier_windows: dict, panel_category: dict,
                extra: Dict[str, Any]) -> Dict[str, Any]:
    """The names a spec expression sees: the sampler's view, the spec's own tables, and the D11 channel (`derived`,
    plus the spec's pools as bare names).

    The `state` here is `ops.rule_view`, not the sampler's view: a declared date arrives as the date it spells, and a
    key the record did not sample arrives as `MissingEvidence`, so a rule that needs it does not match instead of
    erroring (design doc D3 / §5.3 classes A and C). The record the sampler builds keeps the ISO string and every
    key it never sampled — only this name is a date, and only this view is allowed to say "no evidence".
    """
    return {"state": ops.rule_view(state, fields), "fields": fields, "tier_windows": tier_windows,
            "panel_category": panel_category, **extra}


def _label_keys(spec: dict) -> Dict[str, set]:
    """{question id: the keys its labels come from}, from the serving contract itself (`common.label_keys`).

    The rule DSL needs it to tell `then action = file` (the option) apart from `then action = filer` (a typo that used
    to be swallowed and shipped as a string the scorer could not read). Reading it from `kev.api` rather than the spec
    is what keeps the generator and the endpoint agreeing on what a key is (design doc D4, class E).
    """
    return {qid: set(_common.label_keys(spec, qid)) for qid in spec.get("questions") or {}}


def _triggering_field_name(state: dict, fields: List[dict]) -> Optional[str]:
    """The name of the numeric field in `state` whose value is critical; the candidate a minimal pair leads with.

    The `chosen` dict in the legacy `gen_*` builders tracked this implicitly, but BoundarySampler does not return it, so
    we re-derive it: read the typed value each numeric field carries and return the first one past its own critical
    bound. Since PR3 the view is typed (design doc D3) and the bound reading lives in `values`, so this walks the field
    view instead of parsing a formatted measurement back out of it. A unit-suffixed string still parses, which is what a
    spec's hand-written `state_example`-shaped view looks like.

    None means the record carries no crossed measurement — a normal report — and `PairBuilder` then moves any field it
    can (design doc D8), which is what let a pair fire on records the plan never steered.
    """
    for field in fields:
        name = field["name"]
        if name not in state or values.field_type(field) != "numeric":
            continue
        value = state[name]
        if isinstance(value, str):
            value = values.parse_value(value, values.decimals_of(field))
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        if values.in_critical(value, field):
            return name
    return None


#: How often the engine re-draws a record to hit a `by_label` target before it calls the target unreachable (design doc
#: D5). Bounded on purpose: an answer the rules cannot produce is a gap to report, not a loop to run until the machine
#: stops — and the bound is free when the rules do answer, because the retry breaks on the first hit (a cell the rules
#: reach with probability p costs about 1/p draws: 20 for a 5% cell, 39 for the rarest one below).
#: 600 is the number gate G2 needs, not 60. A missed slot falls back to a natural record, so the answer's share moves off
#: its quota by P(miss) x (quota - natural rate) and wobbles by sqrt(P(miss) x (1 - P(miss)) / slots) — the second term
#: is n-dependent, which is exactly what the gate forbids. On `edu-essay-scoring`'s rarest joint cell
#: (`final_band:3 & plagiarism_flag:true`, 2.6% of free draws measured over 1,200 unsteered records, asked for at 4%):
#: P(miss) is 0.9742 ** 60 = 20.8%, so 25 of its 120 slots at n = 3,000 answer something else and its n = 30 read (1.2
#: slots) wobbles by 1.4pp; at 600 attempts P(miss) is 1.5e-7, so neither happens. A cell at the 5% floor is missed
#: 4.6% of the time at 60 and 4.3e-14 at 600. A target the rules truly never reach costs one 600-draw probe and is then
#: drawn singly for the rest of the run (`run`'s dead-target rule).
LABEL_ATTEMPTS = 600

#: The two numbers `common.write_records` has always printed as warnings, now the gate's thresholds (design doc G1).
DEFAULT_FLOOR = 0.05
FALLBACK_CAP = 0.6


class _Assembly(NamedTuple):
    """One spec, read once: everything the per-record loop needs, so `_build` takes a target, an rng and a counter."""

    spec: dict
    gen: dict
    fields: List[dict]
    fields_by_name: Dict[str, dict]
    tier_windows: dict
    panel_category: dict
    label_keys: Dict[str, set]
    sampler: BoundarySampler
    augmentor: Augmentor
    pairer: PairBuilder
    pairs: float
    floor: float

    def label(self, state: dict, names: Dict[str, Any], functions: Dict[str, Any]) -> Dict[str, Any]:
        """The spec's rules over one record's view: the single call shape both a fresh record and its twin go through."""
        return rules.evaluate(self.gen.get("rules", []),
                              _rule_names(state, self.fields, self.tier_windows, self.panel_category, names),
                              functions, self.label_keys)


def _answers(record: dict, target: LabelTarget) -> bool:
    """Whether the finished record carries *every* answer `plan_targets.by_label` asked for.

    Compared on `split_data`'s normalised keys, so a `true` label written by a noul rule matches the `qid:true` the
    spec declared and a score index matches the string the quota names. A question the record does not answer cannot
    match: `common.labelled` refuses such a record outright, so this is the guard, not the report.
    """
    return all(qid in record["questions"] and _common.label_of(record, qid) == key for qid, key in target.pairs)


def _unreachable_answers(label_keys: Dict[str, set], plan_targets: dict) -> List[str]:
    """The `by_label` answers the spec's questions cannot carry, as messages (empty when every one is nameable).

    A gap the exit gate reports is a fact about the spec's *rules*; this is a fact about its serving contract, and a
    target the contract cannot answer would be searched 600 times per slot before the gate called it rare. Keys are
    `kev.api.question_keys` — the same strings the endpoint reports probabilities under (design doc D4).
    """
    problems = []
    for name in (plan_targets.get("by_label") or {}):
        for qid, key in LabelTarget.parse(name).pairs:
            if qid not in label_keys:
                problems.append(f"{name} names the question {qid!r}, which the spec does not ask")
            elif key not in label_keys[qid]:
                choices = ", ".join(sorted(label_keys[qid])) or "none"
                problems.append(f"{name} asks {qid} for {key!r}; the question answers {choices}")
    return problems


def _build(assembler: _Assembly, state_target: StateTarget, rng: random.Random, stats: Counter) -> List[dict]:
    """One plan target, realised as the records it earns: the record, plus its minimal-pair twin when one exists.

    [] means this draw did not answer the target — no rule applied, the sampler could not realise the tier, or a
    `by_label` answer came out different — and the caller retries or falls back. `stats` counts what the exit gate
    reads: `records`, `pairs`, `fallback` and one `label_missed:<qid>:<key>` per target that never answered.

    The derive channel (design doc D10/D11) is why the split happens here: a catalog field's drawn candidates are the
    label's basis, so they leave the view before the rules run and come back on the finished record as `_meta.derive`.
    What stays in `state` is the other seven field types plus each catalog field's `surface` — the only thing a rule,
    or the model, is allowed to see. A spec without a catalog field costs nothing here: `split` moves no key and
    `surfaces` returns before it touches the rng, so those runs stay byte for byte PR1a's.
    """
    sampled = assembler.sampler.sample(None if isinstance(state_target, LabelTarget) else state_target, rng)
    if sampled is None:
        # The target cannot be realised (a tier with no steerable field in the spec); a normal record still teaches.
        sampled = assembler.sampler.sample(None, rng)
    if sampled is None:
        return []
    derived, state = derive.split(sampled, assembler.fields)
    names = derive.extra_names(assembler.spec, derived)
    functions = derive.operators(rng)
    state.update(derive.surfaces(assembler.fields, derived, names, functions))
    trace: Dict[str, Any] = {}
    labels = rules.evaluate(assembler.gen.get("rules", []),
                            _rule_names(state, assembler.fields, assembler.tier_windows, assembler.panel_category,
                                        names),
                            functions, assembler.label_keys, trace=trace)
    if not labels:
        # No rule applied. This is a record the spec cannot answer, so it is skipped rather than labelled —
        # `common.labelled` would raise, and the regression tests count records, not exceptions.
        return []
    # evidence_drop selection lives in the Augmentor; we read it back as `dropped` and thread it through
    # `sampler.make_record` so the record's `missing_context` reflects the dropped element. Keeping the rate check
    # here exactly once per record preserves the rng stream (the test asserts the 8% evidence_sufficient flip share).
    state, labels, soft, dropped = assembler.augmentor.apply(state, labels, rng)
    # The spec decides where each value lands; `dropped` is the one key the engine owns (design doc D2).
    record = derive.attach(
        _common.labelled(assembler.spec, assembler.sampler.make_record(state, dropped=dropped), labels,
                        soft=soft or None), derived)
    if isinstance(state_target, LabelTarget) and not _answers(record, state_target):
        return []
    stats["records"] += 1
    if trace.get("fallback"):
        stats["fallback"] += 1
    out = [record]
    # The twin fires on any record whose evidence survived the Augmentor (legacy `pair_twin` semantics: a record with
    # a hole cut in it on purpose has no boundary to demonstrate). PR3 dropped the old `state_target is not None`
    # condition: an unsteered record has bounds to cross too, and a pair is worth teaching on it (design doc D8).
    if dropped == "" and assembler.pairs > 0 and rng.random() < assembler.pairs:
        twin = _pair(assembler, state, derived, labels, functions, rng, _triggering_field_name(state, assembler.fields))
        if twin is not None:
            out.append(twin)
            stats["pairs"] += 1
    return out


def _pair(assembler: _Assembly, state: dict, derived: Dict[str, Any], labels: Dict[str, Any],
          functions: Dict[str, Any], rng: random.Random, preferred: Optional[str]) -> Optional[dict]:
    """The parent's minimal-pair twin: one fact moved, its answer recomputed by the same rules (design doc D8).

    None — and no twin written — when nothing can be moved, when the move does not change an answer, when the new answer
    does not cover every question, or when it moves more keys than that one fact owns. `common.minimal_pair` refuses a
    pair that does not flip a label for the same reason: a wrong pair teaches a wrong boundary, and a twin that moves two
    facts demonstrates a boundary no record showed.
    """
    moved = assembler.pairer.build(state, assembler.fields_by_name, preferred, rng, derived=derived)
    if moved is None:
        return None
    name, twin_state, twin_derived = moved
    twin_names = derive.extra_names(assembler.spec, twin_derived)
    if name in twin_derived:
        # A catalog draw changed, so the surfaces that spelled it out are stale. Only that field's surfaces are
        # rebuilt: recomputing every surface would let a `pick` in an untouched field draw a second changed fact.
        field = assembler.fields_by_name[name]
        own = set(field.get("surface") or {})
        for key in [key for key in twin_state if key in own]:
            del twin_state[key]
        twin_state.update(derive.surfaces([field], twin_derived, twin_names, functions))
    twin_labels = assembler.label(twin_state, twin_names, functions)
    if not twin_labels or set(twin_labels) != set(labels):
        return None
    if all(_common.label_key_of(assembler.spec, qid, twin_labels[qid]) == _common.label_key_of(assembler.spec, qid,
                                                                                                            labels[qid])
           for qid in labels):
        return None
    if not set(_common.changed_fields(state, twin_state)) <= fact_keys(assembler.fields_by_name[name], name):
        return None
    return derive.attach(
        _common.labelled(assembler.spec, assembler.sampler.make_record(twin_state), twin_labels), twin_derived)


def quality_gaps(spec: dict, records: List[dict], stats: Counter, floor: float = DEFAULT_FLOOR) -> List[str]:
    """Every way this file fails the gates `write_records` has always only warned about (design doc §3, gate G1).

    [] means clean. Each message carries the number the author has to move: the label, how many records it is short of
    the floor, whether a `by_label` quota asked for it and never got it, and how much of the run came from the rule that
    asks nothing. One list, printed by `run`, judged by `--gate`, and reusable by the console's validate route.

    `stats` comes from the run that made the records (`_build`'s counters); an empty one simply has nothing to say about
    fallbacks and missed label targets, which is what `gate_gaps` passes for a file read back off disk.
    """
    if not records:
        return ["no records were produced; an empty file is not a pass"]
    total = len(records)
    gaps: List[str] = []
    invalid = [problem for record in records for problem in _common.split_data.check_record(record)]
    if invalid:
        gaps.append(f"{len(invalid)} record problems, first: {invalid[0]}")
    for qid, table in sorted(_common.label_table(records).items()):
        for key, have in sorted(table.items()):
            if have / total < floor:
                gaps.append(f"{qid}:{key} has {have} of {total} records ({have / total:.1%}), under the floor "
                            f"{floor:.0%}; {math.ceil(floor * total) - have} more needed")
        for key in sorted(set(_common.label_keys(spec, qid)) - set(table)):
            gaps.append(f"{qid}:{key} is never labelled; no rule reaches it, so the model cannot learn it")
    fallback_share = stats["fallback"] / max(stats["records"], 1)
    if stats["records"] and fallback_share > FALLBACK_CAP:
        gaps.append(f"{fallback_share:.0%} of records were labelled by a catch-all rule (cap {FALLBACK_CAP:.0%}); "
                    f"the spec's real rules are not firing")
    for key, count in sorted(stats.items()):
        if key.startswith("label_missed:") and f"label_dead:{key.split(':', 1)[1]}" in stats:
            gaps.append(f"plan_targets.by_label asks for {key.split(':', 1)[1]}, and none of the "
                        f"{LABEL_ATTEMPTS} draws its first slot got an answer; the spec's rules never produce it")
    return gaps


def gate_gaps(spec: dict, records: List[dict]) -> List[str]:
    """The gate over a file someone already has, read from the spec's own `floor` (the console's validate route)."""
    plan_targets = (spec.get("generator") or {}).get("plan_targets") or {}
    return quality_gaps(spec, records, Counter(),
                        float(plan_targets.get("floor", DEFAULT_FLOOR)))


def run(argv: List[str]) -> int:
    args = build_parser().parse_args(argv)
    spec = resolve_spec(args.scenario)
    gen = spec.get("generator") or {}
    # Refuse a spec whose rules cannot be evaluated before sampling a single record (T4, gate G3): a rule that reads a
    # field the spec never declared, calls an operator that does not exist, or labels a question that has no label
    # list, would otherwise cost a full run to produce 30 records that all fell through to the same fallback.
    problems = rules.static_errors(spec)
    if problems:
        raise rules.RuleError(f"spec {args.scenario} is not generatable:\n  " + "\n  ".join(problems))
    plan_targets = gen.get("plan_targets") or {}
    allocator = PlanAllocator(plan_targets)
    # The same refusal one layer up (design doc D5): a quota that fights a weight is an author who means two different
    # things, and a plan that cannot be read is cheaper to refuse before the first draw than to explain after the file.
    plan_errors = allocator.static_errors()
    if plan_errors:
        raise PlanError(f"spec {args.scenario} plan_targets is not readable:\n  " + "\n  ".join(plan_errors))
    fields = gen.get("fields", [])
    assembler = _Assembly(
        spec=spec, gen=gen, fields=fields, fields_by_name={field["name"]: field for field in fields},
        tier_windows=gen.get("tier_windows", {}), panel_category=gen.get("panel_category", {}),
        label_keys=_label_keys(spec),
        sampler=BoundarySampler(fields, gen.get("selectors", []), gen.get("tier_windows", {}), spec=spec),
        augmentor=Augmentor(gen.get("augmentation")),
        pairer=PairBuilder(gen.get("augmentation"), spec=spec), pairs=args.pairs,
        floor=float(plan_targets.get("floor", DEFAULT_FLOOR)))
    # If the spec has no `generator` block, common.labelled has nothing to evaluate against (every question
    # needs a label, and we don't have any) and write_records would still be called on an empty list. Skip
    # both with a one-line stderr note; the byte-for-byte gate (Task 7) is the first call that populates
    # `generator` and runs the full assembly path.
    if not gen:
        print(f"engine: no records produced; spec lacks generator block (scenario={args.scenario})", file=sys.stderr)
        return 0
    # One more refusal before the first draw: an answer the questions cannot be served with would otherwise cost the run
    # its whole retry budget and come back a gap that reads like "the rules reach this answer too rarely to plan for".
    contract_errors = _unreachable_answers(assembler.label_keys, plan_targets)
    if contract_errors:
        raise PlanError(f"spec {args.scenario} plan_targets asks answers its questions cannot carry:\n  "
                        + "\n  ".join(contract_errors))
    rng = random.Random(args.seed)
    plan = allocator.allocate(args.n, rng)
    records: List[dict] = []
    stats: Counter = Counter()
    # `by_label` targets whose full probe answered nothing, once per run: the rules of this spec do not reach that
    # answer, so the target's remaining slots draw a single record and fall back, and the exit gate reports the gap
    # instead of the run spending itself on a search with no answer (design doc D5).
    unreachable: set = set()
    for state_target in plan:
        # A `by_label` target is asked for, not assumed: the sampler cannot know which field has to cross for the rules
        # to answer `final_band:3`, so the engine draws until they do (bounded, design doc D5) and reports a target that
        # never answered as a gap instead of shipping the label the quota did not ask for.
        labelled = isinstance(state_target, LabelTarget)
        attempts = LABEL_ATTEMPTS if labelled and str(state_target) not in unreachable else 1
        produced: List[dict] = []
        for _ in range(attempts):
            produced = _build(assembler, state_target, rng, stats)
            if produced:
                break
        if not produced:
            if labelled:
                stats[f"label_missed:{state_target}"] += 1
                if attempts == LABEL_ATTEMPTS:
                    unreachable.add(str(state_target))
                    stats[f"label_dead:{state_target}"] = 1
            produced = _build(assembler, None, rng, stats)
        else:
            if labelled:
                stats[f"label_hit:{state_target}"] += 1
        records.extend(produced)
    if not records:
        print(f"engine: no records produced; spec lacks generator block (scenario={args.scenario})", file=sys.stderr)
        return 0
    _common.write_records(records, args.out, args.seed, args.scenario, warn=False)
    gaps = quality_gaps(spec, records, stats, assembler.floor)
    for gap in gaps:
        print(f"engine: gate {args.scenario}: {gap}", file=sys.stderr)
    # A target that answers but keeps a slot now and then is not a broken spec: the share moved by a fraction of a
    # percent, and the floor check above is what judges the file. It is still a number worth printing, because the
    # count tells the author which cell of their plan the rules reach only thinly (design doc D5).
    for key, count in sorted(stats.items()):
        if not key.startswith("label_missed:"):
            continue
        target = key.split(":", 1)[1]
        if f"label_dead:{target}" in stats:
            continue
        print(f"engine: note {args.scenario}: {target} fell back on {count} of its "
              f"{count + stats[f'label_hit:{target}']} slots ({count / max(len(records), 1):.1%} of the run); "
              f"the rules reach it thinly", file=sys.stderr)
    # Strict exactly where the spec asked to be judged (design doc §3's exit row): `write_records` has printed the same
    # numbers as warnings since the first generator, and a scenario written before this gate must not redden CI on a
    # threshold nobody chose. The file is still written — the gaps name what to fix, and the exit code is the CI signal.
    strict = args.gate == "strict" or (args.gate == "auto" and "floor" in plan_targets)
    return 1 if gaps and strict else 0


if __name__ == "__main__":
    try:
        sys.exit(run(sys.argv[1:]))
    except (rules.RuleError, PlanError) as error:
        # Loud, and on stderr where a redirected record file cannot mistake it for data: the exit code is the CI signal
        # and the message names the rule (design doc T4) or the plan block (design doc D5).
        print(f"engine: {error}", file=sys.stderr)
        sys.exit(2)
