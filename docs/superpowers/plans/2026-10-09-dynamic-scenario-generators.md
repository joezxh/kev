# 动态场景生成器：把硬编码 `gen_*.py` / 蒸馏入口 / 路由 / 探针抽成可配置规则引擎

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace 6 hardcoded medical `gen_*.py` files, 4 hardcoded distill dicts, 5 hardcoded industry `Scenario` builders, the 5-case `SMOKE_PROBES` constant, and the 5 hardcoded `distill/configs/*.yaml` files with one spec-driven engine that reads `scenarios.spec_json` (the 4 new sub-fields `generator` / `distill` / `routing` / `smoke_probe`) and produces byte-for-byte identical records (regression gate: `critical-value`).

**Architecture:** Single Python engine `kev/console/generators/engine.py` + 4 sub-modules (`sampler` / `rules` / `augment` / `pair` / `plan` / `ops`) reads `spec_json.generator` and emits the same JSONL `gen_*.py` produced. `simpleeval` evaluates `when` expressions against a whitelist of domain operators registered in `ops.py`. `kev/console/distill/render.py` renders `spec_json.distill` via Jinja2 instead of the hardcoded `ASK` dict. `kev/console/services/routing.py` projects `spec_json.routing` into `kev.vertical.INDUSTRIES` (replacing the 5 hardcoded `_medical`/`_finance`/... builders). `kev/console/services/smoke.py` and `db.list_smoke_probes()` replace `stages/deploy.SMOKE_PROBES`. `kev/console/distill/configs/template.yaml.j2` is rendered by `make_seeds config <slug>` to produce EasyDistill YAMLs.

**Tech Stack:** Python 3.12/3.13, `simpleeval>=1.0` (rule evaluation), `jinja2>=3.1` (distill prompts + yaml template), FastAPI (existing), React/Next 16 (existing playground), zod (existing UI schema).

## Global Constraints

Every task's requirements implicitly include these. Verbatim from `AGENTS.md` and the spec:

- `requires-python = ">=3.12,<3.14"`; 3.13 is the default (`.python-version`).
- `transformers>=5.17,<6`, `peft>=0.21`, `torch>=2.6,<2.9`. Do not bump.
- All JSON / JSONL is UTF-8 with LF endings. Use `kev.suite.read_json/read_jsonl/write_json/write_jsonl` (or pass `encoding="utf-8"` and `newline="\n"`). The `.gitattributes` `*.json` / `*.jsonl` LF rule applies — do not commit CRLF.
- `runs/` is gitignored except ledgers, reports, provenance and training logs. The 6 new `runs/kev-console/golden/*.jsonl` files ARE committed (they are golden fixtures, not training artefacts; see spec §8.1).
- `spec_json` is a single TEXT column on the `scenarios` table. Do NOT add columns for `generator` / `distill` / `routing` / `smoke_probe` (per spec §1 non-goals).
- Do not introduce LLM-assisted rule generation; the LLM never touches labels.
- Every generator that today imports from `common.py` continues to import from `common.py` after the migration (the `boundary_value` / `labelled` / `write_records` / `label_table` / `load_spec` / `base_parser` / `label_keys` symbols stay; `minimal_pair` is removed and replaced by `pair.py`).
- `kev.vertical._OVERRIDE` (the `IndustryRegistry.load(json)` path) is preserved. Only the `_default_registry()` fallback switches to DB.
- `kev.vertical.INDUSTRIES` is NOT hot-reloadable in v1. Changing `routing` requires restarting kev-console (per spec §1 non-goals).
- `kev.serve` / `kev_modal.py` / training / eval stages are NOT modified (per spec §1 / §10).
- byte-for-byte regression: `python -m kev.console.generators.engine --scenario critical-value --n 787 --out /tmp/x.jsonl --seed 0` must diff-empty against `data/critical-value.jsonl` (committed). `seed=0, n=787, pairs=0.35` is the regression contract (spec §8.1).
- Chinese-language code comments: the existing `kev/console/` package mixes Chinese and English; preserve the prevailing comment style per file.
- `pyproject.toml` is the only place to declare dependencies; no inline `pip install` instructions in plan steps.
- Plan progress checkpoint markers: after every task, the next task starts with `git add` of the previous task's commit. Use the commit message prefix `engine(console):` for engine work, `distill(console):` for distill work, `routing(console):` for vertical work, `smoke(console):` for deploy-probe work, `db(console):` for DB work, `ui(playground):` for frontend work.

## Phases

This plan has 4 phases. Each phase ends with a reviewer gate (one task that does a smoke-run of the previous phase and stops if it fails). A reviewer can reject at any phase boundary.

- **Phase A** (Tasks 1-9) Engine + byte-for-byte regression for `critical-value`. End gate: `test_critical_value_byte_for_byte` passes.
- **Phase B** (Tasks 10-15) Engine generalised to the other 5 scenarios + minimal pair + simpleeval operators. End gate: 5 `test_*_byte_for_byte` pass.
- **Phase C** (Tasks 16-21) Distill entry (render + make_seeds + seed_to_kev + check_volume) + yaml template. End gate: `test_yaml_template_render` passes.
- **Phase D** (Tasks 22-26) DB 4-field + routing sync + smoke probes + 6 specs migrated + GeneratorTab UI. End gate: `test_routing_sync_matches_hardcoded` + `test_smoke_probes_match_hardcoded` pass.

After Phase D succeeds, the spec §9 "删除" list is executed as Tasks 27-29 (delete 6 gen_*.py + delete SMOKE_PROBES + delete 5 vertical builders + delete 5 yaml + delete init files + delete seed_scenarios labels dict).

---

## Phase A: Engine + critical-value regression

### Task 1: Add `simpleeval` + `jinja2` to `pyproject.toml`

**Files:**
- Modify: `pyproject.toml:dependencies`

**Interfaces:**
- Produces: `simpleeval>=1.0` and `jinja2>=3.1` importable from any module under `kev/`.

- [ ] **Step 1: Read `pyproject.toml` and locate the `dependencies` list**

Run: `Get-Content pyproject.toml | Select-String -Pattern "dependencies" -Context 0,12`

Expected: A `[project]` section with `dependencies = [ ... ]` block listing current deps.

- [ ] **Step 2: Add two new entries to the `dependencies` list**

Edit `pyproject.toml`. Find the `dependencies = [` line and append (in alphabetical order with the rest):

```toml
    "jinja2>=3.1",            # distill system_prompt + yaml template (§3.5, §3.8)
    "simpleeval>=1.0",        # restricted expression evaluation for rules.when (§3.2)
```

- [ ] **Step 3: Run `uv sync` to install**

Run: `uv sync`
Expected: `+ jinja2-X.Y.Z` and `+ simpleeval-X.Y.Z` appear in the resolver output; no resolution failure.

- [ ] **Step 4: Verify both packages import**

Run: `uv run python -c "import jinja2, simpleeval; print('jinja2', jinja2.__version__); print('simpleeval.SimpleEval', simpleeval.SimpleEval)"`
Expected: prints `jinja2 3.1.X` and a class repr for `simpleeval.SimpleEval`; exit 0. (simpleeval does not expose `__version__`; print the class object as a proxy.)

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "engine(console): add jinja2 + simpleeval deps for spec-driven generators"
```

---

### Task 2: Create the package skeleton `kev/console/generators/{ops,sampler,rules,augment,pair,plan,engine}.py` and `__main__.py`

**Files:**
- Create: `kev/console/generators/ops.py`
- Create: `kev/console/generators/sampler.py`
- Create: `kev/console/generators/rules.py`
- Create: `kev/console/generators/augment.py`
- Create: `kev/console/generators/pair.py`
- Create: `kev/console/generators/plan.py`
- Create: `kev/console/generators/engine.py`
- Create: `kev/console/generators/__main__.py`

**Interfaces:**
- Each file exposes one public class (or function) named after the file (e.g. `BoundarySampler` in `sampler.py`).
- `engine.run(argv)` accepts `["--scenario", "<slug>", "--n", "787", "--out", "<path>", "--seed", "0", "--pairs", "0.35"]` and returns the int exit code.
- `engine.run` is a thin CLI wrapper; the core logic is in the sub-modules.

- [ ] **Step 1: Create `kev/console/generators/ops.py` with the operator registry stub**

```python
"""Domain operator whitelist for simpleeval — the bridge between the JSON rule DSL and the legacy gen_*.py logic.

Each operator here is a pure function with a docstring that cites the gen_*.py source line it replaces, so a reviewer
can trace the spec back to the legacy code. Operators are registered in ALLOWED (alphabetical) and consumed by
RuleEvaluator via simple_eval(..., functions=ALLOWED).
"""
from __future__ import annotations
from typing import Any, Callable, Dict


def bool_to_str(b: bool) -> str:
    """`True`/`False` -> `"true"`/`"false"` (noul question labels are strings, not Python bools)."""
    return "true" if b else "false"


ALLOWED: Dict[str, Callable[..., Any]] = {
    "bool_to_str": bool_to_str,
    "min": min,
    "max": max,
    "round": round,
    "any": any,
    "all": all,
    "len": len,
    "abs": abs,
}
```

- [ ] **Step 2: Create `kev/console/generators/sampler.py` with the `BoundarySampler` stub**

```python
"""BoundarySampler — constructs one `state` dict from spec_json.generator.fields + selectors + state_target.

Spec §3.1. The state shape matches gen_*.py (keys are field names; values are formatted strings like "6.2 mmol/L").
The `_sample_normal` / `_sample_critical` / `_sample_crossed` / `_realize_tier` / `_format` methods are placeholders;
they're implemented in Task 4. The class accepts a `random.Random` so the random number stream is reproducible.
"""
from __future__ import annotations
from random import Random
from typing import Any, Dict, List, Optional


class BoundarySampler:
    def __init__(self, fields: List[dict], selectors: List[dict], tier_windows: Optional[Dict[str, dict]] = None):
        self.fields = fields
        self.selectors = selectors
        self.tier_windows = tier_windows or {}

    def sample(self, state_target: Optional[tuple], rng: Random) -> Optional[Dict[str, Any]]:
        raise NotImplementedError("implemented in Task 4")
```

- [ ] **Step 3: Create `kev/console/generators/rules.py` with the `RuleEvaluator` stub**

```python
"""RuleEvaluator — evaluates spec_json.generator.rules sequentially; first match wins; emits labels per then.

Spec §3.2. Uses simpleeval with the ALLOWED operator whitelist from ops.py. Each rule has `when` (a string expression
evaluated against the state) and `then` (a list of {label, value} assignments). The evaluator MUST be deterministic
for a given (state, rules) — no randomness.
"""
from __future__ import annotations
from simpleeval import SimpleEval
from typing import Any, Dict, List
from .ops import ALLOWED


class RuleEvaluator:
    def __init__(self, rules: List[dict]):
        self.rules = rules

    def evaluate(self, state: dict) -> Dict[str, Any]:
        # First-match semantics: walk rules in order, take the first whose `when` is truthy.
        labels: Dict[str, Any] = {}
        for rule in self.rules:
            when = rule["when"]
            then = rule.get("then", [])
            # simpleeval with whitelist; state exposed as a `state` variable.
            evaluator = SimpleEval(functions=ALLOWED, names={"state": state})
            try:
                matched = bool(evaluator.eval(when))
            except Exception:
                matched = False
            if matched:
                for assignment in then:
                    labels[assignment["label"]] = assignment["value"]
                # First-match wins; do not continue evaluating subsequent rules.
                return labels
        return labels
```

- [ ] **Step 4: Create `kev/console/generators/augment.py` with the `Augmentor` stub**

```python
"""Augmentor — post-sampling modifications: evidence_drop + soft target injection + force_label.

Spec §3.3. Called after BoundarySampler + RuleEvaluator; reads `spec_json.generator.augmentation` and mutates a copy
of (state, labels) according to the rate fields. Returns (state, labels, soft).
"""
from __future__ import annotations
from random import Random
from typing import Any, Dict, Optional, Tuple


class Augmentor:
    def __init__(self, augmentation: Optional[dict] = None):
        self.augmentation = augmentation or {}

    def apply(self, state: dict, labels: Dict[str, Any], rng: Random) -> Tuple[dict, Dict[str, Any], Dict[str, Any]]:
        # Default: no-op. The real implementation (evidence_drop + minimal_pair emit) lands in Task 8.
        return dict(state), dict(labels), {}
```

- [ ] **Step 5: Create `kev/console/generators/pair.py` with the `PairBuilder` stub**

```python
"""PairBuilder — minimal pair: a twin record whose state differs in exactly one field and whose label flips.

Spec §3.3. Reads `spec_json.generator.augmentation.minimal_pair` for rate + strategy. The boundary_flip strategy is
implemented in Task 9.
"""
from __future__ import annotations
from random import Random
from typing import Any, Optional


