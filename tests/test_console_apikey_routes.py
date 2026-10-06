"""apikey 路由 + 用量路由（Task A2）。用 FastAPI TestClient；kev 代理的端到端（需真实 kev.serve）留手动验收。

Run: uv run python -m pytest tests/test_console_apikey_routes.py -q
"""
import pytest
from fastapi.testclient import TestClient

from kev.console.app import create_app
from kev.console.db import Store


@pytest.fixture
def client(tmp_path):
    db = Store(tmp_path / "kev-console.db")
    return TestClient(create_app(store=db))


def test_create_and_list_and_revoke(client):
    r = client.post("/console/api/apikeys", json={"name": "pg"})
    assert r.status_code == 201, r.text
    raw = r.json()["key"]
    assert raw.startswith("kev_")
    assert r.json()["prefix"] == raw[:12]
    # 列表只回元数据，绝不回明文 / 哈希
    lst = client.get("/console/api/apikeys").json()
    assert lst[0]["prefix"] == raw[:12]
    assert all("key_hash" not in k for k in lst)
    assert all("key" not in k for k in lst)
    # 撤销
    assert client.delete(f"/console/api/apikeys/{lst[0]['id']}").status_code == 200
    assert client.delete(f"/console/api/apikeys/{lst[0]['id']}").status_code == 404


def test_usage_routes_exist(client):
    # 尚未有任何调用时返回空列表（不报错）
    assert client.get("/console/api/usage").status_code == 200
    assert client.get("/console/api/usage?from=2026-01-01").status_code == 200


def test_proxy_rejects_missing_key(client):
    r = client.post("/console/api/kev/v1/systemone", json={"question": "x", "options": ["a", "b"]})
    assert r.status_code == 401


def test_proxy_rejects_unknown_key(client):
    r = client.post("/console/api/kev/v1/systemone", json={"question": "x", "options": ["a", "b"]},
                     headers={"authorization": "Bearer kev_deadbeef"})
    assert r.status_code == 401
