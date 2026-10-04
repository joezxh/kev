<p align="center">
  <a href="./distill_CN.md"><img alt="中文" src="https://img.shields.io/badge/%E4%B8%AD%E6%96%87-orange?style=for-the-badge"></a>
  <a href="./distill.md"><img alt="English" src="https://img.shields.io/badge/English-blue?style=for-the-badge"></a>
</p>

# Distillation layer manual

[← Implementation entry](./README.md) · [Distill layer overview](./distill/README.md) · [Plan document](../sft-distill.md)

Every command with its expected output, how to read it, and what to do on failure. Design and rationale live in
the [plan document](../sft-distill.md).

```bash
D=docs/medical/distill
```

---

## Step 0 · One-time setup

```powershell
$env:KEV_GEN_API_KEY = "..."                                # Bailin API key
$env:KEV_GEN_BASE_URL = "https://<official base URL>/v1"    # per developer.ant-ling.com
```

**Expected**: no output.
**Read**: the base URL and model id **must** come from the official docs. A 2026-02 third-party blog gives
`api.tbox.cn/api/llm/v1`, which was not cross-checked; the model family turns over every 1–2 months (latest:
Ling-3.0-flash), so do not hardcode it.
**On failure**: if the egress assessment fails, self-host the open-sourced `Ling-3.0-flash` behind vLLM and point
the base URL at `localhost`.

---

## Step 1 · Generate seeds (zero tokens)

```bash
python3 $D/make_seeds.py --all --n 500 --out-dir data/seeds
```

**Expected**: five lines, each printing seed and state counts, then a `next: easydistill --config ...` hint.

**Read**:
- The seeds and states files must have **equal row counts** per scenario (the script asserts it)
- `knowledge-qa` reporting "Kev 轨: 无 / no Kev track" is **correct** — Kev only scores pre-declared options and
  cannot answer open questions
- A seed's `instruction` states facts only and **carries no label clue**

**On failure**:
- `planned targets could not be realized` → rerun with a different `--seed`; if it happens at scale, check the rule
  table against the quota
- `no spec at ...` → the scenario's spec is missing from `docs/medical/specs/`

---

## Step 2 · Distil (the only step that spends tokens)

```bash
easydistill --config $D/configs/inquiry.yaml
```

**Expected**: five stages land in order, ending in `data/sft/inquiry/inquiry.sft.jsonl`.

**Read — check the row count after every stage**, especially `filter`:

| Stage | Expected rows | If off |
| --- | --- | --- |
| `expanded` | seeds × `num_per_seed` (3) | low means the expansion stage rejected output |
| `generated` | ≈ expanded | low means 429 or generation failures; rerun (`resume: true` continues) |
| `judged` | ≈ generated | — |
| `filtered` | **50–80% of judged** | **below 30% means the judge threshold disagrees with the spec** — loosen `pass_score` |
| `*.sft.jsonl` | = filtered | — |

**On failure**:
- `429` → lower `backend.concurrency` (currently 2) and back off
- `401/403` → the key is invalid or not bound to an account
- `404` → the model id does not exist; **re-confirm it on the official models page**

⚠️ **Run scenarios serially, not concurrently** — a low cloud concurrency ceiling only turns parallel scenarios
into 429s.

---

## Step 3 · Convert to Kev records (zero tokens)

```bash
python3 $D/seed_to_kev.py --scenario inquiry \
  --seed-file data/seeds/inquiry.seed.jsonl \
  --state-file data/seeds/inquiry.state.jsonl \
  --out data/inquiry.jsonl
```

**Expected**:

```text
500 records -> data/inquiry.jsonl (spec triage, seed 0)
distinct states: 500 (0 duplicate states)
  department: emergency=65 (13%), cardiology=39 (8%), ...
```

**Read**: the distribution should closely match a direct `gen_triage.py` run — the label source is identical, so
only the seed sampling differs.
**On failure**:
- `N seed ids have no state row` → the two files are out of sync; rerun Step 1
- `labels [...] are not questions of spec` → scenario and spec name are mismatched

---

## Step 4 · Reconcile the teacher against the rules (reporting only)

```bash
python3 $D/seed_to_kev.py --scenario inquiry --from-sft data/sft/inquiry/inquiry.sft.jsonl \
  --report data/inquiry.reconcile.json
```

**Expected**: `teacher/rule agreement: N/M = NN%`, plus the most-disagreed `(question, rule label)` pairs.

**Read**: this is the **boundary agreement rate between teacher and rule engine**, not model accuracy.
- High (>80%) → teacher and rules see the same decision boundary
- Low → those records go to human adjudication first

**On failure**: if the SFT file carries no `id` column the per-record reconciliation is skipped with a note — keep
the seed `id` on the EasyDistill side, otherwise disagreements cannot be located.

---

## Step 5 · Volume and budget gate

```bash
python3 $D/check_volume.py --scenario inquiry --records data/inquiry.jsonl --expect 500 \
  --from-sft data/sft/inquiry/inquiry.sft.jsonl --budget 8000000
```

**Expected**: distribution detail, the token ledger, then `OK: 分布与预算断言全部通过`.

```text
== token 账
  Kev 轨: 0 LLM token（标签与 state 均来自规则引擎，不经 LLM）
  inquiry.sft.jsonl: 617,000 tokens over 500 rows (1,234/row, usage seen on 500 rows)
```

**Read — `1,234/row` is the most valuable number in this manual**: it replaces the plan document's "~1,000 tokens
per record" *estimate* with a **measurement**. Use it to re-budget Tier B/C before talking to anyone about paid quota.
**On failure**: on exit 1, work the `FAILED` list. A wrong `--expect` is a seed-count problem, a `<5%` or
`never labelled` is a rule-table or quota problem, and a token overrun is a volume problem.

---

## Troubleshooting

| Symptom | Cause | Action |
| --- | --- | --- |
| `429` | cloud concurrency / rate ceiling | lower `backend.concurrency` (2 now), back off, rerun; `resume: true` continues |
| `404` on the model | model id does not exist | the family turns over every 1–2 months; re-confirm on the official models page |
| `401/403` | key invalid or account not bound | re-issue; confirm the account completed identity verification |
| `filtered` collapses | judge threshold disagrees with the spec | loosen `pass_score`; do **not** rerun hoping for luck |
| `filtered` empty | threshold too strict, or output shape wrong | inspect one record with a dry run, then adjust |
| reconciliation skipped, "no id" | SFT file lacks `id` | keep the seed `id` on the EasyDistill side |
| agreement rate very low | teacher and rules disagree on the boundary | **do not** change labels; send those records to human review and check `guidance` |
| `N seed ids have no state row` | dual files out of sync | rerun `make_seeds.py`; the two must be same order and length |
| `labels [...] under 5%` | label distribution unbalanced | adjust the generator's share parameter, **not** the volume |
| `never labelled` | an option is never correct | check the rule table / quota so every option can be selected |
| `data/seeds/...` looks trackable | `.gitignore` not in effect | this repo now carries `data/`; verify with `git check-ignore` |
| adults carrying pediatric keywords | `gen_triage.py` vocabulary defect (measured 6.8%) | **must be fixed before distilling**; see plan §13; needs separate authorization |
