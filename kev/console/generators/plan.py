"""PlanAllocator — turns spec_json.generator.plan_targets into a list of `state_target` values.

Spec §3.4. The engine consumes `state_target` per record; the form depends on the spec:

1. Share + by-category quota + tier_split (numeric critical-value style). Each `state_target` is a
   `(tier, category)` tuple the BoundarySampler resolves through `tier_windows`. Normal records are `None`.
2. Custom round-robin (`plan_targets.custom == "round_robin"`, spec §3.4 last paragraph). Each
   `state_target` is a string (department name, `"emergency"`, `"undirected"`, etc.) — the round-robin
   schedule built from `period` and `slots`. The BoundarySampler/`rules.evaluate` chain that follows needs
   the sampler to handle category strings; round-robin parity is gated on Phase B Task 4 (sampler
   upgrade) + Task 8 (rule operators) — this module just produces the schedule.

Algorithm (share + by_category quota + tier_split):

  1. Resolve the **pool**: how many of the `n` records the plan drives at all (`normal_share`, a top-level
     `share.critical`, or the per-category `share` the legacy specs repeat on every block).
  2. Give each block its part of the pool by **weight**, with largest-remainder rounding so the parts add up to the
     pool exactly and the same spec keeps the same proportions at n = 30 and at n = 3000 (design doc D5, gate G2 — the
     numbers used to be absolute, which is what made `critical-value`'s 5x55 steer *every* record of a 60-record run).
  3. Within a block, split its records across the `{tier: weight}` entries in `tier_split`.
  4. Append `None` records for the remainder so the plan is exactly `n` items long.
  5. `rng.shuffle(plan)` (the legacy generators' `rng.shuffle(plan_targets(...))` step).

A block may also be a **label** (`plan_targets.by_label`, design doc D5): the same weight shape, but the target names an
answer — `"final_band:3"`, or a conjunction `"final_band:3 & plagiarism_flag:true"` — and the engine, not the allocator,
has to find a record whose rules give it.

`plan_targets.floor` (design doc D5) is not read here: it is the threshold the *exit gate* judges the produced records
against (`engine.quality_gate`), because a quota can only ask, while whether the rules can answer is a fact about the
generated file. Keys the allocator does not know (`by_issue_type`, `by_missing_element` — two released specs) are left
alone rather than refused: PR4 rewrites those specs onto `by_label`, and refusing them today would red the matrix for a
shape that is the spec's history, not a contradiction.

Algorithm (round_robin, `plan_targets.custom == "round_robin"`):

  1. For each record index `i`, the bucket is `i % period`. Each slot declares `[lo, hi]` (closed
     interval) and a target template.
  2. If the target is a literal string (`"undirected"`, `"emergency"`, `"conflict"`), emit it.
  3. If the target is `"department_index"`, emit
     `department_index_order[(i // stride) % len(department_index_order)]` — the legacy
     `gen_diagnosis.plan_targets` / `gen_triage.plan_targets` shape (`(i // 2) % len(departments)`).
  4. `rng.shuffle(plan)` after the bucket assignment matches the legacy sequencing (the two legacy
     generators both shuffle after assembly).
"""
from __future__ import annotations
from random import Random
from typing import Any, Dict, List, NamedTuple, Optional, Tuple, Union

# A state_target is one of:
#   None                        - normal record (no steers for the sampler)
#   (tier: int, category: str)  - share-based critical record (BoundarySampler + tier_windows)
#   str                         - round-robin department/direction (Phase B Task 4+ to wire through)
#   LabelTarget                 - the answer a record must end up carrying (design doc D5's `by_label`)
StateTarget = Optional[Union[Tuple[int, str], str, "LabelTarget"]]


class PlanError(ValueError):
    """`plan_targets` cannot be read as written (a quota fighting a weight, a label target that names nothing)."""


