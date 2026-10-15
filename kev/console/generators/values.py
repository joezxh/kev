"""Field value samplers — one per field type a spec may declare (design doc D1/D10/D13).

`sampler.BoundarySampler` owns *which* fields go into a record and *how* they land in the state skeleton; this module
owns what a single field's value looks like. Keeping the split here means adding a type touches one file, not the
sampling loop (design doc §3, the F1 fix: `ops.normal_value` used to read `field["normal"]` for every field, which is
the exact line 20/32 spike scenarios died on).

PR1a shipped seven of the eight types; PR1b adds `catalog`, the one a field has no *value* for (design doc D10): a
pool of candidates that carry their own label attributes, k of which are drawn per record. What comes back from
`sample_catalog` is therefore not something a record ships — it is the derived view `derive.surfaces` dissolves into
the state and the rules read as `derived` (D11), and `derive.attach` puts it under the record's `_meta.derive`.

Value shapes on purpose: since PR2a every type returns the value its rules need — numeric a number, bool a bool, a date
the ISO string (JSON has no date type, and `kev/api.date_facts` reads that string; rules see a parsed date, design doc
D3), a list or an object the structure itself. The unit a measurement used to carry inside the value lives in the
spec's `render_units` and is applied when the record is built, so the released checkpoint's prompt surface is unchanged.

PR3 moved the rest of the numeric geometry in here too — the onset a `critical` bound actually declares, the quantiser
that decides whether a value prints as `0` or `0.0`, and the three samplers `ops.py` used to hold (`normal_value`,
`critical_value`, `crossed`). They were never rule operators: nothing in `ops.ALLOWED` calls them, and living in `ops`
meant they read `field["normal"]` and `field["critical"]` directly instead of the declared `bounds`, which is the shape
of §6 defect 5 (the sentinel `1e9` read as the threshold) and of defect 8 (the threshold pinned to the range's lower
end). The dependency runs one way now: `ops` imports `values`, never the reverse.
"""
from __future__ import annotations

from datetime import date, timedelta
from random import Random
from typing import Any, Callable, Dict, List, Optional, Tuple

from . import common

# A field with no `type` is numeric: every committed medical spec is written that way and must stay byte for byte.
DEFAULT_TYPE = "numeric"


class UnsupportedField(ValueError):
    """The field declaration cannot be sampled as written (unknown type, missing pool, catalog before PR1b)."""


def field_type(field: dict) -> str:
    return field.get("type") or DEFAULT_TYPE


def bounds_of(field: dict) -> Dict[str, Any]:
    """The field's named bounds, as {name: range}.

    `normal`/`critical` at the top level are aliases kept for the committed specs (design doc D12); `bounds` is the
    general form, so an industry's own limits (`single_max_mg`, `daily_min_mg`) need no change to this module.
    """
    bounds = dict(field.get("bounds") or {})
    for alias in ("normal", "critical"):
        if alias in field and alias not in bounds:
            bounds[alias] = field[alias]
    return bounds


def pool_of(field: dict, spec: dict) -> List[Any]:
    """A field's inline value pool, or the generator-level list `values_ref` points at (design doc D13).

    Pools live in the spec only: a `corpus` outside the repository would break deterministic replay and would not
    exist on the CI machine, so there is no path for it here.

    Public since PR3 because a minimal pair has to pick *another* value out of the same pool (design doc D8), and a
    second reader of `values`/`values_ref` would be a second home for the lookup.
    """
    if "values" in field:
        values = field["values"]
        if not isinstance(values, list) or not values:
            raise UnsupportedField(f"field {field.get('name')!r} declares an empty or non-list 'values'")
        return values
    ref = field.get("values_ref")
    if ref:
        values = (spec or {}).get("generator", {}).get(ref) or (spec or {}).get(ref)
        if not values:
            raise UnsupportedField(f"field {field.get('name')!r} refs values_ref {ref!r}, which the spec does not declare")
        return list(values)
    raise UnsupportedField(f"field {field.get('name')!r} has no 'values' pool and no 'values_ref'")


def path_of(field: dict) -> List[str]:
    """Where the field's value lands in the record's state (design doc D2). Default: the top level, keyed by name.

    `critical-value`'s `labs` and the legacy `patient` wrapper become something a spec *declares*
    (`"path": ["labs", "K+"]`) instead of something the sampler hardcodes — that hardcoding is F2, the reason a legal
    scenario's record came out looking like a lab report.
    """
    path = field.get("path")
    if path is None:
        return [field["name"]]
    if not isinstance(path, list) or not path or not all(isinstance(part, str) and part for part in path):
        raise UnsupportedField(f"field {field.get('name')!r} declares a bad 'path' {path!r}")
    return list(path)


