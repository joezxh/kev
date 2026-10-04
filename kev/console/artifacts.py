"""产物 id ↔ 路径的唯一真相源，以及作业完成后的产物注册。

为什么必须有这个模块：产物 id（`dataset:cv/summary`、`run:x`）是编排层各阶段的通用契约，
闸门靠它找到产物文件。早期版本把路径推断散落在 app.py 里，于是 split 忘了注册
summary.json、precheck 忘了注册自己的报告，G1/G2/G3 永远失败、train 永远无法提交。
现在阶段处理器与注册逻辑都调 resolve()，只有这一处决定 id 到路径的映射。

meta 只放「UI 直接要用的少量字段」，不复制 report.json 的全部内容 —— report.json
仍然是唯一真相源，这里只是给列表页和闸门用的摘要。
"""
from __future__ import annotations

from pathlib import Path

from kev.suite import read_json

from . import paths

PERSIST = ("success", "start")
SPLITS = ("train", "calibration", "development")
DATA_DIR = "data"
CONSOLE_LOG_DIR = f"{DATA_DIR}/console"

# stage -> 该阶段产出的血缘关系名
RELATION = {
    "generate": "generated_from", "distill": "generated_from", "goldset": "sampled_from",
    "split": "split_into", "precheck": "checked_from", "train": "trained_on",
    "benchmark": "evaluated_on", "baseline": "evaluated_on", "compare": "compared_from",
    "calibrate": "calibrated_from", "image": "built_from", "deploy": "deployed_as",
    "smoke": "smoked",
}


def resolve(artifact_id: str) -> str:
    """artifact id -> 仓库相对路径。endpoint 返回 URL，image 返回 docker tag。"""
    kind, _, name = artifact_id.partition(":")
    if kind == "dataset":
        tail = name.rpartition("/")[2]
        if tail == "summary":
            return f"{DATA_DIR}/{name}.json"
        if tail in SPLITS:
            return f"{DATA_DIR}/{name}.jsonl"
        return f"{DATA_DIR}/{name}"                     # 数据集目录本身
    if kind == "precheck":
        return f"{CONSOLE_LOG_DIR}/precheck-" + name.replace("/", "-") + ".json"
    if kind == "run":
        return f"runs/{name}"
    if kind == "eval":
        return f"runs/{name}-eval"
    if kind == "comparison":
        return f"runs/{name}-compare"
    if kind == "calibration":
        return f"runs/{name}-eval/calibration.json"
    if kind == "image":
        return name
    if kind == "endpoint":
        return f"http://127.0.0.1:{name}"
    raise ValueError(f"未知产物类型 {kind!r}（id={artifact_id!r}）")


def _load(relative: str):
    """读产物文件；不存在或坏掉都返回 None（闸门据此判失败，而不是崩）。"""
    target = Path(paths.ROOT) / relative
    if not target.is_file():
        return None
    try:
        return read_json(target)
    except (OSError, ValueError):
        return None


def summarize(artifact_id: str, path: str) -> dict:
    """产物的小份摘要，给列表页与闸门用。文件不在就返回空 dict。"""
    kind = artifact_id.partition(":")[0]
    if kind in {"dataset", "precheck"}:
        payload = _load(path)
        # partitions 是整份分区摘要（几十项），不属于「UI 直接要用的少量字段」，不抄进 meta。
        return {} if payload is None else {
            key: payload[key] for key in ("records", "invalid_lines", "over_limit")
            if key in payload
        }
    if kind == "comparison":
        payload = _load(path)
        if payload is None:
            return {}
        paired = (payload.get("paired") or {}).get("acc") or {}
        return {"ci95": paired.get("ci95"), "delta": paired.get("macro_acc_delta")}
    if kind == "calibration":
        payload = _load(path)
        if payload is None:
            return {}
        return {"workload_temperature": payload.get("workload_temperature"),
                "shipped_temperature": payload.get("shipped_temperature")}
    if kind == "eval":
        payload = _load(f"{path}/report.json")
        if payload is None:
            return {}
        clean = payload.get("clean") or {}
        return {key: clean.get(key) for key in
                ("acc", "ece", "brier", "aurc", "mean_conf", "coverage_at_5pct_error")}
    if kind == "run":
        payload = _load(f"{path}/training_config.json")
        return {} if payload is None else {"init_source": (payload.get("init_source") or {}).get("init_from")}
    return {}


def register(store, job: dict) -> list[str]:
    """把作业的 artifacts_out 注册为产物，并写 artifacts_in -> artifacts_out 的血缘。

    可重复调用：重试会产生第二个作业写同一个产物，put_artifact 是 upsert、add_lineage 是
    INSERT OR IGNORE，所以这里不需要额外的去重逻辑。
    """
    relation = RELATION.get(job["kind"], "produced_by")
    registered = []
    for artifact_id in job["artifacts_out"]:
        relative = resolve(artifact_id)
        meta = summarize(artifact_id, relative)
        size = None
        target = Path(paths.ROOT) / relative
        if target.is_file():
            size = target.stat().st_size
        store.put_artifact(kind=artifact_id.partition(":")[0], name=artifact_id.partition(":")[2],
                           path=relative, meta=meta, bytes_=size)
        for parent in job["artifacts_in"]:
            store.add_lineage(parent, artifact_id, relation, job_id=job["id"])
        registered.append(artifact_id)
    return registered
