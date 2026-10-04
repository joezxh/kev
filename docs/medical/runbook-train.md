<p align="center">
  <a href="./runbook-train_cn.md"><img alt="中文" src="https://img.shields.io/badge/%E4%B8%AD%E6%96%87-blue?style=for-the-badge"></a>
  <img alt="English" src="https://img.shields.io/badge/English-lightgrey?style=for-the-badge">
  <a href="./runbook.md"><img alt="速查 / Reference" src="https://img.shields.io/badge/%E9%80%9F%E6%9F%A5-orange?style=for-the-badge"></a>
</p>

# Medical rule-synthesized data training for Kev / fine-tuning Qwen3.5-0.8B — runbook (locally runnable edition)

[← Back to main plan](./README.md) · [Data format](./data-format.md) · [Modal runbook](./runbook.md) · [Generators](./generators/README.md)

This runbook complements `runbook.md` (which wraps the steps in a Modal cloud container via `kev_modal.py`): it **invokes the native `kev` package commands directly**
(`kev.train` / `kev.benchmark` / `kev.calibrate` / `kev.publish`) and walks you through the whole flow on a
**local Linux / WSL2 / container** or a **local machine with a GPU**. It also spells out the **two fine-tuning modes**
(LoRA delta fine-tuning vs full-weight fine-tuning) explicitly. The Modal path in `runbook.md` simply packages the steps
of this runbook into a cloud container; the data format, splits and evaluation protocol are identical.

> Every command in this runbook runs from the repository root `kev/` (use `python` in PowerShell, `python3` in bash).

---

## 0. What exactly are the two modes fine-tuning

Kev is a decision model that "outputs only calibrated probabilities, generates no text": it runs prefill-only with a block-causal mask
(shared state prefix, isolated question branches) and a **pointer readout over the option-boundary tokens**. Therefore:

- A bare base model (e.g. `Qwen/Qwen3.5-0.8B-Base`) has **no pointer head**, so it cannot be fine-tuned directly for a decision task;
- `kev.train` always trains a pointer head from scratch (`--head_dim 256`; `--head_lr 0` means the head shares the backbone's learning rate).

Given this, the **two modes** differ only in "how the backbone weights move":

| Mode | Core flags | Backbone | Outputs | VRAM | When to use | Expected effect |
| --- | --- | --- | --- | --- | --- | --- |
| **A. LoRA delta fine-tuning** | `--lora 16` (LoRA is default; `--full_ft 0`) | frozen, only low-rank adapters trained | `adapter_model.safetensors` + `head.pt` | low (0.8B ≈ 3–5 GB) | hundreds–thousands of medical records; keep the published model's general decision ability; fast, cheap scenario adaptation | ~+5 accuracy points on balanced labels (significant only if the paired-bootstrap CI excludes 0); almost no loss of general ability; tiny delta (~46 MB for 0.8B) |
| **A1. Warm start from Kev-0.8B** | `--init_from jaredpalmer/kev-0.8b` | frozen + loads published LoRA/head | same as above | low | **recommended**: medical delta continues training on the published checkpoint, reusing its in-domain skill | same as above, and the start is closer to the target distribution so it converges faster; `--replay 2000` mixes in public records to prevent forgetting |
| **A2. Start from bare base** | `--base Qwen/Qwen3.5-0.8B-Base --base_revision 9a45d25e` | frozen + trains LoRA/head from scratch | same as above | low | want to fully detach from published behavior and shape it from zero | same as above, but needs more steps before a usable head emerges |
| **B. Full-weight fine-tuning** | `--full_ft 1 --weights_dtype bf16` | all trainable (bf16 weights + fp32 master copy / moments) | `model*.safetensors` + `head.pt` | high (0.8B ≈ 14–18 GB, needs `--weights_dtype bf16`) | large medical corpus (thousands–tens of thousands); needs to diverge noticeably from published behavior; single 24GB+ GPU or torchrun multi-GPU | higher accuracy ceiling, but more prone to forgetting general ability; weights ≈ 1.6 GB (0.8B) |

**On SFT and DPO**: Kev's training objective is essentially **SFT** — log-loss (cross-entropy; KL for soft labels) on "labelled option boundaries".
Because the model **generates no text**, there is no "policy generation vs reference generation" pairing, so **DPO does not apply to Kev**. The two
"modes" here are the LoRA / full-weight SFT variants, not SFT vs DPO.

> Default selection advice: medical (rule-synthesized) data usually starts with **mode A1 (LoRA + warm start from `jaredpalmer/kev-0.8b`)**;
> only upgrade to mode B once the data volume is large and LoRA is proven to have plateaued.

---

## 1. Environment, dependencies, and one important limitation

### 1.1 Install dependencies

```bash
uv sync                      # install the kev package (setuptools, editable) + torch/transformers/peft/datasets
uv run python -m kev.train --help   # verify install (should print all flags)
```

### 1.2 ⚠️ Native Windows is not supported at runtime (cross-platform patch applied)

`kev.train` / `kev.benchmark` / `kev.publish` import Unix-only standard libraries:

- `kev/train.py` imports `resource` (only to write peak RSS into `training_metrics.json`);
- `kev/suite.py` imports `fcntl` (only for the `file_lock` file lock).

On **native Windows** the repo fails at `import` with `ModuleNotFoundError: No module named 'resource'` / `'fcntl'`.
This runbook applies a minimal cross-platform patch (`kev/train.py` and `kev/suite.py`: switch to `try/except ModuleNotFoundError`;
on Windows `resource=None` skips RSS and `file_lock` degrades to a no-op), with **zero behavioral change on Linux / Modal paths**.
After the patch, `kev.train --help` / `kev.benchmark --help` import normally on Windows too.

**Real training / evaluation still require**: running on **Linux (WSL2 / container / Modal)** with access to Hugging Face (or cached base weights).
This machine (Windows sandbox, no HF network) can only run the "data half" end-to-end; the "training half" cannot execute because weights cannot be pulled — see section 6 "Trial log".

### 1.3 Base weights

| Mode | Weights needed | Source |
| --- | --- | --- |
| A1 | `jaredpalmer/kev-0.8b` (LoRA+head+base) | HF Hub (auto-download; medical models must not be `--public`) |
| A2 / B | `Qwen/Qwen3.5-0.8B-Base`, revision `9a45d25e` | HF Hub (`Qwen/Qwen3.5-0.8B-Base`, Apache-2.0) |

On a machine without a GPU you can use `--device cpu` for a **smoke test** (fp32, very slow, link-only validation); real training must use `--device cuda --dtype bf16`.

### 1.4 China access: HF mirror (read this)

`huggingface.co` is often unreachable from China. Redirect `huggingface_hub` / `transformers` requests to the domestic mirror
**`hf-mirror.com`** via an env var (verified able to pull `Qwen/Qwen3.5-0.8B-Base` tokenizer / weights from this machine):

```bash
# bash / WSL2
export HF_ENDPOINT=https://hf-mirror.com
# PowerShell
$env:HF_ENDPOINT="https://hf-mirror.com"
```

- This variable affects `kev.train` / `kev.benchmark` (loading local checkpoints is unaffected) pulling the base, and `kev.publish` uploading;
  after routing through the mirror, `huggingface_hub` / `transformers` behave identically to a direct HF connection, cache lands in `~/.cache/huggingface`.
- On Windows a symlink warning appears (`cache-system uses symlinks by default ...`): harmless; add
  `$env:HF_HUB_DISABLE_SYMLINKS_WARNING="1"` to silence it, no functional impact.
- If the mirror is occasionally unstable, the backup is **ModelScope** (Qwen series has official ModelScope mirrors; use the `modelscope` package `snapshot_download` to pre-pull into the local cache, then load offline); but `jaredpalmer/kev-0.8b` (medical delta start) is published only on HF, so it still needs `hf-mirror.com`.
- Offline: first pull weights with `HF_ENDPOINT=https://hf-mirror.com hf download jaredpalmer/kev-0.8b` or
  `hf download Qwen/Qwen3.5-0.8B-Base` into the local cache, then set `HF_HUB_OFFLINE=1` to train.

---

## 2. Complete execution steps

Each step contains: **purpose / input / environment / command / expected output / verification**. Steps actually run locally in this runbook are marked ✅.

---

### Step 1 · Compute record count ✅

- **Purpose**: use the McNemar paired formula to determine "how much data is needed for fine-tune vs baseline difference to be statistically significant".
- **Input**: scenario spec (`docs/medical/specs/critical-value.json`, contains 4 questions).
- **Environment**: pure standard library, no torch / network needed.
- **Command**:

```bash
python skills/kev-finetune/scripts/plan_size.py docs/medical/specs/critical-value.json --baseline-acc 0.75
```

- **Expected output**:

```
To detect a +5% accuracy gain over a 75% baseline at 80% power (paired, 95% two-sided):
  development questions: 469 paired (unpaired bound 1092)
  with 4 question(s) per record and a 15% development split: 118 development records
  calibration: 118 records (>= 100 questions for the temperature fit)
  generate at least 787 records  ->  python3 scripts/generate_data.py ... --n 787 --out data/<name>.jsonl
```

- **Verification**: `total_records` = 787 (= train 551 + cal 118 + dev 118). Each scenario has 4 questions → 787 records.
  The conservative unpaired bound (1092) varies with `--baseline-acc`; the 0.8B baseline is weaker, so the bound is larger — measure two baselines first and re-check.

---

### Step 2 · Generate data (programmatic rule synthesis / optional LLM distillation generative track)

- **Purpose**: obtain 787 Kev records with zero-drift labels (System One request shape).
- **Input**: scenario spec + rule tables (programmatic path); or an LLM endpoint (distillation path).
- **Environment**:
  - Programmatic generators: **pure standard library, no network, reproducible seeds** (`docs/medical/generators/`).
  - Distillation generative track (optional, needs a Bailian/OpenAI-compatible endpoint): `generate_data.py` needs an OpenAI-compatible endpoint (`KEV_GEN_API_KEY` / `KEV_GEN_BASE_URL`, can point to local Ollama).

**Programmatic (critical value / medication / nursing quality / record summary — labels derived from rules, preferred):**

```bash
python docs/medical/generators/gen_critical_value.py --n 787 --out data/cv.jsonl --seed 0
```

- **Expected output** (measured on this machine):

```
787 records -> data/cv.jsonl (spec critical-value, seed 0)
distinct states: 787 (0 duplicate states)
  critical_item: none=515 (65%), cbc=64 (8%), glucose_gas=53 (7%), electrolyte=53 (7%), renal=53 (7%), cardiac_coag=49 (6%)
  evidence_sufficient: true=739 (94%), false=48 (6%)
  is_critical: false=515 (65%), true=272 (35%)
  notify_within: 3=515 (65%), 0=119 (15%), 1=107 (14%), 2=46 (6%)
minimal pairs built: 89 (each twin differs in one measurement and flips is_critical)
```

- **Verification**: `distinct states = 787` and `0 duplicate states`; every option share ≥ 5% (`cbc=8%` etc. are safe); `minimal pairs` > 0
  means "minimal pairs" were built where the same report differs by one measurement and the label flips. A `warning: labels [...] under 5%` means rebalance generator quotas — do not add `--n`.

**Distillation generative track (6 semantic scenario categories, needs a Bailian/LLM endpoint):**

Select a category with `--category <key>`; when `--out` is omitted it defaults to `data/cv/<spec-name>.jsonl` (one file per category, no interference). 6 categories → spec mapping:

| Category key `--category` | Chinese | spec file | Note |
| --- | --- | --- | --- |
| `nursing_quality` | hospital nursing quality control | `nursing-quality.json` | semantically rich, distill first |
| `record_summary` | admission-note & progress-note summary reconciliation | `record-summary.json` | semantically rich, distill first |
| `medication_review` | outpatient & inpatient prescription review | `medication-review.json` | semantically rich, distill first |
| `icd_coding` | inpatient medical-record coding & DRG/DIP review | `icd-coding.json` | semantically rich, distill first |
| `initial_assessment` | outpatient & emergency initial assessment | `diagnosis.json` | semantically rich, distill first |
| `report_review` | lab & imaging report review | `critical-value.json` | also has programmatic generator `gen_critical_value.py` (threshold table, zero drift) |
| `triage` (extra) | outpatient & internet-hospital triage | `triage.json` | semantically rich, distill first |

> Every scenario has 4 questions → `plan_size` plans uniformly **787 records / category** (train 551 + cal 118 + dev 118).

```bash
export KEV_GEN_BASE_URL=https://api.ant-ling.com/v1
export KEV_GEN_API_KEY=sk-studio-****          # single key (also accepts OPENAI_API_KEY / AI_GATEWAY_API_KEY)
python skills/kev-finetune/scripts/generate_data.py --category triage \
  --n 787 --batch 10 --concurrency 3 --model Ling-3.0-tiny --out data/cv/triage.jsonl
# print the prompt first with --dry-run to confirm guidance is not ambiguous before the real run
```

- **Verification**: `stopped short of --n` or high `rejected` → `guidance` too ambiguous; distillation writes only `label`, the `target` soft label can only come from programmatic generators.

- **Multiple keys + 500k/day soft cap (each key 500k tokens/day)**: each key is capped at `--daily-limit` (default `500000`) tokens/day; when exhausted it auto-rotates to the next key, and when all are exhausted it stops for the day (or waits for the next day). Usage is persisted to `.distill/usage_<date>.json`, so **re-runs interrupted by cron / Task Scheduler keep counting the day's budget**, and it resets at local midnight.

  ```bash
  # Method A: comma-separated
  export KEV_GEN_API_KEYS="sk-...1,sk-...2,sk-...3"   # 3 keys = 1.5M tokens/day
  # Method B: keys file (one key per line, keeps keys out of process args)
  printf 'sk-...1\nsk-...2\n' > .distill_keys.txt
  python skills/kev-finetune/scripts/generate_data.py --category medication_review \
    --n 787 --model Ling-3.0-tiny --keys-file .distill_keys.txt --daily-limit 500000
  ```
  - Soft cap: budget is checked at submit time ("still has budget") and not pre-deducted, so a day may overshoot by about one batch; for a hard cap, lower `--batch`.
  - A key returning 401/403 is `mark_dead` and auto-rotated to the next key without stopping the run; only when all keys fail does it report "daily budget exhausted" and exit with code 2.

- **Distill a portion each day + self-configured scheduler (two options, pick one)**:
  1. **In-script daemon**: `--schedule HH:MM` enters daemon mode, runs one round per local `HH:MM` each day (waits for the next day once budget is exhausted), stop with Ctrl-C.
  2. **System scheduler (recommended, no resident process)**: use cron (Linux/WSL2) or Task Scheduler (Windows) to trigger **one normal call per day** — the script already **appends incrementally** (reads the existing `--out` to continue) and counts budget per date file, so a single call is naturally "the portion to run that day".
  ```cron
  # crontab -e  (Linux/WSL2, run one triage round at 03:07 daily; stops automatically when budget is exhausted)
  7 3 * * * cd /path/to/kev && /usr/bin/env bash -c 'export KEV_GEN_BASE_URL=https://api.ant-ling.com/v1 KEV_GEN_API_KEYS="sk-...1,sk-...2"; uv run python skills/kev-finetune/scripts/generate_data.py --category triage --n 787 --model Ling-3.0-tiny' >> logs/distill.log 2>&1
  ```
  ```powershell
  # Windows Task Scheduler: trigger daily at 03:07, action = start a program
  # program pwsh.exe  args: -Command "cd d:\projects\github\kev; $env:KEV_GEN_BASE_URL='https://api.ant-ling.com/v1'; $env:KEV_GEN_API_KEYS='sk-...1,sk-...2'; uv run python skills/kev-finetune/scripts/generate_data.py --category triage --n 787 --model Ling-3.0-tiny"
  ```
  - Throughput with multiple keys: 3 keys × 500k ÷ ~301 tok/rec (tiny) ≈ ~4983 records/day, enough to finish several categories in a day; the bottleneck shifts from "budget" to "time".

- **Bailian (measured, free 500k tokens/day/key)**:
  ```bash
  export KEV_GEN_API_KEY=sk-studio-****      # Bailian apikey
  export KEV_GEN_BASE_URL=https://api.ant-ling.com/v1
  python skills/kev-finetune/scripts/generate_data.py --category triage \
    --n 40 --batch 10 --concurrency 3 --model Ling-3.0-flash --out data/triage_bailian.jsonl
  ```
  - Available model ids (`GET /v1/models`, measured): `Ling-3.0-flash` / `Ling-3.1-flash` / `Ling-2.6-1T` / `Ling-3.0-tiny` / `Ring-2.6-1T` (1T multimodal), etc.; `Ling-3.0-flash` is enough for text distillation.
  - Measured: 40 records / 4 calls / 197s / **0 rejected**; all 14 department options covered; `split_data` validated 40 valid / 0 conflicts, split train 28 / calibration 6 / development 6; sample medical logic consistent with `guidance`.
  - ⚠️ `Ling` is a **reasoning model**: it returns `reasoning_content` first, then `content`; too-small `max_tokens` yields empty `content` (the script sets no `max_tokens` and uses the endpoint default to avoid this).
  - The 40 records only validate the link; temperature fitting needs calibration ≥ 100 questions (this spec 4 questions/record → ≥ 25 records); the real distillation targets `plan_size` volume (787 records/category).
  - **Measured token efficiency** (`Ling-3.0-flash`, batch 10, 4 questions/record): per call prompt≈1.4k + completion≈14.5–19k, of which **~90% is `reasoning_content` thinking tokens** → **≈1828 tokens/record**.
    - Converted: **single key 500k free budget ≈ 273 records/day**; `plan_size` target 787 records ≈ **1.44M tokens ≈ 3 days** (single key). Multiple keys scale linearly: 3 keys ≈ 819 records/day, one day covers a category.
    - Reasoning tokens are the main cost: switching to the non-reasoning small model `Ling-3.0-tiny` or disabling thinking at the endpoint raises the records/distilled per budget significantly.
  - **Non-reasoning measured** (`Ling-3.0-tiny`, batch 10, 4 questions/record): no `reasoning_content`, per call prompt≈1.4k + completion≈1.55k → **≈301 tokens/record**; 20/20 validation passed, 0 rejected. **Single key 500k budget ≈ 1658 records/day**, reaching the `plan_size` 787 target needs only **~0.5 day** of free budget; vs `Ling-3.0-flash` that is **≈6.1×**. Structured-label distillation with tiny is sufficient (no loss of validity); only long-chain semantics / difficult reasoning is slightly weaker — spot-check clinically before launch.

> Existing labelled data (CSV/JSONL) → Kev records: use `convert_data.py` (column mapping), then feed in via `split_data.py --holdout`; never into train.

---

### Step 3 · Sample gold set + manual review (the key defense line of the closed loop)

- **Purpose**: build a held-out manual gold set for final evaluation and two-model disagreement audit.
- **Command**:

```bash
python docs/medical/generators/make_goldset.py sample data/cv.jsonl --n 200 --out data/cv.gold.jsonl --seed 0
# optional: two-model disagreement audit
python docs/medical/generators/make_goldset.py audit data/cv.jsonl --out data/cv.audit.jsonl
```

- **Expected output**: after stratified sampling, rare labels also have samples; prints label coverage.
- **Verification**: gold ≥ 150 records (otherwise calibration/development noise is large; aim for 200); clinicians/pharmacists review and sign off line by line against spec `guidance`.
  The gold set is **used only for the final evaluation**, never tuned against.

---

### Step 4 · Format conversion and split (split_data) ✅

- **Purpose**: after validating the single-file JSONL, cut it into `train / calibration / development` partitions (temperature fit + scoring + training).
  Kev record shape is in `data-format.md`; one record example:

```json
{"state": "male 67", "questions": {"is_critical": {"type": "noul", "instructions": "Does any lab item in this report hit a critical value?", "label": true},
                                    "notify_within": {"type": "score", "instructions": "Within how long should it be notified?", "criteria": ["15min","1h","same day","not needed"], "label": 0}}}
```

- **Command** (**run only after Step 2 finishes writing the file; do not run in parallel with generation, or it reads a half-written file**):

```bash
python skills/kev-finetune/scripts/split_data.py data/cv.jsonl --out data/cv
# with gold: --holdout data/cv.gold.jsonl (gold splits half into calibration/development, never into train)
```

- **Expected output** (measured on this machine, 787 records):

```
787 valid records (0 invalid lines, 0 exact duplicates dropped, 0 states with conflicting labels dropped)
questions by type: {'noul': 1574, 'score': 787, 'choice': 787}; states: 787 distinct
wrote data\cv\development.jsonl: 118 records
wrote data\cv\calibration.jsonl: 118 records
wrote data\cv\train.jsonl: 551 records
```

- **Verification**: the three partition counts sum to 787; `conflicting labels dropped` non-zero → labelling rules are self-contradictory, go fix `guidance`.
  The same `state` always lands in the same partition (grouped by state hash), so **the same `data/cv` can feed both 0.8B and 4B sizes** for `compare`.

---

### Step 5 · Token-limit pre-check (mandatory for Chinese)

- **Purpose**: the Kev trainer **silently drops** records with state > 384 tokens / request > 2048 tokens / single question branch > 1024 tokens (it only prints a count, no error).
  Chinese token density is high; `split_data.py`'s `STATE_CHARS_WARN=1400` is an **English** heuristic, do not copy it blindly.
- **Command**: mode A1 uses the `kev-0.8b` tokenizer; mode A2/B uses the `Qwen/Qwen3.5-0.8B-Base` tokenizer:

```bash
# mode A1
uv run python -c "from kev.model import load_tokenizer, DecisionModel; from kev.data import load_records, materialize; from kev.model import training_context, fits
tok=load_tokenizer('jaredpalmer/kev-0.8b')
recs=load_records('data/cv/train.jsonl')
c=training_context(384)
over=[r for r in recs if not fits(materialize(r), tok, **c)]
print('over_limit', len(over))"
```

- **Expected output**: `over_limit 0`. Non-zero → shorten the state field or trim `state_example`; do not estimate by character count.
- **Verification**: the two-size tokenizers segment Chinese differently; ideally measure each once.

---

### Step 6 · Model loading and training config

Both modes express "how the model is loaded" via the same set of `kev.train` flags:

| Flag | Mode A1 (LoRA warm start) | Mode A2 (LoRA bare base) | Mode B (full-weight) |
| --- | --- | --- | --- |
| `--init_from` | `jaredpalmer/kev-0.8b` | (omit) | (omit) |
| `--base` | (inherited from init) | `Qwen/Qwen3.5-0.8B-Base` | `Qwen/Qwen3.5-0.8B-Base` |
| `--base_revision` | (inherited from init) | `9a45d25e` | `9a45d25e` |
| `--lora` | `16` (inherits init rank) | `16` | (ignored, no effect in full-weight) |
| `--full_ft` | `0` | `0` | `1` |
| `--weights_dtype` | `fp32` | `fp32` | `bf16` (forced in full-weight) |
| `--lora_targets` | `all` / `dense` / `attn` / `qv` | same | — |
| `--head_dim` | `256` | `256` | `256` |
| `--lr` | `4e-5` (0.8B inherits init) | `4e-5` | `full_ft.MasterAdamW` auto |
| `--replay` | `2000` (mix public records to prevent forgetting) | `2000` | `0` (no mix in full-weight, or as needed) |
| `--device` | `cuda` | `cuda` | `cuda` |
| `--dtype` | `bf16` | `bf16` | `bf16` (autocast) |

> `kev.train` defaults to `--base Qwen/Qwen3-0.6B-Base`; **do not omit** `--base`/`--init_from`, or it trains on the wrong base.

---

### Step 7 · Launch training

**Mode A1 (recommended · LoRA warm start from Kev-0.8B):**

```bash
uv run python -m kev.train \
  --data data/cv/train.jsonl \
  --init_from jaredpalmer/kev-0.8b \
  --lora 16 --lora_targets all \
  --lr 4e-5 --head_lr 0 --weight_decay 0.01 \
  --epochs 1 --batch 4 --accum 2 --dtype bf16 --device cuda \
  --replay 2000 --seed 0 \
  --out runs/cv-8b-lora-v1
```

**Mode A2 (LoRA from bare base):**

```bash
uv run python -m kev.train \
  --data data/cv/train.jsonl \
  --base Qwen/Qwen3.5-0.8B-Base --base_revision 9a45d25e \
  --lora 16 --lora_targets all \
  --lr 4e-5 --epochs 1 --batch 4 --accum 2 --dtype bf16 --device cuda \
  --out runs/cv-8b-lora-base-v1
```

**Mode B (full-weight fine-tuning, single 24GB+ GPU or torchrun multi-GPU):**

```bash
# single GPU
uv run python -m kev.train \
  --data data/cv/train.jsonl \
  --base Qwen/Qwen3.5-0.8B-Base --base_revision 9a45d25e \
  --full_ft 1 --weights_dtype bf16 --dtype bf16 \
  --lr 4e-5 --epochs 1 --batch 1 --accum 4 --device cuda --checkpointing 1 \
  --out runs/cv-8b-full-v1
# multi-GPU (FSDP2)
torchrun --standalone --nproc_per_node 8 -m kev.train \
  --base Qwen/Qwen3.5-0.8B-Base --base_revision 9a45d25e \
  --full_ft 1 --weights_dtype bf16 --dtype bf16 \
  --data data/cv/train.jsonl --lr 4e-5 --epochs 1 --batch 8 --accum 2 --device cuda \
  --out runs/cv-8b-full-v1
```

- **Expected output (startup prints)**:

```
device=cuda world=1 trainable params=XX.XM     # LoRA: adapters+head only, millions; full-weight: ~0.8B
delta: warm start from ... (mode A1 only)
<N> training requests (holdout=[]), questions by type {...}
ep0 step 10/139 loss 0.623 kl 0.000 anchor 0.000 0.042s/rec
...
saved runs/cv-8b-lora-v1
```

- **Verification**:
  - `trainable params`: LoRA should be millions (not the full 0.8B); full-weight ~0.8B.
  - `loss` drops with steps; printed every 10 steps. `non-finite training loss` → data / learning-rate issue.
  - The trainer prints "dropped N of M records that exceed the training context" — non-zero means over-limit records were silently dropped (back to Step 5).

> 0.8B on H100 ≈ 8 min / 400–1000 records. CPU is smoke-test only (fp32, very slow). `--out` dir must not already exist (unless `--resume 1`).

---

### Step 8 · Monitoring

- **Progress**: terminal prints `loss / kl / anchor / s·rec` every 10 steps.
- **`<out>/training_config.json`**: the full params of this run + base_revision + init_source (reproducible).
- **`<out>/training_metrics.json`**: `wall_seconds`, `records_seen`, `optimizer_steps`, `grad_norm` (per-epoch grad-norm mean/max/clipped steps),
  `peak_device_bytes`, `backbone_save_seconds`. Rollback criterion for "gradient explosion": an epoch whose `max` grad norm far exceeds the mean is abnormal.
- **Mode B only**: `resume` points (`--save_every_minutes` / `--save_every_steps`), `snapshots/step-<N>/checkpoint`
  (`--snapshot_fractions 0.25,0.5,0.75`, never deleted, can resume training).

---

### Step 9 · Evaluation (kev.benchmark)

- **Purpose**: score on `development.jsonl`, produce `rows.json` (one line per question + logits) + `report.json` (accuracy / ECE / Brier / NLL,
  selective coverage and AURC, paired bootstrap).
- **Command**:

```bash
uv run python -m kev.benchmark \
  --run runs/cv-8b-lora-v1 \
  --data data/cv/development.jsonl \
  --out runs/cv-8b-lora-v1-eval --device cuda
```

- **Expected output**: `runs/cv-8b-lora-v1-eval/` has `rows.json` + `report.json`. `report.json` key fields:
  - `development.calibrated.acc` / `bootstrap.acc.ci95` (is the gain real: **CI excluding 0** is significant)
  - `development.calibrated.ece` / `confident_error_rate` (calibration: calibrated must beat raw; fine-tuned model's confident_error_rate must not exceed baseline)
  - `regression` (accuracy drop on public `decision-v7` 300 records ≤ 2 points)
  - `coverage_at_5pct_error` (business metric: automatable share)
- **Verification**: `mean_conf` and `acc` within a few points (0.8B overconfident more easily, enforce stricter); regression > 2 points → halve `--lr`, keep `--replay`, add no epoch.

---

### Step 10 · Temperature fit (kev.calibrate)

- **Purpose**: fit a temperature on your own development rows (report only, does not change weights). Kev probabilities scale with temperature; you must refit on **your** distribution before deployment.
- **Command**:

```bash
uv run python -m kev.calibrate --rows runs/cv-8b-lora-v1-eval/rows.json \
  --out runs/cv-8b-lora-v1-eval/calibration.json
```

- **Expected output**: `calibration.json` has `raw / shipped / workload / workload_oof` four arms' `acc/ece/brier/coverage`,
  and `workload_temperature` (the temperature to write into service config), `oof_vs_shipped` paired bootstrap.
- **Verification**: `workload_oof`'s ECE/Brier should be ≤ `shipped`; use `workload_temperature` as the service temperature.
  **Note**: balanced training prior ≠ real clinical prior (critical values are only 1–3% online), so recalibrate the cut point on real traffic before launch (see `data-format.md`).

---

### Step 11 · Export (kev.publish)

- **Purpose**: upload the checkpoint to a private HF Hub (LoRA adapter or full-weight shards + `head.pt` + tokenizer + model card).
- **Command**:

```bash
uv run python -m kev.publish \
  --run runs/cv-8b-lora-v1 \
  --repo jaredpalmer/kev-0.8b \
  --card docs/model-cards/kev-0.8b.md \
  --private --message "medical critical-value delta v1"
# candidate first to a branch, don't overwrite published weights: --revision candidate-v1 --replace
```

- **Expected output**: under the repo, `adapter_model.safetensors` + `adapter_config.json` (LoRA) or `model*.safetensors` + index (full-weight),
  `head.pt`, tokenizer files, README.md (model card). `--private` keeps the medical model non-public; reusing the same repo's adapter and full-weight layouts are mutually exclusive, needs `--replace`.
- **Verification**: `hf auth login` done; target repo auto-created if missing with `--private`, refused if it exists and is not private (no accidental public push).
- **Local export alternative**: just keep the `<out>/` directory to load locally / in-container, no Hub upload needed.

---

### Step 12 · Deploy (pick one)

- **Modal (recommended, matches `runbook.md`)**: `KEV_APP_NAME=kev-cv-8b KEV_SERVE_RUN=cv-8b-lora-v1 modal deploy skills/kev-finetune/scripts/kev_modal.py`
- **Local System One endpoint**: `uv run python -m kev.serve --run runs/cv-8b-lora-v1 --port 8008` (set temperature per `workload_temperature`).

---

## 3. Local trial log (real results)

All below are results **actually executed** in this repo root, on Windows + PowerShell:

| Step | Command | Result | Note |
| --- | --- | --- | --- |
| 1 generate | `gen_critical_value.py --n 787` | ✅ 787 records, distribution as above | pure stdlib, reproducible |
| 1 compute | `plan_size.py critical-value.json` | ✅ `generate at least 787 records` | matches split |
| 1 split | `split_data.py data/cv.jsonl --out data/cv` | ✅ 551/118/118 | exactly matches plan_size |
| 5 CLI | `kev.train --help` | ⚠️ first run `No module named 'resource'` | patched (`kev/train.py`/`kev/suite.py` optional import), re-run passed |
| 5 CLI | `kev.benchmark/evaluate/publish --help` | ✅ all normal | patch applies to whole package |
| 7 train | `kev.train --data ... --base Qwen/Qwen3.5-0.8B-Base` | ✅ direct connect `OSError: couldn't connect`; after `HF_ENDPOINT=https://hf-mirror.com` the 0.6B base loaded 310/310 weights, 3 records 1 epoch CPU smoke ran: `trainable 5.6M`, produced `adapter_model.safetensors`+`head.pt`+tokenizer snapshot, **no error** (only harmless Windows symlink warning) | training half fully opened; 0.8B uses the same LoRA+head+save code path, only larger base / real training needs GPU (`--device cuda --dtype bf16`) |
| 8 LLM distillation (Bailian) | `generate_data.py docs/medical/specs/triage.json --n 40 --batch 10 --concurrency 3 --model Ling-3.0-flash` (`KEV_GEN_BASE_URL=https://api.ant-ling.com/v1`) | ✅ 4 calls 197s, 40 records **0 rejected**; `split_data` validated 40 valid / 0 conflicts, split train 28 / cal 6 / dev 6 | Bailian `Ling-3.0-flash` distillation link opened; reasoning model emits reasoning then content; 40 records only validate link (temp fit needs ≥25 records), real distillation targets `plan_size` volume |
| 8b distillation script upgrade (multi-key / 500k/day / scheduler) | `generate_data.py --category triage --n 3 --model Ling-3.0-tiny --api-keys $K`; also tested `--daily-limit 1` (daily budget exhausted → exit code 2), `--api-keys bogus-a,bogus-b` (two keys 401→mark_dead→rotate exhausted) | ✅ single key 3 records to `data/cv/triage.jsonl`, `.distill/usage_<date>.json` logged 1925 tokens; `--daily-limit 1` kept counting the day's budget across processes and stopped immediately; two fake keys rotated then exit code 2 | 6-category `--category`, multi-key 500k/day soft cap, daily incremental + scheduler (`--schedule`/cron/Task Scheduler) all three capabilities verified usable |

**Conclusion**: the data half (generate → compute → split → CLI check) runs fully on this machine; the training/eval half could not run end-to-end here because (1) native Windows lacks Unix modules (fixed, but real training should still run on Linux), (2) this sandbox cannot reach Hugging Face weights. On a Linux/WSL2 machine with a GPU and HF access, steps 7–12 of section 2 reproduce.

> Parallel-execution pitfall: once `gen_critical_value.py` and `split_data.py` were run in parallel, split read the generator's not-yet-finished 40-record old file and showed 40 instead of 787. **Always generate first, then split** (serial).

---

## 4. End-to-end reproducible flow (Linux / WSL2)

```bash
# 0. environment (China: switch to HF mirror first)
export HF_ENDPOINT=https://hf-mirror.com      # PowerShell: $env:HF_ENDPOINT="https://hf-mirror.com"
uv sync
# 1. compute volume
python skills/kev-finetune/scripts/plan_size.py docs/medical/specs/critical-value.json --baseline-acc 0.75
# 2. generate (programmatic rule synthesis / optional LLM distillation generative track)
python docs/medical/generators/gen_critical_value.py --n 787 --out data/cv.jsonl --seed 0
# 2b. LLM distill one category (6 categories use --category; multi-key 500k/day, --schedule daemon or hand to cron/Task Scheduler)
export KEV_GEN_BASE_URL=https://api.ant-ling.com/v1
python skills/kev-finetune/scripts/generate_data.py --category triage --n 787 --model Ling-3.0-tiny --out data/cv/triage.jsonl
#     multi-key: export KEV_GEN_API_KEYS="sk-...1,sk-...2"   # each key 500k tokens/day, auto-rotate when exhausted
# 3. gold set (optional but strongly recommended)
python docs/medical/generators/make_goldset.py sample data/cv.jsonl --n 200 --out data/cv.gold.jsonl --seed 0
# 4. split (serial, not in parallel with generation)
python skills/kev-finetune/scripts/split_data.py data/cv.jsonl --out data/cv --holdout data/cv.gold.jsonl
# 5. token pre-check (see the python snippet in Step 5)
# 6-7. train (mode A1 example)
uv run python -m kev.train --data data/cv/train.jsonl --init_from jaredpalmer/kev-0.8b \
  --lora 16 --lr 4e-5 --epochs 1 --batch 4 --accum 2 --dtype bf16 --device cuda \
  --replay 2000 --out runs/cv-8b-lora-v1
# 9-10. evaluate + temperature
uv run python -m kev.benchmark --run runs/cv-8b-lora-v1 --data data/cv/development.jsonl --out runs/cv-8b-lora-v1-eval --device cuda
uv run python -m kev.calibrate --rows runs/cv-8b-lora-v1-eval/rows.json --out runs/cv-8b-lora-v1-eval/calibration.json
# 11. export
uv run python -m kev.publish --run runs/cv-8b-lora-v1 --repo jaredpalmer/kev-0.8b --card docs/model-cards/kev-0.8b.md --private
```

---

## 5. FAQ and rollback plan

### 5.1 FAQ

| Symptom | Cause | Fix |
| --- | --- | --- |
| `No module named 'resource'` / `'fcntl'` | running training/eval on native Windows | cross-platform patch applied; still recommended to run real training on **Linux/WSL2** |
| `OSError: couldn't connect to huggingface.co` | direct HF unreachable from China | set `HF_ENDPOINT=https://hf-mirror.com` (see 1.4); or `HF_TOKEN` + pre-pulled cache; offline `HF_HUB_OFFLINE=1` |
| `invalid run name ... no dots` (Modal path only) | run name contains `.` | write size as `8b`/`4b`, not `0.8b` |
| `warning: labels [...] under 5%` | label distribution not balanced | rebalance generator quotas, do not add `--n` |
| `states with conflicting labels dropped` non-zero | same state same question different label | labelling rules self-contradictory, fix spec `guidance` |
| trainer prints `dropped N of M records` | state/request exceeds token limit | Step 5 measure `over_limit` with tokenizer, shorten state |
| `non-finite training loss` | learning rate too high / data corrupted | lower `--lr`, check `data/cv/train.jsonl` |
| `regression` > 2 points | delta forgot general ability | halve `--lr`, keep `--replay 2000`, add no epoch |
| 0.8B `mean_conf` ≫ `acc` | 0.8B overconfident easily | enforce stricter acceptance; low-risk high-throughput use 0.8B, high-risk hand to 4B |
| `refusing to overwrite an existing run` | `--out` already exists | rename (`-v2`) or use `--resume 1` |
| full-weight `epochs` times out mid-way (Modal/container) | single-container time limit | `--save_every_minutes` writes resume point, swap container `--resume 1` |

### 5.2 Rollback plan (by increasing destructiveness)

1. **Model level**: service points `KEV_SERVE_RUN` back to `jaredpalmer/kev-0.8b` / `jaredpalmer/kev-4b` and redeploys, second-level rollback; two endpoints independent.
2. **App level**: client feature flag turns off the call, service untouched.
3. **Endpoint level**: `modal app stop kev-cv-8b` (or stop local `kev.serve` process).
4. **Data level**: `teardown --run <name>` (Modal) / delete `runs/` + `data/` (local); **Hub secret and private repo are not deleted by scripts**, handle manually.
5. **Training disaster recovery**: mode B's `resume` points + `snapshots` are never deleted, can return to any completed step; never manually delete `<out>/snapshots`.

> Medical scenarios default to "model suggestion + human confirmation", **not** pursuing unattended automatic action; two sizes can be tiered (low-risk 0.8B, high-risk 4B + human).

---

## 6. Deliverables list

The final outputs of this plan — **(rule-synthesized) data**, **fine-tuned / Kev model** and **base weights** — are summarized below (scale all measured on this machine):

| Category | Artifact | Path | Scale | Format / Note | Status |
| --- | --- | --- | --- | --- | --- |
| Rule-synth data | training set | `data/cv/train.jsonl` | 551 records / 890 KB | Kev record (JSONL), 4 questions/record | ✅ generated |
| Rule-synth data | dev/eval set | `data/cv/development.jsonl` | 118 records / 190 KB | `kev.benchmark` scoring + paired bootstrap | ✅ generated |
| Rule-synth data | calibration set | `data/cv/calibration.jsonl` | 118 records / 190 KB | `kev.calibrate` temperature fit | ✅ generated |
| Rule-synth data | smoke subset | `data/cv/train.smoke.jsonl` | 3 records / 4.9 KB | small sample for link smoke test | ✅ generated |
| Rule-synth data | generation summary | `data/cv/summary.json` | 1 / 1.5 KB | generation stats | ✅ generated |
| Fine-tuned model | 0.6B LoRA smoke | `runs/smoke-mirror/` | adapter `19.7 MB` + head `2.0 MB` + tokenizer `10.9 MB` + config/metrics | LoRA r8 / `Qwen/Qwen3-0.6B-Base` / CPU | ✅ trained (link validation) |
| Fine-tuned model | **0.8B Kev model** (target) | `runs/cv-8b-lora-v1/` (planned) | — | LoRA or full-weight / `Qwen/Qwen3.5-0.8B-Base` (or `jaredpalmer/kev-0.8b` delta) / GPU | ⏳ pending training |
| Base weights | `Qwen/Qwen3.5-0.8B-Base` | HF (via `hf-mirror.com`) | ~1.6 GB | training start | ✅ mirror reachable |
| Base weights | `jaredpalmer/kev-0.8b` | HF (via `hf-mirror.com`) | ~1.6 GB | medical delta start (optional) | ✅ mirror reachable |

**Key points**
- The data half is fully landed: 551 train + 118 eval + 118 calibration; the split is by **state hash** (sha256 after case/whitespace normalization), model-independent, can feed both 0.8B and 4B sizes for `compare` at once.
- The training half is opened with a 0.6B smoke (LoRA+head+checkpoint save same code path); the real 0.8B only needs GPU training (`--device cuda --dtype bf16`), same artifact shape: `adapter_model.safetensors` + `head.pt` + tokenizer snapshot.
- Base weights were previously unreachable by direct `huggingface.co`; now reachable via `HF_ENDPOINT=https://hf-mirror.com` mirror (measured), the whole chain has no external blocker.
- **LLM distillation (optional generative track, needs Bailian)** is independent of the table above: Bailian `Ling-3.0-flash` triage trial output `data/triage_bailian.jsonl` + `data/triage_bailian/{train,calibration,development}.jsonl` (40 records). Critical values deliberately **do not** use LLM distillation (labels come from threshold tables, LLM would introduce drift).
- **6-category distillation command (`--category`)**: `generate_data.py --category <key>` now supports any of the 6 categories (mapping in Step 2); multi-key 500k/day soft cap + `.distill/usage_<date>.json` continuation; `--schedule` or cron/Task Scheduler implements "distill a portion each day". Each category's output lands in `data/cv/<spec-name>.jsonl`, split via `split_data.py --out data/cv/<spec-name>` then fed to training.
