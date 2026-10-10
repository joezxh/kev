"""Vertical deployments: one industry, one adapter per size, and a risk router that decides which size answers.

A vertical Kev deployment is not a new model. It is a released checkpoint (`jaredpalmer/kev-0.8b`, `kev-4b`, ...)
that carries an industry delta as a LoRA adapter, plus a pointer head fitted on that industry's data, plus a
temperature fitted on that industry's calibration rows. Because the delta is an adapter, five industries on one
size share the same frozen backbone in memory: swapping industries is peft's `set_adapter` (kev.checkpoint already
loads an adapter unmerged when it must), not a second copy of the weights (0.8B: 46 MB per industry, 4B: 131 MB).

The interesting decision is not which industry but **which size**, because the two sizes are not interchangeable.
`docs/medical/README.md` measured the gap: 0.8B cannot do date arithmetic (0.35 vs 0.65), takes its knowledge from
the backbone rather than inferring it (MMLU-Pro 0.230), and routes tool calls *below* chance (When2Call 0.133), so
a scenario like "is this record complete enough to decide" is above chance only on 4B. Sent in the other direction,
0.8B is not a weaker 4B, it is a model with a different error budget, and on rule-derivable labels (critical values,
claim adjudication, ticket routing) it matches 4B at a fraction of the cost and is measurable 8 minutes after a
training run starts instead of 15.

So the router has two inputs and one output, and both inputs are auditable:

1. **The scenario's declared risk** (`Scenario.risk`). A table a clinician or a compliance officer can read, diff
   and sign off on. It is the floor: a scenario marked `high` never answers on 0.8B, whatever the confidence says.
2. **The cheap model's own confidence** (the escalation signal). 0.8B answers first; if its answer is not confident
   enough for *this scenario's* budget, the same record is re-asked of 4B. The threshold is the 0.8B checkpoint's
   own `selective["0.8"].confidence_cutoff` from its own development rows (`kev.metrics.metrics`), not a constant:
   a number that came from a measured error rate can be defended to a reviewer, a round 0.9 cannot.

Both inputs fail safe. A record the scenario cannot classify routes to the large model. A 0.8B checkpoint with no
recorded cutoff has no threshold, so it escalates rather than deciding. And the router never reads the *content* of
the state to pick a size: routing on the text would put a learned classifier in front of a calibrated one, and the
one thing a clinical reviewer must be able to check by reading the table is that the table decided.

`kev.vertical` is a decision layer over an unchanged `kev.serve.Server`. It holds no weights, no CUDA state and no
FastAPI app of its own: `Router` answers `(request, probs) -> decision`, the caller (kev.serve's model thread, or a
Modal gateway) runs the passes. That keeps the routing rules testable without a GPU, which is the only way to keep
them honest.

    reg = IndustryRegistry().load(INDUSTRIES)
    router = Router(reg, thresholds=ThresholdBook.from_results({"critical-value": {"8b": result_8b, "4b": result_4b}}))
    plan = router.plan("medical", "critical-value", record)     # -> Decision(size="8b", why="scenario risk: low")
    # ... 0.8B answers; router.escalate(plan, probs, stats) says whether 4B must re-answer the same record.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .checkpoint import read_meta

# Sizes, smallest first. A router only ever moves up this ladder (escalation), never down: the cheap model cannot be
# shown to be safe on a record the large one was needed for. Kept as the one ordering of Kev's two released sizes.
SIZES = ("8b", "4b")
LARGE = SIZES[-1]
SMALL = SIZES[0]

# Risk levels, safest handling first. `escalate` is a floor on the size, `human_review` a floor on the *answer*:
# a scenario may be answerable by 4B and still require a human before anything is acted on (medical default).
RISK_LEVELS = ("low", "medium", "high", "critical")

# A scenario declares the smallest size that may answer it. Anything at or above `high` is a 4B-or-nothing scenario,
# which is where the medical critical-value path sits: 漏报危急值 ≫ 误报, so a cheap model's uncertainty is not a
# reason to let a cheap model answer. This table is the *floor*; escalation only ever raises the floor.
RISK_FLOOR = {"low": "8b", "medium": "8b", "high": "4b", "critical": "4b"}

# Why the router refuses to guess. Recorded on every decision so a review can reconstruct it after the fact.
REASON_SCENARIO = "scenario risk"
REASON_ESCALATED = "low confidence on the small model"
REASON_UNKNOWN_SCENARIO = "unregistered scenario"
REASON_NO_THRESHOLD = "no fitted threshold"
REASON_SMALL_UNAVAILABLE = "small model not registered"
REASON_FORCED = "caller forced a size"

# Errors the adapter layer raises, kept distinct from ValueError so a gateway can map them onto status codes.
class UnknownIndustry(KeyError):
    """A request named an industry that is not in the registry."""


class UnknownScenario(KeyError):
    """A request named a scenario its industry does not declare, or named no scenario at all."""


class AdapterConflict(ValueError):
    """Two adapters in one registry disagree about base, revision, head_dim or lora rank, so they cannot share a backbone."""


# --- the industry registry -------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Adapter:
    """One industry's delta on one size: where its adapter is, and the calibration that goes with it.

    `run` is whatever `kev.checkpoint.Checkpoint` accepts: a run directory on the Modal volume, a local path, or a
    Hub id. `temperature` and `confidence_cutoff` are the two numbers a router cannot invent; both are copied out of
    the run's own `result.json` (`kev.benchmark`'s report) by `Adapter.from_result`, never hand-typed here, because a
    hand-typed temperature is exactly the bug this module exists to prevent.
    """

    industry: str
    scenario: str
    size: str
    run: str
    temperature: float = 1.0
    confidence_cutoff: float = 0.0
    base: str | None = None
    base_revision: str | None = None
    head_dim: int = 256
    lora: int = 0
    label: str = ""

    def __post_init__(self):
        if self.size not in SIZES:
            raise ValueError(f"{self.industry}/{self.scenario}: size must be one of {SIZES}, got {self.size!r}")
        if not 0.0 < self.confidence_cutoff <= 1.0:
            raise ValueError(f"{self.industry}/{self.scenario}/{self.size}: confidence_cutoff must be in (0, 1], got {self.confidence_cutoff!r}")
        if self.temperature <= 0:
            raise ValueError(f"{self.industry}/{self.scenario}/{self.size}: temperature must be positive, got {self.temperature!r}")

    @property
    def name(self) -> str:
        """The registry key: <industry>/<scenario>/<size>."""
        return f"{self.industry}/{self.scenario}/{self.size}"

    def describe(self) -> str:
        return self.label or f"{self.industry}/{self.scenario}/{self.size}"

    @classmethod
    def from_result(cls, industry, scenario, size, run, result, label=""):
        """An Adapter from a run's `result.json` (the shape `kev_modal.py::run_train` writes, i.e. the one every
        fine-tune produces). The temperature is the fitted one the checkpoint serves by default; the cutoff is the 0.8B
        style confidence at which that development set held a 20% error rate, which is the escalation threshold's
        only defensible source. Missing fields are refused rather than defaulted: a cutoff of 0.0 would mean "escalate
        everything", and a cutoff of 1.0 would mean "never escalate", and neither is a measurement."""
        dev = (result or {}).get("development") or {}
        cutoff = _cutoff_from_report(result)
        if cutoff is None:
            raise ValueError(f"{industry}/{scenario}/{size}: result.json has no selective confidence cutoffs to fit an "
                             "escalation threshold on; re-read the development partition (kev_modal.py::evaluate) or set "
                             "the threshold explicitly")
        return cls(industry=industry, scenario=scenario, size=size, run=run, temperature=float(result.get("temperature", 1.0)),
                   confidence_cutoff=cutoff, base=result.get("base"), head_dim=int(result.get("head_dim", 256)),
                   lora=int(result.get("lora", 0)), label=label)

    def to_dict(self) -> dict[str, Any]:
        return {"industry": self.industry, "scenario": self.scenario, "size": self.size, "run": self.run,
                "temperature": self.temperature, "confidence_cutoff": self.confidence_cutoff, "base": self.base,
                "base_revision": self.base_revision, "head_dim": self.head_dim, "lora": self.lora, "label": self.label}

    @classmethod
    def from_dict(cls, d):
        return cls(**{k: d[k] for k in cls.__dataclass_fields__ if k in d})


