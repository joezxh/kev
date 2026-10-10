"""kev.publish 拆 CLI 后：run() 纯函数 + parse_args() 仍 work。

跑：uv run python -m pytest tests/test_kev_publish_cli.py -q
"""
from __future__ import annotations

import sys

import kev.publish


def test_parse_args_returns_namespace():
    args = kev.publish.parse_args(
        ["--run", "runs/x/checkpoint", "--repo", "jaredpalmer/kev-0.8b", "--card", "docs/model-cards/kev-0.8b.md"]
    )
    assert args.run == "runs/x/checkpoint"
    assert args.repo == "jaredpalmer/kev-0.8b"
    assert args.card == "docs/model-cards/kev-0.8b.md"
    assert args.private is False
    assert args.replace is False
    assert args.tag is None
    assert args.revision is None


def test_parse_args_accepts_optional_flags():
    args = kev.publish.parse_args(
        ["--run", "runs/x/checkpoint", "--repo", "jaredpalmer/kev-0.8b", "--card", "x.md",
         "--private", "--replace", "--tag", "v0.2", "--revision", "candidate"]
    )
    assert args.private is True
    assert args.replace is True
    assert args.tag == "v0.2"
    assert args.revision == "candidate"


def test_parse_args_rejects_missing_required():
    import pytest
    with pytest.raises(SystemExit):
        kev.publish.parse_args([])


def test_cli_still_invokable():
    """`python -m kev.publish --help` 仍 work。"""
    import subprocess
    result = subprocess.run(
        [sys.executable, "-m", "kev.publish", "--help"],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, f"stdout={result.stdout!r} stderr={result.stderr!r}"
    assert "--run" in result.stdout
    assert "--repo" in result.stdout
    assert "--card" in result.stdout
