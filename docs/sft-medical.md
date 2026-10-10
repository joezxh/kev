<p align="center">
  <a href="./sft-medical.md"><img alt="English" src="https://img.shields.io/badge/English-blue?style=for-the-badge"></a>
  <a href="./sft-medical_CN.md"><img alt="中文" src="https://img.shields.io/badge/%E4%B8%AD%E6%96%87-orange?style=for-the-badge"></a>
</p>

# Fine-tuning Kev for healthcare decisions

[简体中文](./sft-medical_CN.md) · Implementation directory: [`medical/`](./medical/README.md) · Upstream skill: [`skills/kev-finetune`](../skills/kev-finetune/SKILL.md) · Distillation plan: [`sft-distill.md`](./sft-distill.md)

Fine-tune **Kev-0.8B** and **Kev-4B** on your own healthcare decisions and get *calibrated probabilities* back
instead of generated text — across five decision types: triage routing, critical-value review, medication and
insurance review, nursing quality control, and ICD coding.

Kev is a pointer-readout model scored with log loss. **It emits no tokens at all**, so it cannot hallucinate a
diagnosis and cannot leak PHI through free text. That property is the reason it fits this domain at all, and it is
the reason this whole package is built the way it is.

---

## 1. Status: read this first

This package is **built and locally verified**. It is **not** a trained model, and no number in this document
describes a model trained on your data. The table below is the honest split.

### 1.1 Implemented and verified locally

| Item | Evidence |
| --- | --- |
| Four scenario generators emit 787 records each | `gen_critical_value.py`, `gen_medication_review.py`, `gen_triage.py`, `gen_nursing_quality.py` at `--seed 0` |
| Every record passes the upstream validator | `split_data.py` reports **0 invalid lines, 0 conflicting labels** (nursing drops 3 duplicate states → 784 valid) |
| No label falls under the 5% floor | no `labels [...] under 5%` warning, no `never labelled` warning, in any of the four scenarios |
| Record count is arithmetically correct | `plan_size.py` prints `generate at least 787 records` for all five specs |
| Minimal pairs are genuinely minimal | `gen_critical_value.py` reports 89 twins built; independent inspection of the emitted JSONL finds 86 record pairs differing in **exactly one** field, 82 of which flip a label |
| The dual-size driver emits a correct command sequence | `run_matrix.py --dry-run` for four scenarios; correctly refuses `icd-coding --sizes 8b,4b` and unknown sizes |
| Run names are validated before Modal sees them | `fullmatch` rejects `critical-value-0.8b-v1` (dot), accepts `critical-value-8b-v1` |
| Gold-set sampling and disagreement audit work | `sample` drew 200 records with rare labels represented; `audit` flagged `is_critical` at 12.7% and exited 1 |
| Test suite green | 16 new tests pass; 34 pass together with `test_skill_scripts.py` |
| All intra-package links resolve | every relative link and both anchors in `medical/` verified |

### 1.2 Implemented but **not** verified — no real environment was available

| Item | What is missing |
| --- | --- |
| **No training run has ever happened** | There is no `result.json` anywhere. **This document therefore quotes no accuracy, Brier, ECE or coverage figure for any model trained on your data.** Every performance number below is Kev's own published public benchmark, not a medical result. |
| Neither baseline has been measured | `evaluate --run jaredpalmer/kev-0.8b` and `--run jaredpalmer/kev-4b` have not been run. The `--baseline-acc 0.75` used in sizing is a **placeholder default**, not a measurement. |
| The Chinese token budget is unmeasured | `kev_modal.py::validate` has not been run. Whether your Chinese mixed-language states stay under 384 state tokens is **assumed from a character count, not verified**. |
| No real data exists | Every record is synthetic. There is no clinical data in this repository. |
| The gold set is unadjudicated | The 200 records `make_goldset.py sample` produces are a **review pool**. No clinician or pharmacist has checked or signed them off. |
| The distillation path was never executed | `generate_data.py` was not run. Only the programmatic path was tested. |
| Nothing is deployed | `modal deploy` was never invoked. Only the command sequence was verified. |
| Cheaper GPUs are untested | Training on L4/A10G may be much cheaper, but the skill only documents H100 timings. |

### 1.3 Requires domain-expert review before go-live

**The three rule tables in this package are literature-based defaults. They are not any hospital's actual
standards.** They are structurally correct and internally consistent, but they are placeholders for your own
policies:

| Table | File | Must be replaced by |
| --- | --- | --- |
| Critical-value thresholds, notification tiers, critical zones | `gen_critical_value.py` | **Your laboratory's** critical-value standard, item by item |
| Drug contraindications, dose ceilings, special populations | `gen_medication_review.py` | **Your formulary and pharmacy** rules |
| Nursing quality-control checklist items and severities | `gen_nursing_quality.py` | **Your nursing department's** checklist |

When you change a threshold, change it in **two** places: the generator's rule table and the spec's `guidance`.
They must agree, or the synthetic data and the distilled data silently diverge.

---

## 2. What this is, and how it relates to `medical/`

Two layers, with `AGENTS.md`'s "one canonical home" rule applied:

| Layer | Path | Role |
| --- | --- | --- |
| **Topic entry** | `docs/sft-medical.md` (this file) + `docs/sft-medical_CN.md` | The narrative: why this design, what is verified, what is not, what to do before go-live |
| **Implementation** | [`docs/medical/`](./medical/README.md) | 5 scenario specs, 7 generator modules, the dual-size driver, 16 tests |

Read this document to decide *whether* and *how*. Go to `medical/` to run it.

---

## 3. Base checkpoint correction — read this before anything else

The single easiest way to fail this project is to fine-tune a bare base model.

`skills/kev-finetune/SKILL.md` states it in the Gotchas:

> `--init-from` must be a Kev checkpoint (Hub id or a run name on the volume); base, LoRA rank and head size
> are read from it. **Do not pass `--base`.**

The reason is the **pointer head**: Kev's readout layer reads pointers over the option boundary tokens. A bare
Qwen checkpoint has no such layer, so there is nothing to initialize it from.

| | Kev-0.8B | Kev-4B |
| --- | --- | --- |
| Hub id | `jaredpalmer/kev-0.8b` | `jaredpalmer/kev-4b` |
| Base | `Qwen/Qwen3.5-0.8B-Base` (Apache-2.0) | `Qwen/Qwen3.5-4B-Base` (Apache-2.0) |
| Form | LoRA adapter + pointer head | LoRA adapter + pointer head |
| Weights revision | `9a45d25e` | `139fdd94` |
| Shipped temperature | 2.35 | 2.41 |

- ✗ `--init-from Qwen/Qwen3.5-0.8B` / `Qwen/Qwen3.5-4B` — no pointer head
- ✓ `--init-from jaredpalmer/kev-0.8b` / `jaredpalmer/kev-4b`
- `kev_modal.py` has `DEFAULT_INIT = "jaredpalmer/kev-4b"`, so **the 0.8B track must pass `--init-from` explicitly**

### 3.1 Four-layer inheritance

```
Qwen/Qwen3.5-0.8B-Base (frozen)      Qwen/Qwen3.5-4B-Base (frozen)
  └─ jaredpalmer/kev-0.8b              └─ jaredpalmer/kev-4b
     T=2.35 (public data)                 T=2.41
        └─ <scenario>-8b-v1                 └─ <scenario>-4b-v1
           medical delta; head.pt carries      medical delta; head.pt carries
           a temperature refit to your data     a temperature refit to your data
```

What you inherit for free:

- `lr=0.0` reuses each init's own training arguments — **0.8B is 4e-5, 4B is 2e-5**. `MAX_DELTA_LR = 5e-5`
  is a hard ceiling, so a medical delta never trains hotter than the released deltas did.
- `--replay 2000` mixes in public `decision-v7` records to preserve general skill.
- One `train` call does all of: delta fine-tune → fit temperature on the calibration slice → **refit the baseline's
  temperature on your calibration slice too**, so the zero-shot comparison is fair → score development → paired
  bootstrap → a 300-record public forgetting check.

---

## 4. Dual-size architecture: one dataset, two models

**The fact this design rests on:** `split_data.py` groups records for partitioning by **state hash** (sha256 of the
case-folded, whitespace-normalised state). That grouping is **model-independent**. So a single
`data/<scenario>/{train,calibration,development}.jsonl` can feed both sizes' `--init-from` directly.

Four consequences:

1. **Distillation is paid for once.** One dataset, one gold set, one dev set, two models.
2. **Cross-size `compare` is valid.** Both runs are scored on the same `development.jsonl`, so
   `compare --a x-4b-v1 --b x-8b-v1` gives a real paired bootstrap. The 0.8B-vs-4B gap becomes a **measurement**
   instead of an opinion.
3. **An 8-minute feedback loop.** 0.8B trains in about 8 minutes on an H100. Use it to prove the spec and the rule
   tables are right *before* spending 15 minutes per 4B round discovering a threshold was wrong.
4. **Tiered routing and a fallback.** Both endpoints coexist; route low-risk high-volume decisions to 0.8B and
   high-risk semantic decisions to 4B, with independent thresholds. While 4B is cold-starting, 0.8B can serve.

### 4.1 The two sizes are complementary, not successive replacements

| Dimension | Kev-0.8B | Kev-4B |
| --- | --- | --- |
| Default lr (from init) | 4e-5 | 2e-5 |
| Typical train time (400–1000 records, H100) | ~8 min | ~12–15 min |
| Serving GPU (fine-tune default) | `L4` | `L4` (`L40S` under load) |
| Cold start after idle | ~40 s | ~35 s |
| Warm model time (6 questions, new/repeat) | 23 / 16 ms | 42 / 28 ms |
| Delta size (published tarball, reference) | 46 MB | 131 MB |
| breadth-v1 chance-corrected index | 23.3 | 38.0 |
| transfer-v4 locked OOD (acc / Brier) | 0.697 / 0.397 | 0.838 / 0.224 |
| hard-v1, programmatic labels (acc / Brier) | 0.665 / 0.460 | see model card |
| Validated context | 8,192 tokens | 8,192 tokens |