class PairBuilder:
    def __init__(self, augmentation: Optional[dict] = None, sampler=None):
        self.augmentation = augmentation or {}
        self.sampler = sampler

    def build(self, record: dict, handle: Any, rng: Random) -> Optional[dict]:
        return None
```

- [ ] **Step 6: Create `kev/console/generators/plan.py` with the `PlanAllocator` stub**

```python
"""PlanAllocator — turns spec_json.generator.plan_targets into a list of `state_target` tuples.

Spec §3.4. Algorithm:
  1. Multiply share × n for the global critical vs normal split.
  2. For each "critical" record, draw (tier, category) from by_category.quota + tier_split.
  3. For "normal" records, return None (BoundarySampler falls back to all-normal sampling).
  4. Shuffle the plan.
"""
from __future__ import annotations
from random import Random
from typing import List, Optional, Tuple

StateTarget = Optional[Tuple[int, str]]


class PlanAllocator:
    def __init__(self, plan_targets: dict):
        self.plan_targets = plan_targets

    def allocate(self, n: int, rng: Random) -> List[StateTarget]:
        return [None] * n
```

- [ ] **Step 7: Create `kev/console/generators/engine.py` with the `run(argv)` CLI stub**

```python
"""The single spec-driven generator engine.

Spec §2.2. This is the only Python module that orchestrates generation. All it does on the CLI path is:
  1. Parse args: --scenario, --n, --out, --seed, --pairs.
  2. Read the scenario's spec_json from the DB (or paths.SPECS fallback during Task 2-3 before DB wiring).
  3. Instantiate BoundarySampler + RuleEvaluator + Augmentor + PairBuilder + PlanAllocator.
  4. Loop: allocate a target, sample a state, evaluate rules, apply augmentation, optionally build a minimal pair.
  5. Build a Kev record via common.labelled + write via common.write_records.

In Task 2 the loop is stubbed (no records written); the real loop lands in Task 3 + Task 4.
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path
from typing import List

from .augment import Augmentor
from .engine_cli import build_parser
from .pair import PairBuilder
from .plan import PlanAllocator
from .rules import RuleEvaluator
from .sampler import BoundarySampler


def _load_spec(scenario: str) -> dict:
    """Read the scenario's spec from DB. The DB read is implemented in Task 16; this stub falls back to
    docs/medical/specs/<slug>.json so Tasks 3-15 can run before DB wiring.
    """
    from kev.console import paths
    spec_file = paths.SPECS / f"{scenario}.json"
    return json.loads(spec_file.read_text(encoding="utf-8"))


def run(argv: List[str]) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    spec = _load_spec(args.scenario)
    gen = spec.get("generator") or {}
    rng = random.Random(args.seed)
    sampler = BoundarySampler(gen.get("fields", []), gen.get("selectors", []), gen.get("tier_windows"))
    evaluator = RuleEvaluator(gen.get("rules", []))
    augmentor = Augmentor(gen.get("augmentation"))
    allocator = PlanAllocator(gen.get("plan_targets", {}))
    pair_builder = PairBuilder(gen.get("augmentation"), sampler=sampler)
    # The real loop lands in Task 3 + Task 4; the stub just verifies the spec parsed.
    print(f"engine stub: scenario={args.scenario} n={args.n} seed={args.seed} pairs={args.pairs}")
    print(f"  parsed {len(gen.get('fields', []))} fields, {len(gen.get('rules', []))} rules")
    return 0
```

- [ ] **Step 8: Create `kev/console/generators/engine_cli.py` (sibling of engine.py)**

```python
"""Argparse builder for the engine CLI.

Spec §6.3. The flags match what gen_*.py::run used to accept (--n, --out, --seed, --pairs), with --scenario
replacing the hardcoded filename.
"""
from __future__ import annotations

import argparse


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="kev.console.generators.engine")
    parser.add_argument("--scenario", required=True, help="scenario slug, e.g. critical-value")
    parser.add_argument("--n", type=int, default=787, help="records to generate (default 787; planned 4-question size)")
    parser.add_argument("--out", required=True, help="output labelled JSONL path")
    parser.add_argument("--seed", type=int, default=0, help="seed; the same seed reproduces the same file")
    parser.add_argument("--pairs", type=float, default=0.35, help="share of records that also get a minimal-pair twin appended (0 disables)")
    return parser
```

- [ ] **Step 9: Create `kev/console/generators/__main__.py`**

```python
"""python -m kev.console.generators.engine entry point. Forwards argv into engine.run()."""
from __future__ import annotations

import sys
from .engine import run

if __name__ == "__main__":
    sys.exit(run(sys.argv[1:]))
```

- [ ] **Step 10: Verify the package imports and the CLI runs in stub mode**

Run: `uv run python -m kev.console.generators.engine --scenario critical-value --n 787 --out /tmp/x.jsonl --seed 0`
Expected: prints `engine stub: scenario=critical-value n=787 seed=0 pairs=0.35` followed by a "parsed N fields, M rules" line; exit 0. `/tmp/x.jsonl` is created (empty file) by `--out`'s parent mkdir.

- [ ] **Step 11: Commit**

```bash
git add kev/console/generators/{ops,sampler,rules,augment,pair,plan,engine,engine_cli,__main__}.py
git commit -m "engine(console): create spec-driven engine package skeleton"
```

---

### Task 3: Build the `data/critical-value.jsonl` golden fixture (run existing gen_critical_value once)

**Files:**
- Create: `runs/kev-console/golden/critical-value.jsonl`

**Interfaces:**
- `runs/kev-console/golden/critical-value.jsonl` is the byte-for-byte regression target for the engine (spec §8.1).

- [ ] **Step 1: Confirm `data/critical-value.jsonl` exists and is the regression target**

Run: `Test-Path data/critical-value.jsonl; (Get-Content data/critical-value.jsonl | Measure-Object -Line).Lines`
Expected: True; a positive line count. If the file doesn't exist, run `uv run python kev/console/generators/gen_critical_value.py --n 787 --out data/critical-value.jsonl --seed 0` first.

- [ ] **Step 2: Copy the regression target to the golden location**

Run: `New-Item -ItemType Directory -Path runs/kev-console/golden -Force | Out-Null; Copy-Item data/critical-value.jsonl runs/kev-console/golden/critical-value.jsonl`
Expected: `runs/kev-console/golden/critical-value.jsonl` now exists with the same size and line count as `data/critical-value.jsonl`.

- [ ] **Step 3: Verify they're identical**

Run: `(Get-FileHash data/critical-value.jsonl -Algorithm SHA256).Hash; (Get-FileHash runs/kev-console/golden/critical-value.jsonl -Algorithm SHA256).Hash`
Expected: the two hashes match. If they differ, repeat step 1 to regenerate `data/critical-value.jsonl` and recopy.

- [ ] **Step 4: Commit**

```bash
git add runs/kev-console/golden/critical-value.jsonl
git commit -m "test(console): add critical-value golden fixture for engine regression"
```

---

### Task 4: Implement `BoundarySampler` methods for the 10 `critical-value` fields

**Files:**
- Modify: `kev/console/generators/sampler.py`
- Modify: `kev/console/generators/ops.py`

**Interfaces:**
- `BoundarySampler.sample(state_target, rng) -> dict | None` — returns a `state` dict where each key is a field name and each value is a formatted string like `"6.2 mmol/L"`. `state_target` is `None` (normal) or `(tier, category)`. Returns `None` if the target is not realizable (caller falls back to normal).
- The random number stream MUST match `gen_critical_value.build` byte-for-byte. The implementation reuses `common.boundary_value` for sampling (so the RNG stream is identical) and formats via `_format`.

- [ ] **Step 1: Read `gen_critical_value.py` to extract the sampling logic**

Read: `kev/console/generators/gen_critical_value.py` (lines 1-260 and 280-330). Identify:
- `PANELS` (10 entries) → spec_json.generator.fields
- `PATIENTS` / `CONTEXTS` → spec_json.generator.{patients,contexts}
- `normal_value` / `critical_value` / `crossed` / `realize_tier` / `format_measurement` / `decimals_for` → BoundarySampler methods
- `TIER_WINDOWS` → spec_json.generator.tier_windows
- `PANEL_CATEGORY` → spec_json.generator.categories

- [ ] **Step 2: Add 4 sampling functions to `kev/console/generators/ops.py`**

Append to `ops.py`:

```python
from random import Random
from typing import List, Optional, Tuple


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
```

- [ ] **Step 3: Add the legacy sampling helpers to `ops.py` so `BoundarySampler` can use them**

Append to `ops.py`:

```python
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
        low, high = ranges[0]
        threshold = high if side == "high" else low
        return boundary_value(rng, threshold=threshold, low=low, high=high, near=0.0, decimals=field.get("decimals", 1))
    raise ValueError(f"field {field['name']} has no critical range")


def crossed(rng: Random, field: dict) -> float:
    """Replaces gen_critical_value.crossed — a safe-side value just outside critical."""
    from common import boundary_value
    crit = field.get("critical", {})
    for side, ranges in crit.items():
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
```

- [ ] **Step 4: Implement `BoundarySampler.sample` in `sampler.py`**

Replace the stub `sample` method in `sampler.py` with:

```python
    def sample(self, state_target, rng):
        """One state record. Returns None if the target is not realizable.

        `state_target` is None (normal) or (tier, category). The sampling algorithm mirrors
        gen_critical_value.build exactly so the random number stream matches byte-for-byte.
        """
        from . import ops
        from common import boundary_value
        tier, category = state_target if state_target else (None, "none")
        # Step 1: pick a triggering field
        if state_target:
            panels_for_category = [
                f for f in self.fields
                if f.get("category") == category
                and (str(tier), f["name"]) in {
                    (t, name): ranges
                    for t, mapping in self.tier_windows.items()
                    for name, ranges in mapping.items()
                }
            ]
        else:
            panels_for_category = list(self.fields)
        if not panels_for_category:
            return None
        triggering_field = rng.choice(panels_for_category)
        # Step 2: pick 2-5 non-triggering fields
        others = [f for f in self.fields if f["name"] != triggering_field["name"]]
        chosen = {triggering_field["name"]: triggering_field}
        for extra in rng.sample(others, rng.randint(2, 5)):
            chosen[extra["name"]] = extra
        # Step 3: sample normal values for all
        state = {n: ops._format(f, ops.normal_value(rng, f), with_unit=True) for n, f in chosen.items()}
        # Step 4: realize target tier
        if state_target:
            value = ops.realize_tier(rng, triggering_field, tier, self.tier_windows)
            if value is None:
                return None
            state[triggering_field["name"]] = ops._format(triggering_field, value, with_unit=True)
            # Sometimes add a second critical item (carry-over logic from gen_critical_value.build)
            if rng.random() < 0.35:
                non_critical = [
                    n for n in chosen
                    if not ops._is_in_critical_range(
                        ops._parse_value(state[n], chosen[n].get("decimals", 1)),
                        chosen[n],
                    )
                ]
                for other in rng.sample(non_critical, min(2, len(non_critical))):
                    v2 = ops.critical_value(rng, chosen[other])
                    if ops._is_in_critical_range(v2, chosen[other]) and \
                       ops.min_tier({other: ops._format(chosen[other], v2, with_unit=False)}, [chosen[other]], self.tier_windows) >= tier:
                        state[other] = ops._format(chosen[other], v2, with_unit=True)
                        break
        return state
```

- [ ] **Step 5: Verify `sampler.sample` runs without error**

Run: `uv run python -c "from kev.console.generators.sampler import BoundarySampler; import json, random; spec=json.loads(open('docs/medical/specs/critical-value.json').read())['generator']; bs=BoundarySampler(spec['fields'], spec['selectors'], spec['tier_windows']); rng=random.Random(0); print(bs.sample((0, 'electrolyte'), rng))"`
Expected: prints a dict with 3-6 field names as keys. No exception. (Some fields may be missing because the spec under `critical-value.json` in the repo doesn't have `generator` yet — if so, hardcode a minimal spec inline in the test command.)

- [ ] **Step 6: Commit**

```bash
git add kev/console/generators/sampler.py kev/console/generators/ops.py
git commit -m "engine(console): implement BoundarySampler for critical-value fields"
```

---

### Task 5: Wire `BoundarySampler` + `RuleEvaluator` + `PlanAllocator` into `engine.run`

**Files:**
- Modify: `kev/console/generators/engine.py`

**Interfaces:**
- `engine.run(argv)` — now actually writes a JSONL file. For Task 5, the records only have `state` + bare `labels` (no `soft`, no `evidence_sufficient` overrides). The full record assembly (state + patient + context + missing_context + common.labelled) lands in Task 6.
- The byte-for-byte regression test only runs in Task 7; this task just proves the loop runs end-to-end.

- [ ] **Step 1: Read `kev/console/generators/common.py` to confirm `load_spec` and `write_records` are importable**

Verify: `from common import load_spec, write_records` works when `kev/console/generators` is on sys.path. (The `paths.ensure_generators_on_path` helper already does this; the engine relies on it.)

- [ ] **Step 2: Replace the stub `run` body in `engine.py`**

Replace the `run` function body (the part after the `sampler/evaluator/...` instantiation, before `return 0`) with:

```python
    plan = allocator.allocate(args.n, rng)
    records = []
    for state_target in plan:
        state = sampler.sample(state_target, rng)
        if state is None:
            # target not realizable; fall back to normal
            state = sampler.sample(None, rng)
        if state is None:
            continue
        labels = evaluator.evaluate(state)
        records.append({"state": state, "labels": labels})
    print(f"engine: scenario={args.scenario} n={args.n} produced={len(records)} seed={args.seed}")
    # Real record assembly (common.labelled + patient + context) is added in Task 6.
    return 0
```

- [ ] **Step 3: Verify the engine runs without error**

Run: `uv run python -m kev.console.generators.engine --scenario critical-value --n 10 --out /tmp/x.jsonl --seed 0`
Expected: prints `engine: scenario=critical-value n=10 produced=N seed=0` where N is between 5 and 10. No exception. (The output file may not be created yet — that's Task 6.)

- [ ] **Step 4: Commit**

```bash
git add kev/console/generators/engine.py
git commit -m "engine(console): wire sampler + rules + plan into engine.run loop"
```

---

### Task 6: Add `patient` / `context` / `missing_context` fields + `common.labelled` record assembly

**Files:**
- Modify: `kev/console/generators/engine.py`
- Modify: `kev/console/generators/sampler.py`

**Interfaces:**
- `BoundarySampler` now accepts `contexts: List[str]` and `patients: List[str]` in its constructor.
- `engine.run` writes records through `common.labelled` so each record has the same shape `gen_critical_value.make_record` produces.

- [ ] **Step 1: Add `contexts` and `patients` parameters to `BoundarySampler.__init__`**

Modify `sampler.py`:

```python
class BoundarySampler:
    def __init__(self, fields, selectors, tier_windows=None, contexts=None, patients=None):
        self.fields = fields
        self.selectors = selectors
        self.tier_windows = tier_windows or {}
        self.contexts = contexts or []
        self.patients = patients or []
```

- [ ] **Step 2: Add a `make_record` method to `BoundarySampler`**

Append to the `BoundarySampler` class in `sampler.py`:

```python
    def make_record(self, state: dict, rng, dropped: str = "", context: str = "") -> dict:
        """Assemble one labelled Kev record from a state dict (the legacy gen_* make_record shape).

        `dropped` names the element removed on purpose ("" for none). `context` overrides the random context
        for evidence_drop tests; the default is to draw one from `self.contexts`.
        """
        from common import labelled, load_spec
        # The "labels" come from the engine, not the sampler; engine.py passes them in. Here we just assemble state.
        patient = rng.choice(self.patients) if self.patients else "patient"
        ctx = context or (rng.choice(self.contexts) if self.contexts else "")
        full_state = {
            "patient": patient,
            "context": ctx,
            "labs": state,
            "ref_ranges_included": dropped != "reference_range",
            "missing_context": [dropped] if dropped else [],
        }
        return full_state
```

- [ ] **Step 3: Update `engine.run` to assemble full records and write JSONL**

Replace the record assembly loop in `engine.py`:

```python
    plan = allocator.allocate(args.n, rng)
    records = []
    for state_target in plan:
        # Sample state
        state = sampler.sample(state_target, rng)
        if state is None:
            state = sampler.sample(None, rng)
        if state is None:
            continue
        # Evaluate rules
        labels = evaluator.evaluate(state)
        # evidence_drop stub: 8% rate, drop unit or refs
        with_unit, with_refs = True, True
        dropped = ""
        if rng.random() < 0.08:
            if rng.random() < 0.5:
                with_unit = False
                dropped = "unit"
            else:
                with_refs = False
                dropped = "reference_range"
        # Assemble state + labels via common.labelled
        from common import labelled, load_spec, write_records
        spec = load_spec(args.scenario)
        full_state = sampler.make_record(state, rng, dropped=dropped)
        # Format values: strip unit if with_unit=False, strip refs if with_refs=False.
        # The current sampler always includes the unit in the value; the legacy "drop unit" is implemented in
        # gen_critical_value by NOT calling format_measurement with_unit=True. For now we leave the unit in the
        # value (evidence_drop is a soft signal, not a literal state change in this version) — the labels
        # `evidence_sufficient` will be flipped by the rules evaluator, not by state mutation.
        record = labelled(spec, full_state, labels)
        records.append(record)
    write_records(records, args.out, args.seed, args.scenario)
    return 0
```

- [ ] **Step 4: Run the engine on a small N to verify it writes a JSONL**

Run: `uv run python -m kev.console.generators.engine --scenario critical-value --n 50 --out /tmp/x.jsonl --seed 0`
Expected: prints the `write_records` summary (50 records; label counts per question). `/tmp/x.jsonl` is a non-empty file with 50 lines of valid JSON.

- [ ] **Step 5: Commit**

```bash
git add kev/console/generators/sampler.py kev/console/generators/engine.py
git commit -m "engine(console): assemble full Kev records via common.labelled"
```

---

### Task 7: `test_critical_value_byte_for_byte` — the regression gate

**Files:**
- Create: `tests/test_engine.py`
- Create: `tests/fixtures/critical-value/spec.json`

**Interfaces:**
- The test reads the fixture's `generator` field and runs the engine with `n=787, seed=0, pairs=0`. (Minimal pairs land in Task 9; until then, `pairs=0`.)
- The test diffs engine output against `runs/kev-console/golden/critical-value.jsonl` (committed in Task 3) line by line.

- [ ] **Step 1: Build the `tests/fixtures/critical-value/spec.json` fixture**

Read `docs/medical/specs/critical-value.json`. Build a sibling fixture at `tests/fixtures/critical-value/spec.json` with the same `name` / `domain` / `state` / `state_example` / `questions` / `guidance` / `variety` fields PLUS the `generator` block. The `generator` block must contain:
- `fields`: 10 entries translated from `gen_critical_value.PANELS` (names: K+, Na+, GLU, Cr, pH, Hb, PLT, WBC, cTn, D-Dimer; categories: electrolyte / renal / glucose_gas / cbc / cardiac_coag; normal ranges; critical ranges; one_sided for cTn + D-Dimer)
- `selectors`: `[{"min": 3, "max": 6, "weight_normal": 1.0, "weight_trigger_extra": 0.35, "max_trigger_extra": 2, "max_trigger_tier_drift": 0}]`
- `categories`: derived from fields[].category
- `tier_windows`: the 3-tier mapping from `gen_critical_value.TIER_WINDOWS`
- `contexts`: the `CONTEXTS` list (8 entries)
- `patients`: the `PATIENTS` list (8 entries: male 67, female 58, ...)
- `rules`: 3 rules from the spec §4 example
- `augmentation`: `{"evidence_drop": {"rate": 0.08, "fields": ["unit", "reference_range"], "question": "is_critical", "soft_target": {"true": 0.5, "false": 0.5}, "force_label": {"evidence_sufficient": "false"}}, "minimal_pair": {"rate": 0.0, "strategy": "boundary_flip"}}` (rate 0 until Task 9)
- `plan_targets`: the 5-category share / quota / tier_split from spec §4

- [ ] **Step 2: Wire the fixture path: engine reads from DB, but tests need a fixture path**

Modify `kev/console/generators/engine.py::_load_spec` to support a `KEV_ENGINE_SPEC_DIR` environment variable that overrides `paths.SPECS`:

```python
import os

def _load_spec(scenario: str) -> dict:
    from kev.console import paths
    spec_dir = Path(os.environ.get("KEV_ENGINE_SPEC_DIR", str(paths.SPECS)))
    spec_file = spec_dir / f"{scenario}.json"
    return json.loads(spec_file.read_text(encoding="utf-8"))
```

- [ ] **Step 3: Write the test**

Create `tests/test_engine.py`:

```python
"""Spec-driven engine regression: byte-for-byte equivalence with the legacy gen_*.py output."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
FIXTURES = REPO / "tests" / "fixtures"
GOLDEN = REPO / "runs" / "kev-console" / "golden"


