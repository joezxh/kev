<p align="center">
  <a href="./sft-distill.md"><img alt="English" src="https://img.shields.io/badge/English-blue?style=for-the-badge"></a>
  <a href="./sft-distill_CN.md"><img alt="中文" src="https://img.shields.io/badge/%E4%B8%AD%E6%96%87-orange?style=for-the-badge"></a>
</p>

# Distilling medical data from Ant Ling for Kev and medical SFT

[简体中文](./sft-distill_CN.md) · Implementation: [`medical/distill/`](./medical/distill/README.md) ·
Manual: [`medical/distill.md`](./medical/distill.md) · Parent design: [`sft-medical.md`](./sft-medical.md)

Produce two kinds of medical data from **Ant Ling** (Bailin, cloud Open API) as the teacher and **EasyDistill 2** as
the pipeline: **Kev decision records** with rule-derived labels, and **generative SFT samples** for a medical
assistant model. Five scenarios, two tracks, one shared state per scenario.

---

## 1. Status: read this first

| Class | State |
| --- | --- |
| **Implemented and verified locally** | The pipeline reversal, both new scenarios, the seed dual-file contract, the converter, the volume checker, five EasyDistill configs, the test suite |
| **Implemented but unverified** | The Bailin API was **never called** — no credential, no quota. No `messages` output exists. Every token figure is an estimate, not a measurement. |
| **Needs review before use** | Bailin has **no officially declared medical capability**; its base URL, pricing, free quota and concurrency are **not published on its site**; three rule tables in the parent package still need domain-expert review; one upstream generator defect blocks the SFT track (§8) |

**There is no performance claim anywhere in this document.** What is verified is the machinery; what is not verified
is the teacher and the arithmetic.

---

## 2. The pipeline runs backwards on purpose

The request was "distil Kev training data from Bailin". But the parent package already generates Kev records with
**zero LLM tokens and zero label drift** — six generators, 787 records each, validated. Asking an LLM to produce
those labels would *introduce* drift, contradicting the parent package's own principle that the threshold table is
the authority.

So the teacher does only what it is good at:

```
 rule engine samples state + computes labels        zero tokens, zero drift
          |
          +--> <scenario>.state.jsonl ------> seed_to_kev.py --> Kev decision records
          |      sidecar: the only source of labels                      |
          |                                                              +--> train Kev-0.8B / 4B
          +--> render state as an instruction
                 |
                 +--> <scenario>.seed.jsonl --> EasyDistill --> Bailin writes the answer
                    |                          -> judge -> filter -> build_sft
                    |                                     |
                    |                     only ever sees the instruction
                    |                                     |
                    +--------------------------> generative SFT samples --> SFT a medical assistant
```

Three consequences worth stating plainly:

- **Labels are structurally beyond the LLM's reach.** `seed_to_kev.py` reads only `state.jsonl`; it never opens the
  SFT file. Verified: with 100% deliberately wrong teacher answers injected, the Kev output is **byte-identical**
  (same SHA-256).
- **Both tracks share one state**, so there is no second copy of the data to drift.
- **The Kev track costs 0 LLM tokens.** At ~2,500 tokens per record, the ~8M tokens a naive design would spend on this
  layer's 3,148 Kev records (4 scenarios × 787) are not spent.

### 2.1 What the teacher may and may not do

| Bailin does | Bailin does not |
| --- | --- |
| Write varied clinical narrative | Decide any threshold (critical value, dose, contraindication) |
| Produce the reference answer | Supply any value that becomes a Kev `label` |
| Score candidates in the judge stage | Vouch for medical correctness |

The last row is why §11 makes human adjudication mandatory. Bailin's homepage makes **no medical capability
claim**; its medical knowledge is an unbacked variable, and a domain expert — not a better prompt — closes that gap.

---

## 3. Teacher access: verified vs unverified

### 3.1 Verified

| Item | Value |
| --- | --- |
| Family | Ant Ling: Ling (language), Ring (reasoning), Ming (omni-modal) |
| API | **OpenAI-compatible**; platform "Ling Studio" |
| Developer docs | `https://developer.ant-ling.com/zh-CN/docs` (models: `.../docs/models/`) |
| Model lineage | Ling-1T / Ring-1T (2025-09/10) → Ling-2.5-1T (2026-02) → Ling-2.6-1T (2026-04) → **Ling-3.0-flash** (2026-07, open-sourced to `inclusionAI/Ling-3.0-flash`) |
| Stated focus | Ant Group names healthcare among its target domains |

