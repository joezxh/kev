"""The derive channel: what a catalog field leaves in the record, and what it leaves in the state (design doc D10/D11).

`sampler.BoundarySampler` turns a catalog field into a list of drawn candidates, each one carrying its own label
attributes (`{"name": "持续胸痛", "urgency": 2, "red_flag": true}`). Two things then happen, and keeping them apart is
the whole point of D11:

* the candidates go to `record["_meta"]["derive"]`, and to the rules and the surface expressions as the name
  `derived` — that is where a label's evidence lives;
* the state gets only what the field's `surface` expressions build out of them, the way `gen_triage.py:106-116` wrote
  a chief complaint out of the symptom tuples and never printed an urgency.

Why the split is not decoration: `kev/api.render` flattens every key of a list-of-dict into the prompt
(`- name: 持续胸痛\n  urgency: 2\n  red_flag: True`), so a candidate that reached the state undressed would print the
answer into the model's input and turn the training set into a lookup table. `tests/test_engine_matrix.py`'s G8 test is
the machine guard for that, and it is the only thing standing between this design note and a regression.

Precedent in the repository: `evals/hard-v1` labels come from each family's solver reading `_meta.facts`, while the
state is prose for a human. `split_data.check_record` requires `state` + `questions` and ignores any other top-level
key, so `_meta` rides along legally.
"""
from __future__ import annotations

from random import Random
from typing import Any, Callable, Dict, List, Tuple

from simpleeval import EvalWithCompoundTypes

from . import ops
from . import values
from .ops import ALLOWED, pick


class SurfaceError(ValueError):
    """A catalog field's surface cannot be built as written (bad expression, unknown name, key already a field)."""


# Names the engine owns. A spec pool may not be called one of these, or a surface expression would find the sampler's
# state where it meant a list of strings and the failure would show up as dead data instead of as an error.
RESERVED_NAMES = ("state", "fields", "tier_windows", "panel_category", "derived")


def catalog_fields(fields: List[dict]) -> List[dict]:
    """The declared fields a record draws candidates out of, in spec order."""
    return [field for field in fields if values.field_type(field) == "catalog"]


