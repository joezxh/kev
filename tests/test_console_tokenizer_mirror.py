"""kev.console.tokenizer_mirror: Hub 不通时 precheck 的 tokenizer 来源。

全部用例离线：`_open`（ModelScope 的两个端点）与 `snapshot_download`（HF 回落）都被桩掉，
所以 CI 上没有网络依赖；桩里顺带钉住了 URL 形状与 Size/Sha256 校验。

Run: uv run python -m pytest tests/test_console_tokenizer_mirror.py -q
"""
from __future__ import annotations

import hashlib
import io
import json

import pytest

from kev.console import tokenizer_mirror

MODEL = "jaredpalmer/kev-0.8b"
FILES = {"tokenizer.json": b'{"model": {}}', "tokenizer_config.json": b'{"tokenizer_class": "Qwen2Tokenizer"}'}
MANIFEST = {"Data": {"Files": [
    {"Path": name, "Type": "blob", "Size": len(blob),
     "Sha256": hashlib.sha256(blob).hexdigest()} for name, blob in FILES.items()
] + [{"Path": "adapter_model.safetensors", "Type": "blob", "Size": 8, "Sha256": "00" * 32},
     {"Path": "README.md", "Type": "blob", "Size": 3, "Sha256": "00" * 32}]}}


class _Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


def _fake_open(manifest=None, files=None):
    """A stand-in for _open: the file listing comes from `manifest`, the blobs from `files`."""
    manifest = MANIFEST if manifest is None else manifest
    files = FILES if files is None else files
    requested = []

    def open_(url, timeout):
        requested.append(url)
        if "/repo/files" in url:
            return _Response(json.dumps(manifest).encode("utf-8"))
        name = url.split("FilePath=")[1].split("&")[0]
        return _Response(files[name])

    open_.requested = requested
    return open_


def test_mirror_dir_names_the_owner_and_the_repo():
    """`owner/name` -> `owner__name`, under the console's data dir (gitignored)."""
    assert tokenizer_mirror.mirror_dir(MODEL).name == "jaredpalmer__kev-0.8b"
    assert tokenizer_mirror.mirror_dir(MODEL).parent == tokenizer_mirror.paths.TOKENIZER_MIRROR
    assert str(tokenizer_mirror.paths.TOKENIZER_MIRROR).replace("\\", "/").endswith("data/console/tokenizers")


def test_from_modelscope_pulls_only_tokenizer_files_and_verifies_them(monkeypatch, tmp_path):
    """Weights and docs are left alone; every blob is checked against the manifest's Size + Sha256."""
    open_ = _fake_open()
    monkeypatch.setattr(tokenizer_mirror, "_open", open_)

    written = tokenizer_mirror.from_modelscope(MODEL, tmp_path)

    assert sorted(written) == sorted(FILES)
    assert {p.name for p in tmp_path.iterdir()} == set(FILES)
    assert (tmp_path / "tokenizer.json").read_bytes() == FILES["tokenizer.json"]
    assert all("FilePath=tokenizer" in url or "FilePath=config" in url for url in open_.requested[1:])


def test_from_modelscope_rejects_a_blob_the_manifest_disagrees_with(monkeypatch, tmp_path):
    """A mirror that serves different bytes is not the Hub's file: refuse rather than mirror it."""
    monkeypatch.setattr(tokenizer_mirror, "_open", _fake_open(files={"tokenizer.json": b"tampered",
                                                                    "tokenizer_config.json": FILES["tokenizer_config.json"]}))
    with pytest.raises(ValueError, match="sha256|bytes"):
        tokenizer_mirror.from_modelscope(MODEL, tmp_path)


def test_fetch_is_idempotent(monkeypatch, tmp_path):
    """A mirror already holding a tokenizer is reused; no request goes out."""
    dest = tokenizer_mirror.mirror_dir(MODEL, tmp_path)
    dest.mkdir(parents=True)
    (dest / "tokenizer.json").write_bytes(FILES["tokenizer.json"])

    def refuse(*args, **kwargs):
        raise AssertionError("fetch must not touch the network once the mirror exists")

    monkeypatch.setattr(tokenizer_mirror, "from_modelscope", refuse)
    monkeypatch.setattr(tokenizer_mirror, "from_hub", refuse)
    assert tokenizer_mirror.fetch(MODEL, root=tmp_path) == dest