# The selective-prediction fraction a cutoff is read at: the share of questions a size answered *confidently enough*
# to accept at a 20% error rate among the accepted. 0.8 is the kev.metrics default sweep (0.5, 0.8); 0.8 is the
# higher-coverage end, where the remaining low-confidence tail is exactly the population a router escalates.
SELECTIVE_FRACTION = "0.8"


def _cutoff_from_report(result) -> float | None:
    """The `selective[fraction].confidence_cutoff` of a run's calibrated development report, or None."""
    if not result:
        return None
    dev = result.get("development") or {}
    for block in ("calibrated", "raw"):
        sel = ((dev.get(block) or {}).get("selective") or {}).get(SELECTIVE_FRACTION)
        if sel and sel.get("confidence_cutoff") is not None:
            return float(sel["confidence_cutoff"])
    return None


@dataclass(frozen=True)
class Scenario:
    """One decision task inside an industry, and the risk its answers carry.

    `risk` is the part a human signs off on. `risk` sets the size floor (RISK_FLOOR) and whether a human must see the
    answer before it is acted on (`human_review`), which is the medical default and the reason this module exists:
    a model that never generates text still proposes that a critical value is present, and that proposal is acted on.
    `evidence_question` names the question whose answer is the "the record does not support a decision" signal, when
    the scenario has one: an `evidence_sufficient=false` is a router input, not just a number to report.
    """

    name: str
    industry: str
    risk: str = "medium"
    human_review: bool = True
    evidence_question: str = ""
    escalation_cutoff: float | None = None
    note: str = ""

    def __post_init__(self):
        if self.risk not in RISK_LEVELS:
            raise ValueError(f"{self.name}: risk must be one of {RISK_LEVELS}, got {self.risk!r}")
        if self.escalation_cutoff is not None and not 0.0 < self.escalation_cutoff <= 1.0:
            raise ValueError(f"{self.name}: escalation_cutoff must be in (0, 1], got {self.escalation_cutoff!r}")
        if not self.industry:
            raise ValueError(f"{self.name}: a scenario belongs to an industry")


