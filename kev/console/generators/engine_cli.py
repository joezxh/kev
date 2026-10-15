"""Argparse builder for the engine CLI.

Spec §6.3. The flags match what gen_*.py::run used to accept (--n, --out, --seed, --pairs), with --scenario
replacing the hardcoded filename.

`--gate` is PR3's (design doc §3's exit row): the quality numbers `write_records` has always printed as warnings become
a non-zero exit code, and `auto` is the honest default — strict exactly when the spec declared a `floor`, so a scenario
written before this gate exists keeps shipping files instead of reddening CI on a threshold nobody asked it to meet.
"""
from __future__ import annotations

import argparse


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="kev.console.generators.engine")
    parser.add_argument("--scenario", required=True, help="scenario slug, e.g. critical-value")
    parser.add_argument("--n", type=int, default=787, help="records to generate (default 787; planned 4-question size)")
    parser.add_argument("--out", required=True, help="output labelled JSONL path")
    parser.add_argument("--seed", type=int, default=0, help="seed; the same seed reproduces the same file")
    parser.add_argument("--pairs", type=float, default=0.35, help="share of records that also get a minimal-pair twin appended (0 disables)")
    parser.add_argument("--gate", choices=("auto", "warn", "strict"), default="auto",
                        help="quality gate at the exit: `strict` fails on any gap, `warn` only prints them, and `auto` "
                             "(default) is strict for a spec that declares generator.plan_targets.floor")
    return parser
