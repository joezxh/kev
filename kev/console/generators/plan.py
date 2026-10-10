"""PlanAllocator — turns spec_json.generator.plan_targets into a list of `state_target` values.

Spec §3.4. The engine consumes `state_target` per record; the form depends on the spec:

1. Share + by-category quota + tier_split (numeric critical-value style). Each `state_target` is a
   `(tier, category)` tuple the BoundarySampler resolves through `tier_windows`. Normal records are `None`.
2. Custom round-robin (`plan_targets.custom == "round_robin"`, spec §3.4 last paragraph). Each
   `state_target` is a string (department name, `"emergency"`, `"undirected"`, etc.) — the round-robin
   schedule built from `period` and `slots`. The BoundarySampler/RuleEvaluator chain that follows needs
   the sampler to handle category strings; round-robin parity is gated on Phase B Task 4 (sampler
   upgrade) + Task 8 (rule operators) — this module just produces the schedule.

Algorithm (share + by_category quota + tier_split):

  1. For each category in `by_category.<cat>.quota`, pick `floor(n * share)` records.
  2. Within a category, split its `quota` records across the `{tier: weight}` entries in `tier_split`,
     using the exact integer weights so totals line up. The last bucket absorbs the rounding residual.
  3. Append `None` records for the remainder so the plan is exactly `n` items long.
  4. `rng.shuffle(plan)` (the legacy generators' `rng.shuffle(plan_targets(...))` step).

Algorithm (round_robin):

  1. For each record index `i`, the bucket is `i % period`. Each slot declares `[lo, hi]` (closed
     interval) and a target template.
  2. If the target is a literal string (`"undirected"`, `"emergency"`, `"conflict"`), emit it.
  3. If the target is `"department_index"`, emit
     `department_index_order[(i // stride) % len(department_index_order)]` — the legacy
     `gen_diagnosis.plan_targets` / `gen_triage.plan_targets` shape (`(i // 2) % len(departments)`).
  4. `rng.shuffle(plan)` after the bucket assignment matches the legacy sequencing (the two legacy
     generators both shuffle after assembly).

The class exposes `_IMPLEMENTED = True` so the regression tests can detect the real allocator without
depending on its numerical output (a future refactor that changes the share shape is then signalled by
the class attribute, not by a `== [None] * n` equality check).
"""
from __future__ import annotations
from random import Random
from typing import Any, Dict, List, Optional, Tuple, Union

