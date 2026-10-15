"""The spec-driven engine on scenarios that are not medical (tests/fixtures/engine-matrix, design doc D1/D2/D5/D6/D7/D8/D10/D11/D12/D13/D15).

What this file guards is the B2 premise the spike measured: 20 of the 32 finance / education / research / legal
scenarios died inside the sampler (`ops.normal_value` read `field["normal"]` for every field, whatever its type — F1),
and the ones that survived came out shaped like a lab report because `make_record` hardcoded `patient` / `labs` (F2).
Both are engine defects, not domain ones, so the guard is a matrix of 38 scenarios rather than a medical test with a
new name: 32 the spike ran, four `catalog` ones PR1b added (a spike cannot have measured a field type the engine
refused to sample), and two PR3 added the other way round — written only as JSON, to prove a new industry needs no
Python (gate G4). `resolve_spec` (D7) is here too: three spec truth sources meant a preview showed the committed copy
of what the user had just edited, and a scenario that lived only in the DB raised FileNotFoundError.

PR1b's half of the file is the derive channel (D10/D11) and gate G8: a catalog field's candidates carry the label in
their own attributes, so the guard is that neither those attribute names nor a `choice` label's code ever reach
`render(state)`. A state that shows `urgency: 2` or `owning_team: infra` does not train a decision, it trains a copy.

What this file does NOT claim: that every scenario's labels are right. PR2 taught the evaluator typed values, date
arithmetic, generator expressions and the difference between "this record lacks the evidence" and "this spec is
unusable" (design doc F3/F4, §5.4/§5.5), and the ledger fell from twelve questions to two. PR3 paid those two by
letting a spec ask for an answer by name (`plan_targets.by_label`) and making the engine draw until the spec's own
rules agree (design doc D5), so `LEDGER` is empty and every question of every scenario moves. What is left is a
different debt, counted in answers rather than in engine failures: at n = 120, 51 declared answers are never produced,
14 more sit under the 5 % floor, and 13 scenarios let a catch-all rule answer most of their records. Those are
`NEVER_LABELLED`, `UNDER_FLOOR` and `CATCH_ALL` below, and they are spec-authoring work — `engine.run` exits non-zero
only where a spec declares a `floor`, because switching the gate on for a scenario whose rule was never written would
red CI on its history rather than on a regression.

Run: uv run python -m pytest tests/test_engine_matrix.py -q. Gate G2's n = 3,000 row (~42 s for the three floored
scenarios, 16.2 + 14.3 + 11.9) is the nightly half of the design doc's cost line, so it runs under `KEV_MATRIX_FULL=1`;
the PR CI rows are n = 30 and n = 300.
"""
import contextlib
import io
import json
import os
import random
import re
from collections import Counter
from datetime import date
from pathlib import Path

import pytest
from simpleeval import SimpleEval

from kev.api import render
from kev.console import paths
from kev.console.generators import common, derive, engine, ops, rules, values
from kev.console.generators.pair import PairBuilder, fact_keys
from kev.console.generators.plan import LabelTarget, PlanAllocator, PlanError
from kev.console.generators.sampler import BoundarySampler, place

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests/fixtures/engine-matrix"
SIDECAR = json.loads((FIXTURES / "matrix.json").read_text(encoding="utf-8"))
SLUGS = [entry["slug"] for entry in SIDECAR]
SHAPES = {entry["slug"]: entry["shape"] for entry in SIDECAR}
CRASHED_IN_SPIKE = {entry["slug"] for entry in SIDECAR if entry["spike_error"]}
CATALOG_SLUGS = [entry["slug"] for entry in SIDECAR if entry["shape"] == "catalog"]
PR3_SLUGS = [entry["slug"] for entry in SIDECAR if entry.get("added") == "PR3"]

# Questions whose label is still single-valued, and why. Equality, not a subset: a scenario that collapses again
# fails here, and a scenario whose debt is paid must be moved to one of the PAID maps below rather than quietly
# deleted from a list someone maintains by hand.
#
# PR2a paid seven of the twelve PR1a left (design doc §5.3) — a typed number, a date the rules can subtract, and six
# specs that compared a measurement against its own unit string. PR2b's evaluator paid four more (§5.5): the generator
# expressions `SimpleEval` refused outright and the records that lack a field a rule reads, which used to fall through
# to the `when: "True"` rule instead of being recognised as "no evidence, no label". PR3 paid the last two (§5.6): the
# spec can now name the answer it wants in `plan_targets.by_label` and the engine draws until the spec's own rules give
# it, which is what turned `edu-essay-scoring`'s `final_band` from a threshold its sampler almost never reached (design
# doc §6, defect 8) into a planned share, and gave the scenario a rule that can raise `plagiarism_flag` at all.
LEDGER: dict = {}

# Out of the ledger at PR2a, spelled per question so a regression that collapses one of them again is a failure here
# and not a silent re-enlargement of LEDGER above.
PAID_BY_PR2A = {
    "fin-default-score": ["grade", "warn"],
    "fin-option-expiry": ["action", "must_act"],
    "fin-covenant-text": ["breach", "remedy"],
    "edu-enrollment-deadline": ["action", "at_risk"],
    "sci-reaction-yield": ["grade", "optimize"],
    "law-overtime-compliance": ["compliant", "gap_band"],
    "law-statute-limitations": ["time_barred"],
}

# Out of the ledger at PR2b for the same reason and with the same guard.
PAID_BY_PR2B = {
    "fin-portfolio-rebalance": ["first_move", "rebalance"],
    "edu-knowledge-mastery": ["remedial", "target"],
    "sci-material-composition": ["next_step", "stable"],
    "law-patent-claims": ["action", "novel"],
}

# Out of the ledger at PR3 — the two questions PR2 left, both paid by a plan that asks for the joint answer rather than
# for one question's share. A conjunction is the only shape that works: a target naming `final_band` alone leaves
# `plagiarism_flag` to the natural distribution, which spread 10pp between n = 30 and n = 3,000 (design doc D5, G2).
PAID_BY_PR3 = {
    "edu-essay-scoring": ["final_band", "plagiarism_flag"],
}

# ---------------------------------------------------------------- G1's other half, as debt (design doc §4, G1)
#
# The gate has two halves, and only one of them is about the engine. `test_g1_...` pins the structural one: all 38
# scenarios ship exactly n records that `check_record` accepts. The distribution one — every declared answer at >= 5 %,
# no catch-all rule carrying the file — is spec authoring, and the matrix is 27 spike specs whose `then` blocks were
# written before anyone could express a gap. So it is an equality ledger, read out of the gate's own stderr at n = 120
# seed 0: each entry may only shrink, and a scenario that loses an answer it used to have fails here rather than shipping
# quieter data. `GATE_CLEAN` is the other side of the same coin — the 10 scenarios with nothing to report, and the
# reason the gate can be switched on scenario by scenario instead of all at once.
#
# Why `engine.run` still exits 0 on the other 28: strictness is exactly where a spec declares `plan_targets.floor`
# (design doc §3's exit row). Turning the 51 answers below into failures today would red CI on the spike's history,
# which is a different claim from "this run regressed".
NEVER_LABELLED = {
    "fin-credit-limit": {"driver": ["duration", "risk"], "limit_band": ["2"]},
    "fin-fraud-flags": {"action": ["verify"]},
    "fin-aml-sar": {"driver": ["duration", "network", "size"], "urgency": ["2"]},
    "fin-insurance-denial": {"reason": ["nature", "timeliness"]},
    "fin-default-score": {"grade": ["0", "2"]},
    "fin-option-expiry": {"action": ["exercise", "roll"]},
    "fin-portfolio-rebalance": {"first_move": ["cost", "liquidity", "risk"]},
    "fin-covenant-text": {"remedy": ["repricing", "waiver"]},
    "edu-early-warning": {"driver": ["engagement", "trend"], "urgency": ["2"]},
    "edu-course-placement": {"placement": ["audit"]},
    "edu-scholarship": {"tier": ["2"]},
    "edu-enrollment-deadline": {"action": ["defer", "hold"]},
    "edu-knowledge-mastery": {"target": ["coverage", "retention"]},
    "edu-statement-fit": {"decision": ["wait"]},
    "sci-gw-candidate": {"confidence": ["2"], "driver": ["astro"]},
    "sci-variant-pathogenicity": {"acmg_class": ["likely", "likely_benign"]},
    "sci-reaction-yield": {"grade": ["0", "3"]},
    "sci-reproducibility": {"action": ["partial"]},
    "sci-power-analysis": {"action_band": ["2"], "driver": ["attrition", "noise"]},
    "sci-target-visibility": {"action": ["fallback"]},
    "sci-review-accept": {"recommendation": ["accept"]},
    "law-sentencing": {"band": ["2"], "driver": ["harm", "history"]},
    "law-jurisdiction-venue": {"venue": ["court_other"]},
    "law-contract-breach": {"remedy": ["cure", "penalty"]},
    "law-overtime-compliance": {"gap_band": ["1", "3"]},
    "law-comparative-negligence": {"driver": ["aggravation"], "share": ["2"]},
}