@dataclass
class Industry:
    """One vertical: its scenarios, and (once trained) its adapters per size."""

    name: str
    title: str
    scenarios: dict[str, Scenario] = field(default_factory=dict)
    adapters: dict[str, Adapter] = field(default_factory=dict)   # "<scenario>/<size>" -> Adapter
    note: str = ""

    def add(self, scenario: Scenario) -> "Industry":
        if scenario.industry != self.name:
            raise ValueError(f"{scenario.name} declares industry {scenario.industry!r} but was added to {self.name!r}")
        if scenario.name in self.scenarios:
            raise ValueError(f"{self.name} already declares scenario {scenario.name!r}")
        self.scenarios[scenario.name] = scenario
        return self

    def scenario(self, name: str) -> Scenario:
        try:
            return self.scenarios[name]
        except KeyError:
            raise UnknownScenario(f"{self.name} has no scenario {name!r} (it declares {sorted(self.scenarios)})") from None

    def adapter(self, scenario: str, size: str) -> Adapter:
        key = f"{scenario}/{size}"
        if key not in self.adapters:
            have = sorted(k for k in self.adapters if k.startswith(f"{scenario}/"))
            raise UnknownScenario(f"{self.name}/{scenario} has no {size} adapter (it has {have or 'none'}; train one with "
                                  "kev_modal.py::train --init-from jaredpalmer/kev-0.8b)")
        return self.adapters[key]

    def register(self, adapter: Adapter) -> "Industry":
        """Record an adapter. Adapters sharing a size must agree on the backbone they were trained from, or swapping
        one for another would silently change the model under the request."""
        if adapter.industry != self.name:
            raise ValueError(f"adapter {adapter.name} declares industry {adapter.industry!r}, not {self.name!r}")
        if adapter.scenario not in self.scenarios:
            raise UnknownScenario(f"{self.name} has no scenario {adapter.scenario!r} to attach {adapter.name} to")
        self.adapters[f"{adapter.scenario}/{adapter.size}"] = adapter
        return self

    def sizes(self, scenario: str) -> list[str]:
        return [s for s in SIZES if f"{scenario}/{s}" in self.adapters]

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "title": self.title, "note": self.note,
                "scenarios": {k: _scenario_dict(v) for k, v in self.scenarios.items()},
                "adapters": {k: v.to_dict() for k, v in sorted(self.adapters.items())}}

    @classmethod
    def from_dict(cls, d):
        ind = cls(name=d["name"], title=d.get("title", d["name"]), note=d.get("note", ""))
        for name, s in (d.get("scenarios") or {}).items():
            # the industry's name is the scenario's industry unless the file says otherwise (it usually will not:
            # one industry owns its scenarios, and repeating the name per scenario is how a file drifts)
            ind.scenarios[name] = Scenario(name=name, industry=s.get("industry", ind.name),
                                           **{k: v for k, v in s.items() if k not in ("name", "industry")})
        for key, a in (d.get("adapters") or {}).items():
            ind.adapters[key] = Adapter.from_dict(a)
        return ind


def _scenario_dict(s: Scenario) -> dict[str, Any]:
    return {"risk": s.risk, "human_review": s.human_review, "evidence_question": s.evidence_question,
            "escalation_cutoff": s.escalation_cutoff, "note": s.note}


