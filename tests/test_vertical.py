"""kev.vertical: the industry registry, the risk router and the threshold book's contract.

These are the rules a clinical or compliance reviewer has to be able to check by reading a table, so each test here
pins one of them and says what would go wrong without it. No weights and no GPU: the router is a decision layer over
a served checkpoint (kev.serve), so its correctness is a property of the rules, not of the model behind them.

Run: uv run python -m pytest tests/test_vertical.py -q
"""
import json

import pytest

from kev.vertical import (LARGE, RISK_FLOOR, SIZES, SMALL, Adapter, Industry, IndustryRegistry, Router, Scenario,
                          ThresholdBook, UnknownIndustry, UnknownScenario, _adapter_name, _cutoff_from_report,
                          escalation_report, industries)


def result(size="8b", temperature=1.0, cutoff=0.82, run="runs/critical-value-8b-v1", base="jaredpalmer/kev-0.8b"):
    """A `result.json` in the shape kev_modal.py::run_train writes: the fitted temperature on top, and the selective
    prediction block the development report carries (kev.metrics.metrics)."""
    return {"run": run, "base": base, "temperature": temperature, "lora": 16, "head_dim": 256,
            "development": {"calibrated": {"selective": {"0.8": {"coverage": 0.8, "confidence_cutoff": cutoff}}},
                            "raw": {"selective": {"0.8": {"coverage": 0.81, "confidence_cutoff": min(cutoff + 0.02, 1.0)}}}}}


@pytest.fixture
def registry():
    """A small deployment: one low-risk scenario with a fitted threshold, one high-risk one, one low-risk with no
    measurement yet. Built in code so the tests do not depend on the shipped five industries' contents."""
    reg = IndustryRegistry()
    ind = Industry(name="medical", title="医疗健康")
    ind.add(Scenario("medication-review", "medical", risk="low", human_review=True, evidence_question="evidence_sufficient"))
    ind.add(Scenario("critical-value", "medical", risk="high", human_review=True))
    ind.add(Scenario("nursing-quality", "medical", risk="low", human_review=True))
    ind.add(Scenario("discharge-summary", "medical", risk="medium", human_review=False))
    ind.register(Adapter("medical", "medication-review", "8b", "runs/med-8b-v1", temperature=2.35, confidence_cutoff=0.82,
                         base="jaredpalmer/kev-0.8b", lora=16))
    ind.register(Adapter("medical", "medication-review", "4b", "runs/med-4b-v1", temperature=2.41, confidence_cutoff=0.86,
                         base="jaredpalmer/kev-4b", lora=16))
    reg.add(ind)
    return reg


# --- the risk table ---------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("industry, scenario, risk", [("medical", "critical-value", "high"), ("medical", "triage", "high"),
                                                       ("medical", "icd-coding", "high"), ("medical", "medication-review", "low"),
                                                       ("medical", "nursing-quality", "low"), ("support", "ticket-triage", "low"),
                                                       ("finance", "credit-review", "low"), ("finance", "fraud-detection", "high"),
                                                       ("legal", "clause-classification", "low"), ("legal", "contract-review", "high")])
def test_shipped_scenarios_carry_the_risk_the_medical_package_measured(industry, scenario, risk):
    """The built-in registry agrees with docs/medical/README.md's size table: rule-derivable scenarios (危急值 is the
    exception — high risk even though its labels are derivable, because a miss is not recoverable) are `low`, and
    everything needing inference is `high`. This pins the **declared tier**, not the routing outcome: a site with no
    trained adapter yet still routes every low-risk scenario to 4B (the fail-safe), so `plan()`'s size here would
    say nothing about the tier. Re-tiering a scenario must fail this test and re-argue the reasoning."""
    assert industries().industry(industry).scenarios[scenario].risk == risk


def test_every_industry_declares_at_least_one_low_and_one_high_risk_scenario():
    """A vertical with only high-risk scenarios is a vertical whose router never uses the small model, and one with
    only low-risk ones is a vertical that routes everything to 0.8B. Either is a mistake worth failing a build over,
    because the cost and the safety argument are both made at the tier level."""
    for name in industries().names():
        risks = {s.risk for s in industries().industry(name).scenarios.values()}
        assert "low" in risks and "high" in risks, f"{name} declares risks {sorted(risks)}"