### 3.2 NOT verified — resolve before spending anything

| Item | Status |
| --- | --- |
| **Base URL** | Not published on the homepage. A 2026-02 third-party blog gives `https://api.tbox.cn/api/llm/v1`; the official docs live on a different domain and the two were **not cross-checked**. |
| **Model id** | The lineup turns over every 1–2 months. Pin it from the models page at implementation time; do not hardcode. |
| **Pricing** | The homepage says "limited-time discount" and nothing more. No per-million-token figure published. |
| **Free quota / concurrency** | Third-party: ~500k tokens/day, 1 concurrent request, 3 requests/minute. **Unconfirmed.** Used below only for order-of-magnitude estimates. |
| **Medical capability** | **None declared.** |

Because the base URL is unconfirmed, `medical/distill/configs/*.yaml` reference it as `${KEV_GEN_BASE_URL}` rather
than baking in a value that may be wrong.

### 3.3 Fallback if the cloud path fails

`Ling-3.0-flash` is open-sourced. Self-hosting it behind vLLM and pointing EasyDistill's `openai` backend at
`localhost` removes the quota ceiling and keeps PHI in-network. Not the chosen path, but it is the hedge — and the
only option that scales past Tier A without a procurement conversation.

---

## 4. EasyDistill 2 integration

EasyDistill 2 is [ModelScope's](https://github.com/modelscope/easydistill) Apache-2.0 toolkit for turning black-box
teachers into training data. Verified relevant facts:

- **Backend-agnostic**: `type: openai` accepts any OpenAI-compatible endpoint, which is how Bailin is reached
- **Composable operators**: generation, evaluation, filtering, rewriting, balancing, preference scoring
- **Every pipeline stage is also a standalone `job_type`**, so a run can be resumed from an intermediate JSONL
- Exports work directly with **LLaMA-Factory** and **ms-swift**
- EasyDistill 2 is a rewrite; **not backward compatible with 1.0**

The pipeline used is `advanced_instruct_distill`: expand → generate → judge → filter → build_sft.

`instruction_key: instruction` matches the seed files. `resume: true` is set in every config so an interrupted run
does not re-spend quota. Credentials come from environment variables — **never written into a YAML**.

---

## 5. Data sources and preprocessing

### 5.1 The seed dual-file contract

| File | Fields | Read by |
| --- | --- | --- |
| `<scenario>.seed.jsonl` | `id` / `instruction` / `system` | EasyDistill |
| `<scenario>.state.jsonl` | `id` / `scenario` / `state` / `labels` / `soft` | `seed_to_kev.py` |

**Why two files.** EasyDistill documents that `id` is a row identifier and that `instruction_balance` "preserves the
original fields and adds `category`", but it does **not** guarantee that every stage passes through unknown
fields. Keeping `state` and `labels` in a sidecar the pipeline never touches means the join never depends on that
behaviour. `id` is the only join key and the files are written in the same order.

`instruction` is the structured state rendered as `key: value` lines — the same surface Kev itself renders — and it
**states facts only, never a label clue**.

### 5.2 Preprocessing chain

| Step | Rule |
| --- | --- |
| **De-identification first** | Names, IDs, phone numbers, admission numbers are hashed or replaced **before** any generator runs. The cloud teacher means structured fields leave the network, so this is a precondition, not a nicety. |
| **Rule-engine sampling** | State and labels are sampled together by the parent package's generators, so labels are true by construction. |
| **Date fields precomputed** | Any value needing date arithmetic (days on drug, gestational weeks) is computed during generation and carried as a number. This sidesteps the 0.8B date-arithmetic weakness (0.35) at the data level. |
| **No PHI in the repo** | Specs and generators carry only schema and rule tables. `data/` is git-ignored — verified via `git check-ignore`. |

### 5.3 The four sources, re-ranked for distillation

| Source | Role | Note |
| --- | --- | --- |
| Rule engine (parent package) | **The only label source** | Zero tokens, zero drift |
| LLM teacher | Narrative variety, reference answers, judge scores | The only token spend |
| Existing real data | Gold set for terminal evaluation | None exists yet; `convert_data.py` is the interface |
| Human-written | Style anchor, disagreement pool | `generate_data.py --dry-run` prints the prompt |

---

## 6. Distillation strategy and flow

```bash
# 1. seeds (zero tokens)
python3 kev/console/distill/make_seeds.py --all --n 500 --out-dir data/seeds

# 2. SFT track (the only step that spends tokens)
$env:KEV_GEN_API_KEY = "..."; $env:KEV_GEN_BASE_URL = "https://<official base URL>/v1"
easydistill --config kev/console/distill/configs/inquiry.yaml

# 3. Kev track (zero tokens; labels never touch the LLM)
python3 kev/console/distill/seed_to_kev.py --scenario inquiry \
  --seed-file data/seeds/inquiry.seed.jsonl --state-file data/seeds/inquiry.state.jsonl \
  --out data/inquiry.jsonl

# 4. reconcile the teacher against the rules (reporting only)
python3 kev/console/distill/seed_to_kev.py --scenario inquiry --from-sft data/sft/inquiry/inquiry.sft.jsonl \
  --report data/inquiry.reconcile.json

# 5. volume and budget gate
python3 kev/console/distill/check_volume.py --scenario inquiry --records data/inquiry.jsonl \
  --from-sft data/sft/inquiry/inquiry.sft.jsonl --budget 8000000
```

**Run scenarios serially, not concurrently.** A cloud endpoint with a low concurrency ceiling punishes parallel
scenarios with 429s, and `resume: true` makes serial batches cheap to resume.

**`--from-sft` is a diagnostic, never a data path.** It compares the teacher's answers with the rule labels and
reports an agreement rate. A low rate flags records for human review; it does not change a single label. The
mechanism is structural: `build_records()` iterates the *seed* file and reads labels only from the sidecar.

### 6.1 Flow, stage by stage

| Stage | What happens | Failure handling |
| --- | --- | --- |
| Seeds | Rule engine samples state + labels; state is rendered into an instruction | Retry with a different `--seed`; a scenario producing `None` falls back to an unsteered record |
| Expand | EasyDistill diversifies each seed into several phrasings | Lower `num_per_seed`; the stage is the cheapest, so raise it before touching generation |
| Generate | Bailin writes the reference answer | 429 → back off; `resume: true` restarts from the last completed stage |
| Judge | LLM scores correctness, helpfulness, informativeness, generalization | A too-strict `pass_score` silently empties the dataset — check the count after this stage, not only at the end |
| Filter | Drops rows failing the thresholds | Compare pre/post counts; a >50% drop means the judge and the spec disagree, not that the data was bad |
| build_sft | Emits `messages` + `metadata` | — |

**The judge stage is the quiet failure.** It reads the response, so it roughly doubles cost, and a mis-set threshold
can empty the pipeline without any error. Check the row count after `filter` every time.

---

## 7. Scenario coverage

| Scenario | Kev track | SFT track | Shared state |
| --- | --- | --- | --- |
| **问诊 / inquiry** | reuses `triage` | doctor-style consultation dialogue | `chief_complaint`, `age`/`sex`, `symptoms`, `duration`, `history`, `vitals` |
| **用药指导 / medication** | reuses `medication-review` | indication, dose, interactions, contraindications | `drug`, `dose`, `route`, `days_on_drug`, `age`, `renal`, `allergies` |
| **诊断建议 / diagnosis** | **new** `diagnosis` spec | differential, rationale, suggested tests | `presenting`, `vitals`, `lab_results`, `imaging`, `comorbidities` |
| **病历摘要 / record-summary** | **new** `record-summary` spec | six-element structured summary | `record_text`, `diagnosis`, `medications`, `plan` |
| **医学知识问答 / knowledge-qa** | **none — see below** | open medical Q&A | `topic`, `question` |

### 7.1 Why knowledge-QA has no Kev track

Kev is a pointer-readout model: it scores **pre-declared options** and emits **no tokens at all**. An open medical
question has no such option set. Forcing it into a Kev task would reduce it to a 4-way multiple-choice item and
throw away everything that makes the Q&A track valuable. So it is a single-track scenario, and `check_volume.py`
reports it as such rather than failing.

### 7.2 Reuse kept the new surface small

Two of the five scenarios are clinically isomorphic to scenarios the parent package already ships, so their specs
and generators are reused unchanged: `inquiry` → `triage`, `medication` → `medication-review`. Only `diagnosis`
and `record-summary` are new. Net new code: 2 specs, 2 generators, 3 distill scripts, 5 configs.

### 7.3 Label floors constrain option counts

A `choice` question with `N` options needs each option to appear as correct at least 5% of the time, which forces
a positive rate of at least `5N%`. `diagnosis` uses 9 directions (≥45% positive, easily met) and
`record-summary` uses 7 (≥35%). This is the arithmetic behind why `critical_item` was reduced from 10 options to 6
in the parent package — a 10-option question would demand a 50% critical rate, which is clinically absurd.

---

## 8. Data volume: sizing and guarantees

### 8.1 The assumptions (estimates, not measurements)

| Assumption | Value | Basis |
| --- | --- | --- |
| Tokens per SFT record | ~1,000 | prompt ~250 + completion ~750; Chinese medical answers run long, reasoning models longer |
| Judge overhead | ≈2.5× generate | the judge reads the response, so it roughly doubles cost |
| Free tier (unconfirmed) | 500k tokens/day | third-party, 2026-02 |
| Request rate (unconfirmed) | 3/min = 4,320/day | third-party |
| Calls per record | ~3 | expand, generate, judge |

### 8.2 The arithmetic

| Tier | Per scenario | 5 scenarios | generate | with judge | Free-tier days | Request-rate days |
| --- | --- | --- | --- | --- | --- | --- |
| **A — smoke** | 500 | 2,500 | ~2.5M | **~6.3M** | **~13 days** | ~1.7 days |
| **B — recommended** | 2,000 | 10,000 | ~10M | **~25M** | **~50 days** | ~6.9 days |
| **C — full** | 5,000 | 25,000 | ~25M | **~63M** | **~125 days** | ~17.4 days |

**Token quota is the binding constraint**, not request rate — Tier B is ~7× slower on quota than on rate. The two
bottlenecks must be stated separately or the estimate is meaningless.

### 8.3 The free tier only covers Tier A

This is the single most important number in the document. Tier B requires either a paid quota or the self-hosted
fallback in §3.3.

**Tier A is therefore designed as a metered pilot, not a throwaway smoke test.** After it runs,
`metadata.usage.total_tokens` gives the **real** per-record cost. That measured number — not this estimate — is
what should be used to re-budget Tier B/C and to quote for a paid quota. Every row in §8.2 recomputes from one
substitution.

### 8.4 Volume guarantees

`check_volume.py` fails loudly rather than letting a thin dataset reach the trainer:

| Assertion | Threshold |
| --- | --- |
| Records per scenario | `--expect` (default 787) |
| Every label's share | ≥ 5% (`split_data.py`'s own floor) |
| Every option appears as correct at least once | else the model cannot learn it |
| Questions per scenario | ≥ 100, for a stable temperature fit |
| Token total | `--budget`, when given |
| Teacher/rule agreement | reported per question; low agreement routes records to human review |