> The four benchmark rows are **Kev's published public numbers**, reproduced so you can size the two models against
> each other. They are not healthcare results, and nothing here predicts what either model will score on your
> decisions. Only your own `evaluate` runs will tell you that.

### 4.2 Three things 0.8B must not be used for

Each of these is a measured capability limit that lands directly on healthcare work:

| Limit | Measured | Consequence in this domain | Mitigation |
| --- | --- | --- | --- |
| Date arithmetic | 0.35 on the `deadline` family (4B: 0.65) | Weeks of gestation, course length, expiry dates | **Precompute date fields during generation** — see §8.4. `KEV_DATE_FACTS=1` may assist but is untested here. |
| Knowledge is set by the base | MMLU-Pro as low as 0.230 | ICD coding plausibility needs clinical knowledge | **4B only** for that scenario |
| Tool routing | When2Call 0.133 — *below chance* | Never let it decide "should I look something up in the external system?" | Forbid it explicitly in the spec's `guidance` |

**0.8B also over-confesses less reliably.** The release notes record that one refit on held-out data made 0.8B's
calibration **worse beyond the registered tolerance**, while 4B did not improve (Brier delta −0.0001
[−0.0005, +0.0003]). Practically: hold 0.8B to a stricter `mean_conf` vs `acc` and `confident_error_rate` gate than
4B. See §10.

### 4.3 Run-name rules, including a trap

`kev_modal.py` validates run names with `NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}")` and **`fullmatch`** —
letters, digits, hyphen, underscore, up to 80 characters. **No dots.**

- ✓ `critical-value-8b-v1`, `triage-4b-v2`
- ✗ `critical-value-0.8b-v1` — **the dot is rejected**

So the size tag is written `8b` / `4b`, never `0.8b`. Names are **immutable**: if `/runs/<name>` already exists you
get `FileExistsError` and must retry under a new name. A `modal run` that dies on a network error may already have
started a container — check `modal app list` before relaunching.

`run_matrix.py` applies the same `fullmatch` locally, so a bad name fails before you generate any data.

---

## 5. Record count

Sizing uses the McNemar paired approximation in `plan_size.py`
(`baseline_acc=0.75`, `min_gain=0.05`, `power=0.8`, `regressions=0.05`, 15%/15% splits). The number of development
*questions* is fixed at **469**; the record count falls as you pack more questions onto each shared state.

| Questions per record | 1 | 2 | 3 | **4 (this package)** | 5 |
| --- | --- | --- | --- | --- | --- |
| Development records | 469 | 235 | 157 | 118 | 94 |
| Calibration records | 469 | 235 | 157 | 118 | 94 |
| **Total records** | 3127 | 1567 | 1047 | **787** | 627 |
| Train records | 2189 | 1097 | 733 | 551 | 439 |

All five specs in this package carry **4 questions per record**, so each scenario needs **787 records**
(551 train / 118 calibration / 118 development), shared by both sizes.

Why packing questions is the whole economics: one state carrying four decisions costs 787 records; four datasets
with one question each cost 4 × 3127. This, not parameter count, is why a decision model is cheap.

Two caveats:

- The **unpaired** upper bound does depend on `--baseline-acc`: 1092 at 0.75, 1468 at 0.60. Since 0.8B's baseline
  is weaker, its bound is larger — which is exactly why you must measure both baselines before committing.
- Calibration must carry **at least 100 questions** or the temperature fit and the scores are unstable.

The skill's own evidence on why volume is not optional: 400 records produced **+0.6 points with a ±6 point CI**
(nothing), while 1050 records produced **+5.9 points, CI [+2.3, +9.7]**. Under pure distillation, size the dataset
correctly the first time; do not plan to top up later.

### 5.1 Where this differs from the original plan

| Item | Planned | Actual | Why |
| --- | --- | --- | --- |
| Record count | 627 (assuming 5 questions/record) | **787** (4 questions/record) | All five specs measure at 4 questions; `plan_size.py` prints 787 |

---

## 6. The five scenarios and which size handles them

| Phase | Scenarios | Tracks | Reasoning |
| --- | --- | --- | --- |
| **1** | Critical-value review + triage routing | Critical value on **both** tracks; triage 4B-led with one 0.8B run as a documented capacity control | Critical-value labels are fully rule-derivable → programmatic generation gives zero-drift labels. This is where the dual-size loop gets proven end to end. |
| **2** | Medication/insurance review + nursing quality | **Both** | Rules are explicit and option sets are bounded; reuses the loop and the generator base from phase 1 |
| **3** | ICD coding | **4B only** | Hardest: long text, large label space, rare combinations, and it needs clinical knowledge |

Do not run all five at once. Under pure distillation the worst failure mode is discovering after three runs that
the loop itself was broken and you cannot tell data problems from harness problems.

### 6.1 Question design per scenario