def test_medical_keeps_human_review_on_every_scenario():
    """漏报危急值 ≫ 误报: nothing in medicine is auto-disposed. A medical scenario with human_review=False is a
    policy change, not a refactor, and belongs in the registry file with a sign-off, not in a code edit."""
    for name, sc in industries().industry("medical").scenarios.items():
        assert sc.human_review, f"medical/{name} would answer without a human in the loop"


# --- routing ----------------------------------------------------------------------------------------------------------

def test_high_risk_scenarios_never_start_on_the_small_model(registry):
    """A high/critical scenario goes straight to 4B. The router must not consult the 0.8B model first "just in
    case it is confident": a cheap model's uncertainty is not evidence that a critical value is absent, and a
    confidence check on a model that may not answer is a check with no meaning."""
    d = Router(registry).plan("medical", "critical-value")
    assert d.size == LARGE and not d.escalate and "high" in d.reason


def test_low_risk_scenarios_start_small_with_the_fitted_threshold(registry):
    """0.8B answers, at the threshold its own development rows produced (selective 0.8 confidence cutoff), not at a
    constant. The threshold appears in the audit string so a reviewer can see where the number came from."""
    d = Router(registry).plan("medical", "medication-review")
    assert d.size == SMALL and d.threshold == 0.82 and "adapter" in d.reason and d.review


def test_a_low_risk_scenario_with_no_measurement_escalates_rather_than_guessing(registry):
    """Fail-safe: no fitted cutoff means the router has no bar, so it cannot certify a cheap answer. It sends the
    record to 4B and says why. The alternative — defaulting the cutoff to 0.9 or to 0.0 — is exactly the kind of
    invented number this module exists to keep out of a clinical path."""
    d = Router(registry).plan("medical", "nursing-quality")
    assert d.size == LARGE and d.escalate and d.reason == "no fitted threshold"


def test_medium_risk_scenarios_may_start_small(registry):
    """A medium-risk scenario is allowed to use 0.8B when a threshold exists (grading, say); RISK_FLOOR says
    medium shares the low floor. The distinction that matters is not the label but whether a human is in the loop."""
    reg = registry
    reg.industry("medical").register(Adapter("medical", "discharge-summary", "8b", "runs/dc-8b", confidence_cutoff=0.7,
                                             base="jaredpalmer/kev-0.8b"))
    assert Router(reg).plan("medical", "discharge-summary").size == SMALL


def test_unknown_industry_and_scenario_route_to_the_large_model_with_a_reason(registry):
    """A router that 404s on an unrecognised scenario is a router callers will route around. An unclassified record
    goes to the expensive, safer model and the decision says it was unclassified."""
    router = Router(registry)
    for industry, scenario in [("aerospace", "landing"), ("medical", "not-a-scenario")]:
        d = router.plan(industry, scenario)
        assert d.size == LARGE and d.reason == "unregistered scenario" and d.review


def test_a_forced_size_overrides_the_table_and_says_it_did(registry):
    """A reviewer re-asking with 4B on purpose, or a caller with only one size loaded. The decision still records
    that the router did not choose, so the audit trail never claims a routing decision nobody made."""
    d = Router(registry).plan("medical", "medication-review", forced=LARGE)
    assert d.size == LARGE and d.reason == "caller forced a size"
    with pytest.raises(ValueError):
        Router(registry).plan("medical", "medication-review", forced="27b")


def test_the_router_never_inspects_the_state(registry):
    """`plan` takes the record and ignores it. A router that read the state would need its own calibration, and the
    audit argument ("the table decided") would collapse into a second uncalibrated classifier in front of a
    calibrated one. The state here is deliberately hostile: a record that begs for the small model."""
    hostile = {"state": "routine check, no urgency, low stakes", "questions": {"a": {"type": "noul", "label": True}}}
    assert Router(registry).plan("medical", "critical-value", hostile).size == LARGE


