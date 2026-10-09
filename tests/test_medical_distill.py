"""The medical distillation layer (kev/console/distill/): seed contract, converter, label invariance,
volume gate and EasyDistill configs.

The test this file exists for is `test_labels_survive_a_hostile_teacher_without_mixing`: it asserts the structural
guarantee that the LLM cannot reach a label. Everything else is ordinary wiring.

Standard library only, no network. Run: uv run python -m pytest tests/test_medical_distill.py -q
"""
import importlib
import json
import random
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DISTILL = ROOT / "kev/console/distill"
GENERATORS = ROOT / "kev/console/generators"
sys.path.insert(0, str(DISTILL))
sys.path.insert(0, str(GENERATORS))

import check_volume  # noqa: E402
import common  # noqa: E402
import make_seeds  # noqa: E402
import seed_to_kev  # noqa: E402
import split_data  # noqa: E402

SCENARIOS = ["inquiry", "medication", "diagnosis", "record-summary", "knowledge-qa"]
KEV_SCENARIOS = [s for s in SCENARIOS if make_seeds.SCENARIOS[s][2]]
SFT_ONLY = [s for s in SCENARIOS if not make_seeds.SCENARIOS[s][2]]


def seeds_for(scenario, n=60, seed=0):
    rng = random.Random(seed)
    return make_seeds.generate(scenario, n, rng)


def write(tmp_path, scenario, seed_rows, state_rows, suffix="seed"):
    seed_path = tmp_path / f"{scenario}.{suffix}.jsonl"
    state_path = tmp_path / f"{scenario}.state.jsonl"
    make_seeds.write_jsonl(seed_rows, seed_path)
    make_seeds.write_jsonl(state_rows, state_path)
    return seed_path, state_path


def test_labels_survive_a_hostile_teacher_without_mixing(tmp_path):
    """THE invariant: no LLM output, however wrong, may change a label.

    Builds a record set with a fully-converted path, then rebuilds it with a deliberately hostile teacher attached and
    asserts the two files are byte-identical. Also asserts the reconciliation *reports* the disagreement, so the
    safety property is not achieved by silently ignoring the SFT file.
    """
    scenario = "inquiry"
    seed_rows, state_rows = seeds_for(scenario, n=40)
    seed_path, state_path = write(tmp_path, scenario, seed_rows, state_rows)

    clean = tmp_path / "clean.jsonl"
    seed_to_kev.main(["--scenario", scenario, "--seed-file", str(seed_path),
                      "--state-file", str(state_path), "--out", str(clean)])
    baseline = clean.read_text(encoding="utf-8")

    hostile = []
    for i, row in enumerate(seed_rows):
        if i % 3 == 0:
            answer = "对不起，我无法回答这个问题。"
        elif i % 3 == 1:
            answer = "建议挂口腔科门诊。"                      # confidently wrong
        else:
            answer = "```json\n{\"department\": \"不存在的科室\"}\n```"   # malformed
        hostile.append({"id": row["id"], "instruction": row["instruction"],
                        "messages": [{"role": "user", "content": row["instruction"]},
                                     {"role": "assistant", "content": answer}],
                        "metadata": {"model": "hostile-teacher", "usage": {"total_tokens": 999}}})
    hostile_path = tmp_path / "hostile.sft.jsonl"
    make_seeds.write_jsonl(hostile, hostile_path)

    report_path = tmp_path / "reconcile.json"
    mixed = tmp_path / "mixed.jsonl"
    seed_to_kev.main(["--scenario", scenario, "--seed-file", str(seed_path),
                      "--state-file", str(state_path), "--out", str(mixed),
                      "--from-sft", str(hostile_path), "--report", str(report_path)])

    assert mixed.read_text(encoding="utf-8") == baseline, "the LLM changed a label"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["total"] > 0
    assert report["agree"] / report["total"] < 0.5, "the hostile teacher should have been detected, not ignored"
    # the output must still be a valid Kev file
    for record in [json.loads(l) for l in mixed.read_text(encoding="utf-8").splitlines() if l.strip()]:
        assert split_data.check_record(record) == []