# Declared, reachable, and thinner than the floor at n = 120: the rule exists, the sampler almost never satisfies it.
# This is what `by_label` is for, and none of these eight specs asks for it yet.
UNDER_FLOOR = {
    "fin-covenant-text": {"breach": ["true"], "remedy": ["accelerate"]},
    "edu-enrollment-deadline": {"action": ["escalate"], "at_risk": ["true"]},
    "sci-variant-pathogenicity": {"acmg_class": ["pathogenic"], "report_to_clinician": ["true"]},
    "sci-reaction-yield": {"grade": ["2"], "optimize": ["false"]},
    "sci-power-analysis": {"driver": ["design"]},
    "sci-material-composition": {"next_step": ["synthesize"], "stable": ["true"]},
    "law-statute-limitations": {"action": ["defense"], "time_barred": ["true"]},
    "law-comparative-negligence": {"driver": ["coverage"]},
}

# Share of the run answered by the rule that asks nothing (`when: "True"`), capped at 0.6 by the gate.
CATCH_ALL = {
    "edu-enrollment-deadline": 0.97,
    "edu-statement-fit": 0.80,
    "fin-covenant-text": 0.98,
    "fin-default-score": 0.88,
    "fin-fraud-flags": 0.83,
    "fin-option-expiry": 0.79,
    "law-contract-breach": 0.66,
    "law-overtime-compliance": 0.84,
    "sci-reaction-yield": 0.99,
    "sci-reproducibility": 0.66,
    "sci-review-accept": 0.75,
    "sci-target-visibility": 0.91,
    "sci-variant-pathogenicity": 0.82,
}
GATE_CLEAN = [
    "edu-essay-scoring", "edu-academic-integrity", "edu-unit-remediation", "fin-credit-adverse",
    "law-evidence-admissibility", "law-evidence-weight", "law-patent-claims", "sci-incident-triage",
    "law-appeal-window", "edu-late-work-escalation",
]


@pytest.fixture(autouse=True)
def _specs_come_from_the_matrix(monkeypatch):
    """Every test in this file resolves specs from the fixture directory, never from a local DB projection."""
    monkeypatch.setenv("KEV_ENGINE_SPEC_DIR", str(FIXTURES))


def generate(slug, tmp_path, n=40, seed=0, pairs=0.0):
    """Run the real engine CLI path and read back what it wrote."""
    out = tmp_path / f"{slug}.jsonl"
    assert engine.run(["--scenario", slug, "--n", str(n), "--seed", str(seed),
                       "--pairs", str(pairs), "--out", str(out)]) == 0
    return [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]


def gate_run(slug, out, n, seed=0, pairs=0.0, gate=None):
    """The same CLI path, and everything it has to say about the file: `(exit code, records, stderr lines)`.

    The gate's messages are read off stderr rather than recomputed here because they are the product — what `--gate`,
    the console's validate route and CI all look at — so a test that re-derived the shares from the records would stay
    green while the engine reported nothing at all.
    """
    argv = ["--scenario", slug, "--n", str(n), "--seed", str(seed), "--pairs", str(pairs), "--out", str(out)]
    if gate:
        argv += ["--gate", gate]
    errors = io.StringIO()
    with contextlib.redirect_stderr(errors), contextlib.redirect_stdout(io.StringIO()):
        code = engine.run(argv)
    records = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()] if out.exists() else []
    return code, records, [line.strip() for line in errors.getvalue().splitlines() if line.strip()]


NEVER_RE = re.compile(r"^(?P<qid>\S+?):(?P<key>\S+) is never labelled")
UNDER_RE = re.compile(r"^(?P<qid>\S+?):(?P<key>\S+) has (?P<have>\d+) of (?P<total>\d+) records")
CATCH_RE = re.compile(r"^(?P<share>\d+)% of records")


def gate_debt(messages):
    """One run's gate lines as `(never-labelled, under-floor, catch-all share)` — `{question: [answer, ...]}` both ways."""
    never: dict = {}
    under: dict = {}
    catch = None
    for line in messages:
        if not line.startswith("engine: gate "):
            continue
        message = line.split(": ", 2)[-1]
        for pattern, into in ((NEVER_RE, never), (UNDER_RE, under)):
            if (found := pattern.match(message)):
                keys = into.setdefault(found["qid"], set())
                keys.add(found["key"])
                break
        else:
            if found := CATCH_RE.match(message):
                catch = int(found["share"]) / 100
    return ({qid: sorted(keys) for qid, keys in sorted(never.items())},
            {qid: sorted(keys) for qid, keys in sorted(under.items())}, catch)


def shares_of(records):
    """Per question, the share of the file each answer holds — gate G2's quantity."""
    total = len(records)
    return {qid: {str(key): count / total for key, count in sorted(counter.items())}
            for qid, counter in sorted(common.label_table(records).items())}


def spec_of(slug):
    return json.loads((FIXTURES / f"{slug}.json").read_text(encoding="utf-8"))


def fields_of(slug):
    return spec_of(slug)["generator"]["fields"]


def catalog_fields_of(slug):
    return [field for field in fields_of(slug) if values.field_type(field) == "catalog"]


# The scenarios that declare the exit gate's threshold, so they are the ones a gap can fail a run on.
FLOORED_SLUGS = [slug for slug in SLUGS if "floor" in (spec_of(slug)["generator"].get("plan_targets") or {})]


# ---------------------------------------------------------------- fixtures (D14)


def test_the_matrix_covers_every_shape_and_keeps_the_spike_record():
    assert len(SLUGS) == 38 and len(set(SLUGS)) == 38
    assert len(CRASHED_IN_SPIKE) == 20, "the sidecar lost which scenarios the spike saw die"
    for entry in SIDECAR:
        assert (FIXTURES / f"{entry['slug']}.json").exists()
        if entry.get("added"):
            # a scenario written after the spike cannot be part of what the spike saw die
            assert entry["spike_error"] == "", entry["slug"]
            assert entry["spike_records"] == 0, f"{entry['slug']}: a spec the spike never ran has no spike number"
    shapes = {shape: sum(1 for s in SHAPES.values() if s == shape) for shape in set(SHAPES.values())}
    # four domains x eight shapes: a shape with one scenario would prove almost nothing about the dispatch
    assert all(count >= 4 for count in shapes.values()), shapes
    # T1, the eight-type gate: PR1a shipped seven of these and refused the eighth
    assert set(values.SAMPLERS) == {"numeric", "enum", "bool", "text", "date", "list", "object", "catalog"}
    assert len(CATALOG_SLUGS) == 4
    for slug in CATALOG_SLUGS:
        assert len(catalog_fields_of(slug)) == 1, f"{slug}: a catalog fixture with two pools is a different test"
    # G4's two: the scenarios added the other way round, as JSON with no engine change behind them
    assert PR3_SLUGS == ["law-appeal-window", "edu-late-work-escalation"]


# ---------------------------------------------------------------- field types (T1, D12/D13/D15)


def test_numeric_fields_read_their_bounds_whatever_the_bound_is_called():
    """D12: `normal`/`critical` stay the aliases the released specs use; `bounds` is the general form, so a new
    industry's own limits never reach ops.py."""
    legacy = {"name": "收缩压", "unit": "mmHg", "decimals": 0, "normal": [90, 140]}
    general = {"name": "额度使用率", "unit": "%", "decimals": 1, "bounds": {"normal": [0, 100]}}
    rng = random.Random(0)
    for field in (legacy, general):
        low, high = values.bounds_of(field)["normal"]
        for _ in range(30):
            # PR2a (design doc D3): the sampler's value is the number, not the measurement with its unit glued on — the
            # unit is what the record's text gets at build time — so a bound check reads it without parsing.
            value = values.sample(field, rng, {})
            assert isinstance(value, (int, float)) and not isinstance(value, bool), (field, value)
            assert low <= value <= high, (field, value)
    assert values.bounds_of(legacy)["normal"] == [90, 140]
    assert values.path_of(legacy) == ["收缩压"]


def test_enum_bool_and_text_draw_from_a_pool_that_lives_in_the_spec():
    """D13: there is no corpus path on purpose — a pool outside the spec would not exist on the CI machine and would
    break deterministic replay."""
    rng = random.Random(1)
    spec = {"generator": {"grade_bands": ["A", "B", "C"]}}
    enum = {"name": "评级", "type": "enum", "values": ["A", "B", "C"]}
    ref = {"name": "评级引用", "type": "enum", "values_ref": "grade_bands"}
    text = {"name": "条款", "type": "text", "values": ["第 3 条 交付期限", "第 7 条 不可抗力"]}
    flag = {"name": "已签名", "type": "bool"}
    assert {values.sample(enum, rng, spec) for _ in range(50)} == {"A", "B", "C"}
    assert {values.sample(ref, rng, spec) for _ in range(50)} == {"A", "B", "C"}
    assert values.sample(text, rng, spec) in text["values"]
    assert isinstance(values.sample(flag, rng, spec), bool)


