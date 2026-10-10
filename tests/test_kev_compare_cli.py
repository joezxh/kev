"""kev.compare 拆 CLI 后：run() 纯函数 + parse_args() 仍 work。

跑：uv run python -m pytest tests/test_kev_compare_cli.py -q
"""
from __future__ import annotations

import argparse
import sys

import kev.compare


def test_parse_args_returns_namespace():
    args = kev.compare.parse_args(["--candidate", "a", "--reference", "b", "--out", "c"])
    assert args.candidate == "a"
    assert args.reference == "b"
    assert args.out == "c"


def test_parse_args_rejects_missing_required():
    """三个 required 都缺时 argparse 抛 SystemExit。"""
    import pytest
    with pytest.raises(SystemExit):
        kev.compare.parse_args([])


def test_cli_still_invokable():
    """`python -m kev.compare --help` 仍 work。"""
    import subprocess
    result = subprocess.run(
        [sys.executable, "-m", "kev.compare", "--help"],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, f"stdout={result.stdout!r} stderr={result.stderr!r}"
    assert "--candidate" in result.stdout
    assert "--reference" in result.stdout