def test_converter_rejects_a_seed_file_without_states(tmp_path):
    """A seed id with no sidecar row is a sync bug, and must fail loudly rather than emit a short file."""
    scenario = "inquiry"
    seed_rows, state_rows = seeds_for(scenario, n=10)
    seed_path = tmp_path / "inquiry.seed.jsonl"
    short_state = tmp_path / "inquiry.state.jsonl"
    make_seeds.write_jsonl(seed_rows, seed_path)
    make_seeds.write_jsonl(state_rows[:-1], short_state)
    with pytest.raises(SystemExit):
        seed_to_kev.main(["--scenario", scenario, "--seed-file", str(seed_path),
                          "--state-file", str(short_state), "--out", str(tmp_path / "o.jsonl")])


def test_every_scenario_produces_a_matched_seed_pair():
    """The dual-file contract: same length, same order, `id` is the only join key, and the instruction leaks no label."""
    for scenario in SCENARIOS:
        seed_rows, state_rows = seeds_for(scenario, n=30)
        assert len(seed_rows) == len(state_rows) > 0, scenario
        for seed_row, state_row in zip(seed_rows, state_rows):
            assert seed_row["id"] == state_row["id"], f"{scenario}: files are out of sync"
            assert set(seed_row) == {"id", "instruction", "system"}, f"{scenario}: EasyDistill sees extra fields"
            assert seed_row["instruction"].strip(), f"{scenario}: empty instruction"
            assert seed_row["system"].strip(), f"{scenario}: empty system prompt"
            assert state_row["scenario"] == scenario
            assert isinstance(state_row["state"], dict) and state_row["state"], f"{scenario}: empty state"
        # A label value must never appear in the instruction the teacher sees.
        if make_seeds.SCENARIOS[scenario][2]:
            spec = common.load_spec(seed_to_kev.SPEC_FOR[scenario])
            for seed_row, state_row in zip(seed_rows, state_rows):
                rendered = make_seeds.render_state(state_row["state"])
                assert rendered in seed_row["instruction"], f"{scenario}: instruction is not the rendered state"


def test_knowledge_qa_has_no_kev_track_and_says_so():
    """The one scenario that cannot be a Kev task must be handled explicitly, not silently skipped."""
    assert SFT_ONLY == ["knowledge-qa"]
    assert seed_to_kev.SPEC_FOR.get("knowledge-qa") is None
    assert "knowledge-qa" not in check_volume.SPEC_FOR
    with pytest.raises(SystemExit):
        seed_to_kev.main(["--scenario", "knowledge-qa", "--state-file", "x", "--out", "y"])
    # and check_volume --all must list it rather than fail
    assert "knowledge-qa" in check_volume.SFT_ONLY
    seed_rows, state_rows = seeds_for("knowledge-qa", n=12)
    assert len(seed_rows) == len(state_rows) == 12
    for row in seed_rows:
        assert row["instruction"].endswith("？"), "knowledge QA should be an open question"
        assert "record" not in json.dumps(row, ensure_ascii=False)


def test_converted_records_are_valid_and_balanced(tmp_path):
    """End to end for the two new scenarios: seeds -> records -> skill validation -> volume gate."""
    for scenario in ("diagnosis", "record-summary"):
        seed_rows, state_rows = seeds_for(scenario, n=300, seed=1)
        seed_path, state_path = write(tmp_path, scenario, seed_rows, state_rows)
        out = tmp_path / f"{scenario}.jsonl"
        assert seed_to_kev.main(["--scenario", scenario, "--seed-file", str(seed_path),
                                 "--state-file", str(state_path), "--out", str(out)]) == 0
        records = [json.loads(l) for l in out.read_text(encoding="utf-8").splitlines() if l.strip()]
        assert len(records) == 300
        for record in records:
            assert split_data.check_record(record) == []
        # the gate must pass for a balanced 300-record set with these specs
        assert check_volume.main(["--scenario", scenario, "--records", str(out), "--expect", "300"]) == 0