def test_date_fields_return_iso_dates_inside_their_range():
    """ISO because `kev.api.date_facts` already recognises the pattern, so a time-sensitive scenario gets day counts
    without the model doing arithmetic."""
    field = {"name": "到期日", "type": "date", "range": ["2026-10-01", "2026-10-31"]}
    rng = random.Random(2)
    for _ in range(50):
        value = values.sample(field, rng, {})
        assert date.fromisoformat(value) == date.fromisoformat(value)
        assert field["range"][0] <= value <= field["range"][1]


def test_list_elements_reuse_the_same_type_dispatch():
    """D15: one element schema, so a list of objects does not need a second sampler."""
    field = {"name": "持仓", "type": "list", "min": 2, "max": 3, "items": {"element": {
        "type": "object", "fields": [
            {"name": "code", "type": "enum", "values": ["600519", "510300"]},
            {"name": "weight", "unit": "", "decimals": 1, "normal": [1, 40]},
        ]}}}
    rng = random.Random(3)
    for _ in range(20):
        rows = values.sample(field, rng, {})
        assert 2 <= len(rows) <= 3
        for row in rows:
            assert row["code"] in ["600519", "510300"]
            assert 1 <= float(row["weight"]) <= 40
    scalars = {"name": "标签", "type": "list", "min": 1, "max": 2, "item_values": ["x", "y"]}
    assert all(v in ["x", "y"] for v in values.sample(scalars, rng, {}))


def test_field_declarations_the_engine_cannot_honour_fail_loud():
    """Before this dispatch a missing `normal` was a KeyError from inside the sampler and an unknown `type` silently
    became numeric; both are refusals now, because a half-built record is dead data that nothing downstream notices."""
    rng = random.Random(4)
    cases = [
        ({"name": "x", "unit": "", "decimals": 1}, "no 'normal' bound"),
        ({"name": "x", "type": "enum", "values": []}, "empty or non-list"),
        ({"name": "x", "type": "enum", "values_ref": "nope"}, "does not declare"),
        ({"name": "x", "type": "date"}, "needs a 'range'"),
        ({"name": "x", "type": "date", "range": ["2026-13-01", "2026-01-02"]}, "bad 'range'"),
        ({"name": "x", "type": "list"}, "needs 'item_values'"),
        ({"name": "x", "type": "object"}, "declares no 'fields'"),
        ({"name": "x", "type": "catalog"}, "non-empty 'pool'"),
        ({"name": "x", "type": "catalog", "pool": ["a"]}, "pool entry that is not an object"),
        ({"name": "x", "type": "catalog", "pool": [{"a": 1}], "draw": 3}, "'draw' that is not an object"),
        ({"name": "x", "type": "catalog", "pool": [{"a": 1}], "draw": {"min": 2, "max": 1}}, "not 0 <= min <= max"),
        ({"name": "x", "type": "duration"}, "unknown type"),
    ]
    for field, message in cases:
        with pytest.raises(values.UnsupportedField, match=message):
            values.sample(field, rng, {})
    for bad_path in ("案情", [], ["", "案情"]):
        with pytest.raises(values.UnsupportedField, match="bad 'path'"):
            values.path_of({"name": "x", "path": bad_path})


def test_only_a_critical_bound_numeric_field_can_be_steered_to_a_tier():
    """A plan target names a tier, which only a numeric field with a critical bound can be pushed to; everything else
    stays a companion field. D6's other half is that a companion is now the spec's own choice — `selectors[0]` says how
    many fields a record carries instead of the literal that assumed the released six — which is why the four-field
    G4 specs sample exactly four keys per record (`test_g4_declares_its_own_record_shape_and_a_conjunction_per_slot`)."""
    assert values.steerable({"name": "K+", "normal": [1, 2], "critical": {"low": [[0, 1]]}})
    assert not values.steerable({"name": "K+", "normal": [1, 2]})
    assert not values.steerable({"name": "条款", "type": "text", "values": ["a"]})
    assert not values.steerable({"name": "已签名", "type": "bool"})


# ---------------------------------------------------------------- the catalog field (D10)


def test_the_catalog_sampler_draws_k_candidates_without_replacement():
    """D10: a catalog field has no *value*, it has a pool of candidates that carry their own label attributes, and a
    record draws k of them. Without replacement because the same candidate twice hands a rule the same evidence twice."""
    field = {"name": "症状", "type": "catalog", "draw": {"min": 2, "max": 3},
             "pool": [{"name": f"c{i}", "urgency": i} for i in range(5)]}
    rng = random.Random(6)
    for _ in range(30):
        drawn = values.sample(field, rng, {})
        assert 2 <= len(drawn) <= 3
        names = [candidate["name"] for candidate in drawn]
        assert len(set(names)) == len(names), drawn
        assert set(names) <= {f"c{i}" for i in range(5)}
    # the candidates come back as copies: what a rule or a surface mutates is the record's, never the spec's
    before = json.dumps(field["pool"], sort_keys=True)
    values.sample(field, rng, {})[0]["urgency"] = -1
    assert json.dumps(field["pool"], sort_keys=True) == before
    # a `draw` wider than the pool is clamped, not a crash — and the same for a `min` the pool cannot satisfy
    for draw in ({"min": 1, "max": 9}, {"min": 4, "max": 5}):
        small = {"name": "x", "type": "catalog", "draw": draw, "pool": [{"name": "a"}, {"name": "b"}]}
        assert len(values.sample(small, rng, {})) <= 2


def test_a_three_field_spec_still_fills_every_record():
    """The companion draw asks for 2-5 fields, so a three-field spec — one catalog pool plus two companions, which is how
    the PR1b fixtures are cut — used to die in `rng.sample`. The clamp is also what makes the pool unavoidable, so every
    record of such a spec carries a `_meta.derive`."""
    fields = [{"name": "池", "type": "catalog", "pool": [{"name": "a"}, {"name": "b"}]},
              {"name": "甲", "type": "enum", "values": ["x"]},
              {"name": "乙", "type": "enum", "values": ["y"]}]
    sampler = BoundarySampler(fields, [], spec={})
    rng = random.Random(7)
    for _ in range(20):
        assert set(sampler.sample(None, rng)) == {"池", "甲", "乙"}


# ---------------------------------------------------------------- the derive channel (D11)


def test_the_derive_channel_moves_only_the_catalog_keys_out_of_the_view():
    """PR1b is a channel for one field type, not a rewrite of the other seven: a spec with no catalog field must go on
    producing byte for byte the file PR1a produced, and that starts with `split` returning nothing."""
    fields = [{"name": "症状", "type": "catalog"}, {"name": "年龄"}]
    sampled = {"症状": [{"name": "胸痛", "urgency": 2}], "年龄": "41.0 岁"}
    derived, view = derive.split(sampled, fields)
    assert derived == {"症状": [{"name": "胸痛", "urgency": 2}]}
    assert view == {"年龄": "41.0 岁"}
    assert derive.split({"年龄": "41.0 岁"}, fields) == ({}, {"年龄": "41.0 岁"})


def test_a_pool_that_collides_with_a_name_the_engine_owns_is_refused_before_the_first_record():
    """D13 keeps the pools in the spec; this is the other half — a pool called `derived` would be shadowed by the draw
    every expression means, and the failure would show up as dead data instead of as an error."""
    for declared, message in ((("TONE",), "must be an object"),
                              ({"derived": ["a"]}, "reserved name"),
                              ({"TONE": []}, "non-empty list")):
        with pytest.raises(derive.SurfaceError, match=message):
            derive.pools({"generator": {"pools": declared}})
    assert derive.pools({}) == {}
    assert derive.pools({"generator": {"pools": {"TONE": ["a"]}}}) == {"TONE": ["a"]}
    assert derive.extra_names({"generator": {"pools": {"TONE": ["a"]}}}, {"症状": []}) == {"TONE": ["a"], "derived": {"症状": []}}


def test_pick_reaches_the_random_source_through_the_engine_and_nothing_else():
    """§7.1's third question, settled by probe: `pick` is bound per record because a name is callable — a spec holding
    the rng itself could write `rng.seed(0)` and quietly break the replay the seed is the whole point of. Neither route
    reaches the interpreter: simpleeval refuses `__`-prefixed attributes, which is what `__globals__` would need, and
    since PR2b the binding is a closure, so `.args` — the one hop a `functools.partial` left open onto the Random
    itself (design doc §6, defect 9) — is not there to hop through either."""
    names = derive.extra_names({"generator": {"pools": {"TONE": ["a", "b", "c"]}}}, {})
    evaluator = SimpleEval(functions=derive.operators(random.Random(8)), names=names)
    assert {evaluator.eval("pick(TONE)") for _ in range(60)} == {"a", "b", "c"}
    assert not any(isinstance(value, random.Random) for value in names.values())
    with pytest.raises(Exception, match="not available"):
        evaluator.eval("TONE.__class__")
    with pytest.raises(Exception, match="args"):
        evaluator.eval("pick.args[0].seed(0)")

    def drawn(seed):
        one = SimpleEval(functions=derive.operators(random.Random(seed)), names=names)
        return [one.eval("pick(TONE)") for _ in range(20)]

    assert drawn(9) == drawn(9)


