"""产物 id ↔ 路径的映射，以及作业完成后的产物注册与血缘。

为什么单独一个模块（计划修正）：产物 id 是编排层各阶段的通用契约，闸门要靠它找到产物文件。
早期版本把路径推断散落在 app.py 的 _gate_products 里，导致 split 忘了注册 summary.json、
precheck 忘了注册自己的报告，于是 G1/G2/G3 永远失败、train 永远无法提交。
resolve() 是这件事的唯一真相源，阶段处理器与注册逻辑都调它。

Run: uv run python -m pytest tests/test_console_artifacts.py -q
"""
import pytest

from kev.console import artifacts
from kev.console.db import Store


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "db.sqlite")


@pytest.mark.parametrize("artifact_id,expected", [
    ("dataset:cv", "data/cv"),
    ("dataset:cv/train", "data/cv/train.jsonl"),
    ("dataset:cv/calibration", "data/cv/calibration.jsonl"),
    ("dataset:cv/development", "data/cv/development.jsonl"),
    ("dataset:cv/summary", "data/cv/summary.json"),            # G2/G3 读的就是它
    ("precheck:cv/train", "data/console/precheck-cv-train.json"),   # G1 读的就是它
    ("run:cv-8b-lora-v1", "runs/cv-8b-lora-v1"),
    ("eval:cv-8b-lora-v1", "runs/cv-8b-lora-v1-eval"),
    ("comparison:cv-8b-lora-v1", "runs/cv-8b-lora-v1-compare"),
    ("calibration:cv-8b-lora-v1", "runs/cv-8b-lora-v1-eval/calibration.json"),
    ("image:kev-cv-8b-lora-v1", "kev-cv-8b-lora-v1"),
    ("endpoint:8008", "http://127.0.0.1:8008"),
])
def test_resolve_maps_every_kind(artifact_id, expected):
    assert artifacts.resolve(artifact_id) == expected


def test_resolve_rejects_an_unknown_kind():
    with pytest.raises(ValueError, match="未知产物类型"):
        artifacts.resolve("widget:thing")


def test_summarize_reads_a_split_summary(tmp_path, monkeypatch):
    monkeypatch.setattr(artifacts.paths, "ROOT", tmp_path)
    (tmp_path / "data/cv").mkdir(parents=True)
    text = '{"records": 787, "invalid_lines": 0, "partitions": {}}'
    (tmp_path / "data/cv/summary.json").write_text(text, encoding="utf-8")
    assert artifacts.summarize("dataset:cv/summary", artifacts.resolve("dataset:cv/summary")) == {
        "records": 787, "invalid_lines": 0}


def test_summarize_pulls_the_paired_ci_out_of_a_comparison(tmp_path, monkeypatch):
    monkeypatch.setattr(artifacts.paths, "ROOT", tmp_path)
    (tmp_path / "runs/x-compare").mkdir(parents=True)
    text = '{"paired": {"acc": {"ci95": [0.023, 0.097], "macro_acc_delta": 0.05}}, "clean": {}}'
    (tmp_path / "runs/x-compare/comparison.json").write_text(text, encoding="utf-8")
    meta = artifacts.summarize("comparison:x", "runs/x-compare/comparison.json")
    assert meta["ci95"] == [0.023, 0.097]
    assert meta["delta"] == 0.05


def test_summarize_is_empty_when_the_file_is_absent(tmp_path, monkeypatch):
    monkeypatch.setattr(artifacts.paths, "ROOT", tmp_path)
    assert artifacts.summarize("run:missing", "runs/missing") == {}


def test_register_creates_out_artifacts_and_in_to_out_lineage(store):
    job_id = store.create_job(
        kind="split", stage="data", scenario="critical-value", title="t",
        request={}, argv=["x"], env_overlay={}, cwd=".", log_path="l.log",
        artifacts_in=["dataset:cv"],
        artifacts_out=["dataset:cv/train", "dataset:cv/calibration",
                       "dataset:cv/development", "dataset:cv/summary"])
    registered = artifacts.register(store, store.get_job(job_id))
    assert set(registered) == {"dataset:cv/train", "dataset:cv/calibration",
                               "dataset:cv/development", "dataset:cv/summary"}
    assert store.get_artifact("dataset:cv/summary")["path"] == "data/cv/summary.json"
    edges = {(edge["relation"], edge["child"]) for edge in store.lineage_of("dataset:cv")}
    assert ("split_into", "dataset:cv/train") in edges
    assert ("split_into", "dataset:cv/summary") in edges


def test_register_is_idempotent_across_a_retry(store):
    """重试会产生第二个作业写同一个产物；register 必须能重复跑而不炸。"""
    for attempt in (1, 2):
        job_id = store.create_job(
            kind="split", stage="data", scenario="critical-value", title=f"t{attempt}",
            request={}, argv=["x"], env_overlay={}, cwd=".", log_path="l.log",
            artifacts_in=[], artifacts_out=["dataset:cv/summary"])
        artifacts.register(store, store.get_job(job_id))
    assert len(store.list_artifacts("dataset")) == 1