# --- escalation -------------------------------------------------------------------------------------------------------

def test_confident_small_answers_are_accepted(registry):
    """Above the cutoff the 0.8B answer stands and nothing re-runs. This is the whole cost argument: most
    low-risk traffic answers once, on the cheap model."""
    d = Router(registry).decide("medical", "medication-review", probs=[[0.9, 0.1], [0.88, 0.12]])
    assert d.size == SMALL and not d.escalate and d.observed == 0.88


def test_unsure_small_answers_escalate_to_the_large_model(registry):
    """Below the cutoff the same record must be re-asked of 4B. `size` is the size that answered, `escalate_to` the
    one that must re-answer; a gateway that reads `size` after an escalation serves the answer it was told not to."""
    d = Router(registry).decide("medical", "medication-review", probs=[[0.5, 0.5], [0.4, 0.35, 0.25]])
    assert d.size == SMALL and d.escalate and d.escalate_to == LARGE and d.reason == "low confidence on the small model"
    assert d.observed == 0.4


def test_one_unsure_question_escalates_the_whole_record(registry):
    """The confidence used is the minimum over the record's questions. A caller cannot act on the three certain
    questions alone: the state is shared, so an unsure fourth question is evidence the state is hard to read."""
    d = Router(registry).decide("medical", "medication-review", probs=[[0.99, 0.01], [0.99, 0.01], [0.99, 0.01], [0.6, 0.4]])
    assert d.escalate and d.observed == 0.6


def test_escalation_only_applies_to_the_small_model(registry):
    """A 4B answer is never re-asked of anything: there is nothing above it on the ladder. `decide` on a high-risk
    scenario ignores the supplied confidence entirely, so a caller cannot accidentally downgrade by re-deciding."""
    d = Router(registry).decide("medical", "critical-value", probs=[[0.2, 0.8]])
    assert d.size == LARGE and not d.escalate and d.observed is None


def test_a_scenario_can_demand_a_stricter_bar_than_its_own_development_set(registry):
    """`Scenario.escalation_cutoff` overrides the fitted cutoff, and only downwards in practice: the router reads the
    scenario first. A site that distrusts a 0.82 cutoff sets 0.95 on the scenario and gets 0.95."""
    reg = registry
    reg.industry("medical").scenarios["medication-review"] = Scenario("medication-review", "medical", risk="low",
                                                                     human_review=True, escalation_cutoff=0.95)
    d = Router(reg).plan("medical", "medication-review")
    assert d.threshold == 0.95 and "scenario" in d.reason
    # the stricter bar moves the boundary: 0.90 passed the fitted 0.82 but not the demanded 0.95
    assert Router(reg).decide("medical", "medication-review", probs=[[0.9, 0.1]]).escalate
    assert not Router(reg).decide("medical", "medication-review", probs=[[0.97, 0.03]]).escalate


def test_decide_refuses_both_confidence_forms_at_once(registry):
    """probs or confidence, not both: silently preferring one would let a gateway pass a stale confidence next to
    fresh probabilities."""
    with pytest.raises(ValueError):
        Router(registry).decide("medical", "medication-review", probs=[[0.9, 0.1]], confidence=0.9)


# --- thresholds come from measurements, never from constants ---------------------------------------------------------

def test_adapters_take_their_temperature_and_cutoff_from_a_result(tmp_path):
    """`Adapter.from_result` reads the fitted temperature and the selective cutoff out of a run's result.json, so a
    threshold in the registry is traceable to a development partition. A result without the selective block is
    refused: a cutoff of 0.0 would escalate everything and 1.0 would escalate nothing, and neither is a measurement."""
    a = Adapter.from_result("medical", "critical-value", "8b", "runs/cv-8b", result(temperature=2.35, cutoff=0.82))
    assert a.temperature == 2.35 and a.confidence_cutoff == 0.82 and a.name == "medical/critical-value/8b"
    with pytest.raises(ValueError, match="selective"):
        Adapter.from_result("medical", "critical-value", "8b", "runs/cv-8b", {"temperature": 2.0})


