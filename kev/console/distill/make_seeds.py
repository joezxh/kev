"""种子指令生成器 —— 蒸馏层的入口。

**核心设计：LLM 永不接触标签。** 流水线是反的：规则引擎先采样 state 并算出标签，再把 state 渲染成
种子 instruction 交给 EasyDistill，让百灵只写参考回答。Kev 标签的唯一来源是规则引擎，不经 LLM。

用法::

    python3 kev/console/distill/make_seeds.py --scenario inquiry --n 500 --out-dir data/seeds
    python3 kev/console/distill/make_seeds.py --all --n 500 --out-dir data/seeds

标准库 only，与 kev/console/generators/ 的其余脚本一致。
"""
import argparse
import json
import sys
from pathlib import Path


# 种子指令的提问模板由 DistillRenderer 从 DB 读取，标签来自规则引擎；LLM 不接触标签。


def write_jsonl(rows, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return path


def make_seeds_main(args):
    """Original --all/--scenario flow: produce <slug>.seed.jsonl + <slug>.state.jsonl."""
    from kev.console.db import Store
    from kev.console.distill.render import DistillRenderer
    store = Store()
    slugs = [args.scenario] if args.scenario else store.list_scenario_slugs()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for slug in slugs:
        row = store.get_scenario_by_slug(slug)
        if not row or not row.get("spec_json"):
            continue
        spec = json.loads(row["spec_json"])
        distill = spec.get("distill", {})
        if not distill.get("kev_track", False):
            # knowledge-qa etc.: SFT-only, no Kev sidecar
            continue
        renderer = DistillRenderer(distill)
        system = renderer.render_system_prompt(args.lang)
        # Run the engine to produce states
        from kev.console.generators.engine import run as engine_run
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as tmp:
            tmp_path = Path(tmp.name)
        engine_run(["--scenario", slug, "--n", str(args.n), "--out", str(tmp_path), "--seed", str(args.seed), "--pairs", "0"])
        # Split into seed + state
        with tmp_path.open(encoding="utf-8") as f:
            for i, line in enumerate(f):
                record = json.loads(line)
                state = record["state"]
                ask = renderer.render_ask(state)
                seed_row = {"id": str(i), "instruction": ask, "system": system}
                state_row = {"id": str(i), "scenario": slug, "state": state, "labels": record["questions"], "soft": {}}
                with (out_dir / f"{slug}.seed.jsonl").open("a", encoding="utf-8") as fs:
                    fs.write(json.dumps(seed_row, ensure_ascii=False) + "\n")
                with (out_dir / f"{slug}.state.jsonl").open("a", encoding="utf-8") as fst:
                    fst.write(json.dumps(state_row, ensure_ascii=False) + "\n")
        tmp_path.unlink()
    return 0


def render_config(slug: str, out_dir: str = "data/seeds/configs") -> int:
    """`make_seeds config <slug>` — render the EasyDistill YAML config from template.yaml.j2."""
    from kev.console.db import Store
    from kev.console.distill.render import DistillRenderer
    from jinja2 import Environment, FileSystemLoader
    store = Store()
    row = store.get_scenario_by_slug(slug)
    if not row or not row.get("spec_json"):
        print(f"scenario {slug} not found or has no spec_json", file=sys.stderr)
        return 1
    spec = json.loads(row["spec_json"])
    distill = spec.get("distill", {})
    renderer = DistillRenderer(distill)
    env = Environment(
        loader=FileSystemLoader(str(Path(__file__).parent / "configs")),
        autoescape=False,
        keep_trailing_newline=True,
    )
    template = env.get_template("template.yaml.j2")
    rendered = template.render(
        spec=spec,
        slug=slug,
        system_prompt=renderer.render_system_prompt("zh"),
        input_file=f"data/seeds/{slug}.seed.jsonl",
        output_dir=f"data/sft/{slug}",
    )
    out_path = Path(out_dir) / f"{slug}.yaml"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(rendered, encoding="utf-8")
    print(f"wrote {out_path}")
    return 0


def main():
    """Dispatch on first positional: `config` => render_config; else => make_seeds_main."""
    if len(sys.argv) >= 2 and sys.argv[1] == "config":
        # `make_seeds config --scenario <slug> --out-dir <out>`
        parser = argparse.ArgumentParser(prog="kev.console.distill.make_seeds config")
        parser.add_argument("--scenario", required=True)
        parser.add_argument("--out-dir", default="data/seeds/configs")
        args = parser.parse_args(sys.argv[2:])
        return render_config(args.scenario, args.out_dir)

    parser = argparse.ArgumentParser()
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--scenario", type=str, default=None)
    parser.add_argument("--n", type=int, default=500)
    parser.add_argument("--out-dir", type=str, default="data/seeds")
    parser.add_argument("--lang", type=str, default="zh", choices=["zh", "en"])
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()
    return make_seeds_main(args)


if __name__ == "__main__":
    sys.exit(main())