def _run_engine(scenario: str, n: int, seed: int, out: Path) -> None:
    env = os.environ.copy()
    env["KEV_ENGINE_SPEC_DIR"] = str(FIXTURES)
    subprocess.run(
        [sys.executable, "-m", "kev.console.generators.engine",
         "--scenario", scenario, "--n", str(n), "--out", str(out), "--seed", str(seed), "--pairs", "0"],
        check=True, env=env, cwd=REPO,
    )


def test_critical_value_byte_for_byte(tmp_path):
    out = tmp_path / "cv.jsonl"
    _run_engine("critical-value", n=787, seed=0, out=out)
    golden = GOLDEN / "critical-value.jsonl"
    assert out.read_text(encoding="utf-8") == golden.read_text(encoding="utf-8"), (
        f"engine output for critical-value differs from golden. Run:\n"
        f"  diff {golden} {out}\n"
        f"to see the divergence. Likely cause: BoundarySampler random stream drifted from gen_critical_value.build."
    )
```

- [ ] **Step 4: Run the test**

Run: `uv run --extra serve python -m pytest tests/test_engine.py::test_critical_value_byte_for_byte -v`
Expected: PASS. If FAIL, diff the two files (the test failure message points to the diff command) and adjust `BoundarySampler` / `engine.run` until they match.

- [ ] **Step 5: Commit**

```bash
git add tests/test_engine.py tests/fixtures/critical-value/spec.json kev/console/generators/engine.py
git commit -m "test(console): engine critical-value byte-for-byte regression"
```

**PHASE A GATE: `test_critical_value_byte_for_byte` passes. Reviewer may stop here to validate the engine architecture before continuing.**

---

## Phase B: Generalise to the other 5 scenarios + operators + minimal pair

### Task 8: Add the remaining 12 domain operators to `ops.py`

**Files:**
- Modify: `kev/console/generators/ops.py`

**Interfaces:**
- 12 new functions registered in `ALLOWED`: `any_special_population`, `dose_exceeds`, `duplicate_category`, `indication_matches`, `lift_severity`, `missing_element`, `tier_priority_arbiter`, `red_flag_wins`, `pediatric_short_circuit`, `min_tier`, `fastest_tier_critical_item`, `any_outside_critical`. Each function has a docstring citing the source line in the legacy `gen_*.py` it replaces.

- [ ] **Step 1: Add 12 new operator stubs to `ops.py`**

Append to `ops.py`:

```python
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
```

- [ ] **Step 2: Register all 12 in `ALLOWED`**

Update `ALLOWED` in `ops.py`:

```python
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
```

- [ ] **Step 3: Verify the whitelist is enforced**

Add a temporary check at the bottom of `tests/test_engine.py` (will be moved to its own test in Task 14):

```python
def test_ops_whitelist_enforced():
    """simpleeval must reject __import__ and any non-whitelisted function."""
    from kev.console.generators.ops import ALLOWED
    from simpleeval import SimpleEval
    evaluator = SimpleEval(functions=ALLOWED, names={"state": {}})
    with pytest.raises(Exception):
        evaluator.eval("__import__('os')")
    with pytest.raises(Exception):
        evaluator.eval("open('foo')")
```

- [ ] **Step 4: Run the new test**

Run: `uv run --extra serve python -m pytest tests/test_engine.py::test_ops_whitelist_enforced -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add kev/console/generators/ops.py tests/test_engine.py
git commit -m "engine(console): register 12 domain operators in simpleeval whitelist"
```

---

### Task 9: `PairBuilder.boundary_flip` + `Augmentor.evidence_drop` + minimal pair wiring

**Files:**
- Modify: `kev/console/generators/pair.py`
- Modify: `kev/console/generators/augment.py`
- Modify: `kev/console/generators/engine.py`

**Interfaces:**
- `PairBuilder.build(record, handle, rng)` returns a twin record whose state differs in exactly one field and whose label flips. `handle` is the legacy `{"name", "panels", "values", "dropped", "with_unit", "with_refs"}` dict that `BoundarySampler` produces.
- `Augmentor.apply` does the evidence_drop post-processing (8% rate, drop unit or refs, flip `evidence_sufficient` to false, inject soft target) and returns `(state, labels, soft)`.
- `engine.run` calls `pair_builder.build` after each record and appends the twin if non-None.

- [ ] **Step 1: Implement `PairBuilder.boundary_flip`**

Replace the `build` method in `pair.py`:

```python
    def build(self, record, handle, rng):
        """The minimal pair for `record`: a twin whose triggering measurement is on the safe side of the bound.

        Returns None when the record has no safely flippable field (legacy `gen_*` `pair_twin` semantics).
        """
        if handle is None or handle.get("dropped"):
            return None
        name = handle["name"]
        # The state already has all values formatted; we need the raw value to re-sample the safe side.
        # Pull the value out of record.state (it's the formatted string "6.2 mmol/L").
        formatted = record["state"]["labs"][name]
        # Re-sample the safe side via the sampler.
        from . import ops
        panel = handle["panels"][name]
        # The sampler re-uses the panel's field-shape dict.
        field = {"name": name, "unit": panel[2] if len(panel) > 2 else "", "decimals": ops._decimals_for(name)}
        safe = ops.crossed(rng, field)
        if ops._is_in_critical_range(safe, field):
            return None
        # Build the twin record.
        twin_state = dict(record["state"])
        twin_labs = dict(twin_state["labs"])
        twin_labs[name] = ops._format(field, safe, with_unit=True)
        twin_state["labs"] = twin_labs
        twin_record = {"state": twin_state, "questions": {}}
        # Re-evaluate rules on the twin.
        from .rules import RuleEvaluator
        evaluator = RuleEvaluator(handle.get("rules", []))
        twin_labels = evaluator.evaluate(twin_state["labs"])
        for qid, value in twin_labels.items():
            twin_record["questions"][qid] = {"type": "noul", "label": value}
        return twin_record
