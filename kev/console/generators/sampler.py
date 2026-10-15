"""BoundarySampler — builds one record's state from spec_json.generator.fields + selectors + state_target.

Spec §3.1. Two separations make the engine generic (design doc D1/D2):

* a field's *value* comes from `values.sample`, which dispatches on the field's declared type, so an enum, a date or a
  list of objects is sampled by its own sampler instead of the numeric one (F1: the line 20/32 spike scenarios died on);
* the state *skeleton* is the spec's own: every field declares a `path` (default: the top level) and the engine-injected
  keys come from `generator.aux`. `patient`/`labs` are no longer hardcoded here — that hardcoding is F2, the reason a
  legal scenario came out shaped like a lab report.

`sample` returns the flat `{field name: value}` view the rules are evaluated against; `make_record` turns that view into
the state a record ships, so a rule never has to know about the skeleton.
"""
from __future__ import annotations
from random import Random
from typing import Any, Dict, List, Optional

from . import ops
from . import values


def place(root: dict, path: List[str], value: Any) -> None:
    """Write `value` at `path` inside `root`, creating intermediate dicts on the way."""
    cursor = root
    for step in path[:-1]:
        nested = cursor.get(step)
        if not isinstance(nested, dict):
            nested = {}
            cursor[step] = nested
        cursor = nested
    cursor[path[-1]] = value


# What one record looks like, as the spec declares it (design doc D6). These were literals until PR3, copied out of
# `gen_critical_value.build` — and `tests/fixtures/critical-value/spec.json` already carried them as the numbers 2-5 and
# 0.35 came from, which is why the defaults below are the released behaviour rather than a new one:
#   min / max                fields per record, the triggering one included (legacy: 1 + `randint(2, 5)`)
#   weight_trigger_extra     chance that a second measurement crosses its bound as well
#   max_trigger_extra        how many candidates that second crossing is tried on
#   max_trigger_tier_drift   how many tiers nearer the fast end that extra may sit (0 = never faster than the target,
#                            which is what keeps the record realising the tier the plan asked for)
# `weight_normal` is accepted for the released specs and deliberately not read here: how many records stay unsteered is
# the plan's decision (`plan_targets`, design doc D5), and a second place that answers it is a second truth.
SELECTOR_DEFAULTS: Dict[str, Any] = {"min": 3, "max": 6, "weight_normal": 1.0, "weight_trigger_extra": 0.35,
                                     "max_trigger_extra": 2, "max_trigger_tier_drift": 0}


