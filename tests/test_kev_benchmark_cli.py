"""kev.benchmark 拆 CLI 后：run() 纯函数 + cancel 仍可工作。

跑：uv run python -m pytest tests/test_kev_benchmark_cli.py -q
"""
from __future__ import annotations

import argparse
import sys
import threading

import pytest

import kev.benchmark


def _min_args(**overrides) -> argparse.Namespace:
    """构造一个能跑过 run() 校验的最小 Namespace。

    base_revision=None 让 run() 走 suite 自身 pin（避免与 smoke 套件冲突）。
    """
    defaults = dict(
        run="runs/smoke-hl/00-trial-0/checkpoint",  # 触发现有 smoke checkpoint
        data=None,
        suite="evals/smoke-v1",
        out="runs/test-kev-benchmark-cli",
        device="cpu",
        split="development",
        allow_test=False,
        date_facts=False,
        rotations=1,
        remote=None,
        remote_model="kev-latest",
        remote_concurrency=1,
    )
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


def test_parse_args_returns_namespace():
    """parse_args() 接受 argv list 返回 Namespace，校验失败抛 SystemExit。"""
    args = kev.benchmark.parse_args(
        ["--run", "x", "--suite", "evals/smoke-v1", "--out", "runs/t"]
    )
    assert args.run == "x"
    assert args.suite == "evals/smoke-v1"


def test_parse_args_rejects_both_run_and_remote():
    """同时给 --run 和 --remote 应抛 SystemExit（argparse.error）。"""
    with pytest.raises(SystemExit):
        kev.benchmark.parse_args(
            ["--run", "x", "--remote", "http://x", "--suite", "evals/smoke-v1", "--out", "runs/t"]
        )


def test_cancel_event_is_module_level():
    assert isinstance(kev.benchmark.cancel, threading.Event)


def test_cancel_event_can_be_set_and_reset():
    kev.benchmark.cancel = threading.Event()
    assert kev.benchmark.cancel.is_set() is False
    kev.benchmark.cancel.set()
    assert kev.benchmark.cancel.is_set() is True
    kev.benchmark.cancel = threading.Event()  # 复位（与 service 层契约一致）


def test_cli_still_invokable():
    """`python -m kev.benchmark --help` 仍 work。"""
    import subprocess
    result = subprocess.run(
        [sys.executable, "-m", "kev.benchmark", "--help"],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, f"stdout={result.stdout!r} stderr={result.stderr!r}"
    assert "--run" in result.stdout
    assert "--out" in result.stdout