# --- numeric geometry (design doc §6, defects 5 and 8) -------------------------------------------------------


def decimals_of(field: dict) -> int:
    """The precision the field declares; 1 is what every medical spec that never said otherwise means."""
    return int(field.get("decimals", 1))


def step(field: dict) -> float:
    """One unit at the field's own precision — the smallest move that changes the value it prints."""
    return 10.0 ** -decimals_of(field)


def quantize(value: Any, decimals: int) -> Any:
    """Round at `decimals`, in the type that precision asks for.

    Python's `round` keeps the input's type: `round(160, 1)` is the int 160 and `round(160.0, 1)` is 160.0, so a field
    whose threshold is an integer in JSON while its samples come from `rng.uniform` printed both `0 个` and `160.0 个` in
    the same column (§6, defect 8). `decimals <= 0` declares whole numbers, so the answer is an `int`; anything else is a
    float at exactly that many places.
    """
    if decimals <= 0:
        return int(round(value))
    return round(float(value), decimals)


def typed_value(field: dict, value: Any) -> Any:
    """The value a numeric field's view holds: the number, rounded to the field's own `decimals` (design doc D3).

    Rounded here rather than only at render time so the rule, the critical check and the shipped text agree on one
    number — a rule that reads 6.245 while the model reads "6.2 mmol/L" would be a label the prompt cannot support.
    """
    return quantize(value, decimals_of(field))


def format_value(field: dict, value: Any, with_unit: bool = True) -> str:
    """Replaces gen_critical_value.format_measurement.

    The renderer of a measurement's *surface*, not of its value: since PR2a the field view carries a number and only the
    record's text goes through here (`sampler.BoundarySampler.render`, gated by `generator.render_units`).
    """
    unit = field.get("unit", "")
    rounded = typed_value(field, value)
    if with_unit and unit:
        return f"{rounded} {unit}"
    return str(rounded)


def parse_value(formatted: Any, decimals: int) -> float:
    """`"6.2 mmol/L"` -> `6.2`. Drops the unit suffix after the first space.

    Since PR2a the field view holds a number (design doc D3), so a number comes back rounded the same way it would have
    been parsed — one function still answers both worlds, which is what lets a spec's own `"6.2 mmol/L"` (the legacy
    generators still hand one to these helpers) and an engine's `6.2` mean the same criticality.
    """
    if isinstance(formatted, bool) or formatted is None:
        raise ValueError(f"{formatted!r} is not a measurement")
    if isinstance(formatted, (int, float)):
        return round(float(formatted), decimals)
    head = formatted.split(" ", 1)[0]
    return round(float(head), decimals)


def in_critical(value: Any, field: dict) -> bool:
    """True iff `value` falls inside one of the field's declared `critical` ranges — the authority a label is checked against."""
    for ranges in (bounds_of(field).get("critical") or {}).values():
        for low, high in ranges:
            if low <= value <= high:
                return True
    return False


def critical_sides(field: dict) -> List[Tuple[str, float, Tuple[float, float]]]:
    """Each critical side the field declares, as `(side, onset, window)`.

    `onset` is where the danger starts: the *lower* end of a `high` range, the upper end of a `low` one. The far end is a
    sentinel — `{"high": [[15, 1e9]]}` means "15 and above", not "the threshold is 1e9" — and reading it as the threshold
    is §6 defect 5, which left 52 of the matrix's 99 critical fields unable to produce a value or a minimal pair.

    `window` is the band of critical values the side can actually produce: outward from the onset by the distance the
    onset sits from the normal range (the legacy generators mirrored that distance rather than walking to the sentinel,
    `gen_critical_value.py:114-117`), cut off at the declared end when that is nearer. A side with no room is dropped, so
    whatever this returns is always past the bound.
    """
    normal = bounds_of(field).get("normal") or [0.0, 0.0]
    out: List[Tuple[str, float, Tuple[float, float]]] = []
    for side, ranges in (bounds_of(field).get("critical") or {}).items():
        if not ranges:
            continue
        lo, hi = ranges[0]
        if side == "high":
            onset = lo
            window = (onset, min(hi, onset + max(onset - normal[1], step(field))))
        else:
            onset = hi
            window = (max(lo, onset - max(normal[0] - onset, step(field))), onset)
        if window[0] <= window[1]:
            out.append((side, onset, window))
    return out


