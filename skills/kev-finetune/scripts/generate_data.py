#!/usr/bin/env python3
"""Generate labelled Kev training records for a workload with any OpenAI-compatible chat model.

    export KEV_GEN_API_KEY=...                       # or OPENAI_API_KEY / AI_GATEWAY_API_KEY
    python3 scripts/generate_data.py workload.json --n 600 --out data/support.jsonl --model gpt-4.1-mini
    python3 scripts/generate_data.py workload.json --dry-run          # print one batch prompt and exit

The workload spec describes the state text and the exact System One questions the deployed model will be asked
(see assets/workload.example.json). Every batch asks the LLM for records whose labels fill the least-represented
options first, so the output is balanced per question. Records are validated (split_data.check_question), deduplicated
by state, and appended to --out as they arrive, so an interrupted run resumes where it stopped.

Endpoints: KEV_GEN_BASE_URL (default https://api.openai.com/v1). Vercel AI Gateway: https://ai-gateway.vercel.sh/v1 with
model ids like openai/gpt-4.1-mini or anthropic/claude-sonnet-4.5. Ollama: http://localhost:11434/v1. Standard library only.

Extensions for the medical pipeline:
  * --category <key>  select one of the 6 workload categories (maps to docs/medical/specs/<name>.json).
  * --api-keys / --keys-file / KEV_GEN_API_KEYS  use several keys; each key is capped at --daily-limit tokens/day
    (default 500000); the run rotates to the next key with budget and pauses (or, in --schedule mode, waits for
    the next day) when every key is exhausted.
  * --schedule HH:MM  daemon mode: distill a daily portion, then sleep until the next local HH:MM (budget resets at
    local midnight). Re-run via cron / Windows Task Scheduler for hands-off daily distillation.
"""
import argparse
import datetime
import json
import math
import os
import random
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from split_data import check_question, label_key, normalized_state  # noqa: E402

DEFAULT_BASE_URL = "https://api.openai.com/v1"
REPO_ROOT = Path(__file__).resolve().parents[3]  # .../skills/kev-finetune/scripts -> repo root
SYSTEM = ("You write labelled training examples for a small decision model. Every example is a realistic state text plus the "
          "correct answer to each question. Reply with a single JSON object and nothing else.")

# 6 大类（中文名 → spec 文件名）。triage 为「门诊/互联网医院导诊分诊」并行 spec（可选）。
CATEGORY_SPECS = {
    "nursing_quality": "nursing-quality.json",     # 医院护理质量管控
    "record_summary": "record-summary.json",       # 住院病历的现病史与病程记录摘要核对
    "medication_review": "medication-review.json", # 门诊与住院处方审核
    "icd_coding": "icd-coding.json",               # 住院病案编码与 DRG/DIP 审核
    "initial_assessment": "diagnosis.json",        # 门诊与急诊的初诊评估
    "report_review": "critical-value.json",        # 医院检验科与影像科报告复核
    "triage": "triage.json",                       # 导诊分诊（额外）
}


class AuthError(Exception):
    """Raised when an API key is rejected (401/403); the caller rotates to the next key."""


class KeyPool:
    """A set of API keys, each capped at `daily_limit` tokens for the local calendar day.

    Per-key usage is persisted to <state_dir>/usage_YYYY-MM-DD.json so a process that is stopped and restarted
    (e.g. by cron) keeps its daily budget; a new file is used at local midnight, which resets the budget.
    """

    def __init__(self, keys, daily_limit, state_dir):
        self.keys = list(dict.fromkeys(keys))  # dedupe, keep order
        self.daily_limit = daily_limit
        self.dead = set()
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.usage_path = self.state_dir / f"usage_{datetime.date.today().isoformat()}.json"
        self.usage = self._load()

    def _load(self):
        if self.usage_path.exists():
            try:
                return json.loads(self.usage_path.read_text(encoding="utf-8"))
            except Exception:
                return {}
        return {}

    def _save(self):
        self.usage_path.write_text(json.dumps(self.usage, ensure_ascii=False, indent=2), encoding="utf-8")

    def remaining(self, key):
        if self.daily_limit <= 0:
            return float("inf")
        return self.daily_limit - self.usage.get(key, 0)

    def pick(self):
        if not self.keys:
            return None
        candidates = [k for k in self.keys if k not in self.dead and self.remaining(k) > 0]
        if not candidates:
            return None
        return min(candidates, key=lambda k: self.usage.get(k, 0))  # least-used first, balances the pool

    def record(self, key, tokens):
        if key is None or tokens <= 0:
            return
        self.usage[key] = self.usage.get(key, 0) + tokens
        self._save()

    def mark_dead(self, key):
        self.dead.add(key)


