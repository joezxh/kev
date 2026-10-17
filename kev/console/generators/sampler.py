"""BoundarySampler — constructs one `state` dict from spec_json.generator.fields + selectors + state_target.

Spec §3.1. The state shape matches gen_*.py (keys are field names; values are formatted strings like "6.2 mmol/L").
The class accepts a `random.Random` so the random number stream is reproducible.
"""
from __future__ import annotations
from random import Random
from typing import Any, Dict, List, Optional


class BoundarySampler:
    def __init__(self, fields: List[dict], selectors: List[dict], tier_windows: Optional[Dict[str, dict]] = None,
                 contexts: Optional[List[str]] = None, patients: Optional[List[str]] = None):
        self.fields = fields
        self.selectors = selectors
        self.tier_windows = tier_windows or {}
        self.contexts = contexts or []
        self.patients = patients or []

    def sample(self, state_target, rng: Random) -> Optional[Dict[str, Any]]:
        """One state record. Returns None if the target is not realizable.

        `state_target` is None (normal), (tier, category) (share+quota+tier_split), or a string
        (round-robin department/direction). For the string form, the sampler treats it as a category
        hint: it picks a triggering field whose `category` matches; if none match, it falls back to
        a non-triggered sample.
        """
        from . import ops
        # Three input shapes — string, tuple, None.
        if isinstance(state_target, str):
            category = state_target
            tier = None
        elif state_target:
            tier, category = state_target
        else:
            tier, category = None, "none"
        # Step 1: pick a triggering field. For the string form, prefer fields whose `category` matches.
        if state_target:
            category_matching = [
                f for f in self.fields
                if f.get("category") == category
            ]
            if category_matching:
                triggering_field = rng.choice(category_matching)
            else:
                # No category match (e.g. "undirected", "emergency"); pick a random field.
                triggering_field = rng.choice(self.fields)
        else:
            triggering_field = rng.choice(self.fields)
        # Step 2: pick 2-5 non-triggering fields
        others = [f for f in self.fields if f["name"] != triggering_field["name"]]
        chosen = {triggering_field["name"]: triggering_field}
        for extra in rng.sample(others, rng.randint(2, 5)):
            chosen[extra["name"]] = extra
        # Step 3: sample normal values for all
        state = {n: ops._format(f, ops.normal_value(rng, f), with_unit=True) for n, f in chosen.items()}
        # Step 4: realize target tier
        if state_target:
            value = ops.realize_tier(rng, triggering_field, tier, self.tier_windows)
            if value is None:
                return None
            state[triggering_field["name"]] = ops._format(triggering_field, value, with_unit=True)
            # Sometimes add a second critical item (carry-over logic from gen_critical_value.build)
            if rng.random() < 0.35:
                non_critical = [
                    n for n in chosen
                    if not ops._is_in_critical_range(
                        ops._parse_value(state[n], chosen[n].get("decimals", 1)),
                        chosen[n],
                    )
                ]
                for other in rng.sample(non_critical, min(2, len(non_critical))):
                    v2 = ops.critical_value(rng, chosen[other])
                    if ops._is_in_critical_range(v2, chosen[other]) and \
                       ops.min_tier({other: ops._format(chosen[other], v2, with_unit=False)}, [chosen[other]], self.tier_windows) >= tier:
                        state[other] = ops._format(chosen[other], v2, with_unit=True)
                        break
        return state

    def make_record(self, state: dict, rng: Random, dropped: str = "", context: str = "") -> dict:
        """Assemble one labelled Kev record from a state dict (the legacy gen_* make_record shape).

        `dropped` names the element removed on purpose ("" for none). `context` overrides the random context
        for evidence_drop tests; the default is to draw one from `self.contexts`.
        """
        # The "labels" come from the engine, not the sampler; engine.py passes them in. Here we just assemble state.
        patient = rng.choice(self.patients) if self.patients else "patient"
        ctx = context or (rng.choice(self.contexts) if self.contexts else "")
        full_state = {
            "patient": patient,
            "context": ctx,
            "labs": state,
            "ref_ranges_included": dropped != "reference_range",
            "missing_context": [dropped] if dropped else [],
        }
        return full_state