def test_the_cutoff_prefers_the_calibrated_report(tmp_path):
    """Raw logits and calibrated ones have different cutoffs (that is what the temperature is for). The router's bar
    is the one from the calibrated report, because that is what the served endpoint returns."""
    r = result(temperature=1.0, cutoff=0.82)
    assert _cutoff_from_report(r) == 0.82
    r["development"].pop("calibrated")
    assert _cutoff_from_report(r) == 0.84      # the raw block's cutoff, the fallback
    assert _cutoff_from_report(None) is None


def test_the_threshold_book_builds_a_router_with_no_constants(tmp_path):
    """ThresholdBook.from_results is the bridge from a training pipeline to the router: `{"scenario": {"size": result}}`
    per industry becomes a Router whose every threshold came from a measured development set."""
    book = ThresholdBook.from_results({"medication-review": {"8b": result(cutoff=0.82), "4b": result(cutoff=0.86)}}, "medical")
    assert book.thresholds() == {"medical/medication-review": 0.82}
    reg = IndustryRegistry([Industry("medical", "医疗").add(Scenario("medication-review", "medical", risk="low"))])
    router = book.router(reg)
    assert router.plan("medical", "medication-review").threshold == 0.82
    assert router.decide("medical", "medication-review", probs=[[0.85, 0.15]]).escalate is False
    assert router.decide("medical", "medication-review", probs=[[0.8, 0.2]]).escalate is True


def test_an_adapter_rejects_impossible_thresholds():
    """The bounds are the contract a reviewer relies on: a cutoff outside (0, 1] or a non-positive temperature is a
    data-entry error, caught at the registry boundary rather than at a patient."""
    for bad in [dict(confidence_cutoff=0.0), dict(confidence_cutoff=1.5), dict(confidence_cutoff=-0.1), dict(temperature=0.0)]:
        with pytest.raises(ValueError):
            Adapter("medical", "x", "8b", "runs/x", **bad)


# --- escalation report: what the table would have cost ---------------------------------------------------------------

def rows(*pairs):
    """kev.benchmark row shape: p (the probabilities at the temperature they were served at), label, and the fields
    kev.metrics.scored_rows filters on."""
    return [{"p": list(p), "label": y, "variant": "clean", "source": "custom", "task": "t", "type": "noul"} for p, y in pairs]


def test_the_escalation_report_separates_the_answered_set_from_the_escalated_one():
    """The number a site needs before letting the router take traffic: the share answered by 0.8B (a cost and
    latency projection) and the accuracy inside the set 0.8B was allowed to answer (the safety argument). The two are
    reported separately because a high average accuracy can hide a cheap model answering exactly the hard records."""
    book = ThresholdBook()
    book.put(Adapter("medical", "critical-value", "8b", "runs/cv-8b", temperature=1.0, confidence_cutoff=0.8))
    # 0.95 confident and right; 0.95 confident and wrong; 0.6 unsure and right; 0.5 unsure and wrong
    report = escalation_report(book, {"critical-value": rows(([0.95, 0.05], 0), ([0.95, 0.05], 1), ([0.6, 0.4], 1), ([0.5, 0.5], 0))}, "medical")
    got = report["critical-value"]
    assert got["answered"] == {"n": 2, "accuracy": 0.5, "share": 0.5}
    assert got["escalated"] == {"n": 2, "accuracy": 0.5, "share": 0.5}
    assert got["recall_of_errors_caught"] == 0.5    # one of the two mistakes was escalated
    assert got["cutoff"] == 0.8 and got["temperature"] == 1.0


def test_the_escalation_report_says_so_when_a_scenario_has_no_measurement():
    reg = escalation_report(ThresholdBook(), {"critical-value": rows(([0.9, 0.1], 0))}, "medical")
    assert "error" in reg["critical-value"]


# --- the registry itself ----------------------------------------------------------------------------------------------