def normal_value(field: dict, rng: Random) -> float:
    """A measurement inside the field's `normal` bound, the way `gen_critical_value.py:104` has always put it.

    The boundary the hard cases sit on is a **random point** of the range. Pinning it to the lower end — what the engine
    did — sends `common.boundary_value`'s `span <= 0` branch back with `round(threshold)` on about half the calls, so
    `edu-essay-scoring`'s three components declared on `normal [1, 9]` sat on 1 and the weighted score its rule asks for
    (>= 7) was almost never reached (§6, defect 8; the `LEDGER`'s `final_band`).
    """
    low, high = bounds_of(field)["normal"]
    decimals = decimals_of(field)
    if high <= low:
        return quantize(rng.uniform(low, low + 1.0), decimals)
    return common.boundary_value(rng, rng.uniform(low, high), low, high, decimals=decimals)


def critical_value(field: dict, rng: Random) -> Optional[float]:
    """A measurement just past one of the field's critical onsets, or None when no side has room.

    The side is chosen among the ones with a non-empty window, and `common.boundary_value`'s near-band hugs the onset:
    a value that only barely crosses is the case the model has to get right, while a sentinel-wide uniform draw teaches
    the shortcut "big number -> critical".
    """
    sides = critical_sides(field)
    if not sides:
        return None
    side, onset, (lo, hi) = rng.choice(sides)
    return common.boundary_value(rng, onset, lo, hi, side=(side == "high"), decimals=decimals_of(field))


def crossed(field: dict, rng: Random) -> Optional[float]:
    """A measurement strictly on the safe side of one of the field's critical bounds — the minimal pair's other half.

    The band stops one `step` before the onset, so the value cannot land back inside the range it was meant to escape;
    building the window out of `normal`'s own width instead (§6, defect 5) is what made `critical: {"low": [[-1e9, 30]]}`
    unflippable forever. A field with two critical sides is only flippable on a side whose safe band sits outside *both*
    ranges, so the candidate is checked before it comes back and the caller drops the pair when it fails.
    """
    sides = critical_sides(field)
    if not sides:
        raise UnsupportedField(f"numeric field {field.get('name')!r} has no critical bound to cross")
    normal = bounds_of(field).get("normal") or [0.0, 0.0]
    decimals = decimals_of(field)
    bands = []
    for side, onset, _ in sides:
        if side == "high" and onset - step(field) > normal[0]:
            bands.append((onset - step(field), normal[0], onset - step(field), False))
        elif side != "high" and onset + step(field) < normal[1]:
            bands.append((onset + step(field), onset + step(field), normal[1], True))
    if not bands:
        return None
    threshold, low, high, above = rng.choice(bands)
    value = common.boundary_value(rng, threshold, low, high, side=above, decimals=decimals)
    return value if not in_critical(value, field) else None


def date_bounds(field: dict) -> Tuple[date, date]:
    """The field's declared `range` as two real dates, low first — the same window `sample_date` draws inside."""
    window = field.get("range")
    if not isinstance(window, list) or len(window) != 2:
        raise UnsupportedField(f"date field {field.get('name')!r} needs a 'range' of two ISO dates")
    try:
        low, high = (date.fromisoformat(str(d)) for d in window)
    except ValueError as error:
        raise UnsupportedField(f"date field {field.get('name')!r}: bad 'range' ({error})") from None
    return (low, high) if low <= high else (high, low)


def sample_element(field: dict, rng: Random, spec: dict, index: int = 0) -> Any:
    """One element of a list field, from its `items.element` schema or its scalar `item_values` pool."""
    element = (field.get("items") or {}).get("element")
    if element is not None:
        return sample({**element, "name": f"{field.get('name')}[{index}]"}, rng, spec)
    if "item_values" in field:
        pool = field["item_values"]
        if not pool:
            raise UnsupportedField(f"list field {field.get('name')!r} has an empty 'item_values'")
        return rng.choice(pool)
    raise UnsupportedField(f"list field {field.get('name')!r} needs 'item_values' or 'items.element'")


def sample_numeric(field: dict, rng: Random, spec: dict) -> Any:
    """A value inside the field's `normal` bound, as a number (design doc D3).

    Not a formatted string since PR2a: the unit belongs to the record's surface, which `sampler.BoundarySampler.render`
    builds under `generator.render_units`, while the rules get the arithmetic this field was declared for.
    """
    if bounds_of(field).get("normal") is None:
        raise UnsupportedField(f"numeric field {field.get('name')!r} has no 'normal' bound")
    return typed_value(field, normal_value(field, rng))


def sample_enum(field: dict, rng: Random, spec: dict) -> Any:
    return rng.choice(pool_of(field, spec))


def sample_bool(field: dict, rng: Random, spec: dict) -> Any:
    return rng.random() < float(field.get("true_share", 0.5))