The Kev track is asserted at **0 LLM tokens** explicitly, so nobody later mistakes the two tracks' costs for each
other.

---

## 9. Kev training data format and requirements

One JSON object per line, in the System One request shape plus a `label` on every question:

```json
{"state": {"patient": "male 34", "chief_complaint": "……", "vitals": "……"},
 "questions": {
   "department": {"type": "choice", "instructions": "……", "criteria": {"cardiology": "……"}, "label": "cardiology"},
   "immediate_human": {"type": "noul", "instructions": "……", "label": false},
   "acuity": {"type": "score", "instructions": "……", "criteria": ["…", "…", "…"], "label": 0}}}
```

| Requirement | Value |
| --- | --- |
| State tokens | **≤ 384** — over is **silently dropped by the trainer** |
| Packed request | ≤ 2048 |
| Per-question branch | ≤ 1024 |
| `choice` label | must be one of the `criteria` keys |
| `noul` label | must be a JSON boolean |
| `score` label | integer `0 .. len(criteria)-1` |
| `target` (optional) | non-negative weights over legal keys, total > 0 |
| Label floor | every option ≥ 5% |

Validate before training:

```bash
python3 skills/kev-finetune/scripts/split_data.py data/inquiry.jsonl
modal run skills/kev-finetune/scripts/kev_modal.py::validate --data data/inquiry --init-from jaredpalmer/kev-0.8b
```