class IndustryRegistry:
    """Every industry, scenario and adapter the deployment serves, loaded from one JSON file (or built in code).

    The file is the deployment's source of truth and is meant to be read by a reviewer: it is the table `plan` is
    computed from, so `docs` on it are the audit trail. `INDUSTRIES` below is that file's contents; `load` reads the
    same shape from disk so a site can add a scenario without a code change.
    """

    def __init__(self, industries: Iterable[Industry] = ()):
        self._industries: dict[str, Industry] = {}
        for ind in industries:
            self.add(ind)

    def add(self, industry: Industry) -> "Industry":
        if industry.name in self._industries:
            raise ValueError(f"industry {industry.name!r} is already registered")
        self._industries[industry.name] = industry
        return industry

    def __contains__(self, name) -> bool:
        return str(name) in self._industries

    def __len__(self) -> int:
        return len(self._industries)

    def industry(self, name: str) -> Industry:
        try:
            return self._industries[str(name)]
        except KeyError:
            raise UnknownIndustry(f"no industry {name!r} is registered (this deployment serves {sorted(self._industries)})") from None

    def names(self) -> list[str]:
        return sorted(self._industries)

    def scenarios(self, industry: str | None = None) -> dict[str, list[str]]:
        names = [industry] if industry else self.names()
        return {n: sorted(self._industries[n].scenarios) for n in names}

    def adapters(self, industry: str | None = None, scenario: str | None = None) -> list[Adapter]:
        out = []
        for name in ([industry] if industry else self.names()):
            for a in self._industries[name].adapters.values():
                if scenario is None or a.scenario == scenario:
                    out.append(a)
        return sorted(out, key=lambda a: (a.industry, a.scenario, SIZES.index(a.size)))

    def register(self, adapter: Adapter) -> Adapter:
        """Record an adapter. Refuses an unknown industry as a ValueError (not UnknownIndustry) because a registry
        that accepted one would be a registry whose routing table is not the table it reads."""
        if adapter.industry not in self._industries:
            raise ValueError(f"adapter {adapter.name} names industry {adapter.industry!r}, which is not registered "
                             f"(this deployment serves {sorted(self._industries)})")
        return self._industries[adapter.industry].register(adapter)

    def families(self):
        """(base, base_revision, head_dim, lora) per backbone identity, for AdapterPool's compatibility check.

        Two adapters can share one loaded backbone only if they were trained from the same base at the same revision
        with the same head width and LoRA rank. A registry mixing `kev-0.8b` and `kev-4b` adapters therefore yields two
        families and needs two backbones, and saying so at load time is much cheaper than discovering it as a silently
        wrong answer at serving time."""
        out = set()
        for a in self.adapters():
            out.add((a.base, a.base_revision, a.head_dim, a.lora))
        return out

    def to_dict(self) -> dict[str, Any]:
        return {"industries": {n: self._industries[n].to_dict() for n in self.names()}}

    def save(self, path) -> Path:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self.to_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return p

    @classmethod
    def load(cls, path) -> "IndustryRegistry":
        d = json.loads(Path(path).read_text(encoding="utf-8"))
        reg = cls()
        for name, body in (d.get("industries") or d).items():
            body = dict(body)
            body.setdefault("name", name)
            reg.add(Industry.from_dict(body))
        return reg

    def registry(self) -> "IndustryRegistry":
        return self


# The five industries this module ships with. The medical five are `docs/medical/specs/*.json` and keep the risk
# levels that package's own phasing argues for: the three rule-derivable ones are `low` (a 0.8B may answer), the two
# that need medical inference are `high` (4B only). The other four are declared with scenarios and risk but no
# adapters, which is the state a site is in on day one: the router routes, and a gateway answers 503 until the
# scenario is trained. `tests/test_vertical.py` pins these risk levels.
#
# NOTE: the 5 hardcoded builder functions (_medical / _finance / _legal / _education / _support) were
# removed in Task 24 of docs/superpowers/plans/2026-10-09-dynamic-scenario-generators.md. The registry
# is now built by kev.console.services.routing.sync_registry() from the DB-backed spec_json.routing
# blocks. The 7 medical scenarios are still seeded with identical risk + human_review + note values
# (see docs/medical/specs/*.json, committed in Task 22).


def _default_registry() -> IndustryRegistry:
    """The DB-projected IndustryRegistry (spec §3.6).

    Replaces the legacy _medical / _finance / _legal / _education / _support hardcoded builders. The migration
    is safe because (a) _OVERRIDE preserves the manual `IndustryRegistry.load(json)` path and (b) the 7 medical
    scenarios are still seeded with identical risk + human_review + evidence_question + note values (see
    docs/medical/specs/*.json routing blocks, committed in Task 22).
    """
    from kev.console.services.routing import sync_registry
    return sync_registry()


_DEFAULT: IndustryRegistry | None = None
_OVERRIDE: IndustryRegistry | None = None


def industries() -> IndustryRegistry:
    """The registry this deployment routes over: `kev.vertical.INDUSTRIES` when a caller assigned one (a site loads
    its own JSON with `IndustryRegistry.load`), else the five built-in industries, built on first use so importing
    this module stays cheap (no adapters, no weights)."""
    if _OVERRIDE is not None:
        return _OVERRIDE
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = _default_registry()
    return _DEFAULT


def __getattr__(name):
    """`kev.vertical.INDUSTRIES`, lazily (PEP 562). `from kev.vertical import INDUSTRIES` sees the same object, and a
    deployment can replace the whole registry with `kev.vertical.INDUSTRIES = IndustryRegistry.load(path)`."""
    if name == "INDUSTRIES":
        return industries()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