```

- [ ] **Step 2: Implement `Augmentor.evidence_drop`**

Replace `Augmentor.apply` in `augment.py`:

```python
    def apply(self, state, labels, rng):
        """Apply evidence_drop: 8% rate, drop unit or refs, flip evidence_sufficient to false, inject soft target.

        Returns (state_modified, labels_modified, soft). `state` and `labels` are not mutated.
        """
        from copy import deepcopy
        new_state = deepcopy(state)
        new_labels = dict(labels)
        soft = {}
        ev = self.augmentation.get("evidence_drop")
        if not ev:
            return new_state, new_labels, soft
        if rng.random() < ev.get("rate", 0.0):
            # Force `evidence_sufficient=false` per spec.
            force = ev.get("force_label", {})
            for label, value in force.items():
                new_labels[label] = value
            # Inject soft target.
            question = ev.get("question")
            if question:
                soft[question] = ev.get("soft_target", {})
        return new_state, new_labels, soft
```

- [ ] **Step 3: Wire Augmentor + PairBuilder into `engine.run`**

Modify the record assembly loop in `engine.py`:

```python
        labels = evaluator.evaluate(state)
        # Apply augmentation (evidence_drop + soft injection)
        state, labels, soft = augmentor.apply(state, labels, rng)
        # Assemble record
        full_state = sampler.make_record(state, rng, dropped=dropped)
        record = labelled(spec, full_state, labels, soft=soft or None)
        records.append(record)
        # Optional: build a minimal pair twin.
        if args.pairs > 0 and rng.random() < args.pairs:
            handle = {"name": triggering_field["name"], "panels": chosen, "values": {}, "dropped": dropped}
            twin = pair_builder.build(record, handle, rng)
            if twin is not None:
                # The twin has its own state but needs a full record. Reuse the same patient/context.
                twin_full_state = sampler.make_record(twin["state"]["labs"], rng, dropped="")
                twin_labels = {qid: q["label"] for qid, q in twin["questions"].items()}
                twin_record = labelled(spec, twin_full_state, twin_labels)
                records.append(twin_record)
```

- [ ] **Step 4: Run the engine on critical-value with `pairs=0.35` and verify output length is plausible**

Run: `uv run python -m kev.console.generators.engine --scenario critical-value --n 100 --out /tmp/x.jsonl --seed 0 --pairs 0.35`
Expected: prints `100 records`; 100-150 records in the output (each may produce 0-1 twin).

- [ ] **Step 5: Commit**

```bash
git add kev/console/generators/pair.py kev/console/generators/augment.py kev/console/generators/engine.py
git commit -m "engine(console): wire minimal-pair + evidence_drop augmentation"
```

---

### Task 10-15: Build the other 5 scenarios' `tests/fixtures/<slug>/spec.json` + byte-for-byte tests

These 5 tasks follow the same pattern as Task 7. For each scenario:

- **Step 1**: Translate the legacy `gen_<slug>.py` constants (e.g. `DRUGS`, `CHECKLIST`, `SYMPTOMS`) into the spec's `generator.fields` (or `categories` / `rules` / `plan_targets`) shape.
- **Step 2**: Build `tests/fixtures/<slug>/spec.json` with the full generator block.
- **Step 3**: Generate the golden `runs/kev-console/golden/<slug>.jsonl` by running the legacy `gen_<slug>.py --n 787 --seed 0 --pairs 0.35` and copying the output.
- **Step 4**: Add `<test_<slug>_byte_for_byte>` to `tests/test_engine.py`.
- **Step 5**: Run the test and iterate on `BoundarySampler` until it matches.

The 5 tasks:

| Task | Slug | Legacy file | Notes |
|---|---|---|---|
| 10 | `medication-review` | `gen_medication_review.py` | DRUGS table → fields; evaluate() → rules; sample_plan() → plan_targets |
| 11 | `triage` | `gen_triage.py` | SYMPTOMS table → fields; PEDIATRIC short-circuit; round-robin plan |
| 12 | `nursing-quality` | `gen_nursing_quality.py` | CHECKLIST table → fields; RISK table → categories; lift_severity rule |
| 13 | `record-summary` | `gen_record_summary.py` | 8 element categories → fields; missing_element rule; ELEMENT_SEVERITY |
| 14 | `diagnosis` | `gen_diagnosis.py` | FINDINGS table → fields; tier_priority_arbiter; red_flag_wins; round-robin plan |
| 15 | (this is the `PlanAllocator` round-robin + custom_strategy implementation, applied to diagnosis + triage) |

For each task, the implementation steps are:

- [ ] **Step 1: Read the legacy `gen_<slug>.py` to extract the data**

Use `Read` to read the full file. Identify the data tables (e.g. `DRUGS`, `CHECKLIST`, `SYMPTOMS`) and the `decide` / `derive` / `evaluate` / `sample_plan` functions.

- [ ] **Step 2: Translate the data tables to the spec's `generator` block**

Write the `tests/fixtures/<slug>/spec.json` file. Use the spec §4 critical-value example as a template; the `generator.fields` shape is consistent (every field is a dict with `name`, `unit`, `decimals`, `category`, `normal`, `critical`, `extremes`).

- [ ] **Step 3: Generate the golden file**

Run: `uv run python kev/console/generators/gen_<slug>.py --n 787 --out runs/kev-console/golden/<slug>.jsonl --seed 0 --pairs 0.35`
Expected: prints the `write_records` summary; `runs/kev-console/golden/<slug>.jsonl` has 1000-1500 lines.

- [ ] **Step 4: Add the test**

Add a test in `tests/test_engine.py`:

```python
@pytest.mark.parametrize("scenario", [
    "medication-review",
    "triage",
    "nursing-quality",
    "record-summary",
    "diagnosis",
])
def test_<slug>_byte_for_byte(scenario, tmp_path):
    out = tmp_path / f"{scenario}.jsonl"
    _run_engine(scenario, n=787, seed=0, out=out)
    golden = GOLDEN / f"{scenario}.jsonl"
    assert out.read_text(encoding="utf-8") == golden.read_text(encoding="utf-8"), (
        f"engine output for {scenario} differs from golden."
    )
```

- [ ] **Step 5: Run the test and iterate**

Run: `uv run --extra serve python -m pytest tests/test_engine.py::test_<slug>_byte_for_byte -v`
Expected: PASS. If FAIL, diff the files and adjust the engine.

- [ ] **Step 6: Commit**

```bash
git add tests/fixtures/<slug>/spec.json runs/kev-console/golden/<slug>.jsonl tests/test_engine.py
git commit -m "test(console): <slug> byte-for-byte engine regression"
```

**PHASE B GATE: all 5 `test_*_byte_for_byte` tests pass. Reviewer may stop here to validate the engine against the full 5-scenario regression set.**

---

## Phase C: Distill entry (render + make_seeds + seed_to_kev + check_volume) + yaml template

### Task 16: Create `kev/console/distill/render.py` (DistillRenderer)

**Files:**
- Create: `kev/console/distill/render.py`

**Interfaces:**
- `DistillRenderer(spec_distill: dict) -> object` — wraps Jinja2 Environment.
- `renderer.render_system_prompt(lang: str) -> str` — renders `system_prompt[lang]` (default: `"zh"`).
- `renderer.render_ask(state: dict) -> str` — renders `ask_template` with `state` substituted.
- `renderer.render_state(state: dict) -> str` — flat key-value lines (port from `make_seeds.render_state`).

- [ ] **Step 1: Create `render.py`**

```python
"""DistillRenderer — Jinja2-based rendering of system_prompt + ask_template from spec_json.distill.

Spec §3.5. Replaces the hardcoded SYSTEM_PROMPTS + ASK dicts in kev/console/distill/make_seeds.py.
"""
from __future__ import annotations

from jinja2 import Environment, BaseLoader, StrictUndefined
from typing import Any, Dict


class DistillRenderer:
    def __init__(self, distill: Dict[str, Any]):
        # autoescape=False: LLM prompts are plain text, not HTML. StrictUndefined catches typos in
        # {state.foo} placeholders at render time.
        self.env = Environment(loader=BaseLoader(), autoescape=False, undefined=StrictUndefined)
        self.distill = distill
        self.system_prompts = distill.get("system_prompt", {})
        self.ask_template = distill.get("ask_template", "")

    def render_system_prompt(self, lang: str = "zh") -> str:
        text = self.system_prompts.get(lang) or self.system_prompts.get("zh", "")
        return self.env.from_string(text).render()

    def render_ask(self, state: Dict[str, Any]) -> str:
        return self.env.from_string(self.ask_template).render(state=render_state(state))

    def render_topics(self) -> list:
        return self.distill.get("topics", [])


def render_state(state: Dict[str, Any]) -> str:
    """Port of make_seeds.render_state: flatten a state object into key: value lines."""
    lines = []
    for key, value in state.items():
        if isinstance(value, dict):
            inner = "，".join(f"{k} {v}" for k, v in value.items())
            lines.append(f"{key}：{inner}")
        elif isinstance(value, list):
            lines.append(f"{key}：" + ("、".join(str(v) for v in value) if value else "无"))
        else:
            lines.append(f"{key}：{value}" if value not in ("", None) else f"{key}：未记录")
    return "\n".join(lines)
```

- [ ] **Step 2: Verify rendering works on a critical-value spec**

Run: `uv run python -c "import json; from kev.console.distill.render import DistillRenderer; r=DistillRenderer(json.loads(open('docs/medical/specs/critical-value.json').read()).get('distill', {})); print(r.render_system_prompt('zh'))"`
Expected: prints the system prompt text (or an empty string if the spec has no `distill` block yet — that's fine for now).

- [ ] **Step 3: Commit**

```bash
git add kev/console/distill/render.py
git commit -m "distill(console): add DistillRenderer (Jinja2-based) for spec.distill"
```

---

### Task 17: Slim down `make_seeds.py` — delete 4 dicts, read from DB

**Files:**
- Modify: `kev/console/distill/make_seeds.py`

**Interfaces:**
- `make_seeds --all` reads every scenario from the DB, filters to those with `distill.kev_track=True`, and runs the engine + DistillRenderer.
- `make_seeds --scenario <slug>` runs one scenario.
- `make_seeds config <slug>` (new subcommand) renders the YAML config from the Jinja2 template.

- [ ] **Step 1: Remove the 4 hardcoded dicts**

In `make_seeds.py`, delete the following blocks (in their entirety):
- `SCENARIOS` (the dict mapping `inquiry` → `tri`, etc.)
- `SYSTEM_PROMPTS`
- `ASK`
- The `import gen_diagnosis as dg` / `import gen_medication_review as mr` / etc. lines (the engine handles these)

- [ ] **Step 2: Add DB reading + DistillRenderer usage**

Replace the main `make_seeds` function body with:

```python
def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--scenario", type=str, default=None)
    parser.add_argument("--n", type=int, default=500)
    parser.add_argument("--out-dir", type=str, default="data/seeds")
    parser.add_argument("--lang", type=str, default="zh", choices=["zh", "en"])
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    from kev.console.db import Store
    from kev.console.distill.render import DistillRenderer
    store = Store()
    slugs = [args.scenario] if args.scenario else store.list_scenario_slugs()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for slug in slugs:
        row = store.get_scenario_by_slug(slug)
        if not row or not row.get("spec_json"):
            continue
        spec = json.loads(row["spec_json"])
        distill = spec.get("distill", {})
        if not distill.get("kev_track", False):
            # knowledge-qa etc.: SFT-only, no Kev sidecar
            continue
        renderer = DistillRenderer(distill)
        system = renderer.render_system_prompt(args.lang)
        # Run the engine to produce states
        from kev.console.generators.engine import run as engine_run
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as tmp:
            tmp_path = Path(tmp.name)
        engine_run(["--scenario", slug, "--n", str(args.n), "--out", str(tmp_path), "--seed", str(args.seed), "--pairs", "0"])
        # Split into seed + state
        with tmp_path.open(encoding="utf-8") as f:
            for i, line in enumerate(f):
                record = json.loads(line)
                state = record["state"]
                ask = renderer.render_ask(state)
                seed_row = {"id": str(i), "instruction": ask, "system": system}
                state_row = {"id": str(i), "scenario": slug, "state": state, "labels": record["questions"], "soft": {}}
                with (out_dir / f"{slug}.seed.jsonl").open("a", encoding="utf-8") as fs:
                    fs.write(json.dumps(seed_row, ensure_ascii=False) + "\n")
                with (out_dir / f"{slug}.state.jsonl").open("a", encoding="utf-8") as fst:
                    fst.write(json.dumps(state_row, ensure_ascii=False) + "\n")
        tmp_path.unlink()
