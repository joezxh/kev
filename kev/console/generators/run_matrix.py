"""双尺寸编排驱动器：一个场景、一份数据、两个模型。

    python3 kev/console/generators/run_matrix.py --scenario critical-value --sizes 8b,4b --dry-run
    python3 kev/console/generators/run_matrix.py --scenario critical-value --sizes 8b,4b

为什么可以一份数据喂两个模型：skills/kev-finetune/scripts/split_data.py 按 **state 哈希**（大小写与空白归一
后的 sha256）分组划分，与模型无关，所以同一份 {train,calibration,development}.jsonl 可以直接喂给
jaredpalmer/kev-0.8b 和 jaredpalmer/kev-4b。副作用之一是 compare --a x-4b-v1 --b x-8b-v1 在同一份
development.jsonl 上打分，配对 bootstrap 有效 —— 于是 0.8B 与 4B 的差距可以被量化，而不是拍脑袋。

运行名规范：kev_modal.py 的 NAME 正则是 [A-Za-z0-9][A-Za-z0-9_-]{0,79}，**不允许点号**，所以尺寸标识写
8b / 4b 而不是 0.8b（triage-0.8b-v1 会被 check_name 拒绝）。本模块在启动前就校验，避免跑到 Modal 才报错。
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SKILL_SCRIPTS = ROOT / "skills/kev-finetune/scripts"
SPECS = ROOT / "docs/medical/specs"

# 与 kev_modal.py 中的 NAME 一致：首字符必须是字母数字，其余只允许字母数字、下划线、连字符（无点号）
NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}")

# 尺寸标识 -> (init checkpoint, 部署 app 前缀, 典型训练分钟数, 默认 lr 说明)
SIZES = {
    "8b": ("jaredpalmer/kev-0.8b", "kev-{scenario}-8b", 8, "4e-5（沿用 init 自身参数，比 4B 热）"),
    "4b": ("jaredpalmer/kev-4b", "kev-{scenario}-4b", 13, "2e-5（沿用 init 自身参数）"),
}

# Module-level proxies. These are *not* evaluated at import time (the DB path
# would circular-import). Callers that need a fresh list at runtime should use
# the helper functions below; callers that imported these names get the
# best-effort snapshot computed when the module first loaded.

from kev.console.db import Store as _Store  # noqa: E402  (after sys.path shim)


def list_scenarios() -> list:
    """DB-backed scenarios list."""
    return _Store().list_scenario_slugs()


def list_four_b_only() -> set:
    """DB-backed FOUR_B_ONLY set."""
    store = _Store()
    import json as _json
    slugs = set()
    for slug in store.list_scenario_slugs():
        row = store.get_scenario_by_slug(slug)
        if not row or not row.get("spec_json"):
            continue
        try:
            spec = _json.loads(row["spec_json"])
        except (TypeError, ValueError):
            continue
        if (spec.get("routing") or {}).get("four_b_only") is True:
            slugs.add(slug)
    return slugs


# SCENARIOS / FOUR_B_ONLY names were deleted in Task 29. Downstream callers
# (kev.console.db / kev.console.stages.data / kev.console.stages.train) still
# import them as `from run_matrix import SCENARIOS / FOUR_B_ONLY`; those imports
# are now broken by design. Tasks 30 / 31 will point the callers at
# `list_scenarios()` / `list_four_b_only()` (or their own DB query).


def check_name(name):
    """Validate a Modal run name against the same rule kev_modal.py::check_name applies.

    Uses fullmatch, not match: kev_modal.py's NAME pattern is unanchored at the end, so `match` would accept
    'critical-value-0.8b-v1' (it happily matches the 'critical-value-' prefix) and the dot would only blow up later
    on Modal, after the data was already generated.
    """
    if not NAME_RE.fullmatch(name):
        raise SystemExit(f"invalid run name {name!r}: only letters, digits, underscore and hyphen are allowed "
                         f"(no dots -- use '8b' rather than '0.8b')")
    return name


def steps(scenario, sizes, data, version, python, secret=""):
    """The command sequence, in order, as (name, argv, env) triples so --dry-run can print it faithfully."""
    spec = SPECS / f"{scenario}.json"
    out = [
        ("plan_size", [python, str(SKILL_SCRIPTS / "plan_size.py"), str(spec), "--baseline-acc", "0.75"], None),
        ("generate", [python, str(Path(__file__).resolve().parent / "engine.py"),
                      "--scenario", scenario,
                      "--n", "787", "--out", f"{data}.jsonl", "--seed", "0"], None),
        ("split", [python, str(SKILL_SCRIPTS / "split_data.py"), f"{data}.jsonl", "--out", data], None),
    ]
    for size in sizes:
        out.append((f"validate_{size}", ["modal", "run", str(SKILL_SCRIPTS / "kev_modal.py"), "::validate",
                                         "--data", data, "--init-from", SIZES[size][0]], None))
    names = {}
    for size in sizes:
        names[size] = check_name(f"{scenario}-{size}-v{version}")
        out.append((f"train_{size}", ["modal", "run", str(SKILL_SCRIPTS / "kev_modal.py"), "::train",
                                      "--data", data, "--name", names[size],
                                      "--init-from", SIZES[size][0]], None))
    if len(sizes) == 2:
        out.append(("compare", ["modal", "run", str(SKILL_SCRIPTS / "kev_modal.py"), "::compare",
                                "--a", names[sizes[1]], "--b", names[sizes[0]]], None))
    for size in sizes:
        # Two coexisting endpoints need distinct KEV_APP_NAME and KEV_SERVE_RUN, otherwise the second
        # `modal deploy` replaces the first behind the same app and URL.
        env = {"KEV_APP_NAME": SIZES[size][1].format(scenario=scenario), "KEV_SERVE_RUN": names[size]}
        if secret:
            env["KEV_SERVE_SECRET"] = secret
        out.append((f"deploy_{size}", ["modal", "deploy", str(SKILL_SCRIPTS / "kev_modal.py")], env))
    return out, names


def run(argv, env, dry_run):
    prefix = " ".join(f"{k}={v}" for k, v in sorted((env or {}).items()))
    print(f"  $ {prefix + ' ' if prefix else ''}{' '.join(argv)}")
    if dry_run:
        return 0
    import os

    merged = dict(os.environ)
    merged.update(env or {})
    merged.setdefault("PYTHONIOENCODING", "utf-8")
    return subprocess.run(argv, env=merged).returncode


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--scenario", required=True, choices=SCENARIOS,
                        help=f"one of {', '.join(SCENARIOS)} (specs live in docs/medical/specs)")
    parser.add_argument("--sizes", default="8b,4b", help=f"comma list from {{{', '.join(SIZES)}}}; both share one dataset")
    parser.add_argument("--data", default="", help="split directory; default data/<scenario>")
    parser.add_argument("--version", type=int, default=1, help="run-name version suffix; names are immutable on Modal")
    parser.add_argument("--python", default=sys.executable, help="interpreter for the local scripts")
    parser.add_argument("--secret", default="", help="Modal secret holding KEV_API_KEY for the deployed endpoints")
    parser.add_argument("--start-from", default="", help="skip steps before this one (for resuming)")
    parser.add_argument("--dry-run", action="store_true", help="print the command sequence and exit")
    args = parser.parse_args(argv)

    sizes = [s.strip() for s in args.sizes.split(",") if s.strip()]
    unknown = [s for s in sizes if s not in SIZES]
    if unknown:
        raise SystemExit(f"unknown size(s) {unknown}; choose from {sorted(SIZES)}")
    if args.scenario in FOUR_B_ONLY and set(sizes) != {"4b"}:
        raise SystemExit(f"{args.scenario} supports the 4B track only (semantic difficulty); got --sizes {args.sizes}")
    data = args.data or f"data/{args.scenario}"
    plan, names = steps(args.scenario, sizes, data, args.version, args.python, args.secret)

    print(f"scenario {args.scenario} | sizes {sizes} | data {data} | runs {names}")
    for size in sizes:
        init, _, minutes, lr = SIZES[size]
        print(f"  {size}: init {init}, ~{minutes} min on H100, lr {lr}")
    known = [name for name, _, _ in plan]
    if args.start_from and args.start_from not in known:
        raise SystemExit(f"unknown step {args.start_from!r}; choose from {known}")
    print("steps:")
    for name, cmd, env in plan[known.index(args.start_from) if args.start_from else 0:]:
        if run(cmd, env, args.dry_run) != 0 and not args.dry_run:
            print(f"failed at step {name!r}; fix and resume with --start-from {name}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