| Scenario | Type mix | Tracks | Design note |
| --- | --- | --- | --- |
| Triage routing | `choice` (department, 14) + `noul` (needs a human now) + `score` (acuity) | 4B lead | 14 departments keeps every option above the 5% floor at 787 records. `guidance` must fix the **priority when several symptoms compete** (e.g. chest pain + dyspnoea → cardiology). |
| Critical value | `noul` (is critical) + `score` (notification tier, 4) + `choice` (which panel) | Both | Labels derived from the threshold table. Records with a decision-critical element removed carry a 50/50 `target` to teach "no evidence, no confidence". |
| Medication review | `choice` (verdict) + `noul` (pharmacist review) + `choice` (issue type, 5) | Both | Rules from the formulary: contraindication, dose ceiling, duplicate therapy, special population, indication mismatch. When several rules fire, **severity takes the highest**. |
| Nursing quality | `choice` (issue type, 6) + `noul` (reportable) + `score` (severity) + `choice` (preventability, 3) | Both | Labels derived from checklist items. `issue_type=none` ⟺ severity 0 and not reportable. |
| ICD coding | `choice` (plausible within a candidate set) + `noul` (needs a coder) + `choice` (evidence gap) | 4B only | The model is **not** asked to emit ICD codes. Judge plausibility within a candidate set and route to a human. |

### 6.2 Two arithmetic constraints worth knowing before you design a spec

1. **A `choice` question needs a "nothing found" option.** It is asked on *every* record, including the ones where
   the situation does not arise. Without that option, a normal record gets a meaningless label.
2. **`N` options each needing ≥5% forces a minimum positive rate of `5N%`.** A 10-option question would require
   50% positives to be balanced. This is why `critical_item` is 6 options (≥30% critical) and not 10.

---

## 7. Data acquisition

You have no labelled data yet, so the primary routes are programmatic generation and distillation. The original
requirement covered all four sources; all four are kept.

| Source | Role here | Implementation |
| --- | --- | --- |
| **④ Programmatic** | **Preferred.** For critical value, medication, insurance and nursing, the label is a deterministic function of structured fields. It is also what makes the 0.8B track viable at all: 0.8B's base cannot supply medical knowledge, so the supervision has to be computed in advance. | `medical/generators/gen_*.py` |
| **② LLM distillation** | Secondary, for triage and ICD: rich semantics, rules too numerous to enumerate, highly varied phrasing. | `generate_data.py` with a carefully written `guidance` / `variety` / `state_example` |
| **① Existing data** | Reserved for the gold set. The day you have any, it is the most valuable asset you can add. | `convert_data.py`, then `split_data.py --holdout` |
| **③ Human-written** | Style anchor plus a disagreement pool. | `generate_data.py --dry-run` prints the exact prompt; answer it in batches (practical to ~100) |

### 7.1 In healthcare, public rule resources *are* "existing data"

An underrated fact about this vertical: critical-value standards, formulary contraindications and dose ceilings,
insurance directory restrictions, ICD coding rules and nursing checklists are **rules**, not labelled records —
but a rule engine can consume them into **zero-drift labels**. That is the structural advantage healthcare has over
generic LLM fine-tuning, and it is why both model sizes can share one dataset.

### 7.2 Four defences against a synthetic development set

When the dev set is synthetic, the loop can validate itself and prove nothing. Four defences:

1. **A human gold set.** `make_goldset.py sample` draws 150–250 records stratified by label combination, so rare
   combinations are actually reviewed. A clinician or pharmacist adjudicates each one against the spec's `guidance`
   and signs it off. Feed it in as `--holdout`: it is split half/half into calibration and development, **never
   trained on**, and `split_data` additionally drops synthetic rows sharing a state with it. Run the final
   evaluation on it **once**. Both sizes share the same gold set — that is what makes the size comparison trustworthy.
2. **Two-model disagreement audit.** Two vendors label the same states independently. `make_goldset.py audit`
   reports the rate **per question** and gates on the *worst* question, not the average — a 3% mean can hide one
   question at 13%, and in a medical workflow the per-question rate is what decides whether a labeller is trusted
   on that question.
3. **`guidance` iteration.** Every recurring mistake in `errors.jsonl` is a missing sentence in `guidance`. That is
   the mechanism the upstream skill names explicitly.
4. **Explicit label quotas.** Every label at ≥5%, and every option must have a chance to be correct — otherwise the
   model cannot learn an option it never sees as correct.

---

## 8. The programmatic generators

The generators do not ask a model anything. They sample structured fields, apply a threshold table or rule engine,
and write out labelled Kev records. Zero label drift is the only thing that matters here.

```
medical/generators/
├── README.md                  overview and how to add a scenario
├── common.py                  shared base: build + self-check, quotas, boundary sampling, minimal pairs
├── gen_critical_value.py      threshold tables, notification tiers, minimal pairs, soft labels
├── gen_medication_review.py   formulary rule engine
├── gen_triage.py              department priority arbitration, red flags
├── gen_nursing_quality.py     checklist items and derived severity
├── make_goldset.py            gold sampling + two-model disagreement audit
└── run_matrix.py              dual-size orchestrator (--dry-run prints the command sequence)
```

There is **no generator for ICD coding**: it needs real HIS/EMR extracts and clinical knowledge, and a
programmatic synthesis would produce clinically meaningless records. That scenario uses distillation plus human
spot-checking.

### 8.1 The quota comes before the record