# --- routing --------------------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Decision:
    """What the router decided for one record, and why.

    Read `size` and `escalate` together, because they answer different questions:

    - From `plan` (no model has run): `size` is the size that **must** answer. `escalate` is only ever True here for
      the no-threshold fail-safe, where the answer must come from the large model.
    - From `decide` (a small model's answer was supplied): `size` is the size that **did** answer, and `escalate`
      says whether that answer is acceptable. When it is not, `escalate_to` names the size that must re-answer the
      same record, and `observed` carries the confidence that triggered it.

    So a gateway serves `size` when `escalate` is False, and re-asks `escalate_to` when it is True. `review` says a
    human sees the answer before it is acted on, whichever size produced it. `reason` is the audit string
    (REASON_*). Nothing in this module ever moves a record down the size ladder: the small model cannot be shown to
    be safe on a record the large one was needed for.
    """

    industry: str
    scenario: str
    size: str
    reason: str
    review: bool = True
    escalate: bool = False
    escalate_to: str | None = None
    threshold: float | None = None
    observed: float | None = None
    base: str | None = None
    adapter: str | None = None
    note: str = ""

    @property
    def model_key(self) -> str:
        """The key an AdapterPool is asked for: <industry>/<scenario>/<size>."""
        return f"{self.industry}/{self.scenario}/{self.size}"

    def to_dict(self) -> dict[str, Any]:
        return {k: getattr(self, k) for k in self.decision_fields}

    decision_fields = ("industry", "scenario", "size", "reason", "review", "escalate", "escalate_to", "threshold", "observed", "base", "adapter", "note")

    def with_observation(self, observed: float, escalated: bool) -> "Decision":
        return replace(self, observed=round(float(observed), 6), escalate=escalated, escalate_to=LARGE if escalated else None,
                       reason=REASON_ESCALATED if escalated else self.reason)


class Router:
    """Decides which size answers a record, from a scenario's declared risk and the small model's own confidence.

    `thresholds` maps "<scenario>" (or "<industry>/<scenario>") to the small size's confidence cutoff. It is filled
    from each run's own development rows (Adapter.confidence_cutoff), not from a constant, so a threshold is always a
    measured error rate. The rules, in the order they are applied:

    1. An unknown industry or scenario routes to the large model with an explicit reason. A router that 404s on an
       unknown scenario is a router that will be bypassed the first time a caller typos one.
    2. A `forced` size from the caller wins outright (a reviewer re-asking with 4B on purpose, or a caller that only has
       one size). The decision still records `forced`, so the audit shows the router did not choose.
    3. `Scenario.escalation_cutoff` overrides the fitted cutoff when it is set (a scenario may demand a stricter bar
       than its own development set produced).
    4. The size floor from `RISK_FLOOR[scenario.risk]`: `high`/`critical` are 4B from the start, no confidence test.
    5. Everything else starts on the small model and escalates if the answer's confidence is under the cutoff.
    """

    def __init__(self, registry: IndustryRegistry | None = None, thresholds: Mapping[str, float] | None = None):
        self.registry = registry if registry is not None else industries()
        self.thresholds = dict(thresholds or {})

    def cutoff(self, scenario: Scenario, adapter: Adapter | None = None) -> tuple[float | None, str]:
        """(threshold, where it came from). None means there is no threshold and the record must escalate.

        Precedence: the scenario's explicit `escalation_cutoff`, then the registry's adapter cutoff, then a `thresholds`
        entry keyed "<industry>/<scenario>" or "<scenario>". A scenario that wants a stricter bar than its own
        development set produced sets it on the Scenario; nothing else can *loosen* one."""
        if scenario.escalation_cutoff is not None:
            return float(scenario.escalation_cutoff), "scenario"
        if adapter is not None and adapter.confidence_cutoff > 0:
            return adapter.confidence_cutoff, "adapter"
        for key in (f"{scenario.industry}/{scenario.name}", scenario.name):
            if key in self.thresholds:
                return float(self.thresholds[key]), "thresholds"
        return None, "none"

    def plan(self, industry: str, scenario: str, record: Mapping[str, Any] | None = None, forced: str | None = None) -> Decision:
        """The size that must answer `record`, before any model has run. Pure: it reads the registry, never the state.

        `record` is accepted so a gateway can pass the request; it is deliberately not inspected. A router that read
        the state would need its own calibration, and a clinical reviewer has to be able to check the decision by
        reading the table."""
        if forced is not None and forced not in SIZES:
            raise ValueError(f"forced size must be one of {SIZES}, got {forced!r}")
        if industry not in self.registry:
            return Decision(industry=str(industry), scenario=str(scenario), size=LARGE, reason=REASON_UNKNOWN_SCENARIO,
                            review=True, escalate_to=LARGE, note=f"{industry!r} is not registered; served by the large model")
        ind = self.registry.industry(industry)
        if scenario not in ind.scenarios:
            return Decision(industry=industry, scenario=str(scenario), size=LARGE, reason=REASON_UNKNOWN_SCENARIO,
                            review=True, escalate_to=LARGE, note=f"{industry} has no scenario {scenario!r}; served by the large model")
        sc = ind.scenarios[scenario]
        floor = RISK_FLOOR[sc.risk]
        adapter = ind.adapters.get(f"{scenario}/{SMALL}")
        threshold, source = self.cutoff(sc, adapter)
        common = {"industry": industry, "scenario": scenario, "review": sc.human_review, "base": (adapter or {}).base if adapter else None}

        if forced is not None:
            return Decision(size=forced, reason=REASON_FORCED, threshold=threshold, **common)

        if floor == LARGE:
            # A high/critical scenario never starts on the small model, so there is nothing to escalate *from*: the
            # decision is the large model, and `escalate` stays False because escalation means "the small model's
            # answer was not good enough", which cannot happen when the small model was never asked.
            why = f"{REASON_SCENARIO} {sc.risk}" if threshold is None else f"{REASON_SCENARIO} {sc.risk} (threshold {threshold:.2f} from {source})"
            return Decision(size=LARGE, reason=why, threshold=threshold, **common)

        if floor == SMALL:
            if threshold is None:
                # No fitted cutoff: the small model may answer, but a router with no bar cannot certify its answer, so
                # the record still goes to the large model. This is the "fail safe" the module docstring promises.
                return Decision(size=LARGE, reason=REASON_NO_THRESHOLD, escalate=True, escalate_to=LARGE, **common)
            return Decision(size=SMALL, reason=f"{REASON_SCENARIO} {sc.risk} (threshold {threshold:.2f} from {source})",
                            threshold=threshold, **common)

        raise AssertionError(f"RISK_FLOOR produced an unknown floor {floor!r}")   # unreachable with the four levels

    def review(self, industry: str, scenario: str) -> bool:
        """Whether a human must see this scenario's answer before it is acted on."""
        if industry not in self.registry:
            return True
        ind = self.registry.industry(industry)
        return ind.scenarios[scenario].human_review if scenario in ind.scenarios else True

    def decide(self, industry: str, scenario: str, record: Mapping[str, Any] | None = None, forced: str | None = None,
               probs: Sequence[Sequence[float]] | None = None, confidence: float | None = None) -> Decision:
        """`plan`, then apply the escalation test if a small model's answer is supplied.

        Supply `confidence` (the small model's own confidence in its argmax) or `probs` (per question, the
        probabilities it returned). The confidence used is the **minimum over questions**: one unsure question in a
        4-question record is enough to escalate, because the caller cannot act on the three certain ones alone."""
        decision = self.plan(industry, scenario, record, forced)
        if probs is not None and confidence is not None:
            raise ValueError("give probs or confidence, not both")
        if probs is not None:
            if not len(probs):
                raise ValueError("probs must hold at least one question's distribution")
            confidence = min(max(p) for p in probs)
        if confidence is None or decision.size != SMALL:
            return decision
        cutoff = decision.threshold
        if cutoff is None or confidence < cutoff:
            return decision.with_observation(confidence, escalated=True)
        return decision.with_observation(confidence, escalated=False)

    def route(self, industry: str, scenario: str, record: Mapping[str, Any] | None = None, forced: str | None = None,
              small_probs: Sequence[Sequence[float]] | None = None) -> Decision:
        """`decide` under the name a gateway calls. Identical; kept so a gateway's call site reads as routing."""
        return self.decide(industry, scenario, record, forced, probs=small_probs)


