#!/usr/bin/env python3
"""生成 kev console 的两套初始化 SQL（sqlite / postgresql）。

两个单一数据源：
- 建表 DDL 来自 `kev/console/db.py::_ddl`（含 console_meta 的 schema_version）。
- 领域与场景清单来自 `kev/console/scenario_specs.py`，即 docs/domains/<领域>/specs/*.json 的
  登记结果（中英标签、轨制派生、EasyDistill 配置路径都在那里派生，本脚本不复制任何清单）。

产出 `deploy/console/schema.sqlite.sql` 与 `deploy/console/schema.postgres.sql`。

spec 内容（scenarios.spec_json）**不在这里内联**：61 份 spec 约 780 KB，每次改 spec 都得重生成
两个大文件、diff 也没法看。initdb 之后控制台首次启动（`Store.seed_scenarios`）会补上为空的
spec_json；只想建库不启动服务时，跑 `uv run python scripts/import_domain_specs.py` 显式导入。
运行时读不到 spec_json 的路径本来就回退到 spec_path 文件，所以空着也不影响启动。

改了 db.py 的表结构或 docs/domains 的清单应重跑本脚本
（`uv run python scripts/gen_console_schema.py`），避免两份 DDL 漂移。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from kev.console import db as console_db          # noqa: E402
from kev.console import scenario_specs            # noqa: E402

SEED_TS = "2026-01-01T00:00:00+00:00"


def _sql_str(value: str) -> str:
    """SQL 单引号字符串字面量：内部单引号翻倍。"""
    return "'" + str(value).replace("'", "''") + "'"


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
    entries = scenario_specs.entries()
    lines = ["-- ---- 初始数据（领域与场景登记；spec 内容由 scripts/import_domain_specs.py 或"
             "控制台启动时的 seed_scenarios 落库）----"]
    lines.append(_seed_insert(
        backend, "console_meta", ["key", "value"],
        [_sql_str("schema_version"), _sql_str(console_db.SCHEMA_VERSION)], "key"))
    for domain in scenario_specs.domains():
        lines.append(_seed_insert(
            backend, "scenario_domains",
            ["id", "slug", "label_zh", "label_en", "sort", "spec_dir", "created_at"],
            [_sql_str(domain.slug), _sql_str(domain.slug), _sql_str(domain.label_zh),
             _sql_str(domain.label_en), str(domain.sort), _sql_str(domain.spec_dir),
             _sql_str(SEED_TS)], "slug"))
    for entry in entries:
        lines.append(_seed_insert(
            backend, "scenarios",
            ["id", "domain_id", "slug", "label_zh", "label_en", "spec_path", "category", "sort",
             "track", "generator_kind", "distill_yaml", "origin", "created_at", "updated_at"],
            [_sql_str(entry.slug), _sql_str(entry.domain.slug), _sql_str(entry.slug),
             _sql_str(entry.label_zh), _sql_str(entry.label_en), _sql_str(entry.spec_path),
             _sql_str(entry.domain.slug), str(entry.sort), _sql_str(entry.track),
             _sql_str(entry.generator_kind), _sql_str(entry.distill_yaml),
             _sql_str(console_db.Store.SEED_ORIGIN), _sql_str(SEED_TS), _sql_str(SEED_TS)],
            "slug"))
    return "\n".join(lines)


def generate(backend: str) -> str:
    return console_db._ddl(backend).strip() + "\n\n" + _seed(backend).strip() + "\n"


def main() -> int:
    problems = scenario_specs.audit()
    for problem in problems:
        print("PROBLEM:", problem, file=sys.stderr)
    if problems:
        print("docs/domains 与 README 不一致，先修清单再生成 SQL（详见 --help）", file=sys.stderr)
        return 1
    entries = scenario_specs.entries()
    out_dir = ROOT / "deploy" / "console"
    out_dir.mkdir(parents=True, exist_ok=True)
    for backend, name in (("sqlite", "schema.sqlite.sql"), ("postgres", "schema.postgres.sql")):
        target = out_dir / name
        target.write_text(generate(backend), encoding="utf-8")
        print(f"wrote {target}（{len(scenario_specs.domains())} 领域 / {len(entries)} 场景）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
