"""Domain operator whitelist for simpleeval — the bridge between the JSON rule DSL and the legacy gen_*.py logic.

Each operator here is a pure function with a docstring that cites the gen_*.py source line it replaces, so a reviewer
can trace the spec back to the legacy code. Operators are registered in ALLOWED (alphabetical) and consumed by
`rules.evaluate` / the surface evaluator through `derive.operators`, which is the one place the rng gets bound.
"""
from __future__ import annotations
from datetime import date
from random import Random
from typing import Any, Callable, Dict, List, Optional, Tuple


def bool_to_str(b: bool) -> str:
    """`True`/`False` -> `"true"`/`"false"` (noul question labels are strings, not Python bools)."""
    return "true" if b else "false"


def any_outside_critical(state: dict, fields: List[dict]) -> bool:
    """True iff any field in `state` is in its `critical` range. Replaces gen_critical_value.outside(panels[name], value).

    The `state` is keyed by field name; the `value` is parsed from the formatted string ("6.2 mmol/L" -> 6.2).
    """
    for field in fields:
        if field["name"] not in state:
            continue
        # Reuse the same boundary parser: the spec stores decimals; we round parsed value to that.
        try:
            value = _parse_value(state[field["name"]], field.get("decimals", 1))
        except (ValueError, KeyError):
            continue
        if _is_in_critical_range(value, field):
            return True
    return False


def min_tier(state: dict, fields: List[dict], tier_windows: dict) -> int:
    """The fastest notify tier (0=immediate) across all critical items in `state`. Returns 3 if nothing is critical."""
    fastest = 3
    for field in fields:
        if field["name"] not in state:
            continue
        try:
            value = _parse_value(state[field["name"]], field.get("decimals", 1))
        except (ValueError, KeyError):
            continue
        if not _is_in_critical_range(value, field):
            continue
        # Walk tier_windows from 0 upward; first tier that contains value wins.
        for tier_str, mapping in tier_windows.items():
            tier = int(tier_str)
            for field_name, ranges in mapping.items():
                if field_name != field["name"]:
                    continue
                for low, high in ranges:
                    if low <= value <= high:
                        if tier < fastest:
                            fastest = tier
                        break
    return fastest


def fastest_tier_critical_item(state: dict, fields: List[dict], categories: dict, tier_windows: dict) -> str:
    """The category of the field with the fastest notify tier. Returns 'none' if nothing is critical."""
    tier = min_tier(state, fields, tier_windows)
    if tier == 3:
        return "none"
    for field in fields:
        if field["name"] not in state:
            continue
        try:
            value = _parse_value(state[field["name"]], field.get("decimals", 1))
        except (ValueError, KeyError):
            continue
        if not _is_in_critical_range(value, field):
            continue
        for tier_str, mapping in tier_windows.items():
            if int(tier_str) != tier:
                continue
            for field_name, ranges in mapping.items():
                if field_name != field["name"]:
                    continue
                for low, high in ranges:
                    if low <= value <= high:
                        return categories.get(field_name, "other")
    return "none"


def _parse_value(formatted, decimals: int) -> float:
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


def _is_in_critical_range(value: float, field: dict) -> bool:
    """True iff `value` falls inside the field's critical.low or critical.high range."""
    crit = field.get("critical", {})
    for side, ranges in crit.items():
        for low, high in ranges:
            if low <= value <= high:
                return True
    return False


def normal_value(rng: Random, field: dict) -> float:
    """Replaces gen_critical_value.normal_value."""
    from common import boundary_value
    low, high = field["normal"]
    return boundary_value(rng, threshold=low, low=low, high=high, near=0.0, decimals=field.get("decimals", 1))


def critical_value(rng: Random, field: dict) -> float:
    """Replaces gen_critical_value.critical_value."""
    from common import boundary_value
    crit = field.get("critical", {})
    for side, ranges in crit.items():
        if not ranges:
            continue
        low, high = ranges[0]
        threshold = high if side == "high" else low
        return boundary_value(rng, threshold=threshold, low=low, high=high, near=0.0, decimals=field.get("decimals", 1))
    raise ValueError(f"field {field['name']} has no critical range")