def option_keys(q):
    if q["type"] == "noul": return ["true", "false"]
    if q["type"] == "choice": return list(q["criteria"])
    return [str(i) for i in range(len(q["criteria"]))]


def describe_question(qid, q):
    if q["type"] == "noul":
        crit = q.get("criteria") or {}
        detail = "".join(f' ({k} = {v})' for k, v in crit.items() if v)
        return f'- {qid} (noul): "{q["instructions"]}"{detail} Label: true or false.'
    if q["type"] == "choice":
        opts = "; ".join(f"{k}" + (f" = {v}" if v not in (None, "") else "") for k, v in q["criteria"].items())
        return f'- {qid} (choice): "{q["instructions"]}" Options: {opts}. Label: the option name exactly as written.'
    levels = "; ".join(f"{i} = {lvl}" for i, lvl in enumerate(q["criteria"]))
    return f'- {qid} (score): "{q["instructions"]}" Levels: {levels}. Label: the level index (an integer).'


def batch_targets(counts, keys, done, batch):
    """How many records of this batch should carry each label so the file ends up balanced: fill the deficit against an
    even split of (done + batch) first, then spread the rest evenly."""
    goal = math.ceil((done + batch) / len(keys))
    deficit = {k: max(0, goal - counts.get(k, 0)) for k in keys}
    total = sum(deficit.values())
    if total == 0: deficit = {k: 1 for k in keys}; total = len(keys)
    raw = {k: batch * v / total for k, v in deficit.items()}
    alloc = {k: int(v) for k, v in raw.items()}
    for k in sorted(keys, key=lambda k: raw[k] - alloc[k], reverse=True)[: batch - sum(alloc.values())]: alloc[k] += 1
    return {k: v for k, v in alloc.items() if v}


def build_prompt(spec, counts, done, batch, examples, rng):
    lines = [f"Domain: {spec['domain']}", f"State: {spec['state']}"]
    if spec.get("state_example") is not None:
        lines.append("State shape (produce states of exactly this shape): " + json.dumps(spec["state_example"], ensure_ascii=False))
    lines.append("Questions the model will be asked about each state. Give the correct label for every one:")
    lines += [describe_question(qid, q) for qid, q in spec["questions"].items()]
    if spec.get("guidance"): lines.append(f"Labelling rules: {spec['guidance']}")
    variety = list(spec.get("variety", []))
    if variety:
        rng.shuffle(variety)
        lines.append("Vary the examples along these axes (cover several per batch): " + "; ".join(variety))
    lines.append(f"Label targets for this batch of {batch} records, per question:")
    for qid, q in spec["questions"].items():
        alloc = batch_targets(counts[qid], option_keys(q), done, batch)
        lines.append(f"- {qid}: " + ", ".join(f"{v} x {k}" for k, v in alloc.items()))
    if examples:
        lines.append("Reference examples in the target style (write new ones, do not copy):")
        for ex in examples: lines.append(json.dumps({"state": ex["state"], "labels": {qid: q["label"] for qid, q in ex["questions"].items()}}, ensure_ascii=False))
    lines.append(f"Make every state different from the others (different people, wording, details, and difficulty; include some hard or ambiguous-looking "
                 f"cases whose label still follows the rules). Random seed for variety: {rng.randrange(10**6)}.")
    lines.append('Return {"records": [{"state": <state>, "labels": {<question id>: <label>, ...}}, ...]} with exactly ' + f"{batch} records.")
    return "\n".join(lines)