def test_a_surface_reads_the_draw_the_pools_and_the_surface_it_already_built():
    fields = [{"name": "症状", "type": "catalog", "surface": {
        "主诉": "join_by(derived['症状'], 'name', '、') + '，' + pick(TONE)",
        "红旗": "default_if_empty([s['name'] for s in derived['症状'] if s['red_flag']], ['无'])",
        "复述": "'见 ' + 主诉",
    }}]
    derived = {"症状": [{"name": "胸痛", "red_flag": True}, {"name": "气短", "red_flag": False}]}
    names = derive.extra_names({"generator": {"pools": {"TONE": ["很着急"]}}}, derived)
    built = derive.surfaces(fields, derived, names, derive.operators(random.Random(0)))
    assert built["主诉"] == "胸痛、气短，很着急"
    assert built["红旗"] == ["胸痛"]
    assert built["复述"].startswith("见 胸痛、气短")
    # the reason surfaces are not plain SimpleEval: it refuses both shapes the moment it evaluates one
    for expression in ("[s['name'] for s in derived['症状']]", "'' or ['无']"):
        with pytest.raises(Exception, match="not available"):
            SimpleEval(functions=derive.operators(random.Random(0)), names=names).eval(expression)


def test_a_draw_that_leaves_no_trace_in_the_state_is_a_refusal():
    """Fail-loud on purpose: a hole in the surface is a record whose label has no evidence in the prompt, and nothing
    downstream can see it. A surface key may not name a declared field, a pool or `derived` either."""
    derived = {"症状": [{"name": "胸痛"}]}
    with pytest.raises(derive.SurfaceError, match="declares no 'surface'"):
        derive.surfaces([{"name": "症状", "type": "catalog"}], derived, {"derived": derived}, {})
    for key, message in (("年龄", "names a declared field"), ("TONE", "names an expression name"),
                         ("derived", "names an expression name")):
        fields = [{"name": "症状", "type": "catalog", "surface": {key: "'x'"}}, {"name": "年龄"}]
        with pytest.raises(derive.SurfaceError, match=message):
            derive.surfaces(fields, derived, {"TONE": ["a"], "derived": derived}, {})
    with pytest.raises(derive.SurfaceError, match="'1/0'"):
        derive.surfaces([{"name": "症状", "type": "catalog", "surface": {"x": "1/0"}}], derived, {"derived": derived}, {})


def test_a_spec_without_a_catalog_field_costs_the_run_nothing():
    """The rng is the whole reproducibility story, so `surfaces` has to return before it touches it: same seed, same
    file, for every one of the 32 scenarios PR1a already shipped."""
    rng, control = random.Random(11), random.Random(11)
    fields = [{"name": "年龄"}]
    names = derive.extra_names({"generator": {"pools": {"TONE": ["a"]}}}, {})
    assert derive.surfaces(fields, {}, names, derive.operators(rng)) == {}
    assert rng.random() == control.random()


# ---------------------------------------------------------------- spec resolution (D7)


def test_resolve_spec_prefers_the_env_dir_then_the_db_projection_then_the_repo(tmp_path, monkeypatch):
    """The console edits the DB's copy; the engine used to read `docs/medical/specs`. Whichever wins, it has to win in
    one place, or a preview and a generation disagree (§6 defect 2)."""
    env_dir, console_dir, repo_dir = tmp_path / "env", tmp_path / "console", tmp_path / "repo"
    for directory, marker in ((env_dir, "env"), (console_dir, "console"), (repo_dir, "repo")):
        (directory / "slug").mkdir(parents=True)
        (directory / "slug" / "spec.json").write_text(json.dumps({"name": marker}), encoding="utf-8")
    monkeypatch.setattr(paths, "CONSOLE_SPECS", console_dir)
    monkeypatch.setattr(paths, "SPECS", repo_dir)
    monkeypatch.setenv("KEV_ENGINE_SPEC_DIR", str(env_dir))
    assert common.resolve_spec("slug")["name"] == "env"
    monkeypatch.delenv("KEV_ENGINE_SPEC_DIR")
    assert common.resolve_spec("slug")["name"] == "console"
    # the flat layout (`<dir>/<name>.json`) resolves too, which is what the fixture directory uses
    (repo_dir / "flat.json").write_text('{"name": "flat"}', encoding="utf-8")
    assert common.resolve_spec("flat")["name"] == "flat"
    with pytest.raises(FileNotFoundError, match="no spec for 'absent'"):
        common.resolve_spec("absent")


def test_a_spec_that_never_declared_a_field_type_is_still_numeric(tmp_path, monkeypatch):
    """The backward-compat half of design doc D1: the six engine fixtures were written before `type` existed, and a
    field with no `type` has to keep sampling as numeric, or PR1a would silently turn every released measurement into
    an unsupported field. They also prove the `<dir>/<slug>/spec.json` layout resolves from a real directory."""
    monkeypatch.setenv("KEV_ENGINE_SPEC_DIR", str(tmp_path))  # an env dir without the scenario falls through
    monkeypatch.setattr(paths, "CONSOLE_SPECS", tmp_path)
    monkeypatch.setattr(paths, "SPECS", ROOT / "tests/fixtures")
    checked = 0
    for path in sorted((ROOT / "tests/fixtures").glob("*/spec.json")):
        spec = common.resolve_spec(path.parent.name)
        assert spec["name"] == path.parent.name
        assert spec["questions"]
        for field in (spec.get("generator") or {}).get("fields", []):
            checked += 1
            assert values.field_type(field) == "numeric", (path.parent.name, field["name"])
    assert checked >= 50, f"only {checked} fixture fields were checked"


def test_a_torn_spec_names_its_file_instead_of_falling_through(tmp_path, monkeypatch):
    """The DB projection is written by the console; a half-written file must not send the engine off to generate from
    the committed copy of a spec the user had just edited."""
    directory = tmp_path / "broken"
    directory.mkdir()
    (directory / "spec.json").write_text('{"name": "broken", "questions": ', encoding="utf-8")
    monkeypatch.setenv("KEV_ENGINE_SPEC_DIR", str(tmp_path))
    with pytest.raises(ValueError, match="is not valid JSON"):
        common.resolve_spec("broken")


# ---------------------------------------------------------------- the record skeleton (D2, G6)


def test_make_record_puts_each_value_at_its_declared_path_and_injects_only_what_the_spec_declares():
    spec = {"generator": {"aux": {"missing_context": "dropped"}}}
    fields = [
        {"name": "涉案金额", "path": ["案情", "涉案金额"]},
        {"name": "退赔比例", "path": ["量刑情节", "退赔比例"]},
        {"name": "被害人人数"},
    ]
    sampler = BoundarySampler(fields, [], spec=spec)
    record = sampler.make_record({"涉案金额": "45.0 万元", "退赔比例": "90.0 %", "被害人人数": "5.0 人"}, dropped="unit")
    assert record == {"案情": {"涉案金额": "45.0 万元"}, "量刑情节": {"退赔比例": "90.0 %"},
                      "被害人人数": "5.0 人", "missing_context": ["unit"]}
    assert sampler.make_record({"被害人人数": "1.0 人"})["missing_context"] == []
    # an aux source the engine does not own is a refusal, not a silently empty key
    with pytest.raises(values.UnsupportedField, match="only 'dropped' is implemented"):
        BoundarySampler(fields, [], spec={"generator": {"aux": {"x": "catalog"}}}).make_record({})


def test_place_creates_the_intermediate_dicts():
    root = {"a": {"keep": 1}}
    place(root, ["a", "b", "c"], 2)
    place(root, ["d"], 3)
    assert root == {"a": {"keep": 1, "b": {"c": 2}}, "d": 3}


# ---------------------------------------------------------------- the plan and the selector (D5, D6)


def test_d5_plan_weights_are_relative_to_the_pool_so_the_plan_scales_with_n():
    """The released `critical-value` shape: five blocks of `{share: 0.35, quota: 55}`. The quota is the block's weight
    and the pool is 35 % of n, so the 787-record run the spec was cut for still gets 55 apiece, while a 60-record run
    asks for 4-5 each instead of steering all 60 the way the absolute numbers did (design doc D5, F5)."""
    blocks = {name: {"share": 0.35, "quota": 55} for name in ("renal", "cbc", "plt", "glu", "k")}
    for n, counts in ((787, {"renal": 55, "cbc": 55, "plt": 55, "glu": 55, "k": 55}),
                      (60, {"renal": 5, "cbc": 4, "plt": 4, "glu": 4, "k": 4})):
        plan = PlanAllocator({"by_category": blocks}).allocate(n, random.Random(0))
        assert len(plan) == n
        assert Counter(name for _, name in (t for t in plan if t)) == Counter(counts), (n, counts)
        assert sum(1 for target in plan if target is None) == n - sum(counts.values())


