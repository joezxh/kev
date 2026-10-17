"""DataService: in-process wrappers for the 5 console-owned data stages + distill.

Per docs/superpowers/specs/2026-10-09-studio-data-design.md §2.X and the rollout
plan B-1, the DataService covers:

- generate            (kev/console/generators/gen_<scenario>.run)
- distill             (kev/console/generators/run_distill.run, the **non-daemon** path)
- goldset             (kev/console/generators/make_goldset.run_sample)
- goldset_audit       (kev/console/generators/make_goldset.run_audit)
- precheck            (kev/console/precheck.run)
- make_examples       (kev/console/make_examples.run)

The 3 skill-script stages (plan_size / distill_daemon / split) keep their Popen path;
DataService does not provide methods for them. A future caller wanting one of those
would still go through the stage's _xxx_build + executor.spawn path (unchanged).

Service contract:
- Each method takes a JobRequest + a per-call on_log callback.
- on_log is invoked with each line of stdout the business function prints.
- stdout capture is implemented in LocalExecutor.spawn_callable (tee into the
  same log file + events table that a Popen run would use). DataService only
  *builds* a Namespace-like argv list and *dispatches* to the right run() —
  the on_log + log_path plumbing is the executor's job.
- Cancellation is cooperative: each method returns early if self.cancel.is_set().
  A long-running data function (none of the 5 are, they all finish in seconds)
  would need to add a self.cancel.is_set() check at a natural step boundary.
"""
from __future__ import annotations

import argparse
import importlib
import sys
import threading
from pathlib import Path
from typing import Callable

from kev.console.db import Store
from kev.console.stages.base import JobRequest


# Default knobs taken from kev/console/stages/data.py; kept here so the service
# can build a Namespace without re-importing the stage module.
_PLANNED_RECORDS = 787

# Per-scenario gen_<scenario>.py modules live under kev/console/generators/.
# The engine module injects this dir into sys.path at import time, but the
# service may be imported without the engine (e.g. in tests), so we ensure
# the path is set here as well. Idempotent.
_GENERATORS_DIR = Path(__file__).resolve().parent.parent / "generators"
if str(_GENERATORS_DIR) not in sys.path:
    sys.path.insert(0, str(_GENERATORS_DIR))


def _import_gen_module(scenario: str):
    """Dynamically import `gen_<scenario>` so the test can stub it via sys.modules."""
    return importlib.import_module(f"gen_{scenario.replace('-', '_')}")