Run `validate` **once per model size** — each has its own tokenizer, and `STATE_CHARS_WARN = 1400` in
`split_data.py` is annotated as "~384 tokens of **English**", which is too loose for Chinese.

**The balanced-prior trap carries over.** A balanced critical-value dataset has a critical rate of ≥30% while real
reports run 1–3%. Model probabilities are conditioned on the balanced prior; re-derive operating thresholds against
real traffic before go-live.

---

## 10. Medical SFT data format and requirements

EasyDistill's standard SFT output, which LLaMA-Factory and ms-swift consume directly:

```json
{
  "messages": [
    {"role": "system", "content": "你是一位临床分诊助手……"},
    {"role": "user", "content": "以下是一位患者到院分诊台的情况……"},
    {"role": "assistant", "content": "……"}
  ],
  "metadata": {
    "source": "teacher_model", "model": "…", "request_id": "…", "backend": "openai",
    "usage": {"completion_tokens": 750, "prompt_tokens": 250, "total_tokens": 1000}
  }
}
```

| Field | Requirement |
| --- | --- |
| `messages` | OpenAI/ShareGPT style. Exactly one `assistant` turn — that is the training target |
| `messages[].content` | Multi-turn dialogue is **not** used here; each seed is single-turn |
| `metadata.model` | **Record the teacher's version.** It is the only provenance that survives into the trained model |
| `metadata.usage.total_tokens` | The only source of real cost data; drives §8.3's re-budget |
| `system` | Per-row system prompt; the seeds carry a scenario-specific one |

