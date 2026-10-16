"""PairBuilder — minimal pair: the twin of a record with exactly one *field* moved (design doc D8).

Spec §3.3. Reads `spec_json.generator.augmentation.minimal_pair` for rate + strategy.

What changed in PR1a is the shape it works on: the sampler's **flat field view** (pre-skeleton) instead of reaching into
`record["state"]["labs"]`. The engine re-assembles the twin with `make_record`, so the field's own `path` decides where
the flipped value lands (design doc D2) and a scenario without a `labs` key can have minimal pairs at all.

PR3 made the flip itself typed: `values.flip` moves each field type the way *that type* crosses a decision — a
measurement to the safe side of its bound, an enum or a text to another value of the same pool, a bool to its negation,
a date to the far half of its window, a list by one element, an object by one sub-field, a catalog by one drawn
candidate. One field, one move: what the twin shows is that fact dissolved into the rest, so a catalog pair changes one
candidate in `_meta.derive` and every surface that field's `surface` builds (D11 is what makes those two the same fact).

The twin therefore carries the *derived* view as well as the field view, and the engine rebuilds the surfaces and
re-evaluates the rules on it. A pair whose label does not move is dropped rather than written: a twin that teaches the
same answer twice is noise, which is the rule `common.minimal_pair` already enforces for the legacy generators.
"""
from __future__ import annotations
from random import Random
from typing import Any, Dict, List, Optional, Set, Tuple

from . import values


def fact_keys(field: dict, name: str) -> Set[str]:
    """The field-view keys one fact is allowed to move: the field itself plus every key its `surface` builds.

    D11 makes those the same fact — the drawn candidate and the chief complaint spelled out of it are one thing seen
    two ways — so a catalog pair that changes the draw and its two surfaces is still *one* changed fact, while a pair
    that also moved an unrelated field would not be a minimal pair. The engine asserts the changed keys sit inside this
    set.
    """
    return {name} | set(field.get("surface") or {})


class PairBuilder:
    def __init__(self, augmentation: Optional[dict] = None, sampler=None, spec: Optional[dict] = None):
        self.augmentation = augmentation or {}
        self.sampler = sampler
        self.spec = spec or {}

    def candidates(self, state: Dict[str, Any], derived: Dict[str, Any], fields: Dict[str, dict],
                   preferred: Optional[str], rng: Random) -> List[str]:
        """The names worth moving, best first.

        `preferred` is the field the plan steered — the boundary the record was bought for, so it leads. The rest come in
        a shuffled order rather than in spec order: a run that always moved the same companion would demonstrate one
        boundary and leave the others untaught.
        """
        present = [name for name in fields if name in state or name in (derived or {})]
        lead = [preferred] if preferred in present else []
        rest = [name for name in present if name != preferred]
        return lead + rng.sample(rest, len(rest))

    def build(self, state: Dict[str, Any], fields: Dict[str, dict], name: Optional[str], rng: Random,
              derived: Optional[Dict[str, Any]] = None) -> Optional[Tuple[str, Dict[str, Any], Dict[str, Any]]]:
        """Move field `name` (or the best candidate if it is None), as `(name, twin view, twin derived)`.

        None comes back when nothing can be moved: no candidate, a one-option pool, a list pinned between its `min` and
        `max`, a measurement with no safe band on either side of its bound. A field whose declaration cannot be read at
        all — a numeric with no `critical` to cross — is the same answer, because a twin that cannot change its label is
        not a minimal pair; the sampler already refused an unknown `type` before this point, so nothing to catch here
        hides a schema error. The engine drops the pair rather than writing a duplicate.
        """
        for candidate in self.candidates(state, derived, fields, name, rng):
            field = fields[candidate]
            moves = derived or {}
            current = moves.get(candidate) if candidate in moves else state.get(candidate)
            try:
                moved = values.flip(field, current, rng, self.spec)
            except values.UnsupportedField:
                continue
            if moved is None or moved == current:
                continue
            twin_state = dict(state)
            twin_derived = dict(moves)
            if candidate in twin_derived:
                twin_derived[candidate] = moved
            else:
                twin_state[candidate] = moved
            return candidate, twin_state, twin_derived
        return None