def sample_text(field: dict, rng: Random, spec: dict) -> Any:
    """One string from the spec's inline pool (a chief complaint, a clause, a review comment)."""
    return rng.choice(pool_of(field, spec))


def sample_date(field: dict, rng: Random, spec: dict) -> str:
    """An ISO date inside `range` (inclusive). ISO because JSON has no date type and `kev.api.date_facts`
    already recognises `\\d{4}-\\d{2}-\\d{2}`, so a time-sensitive scenario gets day counts for free."""
    low, high = date_bounds(field)
    return (low + timedelta(days=rng.randint(0, (high - low).days))).isoformat()


def sample_list(field: dict, rng: Random, spec: dict) -> Any:
    """k sampled elements, k in `[min, max]`.

    The element is either a scalar drawn from `item_values`, or any declared field type via `items.element`, which
    reuses this same dispatch instead of a second list schema (design doc D15).
    """
    low = int(field.get("min", 1))
    high = int(field.get("max", low))
    count = rng.randint(low, max(low, high))
    return [sample_element(field, rng, spec, i) for i in range(count)]


def sample_object(field: dict, rng: Random, spec: dict) -> Any:
    """A dict built from the field's declared sub-fields (each one a normal field declaration)."""
    subfields = field.get("fields")
    if not subfields:
        raise UnsupportedField(f"object field {field.get('name')!r} declares no 'fields'")
    return {sub["name"]: sample(sub, rng, spec) for sub in subfields}


def sample_catalog(field: dict, rng: Random, spec: dict) -> Any:
    """k candidates drawn without replacement out of the field's pool (design doc D10).

    The return value is the *derived view*, not a surface: every candidate is an object that carries its own label
    attributes (`{"name": "持续胸痛", "urgency": 2, "red_flag": true}`), so putting it in the state would print the answer
    into the prompt — `kev.api.render` flattens every key of a list-of-dict. `derive` is what turns this into a record.

    Without replacement because two draws of the same candidate would give a rule the same evidence twice and make the
    record look like a duplicate. Copies, not the spec's own dicts: a candidate object ends up in `_meta.derive`, and
    the spec stays the read-only truth source `resolve_spec` handed out.
    """
    pool = field.get("pool")
    if not isinstance(pool, list) or not pool:
        raise UnsupportedField(f"catalog field {field.get('name')!r} needs a non-empty 'pool' of candidate objects")
    if not all(isinstance(candidate, dict) for candidate in pool):
        raise UnsupportedField(f"catalog field {field.get('name')!r} has a pool entry that is not an object")
    draw = field.get("draw") or {}
    if not isinstance(draw, dict):
        raise UnsupportedField(f"catalog field {field.get('name')!r} declares a 'draw' that is not an object")
    try:
        low, high = int(draw.get("min", 1)), int(draw.get("max", draw.get("min", 1)))
    except (TypeError, ValueError) as error:
        raise UnsupportedField(f"catalog field {field.get('name')!r} declares draw {draw!r}: {error}") from None
    if low < 0 or high < low:
        raise UnsupportedField(f"catalog field {field.get('name')!r} declares draw {draw!r}, which is not 0 <= min <= max")
    high = min(high, len(pool))
    return [dict(candidate) for candidate in rng.sample(pool, rng.randint(min(low, high), high))]


SAMPLERS: Dict[str, Callable[[dict, Random, dict], Any]] = {
    "numeric": sample_numeric,
    "enum": sample_enum,
    "bool": sample_bool,
    "text": sample_text,
    "date": sample_date,
    "list": sample_list,
    "object": sample_object,
    "catalog": sample_catalog,
}


# --- the minimal pair's flip (design doc D8) ------------------------------------------------------------


def flip(field: dict, value: Any, rng: Random, spec: dict) -> Optional[Any]:
    """A different value for the same field, moved the way *that type* crosses a decision.

    Each type has its own other side: a measurement goes to the safe side of its bound, an enum or a text takes another
    value from the same pool, a bool is negated, a date moves to the far half of its window, a list grows or shrinks by one
    element, an object has one sub-field moved (D15's recursion makes that a call to this same function), and a catalog
    swaps one drawn candidate — the only type whose value *is* its evidence, so the candidate is what has to move.

    None means the field cannot be moved (a one-option pool, a list at both bounds, a measurement with no safe band), and
    the caller drops the pair: a twin that cannot change its label teaches nothing, which is the rule
    `common.minimal_pair` already enforces for the legacy generators.
    """
    kind = field_type(field)
    if kind == "numeric":
        safe = crossed(field, rng)
        return None if safe is None else typed_value(field, safe)
    if kind in ("enum", "text"):
        others = [option for option in pool_of(field, spec) if option != value]
        return rng.choice(others) if others else None
    if kind == "bool":
        return not bool(value)
    if kind == "date":
        return flip_date(field, value, rng)
    if kind == "list":
        return flip_list(field, value, rng, spec)
    if kind == "object":
        return flip_object(field, value, rng, spec)
    if kind == "catalog":
        return flip_catalog(field, value, rng)
    raise UnsupportedField(f"field {field.get('name')!r} declares unknown type {kind!r} "
                           f"(known: {', '.join(sorted(SAMPLERS))})")


