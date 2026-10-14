"""The spec-driven engine on scenarios that are not medical (tests/fixtures/engine-matrix, design doc D1/D2/D7/D10/D11/D12/D13/D15).

What this file guards is the B2 premise the spike measured: 20 of the 32 finance / education / research / legal
scenarios died inside the sampler (`ops.normal_value` read `field["normal"]` for every field, whatever its type — F1),
and the ones that survived came out shaped like a lab report because `make_record` hardcoded `patient` / `labs` (F2).
Both are engine defects, not domain ones, so the guard is a matrix of 36 scenarios rather than a medical test with a
new name: 32 the spike ran, plus four `catalog` ones PR1b added — a spike cannot have measured a field type the engine
refused to sample. `resolve_spec` (D7) is here too: three spec truth sources meant a preview showed the committed copy
of what the user had just edited, and a scenario that lived only in the DB raised FileNotFoundError.

PR1b's half of the file is the derive channel (D10/D11) and gate G8: a catalog field's candidates carry the label in
their own attributes, so the guard is that neither those attribute names nor a `choice` label's code ever reach
`render(state)`. A state that shows `urgency: 2` or `owning_team: infra` does not train a decision, it trains a copy.

What this file does NOT claim: that every scenario's labels are right. PR2 taught the evaluator typed values, date
arithmetic, generator expressions and the difference between "this record lacks the evidence" and "this spec is
unusable" (design doc F3/F4, §5.4/§5.5), and the ledger fell from twelve questions to two. The ones left are
`test_the_degenerate_ledger_is_what_pr2_left`'s set, and neither is an evaluator failure any more: one question needs a
threshold its sampler almost never reaches (design doc §6, defect 8), the other a rule the spec never wrote. Green
here means "no scenario loses its labels because the engine cannot read the record", which is PR2b's exit condition,
not "every scenario is trainable".

Run: uv run python -m pytest tests/test_engine_matrix.py -q
"""
import json
import random
from datetime import date
from pathlib import Path

import pytest
from simpleeval import SimpleEval

from kev.api import render
from kev.console import paths
from kev.console.generators import common, derive, engine, ops, rules, values
from kev.console.generators.pair import PairBuilder
from kev.console.generators.sampler import BoundarySampler, place

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests/fixtures/engine-matrix"
SIDECAR = json.loads((FIXTURES / "matrix.json").read_text(encoding="utf-8"))
SLUGS = [entry["slug"] for entry in SIDECAR]
SHAPES = {entry["slug"]: entry["shape"] for entry in SIDECAR}
CRASHED_IN_SPIKE = {entry["slug"] for entry in SIDECAR if entry["spike_error"]}
CATALOG_SLUGS = [entry["slug"] for entry in SIDECAR if entry["shape"] == "catalog"]

# Questions whose label is still single-valued, and why. Equality, not a subset: a scenario that collapses again
# fails here, and a scenario whose debt is paid must be moved to one of the PAID maps below rather than quietly
# deleted from a list someone maintains by hand.
#
# PR2a paid seven of the twelve PR1a left (design doc §5.3) — a typed number, a date the rules can subtract, and six
# specs that compared a measurement against its own unit string. PR2b's evaluator paid four more (§5.5): the generator
# expressions `SimpleEval` refused outright and the records that lack a field a rule reads, which used to fall through
# to the `when: "True"` rule instead of being recognised as "no evidence, no label". What survives is not an evaluator
# failure at all. `final_band`: the spec scores three components on `normal [1, 9]` where `sample_numeric` pins roughly
# half the draws on the lower bound (design doc §6, defect 8), so `0.5*内容分 + 0.3*结构分 + 0.2*语言分` almost never
# reaches the 7 that rule asks for. `plagiarism_flag`: both of the spec's rules write `false` — the scenario never had a
# rule that could raise the flag. Neither is a rule that cannot read a value, so both belong to PR3's distribution and
# spec-authoring work, not to the evaluator.
LEDGER = {
    "edu-essay-scoring": ["final_band", "plagiarism_flag"],
}

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


def spec_of(slug):
    return json.loads((FIXTURES / f"{slug}.json").read_text(encoding="utf-8"))


def fields_of(slug):
    return spec_of(slug)["generator"]["fields"]


def catalog_fields_of(slug):
    return [field for field in fields_of(slug) if values.field_type(field) == "catalog"]


# ---------------------------------------------------------------- fixtures (D14)


