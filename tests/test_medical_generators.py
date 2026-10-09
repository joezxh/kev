"""The medical record generators (kev/console/generators): rule-derived labels, minimal pairs, label quotas,
the dual-size run matrix and the gold-set audit. Standard library only, no network.

These tests are the guardrail for a real risk in this project: a generator whose labels drift from its own
threshold table would silently teach the model the wrong rule, and nothing downstream would notice because
split_data.py only checks *shape*, not correctness.

Run: uv run python -m pytest tests/test_medical_generators.py -q
"""
import importlib
import json
import random
import sys
from collections import Counter
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
GENERATORS = ROOT / "kev/console/generators"
sys.path.insert(0, str(GENERATORS))
sys.path.insert(0, str(ROOT / "skills/kev-finetune/scripts"))
import common  # noqa: E402
import gen_critical_value as cv  # noqa: E402
import gen_medication_review as mr  # noqa: E402
import gen_nursing_quality as nq  # noqa: E402
import gen_triage as tri  # noqa: E402
import make_goldset as gold  # noqa: E402
import run_matrix  # noqa: E402
import split_data  # noqa: E402

SPECS = sorted((ROOT / "docs/medical/specs").glob("*.json"))
SPEC_NAMES = [p.stem for p in SPECS]
GENERATED = {"critical-value": cv, "medication-review": mr, "nursing-quality": nq, "triage": tri}


def build(spec_name, n=240, seed=0, share=0.5):
    """Generate n records for a scenario through its real generators, mirroring each main() loop.

    Every generator's build() returns (record, handle) or record; the handle is what pair_twin() needs, so the
    minimal pairs a real run would emit are produced here too.
    """
    module = GENERATED[spec_name]
    rng = random.Random(seed)
    records = []
    for target in module.plan_targets(n, rng, share):
        built = module.build(rng, target)
        record, handle = built if isinstance(built, tuple) else (built, None)
        if record is None:
            fallback = module.build(rng, None)
            record = fallback[0] if isinstance(fallback, tuple) else fallback
            handle = None
        if record is None:
            continue
        records.append(record)
        if handle is not None and target and hasattr(module, "pair_twin"):
            twin = module.pair_twin(rng, record, handle)
            if twin is not None:
                records.append(twin)
    return records


def test_every_spec_exists_and_matches_the_skill_schema():
    assert SPEC_NAMES, "no specs found"
    for path in SPECS:
        spec = json.loads(path.read_text(encoding="utf-8"))
        for field in ("name", "domain", "state", "questions", "guidance", "variety"):
            assert spec.get(field), f"{path.name}: missing {field}"
        assert spec["name"] == path.stem, f"{path.name}: name {spec['name']!r} does not match the filename"
        assert len(spec["questions"]) >= 3, f"{path.name}: fewer than 3 questions wastes the multi-question economy"
        for qid, q in spec["questions"].items():
            probe = {**q, "label": {"noul": True, "choice": next(iter(q.get("criteria") or {}), None),
                                    "score": 0}[q["type"]]}
            assert split_data.check_question(qid, probe) == [], f"{path.name}: {qid} is not a valid question"


def test_choice_questions_that_need_a_no_finding_option_have_one():
    """A choice question is asked on *every* record, so if "nothing was found" is a reachable state it needs its own
    option -- otherwise normal records get a meaningless label. Some questions legitimately have no such state (every
    coding case really is a finding), so the expectation is spelled out per question rather than guessed.
    """
    expected = {
        ("critical-value", "critical_item"): "none",          # normal reports exist
        ("medication-review", "issue_type"): "none",           # clean prescriptions exist
        ("medication-review", "verdict"): "pass",              # pass *is* the no-finding option here
        ("nursing-quality", "issue_type"): "none",             # compliant checks exist
    }
    for (name, qid), option in expected.items():
        criteria = common.load_spec(name)["questions"][qid]["criteria"]
        assert option in criteria, f"{name}:{qid} lost its no-finding option {option!r}"
    # icd-coding: coding_reasonable has no no-finding option because every record is a real coding finding, while
    # evidence_gap does (a clean case has a complete evidence chain).
    coding = common.load_spec("icd-coding")["questions"]
    assert "none" not in coding["coding_reasonable"]["criteria"]
    assert "none" in coding["evidence_gap"]["criteria"]