# A state_target is one of:
#   None                        - normal record (no steers for the sampler)
#   (tier: int, category: str)  - share-based critical record (BoundarySampler + tier_windows)
#   str                         - round-robin department/direction (Phase B Task 4+ to wire through)
StateTarget = Optional[Union[Tuple[int, str], str]]


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

        Three branches: round-robin (`custom == "round_robin"`), share + by_category (every other
        configured shape, which the legacy generators express as `plan_targets.by_category.<cat>` with
        `share` + `quota` + `tier_split`), and the spec-§3.4 canonical form with a top-level `share`.
        An empty `plan_targets` returns `[None] * n`.
        """
        if n <= 0:
            return []
        # Branch 1: round-robin.
        if self.plan_targets.get("custom") == "round_robin":
            return self._allocate_round_robin(n, rng)
        # Branch 2: legacy by_category share form (critical-value's `by_category.<cat>.share` shape,
        # plus a normalised `by_category.critical.{share, quota, tier_split}` form per spec §3.4).
        by_category = self.plan_targets.get("by_category")
        if isinstance(by_category, dict) and by_category:
            return self._allocate_by_category(n, rng)
        # Default: the spec has no plan_targets; every record is unsteered.
        return [None] * n

    # --- share + by_category ---------------------------------------------

    def _allocate_by_category(self, n: int, rng: Random) -> List[StateTarget]:
        """Implement the share + quota + tier_split scheme.

        Accepts two shapes:

          a) Spec §3.4 example:
               {"share": {"critical": 0.35, "normal": 0.65},
                "by_category": {"critical": {"quota": {...}, "tier_split": {...}}}}
             — top-level `share.critical` is the fraction of `n` reserved for the critical bucket;
             `quota` is then a per-category weight inside that bucket.
          b) Legacy / critical-value fixture:
               {"by_category": {"renal": {"share": 0.35, "quota": 55, "tier_split": [...]}, ...}}
             — one block per category, each with its own `quota` (absolute record count) and `share`.
        """
        by_category = self.plan_targets.get("by_category") or {}
        # Spec §3.4 form: the `critical` block under `by_category` carries per-category weights
        # inside a top-level `share.critical` fraction of `n`. Compute the integer critical count
        # and let the per-category quota distribute it.
        if "critical" in by_category and isinstance(by_category["critical"], dict):
            top_share = self.plan_targets.get("share") or {}
            crit_frac = top_share.get("critical")
            if crit_frac is not None:
                crit_count = max(0, int(round(n * float(crit_frac))))
            else:
                # No top-level share → treat the spec-§3.4 quota as direct fractions of `n`.
                crit_count = n
            blocks = self._normalise_spec34(by_category["critical"], crit_count)
        else:
            blocks = self._normalise_legacy(by_category)
        if not blocks:
            return [None] * n
        # Flatten in declared order (category first, then tier within category). The legacy generators
        # build the plan category-by-category, so all renal slots come before all cbc slots.
        plan: List[StateTarget] = []
        for block in blocks:
            plan.extend(block["plan"])
        # Pad with Normal targets so the length matches `n`. Some legacy specs may undershoot quota
        # intentionally (e.g. `share: 0.35` on 787 records = 275 — fewer than the total).
        if len(plan) < n:
            plan.extend([None] * (n - len(plan)))
        elif len(plan) > n:
            # Round down to the request rather than truncate mid-tier: trim from the end of the plan.
            plan = plan[:n]
        rng.shuffle(plan)
        return plan

    def _normalise_spec34(self, crit: dict, crit_count: int) -> List[dict]:
        """Translate the spec-§3.4 `by_category.critical` block into per-category plan lists.

        `quota` is a per-category weight (sums to 1.0). The integer `crit_count` is the absolute
        total for the critical bucket (already computed from `n * share.critical`).
        """
        quota = crit.get("quota")
        if not isinstance(quota, dict) or not quota:
            return []
        tier_split = crit.get("tier_split") or {}
        total_w = sum(float(w) for w in quota.values()) or 1.0
        blocks: List[dict] = []
        cumulative = 0
        items = list(quota.items())
        for idx, (category, weight) in enumerate(items):
            split = tier_split.get(category)
            if not split:
                split = [[0, 1.0]]
            if idx == len(items) - 1:
                cat_count = max(0, crit_count - cumulative)
            else:
                cat_count = int((float(weight) / total_w) * crit_count)
                cumulative += cat_count
            block_plan = self._build_category_plan_from_split(category, cat_count, split)
            if block_plan:
                blocks.append({"category": category, "plan": block_plan})
        return blocks

    def _normalise_legacy(self, by_category: dict) -> List[dict]:
        """Translate the legacy per-category `by_category.<cat>` form into plan blocks.

        Each top-level key is a category with its own `share` / `quota` / `tier_split`. The `quota`
        is an absolute record count.
        """
        blocks: List[dict] = []
        for category, block in by_category.items():
            if not isinstance(block, dict):
                continue
            split = block.get("tier_split")
            if split is None:
                split = [[0, 1.0]]
            block_plan = self._build_category_plan(
                category=category,
                share=block.get("share"),
                quota=block.get("quota"),
                tier_split=split,
            )
            if block_plan:
                blocks.append({"category": category, "plan": block_plan})
        return blocks

    def _build_category_plan(
        self,
        category: str,
        share: Optional[float],
        quota: Optional[int],
        tier_split: List,
    ) -> List[Tuple[int, str]]:
        """Build the per-category `[(tier, category), ...]` list from a share / quota / tier_split block.

        `quota` is the absolute record count for this category (an int). `share` is a float that
        acts as a `quota` of `int(round(share × 1000))` when `quota` is None — only kept for callers
        that pass weight-as-share (e.g. a future direct-share form); the canonical spec §3.4 path
        uses `_build_category_plan_from_split` with a pre-computed absolute count.
        """
        if quota is not None:
            count = max(0, int(quota))
        elif share is not None:
            count = max(0, int(round(share * 1000)))
        else:
            return []
        return self._build_category_plan_from_split(category, count, tier_split)

    def _build_category_plan_from_split(
        self,
        category: str,
        count: int,
        tier_split: List,
    ) -> List[Tuple[int, str]]:
        """Distribute `count` records across the given `tier_split` entries.

        Each tier gets `floor(weight × count)`, the last tier absorbs the residual so the totals
        always sum to `count`. The returned list is in tier_split order — the legacy generators
        iterate categories in `by_category` order, so all renal slots land before all cbc slots.
        """
        if count <= 0:
            return []
        weights = self._coerce_tier_split(tier_split)
        if not weights:
            weights = [{"tier": 0, "weight": 1.0}]
        total_w = sum(w["weight"] for w in weights) or 1.0
        cumulative = 0
        tier_counts: List[Tuple[int, int]] = []
        for idx, w in enumerate(weights):
            if idx == len(weights) - 1:
                tier_counts.append((w["tier"], count - cumulative))
            else:
                tc = int((w["weight"] / total_w) * count)
                tier_counts.append((w["tier"], tc))
                cumulative += tc
        out: List[Tuple[int, str]] = []
        for tier, tc in tier_counts:
            out.extend([(tier, category)] * tc)
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
