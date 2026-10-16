"""服务端密钥库：蒸馏第三方模型凭据的唯一落盘处（spec §4.3 / §7）。

明文 key 只在这里，SQLite 只存非敏感元数据。文件 gitignore、权限 0600。

**别改回 `secrets.py`**：kev/console 的脚本是以 `python kev/console/<stage>.py` 跑的（编排层就是这么拼 argv），
那时 sys.path[0] 就是本目录，模块名 `secrets` 会**遮蔽标准库 secrets**。numpy 2.5 的
`numpy/random/bit_generator` 要 `secrets.randbits`，于是 pandas → datasets → kev.data 整条导入链
当场炸成 `ImportError: cannot import name randbits`，与本文件毫无关系却极难定位。
tests/test_conventions.py 的 stdlib-shadowing 规则钉住了这件事。
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path

from kev.console import paths

DEFAULT_PATH = Path(os.environ.get(
    "KEV_DISTILL_SECRETS", paths.ROOT / "data" / "console" / "secrets" / "distill.json"))


def _path() -> Path:
    return DEFAULT_PATH


def load() -> dict:
    p = _path()
    if not p.is_file():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def put(provider_id: str, entry: dict) -> None:
    p = _path()
    p.parent.mkdir(parents=True, exist_ok=True)
    data = load()
    data[provider_id] = entry
    _atomic_write(p, data)


def remove(provider_id: str) -> None:
    p = _path()
    if not p.is_file():
        return
    data = load()
    if provider_id in data:
        del data[provider_id]
        _atomic_write(p, data)


def mask(key: str) -> tuple[str, str]:
    return (hashlib.sha256(key.encode("utf-8")).hexdigest(),
            f"{key[:3]}...{key[-4:]}")


def _atomic_write(p: Path, data: dict) -> None:
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, p)
    try:
        os.chmod(p, 0o600)
    except OSError:
        pass