def test_generated_records_pass_skill_validation_and_are_well_distributed():
    """The core regression: whatever the generators emit must satisfy split_data's own checks -- 0 problems, every
    label at or above its 5% floor, and no option that is never correct."""
    for name in GENERATED:
        records = build(name, n=300)
        assert records, f"{name}: no records generated"
        for record in records:
            assert split_data.check_record(record) == []
        for qid, table in common.label_table(records).items():
            total = sum(table.values())
            rare = [k for k, v in table.items() if v / total < 0.05]
            assert not rare, f"{name}:{qid} labels under 5%: {rare}"
            spec = common.load_spec(name)
            missing = set(common.label_keys(spec, qid)) - set(table)
            assert not missing, f"{name}:{qid} never labelled: {sorted(missing)}"


def test_critical_value_labels_follow_the_threshold_table():
    """is_critical must be exactly "some panel is outside its critical range", and notify_within the fastest tier."""
    for record in build("critical-value", n=300):
        state, questions = record["state"], record["questions"]
        hits = []
        for name, text in state["labs"].items():
            panel = next((p for p in cv.PANELS if p[0] == name), None)
            assert panel is not None, f"unknown panel {name}"
            value = float(text.split()[0])
            if cv.outside(panel, value):
                hits.append((name, value))
        assert questions["is_critical"]["label"] is bool(hits), "is_critical disagrees with the threshold table"
        if not hits:
            assert questions["critical_item"]["label"] == cv.NONE_ITEM
            assert questions["notify_within"]["label"] == cv.NO_NOTIFY
        else:
            fastest = min(cv.notify_tier(n, v) for n, v in hits)
            assert questions["notify_within"]["label"] == fastest, "notify_within is not the fastest tier"
            assert questions["critical_item"]["label"] == cv.PANEL_CATEGORY[
                next(n for n, v in hits if cv.notify_tier(n, v) == fastest)]


def test_evidence_drop_records_carry_a_soft_target_and_say_so():
    """Records with a decision-critical element removed must be labelled 50/50 and flagged, never hard-labelled."""
    dropped = [r for r in build("critical-value", n=300) if r["questions"]["evidence_sufficient"]["label"] is False]
    assert dropped, "no evidence-drop records were generated"
    for record in dropped:
        assert record["state"]["missing_context"], "evidence_sufficient=false but nothing was actually removed"
        assert record["questions"]["is_critical"]["target"] == {"true": 0.5, "false": 0.5}
        assert split_data.check_record(record) == []


def test_tier_windows_agree_with_the_threshold_table():
    """Every window the planner can sample from must really produce its tier -- this is what stops a threshold edit
    from silently generating mislabelled records."""
    for tier, name in cv.TIER_WINDOWS:
        panel = next(p for p in cv.PANELS if p[0] == name)
        rng = random.Random(0)
        for _ in range(60):
            value = cv.realize_tier(rng, panel, tier)
            assert value is not None, f"tier {tier} {name} could not be realized"
            assert cv.outside(panel, value) and cv.notify_tier(name, value) == tier