def test_the_registry_round_trips_through_its_json(tmp_path):
    """The registry file is the deployment's source of truth and is meant to be read, diffed and signed off by
    someone who does not read Python. A round trip that loses a scenario's risk or an adapter's cutoff would make
    the file a worse copy of the code than the code is."""
    reg = IndustryRegistry([Industry("medical", "医疗健康", note="note").add(
        Scenario("critical-value", "medical", risk="high", human_review=True, evidence_question="evidence_sufficient"))])
    reg.industry("medical").register(Adapter("medical", "critical-value", "4b", "runs/cv-4b", temperature=2.41,
                                             confidence_cutoff=0.86, base="jaredpalmer/kev-4b", lora=16))
    path = reg.save(tmp_path / "registry.json")
    back = IndustryRegistry.load(path)
    assert back.names() == ["medical"]
    sc = back.industry("medical").scenarios["critical-value"]
    assert (sc.risk, sc.human_review, sc.evidence_question) == ("high", True, "evidence_sufficient")
    a = back.industry("medical").adapter("critical-value", "4b")
    assert (a.temperature, a.confidence_cutoff, a.base) == (2.41, 0.86, "jaredpalmer/kev-4b")
    assert back.to_dict() == reg.to_dict()


def test_a_registry_cannot_hold_two_industries_or_two_scenarios_of_one_name(registry):
    """Names are keys, and a duplicate would make the routing table ambiguous in a way a JSON file cannot express."""
    with pytest.raises(ValueError):
        registry.add(Industry("medical", "again"))
    with pytest.raises(ValueError):
        registry.industry("medical").add(Scenario("critical-value", "medical", risk="low"))
    with pytest.raises(ValueError):
        registry.industry("medical").add(Scenario("x", "other-industry", risk="low"))


def test_lookup_failures_name_what_is_available():
    """A gateway turns these into a 404 and a message a caller can act on. 'no industry aerospace is registered
    (this deployment serves [...])' is a bug report; a bare KeyError is not."""
    with pytest.raises(UnknownIndustry, match="aerospace"):
        IndustryRegistry().industry("aerospace")
    with pytest.raises(UnknownScenario, match="critical-value"):
        industries().industry("medical").scenario("not-there")
    with pytest.raises(UnknownScenario, match="has no 4b adapter"):
        IndustryRegistry([Industry("medical", "m").add(Scenario("s", "medical"))]).industry("medical").adapter("s", "4b")


def test_an_adapter_must_attach_to_a_declared_scenario(registry):
    """Registering an adapter for a scenario nobody declared would make the risk tier of that scenario unknown, and
    an unknown tier is the one thing the router must never have to guess about."""
    with pytest.raises(UnknownScenario):
        registry.register(Adapter("medical", "ghost", "8b", "runs/ghost", confidence_cutoff=0.9))
    with pytest.raises(ValueError):
        registry.register(Adapter("other", "critical-value", "8b", "runs/x", confidence_cutoff=0.9))


def test_the_families_helper_separates_the_two_backbones(registry):
    """IndustryRegistry.families() is what tells a deployment it needs two loaded backbones: a registry mixing 0.8B
    and 4B adapters yields two identities, and AdapterPool refuses to mix them."""
    families = registry.families()
    assert ("jaredpalmer/kev-0.8b", None, 256, 16) in families and ("jaredpalmer/kev-4b", None, 256, 16) in families
    assert len(families) == 2


def test_the_built_in_registry_has_all_five_industries_and_no_adapters():
    """The shipped registry declares scenarios and their risk but no adapters: that is a site on day one. A trained
    adapter arrives through ThresholdBook/IndustryRegistry.load, never by editing this module."""
    reg = industries()
    assert set(reg.names()) == {"medical", "finance", "legal", "education", "support"}
    assert reg.adapters() == []
    assert len(reg.scenarios("medical")["medical"]) == 5


def test_a_peft_adapter_name_is_a_valid_identifier():
    """peft's adapter_name must survive peft's own bookkeeping; a scenario key like 'medical/critical-value' would
    not, so the name is sanitised here rather than at every call site."""
    assert _adapter_name("medical/critical-value/8b") == "medical_critical_value_8b"
    assert _adapter_name("support/ticket-triage/4b").isidentifier()