**The system prompts are safety-relevant, not decoration.** Each encodes a refusal boundary — no definitive
diagnosis, no dosing outside the formulary, no fabricated citations — plus a "seek urgent care if…" instruction.
Loosen them and the model learns to give confident answers to questions the teacher itself was told to hedge.

---

## 11. Quality assessment

Four layers, each catching what the one above cannot.

### 11.1 Structure

`split_data.py` — 0 invalid lines, 0 label conflicts, no state over the token limit. Fully automated.

### 11.2 Distribution

`check_volume.py` — record counts, the 5% label floor, option coverage, the ≥100-question minimum. Fully automated.

### 11.3 Teacher/rule agreement

`seed_to_kev.py --from-sft` — the teacher independently states an answer; the report gives the agreement rate per
question and lists the disagreements. This is the cheapest strong signal available before human review: **a low rate
means the teacher and the rule engine see different boundaries**, which is exactly the failure mode that produces a
confidently wrong model. Combine with the parent package's `make_goldset.py audit`, which compares two vendors'
labels on the same states and gates on the **worst** question rather than the average.

### 11.4 Human layer — mandatory

| Item | Owner | Blocking |
| --- | --- | --- |
| Gold set adjudication, 150–250 records | clinician / pharmacist | yes — the only real measurement |
| Critical-value threshold table | laboratory | yes |
| Drug rule table | pharmacy | yes |
| Nursing checklist items | nursing | yes |
| Disagreement records from §11.3 | clinician | yes |

⚠️ **Bailin carries no official medical endorsement.** Its knowledge is a general-purpose model's, so expert review
is the only real quality gate. A pipeline that skips this produces data that is internally consistent and
externally unvalidated — the hardest kind of bad data to detect later.

### 11.5 Medical-specific red lines

- No fabricated literature or guideline citations
- No definitive diagnosis; differential and uncertainty only
- Dosing advice stays within the formulary
- Date-dependent facts arrive precomputed as fields, never as arithmetic for the student to do
- Every clinical answer carries a "when to seek urgent care" escalation path

---

## 12. Compliance and privacy

You chose the cloud API, so structured fields **leave the network**. That makes the following blocking, not advisory.

| Item | Requirement |
| --- | --- |
| De-identification | Completed **before** any generator runs. Generators and EasyDistill only ever see de-identified fields. |
| Data egress assessment | Confirm de-identified structured fields may be sent to the external API; sign a data-processing agreement if required |
| Credentials | Environment variables only; `medical/distill/configs/*.yaml` reference `${KEV_GEN_API_KEY}` and contain no secrets (asserted by the config test) |
| Model publication | `publish` is private by default; **never** pass `--public` for a medical model |
| Provenance | `metadata.model` records which teacher produced every sample |
| Repository hygiene | `data/` is git-ignored (verified with `git check-ignore`); specs and generators contain only schema and rule tables |

**The fallback matters here.** If the egress assessment fails, self-hosting `Ling-3.0-flash` (§3.3) resolves both
the compliance question and the quota ceiling at once.

---

## 13. Known upstream defect that blocks the SFT track

`medical/generators/gen_triage.py` lists pediatric keywords ("儿童咳嗽", "小儿呕吐", "儿童发热", "高热惊厥") as
independent entries in `SYMPTOMS`, while age sampling spans 2–78 years. The result is clinically incoherent records:
**measured at 34 of 500 inquiry seeds (6.8%)**, worst case `female 78 | 小儿呕吐 | dept: pediatrics`.

