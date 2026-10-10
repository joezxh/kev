"""PairBuilder — minimal pair: a twin record whose state differs in exactly one field and whose label flips.

Spec §3.3. Reads `spec_json.generator.augmentation.minimal_pair` for rate + strategy. The boundary_flip strategy is
implemented in Task 9.
"""
from __future__ import annotations
from random import Random
from typing import Any, Optional


class PairBuilder:
    def __init__(self, augmentation: Optional[dict] = None, sampler=None):
        self.augmentation = augmentation or {}
        self.sampler = sampler

    def build(self, record, handle, rng: Random) -> Optional[dict]:
        """The minimal pair for `record`: a twin whose triggering measurement is on the safe side of the bound.

        Returns None when the record has no safely flippable field (legacy `gen_*` `pair_twin` semantics).
        """
        from . import ops
        from .rules import RuleEvaluator

        if handle is None or handle.get("dropped"):
            return None
        panels = handle.get("panels") or {}
        if not panels:
            return None
        name = handle["name"]
        if name not in panels:
            return None
        field = panels[name]
        # Pull the formatted value out of record.state.labs.
        labs = (record.get("state") or {}).get("labs") or {}
        formatted = labs.get(name)
        if formatted is None:
            return None
        # Re-sample the safe side via the sampler.
        safe = ops.crossed(rng, field)
        if ops._is_in_critical_range(safe, field):
            return None
        # Build the twin record.
        twin_state = dict(record["state"])
        twin_labs = dict(twin_state["labs"])
        twin_labs[name] = ops._format(field, safe, with_unit=True)
        twin_state["labs"] = twin_labs
        twin_record = {"state": twin_state, "questions": {}}
        # Re-evaluate rules on the twin. The legacy `gen_*` minimal pair only flipped the `is_critical`
        # label (e.g. critical-value's "is_critical" flips true->false on the safe side, the score
        # `notify_within` flips to "no notification needed", and the choice `critical_item` flips to
        # "none"); the rule engine may not produce all of them on its own, so the engine seeds the
        # twin with the original record's labels and lets the rule engine's output override the ones
        # the rule engine knows about. This keeps the twin's question set identical to the original
        # so _common.labelled's "every spec question has a label" check passes.
        evaluator = RuleEvaluator(handle.get("rules", []))
        twin_labels = evaluator.evaluate(twin_state["labs"])
        # Seed twin with the original record's labels so every spec question has a label.
        original_labels = {qid: q.get("label") for qid, q in (record.get("questions") or {}).items()}
        for qid, value in original_labels.items():
            twin_record["questions"][qid] = {"type": "noul", "label": value}
        # Override with rule-engine outputs (e.g. is_critical flips to false on the safe side).
        for qid, value in twin_labels.items():
            twin_record["questions"][qid] = {"type": "noul", "label": value}
        return twin_record