# --- adapter pools (one backbone, many industries) -------------------------------------------------------------------

@dataclass
class AdapterPool:
    """Many industries' adapters on one loaded backbone, swapped with peft, plus their pointer heads.

    The pooling is the reason a vertical deployment is cheap. A `kev.checkpoint.Checkpoint` for `jaredpalmer/kev-0.8b`
    loads the base once; each industry adds an adapter (`PeftModel.load_adapter`) and a head (`head.pt`'s `head`
    tensor dict). Serving a record means `set_adapter(name)` and copying the industry's head onto `PointerHead`. The
    head is not shared: it is trained per industry, and a delta fine-tune writes a new one every time.

    The unmerged form is deliberate. `LoadOptions.merge` folds W += delta once, which is the fastest way to serve a
    *single* adapter, but switching adapters then means rewriting every weight in the backbone, and a rewrite per
    request is both slow and a source of rounding. Unmerged keeps each adapter's delta exactly as trained; the cost
    is some memory bandwidth per forward, which at these sizes is not what the request waits on.

    This class holds no CUDA state of its own: it wraps a `DecisionModel` someone else loaded, and `use` is the only
    operation that mutates it. It is deliberately not thread-safe — a kev.serve Server serialises passes on its model
    thread, and a gateway that fans out must give each worker its own pool.
    """

    model: Any                      # a kev.model.DecisionModel whose `lm` is a PeftModel
    registry: IndustryRegistry
    base: str | None = None        # the base this pool's backbone is (Checkpoint.meta.base); the family check's ground truth
    active: str | None = None
    _heads: dict[str, Any] = field(default_factory=dict, init=False, repr=False)
    _loaded: set[str] = field(default_factory=set, init=False, repr=False)

    def __post_init__(self):
        lm = getattr(self.model, "lm", None)
        if lm is None or not hasattr(lm, "load_adapter"):
            raise AdapterConflict("AdapterPool needs a DecisionModel whose `lm` is an unmerged PeftModel (Checkpoint.load with LoadOptions(merge=False))")
        # peft 0.21 exposes active_adapters (a list); the singular active_adapter lives on the LoraModel underneath.
        self._default = _active(lm)
        self._check_families()

    def _check_families(self):
        """Refuse a registry whose adapters were trained on a different backbone than this pool loaded.

        The check is on the pool's own `base`, which the caller passes from the `Checkpoint.meta` it loaded, not on
        transformers' `_name_or_path` (which is a cache path on one machine and a Hub id on the next). Cheap now, a
        silently wrong answer later otherwise."""
        for a in self.registry.adapters():
            if a.base and self.base and a.base != self.base:
                raise AdapterConflict(f"{a.name} was trained from {a.base!r} but this pool's backbone is {self.base!r}; "
                                      "one AdapterPool per base (see IndustryRegistry.families), not one per deployment")

    def head(self, key: str):
        return self._heads.get(key)

    def load(self, adapter: Adapter, head: Mapping[str, Any] | None = None) -> Adapter:
        """Load one industry's adapter and head onto the pool's backbone. -> the Adapter, for chaining.

        `adapter.run` is whatever `kev.checkpoint.resolve_run` accepts: a run directory on the Modal volume, a local
        path, or a Hub id. It is resolved with resolve_run, not Checkpoint(...), because an adapter directory does not
        have to be a full Kev checkpoint: `kev.train --init_from` writes the adapter and head together, but a peft
        directory saved by hand has no head.pt and no meta, and refusing it would make the pool unusable for anything
        but a run directory. The head is then whatever the caller passed, or head.pt's `head` if the run has one."""
        import torch
        from .checkpoint import resolve_run
        if adapter.name in self._loaded:
            return adapter
        if adapter.base and self.base and adapter.base != self.base:
            raise AdapterConflict(f"{adapter.name} was trained from {adapter.base!r}, this pool is {self.base!r}")
        if not adapter.run:
            raise ValueError(f"{adapter.name} has no run to load an adapter from")
        directory = resolve_run(adapter.run)
        self.model.lm.load_adapter(directory, adapter_name=_adapter_name(adapter.name), is_trainable=False)
        self._loaded.add(adapter.name)
        if head is None and (Path(directory) / "head.pt").exists():
            head = read_meta(directory).head
        if head:
            self._heads[adapter.name] = {k: v if hasattr(v, "shape") else torch.tensor(v) for k, v in head.items()}
        self._heads.setdefault(adapter.name, {})["temperature"] = adapter.temperature
        return adapter

    def use(self, key: str) -> Any:
        """Activate one adapter (and its head, if loaded). -> the model, for chaining. Raises when the key is unknown.

        `inference_mode=True` matters: peft's `set_adapter` otherwise marks the adapter it activates as trainable, and
        a serving pool that leaves `requires_grad=True` on a 46 MB adapter is both a memory leak of autograd state
        and a foot-gun for anyone who later calls `.train()` on the shared model."""
        if key not in self._loaded:
            raise UnknownScenario(f"adapter {key!r} is not loaded in this pool (loaded: {sorted(self._loaded)}); call load() first")
        self.model.lm.set_adapter(_adapter_name(key), inference_mode=True)
        head = self._heads.get(key)
        if head:
            tensors = {k: v for k, v in head.items() if k != "temperature"}
            if tensors:
                self.model.head.load_state_dict(tensors)
            if "temperature" in head:
                self.model.head.temperature = float(head["temperature"])
        self.active = key
        return self.model

    def restore(self) -> Any:
        """Go back to the adapter the checkpoint itself carried (the pool's baseline), for a fallback answer."""
        self.model.lm.set_adapter(self._default, inference_mode=True)
        self.active = None
        return self.model

    def release(self, key: str) -> None:
        """Unload one adapter (frees its delta). The pointer head is kept only if it is the active one."""
        if key in self._loaded:
            self.model.lm.delete_adapter(_adapter_name(key))
            self._loaded.discard(key)
            if self.active == key:
                self.active = None