class LabelTarget(NamedTuple):
    """A plan target that names answers rather than fields: `{pairs}` = (`question id`, `label key`) that must all hold.

    Nothing in the sampler can realise it — which field has to cross, or which candidate has to be drawn, is spec
    semantics the engine cannot infer. The engine therefore draws records until *this spec's own rules* give every pair
    (a bounded retry, `engine.LABEL_ATTEMPTS`), and a target that keeps missing is reported by the exit gate as the gap
    it is instead of quietly shipping the fallback label.

    A conjunction rather than one answer is what makes gate G2 reachable on a multi-question spec. A target that names
    only `final_band` leaves every other question to the natural distribution, and the plan cannot hold what it never
    asked for: `measured` at PR3 over 200 seeds of `edu-essay-scoring` at n = 30, `plagiarism_flag:true` under
    band-only targets spreads sd 6.75pp (the binomial prediction for its 17% rate is 6.87pp), from 0% to 33.3% of the
    file, and 98 of those 200 runs sit more than G2's 5pp away from the same plan's n = 3,000 read (median 3.57pp, worst
    16.90pp). Under the shipped joint cells the same question is at 23.3% in every one of the 200 runs (sd 0.00pp, 1.67pp
    from n = 3,000 — the quota's rounding at n = 30, the one deviation a plan cannot round away). A plan pins the share
    of a question only by addressing that question.
    """

    pairs: Tuple[Tuple[str, str], ...]

    def __str__(self) -> str:
        return " & ".join(f"{qid}:{key}" for qid, key in self.pairs)

    @classmethod
    def parse(cls, name: str) -> "LabelTarget":
        """`"final_band:3 & plagiarism_flag:true"` -> two pairs; a lone `"final_band:3"` is the one-pair form.

        The *first* colon of each part splits, so a key may keep its own. Empty parts (`"a:1 & "`) are not a shape a
        spec should get away with writing, since the trailing part would silently ask for nothing.
        """
        parts = [part.strip() for part in str(name).split("&")]
        if not all(parts):
            raise PlanError(f"plan_targets.by_label names {name!r}; the form is \"<question id>:<label key>\", parts "
                            f"joined by \" & \"")
        pairs = []
        for part in parts:
            qid, sep, key = part.partition(":")
            if not sep or not qid or not key:
                raise PlanError(f"plan_targets.by_label names {name!r}; every part is \"<question id>:<label key>\"")
            pairs.append((qid, key))
        return cls(tuple(pairs))


def _largest_remainder(weights: List[float], total: int) -> List[int]:
    """Split `total` over `weights` as whole numbers that add up to `total` exactly.

    Each part gets `floor`, then the leftover units go to the largest fractional remainders, declaration order breaking a
    tie. Truncation alone would leave a block of 5 equal weights and a pool of 27 with only 25 planned records (two
    silently dropped), and rounding alone would overshoot; both drift the proportions as `n` changes, which is what gate
    G2 measures. Non-negative weights only; an all-zero weight list falls back to equal shares.
    """
    if not weights:
        return []
    if total <= 0:
        return [0] * len(weights)
    shares = [max(0.0, float(weight)) for weight in weights]
    total_w = sum(shares)
    if total_w <= 0:
        shares = [1.0] * len(weights)
        total_w = float(len(weights))
    exact = [total * share / total_w for share in shares]
    counts = [int(value) for value in exact]
    order = sorted(range(len(counts)), key=lambda index: (-(exact[index] - counts[index]), index))
    for index in order[:total - sum(counts)]:
        counts[index] += 1
    return counts