class BoundarySampler:
    def __init__(self, fields: List[dict], selectors: List[dict], tier_windows: Optional[Dict[str, dict]] = None,
                 spec: Optional[dict] = None):
        self.fields = fields
        self.selectors = selectors
        self.tier_windows = tier_windows or {}
        self.spec = spec or {}
        self.aux = (self.spec.get("generator") or {}).get("aux") or {}
        # Design doc D3: the value the field view holds is typed, the unit is a property of the shipped text. `on` is the
        # default because that is what every released scenario already does — omitting it must be a decision the spec
        # makes, not a silent change of the prompt a trained checkpoint reads.
        self.render_units = (self.spec.get("generator") or {}).get("render_units", "on")
        if self.render_units not in ("on", "off"):
            raise values.UnsupportedField(
                f"generator.render_units must be 'on' or 'off', not {self.render_units!r}")
        self.selector = self._selector(selectors[0] if selectors else {})

    @staticmethod
    def _selector(declared: dict) -> Dict[str, Any]:
        """One selector, the spec's keys over the defaults — checked once, so a typo cannot sample a whole run wrong.

        `min`/`max` count the *fields in one record*, not the extras: the released specs say `{"min": 3, "max": 6}` for
        what the legacy builder wrote as `1 + rng.randint(2, 5)`. A spec whose minimum the field list cannot fill is not
        refused — the draw is clamped to what exists (design doc D6, which also removes the implicit "a spec needs six
        fields" floor the clamp was hacked in for).
        """
        if not isinstance(declared, dict):
            raise values.UnsupportedField(f"generator.selectors[0] must be an object, not {declared!r}")
        unknown = sorted(set(declared) - set(SELECTOR_DEFAULTS))
        if unknown:
            raise values.UnsupportedField(
                f"generator.selectors[0] declares {unknown}; known: {', '.join(sorted(SELECTOR_DEFAULTS))}")
        selector = {**SELECTOR_DEFAULTS, **declared}
        try:
            low, high = int(selector["min"]), int(selector["max"])
        except (TypeError, ValueError) as error:
            raise values.UnsupportedField(f"selectors min/max must be integers: {error}") from None
        if low < 1 or high < low:
            raise values.UnsupportedField(f"selectors declare {low}..{high} fields per record, which is not 1 <= min <= max")
        for key in ("weight_normal", "weight_trigger_extra", "max_trigger_tier_drift"):
            try:
                float(selector[key])
            except (TypeError, ValueError) as error:
                raise values.UnsupportedField(f"selectors.{key} must be a number: {error}") from None
        if not 0.0 <= float(selector["weight_trigger_extra"]) <= 1.0:
            raise values.UnsupportedField(f"selectors.weight_trigger_extra must be a probability, "
                                          f"not {selector['weight_trigger_extra']!r}")
        if int(selector["max_trigger_extra"]) < 0:
            raise values.UnsupportedField(f"selectors.max_trigger_extra cannot be negative: {selector['max_trigger_extra']!r}")
        selector["min"], selector["max"] = low, high
        selector["max_trigger_extra"] = int(selector["max_trigger_extra"])
        return selector

    def sample(self, state_target, rng: Random) -> Optional[Dict[str, Any]]:
        """One flat field view, typed (design doc D3). Returns None if the target is not realizable.

        `state_target` is None (normal), (tier, category) (share+quota+tier_split), or a string
        (round-robin department/direction). For the string form, the sampler treats it as a category
        hint: it picks a triggering field whose `category` matches; if none match, it falls back to
        a non-triggered sample.
        """
        # Three input shapes — string, tuple, None.
        if isinstance(state_target, str):
            tier, category = None, state_target
        elif state_target:
            tier, category = state_target
        else:
            tier, category = None, "none"
        # Step 1: pick a triggering field.
        if tier is not None:
            # A tier steer needs a numeric field with a critical bound; nothing else can be pushed to a tier, so a
            # target with no such field in the spec is not realizable (and the engine records a normal one instead).
            matching = [f for f in self.fields if values.steerable(f) and f.get("category") == category]
            if not matching:
                return None
            triggering_field = rng.choice(matching)
        elif isinstance(state_target, str):
            matching = [f for f in self.fields if f.get("category") == category]
            triggering_field = rng.choice(matching or self.fields)
        else:
            triggering_field = rng.choice(self.fields)
        # Step 2: fill the record to the selector's own size. `min`/`max` count the fields a record carries, the
        # triggering one included, so the extras are that many minus one, clamped to how many the spec actually declares:
        # a three-field scenario — one catalog pool and two companions, which is how PR1b's catalog fixtures are cut —
        # used to die in `rng.sample` when the draw asked for five. The clamp is also what makes a catalog pool
        # unavoidable in such a spec, so every record carries a `_meta.derive`.
        others = [f for f in self.fields if f["name"] != triggering_field["name"]]
        chosen = {triggering_field["name"]: triggering_field}
        want = max(0, rng.randint(self.selector["min"], self.selector["max"]) - 1)
        for extra in rng.sample(others, min(want, len(others))):
            chosen[extra["name"]] = extra
        # Step 3: sample a value of each field's own type. A catalog field answers with the candidates it drew, which
        # is the label basis rather than a value: `derive.split` takes it out of this view before the engine builds a
        # record out of it (design doc D10/D11).
        state = {name: values.sample(field, rng, self.spec) for name, field in chosen.items()}
        if tier is None:
            return state
        # Step 4: realize the target tier on the triggering field.
        value = ops.realize_tier(rng, triggering_field, tier, self.tier_windows)
        if value is None:
            return None
        state[triggering_field["name"]] = values.typed_value(triggering_field, value)
        # Sometimes add a second critical item (carry-over logic from gen_critical_value.build). Numeric fields only:
        # parsing "true" or a clause text as a measurement is not a thing.
        if rng.random() < self.selector["weight_trigger_extra"]:
            numeric = {n: f for n, f in chosen.items() if values.field_type(f) == "numeric"}
            # The view is typed since D3, so the critical check reads these values directly — the format/parse round
            # trip this used to need was only ever a consequence of the unit living in the value.
            non_critical = [
                n for n, f in numeric.items()
                if not values.in_critical(state[n], f)
            ]
            for other in rng.sample(non_critical, min(self.selector["max_trigger_extra"], len(non_critical))):
                v2 = values.critical_value(numeric[other], rng)
                # The extra may never be faster than the tier the plan asked for (a drift of 0, the released number):
                # the record's tier is the fastest across its critical items, so a faster companion would realise a
                # different tier than the quota paid for.
                if v2 is not None and values.in_critical(v2, numeric[other]) and \
                   ops.min_tier({other: v2}, [numeric[other]],
                                self.tier_windows) >= tier - self.selector["max_trigger_tier_drift"]:
                    state[other] = values.typed_value(numeric[other], v2)
                    break
        return state

    def render(self, field: Optional[dict], value: Any) -> Any:
        """The surface a field's value ships as (design doc D3): a declared measurement gets its unit back when
        `render_units` is `on`, and everything else — an enum, an ISO date, a bool, a list, a surface's result — ships
        exactly what the rules were evaluated against.

        Recursive over D15's element schema, because a numeric nested in a list or an object went through the same
        formatter before PR2a: an element declaring `"unit": ""` shipped as `"0.42"`, and a render that stopped at the
        top level would ship `0.42` instead — a silent record-format change for every list-of-object scenario.

        Only a *declared* field is rendered. A key with no field is a surface expression's own output, and the spec
        already chose its shape there; quietly turning a surface that returned `3` into `"3"` would be this function
        inventing a second surface convention (design doc D11).

        The double rounding is idempotent on purpose: `typed_value` already rounded at the field's `decimals`, so a spec
        that changes one surface cannot move the number a rule compared.
        """
        if field is None:
            return value
        kind = values.field_type(field)
        if kind == "numeric":
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                return value
            return values.format_value(field, value, with_unit=self.render_units == "on")
        if kind == "list" and isinstance(value, list):
            element = (field.get("items") or {}).get("element")
            return [self.render(element, item) for item in value] if element is not None else value
        if kind == "object" and isinstance(value, dict):
            declared = {sub["name"]: sub for sub in field.get("fields") or []}
            return {name: self.render(declared.get(name), item) for name, item in value.items()}
        return value

    def make_record(self, state: dict, dropped: str = "") -> dict:
        """The record's `state`: each sampled value at its field's `path`, plus the spec's `aux` keys.

        `state` is the view `derive.split` and `derive.surfaces` left after taking the catalog draws out, so a key with
        no matching field is a surface expression's result and lands at the top level — where the legacy surfaces live
        (`chief_complaint`, `red_flags`). That is not an accident of this function: a surface that printed a candidate's
        attributes would put the label in the prompt (design doc D11, gate G8).

        This is also where a typed value becomes text: the view holds numbers, the record holds what the model reads
        (`render`, design doc D3).

        `dropped` names the element the Augmentor removed on purpose ("" for none). The only injected source PR1a
        supports is `"dropped"` — `{"missing_context": "dropped"}` yields `["unit"]` — because that is the one value
        the engine owns rather than the sampler. The legacy `ref_ranges_included`/`patient`/`context` keys are ordinary
        declared fields now (design doc D2); spelling the six medical fixtures that way is PR4's job.
        """
        by_name = {field["name"]: field for field in self.fields}
        full: Dict[str, Any] = {}
        for name, value in state.items():
            field = by_name.get(name)
            place(full, values.path_of(field or {"name": name}), self.render(field, value))
        for key, source in self.aux.items():
            if source != "dropped":
                raise values.UnsupportedField(
                    f"generator.aux key {key!r} declares source {source!r}; only 'dropped' is implemented")
            place(full, [key], [dropped] if dropped else [])
        return full
