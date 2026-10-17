"""产物 id ↔ 路径的唯一真相源，以及作业完成后的产物注册。

为什么必须有这个模块：产物 id（`dataset:cv/summary`、`run:x`）是编排层各阶段的通用契约，
闸门靠它找到产物文件。早期版本把路径推断散落在 app.py 里，于是 split 忘了注册
summary.json、precheck 忘了注册自己的报告，G1/G2/G3 永远失败、train 永远无法提交。
现在阶段处理器与注册逻辑都调 resolve()，只有这一处决定 id 到路径的映射。

meta 只放「UI 直接要用的少量字段」，不复制 report.json 的全部内容 —— report.json
仍然是唯一真相源，这里只是给列表页和闸门用的摘要。
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from kev.suite import read_json

from . import paths

PERSIST = ("success", "start")
SPLITS = ("train", "calibration", "development")
# 仓库相对前缀的唯一归属是 paths.py（DATA_REL / RUNS_REL / CONSOLE_REL），这里只做引用：
# 同一个 "data/" / "runs/" 字面量不许在两个模块各写一遍。绝对路径则一律现取 paths.ROOT，
# 测试要能 monkeypatch 它。
DATA_DIR = paths.DATA_REL
RUNS_DIR = paths.RUNS_REL
CONSOLE_LOG_DIR = paths.CONSOLE_REL

# stage -> 该阶段产出的血缘关系名
RELATION = {
    "generate": "generated_from", "distill": "generated_from", "goldset": "sampled_from",
    "split": "split_into", "precheck": "checked_from", "train": "trained_on",
    "benchmark": "evaluated_on", "baseline": "evaluated_on", "compare": "compared_from",
    "calibrate": "calibrated_from", "image": "built_from", "deploy": "deployed_as",
    "smoke": "smoked", "plan_size": "planned_for", "modal": "deployed_as",
    "make_examples": "sampled_from",
    # materialize 把成员产物「组成」bundle（PR C）：父 = 成员源产物，子 = bundle 产物。
    "materialize": "composed_of",
}


def resolve(artifact_id: str) -> str:
    """artifact id -> 仓库相对路径。endpoint 返回 URL，image 返回 docker tag。"""
    kind, _, name = artifact_id.partition(":")
    if kind == "dataset":
        tail = name.rpartition("/")[2]
        if tail == "summary":
            return f"{DATA_DIR}/{name}.json"
        if tail in SPLITS or tail == "examples":
            return f"{DATA_DIR}/{name}.jsonl"
        # generate / distill 的原始池是 .jsonl 文件；文件存在则指向文件本身
        # （注册时才有 bytes/meta），否则保留目录语义（兼容历史产物 id）。
        if (Path(paths.ROOT) / DATA_DIR / f"{name}.jsonl").is_file():
            return f"{DATA_DIR}/{name}.jsonl"
        return f"{DATA_DIR}/{name}"                     # 数据集目录本身
    if kind == "bundle":
        # bundle:<slug>/<name> -> data/<slug>/bundles/<name>.jsonl（D4：bundle 是不可变产物）。
        slug, _, bundle_name = name.partition("/")
        return f"{DATA_DIR}/{slug}/bundles/{bundle_name}.jsonl"
    if kind == "precheck":
        return f"{CONSOLE_LOG_DIR}/precheck-" + name.replace("/", "-") + ".json"
    if kind == "plan":
        return f"{CONSOLE_LOG_DIR}/plan-" + name.replace("/", "-") + ".json"
    if kind == "run":
        return f"{RUNS_DIR}/{name}"
    if kind == "eval":
        return f"{RUNS_DIR}/{name}-eval"
    if kind == "comparison":
        return f"{RUNS_DIR}/{name}-compare"
    if kind == "regression":
        return f"{RUNS_DIR}/{name}-compare-public"
    if kind == "calibration":
        return f"{RUNS_DIR}/{name}-eval/calibration.json"
    if kind == "smoke":
        return f"{RUNS_DIR}/{name}-smoke.json"           # 冒烟报告（deploy.smoke 阶段）
    if kind == "image":
        return name
    if kind == "endpoint":
        if name.startswith("modal-"):
            # Modal 端点不在本地端口上；URL 由 Modal 控制台按 app 名给出。
            return f"modal app '{name[len('modal-')]}'（在线状态见 Modal 控制台）"
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
    """产物的小份摘要，给列表页与闸门用。

    各分支的 meta 形状本来就不同，但「读不到文件」这一个意思必须统一：一律返回空 dict，
    不返回「有 meta 但字段全 null」的半成品 —— 否则 UI 分不清「没数据」与「字段缺失」。
    """
    kind = artifact_id.partition(":")[0]
    if kind in {"dataset", "precheck"}:
        payload = _load(path)
        # partitions 是整份分区摘要（几十项），不属于「UI 直接要用的少量字段」，不抄进 meta。
        return {} if payload is None else {
            key: payload[key] for key in ("records", "invalid_lines", "over_limit")
            if key in payload
        }
    if kind == "plan":
        payload = _load(path)
        return {} if payload is None else {"total_records": payload.get("total_records")}
    if kind == "bundle":
        # bundle 的 meta 走旁文件 manifest（记录数 / 复核比），不复制 jsonl 内容。
        payload = _load(path[:-6] + ".manifest.json" if path.endswith(".jsonl") else
                        f"{path}.manifest.json")
        return {} if payload is None else {
            key: payload[key] for key in ("records", "review_ratio") if key in payload}
    if kind in {"comparison", "regression"}:
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
    if kind == "endpoint" and artifact_id.partition(":")[2].startswith("modal-"):
        # Modal 端点：本机探不了活，把部署参数带出来供部署页展示。
        return {"run": artifact_id.partition(":")[2][len("modal-"):], "modal": True}
    return {}


def register(store, job: dict) -> list[str]:
    """把作业的 artifacts_out 注册为产物，并写 artifacts_in -> artifacts_out 的血缘。

    全程一个事务：崩在血缘中途只会留下「什么都没有」，不会留下「产物已登记、血缘残缺」的半成品。
    Task 3 的 on_finished 是 except Exception: pass，半成品会被完全静默 —— 作业显示 succeeded，
    产物列表里却有一条没有来路的产物。N 次 commit 也因此降为 1 次。

    单文件产物在同事务里额外登记一条 artifact_versions（不可变版本，登记即算 sha256/records）；
    目录类产物或未落盘的文件不写版本（历史无版本读列表返回空，PR B Review Focus）。

    可重复调用：重试会产生第二个作业写同一个产物，put_artifact 是 upsert、add_lineage 是
    INSERT OR IGNORE，所以这里不需要额外的去重逻辑；版本则每次注册递增一个 seq。
    """
    relation = RELATION.get(job["kind"], "produced_by")
    registered = []
    with store.tx():
        for artifact_id in job["artifacts_out"]:
            relative = resolve(artifact_id)
            meta = summarize(artifact_id, relative)
            size = None
            target = Path(paths.ROOT) / relative
            if target.is_file():
                size = target.stat().st_size
            store.put_artifact(kind=artifact_id.partition(":")[0], name=artifact_id.partition(":")[2],
                               path=relative, meta=meta, bytes_=size, commit=False)
            if target.is_file():
                sha256, records = _hash_and_count(target)
                store.record_artifact_version(artifact_id=artifact_id, job_id=job["id"],
                                              path=relative, sha256=sha256, records=records,
                                              bytes=size, meta=meta)
            for parent in job["artifacts_in"]:
                store.add_lineage(parent, artifact_id, relation, job_id=job["id"], commit=False)
            registered.append(artifact_id)
    return registered


def _hash_and_count(target: Path) -> tuple[str, int | None]:
    """单文件产物的 (sha256, records)：sha256 是整份字节的摘要，records 仅对 .jsonl 逐非空行计数。"""
    data = target.read_bytes()
    sha256 = hashlib.sha256(data).hexdigest()
    records = None
    if target.suffix == ".jsonl":
        records = sum(1 for line in data.decode("utf-8", "replace").splitlines() if line.strip())
    return sha256, records


def integrity(version: dict) -> str:
    """读时复核登记版本指向的文件：未改=ok、内容变了=drift、文件没了=missing（PR B V3 三态）。"""
    target = Path(paths.ROOT) / version["path"]
    if not target.is_file():
        return "missing"
    current = hashlib.sha256(target.read_bytes()).hexdigest()
    return "ok" if current == version["sha256"] else "drift"


def _record_fingerprint(record) -> str:
    """逐记录定长指纹 —— 复用 split_data.record_fingerprint（与 dedupe 判重同一规范化，D7），绝不复制实现。"""
    paths.ensure_generators_on_path()
    import split_data
    return split_data.record_fingerprint(record)


def preview_records(version: dict, *, offset=0, limit=100, q="", verdict="") -> dict:
    """分页读取版本快照指向的 JSONL，逐行带 1-based 行号与定长指纹；文件缺失返回空页。

    q 是对整行原文的大小写无关子串过滤；verdict 命中任一问题的 label（PR D 落覆盖层后可换成按决定过滤）。
    过滤后才分页，所以 total 是「匹配行数」而非文件行数。limit 上限 500（同 read_events）。
    """
    limit = max(0, min(int(limit), 500))
    target = Path(paths.ROOT) / version["path"]
    if not target.is_file():
        return {"version_id": version["id"], "total": 0, "records": []}
    needle = (q or "").casefold()
    matched = []
    for line_no, line in enumerate((ln for ln in target.read_text(encoding="utf-8").splitlines() if ln.strip()), 1):
        if needle and needle not in line.casefold():
            continue
        try:
            record = json.loads(line)
        except ValueError:
            continue
        if verdict and not _verdict_matches(record, verdict):
            continue
        matched.append({"line_no": line_no, "fingerprint": _record_fingerprint(record), "record": record})
    return {"version_id": version["id"], "total": len(matched),
            "records": matched[offset:offset + limit]}


def _verdict_matches(record, verdict: str) -> bool:
    """记录的任一问题 label 是否等于 verdict（choice/score 用字符串值，noul 用 true/false）。"""
    questions = record.get("questions") if isinstance(record, dict) else None
    if not isinstance(questions, dict):
        return False
    for q in questions.values():
        if isinstance(q, dict) and "label" in q:
            label = q["label"]
            key = str(bool(label)).lower() if isinstance(label, bool) else str(label)
            if key == str(verdict):
                return True
    return False
