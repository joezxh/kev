"""The rule DSL: one evaluator and one static check, shared by the engine and the console.

Spec §3.2, design doc D4. There used to be two evaluators — this module's `RuleEvaluator`, which exposed only `state`
and so could not resolve `any_outside_critical(state, fields)`, and a private copy in `engine.py` that the engine
actually ran. Nothing called the class; the copy is what shipped. They are one implementation now, and the copy is gone.

Three decisions make a broken spec audible (T4, gate G3) — each replaces one `except Exception: continue / pass` that
used to turn a TypeError into a silently single-valued label (design doc F3, §5.3):

* **`EvalWithCompoundTypes`**, the same evaluator the surfaces already run under, so a comprehension
  (`any(m['mastery'] < 0.5 for m in state['知识点掌握'])`) is a rule a spec may write;
* **no evidence is not an error**: a rule that reads a state key this record did not sample does not apply, and the
  scan moves to the next rule. `selectors` make that a normal outcome — one record carries three fields, another six.
  `ops.EvidenceView` is what says so, and only that says so: any other exception is a `RuleError`;
* **a label that is a bare name is a label, not an expression**: `then action = file` means the `file` option, and a
  name that is neither a declared option of that question nor an evaluable expression fails the run. A misspelled
  option (`hld`) used to be caught by the `except`, and shipped.

`static_errors` runs before a single record is sampled, so a typo in a field name is refused as a spec error instead of
being paid for at runtime by every record of every rule that reads it.
"""
from __future__ import annotations

import ast
from typing import Any, Callable, Dict, List, Optional, Set

from simpleeval import EvalWithCompoundTypes

from . import derive, ops


class RuleError(Exception):
    """A rule cannot be evaluated as written. Carries the rule it came from and the expression that failed."""

    def __init__(self, message: str, rule_id: str = "", expression: str = ""):
        super().__init__(message)
        self.rule_id = rule_id
        self.expression = expression


def rule_ref(rule: dict, index: int) -> str:
    """How a rule is named in an error: its own `id` when the spec declares one, otherwise its position."""
    return str(rule.get("id") or rule.get("rule_id") or f"rule {index + 1}")


def label_literal(value: str) -> Optional[str]:
    """The one `then` value shape that is a label rather than an expression: a single bare name (`file`, `none`).

    Deliberately narrow. A numeric string (`acuity = '3'`) is a `score` question's key *and* an expression that
    evaluates to the index the released records carry, and `sci-incident-triage` does exactly that — so it keeps
    evaluating. A quoted string, an operator call or a subscript keeps evaluating too.
    """
    try:
        body = ast.parse(value, mode="eval").body
    except SyntaxError:
        return None
    return body.id if isinstance(body, ast.Name) else None


def _eval(expression: str, names: dict, functions: Dict[str, Callable[..., Any]], where: str) -> Any:
    evaluator = EvalWithCompoundTypes(functions=functions, names=names)
    try:
        return evaluator.eval(expression)
    except ops.MissingEvidence:
        raise
    except Exception as error:
        raise RuleError(f"{where}: {expression!r} -> {type(error).__name__}: {error}",
                        rule_id=where, expression=expression) from error


def evaluate(rules: List[dict], names: dict, functions: Dict[str, Callable[..., Any]],
             label_keys: Dict[str, Set[str]]) -> Dict[str, Any]:
    """First-match-wins over `rules` against one record's `names`; the labels of the first rule that applies.

    `label_keys` is {question id: the keys that question's labels come from} — the spec's own contract, which is what
    tells a bare-name label (`weight`) apart from a typo (`weigth`). Returns {} when no rule applies, which the engine
    treats as "skip this record", never as a label.
    """
    for index, rule in enumerate(rules):
        where = rule_ref(rule, index)
        try:
            if not bool(_eval(rule.get("when", ""), names, functions, where)):
                continue
            labels: Dict[str, Any] = {}
            for assignment in rule.get("then", []):
                qid = assignment["label"]
                value = assignment["value"]
                if isinstance(value, str):
                    literal = label_literal(value)
                    if literal is not None and literal in label_keys.get(qid, set()):
                        labels[qid] = value
                        continue
                    labels[qid] = _eval(value, names, functions, f"{where} -> {qid}")
                else:
                    labels[qid] = value
            return labels
        except ops.MissingEvidence:
            continue
    return {}


