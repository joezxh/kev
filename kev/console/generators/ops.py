"""Domain operator whitelist for simpleeval — the bridge between the JSON rule DSL and the legacy gen_*.py logic.

Each operator here is a pure function with a docstring that cites the gen_*.py source line it replaces, so a reviewer
can trace the spec back to the legacy code. Operators are registered in ALLOWED (alphabetical) and consumed by
RuleEvaluator via simple_eval(..., functions=ALLOWED).
"""
from __future__ import annotations
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


def _parse_value(formatted: str, decimals: int) -> float:
    """`"6.2 mmol/L"` -> `6.2`. Drops the unit suffix after the first space."""
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
        if _is_in_critical_range(value, field) and min_tier({name: _format(field, value, with_unit=False)}, [field], tier_windows) == tier:
            return value
    return None


def _format(field: dict, value: float, with_unit: bool = True) -> str:
    """Replaces gen_critical_value.format_measurement."""
    decimals = field.get("decimals", 1)
    unit = field.get("unit", "")
    rounded = round(value, decimals)
    if with_unit and unit:
        return f"{rounded} {unit}"
    return str(rounded)


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
    "bool_to_str": bool_to_str,
    "dose_exceeds": dose_exceeds,
    "duplicate_category": duplicate_category,
    "fastest_tier_critical_item": fastest_tier_critical_item,
    "indication_matches": indication_matches,
    "len": len,
    "lift_severity": lift_severity,
    "max": max,
    "min": min,
    "min_tier": min_tier,
    "missing_element": missing_element,
    "pediatric_short_circuit": pediatric_short_circuit,
    "red_flag_wins": red_flag_wins,
    "round": round,
    "tier_priority_arbiter": tier_priority_arbiter,
}