def crossed(rng: Random, field: dict) -> float:
    """Replaces gen_critical_value.crossed — a safe-side value just outside critical."""
    from common import boundary_value
    crit = field.get("critical", {})
    for side, ranges in crit.items():
        if not ranges:
            continue
        low, high = ranges[0]
        normal = field["normal"]
        if side == "high":
            # Safe side: just below critical.low
            threshold = high
            safe_low, safe_high = normal[1] - (high - low), high - 0.01
            return boundary_value(rng, threshold=safe_high, low=safe_low, high=safe_high, near=0.0, decimals=field.get("decimals", 1))
        else:
            threshold = low
            safe_low, safe_high = low + 0.01, normal[0] + (low - normal[0])
            return boundary_value(rng, threshold=safe_low, low=safe_low, high=safe_high, near=0.0, decimals=field.get("decimals", 1))
    raise ValueError(f"field {field['name']} has no critical range")


def realize_tier(rng: Random, field: dict, tier: int, tier_windows: dict) -> Optional[float]:
    """Replaces gen_critical_value.realize_tier — a value whose notification tier is exactly `tier`, or None."""
    name = field["name"]
    mapping = tier_windows.get(str(tier), {})
    ranges = mapping.get(name)
    if not ranges:
        return None
    low, high = rng.choice(ranges)
    decimals = field.get("decimals", 1)
    for _ in range(6):
        value = round(rng.uniform(low, high), decimals)
        if _is_in_critical_range(value, field) and min_tier({name: value}, [field], tier_windows) == tier:
            return value
    return None


def _format(field: dict, value: float, with_unit: bool = True) -> str:
    """Replaces gen_critical_value.format_measurement.

    The renderer of a measurement's *surface*, not of its value: since PR2a the field view carries a number and only the
    record's text goes through here (`sampler.BoundarySampler.render`, gated by `generator.render_units`).
    """
    decimals = field.get("decimals", 1)
    unit = field.get("unit", "")
    rounded = round(value, decimals)
    if with_unit and unit:
        return f"{rounded} {unit}"
    return str(rounded)


def typed_value(field: dict, value: float) -> float:
    """The value a numeric field's view holds: the number, rounded to the field's own `decimals` (design doc D3).

    Rounded here rather than only at render time so the rule, the critical check and the shipped text agree on one
    number — a rule that reads 6.245 while the model reads "6.2 mmol/L" would be a label the prompt cannot support.
    """
    return round(value, field.get("decimals", 1))


class MissingEvidence(LookupError):
    """A rule read a state key this record does not carry (design doc §5.3 class A).

    Not a `KeyError`, and deliberately so: `selectors` let one record sample three fields and another six, so "this
    record has no evidence for that rule" is a normal outcome that must read as *no match*, while a `KeyError` from
    inside an operator is a bug that has to stay loud. `rules.evaluate` catches exactly this class and nothing else, so
    the two stop looking alike the way the silent `except Exception` made them look alike before.
    """

    def __init__(self, key: str):
        super().__init__(key)
        self.key = key


class EvidenceView(dict):
    """The rule's read-only state: a missing key is `MissingEvidence`, not `None` and not a `KeyError`.

    `dict.__missing__` is what simpleeval's subscript handler runs into (`_eval_subscript` raises whatever the
    container raises), so the distinction lives in the mapping rather than in a try/except around every expression.
    Containment (`'x' in state`) and `.get` keep their plain-dict answers: an operator that asks politely is stating a
    condition, not reading evidence.
    """

    def __missing__(self, key):
        raise MissingEvidence(key)


def rule_view(state: dict, fields: List[dict]) -> "EvidenceView":
    """The field view as the rules see it: a declared `date` field is the date it spells, not the string holding it.

    The record keeps the ISO string (JSON has no date type, `kev/api.date_facts` reads that string, and a minimal pair
    compares it), but `(state['到期日'] - state['今日']).days <= 3` is how a spec author writes a deadline, and simpleeval
    evaluates it the moment the two operands are real dates (design doc §5.3 class C, settled by probe). A value that is
    not an ISO date — a sentinel like `尚未`, an empty string — stays the string it is, because the rule that matches it
    with `==` has to keep matching; the conversion is per value, not per field.

    The copy is an `EvidenceView` so that the other half of the same probe's finding — ten of the twelve collapsed
    scenarios were losing rules to a field this record never sampled — reads as *this rule does not match* instead of
    as an exception swallowed by the engine.
    """
    dates = {field["name"] for field in fields if (field.get("type") or "numeric") == "date"}
    view = EvidenceView(state)
    for name in dates:
        raw = view.get(name)
        if not isinstance(raw, str):
            continue
        try:
            view[name] = date.fromisoformat(raw)
        except ValueError:
            continue
    return view