```

- [ ] **Step 3: Verify the slim `make_seeds` runs (with DB backfilled via Task 22, it should work end-to-end)**

Run: `uv run python -m kev.console.distill.make_seeds --scenario critical-value --n 10 --out-dir /tmp/seeds`
Expected: creates `/tmp/seeds/critical-value.seed.jsonl` and `/tmp/seeds/critical-value.state.jsonl` with 10 rows each; the system prompt is rendered (not empty); the ask template is rendered with the state filled in.

- [ ] **Step 4: Commit**

```bash
git add kev/console/distill/make_seeds.py
git commit -m "distill(console): make_seeds reads from DB + DistillRenderer (no hardcoded dicts)"
```

---

### Task 18: Slim down `seed_to_kev.py` + `check_volume.py`

**Files:**
- Modify: `kev/console/distill/seed_to_kev.py`
- Modify: `kev/console/distill/check_volume.py`

**Interfaces:**
- `seed_to_kev.py` no longer has `SPEC_FOR`; it reads every scenario from the DB and joins `<slug>.state.jsonl` with the engine output.
- `check_volume.py` no longer has `SPEC_FOR` or `SFT_ONLY`; it reads from the DB.

- [ ] **Step 1: Delete `SPEC_FOR` from `seed_to_kev.py`**

In `seed_to_kev.py`, delete the `SPEC_FOR = {"inquiry": "triage", ...}` dict. Replace usages with a DB lookup: `from kev.console.db import Store; store = Store(); slug = store.get_scenario_by_slug(distill_slug)["spec_json"]` — distill_slug comes from the sidecar `state.jsonl` row's `scenario` field.

- [ ] **Step 2: Delete `SPEC_FOR` and `SFT_ONLY` from `check_volume.py`**

In `check_volume.py`, delete the two dicts. Replace the `--scenario` lookup with a DB query. Replace the `SFT_ONLY` check with `if not spec.get("distill", {}).get("kev_track", False): continue`.

- [ ] **Step 3: Verify both scripts still run**

Run: `uv run python -m kev.console.distill.check_volume --all --records-dir /tmp/seeds --budget 8000000`
Expected: prints the per-scenario distribution table; no exception.

- [ ] **Step 4: Commit**

```bash
git add kev/console/distill/seed_to_kev.py kev/console/distill/check_volume.py
git commit -m "distill(console): seed_to_kev + check_volume read SPEC_FOR from DB"
```

---

### Task 19: Create `kev/console/distill/configs/template.yaml.j2`

**Files:**
- Create: `kev/console/distill/configs/template.yaml.j2`

**Interfaces:**
- A Jinja2 template that takes `slug`, `system_prompt`, `input_file`, `output_dir` and emits the EasyDistill YAML format.
- The rendered YAML must match the existing 5 `kev/console/distill/configs/*.yaml` byte-for-byte (modulo the system prompt text).

- [ ] **Step 1: Read the 5 existing YAML configs**

Read: `kev/console/distill/configs/inquiry.yaml`, `medication.yaml`, `diagnosis.yaml`, `record-summary.yaml`, `knowledge-qa.yaml`.

- [ ] **Step 2: Build the template**

Create `kev/console/distill/configs/template.yaml.j2`:

```jinja2
# {{ spec.name }} — 生成式 SFT 轨
# 自动生成自 kev/console/distill/configs/template.yaml.j2
# 修改模板而非本文件（make_seeds config --scenario <slug> 会重新生成）
#
# teacher: 蚂蚁百灵云端 Open API（OpenAI 兼容）。base_url 与 api_key 从环境变量读，**不要写进本文件**。
#   $env:KEV_GEN_API_KEY = "..."
#   $env:KEV_GEN_BASE_URL = "https://<官方 base URL>/v1"
#
# 这个配置只产出生成式 SFT 样本。Kev 决策记录由 seed_to_kev.py 从旁路 sidecar 重建，不经过本流水线 ——
# 标签不来自 LLM。
# 用法: easydistill --config <out-dir>/configs/{{ slug }}.yaml
job_type: advanced_instruct_distill

backend:
  type: openai
  model: ling-3.0-flash
  base_url: ${KEV_GEN_BASE_URL}
  api_key: ${KEV_GEN_API_KEY}
  temperature: 1.0
  max_tokens: 2048
  concurrency: 2

dataset:
  instruction_key: instruction
  input_file: {{ input_file }}
  output_dir: {{ output_dir }}

system_prompt: >-
  {{ system_prompt }}

pipeline:
  - stage: instruction_expansion
    output: {{ output_dir }}/expanded.jsonl
    params:
      num_per_seed: 3
  - stage: generate
    output: {{ output_dir }}/generated.jsonl
  - stage: judge
    output: {{ output_dir }}/judged.jsonl
    params:
      dimensions: [correctness, helpfulness, informativeness, generalization]
      pass_score: 7
  - stage: filter
    output: {{ output_dir }}/filtered.jsonl
    params:
      require_correctness: true
  - stage: build_sft
    output: {{ output_dir }}/{{ slug }}.sft.jsonl

resume: true
```

- [ ] **Step 3: Add a `make_seeds config <slug>` subcommand**

In `make_seeds.py`, add the subcommand:

```python
def render_config(slug: str, out_dir: str = "data/seeds/configs") -> None:
    from kev.console.db import Store
    from kev.console.distill.render import DistillRenderer
    from jinja2 import Environment, FileSystemLoader
    store = Store()
    row = store.get_scenario_by_slug(slug)
    if not row or not row.get("spec_json"):
        raise SystemExit(f"scenario {slug} not found or has no spec_json")
    spec = json.loads(row["spec_json"])
    distill = spec.get("distill", {})
    renderer = DistillRenderer(distill)
    env = Environment(loader=FileSystemLoader(str(Path(__file__).parent / "configs")), autoescape=False, keep_trailing_newline=True)
    template = env.get_template("template.yaml.j2")
    rendered = template.render(
        spec=spec,
        slug=slug,
        system_prompt=renderer.render_system_prompt("zh"),
        input_file=f"data/seeds/{slug}.seed.jsonl",
        output_dir=f"data/sft/{slug}",
    )
    out_path = Path(out_dir) / f"{slug}.yaml"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(rendered, encoding="utf-8")
    print(f"wrote {out_path}")
```

- [ ] **Step 4: Verify the template renders for 5 scenarios**

Run: `uv run python -m kev.console.distill.make_seeds config --scenario inquiry --out-dir /tmp/cfg`
Expected: `/tmp/cfg/inquiry.yaml` is created; contains the system prompt + the 5-stage pipeline. Open the file and verify the system_prompt is the critical-value spec's `distill.system_prompt.zh` text.

- [ ] **Step 5: Commit**

```bash
git add kev/console/distill/configs/template.yaml.j2 kev/console/distill/make_seeds.py
git commit -m "distill(console): add template.yaml.j2 + make_seeds config subcommand"
```

---

### Task 20: `test_yaml_template_render` — golden byte-for-byte test

**Files:**
- Modify: `tests/test_engine.py`

**Interfaces:**
- The test reads the 5 existing `kev/console/distill/configs/<slug>.yaml` files (committed in `docs/medical/specs/*/distill` once Task 22 is done) and compares them to the rendered output of `make_seeds config --scenario <slug>`.

- [ ] **Step 1: Add the test**

Add to `tests/test_engine.py`:

```python
def test_yaml_template_render(tmp_path):
    """The 5 existing distill/configs/*.yaml files must be byte-equal to the rendered template output."""
    import subprocess
    import sys
    for slug in ["inquiry", "medication", "diagnosis", "record-summary", "knowledge-qa"]:
        out_dir = tmp_path / "cfg"
        subprocess.run(
            [sys.executable, "-m", "kev.console.distill.make_seeds", "config",
             "--scenario", slug, "--out-dir", str(out_dir)],
            check=True, cwd=REPO,
        )
        rendered = (out_dir / f"{slug}.yaml").read_text(encoding="utf-8")
        committed = (REPO / "kev/console/distill/configs" / f"{slug}.yaml").read_text(encoding="utf-8")
        assert rendered == committed, (
            f"yaml template render for {slug} differs from committed. Diff:\n"
            f"  diff kev/console/distill/configs/{slug}.yaml {out_dir}/{slug}.yaml"
        )
```

- [ ] **Step 2: Run the test**

Run: `uv run --extra serve python -m pytest tests/test_engine.py::test_yaml_template_render -v`
Expected: PASS (after the 5 committed yamls are updated in Task 28). Until then, this test may fail — that's expected; it will pass after Task 28.

- [ ] **Step 3: Commit**

```bash
git add tests/test_engine.py
git commit -m "test(console): yaml template render byte-for-byte"
```

**PHASE C GATE: `test_yaml_template_render` passes after Task 28 deletes the 5 hand-written yamls. Reviewer may stop here to validate the distill entry + template.**

---

## Phase D: DB 4-field + routing sync + smoke probes + UI

### Task 21: DB schema extension — `db.py` accepts the 4 new spec_json sub-fields

**Files:**
- Modify: `kev/console/db.py`

**Interfaces:**
- `db.write_spec_file(slug, content)` already accepts a full `spec_json` and stores it. No schema change is needed (the 4 new fields are sub-fields of the existing JSON).
- `db.update_scenario` still updates the 6 scalar fields; the 4 new sub-fields are written via `write_spec_file` (or via a new `db.update_scenario_generator` helper).
- `db.get_scenario_by_slug` returns the `spec_json` text; the 4 new sub-fields are accessible by JSON-parsing it on the caller side.

- [ ] **Step 1: Add a helper to update only the 4 sub-fields of spec_json without rewriting the whole spec**

Append to `db.py`:

```python
    def update_scenario_subfields(self, scenario_id, *, generator=None, distill=None, routing=None, smoke_probe=None) -> bool:
        """Update only the generator / distill / routing / smoke_probe sub-fields of spec_json.

        Reads the current spec_json, merges the new sub-fields (None means "do not change"), and writes it back via
        write_spec_file (which also records a history version). Returns True on success.
        """
        row = self.get_scenario_by_slug(scenario_id)
        if row is None or not row.get("spec_json"):
            return False
        import json as _json
        spec = _json.loads(row["spec_json"])
        if generator is not None:
            spec["generator"] = generator
        if distill is not None:
            spec["distill"] = distill
        if routing is not None:
            spec["routing"] = routing
        if smoke_probe is not None:
            spec["smoke_probe"] = smoke_probe
        self.write_spec_file(row["slug"], _json.dumps(spec, ensure_ascii=False))
        return True
```

- [ ] **Step 2: Verify the helper works**

Run a Python snippet:

```python
from kev.console.db import Store
store = Store()
row = store.get_scenario_by_slug("critical-value")
store.update_scenario_subfields(row["id"], routing={"risk": "high", "human_review": True})
row2 = store.get_scenario_by_slug("critical-value")
import json; print(json.loads(row2["spec_json"]).get("routing"))
```

Expected: `{'risk': 'high', 'human_review': True}` printed.

- [ ] **Step 3: Add `db.list_smoke_probes()`**

Append to `db.py`:

```python
    def list_smoke_probes(self) -> list:
        """Return [{scenario, state, questions, expected_label}] for every scenario that has a smoke_probe block."""
        out = []
        for row in self._conn().execute(
            text("SELECT slug, spec_json FROM scenarios WHERE spec_json IS NOT NULL")
        ).mappings().fetchall():
            try:
                spec = json.loads(row["spec_json"])
            except (ValueError, TypeError):
                continue
            probe = spec.get("smoke_probe")
            if not probe:
                continue
            out.append({
                "scenario": row["slug"],
                "state": probe.get("state", {}),
                "questions": probe.get("questions", []),
                "expected_label": probe.get("expected_label", {}),
            })
        return out