def test_the_matrix_covers_every_shape_and_keeps_the_spike_record():
    assert len(SLUGS) == 36 and len(set(SLUGS)) == 36
    assert len(CRASHED_IN_SPIKE) == 20, "the sidecar lost which scenarios the spike saw die"
    for entry in SIDECAR:
        assert (FIXTURES / f"{entry['slug']}.json").exists()
        if entry.get("added"):
            # a scenario written after the spike cannot be part of what the spike saw die
            assert entry["spike_error"] == "", entry["slug"]
    shapes = {shape: sum(1 for s in SHAPES.values() if s == shape) for shape in set(SHAPES.values())}
    # four domains x eight shapes: a shape with one scenario would prove almost nothing about the dispatch
    assert all(count >= 4 for count in shapes.values()), shapes
    # T1, the eight-type gate: PR1a shipped seven of these and refused the eighth
    assert set(values.SAMPLERS) == {"numeric", "enum", "bool", "text", "date", "list", "object", "catalog"}
    assert len(CATALOG_SLUGS) == 4
    for slug in CATALOG_SLUGS:
        assert len(catalog_fields_of(slug)) == 1, f"{slug}: a catalog fixture with two pools is a different test"


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
    stays a companion field (design doc D6 gives selectors the real choice in PR3)."""
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


def test_the_degenerate_ledger_is_what_pr2_left(tmp_path):
    """F3's debt as a set, both directions: the scenarios still collapsed are exactly LEDGER, and the ones PR2a and
    PR2b paid really do move on both sides now — so the ledger is only allowed to shrink by moving an entry into a PAID
    map, and a paid scenario that collapses again fails here instead of being quietly written back into the debt list."""
    seen = {}
    tables_by_slug = {}
    for slug in SLUGS:
        tables = common.label_table(generate(slug, tmp_path, n=60))
        tables_by_slug[slug] = tables
        flat = sorted(qid for qid, counter in tables.items() if len(counter) == 1)
        if flat:
            seen[slug] = flat
    assert seen == LEDGER
    for paid in (PAID_BY_PR2A, PAID_BY_PR2B):
        for slug, questions in paid.items():
            for qid in questions:
                assert len(tables_by_slug[slug][qid]) >= 2, (slug, qid, tables_by_slug[slug][qid])


def test_the_same_seed_reproduces_the_same_file(tmp_path):
    for slug in ("fin-aml-sar", "sci-review-accept"):
        first = generate(slug, tmp_path, n=30, seed=11)
        second = generate(slug, tmp_path, n=30, seed=11)
        assert [json.dumps(r, sort_keys=True, ensure_ascii=False) for r in first] == \
               [json.dumps(r, sort_keys=True, ensure_ascii=False) for r in second], slug


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
    """The 36 matrix specs are what a user copies, so the check that gates them has to be clean on all of them —
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


# ---------------------------------------------------------------- minimal pairs (D8 partially)


def test_a_pair_flips_a_numeric_field_and_refuses_a_field_it_cannot_move():
    """PR1a keeps the flip numeric (PR3 makes it typed, design doc D8), but it now works on the flat field view, so a
    scenario with no `labs` key can have minimal pairs at all."""
    rng = random.Random(5)
    field = {"name": "下滑幅度", "unit": "%", "decimals": 1, "normal": [0, 8], "critical": {"high": [[15, 1e9]]}}
    builder = PairBuilder({})
    state, fields = {"下滑幅度": 30.0}, {"下滑幅度": field}
    twins = [builder.build(state, fields, "下滑幅度", rng) for _ in range(200)]
    flipped = [t for t in twins if t is not None]
    assert flipped, "a high-side critical value never produced a twin in 200 draws"
    for twin in flipped:
        # the view is typed since PR2a: the twin carries the safe number itself, and the unit is put back by
        # `make_record`, not by the flip (design doc D3)
        assert isinstance(twin["下滑幅度"], (int, float)) and not isinstance(twin["下滑幅度"], bool)
        assert twin["下滑幅度"] != state["下滑幅度"]
        assert not ops._is_in_critical_range(twin["下滑幅度"], field)
    for name in (None, "absent"):
        assert builder.build(state, fields, name, rng) is None
    clause = {"条款": {"name": "条款", "type": "text", "values": ["a", "b"]}}
    assert builder.build({"条款": "a"}, clause, "条款", rng) is None


def test_turning_pairs_on_never_breaks_a_run(tmp_path):
    """The count of twins is not asserted, because two known gaps cap it and both belong to PR3 (design doc D8): the
    flip is numeric only, and `ops.crossed` builds its safe window off `normal` in a way that lands back inside a
    `critical.low` bound, so a field whose danger is on the low side (退赔比例 < 30 %) never escapes it. What PR1a
    promises is that switching pairs on cannot poison the file — every appended twin is still a valid record."""
    records = generate("law-sentencing", tmp_path, n=40, seed=3, pairs=0.9)
    assert records
    for record in records:
        assert common.split_data.check_record(record) == []


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
    """The pair rule fires only on a steered record and these specs declare no plan targets, so a catalog run ships no
    twins today (PR3's selectors are what change that, design doc D8). What is promised here is the safe half: switching
    pairs on cannot drop a draw or smuggle one into the state."""
    records = generate("fin-credit-adverse", tmp_path, n=30, seed=3, pairs=0.9)
    assert len(records) == 30
    for record in records:
        assert record["_meta"]["derive"]["风险事件"]
        assert not set(state_keys(record["state"])) & {"severity", "reviewable", "segment"}