def split(sampled: dict, fields: List[dict]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Cut the flat field view into (the derived view, what the state and the rules may hold).

    Everything that is not a catalog field stays in the second dict, untouched: PR1b is a channel for one field type,
    not a rewrite of the other seven, and a spec without a catalog field must keep producing byte-for-byte the file
    PR1a produced.
    """
    names = {field["name"] for field in catalog_fields(fields)}
    derived = {name: sampled[name] for name in names if name in sampled}
    view = {name: value for name, value in sampled.items() if name not in names}
    return derived, view


def pools(spec: dict) -> Dict[str, List[Any]]:
    """`generator.pools`: the named string pools a surface or a rule may reach for (design doc D13).

    The pools live in the spec, like every other pool: the legacy generators kept `TONE`, `CONTEXTS`, `VITALS` as
    module constants (`gen_diagnosis.py:72-82`), and D13 refuses anything outside the document, or a spec would stop
    replaying on a machine that does not have the corpus.
    """
    declared = (spec.get("generator") or {}).get("pools") or {}
    if not isinstance(declared, dict):
        raise SurfaceError("generator.pools must be an object of named lists")
    for name, values_ in declared.items():
        if name in RESERVED_NAMES:
            raise SurfaceError(f"generator.pools declares the reserved name {name!r}")
        if not isinstance(values_, list) or not values_:
            raise SurfaceError(f"generator.pools.{name} must be a non-empty list")
    return {name: list(values_) for name, values_ in declared.items()}


def extra_names(spec: dict, derived: Dict[str, Any]) -> Dict[str, Any]:
    """The names D11 adds to the evaluator: the drawn candidates, plus the spec's pools as bare names.

    `derived` is an `ops.EvidenceView` like the state: a catalog field the record did not draw is the same fact there
    as a numeric field the record did not sample here, and a rule that reads `derived['症状']` for a record with no
    symptom draw must fall through to the next rule rather than raise a `KeyError` the evaluator would have to swallow
    (design doc §5.3 class A).
    """
    return {**pools(spec), "derived": ops.EvidenceView(derived)}


def operators(rng: Random, base: Dict[str, Callable[..., Any]] = None) -> Dict[str, Callable[..., Any]]:
    """The operator table for one record: the shared `ALLOWED` plus `pick` bound to this record's random source.

    `ops.pick` takes the rng as its first argument, which is how a pure function reaches one; the spec writes
    `pick(TONE)`. The rng is bound here instead of being handed over as a *name* because a name is callable: a spec
    could then write `rng.seed(0)` or `rng.shuffle(STATE)` and silently break the replay the seed is the whole point of,
    while the binding exposes only the one call we meant to give out. Neither route reaches the interpreter --
    simpleeval refuses `__`-prefixed and `func_`-prefixed attributes, so `pick.args[0].seed.__globals__` dies at
    `__globals__` (design doc §7.1, settled by probe).

    A closure and not a `functools.partial`, which is the difference between "refuses" and "reachable": a partial
    exposes the rng it wrapped as `.args`, so `pick.args[0].seed(0)` was a legal expression that reset the stream
    mid-run (design doc §6, defect 9). A function object has no non-dunder attribute to hop through, so the same
    expression is now an `AttributeError` the evaluator reports instead of a mutation it never notices.
    """
    def bound_pick(pool: Any) -> Any:
        return pick(rng, pool)

    return {**(base or ALLOWED), "pick": bound_pick}


def surfaces(fields: List[dict], derived: Dict[str, Any], names: Dict[str, Any],
             functions: Dict[str, Callable[..., Any]]) -> Dict[str, Any]:
    """Evaluate every drawn catalog field's `surface`, as {state key: value} (design doc D11's second channel).

    A surface key lands at the top level of the state, which is what the legacy surfaces look like
    (`chief_complaint`, `red_flags`, `accompanying`); a nested surface needs a path convention, and PR4 gets to pick
    one when it rewrites the six fixtures against the real outputs. A later surface may read an earlier one, which is
    how a spec builds a summary out of a list it filtered first instead of repeating the expression.

    Fail-loud on purpose: an expression that raises here would leave a hole in the state that nothing downstream
    notices, which is the T4 failure mode this engine keeps being caught producing. A surface key may not name a
    declared field, a spec pool or `derived` either — the first would be overwritten by the draw it is supposed to
    describe, the other two would disappear from the expressions that come after it.

    Surfaces evaluate under `EvalWithCompoundTypes` because a fallback is a literal (`default_if_empty(..., ['无'])`)
    and a comprehension is a natural way to build one; plain `SimpleEval` refuses both at the moment it evaluates them,
    which is the worse failure — `'' or ['无']` dies only on the record whose draw came out empty, so a surface would
    look fine for 39 records and then hole the 40th. Since PR2b the rules run under the same evaluator (`rules.py`), so
    the two channels no longer disagree about what a spec is allowed to write — that disagreement is why
    `tests/fixtures/engine-matrix` had five scenarios whose rules were dead on arrival.
    """
    if not derived:
        return {}
    declared = {field["name"] for field in fields}
    built: Dict[str, Any] = {}
    for field in catalog_fields(fields):
        if field["name"] not in derived:
            continue
        surface = field.get("surface")
        if not surface:
            raise SurfaceError(f"catalog field {field['name']!r} draws candidates but declares no 'surface', so the "
                               f"record would carry no trace of them in the state")
        for key, expression in surface.items():
            if key in declared:
                raise SurfaceError(f"catalog field {field['name']!r} surface key {key!r} names a declared field")
            if key in names:
                raise SurfaceError(f"catalog field {field['name']!r} surface key {key!r} names an expression name "
                                   f"(a spec pool or `derived`), which the rest of the surface would lose")
            evaluator = EvalWithCompoundTypes(functions=functions, names={**names, **built})
            try:
                built[key] = evaluator.eval(expression)
            except Exception as error:
                raise SurfaceError(f"catalog field {field['name']!r} surface {key!r}: {expression!r} -> {error}") from None
    return built


def attach(record: dict, derived: Dict[str, Any]) -> dict:
    """Put the label basis on the finished record, where the renderer cannot reach it."""
    if derived:
        record.setdefault("_meta", {})["derive"] = derived
    return record