def flip_date(field: dict, value: Any, rng: Random) -> Optional[str]:
    """A date on the far half of the window, so `state['到期日'] - 今日` changes sign rather than just its value."""
    low, high = date_bounds(field)
    try:
        current = date.fromisoformat(str(value))
    except ValueError:
        return None
    if high <= low:
        return None
    middle = low + timedelta(days=(high - low).days // 2)
    start, end = (middle + timedelta(days=1), high) if current <= middle else (low, middle)
    if start > end:
        return None
    return (start + timedelta(days=rng.randint(0, (end - start).days))).isoformat()


def flip_list(field: dict, value: Any, rng: Random, spec: dict) -> Optional[List[Any]]:
    """One element fewer, or one more when the list is already at `min` — the length is what a list rule reads."""
    items = list(value or [])
    low = int(field.get("min", 1))
    high = int(field.get("max", low))
    if items and len(items) > low:
        shorter = list(items)
        shorter.pop(rng.randrange(len(shorter)))
        return shorter
    if len(items) < max(low, high):
        return items + [sample_element(field, rng, spec, len(items))]
    return None


def flip_object(field: dict, value: Any, rng: Random, spec: dict) -> Optional[dict]:
    """Exactly one sub-field moved, the same flip one level down (design doc D15).

    Sub-fields are tried in a random order and the first that can move wins, so a pair over an object whose first key is
    a one-option enum still gets a twin instead of returning None. A sub-field that *cannot* be flipped at all — a
    measurement with no `critical` bound, which `crossed` refuses — is the same kind of answer as a one-option enum and
    is skipped here rather than allowed to escape: it used to raise through this loop, so half the draws of an object
    whose second key is flippable lost the pair outright (measured 100 of 200 before, 200 of 200 after).
    """
    if not isinstance(value, dict):
        return None
    declared = {sub["name"]: sub for sub in field.get("fields") or []}
    for name in rng.sample(sorted(value), len(value)):
        sub = declared.get(name)
        if sub is None:
            continue
        try:
            moved = flip(sub, value[name], rng, spec)
        except UnsupportedField:
            continue
        if moved is not None:
            flipped = dict(value)
            flipped[name] = moved
            return flipped
    return None


def flip_catalog(field: dict, value: Any, rng: Random) -> Optional[List[dict]]:
    """One drawn candidate replaced by another the record did not draw (design doc D8, the catalog half).

    The replacement comes from the pool minus the current draw, so the twin stays a without-replacement draw
    (`sample_catalog`'s own rule: the same candidate twice hands a rule the same evidence twice) and exactly one piece of
    evidence moves. The engine rebuilds the surfaces and re-evaluates the rules on the new draw, which is the point: the
    label has to move because a *different* candidate was chosen, not because a string was edited.
    """
    drawn = list(value or [])
    left = [candidate for candidate in field.get("pool") or [] if candidate not in drawn]
    if not drawn or not left:
        return None
    moved = list(drawn)
    moved[rng.randrange(len(moved))] = dict(rng.choice(left))
    return moved


def sample(field: dict, rng: Random, spec: dict) -> Any:
    """One value for `field`, dispatched on its declared type.

    An unknown type is refused here rather than falling through to numeric: silently treating an enum as a number is
    how the engine produced 30 records of dead data per scenario before fail-loud existed.
    """
    kind = field_type(field)
    sampler = SAMPLERS.get(kind)
    if sampler is None:
        raise UnsupportedField(f"field {field.get('name')!r} declares unknown type {kind!r} "
                               f"(known: {', '.join(sorted(SAMPLERS))})")
    return sampler(field, rng, spec)


def steerable(field: dict) -> bool:
    """True iff a `(tier, category)` plan target can be realized on this field.

    Tiers come from `tier_windows`, which map a field name onto numeric ranges, so only a numeric field with a
    `critical` bound can be pushed to a tier. Everything else can still be drawn into a record as a companion field.
    """
    if field_type(field) != "numeric":
        return False
    return bool(bounds_of(field).get("critical"))