def test_medication_rule_engine_is_deterministic_and_consistent():
    for _ in range(200):
        rng = random.Random()
        plan = (rng.choice(list(mr.DRUGS)), rng.randint(50, 4000), rng.choice([1, 2, 3]),
                rng.choice([[], ["pregnant"], ["child"], ["elderly"], ["renal"]]),
                rng.choice(["", "青霉素（皮疹）"]), rng.choice(list(mr.INDICATIONS)), None)
        first = mr.evaluate(plan)
        assert first == mr.evaluate(plan), "rule engine is not deterministic"
        verdict, issues, severity = first
        assert severity == mr.VERDICT_SEVERITY[verdict], "severity must follow verdict"
        if verdict == "pass":
            assert severity == 0 and not issues
        if "contraindication" in issues or "dose_over" in issues or "duplicate" in issues:
            assert verdict == "reject" and severity == 3


def test_medication_dates_are_precomputed_not_left_to_the_model():
    """0.8B's date arithmetic is weak (0.35 on deadline tasks), so day counts must arrive already calculated."""
    for record in build("medication-review", n=200):
        state = record["state"]
        assert isinstance(state["days_on_drug"], int), "days_on_drug must be a number, not a date to subtract"
        assert not any(k for k in state if k in ("started", "prescribed", "lmp", "admission"))


def test_nursing_severity_and_reportable_stay_within_spec_limits():
    for record in build("nursing-quality", n=300):
        labels = record["questions"]
        if labels["issue_type"]["label"] == "none":
            assert labels["severity"]["label"] == 0 and labels["reportable"]["label"] is False
        assert 0 <= labels["severity"]["label"] <= 3


def test_triage_priority_rules_hold():
    """A red flag must force emergency; a pediatric chief complaint must go to pediatrics; acuity 0 must not
    escalate to a human."""
    for record in build("triage", n=400):
        labels, state = record["questions"], record["state"]
        red = labels["red_flag"]["label"]
        assert state["red_flags"] != "无" or red is False, "red_flag=true but nothing was described"
        if red:
            assert labels["department"]["label"] == "emergency"
            assert labels["immediate_human"]["label"] is True
            assert labels["acuity"]["label"] == 2
        if labels["acuity"]["label"] == 0:
            assert labels["immediate_human"]["label"] is False
        assert labels["department"]["label"] in common.load_spec("triage")["questions"]["department"]["criteria"]


def test_generators_are_deterministic_under_a_seed():
    """Same seed, same file -- otherwise "change one rule, see the effect" is not a controlled experiment."""
    for name in GENERATED:
        first = build(name, n=120, seed=7)
        second = build(name, n=120, seed=7)
        assert [json.dumps(r, sort_keys=True, ensure_ascii=False) for r in first] == \
               [json.dumps(r, sort_keys=True, ensure_ascii=False) for r in second], f"{name} is not deterministic"
        assert build(name, n=120, seed=8) != first or True  # a different seed may coincide; never assert it must differ


def test_minimal_pairs_differ_in_exactly_one_field_and_flip_the_label():
    """common.minimal_pair is the shared guard: a twin that changes more than one field, or fails to flip any
    label, must be skipped rather than written -- a wrong pair teaches a wrong boundary."""
    rng = random.Random(3)
    records = build("critical-value", n=200, seed=3)
    index = {}
    rebuilt = []
    for record in records:
        rebuilt.append(record)
    # construct a twin by hand and let minimal_pair judge it
    base = rebuilt[0]
    twin_state = json.loads(json.dumps(base["state"], ensure_ascii=False))
    key, text = next(iter(twin_state["labs"].items()))
    panel = next(p for p in cv.PANELS if p[0] == key)
    moved = cv.critical_value(rng, panel) if not cv.outside(panel, float(text.split()[0])) \
        else cv.crossed(rng, panel)
    twin_state["labs"][key] = f"{moved} {panel[1]}".strip()
    labels = {qid: dict(q) for qid, q in base["questions"].items()}
    is_out = cv.outside(panel, moved)
    for qid, q in labels.items():
        q.pop("target", None)
    labels["is_critical"]["label"] = is_out
    twin = common.labelled(common.load_spec("critical-value"), twin_state,
                           {qid: q["label"] for qid, q in labels.items()})
    assert common.changed_fields(base["state"], twin["state"]) == ["labs"]
    assert common.minimal_pair([base], lambda r: twin) == 1
    # a twin identical to the original must be rejected
    assert common.minimal_pair([base], lambda r: json.loads(json.dumps(r, ensure_ascii=False))) == 0


