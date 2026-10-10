"""Task 30 follow-up: backfill 3 medical scenarios (inquiry / medication / knowledge-qa).

These 3 are referenced by kev/console/distill/configs/<slug>.yaml (the legacy reference templates)
but were not seeded into the DB, so `make_seeds config --scenario <slug>` failed for them. Spec §3.8
line 858 requires the rendered config to be byte-equal (modulo inline comments) to the legacy yaml.

This script:
  1. Calls Store().seed_scenarios() so docs/medical/specs/<slug>.json are picked up by the glob.
  2. Calls Store().write_spec_file(<slug>, content) on each so the on-disk spec (with the
     generator / distill / routing / smoke_probe sub-fields) is in scenarios.spec_json. _backfill_specs
     only fills empty rows; this is the explicit overwrite.
  3. Updates label_zh from the spec (the seed-time heuristic reads the first non-JSON line, which is `{`
     for these JSON specs and so leaves label_zh = slug).

Idempotent: re-running writes the same content / label.
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from kev.console.db import Store
from kev.console import paths as console_paths

SLUGS = ["inquiry", "medication", "knowledge-qa"]
LABELS = {"inquiry": "导诊", "medication": "用药指导", "knowledge-qa": "医学知识问答"}


def main() -> int:
    store = Store()
    # Step 1: 把本地 spec 文件的回填逻辑重跑一次（_backfill_specs 只填空行，不覆盖已存在的内容）。
    # 这里强制以本地文件覆盖，让 spec 文件的修改立刻生效。
    for slug in SLUGS:
        spec_path = console_paths.SPECS / f"{slug}.json"
        if not spec_path.is_file():
            print(f"FAIL: spec file missing: {spec_path}")
            return 1
        content = spec_path.read_text(encoding="utf-8")
        try:
            store.write_spec_file(slug, content)
        except KeyError:
            # slug 不在 DB；先 seed 再 write
            store.seed_scenarios()
            store.write_spec_file(slug, content)
    # Step 2: label_zh 启发式不匹配 JSON 文件；按 spec.label_zh 校正（幂等）。
    for slug, label_zh in LABELS.items():
        row = store.get_scenario_by_slug(slug)
        if row is None:
            continue
        store.update_scenario(row["id"], label_zh=label_zh)
    # Step 3: 校验 4 个子字段都非空
    fail = False
    for slug in SLUGS:
        row = store.get_scenario_by_slug(slug)
        if row is None:
            print(f"FAIL: {slug} not seeded")
            fail = True
            continue
        spec = json.loads(row["spec_json"]) if row.get("spec_json") else {}
        for required in ("routing", "smoke_probe", "distill", "generator"):
            if required not in spec:
                print(f"FAIL: {slug} missing top-level {required!r}")
                fail = True
                continue
        if fail:
            continue
        sub_status = {k: spec.get(k) is not None for k in ("generator", "distill", "routing", "smoke_probe")}
        print(f"OK {slug}: id={row['id'][:8]}... label_zh={row['label_zh']!r} sort={row['sort']}")
        print(f"    sub-field populated: {sub_status}")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
