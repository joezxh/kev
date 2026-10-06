"""蒸馏配置路由 + 用量采集（Task B3）。
Run: uv run python -m pytest tests/test_console_distill_routes.py -q
"""
import json

import pytest
from fastapi.testclient import TestClient

from kev.console.app import create_app
from kev.console.db import Store
from kev.console import secrets as distill_secrets


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(distill_secrets, "DEFAULT_PATH", tmp_path / "secrets.json")
    db = Store(tmp_path / "kev-console.db")
    return TestClient(create_app(store=db))


def test_provider_crud_and_usage_ingest(client, tmp_path):
    r = client.post("/console/api/distill-providers", json={
        "name": "oa", "base_url": "https://api.openai.com/v1", "model": "gpt-4.1-mini",
        "daily_limit": 100, "keys": ["sk-aaa1111"]})
    assert r.status_code == 201, r.text
    pid = r.json()["id"]
    # 列表/详情绝不回明文 key
    assert all("keys" not in p for p in client.get("/console/api/distill-providers").json())
    # 停用即删密钥库
    assert client.delete(f"/console/api/distill-providers/{pid}").status_code == 200
    assert client.get("/console/api/distill-providers").json() == []

    # 用量采集：造一个 distill 作业 + 假 usage 文件
    jid = client.app.state.store.create_job(
        kind="distill", stage="data", scenario="critical-value", title="t",
        request={"provider_id": pid, "state_dir": str(tmp_path / "state")},
        argv=["x"], env_overlay={}, cwd="/repo", log_path="l.log",
        artifacts_in=[], artifacts_out=[])
    (tmp_path / "state").mkdir()
    (tmp_path / "state" / "usage_2026-10-06.json").write_text(
        json.dumps({"sk-aaa1111": 123}), encoding="utf-8")
    rows = client.get(f"/console/api/distill/{jid}/usage").json()
    assert rows[0]["tokens"] == 123
    assert rows[0]["key_hint"] == "sk-...1111"


def test_distill_build_resolves_existing_generate_data_script():
    """_distill_build 依赖 skills/kev-finetune/scripts/generate_data.py：该脚本读取
    KEV_GEN_* 环境并写 <state_dir>/usage_<date>.json（spec §9 的用量上报契约）。若路径被
    移动/改名，蒸馏端到端会静默失败。守卫：引用文件必须存在，且 argv[1] 指向同一文件。
    """
    from pathlib import Path

    from kev.console import paths
    from kev.console.stages.base import JobRequest
    from kev.console.stages.data import _distill_build

    target = paths.SKILL_SCRIPTS / "generate_data.py"
    assert target.exists(), f"蒸馏脚本缺失：{target}（_distill_build 依赖它）"
    req = JobRequest(scenario="critical-value", run_name="cv-8b-lora-v1",
                     params={"skip_exists_check": True, "api_keys": ["sk-test0001"]})
    built = _distill_build(req)
    assert Path(built.argv[1]) == target, (
        f"_distill_build 指向 {built.argv[1]}，与 {target} 不一致")
