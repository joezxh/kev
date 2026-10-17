"""把 docs/domains 五领域的全量 spec 导入控制台库（scenario_domains + scenarios）。

单一真相源是 `kev/console/scenario_specs.py`：它读 docs/domains/<领域>/specs/*.json、
kev/console/distill/configs/*.yaml 与 generators/gen_*.py，派生出「有哪些域、有哪些场景、
每个场景走哪条轨（track / generator_kind / distill_yaml）、spec 内容是什么」，再和
docs/domains/README.md §1 的清单交叉校验。本脚本不复制任何清单，只负责：

  1. 注入 .env 里的 KEV_CONSOLE_DB_*（仓库不自动加载 .env，见 kev/console/db.py::backend_url）；
  2. 跑 scenario_specs.audit()，清单与 README 不一致就直接失败，不带病入库；
  3. 调 Store().seed_scenarios(...) 落库（建表/迁移由 Store 完成：schema_version 7 -> 8 会给
     scenario_domains 补 spec_dir、给 scenarios 补 track/generator_kind/distill_yaml/origin）；
  4. 回读库里的实际状态并打印（每领域场景数、轨制分布、spec_json 覆盖率），并和 README 对账。

用法：
  uv run python scripts/import_domain_specs.py                 # 幂等导入（可反复跑）
  uv run python scripts/import_domain_specs.py --force         # 以文件为准覆盖 spec_json（覆盖前的库内内容进 scenario_spec_history）
  uv run python scripts/import_domain_specs.py --check         # 只读校验/对账，绝不写库（CI 用）
  uv run python scripts/import_domain_specs.py --domain medical,law --json

默认不覆盖已有的 spec_json：库里已被编辑过的内容才是真相，只有为空时才会填上文件内容。
既有场景行的中英文标签、sort、category 同样不被种子改动；重跑不会翻倍。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import sqlalchemy as sa  # noqa: E402

from kev.console import db as console_db      # noqa: E402
from kev.console import scenario_specs        # noqa: E402


def load_dotenv(path: Path = ROOT / ".env") -> dict[str, str]:
    """把 .env 里的 KEV_* 变量注入 os.environ（已存在的不覆盖），返回注入了哪些。

    仓库没有 python-dotenv 依赖，控制台库的连接参数只从 os.environ 读，
    所以手工跑脚本时必须自己把 .env 递进去。
    """
    injected: dict[str, str] = {}
    if not path.is_file():
        return injected
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if not key.startswith("KEV_") or key in os.environ:
            continue
        os.environ[key] = value
        injected[key] = value
    return injected


def read_only_snapshot() -> tuple[sa.engine.Engine, list[dict], list[dict]]:
    """不建 Store（避免建表/迁移/播种），只做 SELECT：--check 与前后对账用。"""
    engine = sa.create_engine(console_db.backend_url())
    with engine.connect() as conn:
        domains = [dict(r) for r in conn.execute(sa.text(
            "SELECT id, slug, label_zh, label_en, sort, spec_dir"
            " FROM scenario_domains ORDER BY sort, slug")).mappings().fetchall()]
        scenarios = [dict(r) for r in conn.execute(sa.text(
            "SELECT slug, domain_id, label_zh, spec_path, spec_json, track,"
            " generator_kind, distill_yaml, origin FROM scenarios ORDER BY slug")).mappings().fetchall()]
    return engine, domains, scenarios


def compare_with_files(entries: list[scenario_specs.SpecEntry],
                       domains: list[dict], scenarios: list[dict]) -> list[str]:
    """库内现状 vs docs/domains 的派生清单，返回问题清单（空 = 一致）。"""
    problems: list[str] = []
    by_slug = {s["slug"]: s for s in scenarios}
    # 导入按 scenario_domains.spec_dir 认领域行，旧库里用户手工建的同义 slug（research 即 science）
    # 不会被重命名，所以对账也必须比 spec_dir，不能比 slug。
    domain_rows = {d["id"]: (d["slug"], d["spec_dir"] or "") for d in domains}
    for entry in entries:
        row = by_slug.get(entry.slug)
        if row is None:
            problems.append(f"{entry.slug}: 库里没有该场景（需要导入）")
            continue
        slug_of_row, dir_of_row = domain_rows.get(row["domain_id"], ("?", ""))
        if (dir_of_row or slug_of_row) != entry.domain.spec_dir:
            problems.append(f"{entry.slug}: 库里属于域 {slug_of_row}(spec_dir={dir_of_row or '空'})，"
                            f"文件在 docs/domains/{entry.domain.spec_dir}/specs")
        if row["track"] != entry.track:
            problems.append(f"{entry.slug}: 库里 track={row['track']!r}，派生={entry.track!r}")
        if not row["spec_json"]:
            problems.append(f"{entry.slug}: spec_json 为空（运行时回退 spec_path 文件）")
    for slug in sorted(set(by_slug) - {e.slug for e in entries}):
        row = by_slug[slug]
        if row["origin"] == console_db.Store.SEED_ORIGIN:
            problems.append(f"{slug}: 种子行但 docs/domains 下已无对应 spec 文件")
        # origin 为空 = 用户手工建的场景，不算问题
    return problems


def report(entries: list[scenario_specs.SpecEntry], domains: list[dict],
           scenarios: list[dict]) -> dict:
    """把库内现状压成一份可打印/可 JSON 化的摘要。"""
    domain_slug = {d["id"]: d["slug"] for d in domains}
    counts: Counter[str] = Counter(domain_slug.get(s["domain_id"], "(未知域)") for s in scenarios)
    tracks: Counter[str] = Counter(s["track"] or "(无)" for s in scenarios)
    slugs = {e.slug for e in entries}
    contents = {e.slug: e.content for e in entries}
    # 库内与文件内容不一致的行不算问题：spec_json 是真相源，经控制台编辑后本来就该领先于文件；
    # 报出来是为了预告「--force 会覆盖这 N 行」。
    drift = sum(1 for s in scenarios
                if s["slug"] in contents and s["spec_json"]
                and s["spec_json"] != contents[s["slug"]])
    return {
        "database": console_db.backend_url().render_as_string(hide_password=True),
        "schema_version": console_db.SCHEMA_VERSION,
        "domains": [{"slug": d["slug"], "label_zh": d["label_zh"], "spec_dir": d["spec_dir"],
                     "scenarios": counts[d["slug"]]} for d in domains],
        "domain_count": len(domains),
        "scenario_count": len(scenarios),
        "scenarios_per_domain": dict(sorted(counts.items())),
        "track_distribution": dict(sorted(tracks.items())),
        "spec_json_filled": sum(1 for s in scenarios if s["spec_json"]),
        # 三个互斥桶：本脚本导入登记的行 / 旧库里已有、本次只刷派生列的行 /
        # 库里多出来的手工行（docs/domains 下无对应文件，本脚本不管）。
        "imported_rows": sum(1 for s in scenarios if s["origin"] == console_db.Store.SEED_ORIGIN),
        "preexisting_rows": sum(1 for s in scenarios
                                if s["origin"] != console_db.Store.SEED_ORIGIN and s["slug"] in slugs),
        "unmanaged_rows": sum(1 for s in scenarios if s["slug"] not in slugs),
        "spec_json_drift": drift,
        "expected_from_files": {"domains": len(scenario_specs.domains()),
                                "scenarios": len(entries)},
    }


def print_report(summary: dict, stats: "dict | None") -> None:
    print(f"库：{summary['database']}  schema_version={summary['schema_version']}")
    if stats is not None:
        print(f"本次：新建域 {stats['domains_created']}，新建场景 {stats['scenarios_created']}，"
              f"刷新场景 {stats['scenarios_updated']}，写入 spec_json {stats['specs_written']}")
    print("领域：")
    for d in summary["domains"]:
        source = d["spec_dir"] or "手工建域（无 docs/domains 目录）"
        print(f"  {d['slug']:<10} {d['label_zh']:<4} 场景 {d['scenarios']:>3}  <- docs/domains/{source}")
    print(f"合计：{summary['domain_count']} 领域 / {summary['scenario_count']} 场景"
          f"（导入登记 {summary['imported_rows']}，旧库已有 {summary['preexisting_rows']}，"
          f"手工未纳管 {summary['unmanaged_rows']}），spec_json 已填 {summary['spec_json_filled']}")
    print(f"轨制分布：{summary['track_distribution']}")
    if summary.get("spec_json_drift"):
        print(f"提示：{summary['spec_json_drift']} 行的库内 spec_json 与文件不同（以库内为准；"
              "--force 会以文件覆盖并把旧内容归档）")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="导入 docs/domains 五领域 spec 到控制台库（域表 + 场景表）")
    parser.add_argument("--force", action="store_true",
                        help="以文件为准覆盖 scenarios.spec_json（覆盖前的库内内容进历史表）")
    parser.add_argument("--check", action="store_true",
                        help="只读：校验清单与库内一致性，绝不写库")
    parser.add_argument("--domain", default="",
                        help="只处理这些领域（逗号分隔，如 medical,law）；--check 时只对这些场景对账")
    parser.add_argument("--json", action="store_true", dest="as_json", help="输出 JSON 摘要")
    args = parser.parse_args()

    only = tuple(s.strip() for s in args.domain.split(",") if s.strip())
    injected = load_dotenv()

    problems = scenario_specs.audit()
    if problems:
        for problem in problems:
            print("PROBLEM:", problem, file=sys.stderr)
        print("docs/domains 与 README 不一致，先修清单再导入", file=sys.stderr)
        return 1

    entries = scenario_specs.entries()
    if only:
        known = {d.slug for d in scenario_specs.domains()}
        unknown = [d for d in only if d not in known]
        if unknown:
            print(f"PROBLEM: 未知领域 {unknown}（可选：{sorted(known)}）", file=sys.stderr)
            return 1
        entries = [e for e in entries if e.domain.slug in only]

    if args.check:
        try:
            engine, domains, scenarios = read_only_snapshot()
        except sa.exc.DBAPIError as exc:
            print(f"PROBLEM: 读不到 scenario_domains / scenarios 表（{type(exc).__name__}: {exc.orig}），"
                  "先用不带 --check 的本脚本建库导入", file=sys.stderr)
            return 1
        engine.dispose()
        scoped = {e.slug for e in entries}
        mismatches = compare_with_files(entries, domains,
                                        [s for s in scenarios if s["slug"] in scoped])
        summary = report(entries, domains, scenarios)
        summary["mismatches"] = mismatches
        if args.as_json:
            print(json.dumps(summary, ensure_ascii=False, indent=2))
        else:
            print_report(summary, None)
            for mismatch in mismatches:
                print("DIFF:", mismatch)
        return 1 if mismatches else 0

    if injected and not args.as_json:
        print(f"已从 .env 注入 {len(injected)} 个 KEV_* 变量")

    # Store() 建表并把 schema 推到 v8；seed=False 把「何时、导哪些域」交给下面的显式播种
    store = console_db.Store(seed=False)
    stats = store.seed_scenarios(force=args.force, only_domains=only or None)

    engine, domain_rows, scenario_rows = read_only_snapshot()
    engine.dispose()
    scoped = {e.slug for e in entries}
    mismatches = compare_with_files(entries, domain_rows,
                                    [r for r in scenario_rows if r["slug"] in scoped])
    summary = report(entries, domain_rows, scenario_rows)
    summary["seed_stats"] = stats
    summary["mismatches"] = mismatches

    if args.as_json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print_report(summary, stats)
        for mismatch in mismatches:
            print("DIFF:", mismatch)
    for problem in mismatches:
        print("PROBLEM:", problem, file=sys.stderr)
    return 1 if mismatches else 0


if __name__ == "__main__":
    sys.exit(main())