def test_decisions_serialise_for_the_audit_log(registry):
    """Every decision is logged as the dict a reviewer reads: which industry, which scenario, which size, why, and
    whether a human is in the loop. The keys are pinned so a log parser does not break on a refactor."""
    from kev.vertical import Decision
    d = Router(registry).decide("medical", "medication-review", probs=[[0.5, 0.5]])
    body = d.to_dict()
    assert set(body) == set(Decision.decision_fields) and body["escalate"] is True and body["size"] == SMALL
    assert json.dumps(body)   # must be plain JSON for the log


# --- sizes and tiers are the one ordering -------------------------------------------------------------------------------

def test_the_size_ladder_is_small_to_large():
    """Escalation only moves up SIZES. A new size must be inserted in the middle, never appended, or
    RISK_FLOOR's "high = SIZES[-1]" would silently mean something else."""
    assert SIZES.index(SMALL) < SIZES.index(LARGE)
    assert RISK_FLOOR["high"] == LARGE and RISK_FLOOR["critical"] == LARGE
    assert RISK_FLOOR["low"] == SMALL and RISK_FLOOR["medium"] == SMALL


# --- the adapter pool, against a real peft model ----------------------------------------------------------------------
# The pooling is the reason a vertical deployment is cheap, and it is the part of this module that talks to peft's
# own multi-adapter API. These run a 25k-parameter llama with a rank-4 adapter: no weights to download, real peft.

def tiny_peft(tmp_path, seed=0):
    """A real PeftModel on a two-layer llama, saved as two adapter directories (two 'industries')."""
    import torch
    from peft import LoraConfig, get_peft_model
    from transformers import AutoConfig, AutoModelForCausalLM
    torch.manual_seed(seed)
    cfg = AutoConfig.for_model("llama", hidden_size=32, intermediate_size=64, num_hidden_layers=2,
                               num_attention_heads=4, num_key_value_heads=2, vocab_size=99)
    base = AutoModelForCausalLM.from_config(cfg).model
    dirs = []
    for i in range(2):
        torch.manual_seed(seed + i)
        peft = get_peft_model(base, LoraConfig(task_type="FEATURE_EXTRACTION", r=4, lora_alpha=8,
                                               target_modules=["q_proj", "v_proj"]))
        # a non-zero delta, so 'which adapter is active' changes the output
        for n, p in peft.named_parameters():
            if "lora_B" in n:
                with torch.no_grad():
                    p.add_(torch.randn_like(p) * 0.1)
        path = tmp_path / f"industry{i}"
        peft.save_pretrained(str(path))
        dirs.append(str(path))
    return base, dirs