def chat(base_url, api_key, model, prompt, json_mode=True, timeout=180, retries=5):
    body = {"model": model, "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}], "temperature": 1.0}
    if json_mode: body["response_format"] = {"type": "json_object"}
    req = urllib.request.Request(f"{base_url.rstrip('/')}/chat/completions", data=json.dumps(body).encode(), method="POST",
                                 headers={"content-type": "application/json", "authorization": f"Bearer {api_key}"})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read())
                return data["choices"][0]["message"]["content"], data.get("usage", {})
        except urllib.error.HTTPError as error:
            detail = error.read().decode(errors="replace")[:300]
            if error.code == 400 and json_mode and "response_format" in detail:
                return chat(base_url, api_key, model, prompt, json_mode=False, timeout=timeout, retries=retries)
            if error.code in (401, 403): raise AuthError(f"authentication failed at {base_url}: {detail}")
            if error.code == 404: raise SystemExit(f"model or endpoint not found ({model} at {base_url}): {detail}")
            if error.code not in (408, 409, 429) and error.code < 500: raise SystemExit(f"HTTP {error.code}: {detail}")
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            if attempt == retries - 1: raise SystemExit(f"cannot reach {base_url}: {error}")
        time.sleep(min(2 ** attempt, 30))
    raise SystemExit("the endpoint kept failing; try again later or lower --concurrency")


def parse_records(text):
    text = text.strip()
    if text.startswith("```"): text = text.split("\n", 1)[1].rsplit("```", 1)[0]
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end < 0: return []
        try: data = json.loads(text[start:end + 1])
        except json.JSONDecodeError: return []
    records = data.get("records") if isinstance(data, dict) else data
    return records if isinstance(records, list) else []


def coerce_label(q, value):
    if q["type"] == "noul":
        if isinstance(value, bool): return value
        if isinstance(value, str) and value.lower() in ("true", "false"): return value.lower() == "true"
        return value
    if q["type"] == "score":
        if isinstance(value, str) and value.strip().lstrip("-").isdigit(): return int(value)
        if isinstance(value, float) and value.is_integer(): return int(value)
        return value
    if isinstance(value, str) and value not in q["criteria"]:
        matches = [k for k in q["criteria"] if k.casefold() == value.strip().casefold()]
        return matches[0] if len(matches) == 1 else value
    return value


def to_record(spec, item):
    """A generated {"state", "labels"} item -> a labelled request, or None with the reason when it is invalid."""
    if not isinstance(item, dict) or "state" not in item or not isinstance(item.get("labels"), dict): return None, "missing state or labels"
    if item["state"] in (None, ""): return None, "empty state"
    questions = {}
    for qid, q in spec["questions"].items():
        if qid not in item["labels"]: return None, f"no label for {qid}"
        labelled = {k: v for k, v in q.items() if k in ("type", "instructions", "criteria")}
        labelled["label"] = coerce_label(q, item["labels"][qid])
        problems = check_question(qid, labelled)
        if problems: return None, problems[0]
        questions[qid] = labelled
    return {"state": item["state"], "questions": questions}, None


def load_spec(path):
    spec = json.loads(Path(path).read_text(encoding="utf-8"))
    for field in ("domain", "state", "questions"):
        if not spec.get(field): raise SystemExit(f"{path}: the spec needs a non-empty {field!r} field (see assets/workload.example.json)")
    for qid, q in spec["questions"].items():
        probe = {**q, "label": {"noul": True, "choice": next(iter(q.get("criteria") or {}), None), "score": 0}.get(q.get("type"))}
        problems = check_question(qid, probe)
        if problems: raise SystemExit(f"{path}: {problems[0]}")
    return spec


def existing_records(path):
    if not Path(path).exists(): return []
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def resolve_spec(arg):
    """arg may be a category key, a spec filename (with/without .json), or a path."""
    if arg in CATEGORY_SPECS:
        return str(REPO_ROOT / "docs" / "medical" / "specs" / CATEGORY_SPECS[arg])
    cand = Path(arg)
    if cand.exists():
        return str(cand)
    if not cand.is_absolute():
        name = arg if arg.endswith(".json") else arg + ".json"
        p = REPO_ROOT / "docs" / "medical" / "specs" / name
        if p.exists():
            return str(p)
    raise SystemExit(f"cannot resolve spec from {arg!r}; use a category key {list(CATEGORY_SPECS)} or a spec path")