def test_run_names_reject_dots_and_accept_size_suffixes():
    """kev_modal.py's NAME regex forbids dots, so 'cv-0.8b-v1' would fail on Modal. run_matrix must catch it here."""
    assert run_matrix.check_name("critical-value-8b-v1")
    assert run_matrix.check_name("triage_4b-v2")
    for bad in ("critical-value-0.8b-v1", "cv.4b", ".leading", "has space", ""):
        with pytest.raises(SystemExit):
            run_matrix.check_name(bad)


def test_run_matrix_shares_one_dataset_across_both_sizes():
    plan, names = run_matrix.steps("critical-value", ["8b", "4b"], "data/cv", 1, "python3", "kev-serve-key")
    steps_by_name = {name: cmd for name, cmd, _ in plan}
    assert names == {"8b": "critical-value-8b-v1", "4b": "critical-value-4b-v1"}
    # both trains read the same --data directory: that is what makes the cross-size compare valid
    assert "--data" in steps_by_name["train_8b"] and "--data" in steps_by_name["train_4b"]
    assert steps_by_name["train_8b"][steps_by_name["train_8b"].index("--data") + 1] == "data/cv"
    assert steps_by_name["train_4b"][steps_by_name["train_4b"].index("--data") + 1] == "data/cv"
    assert "--init-from" in steps_by_name["train_8b"] and "jaredpalmer/kev-0.8b" in steps_by_name["train_8b"]
    assert "jaredpalmer/kev-4b" in steps_by_name["train_4b"]
    # two endpoints need distinct app names, or the second deploy replaces the first
    apps = [env["KEV_APP_NAME"] for name, _, env in plan if name.startswith("deploy_")]
    assert len(apps) == 2 and apps[0] != apps[1]
    assert all("KEV_SERVE_RUN" in env for name, _, env in plan if name.startswith("deploy_"))


def test_run_matrix_dry_run_prints_every_step():
    assert run_matrix.main(["--scenario", "critical-value", "--sizes", "8b,4b", "--dry-run"]) == 0
    # a 4B-only scenario must refuse the 0.8B track rather than silently producing a bad run
    with pytest.raises(SystemExit):
        run_matrix.main(["--scenario", "icd-coding", "--sizes", "8b,4b", "--dry-run"])
    assert run_matrix.main(["--scenario", "icd-coding", "--sizes", "4b", "--dry-run"]) == 0
    with pytest.raises(SystemExit):
        run_matrix.main(["--scenario", "triage", "--sizes", "27b", "--dry-run"])


def test_goldset_sampling_is_stratified_and_audit_reports_per_question():
    records = build("critical-value", n=300, seed=1)
    picked = gold.sample(records, 120, seed=0)
    assert len(picked) == 120
    assert len({common.split_data.state_key(r["state"]) for r in picked}) == 120, "sample must not repeat states"
    # rare label combinations must be represented, not just the common ones
    source = {s for s in (gold.stratum(r) for r in records)}
    assert len({gold.stratum(r) for r in picked}) >= min(len(source), 2)

    flipped = json.loads(json.dumps(records, ensure_ascii=False))
    for record in flipped:
        record["questions"]["is_critical"]["label"] = not record["questions"]["is_critical"]["label"]
    rows, per_question, shared = gold.disagreement(records, flipped)
    assert shared == len(records)
    assert per_question["is_critical"] == len(records), "every is_critical label was flipped"
    assert len(rows) == len(records)
    assert all(r["question"] == "is_critical" for r in rows)
    # identical inputs must produce no disagreement at all
    assert gold.disagreement(records, records)[0] == []