Every generator first plans the batch's **labels** (`plan_targets`), then constructs fields that realise them.
The reason is `split_data.py`: it warns when a label falls under 5% and when an option is never correct. If you
sample fields first and derive labels afterwards, the distribution is whatever the sampling noise produced.

### 8.2 Minimal pairs teach the decision boundary

`gen_critical_value.py` emits pairs where the state differs in **exactly one measurement** and the label flips —
potassium 6.2 mmol/L against 5.9, everything else identical. This is what `references/data-generation.md`
recommends, and it is how Kev's own contrastive policy data was built. It teaches the model *which field the
decision depends on* instead of a shortcut feature. Verified two ways: `gen_critical_value.py` reports 89 twins
built, and independent inspection of the emitted JSONL finds 86 record pairs differing in exactly one field, 82 of
which flip a label. (The two counts differ because the inspection groups records by patient, context and lab-key
set, and counts every qualifying pair within each group.)

`common.minimal_pair()` is the shared guard: a twin that changes more than one field, or fails to flip any label,
is discarded rather than written.

### 8.3 Sampling must straddle the boundary

Values are drawn from both sides of each threshold **with extra density near the boundary**
(`|x - threshold| < δ`). Sample only far from the boundary and the model learns the trivial feature "very high
value" instead of the actual cut-off.

### 8.4 Date fields are precomputed — this is a 0.8B workaround, not a style choice

Wherever a decision would otherwise require date arithmetic (weeks of gestation, course length, days on drug,
expiry), the generator **computes the number and puts it in the state as a field**. The model's job becomes
reading a number, not doing arithmetic it is measurably bad at. `days_on_drug` arrives as an integer, never as
`started` / `prescribed` dates.

### 8.5 Balanced prior vs clinical prior — read before go-live

`split_data.py` requires every label at ≥5%, so a balanced critical-value dataset has a critical rate of **at least
30%**. In real reports critical values are roughly **1–3%**.

This is a genuine and deliberate mismatch. It exists because the balance is what makes the comparison
statistically meaningful — but it means **the model's probabilities are conditioned on the balanced prior**, so
setting a production threshold directly from an absolute probability will over-alarm on real traffic. Re-derive
the operating thresholds from `result.json` against real traffic before go-live. `data-format.md` covers the
mechanics.

---

## 9. Execution

```bash
# Print the full command sequence first — review before spending anything
python3 kev/console/generators/run_matrix.py --scenario critical-value --sizes 8b,4b --dry-run

# Execute (fail-fast; resume with --start-from <step>)
python3 kev/console/generators/run_matrix.py --scenario critical-value --sizes 8b,4b --secret kev-serve-key
```

Steps, in order: `plan_size → generate → split → validate ×2 → train(0.8B) → train(4B) → compare → deploy both`.
The same `data/<scenario>/` directory feeds both `train` calls — that is what makes the cross-size `compare` valid.

```bash
S=skills/kev-finetune/scripts

# 0. measure both baselines on the same small dev split (do this before trusting any sizing)
modal run $S/kev_modal.py::evaluate --data data/cv --name base-8b --run jaredpalmer/kev-0.8b
modal run $S/kev_modal.py::evaluate --data data/cv --name base-4b --run jaredpalmer/kev-4b

# 1. size the dataset
python3 $S/plan_size.py docs/medical/specs/critical-value.json --baseline-acc 0.75

# 2. generate once
python3 kev/console/generators/gen_critical_value.py --n 787 --out data/cv.jsonl --seed 0

# 3. draw the gold pool, have it adjudicated, then split with --holdout
python3 kev/console/generators/make_goldset.py sample data/cv.jsonl --n 200 --out data/cv.gold.jsonl
python3 $S/split_data.py data/cv.jsonl --out data/cv --holdout data/cv.gold.jsonl

# 4. CPU pre-flight for the Chinese token budget — both sizes
modal run $S/kev_modal.py::validate --data data/cv --init-from jaredpalmer/kev-0.8b
modal run $S/kev_modal.py::validate --data data/cv --init-from jaredpalmer/kev-4b

# 5. train both sizes on the same data
modal run $S/kev_modal.py::train --data data/cv --name cv-8b-v1 --init-from jaredpalmer/kev-0.8b
modal run $S/kev_modal.py::train --data data/cv --name cv-4b-v1 --init-from jaredpalmer/kev-4b

# 6. quantify the gap
modal run $S/kev_modal.py::compare --a cv-4b-v1 --b cv-8b-v1

# 7. two coexisting endpoints, each with its own app name
modal secret create kev-serve-key KEV_API_KEY=$(openssl rand -hex 24)
KEV_APP_NAME=kev-cv-8b KEV_SERVE_SECRET=kev-serve-key KEV_SERVE_RUN=cv-8b-v1 modal deploy $S/kev_modal.py
KEV_APP_NAME=kev-cv-4b KEV_SERVE_SECRET=kev-serve-key KEV_SERVE_RUN=cv-4b-v1 modal deploy $S/kev_modal.py
```

`medical/runbook.md` has every step with its expected output, how to read it, and what to do on failure, plus a
14-entry troubleshooting table.

### 9.1 The token limit is the one that fails silently

