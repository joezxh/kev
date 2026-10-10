"""Argparse builder for the engine CLI.

Spec §6.3. The flags match what gen_*.py::run used to accept (--n, --out, --seed, --pairs), with --scenario
replacing the hardcoded filename.
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
    return parser