def _adapter_name(key: str) -> str:
    """A peft adapter name: alphanumerics and underscores only, so a scenario key like 'medical/critical-value' works."""
    return "".join(c if c.isalnum() else "_" for c in key)


def _active(lm) -> str:
    """The peft adapter name currently active on a PeftModel.

    peft 0.21's `PeftModel.active_adapters` is a list, and the singular `active_adapter` is the LoraModel's; the
    fallback keeps this working if either shape changes. A pool with no adapter loaded is an error at construction
    time (kev.checkpoint always loads one), but not a crash here."""
    names = getattr(lm, "active_adapters", None)
    if isinstance(names, str):
        return names
    if names:
        return names[0]
    single = getattr(lm, "active_adapter", None)
    return single if isinstance(single, str) else "default"


# --- thresholds from run results -------------------------------------------------------------------------------------

class ThresholdBook:
    """The escalation thresholds, collected from each size's own development rows.

    A vertical deployment is measured per (industry, scenario, size), and each measurement is what the router reads.
    `from_results` takes the mapping a training pipeline already produces — `{"critical-value": {"8b": result, "4b": result}}`,
    where each result is a `result.json` — and pulls the fitted temperature and the selective confidence cutoff out of
    it. The router then has no constants of its own, which is the whole point: a threshold that can be traced to a
    development partition is auditable, and one hard-coded in a module is not.
    """

    def __init__(self, entries: Mapping[tuple[str, str, str], Adapter] | None = None):
        self._entries: dict[tuple[str, str, str], Adapter] = dict(entries or {})

    def put(self, adapter: Adapter) -> Adapter:
        self._entries[(adapter.industry, adapter.scenario, adapter.size)] = adapter
        return adapter

    def get(self, industry: str, scenario: str, size: str) -> Adapter | None:
        return self._entries.get((industry, scenario, size))

    def thresholds(self) -> dict[str, float]:
        """{"<industry>/<scenario>": cutoff} for the small size of each scenario, what Router accepts."""
        out = {}
        for (industry, scenario, size), a in self._entries.items():
            if size == SMALL and a.confidence_cutoff > 0:
                out[f"{industry}/{scenario}"] = a.confidence_cutoff
        return out

    def router(self, registry: IndustryRegistry | None = None) -> Router:
        """A Router over `registry` whose thresholds come from this book. Scenarios without a fitted cutoff escalate."""
        reg = registry if registry is not None else industries()
        for a in self._entries.values():
            reg.industry(a.industry).register(a)
        return Router(reg, thresholds=self.thresholds())

    def to_dict(self) -> dict[str, Any]:
        return {f"{i}/{s}/{z}": a.to_dict() for (i, s, z), a in sorted(self._entries.items())}

    @classmethod
    def from_results(cls, results: Mapping[str, Mapping[str, Mapping[str, Any]]], industry: str) -> "ThresholdBook":
        """{"<scenario>": {"<size>": result.json}} -> a book. Every scenario/size pair that has a result becomes an
        Adapter with its fitted temperature and cutoff. A result missing the selective block is refused (see
        Adapter.from_result): the router must not run on a threshold nobody measured."""
        book = cls()
        for scenario, sizes in results.items():
            for size, result in sizes.items():
                if size not in SIZES:
                    continue
                book.put(Adapter.from_result(industry, scenario, size, result.get("run", ""), result))
        return book

    def __len__(self) -> int:
        return len(self._entries)