| Limit | Value |
| --- | --- |
| State tokens | **≤ 384** |
| Packed request | ≤ 2048 |
| Per-question branch | ≤ 1024 |

Records over the limit are **dropped silently by the trainer**, with a printed count. Worse,
`split_data.py`'s `STATE_CHARS_WARN = 1400` is annotated in the source as "~384 tokens of **English**" — it is
**too loose for Chinese**, and copying it will quietly lose data. Chinese 384 tokens is roughly 380–560 characters,
but medical text is dense in numbers, abbreviations and units, so the real figure is tighter. Use
`kev_modal.py::validate` as the authority, **once per size**, because each has its own tokenizer.

### 9.2 Two rules that are not negotiable

- **Never fit the temperature on `development.jsonl`**, and do not tune against it repeatedly. Reserve the gold set
  for one final `evaluate`.
- **Calibration and thresholds belong to a checkpoint.** 0.8B and 4B have different temperatures; re-read both
  `result.json` files after every retrain.

### 9.3 Designing for asymmetric error cost

A missed critical value costs far more than a false alarm, so **do not auto-act on argmax**:

- For `noul` questions use a **low threshold plus mandatory human review**, with the cut-off taken from
  `development.calibrated.selective["0.5"|"0.8"].confidence_cutoff`
- Records with insufficient evidence carry `target: {"false": 0.5, "true": 0.5}` to teach "no evidence, no confidence"
- Exploit the intrinsic property: probabilities only, no generated text ⇒ structurally no hallucinated diagnosis
  and no free-text PHI egress
- **Dual-size routing is risk tiering**: low-risk high-volume to 0.8B, high-risk semantic to 4B, thresholds set
  independently
- Human review is the last gate. Do not target 100% automation.

---

## 10. Acceptance gates

Each gate is a number you can check, not a judgement call.

| Dimension | `result.json` field | Pass condition | Difference between sizes |
| --- | --- | --- | --- |
| Gain is real | `bootstrap.acc.ci95` | **CI excludes 0**. A CI containing 0 means the data is too thin or the gain too small — change the data, not the volume | Judged per size |
| Calibration improved | `development.calibrated.ece`, `confident_errors` | calibrated beats raw, and the fine-tuned model's `confident_error_rate` **must not exceed its baseline** | **Stricter for 0.8B** — it is known to over-confess |
| Honest | `mean_conf` vs `acc` | Within a few points. Far above `acc` means overconfidence — usually too many epochs or near-duplicate training states | 0.8B is the focus |
| No forgetting | `regression` section | ≤ 2 accuracy points on the 300 public `decision-v7` records. More means the delta drifted | Judged per size |
| Business value | `development.calibrated.coverage_at_5pct_error` | Meets the target you set. A critical-value scenario should target far higher coverage at a low error budget than a routine one | — |
| Post hoc | `plan_size.py --from-result` | Already significant / how many more records / the gain is too small to chase | Run per size |
| Temperature | `result.json.temperature` | Fitted on calibration only; gold set evaluated once | **The two sizes differ — never reuse one for the other** |
| Size decision | `compare --a <4b> --b <8b>` | A CI excluding 0 means 4B is genuinely better and worth the extra cost. A CI containing 0 means **choose 0.8B** | — |

**Gold-set final evaluation.** Run `evaluate --remote <url>` (`KEV_REMOTE_API_KEY`) against the held-out human gold
file, **once per size**, and confirm the served numbers match the offline ones. Remote probabilities are taken as
returned (no temperature fit), so this compares "what the service gives you" against "what your calibrated model
gives you".

---

## 11. The optimisation loop

1. `pull --name <run>` to bring back `result.json`, `errors.jsonl`, `train.log`
2. Read the top of `errors.jsonl` — it is sorted by confidence, so the first lines are the model's most confident
   mistakes
3. Turn each recurring class of error into the missing sentence in the spec's `guidance`
4. Programmatic scenarios: change the threshold or rule table. Triage and ICD: change `guidance` and `variety`,
   then generate targeted records
5. Regenerate → resplit → train as `-v2` → `compare --a x-2b-v2 --b x-2b-v1`

Ranked by return, from the upstream skill:

1. **More and better data** — doubling the training set usually beats any hyperparameter
2. `--epochs 2` when you have 1000+ records and epoch 1's loss is still falling at its end
3. Lower `--lr` (halve from 4e-5 on 0.8B or 2e-5 on 4B), keep `--replay 2000`, do not add epochs
4. `--replay 500` when the dataset is large and training time matters
5. Reach for `jaredpalmer/kev-9b` only when two data rounds stop moving the 4B

---

## 12. Go-live and rollback

**Go live in stages:** shadow mode (record only, compare against human conclusions) → human review (low confidence
plus high-risk categories always reviewed) → gradual rollout. In healthcare the default is "model advises, human
confirms". Fully automated disposition is not recommended. With two sizes you can tier: open up 0.8B on low-risk
decisions first while keeping 4B plus a human for high-risk ones.

**Rollback, in increasing order of destructiveness:**

