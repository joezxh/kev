"""The single spec-driven generator engine.

Spec §2.2. This is the only Python module that orchestrates generation. All it does on the CLI path is:
  1. Parse args: --scenario, --n, --out, --seed, --pairs.
  2. Resolve the scenario's spec through `resolve_spec` (one truth source, design doc D7).
  3. Instantiate BoundarySampler + Augmentor + PairBuilder + PlanAllocator.
  4. Loop: allocate a target, sample a state, split the derive channel off it (D10/D11), build the surfaces, evaluate
     the rules against what the state is allowed to show, apply augmentation, optionally build a minimal pair.
  5. Build a Kev record via common.labelled, hang the label basis on it as `_meta.derive`, write via
     common.write_records.

Step 4 is the whole of PR1b: a catalog field's drawn candidates are the label's evidence, never its surface, so the
loop splits them out before the rules run and re-attaches them after the record is built (design doc D11, gate G8).
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional


# Ensure `from common import ...` inside the sub-modules resolves when the engine is invoked from a different
# working directory (the regression test runs from the repo root). The legacy gen_*.py entry points all rely
# on cwd == this directory; we add it to sys.path so the engine is cwd-agnostic.
_GENERATORS_DIR = Path(__file__).resolve().parent
if str(_GENERATORS_DIR) not in sys.path:
    sys.path.insert(0, str(_GENERATORS_DIR))

from .augment import Augmentor
from .common import resolve_spec
from . import derive
from .engine_cli import build_parser
from .pair import PairBuilder
from .plan import PlanAllocator
from .sampler import BoundarySampler
from . import common as _common
from . import ops
from . import rules


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
    """The name of the field whose value in `state` is critical; the candidate the minimal pair would flip.

    The `chosen` dict in the legacy `gen_*` builders tracked this implicitly, but BoundarySampler does
    not return it, so we re-derive it: walk every field whose name is in `state`, read its typed value, and return the
    first one that falls in the field's critical range. Returns None if no field in the state is critical.
    """
    for field in fields:
        name = field["name"]
        if name not in state:
            continue
        try:
            value = ops._parse_value(state[name], field.get("decimals", 1))
        except (ValueError, KeyError):
            continue
        if ops._is_in_critical_range(value, field):
            return name
    return None


def run(argv: List[str]) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    spec = resolve_spec(args.scenario)
    gen = spec.get("generator") or {}
    # Refuse a spec whose rules cannot be evaluated before sampling a single record (T4, gate G3): a rule that reads a
    # field the spec never declared, calls an operator that does not exist, or labels a question that has no label
    # list, would otherwise cost a full run to produce 30 records that all fell through to the same fallback.
    problems = rules.static_errors(spec)
    if problems:
        raise rules.RuleError(f"spec {args.scenario} is not generatable:\n  " + "\n  ".join(problems))
    rng = random.Random(args.seed)
    fields = gen.get("fields", [])
    tier_windows = gen.get("tier_windows", {})
    panel_category = gen.get("panel_category", {})
    label_keys = _label_keys(spec)
    # The spec itself goes to the sampler: a field's pool may be a generator-level list (`values_ref`, design doc D13)
    # and the record's skeleton (paths + `aux`) is read out of the same document (design doc D2).
    sampler = BoundarySampler(fields, gen.get("selectors", []), tier_windows, spec=spec)
    augmentor = Augmentor(gen.get("augmentation"))
    allocator = PlanAllocator(gen.get("plan_targets", {}))
    pair_builder = PairBuilder(gen.get("augmentation"), sampler=sampler)
    plan = allocator.allocate(args.n, rng)
    records = []
    # If the spec has no `generator` block, common.labelled has nothing to evaluate against (every question
    # needs a label, and we don't have any) and write_records would still be called on an empty list. Skip
    # both with a one-line stderr note; the byte-for-byte gate (Task 7) is the first call that populates
    # `generator` and runs the full assembly path.
    if not gen:
        print(f"engine: no records produced; spec lacks generator block (scenario={args.scenario})", file=sys.stderr)
        return 0
    for state_target in plan:
        # Sample state
        sampled = sampler.sample(state_target, rng)
        if sampled is None:
            # target not realizable; fall back to normal
            sampled = sampler.sample(None, rng)
        if sampled is None:
            continue
        # The derive channel (design doc D10/D11): a catalog field's drawn candidates are the label's basis, so they
        # leave the view here and come back on the finished record as `_meta.derive`. What stays in `state` is the
        # other seven field types plus each catalog field's `surface`, and that is the only thing a rule — or the
        # model — is allowed to see. A spec without a catalog field costs nothing here: `split` moves no key and
        # `surfaces` returns before it touches the rng, so those runs stay byte for byte PR1a's.
        derived, state = derive.split(sampled, fields)
        names = derive.extra_names(spec, derived)
        functions = derive.operators(rng)
        state.update(derive.surfaces(fields, derived, names, functions))
        # Evaluate rules with the full spec context (state, fields, tier_windows, panel_category, derived + pools).
        labels = rules.evaluate(gen.get("rules", []), _rule_names(state, fields, tier_windows, panel_category, names),
                                functions, label_keys)
        if not labels:
            # Defensive: if neither the rule evaluator nor the spec rules produce labels, skip the record
            # rather than letting common.labelled raise (the regression test asserts record-count parity).
            continue
        # evidence_drop selection lives in the Augmentor; we read it back as `dropped` and thread it
        # through `sampler.make_record` so the record's `missing_context` reflects the dropped element.
        # Keeping the rate check in one place preserves the rng stream (the test asserts the
        # 8% evidence_sufficient flip share; the rate check is here exactly once per record).
        state, labels, soft, dropped = augmentor.apply(state, labels, rng)
        # The spec decides where each value lands; `dropped` is the one key the engine owns (design doc D2).
        record = derive.attach(
            _common.labelled(spec, sampler.make_record(state, dropped=dropped), labels, soft=soft or None), derived)
        records.append(record)
        # Optional: build a minimal pair twin. Activates only when a steered (critical) record survived the
        # Augmentor untouched — the legacy gen_* `pair_twin` semantics: a record with evidence dropped on purpose
        # has no boundary to demonstrate.
        if dropped == "" and state_target is not None and args.pairs > 0 and rng.random() < args.pairs:
            chosen = {f["name"]: f for f in fields if f["name"] in state}
            twin_state = pair_builder.build(state, chosen, _triggering_field_name(state, fields), rng)
            if twin_state is not None:
                # Re-evaluate the rules on the flipped view: the point of the pair is that a rule, not a copy,
                # moves the label. Falls back to the parent's labels if no rule matches the safe side. The twin keeps
                # the parent's draw — a minimal pair shows one fact moving, and PR3 is what teaches a pair to flip a
                # *candidate* instead (design doc D8) — so `names` and the attached `derived` are the parent's.
                twin_labels = rules.evaluate(
                    gen.get("rules", []), _rule_names(twin_state, fields, tier_windows, panel_category, names),
                    functions, label_keys) or labels
                records.append(derive.attach(
                    _common.labelled(spec, sampler.make_record(twin_state), twin_labels), derived))
    if not records:
        print(f"engine: no records produced; spec lacks generator block (scenario={args.scenario})", file=sys.stderr)
        return 0
    _common.write_records(records, args.out, args.seed, args.scenario)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(run(sys.argv[1:]))
    except rules.RuleError as error:
        # Loud, and on stderr where a redirected record file cannot mistake it for data: the exit code is the CI signal
        # and the message names the rule (design doc T4).
        print(f"engine: {error}", file=sys.stderr)
        sys.exit(2)