class PlanAllocator:
    """Turn a `plan_targets` spec into a 1-1 list of `state_target` values, one per record."""

    # Sentinel: regression tests check this before they attempt the byte-for-byte diff. Setting it
    # False with `[None] * n` is the only signal the engine has been "is the allocator a stub?" —
    # but that equality is too tight (a real allocator with an empty plan_targets config legitimately
    # returns all-Normal), so we expose the flag explicitly.
    _IMPLEMENTED = True

    def __init__(self, plan_targets: dict):
        self.plan_targets = plan_targets or {}

    # --- public API --------------------------------------------------------

    def allocate(self, n: int, rng: Random) -> List[StateTarget]:
        """Produce exactly `n` state targets, in record order. Shuffles the plan before returning.

        Three branches: round-robin (`custom == "round_robin"`), weights over a pool (every other configured shape —
        `plan_targets.by_category`, `plan_targets.by_label`, or the spec-§3.4 `by_category.critical` block), and the
        unconfigured one, where every record is unsteered. Refused before it samples when the shape contradicts itself
        (`PlanError`), because a quota that fights a weight is a spec author who means two different things.
        """
        if n <= 0:
            return []
        # Branch 1: round-robin.
        if self.plan_targets.get("custom") == "round_robin":
            return self._allocate_round_robin(n, rng)
        errors = self.static_errors()
        if errors:
            raise PlanError("plan_targets is not readable:\n  " + "\n  ".join(errors))
        # Branch 2: share + by_category / by_category weights (design doc D5).
        entries = self._entries()
        if not entries:
            return [None] * n
        pool = self._pool(n)
        counts = _largest_remainder([entry["weight"] for entry in entries], pool)
        plan: List[StateTarget] = []
        for entry, count in zip(entries, counts):
            if count <= 0:
                continue
            if "label" in entry:
                plan.extend([entry["label"]] * count)
            else:
                plan.extend(self._build_category_plan_from_split(entry["category"], count, entry["tier_split"]))
        # Absolute `quota` blocks are outside the pool on purpose — the author asked for that many records whatever `n`
        # says — so they come after the weighted ones and the whole plan is then fit to `n`.
        for block in self._absolute_blocks():
            plan.extend(self._build_category_plan_from_split(block["category"], block["count"], block["tier_split"]))
        # Pad with Normal targets so the length matches `n`. Some legacy specs may undershoot quota
        # intentionally (e.g. `share: 0.35` on 787 records = 275 — fewer than the total).
        if len(plan) < n:
            plan.extend([None] * (n - len(plan)))
        elif len(plan) > n:
            # Round down to the request rather than truncate mid-tier: trim from the end of the plan.
            plan = plan[:n]
        rng.shuffle(plan)
        return plan

    # --- the declared shape (D5) -------------------------------------------

    #: what one `by_category` / `by_label` block may declare.
    BLOCK_KEYS = ("share", "quota", "weight", "tier_split")

    def static_errors(self) -> List[str]:
        """Every way this `plan_targets` contradicts itself, as messages. [] means it can be allocated.

        Called before the first record is sampled (the engine refuses a spec it cannot plan from), and the same list is
        what `rules.static_problems` reports through the console's `generator/validate` route.
        """
        problems: List[str] = []
        for key, block in self._declared_blocks():
            if not isinstance(block, dict):
                problems.append(f"{key} must be an object of share/quota/weight/tier_split")
                continue
            unknown = sorted(set(block) - set(self.BLOCK_KEYS))
            if unknown:
                problems.append(f"{key} declares {unknown}; known: {', '.join(self.BLOCK_KEYS)}")
            if "weight" in block and "quota" in block:
                problems.append(f"{key} declares both `weight` (relative to the pool) and `quota` (an absolute count); "
                                f"pick one")
            for name in ("share", "quota", "weight"):
                if name in block:
                    try:
                        float(block[name])
                    except (TypeError, ValueError):
                        problems.append(f"{key}.{name} = {block[name]!r} is not a number")
        for key in ("normal_share",):
            if key in self.plan_targets:
                try:
                    share = float(self.plan_targets[key])
                except (TypeError, ValueError):
                    problems.append(f"plan_targets.{key} = {self.plan_targets[key]!r} is not a number")
                else:
                    if not 0.0 <= share <= 1.0:
                        problems.append(f"plan_targets.{key} = {share} is not a share of n (0..1)")
        declared_shares = {round(float(block["share"]), 9): name
                           for name, block in self._declared_blocks()
                           if isinstance(block, dict) and isinstance(block.get("share"), (int, float))}
        if len(declared_shares) > 1:
            problems.append("every block of plan_targets names the pool it is drawn from, but they disagree: "
                            + ", ".join(f"{name}: {share}" for share, name in sorted(declared_shares.items())))
        for target in (self.plan_targets.get("by_label") or {}):
            try:
                parsed = LabelTarget.parse(target)
            except PlanError as error:
                problems.append(str(error))
                continue
            repeated = sorted({qid for qid, _ in parsed.pairs
                               if [q for q, _ in parsed.pairs].count(qid) > 1})
            if repeated:
                problems.append(f"plan_targets.by_label.{target} asks two answers of {repeated}; a record answers each "
                                f"question once — name one key per question")
        return problems

    def _declared_blocks(self) -> List[Tuple[str, Any]]:
        """(name, block) for every block the spec declares, categories first, then labels."""
        by_category = self.plan_targets.get("by_category") or {}
        out = [(f"plan_targets.by_category.{category}", block) for category, block in by_category.items()]
        by_label = self.plan_targets.get("by_label") or {}
        out += [(f"plan_targets.by_label.{name}", block) for name, block in by_label.items()]
        return out

    def _entries(self) -> List[dict]:
        """One entry per declared block: what it wants, and how much of the pool it should get.

        Two shapes answer for the same thing today. The released specs write a `share` on every block (the CLI's one
        global fraction, copied into each) next to a `quota`; `weight` is the new name for the same relative claim, and
        a block that declares only `weight` is read as if the pool were all of `n`. The legacy `quota` therefore *is*
        the weight — which is what makes `critical-value`'s five blocks of `{share: 0.35, quota: 55}` still come out at
        55 records apiece on its released 787 (0.35 x 787 = 275.45 over five equal weights) while a 60-record run now
        asks it for 4 each instead of steering all 60 (design doc D5, F5).
        """
        entries: List[dict] = []
        for category, block in (self.plan_targets.get("by_category") or {}).items():
            if not isinstance(block, dict):
                continue
            weight = block.get("weight")
            if weight is None:
                weight = block.get("quota")
            entries.append({"category": category,
                            "weight": 1.0 if weight is None else max(0.0, float(weight)),
                            "tier_split": block.get("tier_split") or [[0, 1.0]]})
        for name, block in (self.plan_targets.get("by_label") or {}).items():
            block = block or {}
            weight = block.get("weight", 1.0)
            entries.append({"label": LabelTarget.parse(name), "weight": max(0.0, float(weight))})
        return entries

    def _absolute_blocks(self) -> List[dict]:
        """Blocks that asked for an exact number of records (`quota` with no `share` and no `weight`)."""
        out = []
        for category, block in (self.plan_targets.get("by_category") or {}).items():
            if not isinstance(block, dict) or "quota" not in block:
                continue
            if "share" in block or "weight" in block:
                continue
            out.append({"category": category, "count": max(0, int(block["quota"])),
                        "tier_split": block.get("tier_split") or [[0, 1.0]]})
        return out

    def _pool(self, n: int) -> int:
        """How many of the `n` records the plan drives; the rest stay unsteered.

        `normal_share` says it directly, a top-level `share.critical` (spec §3.4) or the `share` the legacy blocks
        repeat says it as the steered fraction. With none of them every record is up for allocation.
        """
        declared = self.plan_targets.get("normal_share")
        if declared is not None:
            return n - int(round(n * float(declared)))
        top = self.plan_targets.get("share")
        if isinstance(top, dict) and top.get("critical") is not None:
            return int(round(n * float(top["critical"])))
        shares = [float(block["share"]) for _, block in self._declared_blocks()
                  if isinstance(block, dict) and isinstance(block.get("share"), (int, float))]
        if shares:
            return int(round(n * shares[0]))
        return n

    # --- share + by_category ---------------------------------------------

    def _build_category_plan_from_split(
        self,
        category: str,
        count: int,
        tier_split: List,
    ) -> List[Tuple[int, str]]:
        """Distribute `count` records across the given `tier_split` entries.

        Largest-remainder rounding again, so a block of 11 split over two equal tiers gives 6/5 rather than the 5/6 the
        old "last tier absorbs the residual" rule gave: the residual goes to whoever wanted it most, and the tiers keep
        their proportions at every `n` (gate G2). The returned list is in `tier_split` order — the legacy generators
        iterate categories in `by_category` order, so all renal slots land before all cbc slots, and the engine's
        `rng.shuffle` is what spreads them across the file.
        """
        if count <= 0:
            return []
        weights = self._coerce_tier_split(tier_split) or [{"tier": 0, "weight": 1.0}]
        out: List[Tuple[int, str]] = []
        for entry, tier_count in zip(weights, _largest_remainder([w["weight"] for w in weights], count)):
            out.extend([(entry["tier"], category)] * tier_count)
        return out

    @staticmethod
    def _coerce_tier_split(tier_split: List) -> List[dict]:
        """Accept `[[tier, weight], ...]` OR `[{"tier": int, "weight": float}, ...]`. Return the latter.

        The spec §3.4 example uses pairs (legacy `boundary_value` notation), the critical-value
        fixture uses objects; both translate to `{"tier": int, "weight": float}` here so the rest
        of the allocator can stay agnostic.
        """
        out: List[dict] = []
        for entry in tier_split:
            if isinstance(entry, dict):
                if "tier" not in entry:
                    continue
                out.append({"tier": int(entry["tier"]), "weight": float(entry.get("weight", 1.0))})
            elif isinstance(entry, (list, tuple)) and len(entry) == 2:
                out.append({"tier": int(entry[0]), "weight": float(entry[1])})
        return out

    # --- round-robin -------------------------------------------------------

    def _allocate_round_robin(self, n: int, rng: Random) -> List[StateTarget]:
        """Build the round-robin schedule from `period` + `slots` + `department_index_order`.

        For each record index `i`:

          - Compute `bucket = i % period`.
          - Walk `slots` (declared in spec order); the first whose `[lo, hi]` closed interval contains
            `bucket` wins.
          - If `slots[entry].target` is a literal string (`"undirected"`, `"emergency"`,
            `"conflict"`), emit it.
          - If `target` is `"department_index"`, emit
            `department_index_order[(i // stride) % len(department_index_order)]` —
            the legacy `gen_diagnosis.plan_targets` formula is `(i // 2) % len(directions)` with
            `stride=2`; `gen_triage.plan_targets` is identical.

        Returns a list of plain strings (one per record). The engine+BoundarySampler pass that
        consumes these is upgraded in Phase B Task 4 (sampler-aware categories); for now the engine
        treats any unrecognised `state_target` form as a fallback to `sampler.sample(None, rng)`.
        """
        rb = self.plan_targets.get("round_robin") or {}
        period = int(rb.get("period", 1))
        slots = rb.get("slots") or []
        order = rb.get("department_index_order") or []
        # Default stride for the legacy algorithms is 2 (`(i // 2) % len(...)`).
        default_stride = 2
        plan: List[StateTarget] = []
        for i in range(n):
            bucket = i % period if period > 0 else 0
            target = self._resolve_slot(slots, bucket, default_target="undirected")
            if isinstance(target, str) and target.startswith("department_index"):
                plan.append(self._resolve_department_index(target, i, order, default_stride))
            else:
                plan.append(target)
        rng.shuffle(plan)
        return plan

    @staticmethod
    def _resolve_slot(slots: List[dict], bucket: int, default_target: str) -> Any:
        """Find the slot whose `[lo, hi]` interval contains `bucket` and return its target.

        Tolerant of missing `slot` (treated as `[0, period-1]` style? no — that's wrong; the legacy
        generators use explicit `[lo, hi]` intervals, so we just default to the configured
        `default_target` if no slot matches).
        """
        for slot in slots:
            try:
                lo, hi = slot["slot"]
            except (KeyError, TypeError, ValueError):
                continue
            if lo <= bucket <= hi:
                return slot.get("target", default_target)
        return default_target

    @staticmethod
    def _resolve_department_index(target: str, i: int, order: List[str], default_stride: int) -> str:
        """Resolve a `"department_index"` target via `(i // stride) % len(order)`.

        The `target` may optionally carry the stride (e.g. `"department_index:2"`); otherwise
        `default_stride` (2, matching the legacy generators) is used.
        """
        if not order:
            return "undirected"
        stride = default_stride
        if ":" in target:
            try:
                stride = int(target.split(":", 1)[1])
            except ValueError:
                stride = default_stride
        if stride <= 0:
            stride = 1
        return order[(i // stride) % len(order)]