def test_fetch_falls_through_to_the_next_source(monkeypatch, tmp_path):
    """ModelScope first, the Hub mirror second; one source being down is not an error."""
    def offline_modelscope(model, dest, timeout=180.0):
        raise OSError("connection reset")

    def hub(model, dest, allow_patterns=None):
        (dest / "tokenizer.json").parent.mkdir(parents=True, exist_ok=True)
        (dest / "tokenizer.json").write_bytes(FILES["tokenizer.json"])
        return ["tokenizer.json"]

    monkeypatch.setattr(tokenizer_mirror, "from_modelscope", offline_modelscope)
    monkeypatch.setattr(tokenizer_mirror, "from_hub", hub)

    dest = tokenizer_mirror.fetch(MODEL, root=tmp_path)
    assert (dest / "tokenizer.json").read_bytes() == FILES["tokenizer.json"]


def test_fetch_reports_both_sources_and_gives_up(monkeypatch, tmp_path):
    def dead(*args, **kwargs):
        raise OSError("unreachable")

    monkeypatch.setattr(tokenizer_mirror, "from_modelscope", dead)
    monkeypatch.setattr(tokenizer_mirror, "from_hub", dead)
    assert tokenizer_mirror.fetch(MODEL, root=tmp_path) is None


def test_ensure_source_prefers_a_directory_it_already_has(monkeypatch, tmp_path):
    """`--init-from` pointed at a local path is used as it stands (no mirroring, no download)."""
    def refuse(*args, **kwargs):
        raise AssertionError("a local directory must be used as it stands")

    monkeypatch.setattr(tokenizer_mirror, "fetch", refuse)
    assert tokenizer_mirror.ensure_source(str(tmp_path), root=tmp_path / "mirror") == str(tmp_path)


def test_ensure_source_mirrors_a_hub_id_once(monkeypatch, tmp_path):
    """A Hub id resolves to the mirror directory, and only fetches when the mirror is empty."""
    calls = []

    def fetch(model, sources=None, timeout=None, force=False, root=None):
        calls.append(model)
        dest = tokenizer_mirror.mirror_dir(model, root)
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "tokenizer.json").write_bytes(FILES["tokenizer.json"])
        return dest

    monkeypatch.setattr(tokenizer_mirror, "fetch", fetch)
    first = tokenizer_mirror.ensure_source(MODEL, root=tmp_path)
    second = tokenizer_mirror.ensure_source(MODEL, root=tmp_path)

    assert first == second == str(tokenizer_mirror.mirror_dir(MODEL, tmp_path))
    assert calls == [MODEL]      # the second call was served by the mirror


def test_ensure_source_hands_the_hub_id_back_when_nothing_works(monkeypatch, tmp_path):
    """Mirroring failed: return the id unchanged so transformers raises its own, honest error."""
    monkeypatch.setattr(tokenizer_mirror, "fetch", lambda *args, **kwargs: None)
    assert tokenizer_mirror.ensure_source(MODEL, root=tmp_path) == MODEL


def test_precheck_scores_through_the_mirror_and_records_it(monkeypatch, tmp_path):
    """precheck asks the mirror for a tokenizer source and writes down which one it used."""
    from kev.console import precheck

    record = {"state": "客户要求退款，订单已发货。", "questions": {
        "team": {"type": "choice", "instructions": "交给哪个团队？",
                 "criteria": {"billing": "账单团队", "support": "客服团队"}, "label": "billing"},
        "urgent": {"type": "noul", "instructions": "是否加急？", "label": True}}}
    split = tmp_path / "cv"
    split.mkdir()
    (split / "train.jsonl").write_text(json.dumps(record, ensure_ascii=False) + "\n", encoding="utf-8")
    out = tmp_path / "precheck.json"
    mirror = tmp_path / "mirror"
    mirror.mkdir()
    (mirror / "tokenizer.json").write_bytes(FILES["tokenizer.json"])

    loaded = []
    monkeypatch.setattr(precheck.tokenizer_mirror, "ensure_source",
                        lambda model, **kwargs: str(mirror) if model == MODEL else model)
    monkeypatch.setattr(precheck, "load_tokenizer", lambda name, revision=None: loaded.append(name) or object())
    monkeypatch.setattr(precheck, "fits", lambda *args, **kwargs: True)

    assert precheck.run(["--data", str(split), "--init-from", MODEL, "--out", str(out)]) == 0
    assert loaded == [str(mirror)]
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["init_from"] == MODEL
    assert report["tokenizer_source"] == str(mirror)
    assert (report["records"], report["over_limit"]) == (1, 0)