def test_the_pool_swaps_adapters_and_heads_without_touching_the_backbone(tmp_path):
    """The whole point: one frozen backbone, many industries. `use` changes the forward pass (the two adapters hold
    different deltas) and the pointer head (each industry trained its own), and restoring the checkpoint's own adapter
    gives the baseline back. The backbone's parameters are never rewritten, so no rounding is introduced per request."""
    import torch
    from types import SimpleNamespace
    from kev.vertical import AdapterPool
    base, dirs = tiny_peft(tmp_path)
    from peft import LoraConfig, get_peft_model
    from transformers import AutoConfig, AutoModelForCausalLM
    cfg = AutoConfig.for_model("llama", hidden_size=32, intermediate_size=64, num_hidden_layers=2,
                               num_attention_heads=4, num_key_value_heads=2, vocab_size=99)
    torch.manual_seed(7)
    model = get_peft_model(AutoModelForCausalLM.from_config(cfg).model,
                           LoraConfig(task_type="FEATURE_EXTRACTION", r=4, lora_alpha=8, target_modules=["q_proj", "v_proj"]))
    model.eval()
    model.head = torch.nn.Linear(4, 2)   # the pool only copies a state dict onto .head; any real module will do
    ids = torch.tensor([[1, 2, 3, 4]])

    reg = IndustryRegistry([Industry("medical", "医疗").add(Scenario("cv", "medical", risk="high"))])
    pool = AdapterPool(SimpleNamespace(lm=model, head=model.head), reg, base="jaredpalmer/kev-0.8b")
    a0 = Adapter("medical", "cv", "8b", dirs[0], temperature=2.35, confidence_cutoff=0.8, base="jaredpalmer/kev-0.8b")
    a1 = Adapter("medical", "cv", "4b", dirs[1], temperature=2.41, confidence_cutoff=0.8, base="jaredpalmer/kev-0.8b")
    pool.load(a0, head={"weight": torch.zeros(2, 4), "bias": torch.zeros(2)})
    pool.load(a1, head={"weight": torch.ones(2, 4), "bias": torch.ones(2)})

    # the frozen backbone, captured after the adapters are loaded (loading only adds adapter tensors): a swap must
    # not rewrite a single base weight, which is what "one backbone, many industries" means
    before = {n: p.detach().clone() for n, p in model.named_parameters() if "lora" not in n and n.startswith("base_model")}

    out = {}
    for a in (a0, a1):
        pool.use(a.name)
        out[a.name] = model(input_ids=ids).last_hidden_state.clone()
        assert pool.active == a.name
    assert not torch.allclose(out[a0.name], out[a1.name]), "two industries must not produce the same hidden states"
    # the frozen backbone is untouched by a swap
    assert all(torch.equal(before[n], p) for n, p in model.named_parameters() if n in before)
    # the head follows the adapter, along with its temperature
    pool.use(a0.name)
    assert torch.equal(model.head.weight, torch.zeros(2, 4)) and model.head.temperature == 2.35
    pool.use(a1.name)
    assert torch.equal(model.head.weight, torch.ones(2, 4)) and model.head.temperature == 2.41
    # set_adapter(inference_mode=True) must not leave the pool's adapters trainable
    assert not any(p.requires_grad for n, p in model.named_parameters() if "lora" in n)
    pool.restore(); assert pool.active is None


def test_the_pool_refuses_a_backbone_the_adapters_were_not_trained_on(tmp_path):
    """A registry that mixes 0.8B and 4B adapters cannot share one backbone. Catching it when the pool is built
    costs one line; catching it at serving time costs a wrong answer."""
    from types import SimpleNamespace
    from kev.vertical import AdapterConflict, AdapterPool
    model = SimpleNamespace(lm=SimpleNamespace(load_adapter=lambda *a, **k: None, active_adapters=["default"]),
                             head=SimpleNamespace())
    reg = IndustryRegistry([Industry("m", "m").add(Scenario("s", "m", risk="low"))])
    reg.register(Adapter("m", "s", "4b", "runs/x", confidence_cutoff=0.9, base="jaredpalmer/kev-4b"))
    with pytest.raises(AdapterConflict, match="kev-4b"):
        AdapterPool(model, reg, base="jaredpalmer/kev-0.8b")


def test_the_pool_needs_an_unmerged_peft_model():
    """A merged backbone has no adapters to swap, so a pool over one is a programming error, not a slow path."""
    from types import SimpleNamespace
    from kev.vertical import AdapterConflict, AdapterPool
    with pytest.raises(AdapterConflict, match="unmerged PeftModel"):
        AdapterPool(SimpleNamespace(lm=SimpleNamespace(), head=SimpleNamespace()), IndustryRegistry(), base=None)


def test_using_an_unloaded_adapter_is_an_error_not_a_silent_baseline(tmp_path):
    """A typo in an adapter key must not quietly serve the base checkpoint's answers labelled as the industry's."""
    from types import SimpleNamespace
    from kev.vertical import AdapterPool
    model = SimpleNamespace(lm=SimpleNamespace(load_adapter=lambda *a, **k: None, active_adapters=["default"]),
                            head=SimpleNamespace())
    pool = AdapterPool(model, IndustryRegistry(), base=None)
    with pytest.raises(UnknownScenario, match="not loaded"):
        pool.use("medical/ghost/8b")