def any_special_population(drug: dict, flags: list) -> bool:
    """Replaces gen_medication_review.special_population branch in evaluate(). drug is a dict; flags is a list of patient state_flags."""
    for pop in drug.get("special_population", []):
        if any(flag in pop for flag in flags):
            return True
    return False


def dose_exceeds(drug: dict, dose_per: float, times_per_day: int) -> bool:
    """Replaces gen_medication_review.dose_over."""
    daily = drug.get("max_daily_dose")
    if daily is None:
        return False
    return dose_per * times_per_day > daily


def duplicate_category(drug: dict, current_meds: list) -> bool:
    """Replaces gen_medication_review.duplicate."""
    drug_cat = drug.get("category")
    for other in current_meds:
        if other.get("category") == drug_cat and other.get("name") != drug.get("name"):
            return True
    return False


def indication_matches(drug: dict, indication: str) -> bool:
    """True iff the indication is in drug.indications. Replaces gen_medication_review.indication_mismatch's negation."""
    return indication in drug.get("indications", [])


def lift_severity(severity: int, high_dep: bool) -> int:
    """Replaces gen_nursing_quality.decide's high-dependency lift: severity += 1 if high_dep."""
    return severity + (1 if high_dep else 0)


def missing_element(missing: list, mismatch: bool) -> str:
    """Replaces gen_record_summary.ELEMENT_SEVERITY mapping. Returns a severity label."""
    if len(missing) >= 3:
        return "3"
    if len(missing) >= 1 or mismatch:
        return "2"
    return "1"


def tier_priority_arbiter(presentations: list) -> str:
    """Replaces gen_diagnosis.derive's `min(top, key=...)` — pick the highest-priority department from a list of
    (department, score) tuples. The priority order is the index of the department in `department_index`.
    """
    if not presentations:
        return "undirected"
    return min(presentations, key=lambda p: p.get("priority", 99))[0]


# --- catalog surface operators (design doc D10/D11) -------------------------------------------------------
#
# A catalog candidate carries its own label attributes, so the state can only show it *dissolved*: these operators are
# the enumeration §7.1 asked for, one per string built in `gen_triage.py:106-116` and `gen_diagnosis.py:144-152`. Every
# surface in those two generators is one of these composed with `+`, which is what lets D11 refuse a template language.


def join_by(items: List[dict], attr: str, sep: str) -> str:
    """`"，".join(s[0] for s in symptoms)` (gen_triage.py:109, gen_diagnosis.py:146) over drawn candidates."""
    return sep.join(str(item[attr]) for item in items)


def pluck(items: List[dict], attr: str) -> List[Any]:
    """`[s[0] for s in symptoms]` (gen_triage.py:112) — the same attribute as a list instead of a joined string."""
    return [item[attr] for item in items]


def rest(items: List[Any]) -> List[Any]:
    """`symptoms[1:]` (gen_triage.py:112): every candidate but the lead one, so a surface can split chief complaint
    from accompanying symptoms. A single-candidate draw has no remainder; `default_if_empty` fills that in."""
    return list(items)[1:]


def where(items: List[dict], attr: str, value: Any) -> List[dict]:
    """`[s for s in symptoms if s[2]]` (gen_triage.py:115): the candidates whose attribute matches.

    A rule needs this too — `len(where(derived['症状'], 'red_flag', True)) > 0` is how "any red flag" is written today,
    because simpleeval 1.x has no generator expressions outside `EvalWithCompoundTypes`, which since PR2b is what
    the rules run under too (`rules.py`).
    """
    return [item for item in items if item.get(attr) == value]


def default_if_empty(value: Any, fallback: Any) -> Any:
    """`... or "无"` / `... or ["无"]` / `labs or {"血常规": "未见明显异常"}` (gen_triage.py:112,115; gen_diagnosis.py:148).

    Falsy, not None: an empty joined string and an empty list both mean "nothing of that kind was drawn", which is
    exactly the case the legacy generators wrote a placeholder for. A numeric zero would also fall back, so do not use
    this on a bound — read the field's `bounds` instead.
    """
    return fallback if not value else value


