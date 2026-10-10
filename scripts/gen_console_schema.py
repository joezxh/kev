#!/usr/bin/env python3
"""生成 kev console 的两套初始化 SQL（sqlite / postgresql）。

单一数据源：从这里产出 ``deploy/console/schema.sqlite.sql`` 与
``deploy/console/schema.postgres.sql``，含完整建表 DDL + 初始数据
（scenario_domains、scenarios 含 spec 内容、console_meta 版本）。

与 ``kev/console/db.py`` 的 ``_ddl`` 保持结构一致：改了 db.py 的表结构应重跑本脚本
（``uv run python scripts/gen_console_schema.py``）重新生成，避免两份 DDL 漂移。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from kev.console.db import _ddl  # noqa: E402

SPECS = ROOT / "docs/medical/specs"
SEED_TS = "2026-01-01T00:00:00+00:00"
SCENARIOS = (
    "critical-value", "diagnosis", "icd-coding", "medication-review",
    "nursing-quality", "record-summary", "triage",
)
LABELS = {
    "critical-value": ("危急值", "Critical Value"),
    "diagnosis": ("诊断", "Diagnosis"),
    "icd-coding": ("ICD 编码", "ICD Coding"),
    "medication-review": ("用药审查", "Medication Review"),
    "nursing-quality": ("护理质量", "Nursing Quality"),
    "record-summary": ("病历摘要", "Record Summary"),
    "triage": ("分诊", "Triage"),
}


def _sql_str(value: str) -> str:
    """SQL 单引号字符串字面量：内部单引号翻倍（JSON 用双引号，内部单引号仅见于文本值）。"""
    return "'" + value.replace("'", "''") + "'"


def _seed_insert(backend: str, table: str, columns: list[str],
                 values: list[str], conflict_cols: str) -> str:
    """冲突则忽略的 seed INSERT：sqlite 用前缀 INSERT OR IGNORE，postgres 用后缀
    ON CONFLICT ... DO NOTHING。"""
    cols = ", ".join(columns)
    vals = ", ".join(values)
    if backend == "postgres":
        return f"INSERT INTO {table} ({cols}) VALUES ({vals}) ON CONFLICT({conflict_cols}) DO NOTHING;"
    return f"INSERT OR IGNORE INTO {table} ({cols}) VALUES ({vals});"


def _seed(backend: str) -> str:
    lines = ["-- ---- 初始数据 ----"]
    # console_meta 版本
    lines.append(_seed_insert(
        backend, "console_meta", ["key", "value"],
        [_sql_str("schema_version"), _sql_str("4")], "key"))
    # scenario_domains
    lines.append(_seed_insert(
        backend, "scenario_domains",
        ["id", "slug", "label_zh", "label_en", "sort", "created_at"],
        [_sql_str("medical"), _sql_str("medical"), _sql_str("医疗"), _sql_str("Medical"),
         "0", _sql_str(SEED_TS)], "slug"))
    # scenarios（含 spec 内容）
    for idx, slug in enumerate(SCENARIOS):
        zh, en = LABELS.get(slug, (slug, slug))
        spec_file = SPECS / f"{slug}.json"
        spec_json = spec_file.read_text(encoding="utf-8") if spec_file.is_file() else "{}"
        spec_path = f"docs/medical/specs/{slug}.json"
        lines.append(_seed_insert(
            backend, "scenarios",
            ["id", "domain_id", "slug", "label_zh", "label_en", "spec_path",
             "spec_json", "category", "sort", "created_at", "updated_at"],
            [_sql_str(slug), _sql_str("medical"), _sql_str(slug), _sql_str(zh), _sql_str(en),
             _sql_str(spec_path), _sql_str(spec_json), _sql_str("medical"), str(idx),
             _sql_str(SEED_TS), _sql_str(SEED_TS)], "slug"))
    return "\n".join(lines)


def generate(backend: str) -> str:
    return _ddl(backend).strip() + "\n\n" + _seed(backend).strip() + "\n"


def main() -> None:
    out_dir = ROOT / "deploy" / "console"
    out_dir.mkdir(parents=True, exist_ok=True)
    sqlite_path = out_dir / "schema.sqlite.sql"
    postgres_path = out_dir / "schema.postgres.sql"
    sqlite_path.write_text(generate("sqlite"), encoding="utf-8")
    postgres_path.write_text(generate("postgres"), encoding="utf-8")
    print(f"wrote {sqlite_path}")
    print(f"wrote {postgres_path}")


if __name__ == "__main__":
    main()
