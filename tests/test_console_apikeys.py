"""apikey 管理 + 核心接口用量落库（本计划 Task A1）。

Run: uv run python -m pytest tests/test_console_apikeys.py -q
"""
import hashlib

import pytest

from kev.console.db import Store


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "kev-console.db")


def test_create_api_key_returns_raw_once_and_hashes(store):
    raw, meta = store.create_api_key("playground")
    assert raw.startswith("kev_")
    assert meta["prefix"] == raw[:12]
    assert meta["active"] == 1   # SQLite 以 INTEGER 存 active; 前端按真值使用
    assert meta["key_hash"] == hashlib.sha256(raw.encode()).hexdigest()
    # 库里查不到明文
    row = store.connect().execute("SELECT key_hash FROM api_keys WHERE id=?", (meta["id"],)).fetchone()
    assert row["key_hash"] != raw


def test_get_key_by_hash_only_active(store):
    raw, meta = store.create_api_key("k")
    h = hashlib.sha256(raw.encode()).hexdigest()
    assert store.get_key_by_hash(h) is not None
    assert store.revoke_api_key(meta["id"]) is True
    assert store.get_key_by_hash(h) is None


def test_record_and_summary_aggregates(store):
    raw, meta = store.create_api_key("k")
    store.record_usage(key_id=meta["id"], endpoint="systemone", method="POST",
                        status=200, input_tokens=10, output_tokens=5, latency_ms=12.0)
    store.record_usage(key_id=meta["id"], endpoint="systemone", method="POST",
                        status=200, input_tokens=20, output_tokens=8, latency_ms=20.0)
    summary = store.usage_summary()
    assert summary[0]["calls"] == 2
    assert summary[0]["input_tokens"] == 30
    assert summary[0]["p99_latency_ms"] == 20.0   # 两样本 99 分位取最大
    series = store.usage_timeseries(meta["id"])
    assert series[0]["calls"] == 2