def escalation_report(book: ThresholdBook, rows_by_scenario: Mapping[str, Sequence[Mapping[str, Any]]], industry: str) -> dict[str, Any]:
    """What the routing table would have cost on already-scored rows: for each scenario, how many questions the small
    model would have answered alone, how many would have escalated, and the error rate inside each group.

    This is the number a site needs before it lets the router take traffic: the escalation rate is a latency and cost
    projection (every escalated question runs 4B after 0.8B), and the small model's error rate *among the questions it
    was allowed to answer* is the safety argument. A router whose escalated set contains most of the errors is doing its
    job; one whose answered set contains them is not, whatever the headline accuracy.

    `rows_by_scenario` maps a scenario name to scored rows in `kev.benchmark`'s row shape (`p`, `label`, and the
    `variant`/`source` fields `kev.metrics.scored_rows` filters on)."""
    from .metrics import probabilities_at_temperature, scored_rows

    out: dict[str, Any] = {}
    for scenario, rows in rows_by_scenario.items():
        adapter = book.get(industry, scenario, SMALL)
        if adapter is None:
            out[scenario] = {"error": "no small-size adapter in the book"}
            continue
        cutoff = adapter.confidence_cutoff
        answered, escalated = [], []
        for r in scored_rows(rows):
            p = probabilities_at_temperature(r, adapter.temperature)
            (escalated if float(max(p)) < cutoff else answered).append(int(int(p.argmax()) == r["label"]))
        n_a, n_e = len(answered), len(escalated)
        out[scenario] = {
            "n": n_a + n_e,
            "cutoff": cutoff,
            "temperature": adapter.temperature,
            "answered": {"n": n_a, "accuracy": (sum(answered) / n_a) if n_a else None, "share": (n_a / (n_a + n_e)) if n_a + n_e else None},
            "escalated": {"n": n_e, "accuracy": (sum(escalated) / n_e) if n_e else None, "share": (n_e / (n_a + n_e)) if n_a + n_e else None},
            "recall_of_errors_caught": _error_recall(answered, escalated) if (answered or escalated) else None,
        }
    return out


def _error_recall(answered, escalated) -> float | None:
    """The share of all wrong answers that the escalation rule sent to the large model. 1.0 = every miss escalates."""
    wrong = len(answered) - sum(answered) + len(escalated) - sum(escalated)
    if wrong == 0:
        return None
    return (len(escalated) - sum(escalated)) / wrong
