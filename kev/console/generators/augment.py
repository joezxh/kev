"""Augmentor — post-sampling modifications: evidence_drop + soft target injection + force_label.

Spec §3.3. Called after BoundarySampler + RuleEvaluator; reads `spec_json.generator.augmentation` and mutates a copy
of (state, labels) according to the rate fields. Returns (state, labels, soft, dropped).
"""
from __future__ import annotations
from copy import deepcopy
from random import Random
from typing import Any, Dict, Optional, Tuple


class Augmentor:
    def __init__(self, augmentation: Optional[dict] = None):
        self.augmentation = augmentation or {}

    def apply(self, state: dict, labels: Dict[str, Any], rng: Random) -> Tuple[dict, Dict[str, Any], Dict[str, Any], str]:
        """Apply evidence_drop: 8% rate, drop unit or refs, flip evidence_sufficient to false, inject soft target.

        Returns (state_modified, labels_modified, soft, dropped). `state` and `labels` are not mutated.
        The `dropped` value is "" when the augmentation did not fire, or one of "unit" / "reference_range"
        (a single `rng.random() < 0.5` decides which). The engine threads this through `sampler.make_record`
        so the record's `missing_context` reflects the dropped element.

        The signature extends the plan's `(state, labels, soft)` return with `dropped` so the engine can
        pass it to `sampler.make_record(state, rng, dropped=dropped)` without computing the rate itself;
        this keeps the rng stream identical to the pre-refactor engine (one `rng.random()` call per record
        when the rate does not fire, two when it does) and preserves the test_critical_value_structural_parity
        evidence_sufficient distribution.
        """
        new_state = deepcopy(state)
        new_labels = dict(labels)
        soft: Dict[str, Any] = {}
        dropped = ""
        ev = self.augmentation.get("evidence_drop")
        if not ev:
            return new_state, new_labels, soft, dropped
        if rng.random() < ev.get("rate", 0.0):
            # Pick the dropped element: half unit, half reference_range.
            dropped = "unit" if rng.random() < 0.5 else "reference_range"
            # Force `evidence_sufficient=false` per spec. The `force_label` value is a JSON string
            # (e.g. "false" / "true"); noul labels require a Python bool, so coerce.
            force = ev.get("force_label", {})
            for label, value in force.items():
                if isinstance(value, str):
                    new_labels[label] = (value == "true")
                else:
                    new_labels[label] = value
            # Inject soft target.
            question = ev.get("question")
            if question:
                soft[question] = ev.get("soft_target", {})
        return new_state, new_labels, soft, dropped