def test_d5_a_by_label_block_buys_the_joint_answer_and_not_just_one_question():
    """A target is a conjunction of pairs, so a plan that addresses every question is the only way to hold a share as n
    moves (gate G2, design doc D5). The allocator hands the block its weight over the pool and the engine is the one
    that has to find a record whose rules agree."""
    targets = {"a:1 & b:2": {"weight": 3}, "a:0 & b:2": {"weight": 1}}
    plan = PlanAllocator({"by_label": targets}).allocate(8, random.Random(0))
    assert Counter(str(target) for target in plan) == Counter({"a:1 & b:2": 6, "a:0 & b:2": 2})
    assert all(isinstance(target, LabelTarget) for target in plan)
    assert {(qid, key) for target in plan for qid, key in target.pairs} == {("a", "1"), ("a", "0"), ("b", "2")}


def test_d5_a_plan_that_contradicts_itself_is_named_before_the_first_draw():
    """Five shapes that would otherwise cost a full run to explain themselves: a quota fighting a weight (two answers
    to "how many"), a target part that names nothing, two answers of one question, blocks that disagree about the pool
    they are drawn from, and a key the allocator does not know."""
    for targets, fragment in (({"by_category": {"x": {"quota": 3, "weight": 2}}}, "declares both `weight`"),
                              ({"by_label": {"a:1 & ": {"weight": 1}}}, 'parts joined by " & "'),
                              ({"by_label": {"a:1 & a:2": {"weight": 1}}}, "asks two answers of ['a']"),
                              ({"by_category": {"x": {"share": 0.2}, "y": {"share": 0.4}}}, "they disagree"),
                              ({"by_category": {"x": {"normal": 1}}}, r"['normal']"),
                              ({"normal_share": 1.5}, "is not a share of n (0..1)")):
        assert any(fragment in error for error in PlanAllocator(targets).static_errors()), (targets, fragment)
    assert PlanAllocator({"by_label": {"a:1": {"weight": 1}}}).static_errors() == []
    with pytest.raises(PlanError, match="declares both `weight`"):
        PlanAllocator({"by_category": {"x": {"quota": 3, "weight": 2}}}).allocate(10, random.Random(0))


def test_d5_a_floor_the_questions_cannot_serve_is_refused_before_the_search(tmp_path, monkeypatch):
    """A gap the exit gate reports is a fact about the spec's rules; this is a fact about its serving contract, and a
    target the contract cannot answer would be searched `LABEL_ATTEMPTS` times per slot before the gate called it rare.
    The same for a question the spec never asks."""
    for answer, fragment in (("window_band:9", "the question answers 0, 1, 2"),
                             ("no_such_question:0", "which the spec does not ask")):
        spec = spec_of("law-appeal-window")
        spec["generator"]["plan_targets"] = {"floor": 0.05, "by_label": {answer: {"weight": 1}}}
        directory = tmp_path / "bad-plan"
        directory.mkdir(exist_ok=True)
        (directory / "spec.json").write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
        monkeypatch.setenv("KEV_ENGINE_SPEC_DIR", str(tmp_path))
        out = tmp_path / "bad-plan.jsonl"
        with pytest.raises(PlanError, match="answers its questions cannot carry"):
            engine.run(["--scenario", "bad-plan", "--n", "5", "--seed", "0", "--pairs", "0", "--out", str(out)])
        assert not out.exists(), "a refused plan must not leave a half-written file"


def test_d6_the_selector_is_the_spec_saying_how_many_fields_a_record_carries():
    """D6: `min`/`max` were literals copied out of the legacy builder (1 + randint(2, 5)) and they count the fields in
    one record, the triggering one included. `min`/`max` of 3..6 are the released numbers, so omitting the block stays
    today's behaviour, and the draw is clamped to the fields that exist instead of carrying an implicit "a spec needs
    six fields" floor — which is what `test_a_three_field_spec_still_fills_every_record` is about."""
    fields = [{"name": f"f{i}", "type": "enum", "values": ["a", "b"]} for i in range(8)]
    rng = random.Random(0)
    sized = BoundarySampler(fields, [{"min": 5, "max": 5}], spec={})
    assert {len(sized.sample(None, rng)) for _ in range(30)} == {5}
    default = BoundarySampler(fields, [], spec={})
    assert {len(default.sample(None, rng)) for _ in range(60)} == {3, 4, 5, 6}
    clamped = BoundarySampler(fields[:3], [{"min": 3, "max": 6}], spec={})
    assert {len(clamped.sample(None, rng)) for _ in range(20)} == {3}


def test_d6_a_selector_the_engine_cannot_read_is_refused_at_construction():
    """Checked once, so a typo cannot sample a whole run wrong — the keys are the spec's, and so is a wrong one."""
    fields = [{"name": "f", "type": "enum", "values": ["a", "b"]}]
    for declared, message in ((("TONE",), "must be an object"),
                              ({"min": 6, "max": 3}, "not 1 <= min <= max"),
                              ({"min": 0}, "not 1 <= min <= max"),
                              ({"min": "x"}, "must be integers"),
                              ({"minz": 3}, r"declares \['minz'\]"),
                              ({"weight_trigger_extra": 1.5}, "must be a probability"),
                              ({"max_trigger_extra": -1}, "cannot be negative")):
        with pytest.raises(values.UnsupportedField, match=message):
            BoundarySampler(fields, [declared], spec={})


# ---------------------------------------------------------------- the matrix itself (G1, G6)


@pytest.mark.parametrize("slug", SLUGS)
def test_every_spike_scenario_generates_without_crashing(slug, tmp_path):
    """G1: the 20 scenarios the spike lost to `KeyError: 'normal'` now produce a full run; G6: none of them is
    dressed as a lab report."""
    records = generate(slug, tmp_path, n=40)
    assert len(records) == 40, f"{slug}: {len(records)} of 40 records"
    questions = spec_of(slug)["questions"]
    for record in records:
        state = record["state"]
        assert "patient" not in state and "labs" not in state, f"{slug}: the legacy skeleton leaked into a new domain"
        assert set(record["questions"]) == set(questions)
        assert common.split_data.check_record(record) == []


def test_a_scenario_with_declared_paths_ships_a_nested_state(tmp_path):
    """The other half of D2: the paths are not decoration, the values really land there, and the aux key the spec
    declares is present on every record."""
    records = generate("law-sentencing", tmp_path, n=30)
    groups = {name for field in fields_of("law-sentencing") for name in field["path"][:-1]}
    assert groups == {"案情", "损害后果", "量刑情节"}
    state = records[0]["state"]
    assert set(state) >= groups | {"missing_context"}
    for group in groups:
        assert isinstance(state[group], dict) and state[group]
        assert all(isinstance(value, str) for value in state[group].values())


def test_labels_are_reachable_on_both_sides_where_the_rules_can_read_them(tmp_path):
    """The scenarios whose rules need nothing beyond an arithmetic value and what simpleeval can do must not collapse to
    one answer — that is the difference between "it ran" and "it taught something"."""
    for slug in ("fin-fraud-flags", "law-comparative-negligence", "edu-course-placement"):
        tables = common.label_table(generate(slug, tmp_path, n=120))
        assert all(len(counter) >= 2 for counter in tables.values()), (slug, tables)


def test_the_degenerate_ledger_is_empty_since_pr3_paid_the_last_two(gate_dir):
    """F3's debt as a set, both directions: nothing is collapsed any more — `LEDGER` is empty, so a question that
    collapses again puts a name in `seen` and fails here instead of quietly re-enlarging the ledger — and the scenarios
    each PR paid really do move on both sides.

    Read at the gate's own n = 120, which is the size the floor is a whole number of records at: at n = 60 two spike
    specs drop their single under-floor answer outright and read as collapsed, which is `UNDER_FLOOR`'s claim about the
    spec's rules, not `LEDGER`'s about the engine."""
    seen = {}
    tables_by_slug = {}
    for slug in SLUGS:
        tables = common.label_table(gate_once(slug, gate_dir)[1])
        tables_by_slug[slug] = tables
        flat = sorted(qid for qid, counter in tables.items() if len(counter) == 1)
        if flat:
            seen[slug] = flat
    assert seen == LEDGER == {}
    for paid in (PAID_BY_PR2A, PAID_BY_PR2B, PAID_BY_PR3):
        for slug, questions in paid.items():
            for qid in questions:
                assert len(tables_by_slug[slug][qid]) >= 2, (slug, qid, tables_by_slug[slug][qid])


def test_the_same_seed_reproduces_the_same_file(tmp_path):
    for slug in ("fin-aml-sar", "sci-review-accept"):
        first = generate(slug, tmp_path, n=30, seed=11)
        second = generate(slug, tmp_path, n=30, seed=11)
        assert [json.dumps(r, sort_keys=True, ensure_ascii=False) for r in first] == \
               [json.dumps(r, sort_keys=True, ensure_ascii=False) for r in second], slug


# ---------------------------------------------------------------- the exit gate (G1, G2, G4)

#: The size G1 reads the matrix at. 120 is the smallest n for which the 5 % floor is a whole number of records (6)
#: and still big enough that a 2 % answer is a miss rather than a rounding artefact.
GATE_N = 120

_GATE_CACHE: dict = {}


@pytest.fixture(scope="session")
def gate_dir(tmp_path_factory):
    return tmp_path_factory.mktemp("engine-gate")