def expressions_of(rules: List[dict], label_keys: Dict[str, Set[str]]) -> List[tuple]:
    """(where, expression) for everything the engine will evaluate: each `when`, and each `then` value that is not a
    bare-name label the spec declares. Static and runtime must look at the same set, or a check passes an expression
    the evaluator will never see."""
    out = []
    for index, rule in enumerate(rules):
        where = rule_ref(rule, index)
        out.append((where, rule.get("when", "")))
        for assignment in rule.get("then", []):
            value = assignment.get("value")
            if not isinstance(value, str):
                continue
            literal = label_literal(value)
            if literal is not None and literal in label_keys.get(assignment.get("label"), set()):
                continue
            out.append((where, value))
    return out


def names_used(expression: str) -> tuple:
    """(bare names, called names, {container: keys}) an expression reads, minus the names a comprehension binds.

    `ast.walk` is the whole point: the spec is JSON, so the only way to ask what a rule reads is to parse what it says.
    """
    tree = ast.parse(expression, mode="eval")
    bound = {target.id for node in ast.walk(tree) if isinstance(node, ast.comprehension)
             for target in ast.walk(node.target) if isinstance(target, ast.Name)}
    called = {node.func.id for node in ast.walk(tree)
              if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}
    bare = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)} - bound
    keyed: Dict[str, Set[str]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name) and isinstance(node.slice, ast.Constant) \
                and isinstance(node.slice.value, str):
            keyed.setdefault(node.value.id, set()).add(node.slice.value)
    return bare, called, keyed


def static_errors(spec: dict) -> List[str]:
    """Every way this spec's rules would fail the evaluator, as messages. [] means the spec is sound to generate from.

    The engine's refusal prints these; the console route reports them through `static_problems`, which is the same list
    with the rule separated out — one check, two shapes, and never a third copy of either.
    """
    return [f"{where}: {message}" for where, message in static_problems(spec)]


def static_problems(spec: dict) -> List[tuple]:
    """(rule id, message) for each problem, so an API response can name the rule without the caller parsing text.

    Checks names and keys, not arithmetic: `state['x'] > '80 %'` is valid syntax and PR2a already moved the specs that
    compared a measurement against its own unit string. A key a rule reads must be something the engine can put in the
    view — a declared field, a catalog field's `surface` result, an `aux` key — which is what separates a typo from the
    ordinary case of a record that did not sample the field.
    """
    from kev.api import question_keys
    gen = spec.get("generator") or {}
    fields = gen.get("fields", [])
    declared = {field["name"] for field in fields}
    viewable = declared | {key for field in fields for key in (field.get("surface") or {})} \
        | set((gen.get("aux") or {}))
    known_names = set(derive.RESERVED_NAMES) | set((gen.get("pools") or {}))
    functions = set(ops.ALLOWED)
    label_keys: Dict[str, Set[str]] = {}
    for qid, question in (spec.get("questions") or {}).items():
        try:
            label_keys[qid] = set(question_keys(question.get("type", ""), question.get("criteria")))
        except Exception:
            label_keys[qid] = set()
    problems: List[tuple] = []
    for where, expression in expressions_of(gen.get("rules") or [], label_keys):
        try:
            bare, called, keyed = names_used(expression)
        except SyntaxError as error:
            problems.append((where, f"{expression!r} is not an expression: {error}"))
            continue
        for name in sorted(bare):
            if name not in known_names and name not in functions:
                problems.append((where, f"{expression!r} reads {name!r}, which the spec declares as neither a pool "
                                        f"nor an expression name"))
        for name in sorted(called):
            if name not in functions:
                problems.append((where, f"{expression!r} calls {name!r}, which is not an operator"))
        for container in ("state", "derived"):
            for key in sorted(keyed.get(container, set()) - viewable):
                problems.append((where, f"{container}[{key!r}] is not a declared field"
                                        + (" or surface key" if container == "state" else "")))
    for index, rule in enumerate(gen.get("rules") or []):
        for assignment in rule.get("then", []):
            if assignment.get("label") not in label_keys:
                problems.append((rule_ref(rule, index), f"labels {assignment.get('label')!r}, "
                                                        f"which the spec declares no such question"))
    return problems
