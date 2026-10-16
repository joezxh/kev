"""服务端密钥库（Task B1）。明文 key 只落这个文件。

Run: uv run python -m pytest tests/test_console_secret_store.py -q
"""
import hashlib

import pytest

from kev.console import secret_store


@pytest.fixture
def isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(secret_store, "DEFAULT_PATH", tmp_path / "secrets.json")


def test_put_load_remove(isolate):
    secret_store.put("p1", {"keys": ["sk-aaa1111"], "base_url": "x", "model": "m", "daily_limit": 1})
    data = secret_store.load()
    assert data["p1"]["keys"] == ["sk-aaa1111"]
    secret_store.remove("p1")
    assert "p1" not in secret_store.load()


def test_mask_hashes_and_hints(isolate):
    h, hint = secret_store.mask("sk-abcdefghijklmnop")
    assert h == hashlib.sha256(b"sk-abcdefghijklmnop").hexdigest()
    assert hint == "sk-...mnop"