def gate_once(slug, gate_dir, n=GATE_N, seed=0):
    """One engine run per (slug, n, seed) for the whole file.

    The same run answers four questions below — the record count, the shape of every record, the gate's own lines and
    the exit code — and 38 scenarios at n = 120 is the slowest thing in this module, so the first caller caches it.
    """
    key = (slug, n, seed)
    if key not in _GATE_CACHE:
        _GATE_CACHE[key] = gate_run(slug, gate_dir / f"{slug}-{n}-{seed}.jsonl", n, seed=seed)
    return _GATE_CACHE[key]


@pytest.mark.parametrize("slug", SLUGS)
def test_g1_the_gate_reports_exactly_the_debt_this_spec_owes(slug, gate_dir):
    """G1, both halves, read off the engine's own stderr rather than recomputed here.

    The structural half is the engine's: every scenario ships exactly n records and `check_record` accepts each one.
    The distribution half is the spec author's: an answer no rule reaches, an answer under the floor, a catch-all that
    answers most of the file. Those three are `NEVER_LABELLED`, `UNDER_FLOOR` and `CATCH_ALL`, and the equality is the
    point in both directions — a scenario that pays a debt has to move its name into the map below (and out of
    `GATE_CLEAN`'s opposite), and one that gains a new dead answer fails here instead of shipping it quietly.

    The exit code is 0 for all 38, which is §3's exit row, not an absence of gaps: strictness is exactly where a spec
    declares a `floor`, so 28 spike specs report their history without reddening CI on a threshold nobody chose.
    """
    code, records, messages = gate_once(slug, gate_dir)
    assert len(records) == GATE_N, f"{slug}: {len(records)} of {GATE_N} records"
    problems = [problem for record in records for problem in common.split_data.check_record(record)]
    assert problems == [], (slug, problems[:3])
    never, under, catch = gate_debt(messages)
    assert never == NEVER_LABELLED.get(slug, {}), slug
    assert under == UNDER_FLOOR.get(slug, {}), slug
    assert catch == CATCH_ALL.get(slug), slug
    assert bool(never or under or catch) == (slug not in GATE_CLEAN), (slug, messages)
    assert code == 0, (slug, messages)


def test_g1_strictness_is_exactly_where_a_gap_exists(gate_dir):
    """The other side of the exit row: `--gate strict` does fail, so the 28 zeros above are a choice about whose history
    to red, not a gate that cannot bite. And a clean spec that *did* ask to be judged (`edu-essay-scoring`) still exits
    0, or the gate would fail on its own best customer."""
    assert sorted(FLOORED_SLUGS) == ["edu-essay-scoring", "edu-late-work-escalation", "law-appeal-window"]
    for slug in FLOORED_SLUGS:
        assert gate_once(slug, gate_dir)[0] == 0, slug
    owing = sorted(set(SLUGS) - set(GATE_CLEAN))
    code, _, messages = gate_run(owing[0], gate_dir / f"{owing[0]}-strict.jsonl", GATE_N, gate="strict")
    assert code == 1, messages
    assert gate_debt(messages) != ({}, {}, None)
    code, _, messages = gate_run(GATE_CLEAN[0], gate_dir / f"{GATE_CLEAN[0]}-strict.jsonl", GATE_N, gate="strict")
    assert (code, messages) == (0, []), messages
    code, _, _ = gate_run(owing[0], gate_dir / f"{owing[0]}-warn.jsonl", GATE_N, gate="warn")
    assert code == 0, "`warn` is the pre-PR3 behaviour: the numbers printed, the file kept, the run passed"


def test_g2_a_planned_share_does_not_move_with_n(gate_dir):
    """Gate G2, the arithmetic half of design doc D5: weights over a pool with largest-remainder rounding, and a
    `by_label` target that names every question's answer, hold the shares as n grows.

    The rounding alone is not enough. A question the plan does not address is left to the natural distribution, and the
    plan cannot hold what it never asked for: measured at PR3 over 200 seeds of `edu-essay-scoring` at n = 30 against the
    same plan's n = 3,000 read, `plagiarism_flag:true` under band-only targets spreads sd 6.75pp (the binomial
    prediction for its 17% rate is 6.87pp) from 0% to 33.3% of the file, and 98 of the 200 runs land more than the gate's
    5pp away (median 3.57pp, worst 16.90pp). Under the shipped joint cells that question is at 23.3% in all 200 runs.
    That is why `LabelTarget` is a conjunction.

    The shipped conjunction's own drift is rounding, which is why it is the same number every seed: the worst PR3
    measured is 1.67pp — `edu-essay-scoring`'s `plagiarism_flag` (plan 25% at n = 30 is 7.5 records) and band 2, and
    `edu-late-work-escalation`'s two thinner tiers, all between n = 30 and n = 300, and 1.33pp for `law-appeal-window`.
    n = 3,000 is the nightly row (16.2 + 14.3 + 11.9 s for the three, so the file goes from ~15 s to ~58 s), which is why
    PR CI reads n = 30 and n = 300.

    `messages == []` is the same claim from the other side: a floored spec that needs retries shows a `note` line and
    then a gap, so silence means the plan's cells are ones the rules reach without searching.
    """
    sizes = [30, 300] + ([3000] if os.environ.get("KEV_MATRIX_FULL") else [])
    for slug in FLOORED_SLUGS:
        base = None
        for n in sizes:
            code, records, messages = gate_once(slug, gate_dir, n)
            assert (code, messages) == (0, []), (slug, n, messages)
            shares = shares_of(records)
            if base is None:
                base = shares
                continue
            for qid, per_key in base.items():
                assert set(shares[qid]) == set(per_key), (slug, n, qid)
                for key, share in per_key.items():
                    assert abs(shares[qid][key] - share) < 0.05, (slug, n, qid, key, share, shares[qid][key])


@pytest.mark.parametrize("slug", PR3_SLUGS)
def test_g4_a_new_industry_written_only_as_json_passes_the_gate(slug, gate_dir):
    """G4, the gate these two specs exist to pass: a new industry needs no Python.

    They are the matrix's only scenarios added after the engine rather than before a fix, and each one ships 120
    records the gate has nothing to say about. The structural claim is that nothing in the generators names a field or
    a question of theirs — a scenario that needed an engine patch would leave its vocabulary in the engine's Python,
    and that is exactly the shape `ops.normal_value` reading `field["normal"]` for every type had (F1).
    """
    code, records, messages = gate_once(slug, gate_dir)
    assert (code, messages) == (0, []), (slug, messages)
    assert len(records) == GATE_N
    assert all(common.split_data.check_record(record) == [] for record in records), slug
    engine_source = "\n".join(path.read_text(encoding="utf-8")
                              for path in sorted((ROOT / "kev/console/generators").glob("*.py")))
    spec = spec_of(slug)
    for field in spec["generator"]["fields"]:
        assert field["name"] not in engine_source, f"{slug}: {field['name']} reached the engine's Python"
    for qid in spec["questions"]:
        assert qid not in engine_source, f"{slug}: {qid} reached the engine's Python"


def test_g4_declares_its_own_record_shape_and_a_conjunction_per_slot():
    """What makes the two new specs a G4 rather than two more spike files: `selectors` says four fields per record
    instead of inheriting a literal that assumed six (D6), and every `by_label` cell is a conjunction over both
    questions with a `floor` next to it, which is what lets the gate judge the file (D5, G2).
    """
    for slug in PR3_SLUGS:
        gen = spec_of(slug)["generator"]
        assert gen["selectors"] == [{"min": 4, "max": 4}], slug
        assert len(gen["fields"]) == 4, slug
        targets = gen["plan_targets"]
        assert targets["floor"] == 0.05, slug
        cells = list(targets["by_label"])
        assert len(cells) == 6, (slug, cells)
        assert all(" & " in cell for cell in cells), (slug, cells)
        questions = set(spec_of(slug)["questions"])
        assert all({qid for qid, _ in LabelTarget.parse(cell).pairs} == questions for cell in cells), slug
        rng = random.Random(0)
        sampler = BoundarySampler(gen["fields"], gen["selectors"], spec={"generator": gen})
        assert {len(sampler.sample(None, rng)) for _ in range(30)} == {4}, slug


# ---------------------------------------------------------------- the rule evaluator (D4, T3/T4, G3)


BROKEN = ROOT / "tests/fixtures/engine-broken"


def mini_spec(fields, rule_list, questions=None, pools=None):
    """A spec with only what the evaluator reads, for a test that is about one rule rather than about a scenario."""
    return {"questions": questions or {"grade": {"type": "choice", "criteria": {"a": "A", "b": "B"}}},
            "generator": {"fields": fields, "rules": rule_list, "pools": pools or {}}}


def label_the(spec, state, derived=None, seed=0):
    """Run a spec's rules through the engine's own seam — the same names, functions and label keys `run` builds."""
    gen = spec["generator"]
    names = derive.extra_names(spec, derived or {})
    return rules.evaluate(gen["rules"],
                          engine._rule_names(state, gen.get("fields", []), gen.get("tier_windows", {}), {}, names),
                          derive.operators(random.Random(seed)), engine._label_keys(spec))


