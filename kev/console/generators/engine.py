"""The single spec-driven generator engine.

Spec §2.2. This is the only Python module that orchestrates generation. All it does on the CLI path is:
  1. Parse args: --scenario, --n, --out, --seed, --pairs.
  2. Read the scenario's spec_json from the DB (or paths.SPECS fallback during Task 2-3 before DB wiring).
  3. Instantiate BoundarySampler + RuleEvaluator + Augmentor + PairBuilder + PlanAllocator.
  4. Loop: allocate a target, sample a state, evaluate rules, apply augmentation, optionally build a minimal pair.
  5. Build a Kev record via common.labelled + write via common.write_records.

In Task 2 the loop is stubbed (no records written); the real loop lands in Task 3 + Task 4.
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
from .engine_cli import build_parser
from .pair import PairBuilder
from .plan import PlanAllocator
from .sampler import BoundarySampler
from . import common as _common
from .ops import ALLOWED, any_outside_critical, min_tier, fastest_tier_critical_item
from simpleeval import SimpleEval


# The base ALLOWED registry (kev/console/generators/ops.py) covers generic helpers (min/max/round/...).
# Spec §3.2 + Task 8 extend it with the medical domain operators; until Task 8 lands we register them
# here so the regression fixture's `any_outside_critical` / `min_tier` / `fastest_tier_critical_item` rules
# can resolve. When Task 8 moves these into ALLOWED, this re-binding is a no-op (the names are the same).
_EXTENDED_ALLOWED = {**ALLOWED,
                     "any_outside_critical": any_outside_critical,
                     "min_tier": min_tier,
                     "fastest_tier_critical_item": fastest_tier_critical_item}


def _load_spec(scenario: str) -> dict:
    """Read the scenario's spec from DB. The DB read is implemented in Task 16; this stub falls back to
    docs/medical/specs/<slug>.json so Tasks 3-15 can run before DB wiring.

    `KEV_ENGINE_SPEC_DIR` overrides the default spec directory; the regression test in tests/test_engine.py
    sets it so a fixture at tests/fixtures/<slug>/spec.json (per the plan) can be loaded instead of the
    committed medical spec. We try two layouts in order: <spec_dir>/<scenario>/spec.json (the per-scenario
    subdirectory the regression test creates) and <spec_dir>/<scenario>.json (the legacy convention).
    """
    import os
    from kev.console import paths
    spec_dir = Path(os.environ.get("KEV_ENGINE_SPEC_DIR") or paths.SPECS)
    candidates = [spec_dir / scenario / "spec.json", spec_dir / f"{scenario}.json"]
    for spec_file in candidates:
        if spec_file.exists():
            return json.loads(spec_file.read_text(encoding="utf-8"))
    raise FileNotFoundError(f"no spec at {candidates[0]} or {candidates[1]}")


def _evaluate_rules(rules: List[dict], state: dict, fields: List[dict], tier_windows: dict, panel_category: dict) -> Dict[str, Any]:
    """Evaluate `rules` (first-match wins) against `state`, exposing `fields`/`tier_windows`/`panel_category` to simpleeval.

    RuleEvaluator (kev/console/generators/rules.py) only exposes `state` to simpleeval, so it cannot resolve
    domain helpers like `any_outside_critical(state, fields)` or `min_tier(state, fields, tier_windows)`. We
    re-implement first-match evaluation here with the full spec context until RuleEvaluator is upgraded
    (spec §3.2 + Task 14).
    """
    names = {"state": state, "fields": fields, "tier_windows": tier_windows, "panel_category": panel_category}
    for rule in rules:
        when = rule.get("when", "")
        then = rule.get("then", [])
        evaluator = SimpleEval(functions=_EXTENDED_ALLOWED, names=names)
        try:
            if not bool(evaluator.eval(when)):
                continue
        except Exception:
            continue
        labels: Dict[str, Any] = {}
        for assignment in then:
            value = assignment["value"]
            if isinstance(value, str):
                try:
                    value = evaluator.eval(value)
                except Exception:
                    pass
            labels[assignment["label"]] = value
        return labels
    return {}


def _triggering_field_name(state: dict, fields: List[dict]) -> Optional[str]:
    """The name of the field whose value in `state` is critical; the candidate the minimal pair would flip.

    The `chosen` dict in the legacy `gen_*` builders tracked this implicitly, but BoundarySampler does
    not return it, so we re-derive it: walk every field whose name is in `state`, parse the formatted
    value, and return the first one that falls in the field's critical range. Returns None if no field
    in the state is critical.
    """
    from . import ops
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
    spec = _load_spec(args.scenario)
    gen = spec.get("generator") or {}
    rng = random.Random(args.seed)
    fields = gen.get("fields", [])
    tier_windows = gen.get("tier_windows", {})
    panel_category = gen.get("panel_category", {})
    sampler = BoundarySampler(fields, gen.get("selectors", []), tier_windows,
                              contexts=gen.get("contexts"), patients=gen.get("patients"))
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
        state = sampler.sample(state_target, rng)
        if state is None:
            # target not realizable; fall back to normal
            state = sampler.sample(None, rng)
        if state is None:
            continue
        # Evaluate rules with the full spec context (state, fields, tier_windows, panel_category).
        labels = _evaluate_rules(gen.get("rules", []), state, fields, tier_windows, panel_category)
        if not labels:
            # Defensive: if neither the rule evaluator nor the spec rules produce labels, skip the record
            # rather than letting common.labelled raise (the regression test asserts record-count parity).
            continue
        # evidence_drop selection lives in the Augmentor; we read it back as `dropped` and thread it
        # through `sampler.make_record` so the record's `missing_context` reflects the dropped element.
        # Keeping the rate check in one place preserves the rng stream (the test asserts the
        # 8% evidence_sufficient flip share; the rate check is here exactly once per record).
        state, labels, soft, dropped = augmentor.apply(state, labels, rng)
        # Assemble state + labels via common.labelled
        full_state = sampler.make_record(state, rng, dropped=dropped)
        # The legacy "drop unit" was implemented in gen_critical_value by NOT calling format_measurement
        # with_unit=True. For now we leave the unit in the formatted value (evidence_drop is a soft signal,
        # not a literal state change in this version) — the `evidence_sufficient` label is flipped by the
        # Augmentor instead, and `sampler.make_record(..., dropped=dropped)` records the missing piece in
        # the record's `missing_context` list so downstream readers can still see it.
        record = _common.labelled(spec, full_state, labels, soft=soft or None)
        records.append(record)
        # Optional: build a minimal pair twin. Activates only when a non-None state_target was set
        # (i.e. a critical record was sampled) and args.pairs > 0; this matches the legacy gen_* `pair_twin`
        # semantics, where only records that came from a critical state are eligible for the boundary flip.
        if state_target is not None and args.pairs > 0 and rng.random() < args.pairs:
            chosen = {f["name"]: f for f in fields if f["name"] in state}
            if chosen:
                triggering_name = _triggering_field_name(state, fields)
                if triggering_name and triggering_name in chosen:
                    handle = {"name": triggering_name, "panels": chosen, "values": {}, "dropped": dropped}
                    twin = pair_builder.build(record, handle, rng)
                    if twin is not None:
                        # The twin has its own state but needs a full record. Reuse the same patient/context.
                        twin_full_state = sampler.make_record(twin["state"]["labs"], rng, dropped="")
                        twin_labels = {qid: q["label"] for qid, q in twin["questions"].items()}
                        twin_record = _common.labelled(spec, twin_full_state, twin_labels)
                        records.append(twin_record)
    if not records:
        print(f"engine: no records produced; spec lacks generator block (scenario={args.scenario})", file=sys.stderr)
        return 0
    _common.write_records(records, args.out, args.seed, args.scenario)
    return 0


if __name__ == "__main__":
    sys.exit(run(sys.argv[1:]))