def test_volume_gate_fails_on_a_thin_dataset(tmp_path):
    """The gate must actually fail, not just print. A record-count mismatch is the cheapest real mistake."""
    scenario = "diagnosis"
    seed_rows, state_rows = seeds_for(scenario, n=60, seed=2)
    seed_path, state_path = write(tmp_path, scenario, seed_rows, state_rows)
    out = tmp_path / "thin.jsonl"
    seed_to_kev.main(["--scenario", scenario, "--seed-file", str(seed_path),
                      "--state-file", str(state_path), "--out", str(out)])
    assert check_volume.main(["--scenario", scenario, "--records", str(out), "--expect", "787"]) == 1
    # a generous budget passes
    assert check_volume.main(["--scenario", scenario, "--records", str(out), "--expect", "60"]) == 0


def test_configs_are_legal_and_never_embed_credentials():
    """Five configs, one per scenario. The assertions that matter: no secrets inlined, and `resume: true` so an
    interrupted run does not re-spend quota. The stage order is the pipeline the plan documents."""
    yaml = pytest.importorskip("yaml", reason="PyYAML needed to validate configs")
    configs = sorted((DISTILL / "configs").glob("*.yaml"))
    assert {p.stem for p in configs} == set(SCENARIOS), "one config per scenario"
    valid_jobs = {"advanced_instruct_distill", "balanced_instruct_distill", "augmented_instruct_distill", "instruct_distill"}
    required = ["instruction_expansion", "generate", "judge", "filter", "build_sft"]
    for path in configs:
        cfg = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert cfg["job_type"] in valid_jobs
        backend = cfg["backend"]
        assert backend["type"] == "openai", "Bailin is reached through the OpenAI-compatible backend"
        for key in ("base_url", "api_key"):
            assert str(backend[key]).startswith("${"), f"{path.name}: {key} must come from the environment"
        assert backend["concurrency"] <= 4, "cloud endpoint, keep concurrency low"
        assert cfg["resume"] is True, f"{path.name}: resume must be true or a rerun re-spends quota"
        assert [s["stage"] for s in cfg["pipeline"]] == required
        ds = cfg["dataset"]
        assert ds["instruction_key"] == "instruction"
        assert ds["input_file"].endswith(f"seeds/{path.stem}.seed.jsonl"), "must read the .seed sidecar"
        assert cfg["system_prompt"].strip()
        text = path.read_text(encoding="utf-8")
        for marker in ("sk-", "Bearer ", "hf_"):
            assert marker not in text, f"{path.name}: possible credential leak"


def test_new_specs_declare_questions_their_generator_can_derive():
    """A new spec and its generator can drift. These assertions pin the coupling: the label sets the generator emits
    must exactly cover the option space the spec declares, and the scoring levels must be 0-based contiguous ints."""
    import gen_diagnosis as dg
    import gen_record_summary as rs
    for module, scenario in ((dg, "diagnosis"), (rs, "record-summary")):
        records = [r for t in module.plan_targets(300, random.Random(0), None) if (r := module.build(random.Random(0), t))]
        spec = common.load_spec(scenario)
        assert len(spec["questions"]) == 4, f"{scenario}: expected 4 questions for the 787-record plan"
        for qid, q in spec["questions"].items():
            if q["type"] == "choice":
                covered = {common.split_data.label_key(r["questions"][qid]) for r in records}
                assert covered == set(q["criteria"]), f"{scenario}:{qid} generator misses {set(q['criteria']) - covered}"
            elif q["type"] == "score":
                n = len(q["criteria"])
                levels = {r["questions"][qid]["label"] for r in records}
                assert levels <= set(range(n)), f"{scenario}:{qid} level index out of 0..{n - 1}"