def test_a_rule_that_loops_its_evidence_is_a_rule_now():
    """T3, §5.3 class B: every one of these the matrix specs wrote was refused by `SimpleEval` outright
    (`FeatureNotAvailable: GeneratorExp`), so the rule never matched and the record kept the fallback label."""
    spec = mini_spec([{"name": "知识点掌握", "type": "catalog"}],
                     [{"id": "weak-any", "when": "any(x['mastery'] < 0.5 for x in derived['知识点掌握'])",
                       "then": [{"label": "grade", "value": "b"}]},
                      {"when": "True", "then": [{"label": "grade", "value": "a"}]}])
    weak = [{"name": "循环", "mastery": 0.8}, {"name": "指针", "mastery": 0.2}]
    strong = [{"name": "循环", "mastery": 0.9}, {"name": "指针", "mastery": 0.7}]
    assert label_the(spec, {}, {"知识点掌握": weak})["grade"] == "b"
    assert label_the(spec, {}, {"知识点掌握": strong})["grade"] == "a"


def test_a_record_without_the_evidence_a_rule_reads_falls_to_the_next_rule():
    """§5.3 class A: `selectors` mean one record carries three fields and another six, so a missing key is a normal
    outcome — but "no evidence" and "evidence says no" are the same answer only for the rule that lacks it. The old
    `except Exception: continue` got this right for the wrong reason and stayed silent about a misspelled field name."""
    spec = mini_spec([{"name": "逾期天数", "unit": "天", "decimals": 0, "normal": [0, 90]}],
                     [{"id": "late", "when": "state['逾期天数'] > 30", "then": [{"label": "grade", "value": "b"}]},
                      {"when": "True", "then": [{"label": "grade", "value": "a"}]}])
    assert label_the(spec, {"逾期天数": 45})["grade"] == "b"
    assert label_the(spec, {"逾期天数": 12})["grade"] == "a"
    assert label_the(spec, {})["grade"] == "a"


def test_no_evidence_and_no_fallback_is_no_label_at_all():
    """A suspended rule is not a match: with nothing left to try the record gets no labels, and the engine drops it
    rather than inventing an answer. The view says so in one class only — `in` and `.get` keep the plain-dict answer,
    because a spec may legitimately ask whether the evidence is there."""
    spec = mini_spec([{"name": "逾期天数", "unit": "天", "decimals": 0, "normal": [0, 90]}],
                     [{"when": "state['逾期天数'] > 30", "then": [{"label": "grade", "value": "b"}]}])
    assert label_the(spec, {}) == {}
    view = ops.EvidenceView({})
    assert "逾期天数" not in view and view.get("逾期天数") is None
    with pytest.raises(ops.MissingEvidence):
        view["逾期天数"]


def test_a_label_expression_reading_missing_evidence_suspends_its_rule_too():
    """The `when` is not the only half of a rule: a `then` that cannot be computed makes the rule inapplicable, or the
    first matching rule would ship a label built out of nothing but the fallback's answer."""
    spec = mini_spec([{"name": "逾期天数", "unit": "天", "decimals": 0, "normal": [0, 90]}],
                     [{"id": "grade-by-days", "when": "True",
                       "then": [{"label": "grade", "value": "'b' if state['逾期天数'] > 30 else 'a'"}]},
                      {"when": "True", "then": [{"label": "grade", "value": "a"}]}])
    assert label_the(spec, {"逾期天数": 60})["grade"] == "b"
    assert label_the(spec, {})["grade"] == "a"


def test_a_bare_name_that_is_a_declared_label_is_a_label_and_a_misspelling_is_an_error():
    """§5.3 class E, the `then` half: `value: "a"` means the option, and `value: "aa"` is a broken spec — not a string
    that gets shipped to the scorer because an `except Exception: pass` found nothing better to do with it."""
    spec = mini_spec([{"name": "分数", "unit": "分", "decimals": 1, "normal": [0, 100]}],
                     [{"when": "state['分数'] >= 60", "then": [{"label": "grade", "value": "a"}]},
                      {"when": "True", "then": [{"label": "grade", "value": "b"}]}])
    assert label_the(spec, {"分数": 80.0}) == {"grade": "a"}
    assert label_the(spec, {"分数": 10.0}) == {"grade": "b"}
    misspelt = mini_spec([{"name": "分数", "unit": "分", "decimals": 1, "normal": [0, 100]}],
                         [{"id": "grade-rule", "when": "True", "then": [{"label": "grade", "value": "aa"}]}])
    with pytest.raises(rules.RuleError, match="grade-rule -> grade"):
        label_the(misspelt, {"分数": 80.0})


def test_a_numeric_label_string_keeps_being_an_expression(tmp_path):
    """Why the literal test is a single bare name and not "any value that is a legal key": `sci-incident-triage` writes
    `acuity = '3'` on a `score` question whose keys are '0'..'3', and simpleeval has always evaluated that to the int
    the released records carry. Calling it a literal would quietly retune 3 into "3" — a data change wearing a fix."""
    criteria = ["记录即可", "当班处理", "立刻升级", "全员呼叫"]
    spec = mini_spec([], [{"when": "True", "then": [{"label": "acuity", "value": "3"}]}],
                     questions={"acuity": {"type": "score", "criteria": criteria}})
    assert label_the(spec, {}) == {"acuity": 3}
    for record in generate("sci-incident-triage", tmp_path, n=40):
        assert isinstance(record["questions"]["acuity"]["label"], int), record["questions"]["acuity"]


def test_a_rule_that_is_sound_to_parse_and_wrong_to_run_fails_loud():
    """The other half of T4. The static check sees names, not types: comparing a `text` field to a number is a rule it
    cannot refuse, and it must still arrive as an error instead of 60 records that all took the fallback."""
    spec = mini_spec([{"name": "条款", "type": "text", "values": ["a", "b"]}],
                     [{"id": "apples", "when": "state['条款'] > 30", "then": [{"label": "grade", "value": "b"}]},
                      {"when": "True", "then": [{"label": "grade", "value": "a"}]}])
    with pytest.raises(rules.RuleError, match="apples"):
        label_the(spec, {"条款": "a"})


def test_every_shipped_spec_survives_the_static_check():
    """The 38 matrix specs are what a user copies, so the check that gates them has to be clean on all of them —
    otherwise G3 refuses the library instead of the broken spec."""
    for slug in SLUGS:
        assert rules.static_errors(spec_of(slug)) == [], slug


@pytest.mark.parametrize("slug,fragment", [("unknown-operator", "is not an operator"),
                                            ("unknown-state-key", "is not a declared field"),
                                            ("illegal-label", "grade-label")])
def test_a_spec_no_record_can_satisfy_is_refused_before_the_first_record(slug, fragment, monkeypatch, tmp_path):
    """G3: three ways PR1a lost a scenario's labels, each caught by reading the spec, each named by the rule so the
    person fixing the JSON is not debugging 60 identical answers."""
    monkeypatch.setenv("KEV_ENGINE_SPEC_DIR", str(BROKEN))
    spec = json.loads((BROKEN / f"{slug}.json").read_text(encoding="utf-8"))
    problems = rules.static_errors(spec)
    assert any(fragment in problem for problem in problems), problems
    out = tmp_path / f"{slug}.jsonl"
    with pytest.raises(rules.RuleError):
        engine.run(["--scenario", slug, "--n", "5", "--seed", "0", "--pairs", "0", "--out", str(out)])
    assert not out.exists(), "a refused spec must not leave a half-written file"


# ---------------------------------------------------------------- minimal pairs (D8)