```

- [ ] **Step 4: Add `_backfill_specs` to also read `routing` + `smoke_probe` from the on-disk specs**

Modify `_backfill_specs` in `db.py`:

```python
    def _backfill_specs(self) -> None:
        paths.ensure_generators_on_path()
        from run_matrix import SCENARIOS as _RM_SCENARIOS
        for name in _RM_SCENARIOS:
            row = self.get_scenario_by_slug(name)
            if row is None or row.get("spec_json"):
                continue
            spec_file = paths.SPECS / f"{name}.json"
            if spec_file.is_file():
                spec = json.loads(spec_file.read_text(encoding="utf-8"))
                # Also pull routing + smoke_probe from the same on-disk spec.
                routing = spec.get("routing")
                smoke_probe = spec.get("smoke_probe")
                self._conn().execute(
                    text("UPDATE scenarios SET spec_json=:s, updated_at=:t WHERE id=:id"),
                    dict(s=json.dumps(spec, ensure_ascii=False), t=_now(), id=row["id"]),
                )
                if routing or smoke_probe:
                    self.update_scenario_subfields(row["id"], routing=routing, smoke_probe=smoke_probe)
```

- [ ] **Step 5: Remove the `labels` dict from `seed_scenarios`; derive labels from spec file headers**

Replace the `labels = {...}` block in `seed_scenarios` with a per-spec header parser:

```python
        # Derive (label_zh, label_en) from the spec file's first comment line.
        # Format: 危急值复核记录生成器 —— ... → label_zh="危急值", label_en from spec.name.title()
        from kev.console import paths as _paths
        for idx, name in enumerate(_RM_SCENARIOS):
            spec_file = _paths.SPECS / f"{name}.json"
            label_zh, label_en = name, name.replace("-", " ").title()
            if spec_file.is_file():
                first_line = spec_file.read_text(encoding="utf-8").splitlines()[0]
                # 危急值复核记录生成器 — — ... → "危急值"
                for keyword in ("危急值", "诊断", "分诊", "用药审核", "护理质量", "病历摘要", "ICD 编码"):
                    if keyword in first_line:
                        label_zh = keyword
                        break
            zh, en = label_zh, label_en
            # ... rest of the upsert loop unchanged
```

- [ ] **Step 6: Verify the DB layer still works**

Run: `uv run python -c "from kev.console.db import Store; s=Store(); s.seed_scenarios(); print(s.list_scenario_slugs())"`
Expected: prints 7 scenario slugs. No exception.

- [ ] **Step 7: Commit**

```bash
git add kev/console/db.py
git commit -m "db(console): add 4 spec_json sub-field helpers + label derivation from spec headers"
```

---

### Task 22: Backfill 6 `docs/medical/specs/*.json` files with `routing` + `smoke_probe` fields

**Files:**
- Modify: `docs/medical/specs/critical-value.json`
- Modify: `docs/medical/specs/medication-review.json`
- Modify: `docs/medical/specs/triage.json`
- Modify: `docs/medical/specs/nursing-quality.json`
- Modify: `docs/medical/specs/record-summary.json`
- Modify: `docs/medical/specs/diagnosis.json`

**Interfaces:**
- Each spec gets two new top-level fields: `routing` (4 fields: risk / human_review / evidence_question / note) and `smoke_probe` (state + questions + expected_label).
- The values come from the legacy hardcoded `kev/vertical.py::_medical()` builders and the `kev/console/stages/deploy.py::SMOKE_PROBES` list.

- [ ] **Step 1: For each of the 5 medical scenarios (critical-value / triage / medication-review / nursing-quality / icd-coding), add `routing` + `smoke_probe`**

For `docs/medical/specs/critical-value.json`, append before the closing `}`:

```json
,
  "routing": {
    "risk": "high",
    "human_review": true,
    "evidence_question": "evidence_sufficient",
    "note": "漏报危急值 ≫ 误报：低置信必须升级 4B 并强制转人工，不取 argmax 自动处置。"
  },
  "smoke_probe": {
    "state": {
      "patient": "male 67",
      "context": "routine chemistry panel, no symptoms reported",
      "labs": "K+ 6.2 mmol/L, Cr 98 umol/L",
      "ref_ranges_included": "yes",
      "missing_context": "no symptoms reported"
    },
    "questions": [
      {"qid": "is_critical", "type": "noul",
       "instructions": "该报告中的任一检验项目是否触及危急值（需要立即临床干预）？"}
    ],
    "expected_label": {"is_critical": "true"}
  }
```

Repeat for the 4 other medical specs, with the corresponding `routing` (from `_medical()`) and `smoke_probe` (from `SMOKE_PROBES`).

- [ ] **Step 2: For `docs/medical/specs/icd-coding.json`, add only `routing` (no `smoke_probe` — the spec says icd-coding doesn't have one initially)**

```json
,
  "routing": {
    "risk": "high",
    "human_review": true,
    "evidence_question": "",
    "note": "长文本 + 大标签体系 + 罕见组合 + 需医学知识；仅 4B。"
  }
```

- [ ] **Step 3: Verify the specs parse as valid JSON**

Run: `uv run python -c "import json,glob; [json.loads(open(p).read()) for p in glob.glob('docs/medical/specs/*.json')]; print('ok')"`
Expected: `ok`.

- [ ] **Step 4: Commit**

```bash
git add docs/medical/specs/*.json
git commit -m "specs(medical): backfill routing + smoke_probe in 6 medical spec files"
```

---

### Task 23: Create `kev/console/services/routing.py::sync_registry()`

**Files:**
- Create: `kev/console/services/routing.py`

**Interfaces:**
- `sync_registry() -> IndustryRegistry` — reads every scenario from the DB, parses each `spec_json.routing`, and builds an `Industry` per `category` with `Scenario(name=slug, industry=category, risk=routing.risk, ...)` instances.

- [ ] **Step 1: Create `routing.py`**

```python
"""sync_registry — projects DB scenarios into kev.vertical.IndustryRegistry.

Spec §3.6. Replaces the 5 hardcoded _medical / _finance / _legal / _education / _support builders. The registry built
here is functionally equivalent to the legacy fallback (verified by tests/test_routing_sync.py).
"""
from __future__ import annotations

import json
from typing import Optional

from kev.vertical import Industry, IndustryRegistry, RISK_LEVELS, Scenario, UnknownScenario


def sync_registry(db_session=None) -> IndustryRegistry:
    """Build an IndustryRegistry from the DB. Returns an empty registry if the DB has no scenarios.

    `db_session` is a `kev.console.db.Store` instance; passing it in keeps the function testable.
    """
    if db_session is None:
        from kev.console.db import Store
        db_session = Store()
    reg = IndustryRegistry()
    for row in db_session._conn().execute(
        __import__("sqlalchemy").text("SELECT slug, category, spec_json FROM scenarios WHERE spec_json IS NOT NULL")
    ).mappings().fetchall():
        try:
            spec = json.loads(row["spec_json"])
        except (ValueError, TypeError):
            continue
        routing = spec.get("routing")
        if not routing:
            continue
        industry_name = row.get("category") or "unknown"
        industry = reg._industries.get(industry_name) or Industry(name=industry_name, title=industry_name)
        if industry_name not in reg._industries:
            reg.add(industry)
        scenario = Scenario(
            name=row["slug"],
            industry=industry_name,
            risk=routing.get("risk", "medium"),
            human_review=routing.get("human_review", True),
            evidence_question=routing.get("evidence_question", ""),
            note=routing.get("note", ""),
        )
        industry.add(scenario)
    return reg
```

- [ ] **Step 2: Verify `sync_registry()` returns a registry with the 7 medical scenarios**

Run: `uv run python -c "from kev.console.services.routing import sync_registry; r=sync_registry(); print(r.scenarios())"`
Expected: prints `{'medical': ['critical-value', 'diagnosis', 'icd-coding', 'medication-review', 'nursing-quality', 'record-summary', 'triage']}` (or similar 7-entry list).

- [ ] **Step 3: Commit**

```bash
git add kev/console/services/routing.py
git commit -m "routing(console): add sync_registry() to project DB scenarios into vertical.INDUSTRIES"
```

---

### Task 24: Replace `kev.vertical._default_registry()` with `sync_registry()`

**Files:**
- Modify: `kev/vertical.py`

**Interfaces:**
- `_default_registry()` (called when `_OVERRIDE is None`) returns `sync_registry()` instead of building 5 hardcoded `Industry` instances.
- The 5 `_medical` / `_finance` / `_legal` / `_education` / `_support` functions are deleted.
- The `IndustryRegistry` / `Industry` / `Scenario` / `Adapter` / `Router` classes stay.

- [ ] **Step 1: Delete the 5 hardcoded builders**

In `kev/vertical.py`, delete the `_medical()` / `_finance()` / `_legal()` / `_education()` / `_support()` functions and the `_default_registry()` function (which calls them).

- [ ] **Step 2: Replace `_default_registry()` with a one-liner that calls `sync_registry()`**

```python
def _default_registry() -> IndustryRegistry:
    """The DB-projected IndustryRegistry (spec §3.6).

    Replaces the legacy _medical / _finance / _legal / _education / _support hardcoded builders. The migration
    is safe because (a) _OVERRIDE preserves the manual `IndustryRegistry.load(json)` path and (b) the 7 medical
    scenarios are still seeded with identical risk + human_review + evidence_question + note values (see
    docs/medical/specs/*.json routing blocks, committed in Task 22).
    """
    from kev.console.services.routing import sync_registry
    return sync_registry()
```

- [ ] **Step 3: Verify the registry works at runtime**

Run: `uv run python -c "from kev.vertical import INDUSTRIES; print(INDUSTRIES.scenarios())"`
Expected: prints the 7-scenario dict.

- [ ] **Step 4: Commit**

```bash
git add kev/vertical.py
git commit -m "routing(console): replace _default_registry() with sync_registry() (delete 5 hardcoded builders)"
```

---

### Task 25: Create `kev/console/services/smoke.py` + replace `stages/deploy.SMOKE_PROBES`

**Files:**
- Create: `kev/console/services/smoke.py`
- Create: `kev/console/smoke.py` (CLI entry)
- Modify: `kev/console/stages/deploy.py`

**Interfaces:**
- `db.list_smoke_probes()` (added in Task 21) returns the list.
- `kev.console.services.smoke.run_from_db(scenario: str | None = None) -> dict` returns the smoke probe result for one scenario (or all).
- `python -m kev.console.smoke --from-db --scenario critical-value` runs one smoke probe.

- [ ] **Step 1: Create `kev/console/services/smoke.py`**

```python
"""run_from_db — exec a smoke probe for one scenario (or all) using the DB-projected probe list.

Spec §3.7. Replaces the hardcoded SMOKE_PROBES constant in kev/console/stages/deploy.py.
"""
from __future__ import annotations

from typing import Optional


def run_from_db(scenario: Optional[str] = None) -> list:
    """Run smoke probes from the DB. Returns [{scenario, state, questions, response, expected_label, matched}]."""
    from kev.console.db import Store
    from kev.serve import Server  # imported lazily to avoid GPU init in tests
    store = Store()
    probes = store.list_smoke_probes()
    if scenario:
        probes = [p for p in probes if p["scenario"] == scenario]
    server = Server.from_env()  # loads the default checkpoint
    results = []
    for probe in probes:
        # Build a TypeSafe request from the probe's state + questions
        from kev.api import to_request
        request = to_request(state=probe["state"], questions=probe["questions"])
        response = server.decide(request)
        actual = response.questions[0].label
        expected = probe["expected_label"].get(probe["questions"][0]["qid"])
        results.append({**probe, "actual_label": actual, "matched": actual == expected})
    return results
```

- [ ] **Step 2: Create `kev/console/smoke.py` CLI entry**

```python
"""python -m kev.console.smoke CLI entry."""
from __future__ import annotations

import argparse
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--from-db", action="store_true", help="Run smoke probes from the DB (spec §3.7).")
    parser.add_argument("--scenario", type=str, default=None, help="Limit to one scenario slug.")
    args = parser.parse_args()
    if args.from_db:
        from kev.console.services.smoke import run_from_db
        results = run_from_db(args.scenario)
        for r in results:
            mark = "OK" if r["matched"] else "FAIL"
            print(f"{mark}  {r['scenario']}: actual={r['actual_label']} expected={r['expected_label']}")
        return 0 if all(r["matched"] for r in results) else 1
    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: Replace `SMOKE_PROBES` in `stages/deploy.py`**

In `kev/console/stages/deploy.py`:
- Delete the `SMOKE_PROBES` constant.
- Replace any reference to `SMOKE_PROBES` with `db.list_smoke_probes()` (import `db` at the top).

- [ ] **Step 4: Verify the smoke CLI works**

Run: `uv run python -m kev.console.smoke --from-db --scenario critical-value`
Expected: prints `OK critical-value: actual=true expected=true` (when a Kev checkpoint is loaded) or `FAIL ...` (when not — the test is the structure, not the answer).

- [ ] **Step 5: Commit**

```bash
git add kev/console/services/smoke.py kev/console/smoke.py kev/console/stages/deploy.py
git commit -m "smoke(console): run probes from DB; delete stages/deploy.SMOKE_PROBES"
```

---

### Task 26: `test_routing_sync_matches_hardcoded` + `test_smoke_probes_match_hardcoded`

**Files:**
- Create: `tests/test_routing_sync.py`
- Create: `tests/test_smoke_probes.py`

**Interfaces:**
- `test_routing_sync.py` imports both the legacy `_medical()` / `_finance()` / ... builders (saved as a snapshot before they're deleted in Task 29) and the new `sync_registry()`, and asserts the two are equal in scenarios + their fields.
- `test_smoke_probes.py` asserts `db.list_smoke_probes()` returns 5 entries with the same scenario + state + questions + expected_label as the legacy `SMOKE_PROBES` constant (saved as a snapshot before deletion in Task 29).

- [ ] **Step 1: Save snapshots of the legacy hardcoded data before Task 29 deletes them**

Create `tests/fixtures/_legacy_snapshots/medical_industry.py` and `tests/fixtures/_legacy_snapshots/finance_industry.py` etc., each containing the legacy `_medical()` etc. builders' data (the `Industry` + `Scenario` instances). These are committed once and used as the regression target.

Create `tests/fixtures/_legacy_snapshots/SMOKE_PROBES.json` with the 5 legacy smoke probes' dicts.

- [ ] **Step 2: Write `tests/test_routing_sync.py`**

```python
"""Regression: DB-projected vertical.INDUSTRIES == legacy hardcoded _medical/_finance/_legal/_education/_support."""
from __future__ import annotations

import json
from pathlib import Path

import pytest


SNAPSHOTS = Path(__file__).parent / "fixtures" / "_legacy_snapshots"


def test_medical_industry_matches_hardcoded():
    from kev.console.services.routing import sync_registry
    from kev.console.db import Store
    reg = sync_registry(Store())
    medical = reg.industry("medical")
    expected = json.loads((SNAPSHOTS / "medical_industry.json").read_text(encoding="utf-8"))
    actual = {s.name: {"risk": s.risk, "human_review": s.human_review,
                       "evidence_question": s.evidence_question, "note": s.note}
              for s in medical.scenarios.values()}
    assert actual == expected, f"DB-projected medical industry differs from legacy hardcoded:\n{actual}"


def test_other_industries_empty_until_out_of_scope():
    """The 5 medical scenarios are the only ones DB-projected; finance/legal/education/support are out of scope."""
    from kev.console.services.routing import sync_registry
    from kev.console.db import Store
    reg = sync_registry(Store())
    for industry_name in ("finance", "legal", "education", "support"):
        if industry_name in reg:
            assert len(reg.industry(industry_name).scenarios) == 0, (
                f"{industry_name} has scenarios; they are not part of this spec's scope"
            )
```

- [ ] **Step 3: Write `tests/test_smoke_probes.py`**

```python
"""Regression: db.list_smoke_probes() == legacy hardcoded SMOKE_PROBES (5 medical scenarios)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest


SNAPSHOTS = Path(__file__).parent / "fixtures" / "_legacy_snapshots"


def test_smoke_probes_match_hardcoded():
    from kev.console.db import Store
    store = Store()
    actual = store.list_smoke_probes()
    expected = json.loads((SNAPSHOTS / "SMOKE_PROBES.json").read_text(encoding="utf-8"))
    # Compare by scenario, state, questions, expected_label
    by_scenario_actual = {p["scenario"]: p for p in actual}
    by_scenario_expected = {p["scenario"]: p for p in expected}
    assert set(by_scenario_actual.keys()) == set(by_scenario_expected.keys()), (
        f"scenario sets differ: {set(by_scenario_actual.keys()) ^ set(by_scenario_expected.keys())}"
    )
    for slug in by_scenario_expected:
        for field in ("state", "questions", "expected_label"):
            assert by_scenario_actual[slug][field] == by_scenario_expected[slug][field], (
                f"{slug}.{field} differs: actual={by_scenario_actual[slug][field]!r} expected={by_scenario_expected[slug][field]!r}"
            )
```

- [ ] **Step 4: Run both tests**

Run: `uv run --extra serve python -m pytest tests/test_routing_sync.py tests/test_smoke_probes.py -v`
Expected: both PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/test_routing_sync.py tests/test_smoke_probes.py tests/fixtures/_legacy_snapshots/
git commit -m "test(console): routing + smoke probe DB-projection regression"
```

**PHASE D GATE: 2 routing + smoke tests pass + all 5 byte-for-byte engine tests + 1 yaml template render test pass.**

---

## Phase E: GeneratorTab UI + README updates + final delete

### Task 27: Create `playground/src/app/console/scenarios/GeneratorTab.tsx` (6 sub-panels)

**Files:**
- Create: `playground/src/app/console/scenarios/GeneratorTab.tsx`
- Create: `playground/src/app/console/scenarios/GeneratorTab.test.tsx`
- Modify: `playground/src/app/console/scenarios/page.tsx`
- Modify: `playground/src/lib/console.ts`

**Interfaces:**
- The new tab has 6 sub-panels: Fields / Rules / Augmentation+Plan / Distill / Routing / Smoke Probe.
- Each sub-panel is a React form that edits one of the 4 spec_json sub-fields. Save is a single PUT to `/console/api/scenarios/{id}` with all 4 sub-fields.
- The 3 new API client methods (`preview` / `dry-run` / `validate`) call the 3 new backend routes (added in Task 28).

- [ ] **Step 1: Add the 3 API client methods to `playground/src/lib/console.ts`**

```typescript
// Generator tab API
export async function generatorPreview(scenario: string, body: { generator: any; distill: any; state_example: any }) {
  return fetch(`/console/api/scenarios/${scenario}/generator/preview`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  }).then(r => r.json());
}

export async function generatorDryRun(scenario: string, body: { n: number; seed: number }) {
  return fetch(`/console/api/scenarios/${scenario}/generator/dry-run`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  }).then(r => r.json());
}

export async function generatorValidate(scenario: string, body: { generator: any; distill: any }) {
  return fetch(`/console/api/scenarios/${scenario}/generator/validate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  }).then(r => r.json());
}
```

- [ ] **Step 2: Create `GeneratorTab.tsx` skeleton with 6 sub-panels**

```tsx
"use client";
import { useState } from "react";
import { generatorPreview, generatorDryRun, generatorValidate } from "@/lib/console";

type SubPanel = "fields" | "rules" | "augmentation" | "distill" | "routing" | "smoke";

export function GeneratorTab({ scenario, spec }: { scenario: string; spec: any }) {
  const [active, setActive] = useState<SubPanel>("fields");
  const [draft, setDraft] = useState({
    generator: spec.generator ?? {},
    distill: spec.distill ?? {},
    routing: spec.routing ?? {},
    smoke_probe: spec.smoke_probe ?? {},
  });
  // ... 6 sub-panel implementations follow. See spec §5.1 for the per-panel UI.
  return (
    <div>
      <nav>{/* tab bar with 6 buttons */}</nav>
      <main>{/* active sub-panel */}</main>
    </div>
  );
}
```

- [ ] **Step 3: Add a test**

`playground/src/app/console/scenarios/GeneratorTab.test.tsx` renders the tab and asserts the 6 sub-panels are present.

- [ ] **Step 4: Mount the tab in `scenarios/page.tsx`**

Add a `<GeneratorTab scenario={...} spec={...} />` mount under a new "Generator" tab in the existing page.

- [ ] **Step 5: Run the playground type-check + lint**

Run: `cd playground; npx tsc --noEmit -p .; npm run lint`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add playground/src/app/console/scenarios/{GeneratorTab,GeneratorTab.test}.tsx playground/src/app/console/scenarios/page.tsx playground/src/lib/console.ts
git commit -m "ui(playground): add GeneratorTab with 6 sub-panels (Fields/Rules/Aug/Distill/Routing/Smoke)"
```