def collect_keys(a):
    keys = []
    if a.api_keys:
        keys += [k.strip() for k in a.api_keys.split(",") if k.strip()]
    if a.keys_file:
        keys += [k.strip() for k in Path(a.keys_file).read_text(encoding="utf-8").splitlines() if k.strip()]
    if not keys:
        single = os.environ.get("KEV_GEN_API_KEY") or os.environ.get("OPENAI_API_KEY") or os.environ.get("AI_GATEWAY_API_KEY")
        if single:
            keys = [single]
    if not keys:
        raise SystemExit("no API key: set KEV_GEN_API_KEY / KEV_GEN_API_KEYS, or pass --api-keys / --keys-file")
    return keys


def sleep_until(hhmm):
    h, m = (int(x) for x in hhmm.split(":"))
    now = datetime.datetime.now()
    target = now.replace(hour=h, minute=m, second=0, microsecond=0)
    if target <= now:
        target += datetime.timedelta(days=1)
    secs = (target - now).total_seconds()
    print(f"[scheduler] next run at {target:%Y-%m-%d %H:%M}; sleeping {secs / 3600:.1f}h", flush=True)
    time.sleep(secs)


def run_daily(a, spec, rng, examples, keys):
    """Distill toward --n for today. Returns True if the target --n was reached (for this spec)."""
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    have = existing_records(a.out)
    seen = set()
    counts = {qid: Counter() for qid in spec["questions"]}
    for r in have:
        seen.add(normalized_state(r["state"]))
        for qid, q in r["questions"].items():
            if qid in counts:
                counts[qid][label_key(q)] += 1
    if len(have) >= a.n:
        print(f"{len(have)} records already in {out} (>= --n {a.n}); nothing to do", flush=True)
        return True
    print(f"{len(have)} records already in {out}; distilling toward {a.n} with {a.model} at {a.base_url}", flush=True)
    rejected, calls, started = Counter(), 0, time.time()
    with out.open("a", encoding="utf-8", newline="\n") as f, ThreadPoolExecutor(a.concurrency) as ex:
        while len(have) < a.n and calls < 3 * math.ceil(a.n / a.batch) + a.concurrency:
            if keys.pick() is None:
                print(f"[budget] all {len(keys.keys)} key(s) hit daily limit ({keys.daily_limit} tok/key); stopping for today", flush=True)
                break
            wanted = min(a.concurrency, math.ceil((a.n - len(have)) / a.batch))
            futures = {}
            for _ in range(wanted):
                k = keys.pick()
                if k is None:
                    break
                prompt = build_prompt(spec, counts, len(have), a.batch, rng.sample(examples, min(a.n_examples, len(examples))), random.Random(rng.random()))
                futures[ex.submit(chat, a.base_url, k, a.model, prompt)] = k
                calls += 1
            if not futures:
                break
            for future in as_completed(list(futures)):
                k = futures[future]
                try:
                    content, usage = future.result()
                except AuthError as e:
                    keys.mark_dead(k)
                    print(f"[auth] {e}; rotating to next key", flush=True)
                    continue
                tokens = int(usage.get("total_tokens", 0) or 0)
                keys.record(k, tokens)
                added = 0
                for item in parse_records(content):
                    record, why = to_record(spec, item)
                    if record is None:
                        rejected[why] += 1
                        continue
                    norm = normalized_state(record["state"])
                    if norm in seen:
                        rejected["duplicate state"] += 1
                        continue
                    if len(have) >= a.n:
                        break
                    seen.add(norm)
                    have.append(record)
                    added += 1
                    for qid, q in record["questions"].items():
                        counts[qid][label_key(q)] += 1
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")
                f.flush()
                print(f"  +{added} -> {len(have)}/{a.n} ({time.time() - started:.0f}s) [key {k[:8]}… used {keys.usage.get(k, 0)} tok]", flush=True)
    print(f"{len(have)} records in {out} after {calls} calls; rejected: {dict(rejected) or 'none'}", flush=True)
    for qid, c in counts.items():
        print(f"  {qid}: " + ", ".join(f"{k}={v}" for k, v in c.most_common()), flush=True)
    if len(have) < a.n:
        print(f"stopped short of {a.n}: model kept returning invalid/duplicate records or daily budget exhausted; "
              f"resume later (budget resets next day) or check the spec's guidance", file=sys.stderr)
        return False
    print(f"next: python3 scripts/split_data.py {out} --out {out.with_suffix('')}")
    return True


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0], formatter_class=argparse.RawDescriptionHelpFormatter,
                                 epilog="Environment: KEV_GEN_API_KEY (or OPENAI_API_KEY / AI_GATEWAY_API_KEY), KEV_GEN_BASE_URL, KEV_GEN_MODEL.")
    ap.add_argument("spec", nargs="?", help="workload spec JSON path; omit when using --category")
    ap.add_argument("--category", help="one of the 6 categories: " + ", ".join(CATEGORY_SPECS))
    ap.add_argument("--n", type=int, default=787, help="total records wanted in --out (existing valid records count); default 787")
    ap.add_argument("--out", help="JSONL to append to (default data/cv/<spec-name>.jsonl)")
    ap.add_argument("--model", default=os.environ.get("KEV_GEN_MODEL", "gpt-4.1-mini"), help="chat model id at the endpoint; default gpt-4.1-mini")
    ap.add_argument("--base-url", default=os.environ.get("KEV_GEN_BASE_URL", DEFAULT_BASE_URL))
    ap.add_argument("--batch", type=int, default=20, help="records requested per call; default 20")
    ap.add_argument("--concurrency", type=int, default=4, help="parallel calls; default 4")
    ap.add_argument("--examples", help="JSONL of real labelled records to show as style references (up to --n-examples per batch)")
    ap.add_argument("--n-examples", type=int, default=4)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--dry-run", action="store_true", help="print one batch prompt (use it yourself or in another tool) and exit")
    ap.add_argument("--api-keys", help="comma-separated API keys; each key is capped at --daily-limit tokens/day")
    ap.add_argument("--keys-file", help="file with one API key per line; each key capped at --daily-limit tokens/day")
    ap.add_argument("--daily-limit", type=int, default=500000, help="per-key daily token cap (soft); 0 disables the cap")
    ap.add_argument("--state-dir", default=".distill", help="directory for the per-day token-usage state; default .distill")
    ap.add_argument("--schedule", help="scheduler mode: run a daily portion, then sleep until local HH:MM (e.g. 03:00)")
    a = ap.parse_args()
    if a.category and a.spec:
        ap.error("give either --category or a positional spec path, not both")
    spec_arg = a.category or a.spec
    if not spec_arg:
        ap.error("provide --category <key> or a spec JSON path")
    spec_path = resolve_spec(spec_arg)
    spec = load_spec(spec_path)
    if not a.out:
        a.out = f"data/cv/{Path(spec_path).stem}.jsonl"
    if a.dry_run:
        rng = random.Random(a.seed)
        examples = [json.loads(l) for l in Path(a.examples).read_text(encoding="utf-8").splitlines() if l.strip()] if a.examples else []
        print(build_prompt(spec, {qid: Counter() for qid in spec["questions"]}, 0, a.batch, rng.sample(examples, min(a.n_examples, len(examples))), rng))
        return 0
    if not a.schedule and a.base_url == DEFAULT_BASE_URL and os.environ.get("AI_GATEWAY_API_KEY") and not os.environ.get("KEV_GEN_API_KEY") and not os.environ.get("OPENAI_API_KEY"):
        a.base_url = "https://ai-gateway.vercel.sh/v1"
    rng = random.Random(a.seed)
    examples = [json.loads(l) for l in Path(a.examples).read_text(encoding="utf-8").splitlines() if l.strip()] if a.examples else []
    keys = collect_keys(a)
    if len(keys) > 1:
        print(f"{len(keys)} API keys; per-key daily limit {a.daily_limit} tokens (state in {a.state_dir}/usage_<date>.json)", flush=True)
    keypool = KeyPool(keys, a.daily_limit, a.state_dir)
    while True:
        reached = run_daily(a, spec, rng, examples, keypool)
        if reached:
            print("target reached; done", flush=True)
            return 0
        if not a.schedule:
            print("daily budget exhausted for every key; rerun tomorrow, add keys, or raise --daily-limit", file=sys.stderr)
            return 2
        sleep_until(a.schedule)


if __name__ == "__main__":
    sys.exit(main())