def max_attr(items: List[dict], attr: str, default: Any = 0) -> Any:
    """`max(p[2] for p in presentations)` (gen_diagnosis.py:97): the highest urgency among the drawn candidates."""
    found = [item[attr] for item in items if attr in item]
    return max(found) if found else default


def min_attr(items: List[dict], attr: str, default: Any = 0) -> Any:
    """The lowest `attr` across candidates, for pools where the smaller number is the more urgent answer."""
    found = [item[attr] for item in items if attr in item]
    return min(found) if found else default


def attr_of_max(items: List[dict], key: str, attr: str, default: Any = "") -> Any:
    """The `attr` of the candidate whose `key` is largest: `best = max(symptoms, key=...); department = best[1]`
    (gen_triage.py:81-82). Ties go to the first candidate, the way the legacy `max` picked one.

    This is the operator that lets a label come out of a *drawn* catalog candidate rather than a copy: "which team
    owns this incident" is an attribute of the most urgent signal, and the rule that reads it never reads the surface.
    """
    ranked = [item for item in items if key in item]
    if not ranked:
        return default
    return max(ranked, key=lambda item: item[key]).get(attr, default)


def attr_of_min(items: List[dict], key: str, attr: str, default: Any = "") -> Any:
    """The `attr` of the candidate whose `key` is smallest: `best = min(top, key=lambda p: p.priority)`
    (gen_diagnosis.py:102), the tie-break that sends two equally urgent findings to the more specialised owner.
    """
    ranked = [item for item in items if key in item]
    if not ranked:
        return default
    return min(ranked, key=lambda item: item[key]).get(attr, default)


def pick(rng: Random, pool: List[Any]) -> Any:
    """`rng.choice(TONE)` (gen_triage.py:110, gen_diagnosis.py:146): one line out of a pool, at random.

    The only operator that needs the record's random source. A spec never writes `pick(rng, ...)`: the engine binds
    `rng` into a one-argument closure per record (`derive.operators`), because a *name* is callable -- a spec could then
    write `rng.seed(0)` or `rng.shuffle(STATE)` and silently break the replay the seed is the whole point of, while the
    binding exposes only the one call we meant to give out. Escaping the sandbox is not the reason: simpleeval refuses
    `__`-prefixed and `func_`-prefixed attributes, so even `pick.args[0].seed.__globals__` dies at `__globals__` (design
    doc §7.1, settled by probe), and the binding is a closure, so there is no `.args` to reach the rng through at all
    (design doc §6, defect 9). That is why ALLOWED below
    carries the two-argument form only as the implementation.
    """
    return rng.choice(pool)


def red_flag_wins(presentations: list) -> bool:
    """True iff any presentation is flagged as a red flag (emergency department + severity >= 2)."""
    return any(p.get("red_flag") for p in presentations)


def pediatric_short_circuit(symptoms: list, age: int) -> bool:
    """True iff any pediatric keyword is present AND the patient is a child. Replaces gen_triage.PEDIATRIC branch."""
    pediatric_keywords = {"小儿", "幼儿", "儿童", "婴儿", "新生儿"}
    if age >= 14:
        return False
    return any(kw in s for s in symptoms for kw in pediatric_keywords)


ALLOWED: Dict[str, Callable[..., Any]] = {
    "abs": abs,
    "all": all,
    "any": any,
    "any_outside_critical": any_outside_critical,
    "any_special_population": any_special_population,
    "attr_of_max": attr_of_max,
    "attr_of_min": attr_of_min,
    "bool_to_str": bool_to_str,
    "default_if_empty": default_if_empty,
    "dose_exceeds": dose_exceeds,
    "duplicate_category": duplicate_category,
    "fastest_tier_critical_item": fastest_tier_critical_item,
    "indication_matches": indication_matches,
    "join_by": join_by,
    "len": len,
    "lift_severity": lift_severity,
    "max": max,
    "max_attr": max_attr,
    "min": min,
    "min_attr": min_attr,
    "min_tier": min_tier,
    "missing_element": missing_element,
    "pediatric_short_circuit": pediatric_short_circuit,
    "pick": pick,
    "pluck": pluck,
    "red_flag_wins": red_flag_wins,
    "rest": rest,
    "round": round,
    "tier_priority_arbiter": tier_priority_arbiter,
    "where": where,
}