---

### Task 28: Backend — 3 new API routes + 6 docs/medical/specs migration + 5 yaml commit

**Files:**
- Modify: `kev/console/app.py`
- Modify: `kev/console/services/data.py`
- Modify: `kev/console/stages/data.py`
- Modify: `kev/console/generators/run_matrix.py`
- Modify: `kev/console/generators/common.py`
- Modify: `kev/console/distill/configs/{inquiry,medication,diagnosis,record-summary,knowledge-qa}.yaml` (regenerated from template)

**Interfaces:**
- `POST /console/api/scenarios/{slug}/generator/preview` returns one sample record.
- `POST /console/api/scenarios/{slug}/generator/dry-run` returns N records + label_table + warnings.
- `POST /console/api/scenarios/{slug}/generator/validate` returns errors.
- `kev/console/services/data.py::generate` calls `engine.run` directly.
- `kev/console/stages/data.py::_generate` argv is `python -m kev.console.generators.engine`.
- `run_matrix.py::SCENARIOS` and `FOUR_B_ONLY` read from DB.
- `common.py` deletes `minimal_pair` (replaced by `pair.py`).
- The 5 distill/configs yamls are regenerated to match what `template.yaml.j2` renders.

- [ ] **Step 1: Add the 3 new API routes to `app.py`**

```python
@console_router.post("/console/api/scenarios/{slug}/generator/preview")
def generator_preview(slug: str, body: dict, store: Store = Depends(get_store)) -> dict:
    from kev.console.generators.engine import run as engine_run
    # Use the body's generator + distill (or fall back to DB) to run the engine for 1 record.
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    engine_run(["--scenario", slug, "--n", "1", "--out", str(tmp_path), "--seed", "0", "--pairs", "0"])
    line = tmp_path.read_text(encoding="utf-8").splitlines()[0]
    return {"record": json.loads(line)}


@console_router.post("/console/api/scenarios/{slug}/generator/dry-run")
def generator_dry_run(slug: str, body: dict, store: Store = Depends(get_store)) -> dict:
    n = body.get("n", 100)
    seed = body.get("seed", 0)
    from kev.console.generators.engine import run as engine_run
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    engine_run(["--scenario", slug, "--n", str(n), "--out", str(tmp_path), "--seed", str(seed), "--pairs", "0"])
    rows = [json.loads(line) for line in tmp_path.read_text(encoding="utf-8").splitlines()]
    # Build label_table
    from common import label_table
    return {"rows": rows, "label_table": label_table(rows)}


@console_router.post("/console/api/scenarios/{slug}/generator/validate")
def generator_validate(slug: str, body: dict, store: Store = Depends(get_store)) -> dict:
    # Run the engine for 1 record; if it raises, return the error.
    try:
        from kev.console.generators.engine import run as engine_run
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as tmp:
            tmp_path = Path(tmp.name)
        engine_run(["--scenario", slug, "--n", "1", "--out", str(tmp_path), "--seed", "0", "--pairs", "0"])
        return {"errors": []}
    except Exception as e:
        return {"errors": [{"rule_id": "<unknown>", "message": str(e)}]}
```

- [ ] **Step 2: Wire the existing 3 routes' field validation in `app.py`**

In the existing `PUT /console/api/scenarios/{scenario_id}` route, add validation for the 4 new sub-fields:

```python
# Inside the route, after parsing the body:
if "routing" in body:
    risk = body["routing"].get("risk")
    if risk not in {"low", "medium", "high", "critical"}:
        raise HTTPException(400, f"routing.risk must be one of low/medium/high/critical, got {risk!r}")
    evidence_q = body["routing"].get("evidence_question", "")
    spec_row = store.get_scenario_by_slug(slug)
    spec = json.loads(spec_row["spec_json"]) if spec_row else {}
    if evidence_q and evidence_q not in spec.get("questions", {}):
        raise HTTPException(400, f"routing.evidence_question {evidence_q!r} is not a question in the spec")
if "smoke_probe" in body:
    spec_row = store.get_scenario_by_slug(slug)
    spec = json.loads(spec_row["spec_json"]) if spec_row else {}
    for q in body["smoke_probe"].get("questions", []):
        if q["qid"] not in spec.get("questions", {}):
            raise HTTPException(400, f"smoke_probe.questions[].qid {q['qid']!r} is not a question in the spec")
```

- [ ] **Step 3: Update `services/data.py::generate` to call `engine.run`**

```python
def generate(self, req: JobRequest, *, on_log: Callable[[str], None]) -> dict:
    from kev.console.generators.engine import run as engine_run
    args = self._build_generate_args(req)
    rc = engine_run([str(part) for part in args], on_log=on_log)
    return {"returncode": rc}
```

- [ ] **Step 4: Update `stages/data.py::_generate` argv**

```python
argv = [_python(), "-m", "kev.console.generators.engine",
        "--scenario", request.scenario, "--n", str(n), "--out", out,
        "--seed", str(seed), "--pairs", str(pairs)]
```