| Track | Impact |
| --- | --- |
| **Kev** | Labels stay self-consistent (the table lookup still decides), so the model learns a literal string shortcut. A realism problem, not a correctness one. |
| **SFT** | The teacher is asked to reason about a 78-year-old with "小儿呕吐" and will produce a confused reference answer. **This must be fixed before distillation.** |

The fix is an age guard in that vocabulary (pediatric entries only sampleable when `age < 14`). That is a **logic
change to an upstream generator** and needs separate authorization; this layer deliberately does not make it.

---

## 14. Verified vs unverified

| Verified locally | How |
| --- | --- |
| Six generators produce 787 records each | `gen_* --n 787 --seed 0` |
| Skill validator accepts them | `split_data.py`: 0 invalid, 0 conflicting labels |
| Label floors respected | no `under 5%`, no `never labelled` warnings |
| Sizing arithmetic | `plan_size.py`: `generate at least 787 records` for every spec |
| Seeds: 5 scenarios × 500 | `make_seeds.py --all --n 500` |
| Converter rebuilds records from the sidecar | 500 records, 0 invalid, 0 conflicts, 0 duplicate states |
| **Label invariance under a hostile teacher** | 100% wrong answers injected → Kev output **byte-identical** (SHA-256 match); agreement correctly fell to 0.5% |
| Volume gate fails loudly | exit 1 on budget overrun and on record-count mismatch |
| Five configs are legal YAML | `yaml.safe_load` + assertions on job_type, backend, env-var credentials, stage order, `resume: true` |
| `data/` is git-ignored | `git check-ignore` exit 0 |

| **Not** verified | Why |
| --- | --- |
| Any Bailin API call | No credential, no quota. The teacher has never been invoked. |
| Any real `messages` output | Follows from the above |
| Every token figure | Estimates from the stated assumptions; only Tier A produces real numbers |
| The base URL, pricing, quota, concurrency | Not published by Bailin; third-party figures unconfirmed |
| Medical quality of teacher answers | Requires §11.4's human layer, which has not run |
| Whether the judge thresholds are well set | Only observable after a real run |

---

## 15. Go-live checklist

- [ ] Confirm Bailin's base URL and model id from `developer.ant-ling.com/zh-CN/docs`
- [ ] Obtain pricing; **run Tier A first** and re-budget from its measured `usage.total_tokens`
- [ ] Complete the data-egress assessment, or switch to the self-hosted fallback
- [ ] Authorize and fix the `gen_triage.py` pediatric-vocabulary defect (§13)
- [ ] Have the laboratory, pharmacy and nursing tables reviewed
- [ ] Generate seeds, then adjudicate a 150–250 record gold set
- [ ] Run Tier A; check the row count after `filter`; read the teacher/rule agreement per question
- [ ] Decide Tier B on the basis of Tier A's measured cost, not this document's estimate
- [ ] Confirm no credentials are in any YAML and that `data/` stays ignored
- [ ] Confirm the medical model is never published with `--public`

---

## 16. File inventory

| Path | Role |
| --- | --- |
| `docs/sft-distill.md` | This document |
| `docs/sft-distill_CN.md` | Complete Chinese translation, matched section by section |
| `kev/console/distill.md` / `_CN.md` | Command reference and troubleshooting |
| `kev/console/distill/README.md` | Layer overview, seed contract, adding a scenario |
| `kev/console/distill/make_seeds.py` | Seed generator; writes both files |
| `kev/console/distill/seed_to_kev.py` | Converter; `--from-sft` reconciliation |
| `kev/console/distill/check_volume.py` | Distribution and budget gate |
| `kev/console/distill/configs/*.yaml` | Five EasyDistill configs |
| `kev/console/distill/seeds/README.md` | Seed directory notes |
| `docs/medical/specs/diagnosis.json` | New: diagnosis suggestion spec |
| `docs/medical/specs/record-summary.json` | New: record summary spec |
| `kev/console/generators/gen_diagnosis.py` | New: diagnosis generator |
| `kev/console/generators/gen_record_summary.py` | New: record summary generator |
| `tests/test_medical_distill.py` | Seed, converter, invariance, volume and config tests |
| `.gitignore` | Added `data/`, `medical-data/` |

`skills/kev-finetune/` and the `kev/` library are **untouched**.

---

[简体中文](./sft-distill_CN.md) · Implementation: [`medical/distill/`](./medical/distill/README.md) ·
Parent design: [`sft-medical.md`](./sft-medical.md)
