"""蒸馏配置 + 用量聚合（Task B2）。

Run: uv run python -m pytest tests/test_console_distill_db.py -q
"""
import pytest

from kev.console.db import Store


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "kev-console.db")


def test_provider_crud_and_usage_upsert(store):
    meta = store.create_distill_provider("openai", "https://api.openai.com/v1",
                                         "gpt-4.1-mini", 500000, ["sk-aaa1111", "sk-bbb2222"])
    assert meta["key_count"] == 2
    assert meta["active"] == 1
    assert store.list_distill_providers()[0]["key_hints"]
    # 停用双删
    assert store.deactivate_distill_provider(meta["id"]) is True
    assert store.list_distill_providers() == []   # 列表只回启用
    # 用量 upsert 幂等（job_id 必须指向真实作业，否则外键失败）
    job_id = store.create_job(kind="distill", stage="data", scenario="critical-value", title="t",
        request={"provider_id": meta["id"], "state_dir": "x"}, argv=["x"], env_overlay={},
        cwd="/repo", log_path="l.log", artifacts_in=[], artifacts_out=[])
    store.upsert_distill_usage(job_id=job_id, provider_id=meta["id"], key_hash="h1",
        key_hint="sk-...1111", model="gpt-4.1-mini", base_url="x", day="2026-10-06", tokens=100)
    store.upsert_distill_usage(job_id=job_id, provider_id=meta["id"], key_hash="h1",
        key_hint="sk-...1111", model="gpt-4.1-mini", base_url="x", day="2026-10-06", tokens=250)
    agg = store.distill_usage_by_provider(meta["id"])
    assert agg[0]["tokens"] == 250          # 覆盖写，非累加
    assert agg[0]["days"] == 1
    by_job = store.distill_usage_by_job(job_id)
    assert by_job[0]["daily_limit"] == 500000
