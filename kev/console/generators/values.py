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
"""
from __future__ import annotations

from datetime import date, timedelta
from random import Random
from typing import Any, Callable, Dict, List

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


def _pool(field: dict, spec: dict) -> List[Any]:
    """A field's inline value pool, or the generator-level list `values_ref` points at (design doc D13).

    Pools live in the spec only: a `corpus` outside the repository would break deterministic replay and would not
    exist on the CI machine, so there is no path for it here.
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
    if not isinstance(path, list) or not path or not all(isinstance(step, str) and step for step in path):
        raise UnsupportedField(f"field {field.get('name')!r} declares a bad 'path' {path!r}")
    return list(path)


def sample_numeric(field: dict, rng: Random, spec: dict) -> Any:
    """A value inside the field's `normal` bound, as a number (design doc D3).

    Not a formatted string since PR2a: the unit belongs to the record's surface, which `sampler.BoundarySampler.render`
    builds under `generator.render_units`, while the rules get the arithmetic this field was declared for.
    """
    from . import common, ops
    normal = bounds_of(field).get("normal")
    if normal is None:
        raise UnsupportedField(f"numeric field {field.get('name')!r} has no 'normal' bound")
    low, high = normal
    # The same call ops.normal_value makes, so a field that still spells `normal` samples byte for byte like the
    # legacy generator; `bounds` is read here so an industry's own bound names never reach ops.py (design doc D12).
    value = common.boundary_value(rng, threshold=low, low=low, high=high, near=0.0,
                                  decimals=field.get("decimals", 1))
    return ops.typed_value(field, value)


def sample_enum(field: dict, rng: Random, spec: dict) -> Any:
    return rng.choice(_pool(field, spec))


def sample_bool(field: dict, rng: Random, spec: dict) -> Any:
    return rng.random() < float(field.get("true_share", 0.5))


def sample_text(field: dict, rng: Random, spec: dict) -> Any:
    """One string from the spec's inline pool (a chief complaint, a clause, a review comment)."""
    return rng.choice(_pool(field, spec))


def sample_date(field: dict, rng: Random, spec: dict) -> str:
    """An ISO date inside `range` (inclusive). ISO because JSON has no date type and `kev.api.date_facts`
    already recognises `\\d{4}-\\d{2}-\\d{2}`, so a time-sensitive scenario gets day counts for free."""
    window = field.get("range")
    if not isinstance(window, list) or len(window) != 2:
        raise UnsupportedField(f"date field {field.get('name')!r} needs a 'range' of two ISO dates")
    try:
        low, high = (date.fromisoformat(str(d)) for d in window)
    except ValueError as error:
        raise UnsupportedField(f"date field {field.get('name')!r}: bad 'range' ({error})") from None
    if high < low:
        low, high = high, low
    return (low + timedelta(days=rng.randint(0, (high - low).days))).isoformat()


def sample_list(field: dict, rng: Random, spec: dict) -> Any:
    """k sampled elements, k in `[min, max]`.

    The element is either a scalar drawn from `item_values`, or any declared field type via `items.element`, which
    reuses this same dispatch instead of a second list schema (design doc D15).
    """
    low = int(field.get("min", 1))
    high = int(field.get("max", low))
    count = rng.randint(low, max(low, high))
    element = (field.get("items") or {}).get("element")
    if element is not None:
        return [sample({**element, "name": f"{field.get('name')}[{i}]"}, rng, spec) for i in range(count)]
    if "item_values" in field:
        pool = field["item_values"]
        if not pool:
            raise UnsupportedField(f"list field {field.get('name')!r} has an empty 'item_values'")
        return [rng.choice(pool) for _ in range(count)]
    raise UnsupportedField(f"list field {field.get('name')!r} needs 'item_values' or 'items.element'")


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
