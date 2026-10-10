"""kev.calibrate 拆 CLI 后：run() 纯函数 + parse_args() 仍 work。

跑：uv run python -m pytest tests/test_kev_calibrate_cli.py -q
"""
from __future__ import annotations

import sys

import kev.calibrate


def test_parse_args_returns_namespace():
    args = kev.calibrate.parse_args(["--rows", "runs/x/rows.json", "--folds", "3"])
    assert args.rows == "runs/x/rows.json"
    assert args.folds == 3
    assert args.seed == 0  # default
    assert args.samples == 1000  # default


def test_parse_args_rejects_missing_required():
    import pytest
    with pytest.raises(SystemExit):
        kev.calibrate.parse_args([])


def test_cli_still_invokable():
    """`python -m kev.calibrate --help` 仍 work。"""
    import subprocess
    result = subprocess.run(
        [sys.executable, "-m", "kev.calibrate", "--help"],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, f"stdout={result.stdout!r} stderr={result.stderr!r}"
    assert "--rows" in result.stdout