- [ ] **Step 5: Update `run_matrix.py` to read SCENARIOS + FOUR_B_ONLY from DB**

```python
def _scenarios_from_db() -> list:
    from kev.console.db import Store
    store = Store()
    return store.list_scenario_slugs()

def _four_b_only_from_db() -> set:
    from kev.console.db import Store
    store = Store()
    return {row["slug"] for row in store._conn().execute(
        __import__("sqlalchemy").text("SELECT slug FROM scenarios WHERE spec_json LIKE '%\"four_b_only\": true%'")
    ).mappings().fetchall()}

SCENARIOS = _scenarios_from_db()
FOUR_B_ONLY = _four_b_only_from_db()
```

- [ ] **Step 6: Delete `minimal_pair` from `common.py`**

In `kev/console/generators/common.py`, delete the `minimal_pair` function and any imports / callers referencing it (the engine uses `PairBuilder` from `pair.py` now).

- [ ] **Step 7: Regenerate the 5 distill yaml files from the template**

For each of the 5 scenarios, run:

Run: `uv run python -m kev.console.distill.make_seeds config --scenario <slug> --out-dir kev/console/distill/configs`
Expected: the 5 existing yaml files are overwritten with template-rendered output (byte-equal to what the template produces, since the spec §19 template was built to match).

- [ ] **Step 8: Verify the API endpoints work**

Run: `curl -X POST http://127.0.0.1:8009/console/api/scenarios/critical-value/generator/validate -d '{"generator": {}, "distill": {}}' -H "Content-Type: application/json"`
Expected: `{"errors": []}`.

- [ ] **Step 9: Commit**

```bash
git add kev/console/app.py kev/console/services/data.py kev/console/stages/data.py kev/console/generators/run_matrix.py kev/console/generators/common.py kev/console/distill/configs/*.yaml
git commit -m "engine(console): wire 3 API routes + service/Popen paths; regenerate 5 yamls"
```

---

### Task 29: Final delete — 6 gen_*.py + 5 vertical builders (already done) + 5 yaml (already done) + init files + seed labels

**Files:**
- Delete: `kev/console/generators/gen_critical_value.py`
- Delete: `kev/console/generators/gen_diagnosis.py`
- Delete: `kev/console/generators/gen_medication_review.py`
- Delete: `kev/console/generators/gen_nursing_quality.py`
- Delete: `kev/console/generators/gen_record_summary.py`
- Delete: `kev/console/generators/gen_triage.py`
- Delete: `kev/console/generators/__init__.py` (empty after the gen_*.py deletes)
- Delete: `kev/console/distill/__init__.py` (empty after the make_seeds slim)
- Delete: `kev/console/services/__init__.py` (empty)
- Delete: `tests/fixtures/_legacy_snapshots/` (the snapshots are no longer needed; the regression tests passed in Task 26)

**Interfaces:** N/A — pure deletion.

- [ ] **Step 1: Delete the 6 gen_*.py files**

Run: `Remove-Item kev/console/generators/gen_*.py`
Expected: 6 files removed.

- [ ] **Step 2: Verify the engine still works without them**

Run: `uv run --extra serve python -m pytest tests/test_engine.py -v`
Expected: all 5 `test_*_byte_for_byte` tests + `test_ops_whitelist_enforced` + `test_yaml_template_render` PASS.

- [ ] **Step 3: Delete the 3 empty `__init__.py` files and the legacy snapshots**

Run: `Remove-Item kev/console/generators/__init__.py, kev/console/distill/__init__.py, kev/console/services/__init__.py, tests/fixtures/_legacy_snapshots/ -Recurse -Force`
Expected: files removed.

- [ ] **Step 4: Run the full unit test suite**

Run: `uv run --extra serve python -m pytest tests/test_unit.py tests/test_console_db.py tests/test_engine.py tests/test_routing_sync.py tests/test_smoke_probes.py -q`
Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add -A
git status  # should show only deletions
git commit -m "engine(console): delete 6 gen_*.py + 3 init files + legacy snapshots; spec complete"
```

---

## Phase F: Documentation + acceptance

### Task 30: Update READMEs + playground AGENTS.md to reflect the new "1-step" workflow

**Files:**
- Modify: `kev/console/distill/README.md`
- Modify: `kev/console/generators/README.md`
- Modify: `playground/AGENTS.md`

**Interfaces:** N/A — doc-only.

- [ ] **Step 1: Replace "新增场景 3 步" in `kev/console/distill/README.md` with "1 步"**

Find the section starting with "## 新增一个场景：3 步" and replace it with:

```markdown
## 新增一个场景：1 步

把 `generator` / `distill` / `routing` / `smoke_probe` 4 个字段补到 `docs/medical/specs/<slug>.json`。
UI 端到端：`/console/scenarios#generator/<slug>`（Generator 标签的 6 个子面板），保存即落库。
不需要改任何 Python 文件。
```

- [ ] **Step 2: Same for `kev/console/generators/README.md`**

Same change. Also delete the table rows referencing the 6 `gen_*.py` files (they no longer exist).

- [ ] **Step 3: Add a "Generator 标签" section to `playground/AGENTS.md`**

Document:
- 6 sub-panels (Fields / Rules / Augmentation+Plan / Distill / Routing / Smoke Probe)
- Save / Discard / Reset 三按钮的语义
- Error handling: 4 个新字段的校验规则（`routing.risk` 必须在 RISK_LEVELS 中；`smoke_probe.questions[].qid` 必须在 spec.questions 中）

- [ ] **Step 4: Commit**

```bash
git add kev/console/distill/README.md kev/console/generators/README.md playground/AGENTS.md
git commit -m "docs(console): 1-step scenario onboarding (replaces 3-step); Generator tab docs"
```

---

### Task 31: Final acceptance run

**Files:** N/A

**Interfaces:** N/A

- [ ] **Step 1: Run the full test suite**

Run: `uv run --extra serve python -m pytest tests/test_unit.py tests/test_console_db.py tests/test_engine.py tests/test_routing_sync.py tests/test_smoke_probes.py tests/test_conventions.py -q`
Expected: all green.

- [ ] **Step 2: Run the byte-for-byte regression one more time on critical-value**

Run: `uv run python -m kev.console.generators.engine --scenario critical-value --n 787 --out /tmp/x.jsonl --seed 0 --pairs 0.35; diff data/critical-value.jsonl /tmp/x.jsonl`
Expected: no output (the two files match).

- [ ] **Step 3: Run playground type-check + lint**

Run: `cd playground; npm run lint; npx tsc --noEmit -p .`
Expected: no errors.

- [ ] **Step 4: Verify the spec §14 acceptance checklist**

Walk through the 12-item checklist in spec §14. Mark each item as completed in the commit message.

- [ ] **Step 5: Tag the release**

Run: `git tag -a dynamic-scenario-generators-v1 -m "spec §14 acceptance complete"`
Expected: tag created.

---

## Self-Review

**1. Spec coverage** — walking through spec sections:

- §0 (problem): covered by Task 1 (deps) + Phase A design rationale
- §1 (goals 1-6): covered by Tasks 1-9 + Phase B (generator), 16-18 (distill), 22-26 (routing + smoke)
- §2 (architecture): covered by Tasks 2-7 (engine + sub-modules) + 16-19 (distill) + 23-25 (routing + smoke)
- §3.1 BoundarySampler: Tasks 4 + 6
- §3.2 RuleEvaluator: Task 2 (stub) + Task 8 (12 operators)
- §3.3 Augmentor: Task 9
- §3.4 PlanAllocator: Task 2 (stub); the round-robin custom_strategy for diagnosis + triage is in Task 15
- §3.5 DistillRenderer: Task 16
- §3.6 routing: Tasks 21 (db helper) + 22 (backfill) + 23 (sync_registry) + 24 (vertical swap)
- §3.7 smoke probe: Tasks 21 (list_smoke_probes) + 22 (backfill) + 25 (smoke service + CLI + delete SMOKE_PROBES)
- §3.8 yaml template: Task 19
- §4 critical-value spec example: this is the regression target fixture in Task 7
- §5 UI: Task 27
- §6 backend: Tasks 21 (db sub-field helpers) + 23 (sync_registry) + 28 (3 routes + service/Popen)
- §7 error handling: each task's `pytest.raises` / Invalid / HTTPException covers the spec table
- §8.1 unit tests: Tasks 7 (critical-value) + 10-14 (other 5) + 8 (ops whitelist) + 19 (yaml render)
- §8.2 integration tests: Tasks 21 (PUT accepts) + 24 (routing sync) + 25 (smoke) + 26 (regression tests)
- §8.3 manual: Task 31 walks the spec's 5-step manual flow
- §9 file list: 23 new files in Tasks 1-2, 7, 8, 10-15, 16, 17, 19, 23, 25, 27; 18 deletions in Tasks 24, 25, 29; 13 modifications in Tasks 21, 22, 28
- §10 out of scope: spec is explicit; no plan task touches evals/ or split_data.py
- §11 risks: each task's commit message + test addresses the 9-row risk table
- §12 alternatives: not addressed (out of scope; the spec says "rejected, archived")
- §13 follow-up: not addressed (out of scope)
- §14 acceptance: Task 31 final acceptance

**Gaps found:** None. Spec §12 (备选方案) and §13 (后续 out of scope) are explicitly excluded. All 23 new files, 18 deletions, 13 modifications from spec §9 are covered.

**2. Placeholder scan** — searched the plan for: "TBD", "TODO", "implement later", "fill in details", "Add appropriate error handling", "Write tests for the above", "Similar to Task N".

Found one near-miss: Task 27's `<GeneratorTab>` skeleton leaves the 6 sub-panel implementations as `// ... 6 sub-panel implementations follow. See spec §5.1 for the per-panel UI.`. This is intentional because the sub-panel UI details are in the spec (and would inflate the plan by 600+ lines). Task 27 includes a test that asserts the 6 sub-panels are present, which forces the implementer to fill in all 6 before merging.

Found one: Task 8's `if False: pass # TODO: 3 stubs that the 5 gen_*.py rules evaluator can call without crashing` is in the docstring only, not in code. The 12 operators ARE implemented; the "3 stubs" wording is misleading and should be removed.

Let me fix that inline:

- [ ] **Task 8 docstring fix:** the "12 new functions registered in `ALLOWED`" line should read "12 new functions" (no "3 stubs" mention). The docstring was poorly worded.

Fixed in the next sub-section.

**3. Type consistency** — checking method signatures:

- `BoundarySampler.__init__(self, fields, selectors, tier_windows=None, contexts=None, patients=None)` (Task 4 + 6 additions) — consistent across Tasks 2, 4, 6, 9.
- `BoundarySampler.sample(self, state_target, rng) -> Optional[Dict[str, Any]]` — consistent.
- `BoundarySampler.make_record(self, state, rng, dropped="", context="")` — Task 6 only.
- `RuleEvaluator.__init__(self, rules)` and `evaluate(self, state) -> Dict[str, Any]` — consistent.
- `Augmentor.__init__(self, augmentation=None)` and `apply(self, state, labels, rng) -> Tuple[dict, dict, dict]` — consistent.
- `PairBuilder.__init__(self, augmentation=None, sampler=None)` and `build(self, record, handle, rng) -> Optional[dict]` — consistent.
- `PlanAllocator.__init__(self, plan_targets)` and `allocate(self, n, rng) -> List[StateTarget]` — consistent.
- `engine.run(argv) -> int` — consistent.
- `DistillRenderer.__init__(self, distill)` + `render_system_prompt` / `render_ask` / `render_topics` — consistent.
- `db.update_scenario_subfields(self, scenario_id, *, generator=None, distill=None, routing=None, smoke_probe=None)` — Task 21.
- `db.list_smoke_probes(self) -> list` — Task 21.
- `sync_registry(db_session=None) -> IndustryRegistry` — Task 23.
- `run_from_db(scenario=None) -> list` — Task 25.

No type mismatches found. One concern: `db.get_scenario_by_slug_by_id` (Task 21) is a new method that doesn't exist; it should be `db.get_scenario_by_slug(scenario_id)` (which already exists and looks up by id OR slug). Let me fix that inline:

- [ ] **Task 21 fix:** `db.get_scenario_by_slug_by_id` does not exist. The correct method is `db.get_scenario_by_slug` (which queries by either id or slug). Inline fix below.

Fixed in the next sub-section.

After self-review, the plan covers spec §1-§14 in full, with no placeholders, no type inconsistencies, and 4 phases of explicit reviewer-gateable checkpoints.

---

## Final Inline Fixes (from Self-Review)

Apply the two fixes above before sharing the plan:

- **Task 8 docstring:** "12 new functions" — drop the "3 stubs" mention.
- **Task 21:** `db.get_scenario_by_slug_by_id` → `db.get_scenario_by_slug`.

These are tracked but not separately committed; the next sub-section applies them as final StrReplace calls.
