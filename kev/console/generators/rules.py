"""RuleEvaluator — evaluates spec_json.generator.rules sequentially; first match wins; emits labels per then.

Spec §3.2. Uses simpleeval with the ALLOWED operator whitelist from ops.py. Each rule has `when` (a string expression
evaluated against the state) and `then` (a list of {label, value} assignments). The evaluator MUST be deterministic
for a given (state, rules) — no randomness.
"""
from __future__ import annotations
from simpleeval import SimpleEval
from typing import Any, Dict, List
from .ops import ALLOWED


class RuleEvaluator:
    def __init__(self, rules: List[dict]):
        self.rules = rules

    def evaluate(self, state: dict) -> Dict[str, Any]:
        # First-match semantics: walk rules in order, take the first whose `when` is truthy.
        labels: Dict[str, Any] = {}
        for rule in self.rules:
            when = rule["when"]
            then = rule.get("then", [])
            # simpleeval with whitelist; state exposed as a `state` variable.
            evaluator = SimpleEval(functions=ALLOWED, names={"state": state})
            try:
                matched = bool(evaluator.eval(when))
            except Exception:
                matched = False
            if matched:
                for assignment in then:
                    labels[assignment["label"]] = assignment["value"]
                # First-match wins; do not continue evaluating subsequent rules.
                return labels
        return labels
