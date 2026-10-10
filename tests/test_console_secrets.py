"""服务端密钥库（Task B1）。明文 key 只落这个文件。

Run: uv run python -m pytest tests/test_console_secrets.py -q
"""
import hashlib

import pytest

from kev.console import secrets


@pytest.fixture
def isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(secrets, "DEFAULT_PATH", tmp_path / "secrets.json")


def test_put_load_remove(isolate):
    secrets.put("p1", {"keys": ["sk-aaa1111"], "base_url": "x", "model": "m", "daily_limit": 1})
    data = secrets.load()
    assert data["p1"]["keys"] == ["sk-aaa1111"]
    secrets.remove("p1")
    assert "p1" not in secrets.load()


def test_mask_hashes_and_hints(isolate):
    h, hint = secrets.mask("sk-abcdefghijklmnop")
    assert h == hashlib.sha256(b"sk-abcdefghijklmnop").hexdigest()
    assert hint == "sk-...mnop"
