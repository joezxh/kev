"""控制台数据库后端切换测试。

sqlite 为默认且必测（CI 里有 sqlite）；postgres 路径在没有可用 postgres 时跳过，
仅当显式设置 KEV_CONSOLE_DB_BACKEND=postgres 且提供连接信息时才真正连库跑一轮往返。
"""
import os

import pytest
import sqlalchemy as sa

from kev.console.db import Store, backend_url


def test_backend_url_defaults_to_sqlite(monkeypatch):
    for var in ("KEV_CONSOLE_DB_BACKEND", "KEV_CONSOLE_DB", "KEV_CONSOLE_DB_PATH"):
        monkeypatch.delenv(var, raising=False)
    url = backend_url()
    assert url.get_backend_name() == "sqlite"
    assert url.database.endswith("kev-console.db")


def test_backend_url_sqlite_path_override(monkeypatch):
    for var in ("KEV_CONSOLE_DB_BACKEND", "KEV_CONSOLE_DB", "KEV_CONSOLE_DB_PATH"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("KEV_CONSOLE_DB_PATH", "/tmp/foo.sqlite")
    assert backend_url().database.replace("\\", "/") == "/tmp/foo.sqlite"


def test_backend_url_postgres(monkeypatch):
    monkeypatch.setenv("KEV_CONSOLE_DB_BACKEND", "postgres")
    monkeypatch.setenv("KEV_CONSOLE_DB_HOST", "db.example.com")
    monkeypatch.setenv("KEV_CONSOLE_DB_PORT", "6543")
    monkeypatch.setenv("KEV_CONSOLE_DB_USER", "u")
    monkeypatch.setenv("KEV_CONSOLE_DB_PASSWORD", "p")
    monkeypatch.setenv("KEV_CONSOLE_DB_NAME", "kev_console")
    url = backend_url()
    assert url.get_backend_name().startswith("postgres")
    assert url.username == "u"
    assert url.password == "p"
    assert url.host == "db.example.com"
    assert url.port == 6543
    assert url.database == "kev_console"


def test_store_default_is_sqlite_round_trip(tmp_path):
    store = Store(tmp_path / "switch.sqlite")
    try:
        assert store.backend == "sqlite"
        assert store.schema_version() == 4
        jid = store.create_job(kind="train", stage="data", scenario="diagnosis", title="t",
                               request={}, argv=[], env_overlay={}, cwd="/tmp",
                               log_path="/tmp/x.log", artifacts_in=[], artifacts_out=[])
        assert store.get_job(jid)["status"] == "pending"
    finally:
        store.engine.dispose()


def test_postgres_round_trip_if_configured():
    if os.environ.get("KEV_CONSOLE_DB_BACKEND", "sqlite").lower() not in ("postgres", "postgresql"):
        pytest.skip("set KEV_CONSOLE_DB_BACKEND=postgres (+ connection env) to run the postgres integration test")
    store = Store()
    try:
        assert store.backend == "postgresql"
        # 表结构由 schema.postgres.sql / Store() 建好；这里跑一轮基础往返
        assert store.list_scenario_slugs()
        jid = store.create_job(kind="train", stage="data", scenario="diagnosis", title="t",
                               request={}, argv=[], env_overlay={}, cwd="/tmp",
                               log_path="/tmp/x.log", artifacts_in=[], artifacts_out=[])
        assert store.get_job(jid)["status"] == "pending"
        store.transition(jid, "running")
        store.transition(jid, "succeeded")
        assert store.get_job(jid)["status"] == "succeeded"
    finally:
        store.engine.dispose()