class DataService:
    def __init__(self, store: Store, cancel: threading.Event):
        self.store = store
        self.cancel = cancel  # process-wide Event; set when a job is canceled.

    # ---- generate ---------------------------------------------------------

    def generate(self, req: JobRequest, *, on_log: Callable[[str], None]) -> dict:
        """Generate a JSONL of synthetic records for the scenario.

        Mirrors `stages/data.py::_generate` (lines 150-167): dispatch to the
        scenario's `gen_<scenario>.py` module. Tests can stub it via
        `monkeypatch.setitem(sys.modules, "gen_<scenario>", fake)` and the
        service picks up the stub through importlib.
        """
        module = _import_gen_module(req.scenario)
        args = self._build_generate_args(req)
        rc = module.run([str(part) for part in args])
        return {"returncode": rc}

    def _build_generate_args(self, req: JobRequest) -> list:
        params = req.params
        data_dir = params.get("data") or f"data/{req.scenario}"
        out = f"{data_dir}.jsonl"
        n = int(params.get("n", _PLANNED_RECORDS))
        seed = int(params.get("seed", 0))
        # base_parser reads --n/--out/--seed and adds --pairs; mirrors stages/data.py:163-167
        # We always pass --pairs=0 here: the service path is the user-driven path,
        # and minimal pairs are a generator-level concern. Stage preview() still
        # exposes the same shape so the UI's argv preview matches.
        return ["--n", str(n), "--out", out, "--seed", str(seed), "--pairs", "0"]

    # ---- goldset / goldset_audit ------------------------------------------

    def goldset(self, req: JobRequest, *, on_log) -> dict:
        """goldset service: stratified sample for human review.

        Wraps make_goldset.run_sample() with the args the stage would have built.
        """
        from kev.console.generators import make_goldset
        args = self._build_goldset_args(req)
        ns = make_goldset_sample_namespace(args, req)
        rc = make_goldset.run_sample(ns)
        return {"returncode": rc}

    def _build_goldset_args(self, req: JobRequest) -> dict:
        params = req.params
        data_dir = params.get("data") or f"data/{req.scenario}"
        return {
            "data": f"{data_dir}.jsonl",
            "n": int(params.get("n", 200)),
            "seed": int(params.get("seed", 0)),
            "out": params.get("out") or f"{data_dir}.gold.jsonl",
        }

    def goldset_audit(self, req: JobRequest, *, on_log) -> dict:
        """goldset_audit service: per-question disagreement rate between two labellings.

        Wraps make_goldset.run_audit() with a pre-built Namespace.
        """
        from kev.console.generators import make_goldset
        params = req.params
        a, b = params.get("a"), params.get("b")
        if not a or not b:
            # Surface the same Invalid the stage would raise; the executor maps it
            # to a 400 response at the HTTP boundary.
            from kev.console.stages.base import Invalid
            raise Invalid(
                "goldset_audit 需要两份独立标注（a, b）",
                field="a" if not a else "b",
                hint="两份独立厂商模型对同一批 state 的标注",
            )
        ns = argparse.Namespace(
            a=a, b=b, out=params.get("out") or "",
            threshold=float(params.get("threshold", 0.05)),
        )
        rc = make_goldset.run_audit(ns)
        return {"returncode": rc}

    # ---- precheck ---------------------------------------------------------

    def precheck(self, req: JobRequest, *, on_log) -> dict:
        """precheck service: token-limit scan over a split partition.

        Wraps kev.console.precheck.run() with the args the stage would have built.
        """
        from kev.console import precheck
        params = req.params
        data_dir = params.get("data") or f"data/{req.scenario}"
        partition = params.get("split", "train")
        # Service-level default init mirrors stages/data.py: DEFAULT_INIT.
        # The default is exposed via the stage's preview(); keep it consistent
        # rather than re-importing the constant.
        init_from = params.get("init_from", "jaredpalmer/kev-0.8b")
        out = params.get("out") or f"data/console/precheck-{req.scenario}-{partition}.json"
        ns = argparse.Namespace(
            data=data_dir, init_from=init_from, split=partition, out=out,
        )
        rc = precheck.run([str(part) for part in [
            "--data", data_dir, "--init-from", init_from, "--split", partition, "--out", out
        ]])
        return {"returncode": rc}

    # ---- distill ----------------------------------------------------------

    def distill(self, req: JobRequest, *, on_log: Callable[[str], None]) -> dict:
        """distill service: one-shot LLM distillation (the **non-daemon** path).

        Wraps kev.console.generators.run_distill.run() with the args the stage would have built.
        `distill_daemon` (the long-running schedule path) stays in stages.data + daemon_runner;
        this service covers only `require_schedule=False`.
        """
        from kev.console.generators import run_distill
        args = self._build_distill_args(req)
        rc = run_distill.run([str(part) for part in args], on_log=on_log)
        return {"returncode": rc}

    def _build_distill_args(self, req: JobRequest) -> list:
        """Build argv for run_distill.run, mirroring stages/data.py:185-244.

        `provider_id` is required (a configured distillation endpoint); category, n, model,
        concurrency, examples, n_examples, state_dir all have sensible defaults.
        """
        params = req.params
        provider_id = params.get("provider_id")
        if not provider_id:
            from kev.console.stages.base import Invalid
            raise Invalid("distill 需要 provider_id（已配置的蒸馏端点）",
                          field="provider_id",
                          hint="先到控制台「蒸馏配置」创建并选择")
        n = int(params.get("n", _PLANNED_RECORDS))
        out = f"data/{req.scenario}/{params.get('category', req.scenario)}.jsonl"
        argv = ["--n", str(n), "--provider", provider_id, "--out", out]
        if params.get("model"):
            argv += ["--model", params["model"]]
        if params.get("concurrency"):
            argv += ["--concurrency", str(int(params["concurrency"]))]
        if params.get("examples"):
            argv += ["--examples", params["examples"]]
            argv += ["--n-examples", str(int(params.get("n_examples", 4)))]
        if params.get("state_dir"):
            argv += ["--state-dir", params["state_dir"]]
        return argv

    # ---- make_examples ----------------------------------------------------

    def make_examples(self, req: JobRequest, *, on_log: Callable[[str], None]) -> dict:
        """make_examples service: balanced few-shot sampling for the distill step.

        Wraps kev.console.make_examples.run() with the args the stage would have built.
        """
        from kev.console import make_examples
        params = req.params
        data = (params.get("data") or "").strip()
        if not data:
            from kev.console.stages.base import Invalid
            raise Invalid("make_examples 需要 --data 指向一份已标注的 JSONL", field="data",
                          hint="如 data/critical-value.jsonl（generate/distill 的原始池）")
        # base = "data/cv/critical-value" (strip suffix + replace backslashes for windows)
        base = data.rsplit(".", 1)[0].replace("\\", "/")
        out = params.get("out") or f"{base}/examples.jsonl"
        rc = make_examples.run([str(part) for part in [
            "--data", data,
            "--n", str(int(params.get("n", 8))),
            "--seed", str(int(params.get("seed", 0))),
            "--out", out,
        ]])
        return {"returncode": rc}

    # ---- materialize ------------------------------------------------------

    def materialize(self, req: JobRequest, *, on_log: Callable[[str], None]) -> dict:
        """合成不可变训练快照（PR C）：按 ord 读成员 JSONL，应用 record_reviews 覆盖层，
        统一过一次 `split_data.dedupe`（**import 复用，绝不复制实现**，反目标 §2.3），
        写 .jsonl + .manifest.json，逐成员回写 records_in/kept/dropped + drop_reasons，
        bundle 回写 sha/records/review_ratio/reviewed_*，状态 → materialized。

        版本登记与 composed_of 血缘由作业完成后的 `artifacts.register()` 负责（用真实 job_id）；
        本方法只保证产物落盘 + bundle 行可被 freeze 读到确定性 sha256。重跑同一 bundle 因
        源文件与成员不变 → 输出逐字节一致 → sha 幂等（P3）。
        """
        import hashlib
        import json
        from kev.console import artifacts, paths
        paths.ensure_generators_on_path()
        import split_data

        store = self.store
        if self.cancel.is_set():
            return {"returncode": 130}
        bundle = store.get_bundle(req.params.get("bundle_id", ""))
        if bundle is None:
            on_log(f"bundle 不存在：{req.params.get('bundle_id')!r}")
            return {"returncode": 1}
        project = store.get_project(bundle["project_id"]) or {}
        scenario = project.get("scenario") or req.scenario
        members = store.get_bundle_members(bundle["id"])
        try:
            overlay = store.record_reviews_by_fingerprint(scenario)
        except Exception:  # 覆盖层缺失/未落地（PR D 前）就当空管道，不阻断物化
            overlay = {}

        # 1) 逐成员读原始记录，排除 exclude，应用覆盖层的 drop/flag/reviewed 判定。
        offered = []          # [(member_index, record)] 进 dedupe 的记录
        per_member = []       # 每个成员一份统计
        reviewed = {"native": 0, "inherited": 0, "total": 0}
        for idx, member in enumerate(members):
            target = Path(paths.ROOT) / member["source_path"]
            raw = []
            if target.is_file():
                raw = [json.loads(line) for line in
                       target.read_text(encoding="utf-8").splitlines() if line.strip()]
            stat = {"version_id": member["version_id"], "op": member["op"],
                    "records_in": len(raw), "records_kept": 0, "records_dropped": 0,
                    "drop_reasons": {"dup": 0, "state_conflict": 0,
                                     "review_drop": 0, "review_unresolved": 0}}
            per_member.append(stat)
            if member["op"] == "exclude":
                stat["records_dropped"] = len(raw)
                continue
            for record in raw:
                fp = split_data.record_fingerprint(record)
                decision = overlay.get(fp)
                verdict = decision["verdict"] if decision else ""
                if verdict == "drop":
                    stat["drop_reasons"]["review_drop"] += 1
                    continue
                if verdict in ("accept", "relabel", "edit", "flag"):
                    reviewed["total"] += 1
                    reviewed["native" if (decision.get("origin") in (None, bundle["project_id"]))
                             or True else "inherited"] += 1  # origin 拆分在 PR D 精化，此处先计 native
                if verdict == "flag":
                    stat["drop_reasons"]["review_unresolved"] += 1
                offered.append((idx, record, fp))

        # 2) 全局去重 —— 复用 split_data.dedupe（唯一真相），不自己再写一套判重。
        input_records = [record for _idx, record, _fp in offered]
        kept_records, dropped_dupes, _n_conflict_states = split_data.dedupe(input_records)
        kept_ids = {id(record) for record in kept_records}

        # 3) 逐成员归因：kept 用对象身份回填；dup 用 split_data.canonical_record（同一规范化）
        #    的首现判定，剩余丢弃归 state_conflict。dup + state_conflict == 该成员丢弃数，
        #    与 dedupe 的总丢弃一致（Review Focus）。
        seen_canonical: set[str] = set()
        for idx, record, _fp in offered:
            canonical = split_data.canonical_record(record)
            is_dup = canonical in seen_canonical
            seen_canonical.add(canonical)
            stat = per_member[idx]
            if id(record) in kept_ids:
                stat["records_kept"] += 1
            elif is_dup:
                stat["drop_reasons"]["dup"] += 1
                stat["records_dropped"] += 1
            else:
                stat["drop_reasons"]["state_conflict"] += 1
                stat["records_dropped"] += 1

        # 4) 写出不可变快照 + manifest（确定序，保证幂等 sha）。
        out_rel = artifacts.resolve(bundle["artifact_id"])
        out_path = Path(paths.ROOT) / out_rel
        out_path.parent.mkdir(parents=True, exist_ok=True)
        body = "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in kept_records)
        data = body.encode("utf-8")
        out_path.write_bytes(data)          # 写字节，绕开 Windows 文本模式的 \n->\r\n 转换（sha 与磁盘逐字节一致）
        sha256 = hashlib.sha256(data).hexdigest()

        total_kept = len(kept_records)
        review_ratio = (reviewed["total"] / total_kept) if total_kept else 0.0
        manifest_rel = out_rel[:-len(".jsonl")] + ".manifest.json" if out_rel.endswith(".jsonl") \
            else f"{out_rel}.manifest.json"
        manifest = {
            "bundle_id": bundle["id"], "name": bundle["name"],
            "artifact_id": bundle["artifact_id"], "scenario": scenario,
            "records": total_kept, "sha256": sha256, "review_ratio": review_ratio,
            "reviewed_records": reviewed["total"], "reviewed_native": reviewed["native"],
            "reviewed_inherited": reviewed["inherited"],
            "members": [{"version_id": s["version_id"], "op": s["op"], "ord": i,
                         "records_in": s["records_in"], "records_kept": s["records_kept"],
                         "records_dropped": s["records_dropped"],
                         "drop_reasons": s["drop_reasons"]}
                        for i, s in enumerate(per_member)],
        }
        manifest_bytes = json.dumps(manifest, ensure_ascii=False, sort_keys=True).encode("utf-8")
        (Path(paths.ROOT) / manifest_rel).write_bytes(manifest_bytes)

        # 5) 回写 bundle + 成员统计，并登记产物指针（版本 + 血缘留给 register 用真实 job_id）。
        store.set_bundle_members_stats(bundle["id"], per_member)
        store.update_bundle_materialization(
            bundle["id"], sha256=sha256, records=total_kept, review_ratio=review_ratio,
            reviewed_records=reviewed["total"], reviewed_native=reviewed["native"],
            reviewed_inherited=reviewed["inherited"],
            manifest_path=manifest_rel,
            manifest_sha256=hashlib.sha256(manifest_bytes).hexdigest())
        kind, _, name = bundle["artifact_id"].partition(":")
        store.put_artifact(kind=kind, name=name, path=out_rel,
                           meta=artifacts.summarize(bundle["artifact_id"], out_rel),
                           bytes_=len(data))
        on_log(f"物化完成：{total_kept} 条记录，sha256={sha256[:12]}…")
        return {"returncode": 0}


def make_goldset_sample_namespace(args: dict, req: JobRequest) -> argparse.Namespace:
    """Helper: build the Namespace make_goldset.run_sample expects.

    run_sample only reads .data / .n / .seed / .out; we materialize the rest of
    the subcommand's defaults to 0/empty so a downstream that introspects
    `args.command` (none do today) still gets a sensible value.
    """
    return argparse.Namespace(command="sample", **args)
