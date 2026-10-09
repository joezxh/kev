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
    kid = r.json()["key"]
    # 现在返回的 key 即 key 的 id（uuid hex，32 位），前端选中后原样作为凭据提交。
    assert len(kid) == 32 and set(kid) <= set("0123456789abcdef")
    assert r.json()["prefix"].startswith("kev_")
    # 列表只回元数据，绝不回明文 / 哈希
    lst = client.get("/console/api/apikeys?all=1").json()
    assert lst[0]["id"] == kid
    assert lst[0]["prefix"].startswith("kev_")
    assert all("key_hash" not in k for k in lst)
    assert all("key" not in k for k in lst)
    # 撤销
    assert client.delete(f"/console/api/apikeys/{lst[0]['id']}").status_code == 200
    assert client.delete(f"/console/api/apikeys/{lst[0]['id']}").status_code == 404


def test_revoke_and_reactivate(client):
    r = client.post("/console/api/apikeys", json={"name": "pg"})
    kid = r.json()["id"]
    # 撤销后列表里 active 变 False
    assert client.delete(f"/console/api/apikeys/{kid}").status_code == 200
    assert client.get("/console/api/apikeys?all=1").json()[0]["active"] is False
    # 重新启用
    assert client.post(f"/console/api/apikeys/{kid}/reactivate").status_code == 200
    assert client.get("/console/api/apikeys?all=1").json()[0]["active"] is True
    # 已启用的再 re-enable 应 404
    assert client.post(f"/console/api/apikeys/{kid}/reactivate").status_code == 404


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


def test_apikeys_pagination(client):
    for i in range(5):
        client.post("/console/api/apikeys", json={"name": f"k{i}"})
    # 分页信封：total 为总数，items 为当前页。
    r = client.get("/console/api/apikeys?page=1&page_size=2").json()
    assert r["total"] == 5
    assert r["page"] == 1 and r["page_size"] == 2
    assert len(r["items"]) == 2
    # 第二页再返回 2 条。
    r2 = client.get("/console/api/apikeys?page=2&page_size=2").json()
    assert r2["page"] == 2 and len(r2["items"]) == 2
    # 越界页返回空，但 total 不变。
    r3 = client.get("/console/api/apikeys?page=99&page_size=2").json()
    assert len(r3["items"]) == 0 and r3["total"] == 5
    # ?all=1 仍返回全集（首页下拉选择器用）。
    assert len(client.get("/console/api/apikeys?all=1").json()) == 5