1. Point `KEV_SERVE_RUN` back at `jaredpalmer/kev-0.8b` / `jaredpalmer/kev-4b` and redeploy — model-level, seconds.
   **The two endpoints roll back independently**, isolated by their distinct `KEV_APP_NAME`
2. Turn off the call from a client feature flag — application-level, service untouched
3. `modal app stop kev-<scenario>-8b` / `-4b` — take one endpoint offline
4. `teardown --run <name> --yes` / `--endpoint` / `--everything [--cache] --yes` — remove data.
   **Modal secrets are never deleted by the script**; remove them yourself with `modal secret delete`
5. Always keep both baseline endpoints as a fallback — an idle deployed endpoint costs nothing

---

## 13. Compliance and privacy

- **De-identify before generation.** Names, IDs, phone numbers and admission numbers are hashed or replaced, and
  this happens **before** records reach a generator — the generators only ever see de-identified fields.
- **Keep data in-network if you must.** Point `KEV_GEN_BASE_URL` at a local Ollama
  (`http://localhost:11434/v1`) so distillation never leaves your network; otherwise assess whether de-identified
  structured fields may be sent to an external API.
- **Never publish a medical model.** `publish` is private by default; **do not pass `--public`**. Prefer keeping the
  checkpoint on the Modal volume.
- **Credentials live in Modal secrets** (`KEV_SERVE_SECRET` / `KEV_HF_SECRET`), never in the repository.
- **Data retention:** deltas are small (0.8B roughly 0.1 GB, 4B roughly 0.3 GB by tarball reference); the three
  `teardown` levels are documented in the runbook.
- **Specs and generators contain only schema and rule tables — no patient data.** Real and gold data live in
  `data/`, which is git-ignored.

---

## 14. Verified vs unverified, item by item

The single most important section, restated in full so nobody has to infer it from the rest of the document.

### 14.1 Verified locally

| Check | Command | Result |
| --- | --- | --- |
| Four generators produce data | `gen_*.py --n 787 --seed 0` | 787 records each |
| Upstream validator accepts it | `split_data.py <file>` | 0 invalid lines, 0 conflicting labels (nursing 784 valid after 3 duplicates dropped) |
| Label floors respected | `split_data.py` warnings | no `under 5%`, no `never labelled` |
| Sizing arithmetic | `plan_size.py <spec>` | `generate at least 787 records` for all five specs |
| Minimal pairs | `gen_critical_value.py` output + inspection of emitted JSONL | 89 twins built; 86 record pairs differ in exactly one field, 82 flip a label |
| Dual-size command sequence | `run_matrix.py --dry-run` | correct for 4 scenarios; refuses `icd-coding --sizes 8b,4b`; refuses `27b` |
| Run-name validation | `check_name` | rejects `critical-value-0.8b-v1`; accepts `critical-value-8b-v1`, `triage_4b-v2` |
| Gold sampling | `make_goldset.py sample` | 200 of 787, rare labels represented |
| Disagreement audit | `make_goldset.py audit` | per-question rates; gates on worst question; exit 1 at 12.7% on `is_critical` |
| Tests | `pytest tests/test_medical_generators.py` | 16 passed; 34 with `test_skill_scripts.py` |
| Links and anchors | link check over `medical/` | all resolve |
| Lint | `read_lints` | 0 issues |

### 14.2 Not verified — no real environment

| Item | Why it matters |
| --- | --- |
| **No training run at all** | No `result.json` exists, so this document contains no measured accuracy, Brier, ECE or coverage for any model trained on your data |
| **Baselines unmeasured** | `--baseline-acc 0.75` is a placeholder. Sizing should be re-run after measuring both |
| **Chinese token budget unmeasured** | `validate` was never run. A silent-drop risk remains until it is |
| **No real data** | Everything is synthetic; there is no clinical data in this repo |
| **Gold set unadjudicated** | 200 records are a review pool, not a signed gold set |
| **Distillation path unexecuted** | `generate_data.py` was never run |
| **Deployment unexecuted** | `modal deploy` was never invoked |
| **ICD scenario has no data** | Spec only; no generator, no records |
| **Cheaper-GPU training untested** | L4/A10G cost savings are plausible, unverified |

**A note on the wider test suite.** On the Windows development machine the full unit suite reports 110 failures and
6 collection errors. The cause is `kev/suite.py` importing `fcntl`, which is Unix-only. `git status` confirms `kev/`
and the existing tests are **unmodified** by this work, so these are pre-existing platform failures, not
regressions introduced here. The medical package's own tests are green.

### 14.3 Where the implementation differs from the original plan

| Item | Planned | Actual | Why |
| --- | --- | --- | --- |
| Record count | 627 | **787** | Specs measure at 4 questions/record, not 5 |
| `critical_item` options | 10 | **6** | `N` options at ≥5% each forces a positive rate of `5N%`; 10 options would need 50% critical |
| `quota_labels` helper | provided | **removed** | Quota shape differs per scenario; a shared helper became dead code |
| Balanced-prior warning | absent | **added as §8.5** | The balanced-vs-clinical prior mismatch must be stated before go-live |
| `critical_value.build` return | a record | `(record, handle)` with `pair_twin` separate | Lets "construct for a target label" and "construct a minimal pair" be tested independently |