def test_a_pair_moves_every_field_type_the_way_that_type_crosses_a_decision():
    """D8: the flip is typed, and `build` hands back `(name, twin view, twin derived)` so a catalog pair moves the draw
    and the engine rebuilds the surfaces from it, instead of editing a string a rule never read.

    Each type has its own other side: a measurement to the safe side of its bound, a pool member to another member, a
    bool to its negation, a date to the far half of its window, a list by one element, an object by one sub-field, a
    catalog by one drawn candidate. The low-side measurement is §6 defect 5 paid: the safe window used to be built out of
    `normal`'s own width, so `critical: {"low": [[-1e9, 30]]}` landed straight back inside its bound and never escaped —
    0 twins in 200 draws, 200 in 200 now. The refusals under them are not gaps: a one-option pool, a list pinned between
    its `min` and `max` and a measurement with no `critical` to cross cannot change an answer, and a twin that teaches
    the same label twice is noise (`common.minimal_pair` refuses it for the same reason)."""
    rng = random.Random(5)
    builder = PairBuilder({})
    high = {"name": "下滑幅度", "unit": "%", "decimals": 1, "normal": [0, 8], "critical": {"high": [[15, 1e9]]}}
    low = {"name": "退赔比例", "unit": "%", "decimals": 1, "normal": [0, 100], "critical": {"low": [[-1e9, 30]]}}
    enum = {"name": "评级", "type": "enum", "values": ["A", "B", "C"]}
    text = {"name": "条款", "type": "text", "values": ["第 3 条", "第 7 条"]}
    flag = {"name": "已签名", "type": "bool"}
    day = {"name": "到期日", "type": "date", "range": ["2026-10-01", "2026-10-31"]}
    rows = {"name": "持仓", "type": "list", "min": 1, "max": 3, "item_values": ["a", "b", "c"]}
    parent = {"送达延误天数": 9, "异议已登记": True}
    nested = {"name": "送达回执", "type": "object", "fields": [
        {"name": "送达延误天数", "unit": "天", "decimals": 0, "normal": [0, 10], "critical": {"high": [[7, 1e9]]}},
        {"name": "异议已登记", "type": "bool"}]}
    pool = [{"name": f"c{i}", "urgency": i} for i in range(4)]
    catalog = {"name": "症状", "type": "catalog", "pool": pool}
    drawn = [dict(pool[0]), dict(pool[1])]

    def flips(field, value, derived=None, draws=200):
        """The moved value from every draw of one field, and a refusal to lose a single one of them."""
        name = field["name"]
        results = [builder.build({} if derived else {name: value}, {name: field}, name, rng, derived=derived)
                   for _ in range(draws)]
        lost = sum(1 for result in results if result is None)
        assert lost == 0 and all(result[0] == name for result in results), f"{name}: {lost} of {draws} lost"
        return [result[2 if derived else 1][name] for result in results]

    assert all(not values.in_critical(v, high) and v < 15 and v != 30.0 for v in flips(high, 30.0))
    assert all(not values.in_critical(v, low) and v > 30 for v in flips(low, 12.0))
    assert set(flips(enum, "B")) == {"A", "C"}
    assert set(flips(text, "第 3 条")) == {"第 7 条"}
    assert set(flips(flag, True)) == {False}
    middle = date.fromisoformat("2026-10-16")
    assert all(date.fromisoformat(v) > middle for v in flips(day, "2026-10-05"))
    assert all(date.fromisoformat(v) <= middle for v in flips(day, "2026-10-28"))
    assert all(len(v) == 2 for v in flips(rows, ["a", "b", "c"]))
    for moved in flips(nested, dict(parent)):
        assert set(moved) == set(parent)
        assert sum(1 for key in moved if moved[key] != parent[key]) == 1, moved
    for moved in flips(catalog, None, derived={"症状": drawn}):
        assert len(moved) == 2 and sum(1 for c in moved if c not in drawn) == 1, moved
        assert len({candidate["name"] for candidate in moved}) == 2, "a catalog twin drew the same candidate twice"
    # the refusals: nothing here can change an answer, so there is no pair to write
    for field, value in (({"name": "唯一", "type": "enum", "values": ["A"]}, "A"),
                         ({"name": "标签", "type": "list", "min": 2, "max": 2, "item_values": ["a", "b"]}, ["a", "b"]),
                         ({"name": "K+", "unit": "mmol/L", "decimals": 1, "normal": [1, 2]}, 1.5)):
        name = field["name"]
        assert builder.build({name: value}, {name: field}, name, rng) is None, name
        assert builder.build({name: value}, {name: field}, "absent", rng) is None, name


def test_a_catalog_twin_moves_exactly_one_drawn_candidate():
    """The pool minus the draw is the only place a replacement can come from, so a catalog whose whole pool is already
    drawn has nothing left to move and the pair is dropped rather than duplicated."""
    pool = [{"name": "a"}, {"name": "b"}, {"name": "c"}]
    field = {"name": "症状", "type": "catalog", "pool": pool}
    builder = PairBuilder({})
    rng = random.Random(5)
    moved = builder.build({}, {"症状": field}, "症状", rng, derived={"症状": [dict(pool[0]), dict(pool[1])]})
    assert moved[2]["症状"][0] in pool and moved[2]["症状"][1] in pool
    assert sum(1 for c in moved[2]["症状"] if c not in pool[:2]) == 1
    assert builder.build({}, {"症状": field}, "症状", rng,
                         derived={"症状": [dict(c) for c in pool]}) is None, "every candidate was already drawn"


def test_a_catalog_pair_cannot_smuggle_a_second_fact_into_the_twin():
    """`fact_keys` is the guard: the field plus the keys its own `surface` builds. A catalog twin changes the draw and
    every surface spelled out of it, which is one fact seen two ways (D11) — a twin that also moved an unrelated field
    would demonstrate a boundary no record showed, and the engine drops it."""
    field = {"name": "症状", "type": "catalog", "surface": {"主诉": "x"}}
    assert fact_keys(field, "症状") == {"症状", "主诉"}
    assert fact_keys({"name": "年龄", "unit": "岁"}, "年龄") == {"年龄"}


def test_turning_pairs_on_appends_twins_that_are_still_valid_records(tmp_path):
    """Since D8 an unsteered record has bounds to cross too, so a run with `--pairs` ships more than `--n` lines: the
    number PR3 measured for this spec is 59 records for n = 40 at seed 3 (the spike's own file, whose `退赔比例` used to
    be unflippable and is not now). What is promised here is the safe half of turning it on — every appended twin is a
    record `check_record` accepts, with the same questions as its parent."""
    records = generate("law-sentencing", tmp_path, n=40, seed=3, pairs=0.9)
    assert len(records) == 59, len(records)
    questions = set(spec_of("law-sentencing")["questions"])
    for record in records:
        assert common.split_data.check_record(record) == []
        assert set(record["questions"]) == questions


# ---------------------------------------------------------------- the label never reaches the prompt (G8)


def state_keys(node):
    """Every dict key `render` would flatten into the prompt, at any depth (a list of dicts puts its keys on `- ` lines)."""
    if isinstance(node, dict):
        yield from node
        for value in node.values():
            yield from state_keys(value)
    elif isinstance(node, list):
        for value in node:
            yield from state_keys(value)


@pytest.mark.parametrize("slug", CATALOG_SLUGS)
def test_a_catalog_label_never_appears_in_the_prompt(slug, tmp_path):
    """G8, the gate PR1b exists to pass. A candidate's attributes are the *reason* for a label, so an attribute may not
    become a state key (`urgency: 2` in the prompt is a free answer) and a `choice` label's code may not appear anywhere
    in the rendered state. The legacy generators held the same line on the same two terms: `gen_triage.py:106-116`
    prints a red flag's *name*, never its urgency, and a triage state that spelled out the department would have made
    `department` unlearnable — which is exactly how the first cut of `sci-incident-triage` read until G8 was written."""
    records = generate(slug, tmp_path, n=40)
    spec = spec_of(slug)
    drawn_fields = catalog_fields_of(slug)
    attributes = {key for field in drawn_fields for candidate in field["pool"] for key in candidate}
    surfaces = {key for field in drawn_fields for key in field["surface"]}
    companions = {field["name"] for field in fields_of(slug)} - {field["name"] for field in drawn_fields}
    for record in records:
        # `_meta` rides along because `check_record` requires `state` + `questions` and ignores any other top-level key
        assert common.split_data.check_record(record) == []
        assert set(record["state"]) == surfaces | companions, slug
        rendered = render(record["state"])
        leaked = set(state_keys(record["state"])) & attributes
        assert not leaked, (slug, sorted(leaked), rendered)
        for qid, question in record["questions"].items():
            if spec["questions"][qid]["type"] == "choice" and isinstance(question["label"], str):
                assert question["label"] not in rendered, (slug, qid, question["label"], rendered)
        derive_block = record["_meta"]["derive"]
        assert set(derive_block) == {field["name"] for field in drawn_fields}, slug
        for name, candidates in derive_block.items():
            assert candidates, (slug, name)
            pool = {json.dumps(c, sort_keys=True) for c in next(f for f in drawn_fields if f["name"] == name)["pool"]}
            assert {json.dumps(c, sort_keys=True) for c in candidates} <= pool, slug


@pytest.mark.parametrize("slug", CATALOG_SLUGS)
def test_the_fixtures_documented_example_has_the_keys_a_real_record_has(slug, tmp_path):
    """The `state_example` block is what a reader (and the console preview) believes a record looks like, so a surface
    added or dropped from the spec has to move it — the first cut of `sci-incident-triage` still listed a key its own
    spec had just lost, and nothing else in the file would have noticed."""
    keys = set(generate(slug, tmp_path, n=20)[0]["state"])
    assert set(spec_of(slug)["state_example"]) == keys, slug


def test_turning_pairs_on_leaves_a_catalog_run_clean(tmp_path):
    """The pair rule now fires on unsteered records too (design doc D8), so a catalog run with `--pairs` 0.9 ships twins
    on top of its 30 records — 38 at seed 3, the number PR3 measured with the object flip repaired (100 of 200 draws
    lost before, 200 of 200 after). What is promised here is the G8 half: a twin may move the draw, it may not drop a
    draw or smuggle one's attributes into the state."""
    records = generate("fin-credit-adverse", tmp_path, n=30, seed=3, pairs=0.9)
    assert len(records) == 38, len(records)
    for record in records:
        assert record["_meta"]["derive"]["风险事件"]
        assert not set(state_keys(record["state"])) & {"severity", "reviewable", "segment"}
