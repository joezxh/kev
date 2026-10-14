"""PairBuilder — minimal pair: the twin of a record with exactly one field moved across its boundary.

Spec §3.3. Reads `spec_json.generator.augmentation.minimal_pair` for rate + strategy.

What changed in PR1a is the shape it works on: the sampler's **flat field view** (pre-skeleton) instead of reaching into
`record["state"]["labs"]`. The engine re-assembles the twin with `make_record`, so the field's own `path` decides where
the flipped value lands (design doc D2) and a scenario without a `labs` key can have minimal pairs at all.

The flip itself is still numeric — pushing a measurement to the safe side of its bound (`ops.crossed`). Flipping an
enum, a bool or a catalog candidate is the typed minimal pair of PR3 (design doc D8). It moves the *typed* value, like
everything else in the view since PR2a; the engine re-renders the twin through `make_record`, so the surface and the rule
read the same number the parent's did.
"""
from __future__ import annotations
from copy import deepcopy
from random import Random
from typing import Any, Dict, Optional

from . import values


class PairBuilder:
    def __init__(self, augmentation: Optional[dict] = None, sampler=None):
        self.augmentation = augmentation or {}
        self.sampler = sampler

    def build(self, state: Dict[str, Any], fields: Dict[str, dict], name: Optional[str],
              rng: Random) -> Optional[Dict[str, Any]]:
        """A copy of `state` with field `name` on the safe side of its bound, or None when nothing can be flipped.

        `fields` maps a name to its declaration, restricted to the fields present in `state`. None comes back when
        there is no triggering field, when it is not a numeric one (PR3), or when its critical bound is missing —
        a twin whose label cannot move is not a minimal pair, so the engine drops it rather than writing a duplicate.
        """
        from . import ops
        if name is None or name not in state or name not in fields:
            return None
        field = fields[name]
        if values.field_type(field) != "numeric":
            return None
        safe = ops.crossed(rng, field)
        if ops._is_in_critical_range(safe, field):
            return None
        twin = deepcopy(state)
        twin[name] = ops.typed_value(field, safe)
        return twin