---

## 15. Go-live checklist

Everything here needs a real environment, a real person, or a real institution. None of it can be done from this
repository.

### 15.1 Accounts and setup

- [ ] Python 3.10+ and [`uv`](https://docs.astral.sh/uv/)
- [ ] A Modal account: `uvx modal setup`
- [ ] Optional, for distillation: an OpenAI-compatible API key; decide whether de-identified structured fields may
      leave your network, or stand up a local Ollama and point `KEV_GEN_BASE_URL` at it
- [ ] Optional: a Hugging Face token **only** if you intend to publish privately

### 15.2 Rule tables — domain review, blocking

- [ ] **Laboratory:** review every threshold, notification tier and critical zone in `gen_critical_value.py`
- [ ] **Pharmacy:** review every drug rule in `gen_medication_review.py`
- [ ] **Nursing:** review every checklist item and severity in `gen_nursing_quality.py`
- [ ] For each change, update **both** the generator's rule table and the spec's `guidance`

### 15.3 Data

- [ ] Adjudicate the 200-record gold pool with a clinician or pharmacist; record who signed it and when
- [ ] Confirm the gold set is **not** used for anything except the single final evaluation
- [ ] Confirm de-identification happened before generation, and that no patient data entered the repository

### 15.4 Measurement

- [ ] Measure both baselines: `evaluate --run jaredpalmer/kev-0.8b` and `--run jaredpalmer/kev-4b`
- [ ] Re-run `plan_size.py` with each measured baseline; adjust the record count if the bounds differ materially
- [ ] Run `validate` for **both** sizes and confirm `over_limit: 0` on every partition
- [ ] Train both sizes; read `bootstrap.acc.ci95` and confirm the CI excludes 0
- [ ] Confirm calibrated beats raw, and that 0.8B's `confident_error_rate` does not exceed its baseline
- [ ] Confirm the public regression is within 2 accuracy points for **each** size
- [ ] Read `development.calibrated.selective` cut-offs for **each** size — they are not interchangeable
- [ ] Run `compare --a <4b> --b <8b>`; if the CI contains 0, choose 0.8B

### 15.5 Go-live

- [ ] Shadow mode first: log predictions, compare against human conclusions, do not act on them
- [ ] Re-derive operating thresholds from **real traffic**, not from the balanced-prior probabilities (§8.5)
- [ ] Confirm the low-threshold-plus-human-review rule for every `noul` question
- [ ] Confirm the two endpoints have distinct `KEV_APP_NAME` values and therefore independent rollback
- [ ] Verify rollback by actually redeploying the baseline once before you need it
- [ ] Confirm `KEV_SERVE_SECRET` is set: without it the endpoint is public and the URL is the only secret
- [ ] Confirm no medical model is ever published with `--public`

---

## 16. File inventory

| Path | Lines / size | Role |
| --- | --- | --- |
| `docs/sft-medical.md` | this file | English master document |
| `docs/sft-medical_CN.md` | parallel | Complete Chinese translation, structure matched section by section |
| `docs/medical/README.md` | 20,330 B | Chinese implementation entry: the full design narrative |
| `docs/medical/data-format.md` | 14,551 B | State schema, label systems, token budget, balanced-prior mismatch |
| `docs/medical/runbook.md` | 10,577 B | 11-step command reference and 14-entry troubleshooting table |
| `docs/medical/specs/critical-value.json` | 4,734 B | Critical-value spec |
| `docs/medical/specs/medication-review.json` | 5,302 B | Medication/insurance review spec |
| `docs/medical/specs/nursing-quality.json` | 5,408 B | Nursing quality spec |
| `docs/medical/specs/triage.json` | 5,085 B | Triage routing spec |
| `docs/medical/specs/icd-coding.json` | 5,842 B | ICD coding spec (4B only) |
| `kev/console/generators/README.md` | 5,276 B | Generator overview and how to add a scenario |
| `kev/console/generators/common.py` | 9,089 B | Shared base, size-independent |
| `kev/console/generators/gen_critical_value.py` | 18,152 B | Critical-value generator |
| `kev/console/generators/gen_medication_review.py` | 11,507 B | Medication review generator |
| `kev/console/generators/gen_nursing_quality.py` | 9,895 B | Nursing quality generator |
| `kev/console/generators/gen_triage.py` | 9,364 B | Triage generator |
| `kev/console/generators/make_goldset.py` | 7,619 B | Gold sampling and disagreement audit |
| `kev/console/generators/run_matrix.py` | 7,461 B | Dual-size orchestrator |
| `tests/test_medical_generators.py` | 16 tests | Generator, spec and orchestrator tests |
| `.github/workflows/ci.yml` | one line | Added to the CI unit job |

**Nothing under `skills/kev-finetune/` was modified.** That directory has a `skills-lock.json` packaging boundary
and `tests/test_skill_scripts.py` depends on its structure. The medical side adapts entirely through specs and
external generators.

---

[简体中文](./sft-medical_CN.md) · Implementation: [`medical/`](./medical/README.md) · Upstream skill:
[`skills/kev-finetune`](../skills/kev-finetune/SKILL.md)
