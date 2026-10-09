"""三个阶段处理器的 argv 组装（Task 5-7）。

三条主线：
1. **golden argv**：每个 kind 的 argv 必须与 kev/console/generators/run_matrix.py::steps()
   的前三步（plan_size / generate / split，那是纯本地的）逐字一致，避免第二套参数语义。
2. **契约**：产物 id 必须能被 artifacts.resolve 解析、关系名必须能在 artifacts.RELATION
   里查到，否则产物注册会抛。
3. **前置校验**：运行名含点号、目录已存在、快照缺 max_steps、未知方式/场景…都要在
   spawn 之前拦住，而不是让子进程抛栈。

**绝不能把 params 放顶层** —— pydantic 默认 extra='ignore'，放顶层会被静默丢弃。

Run: uv run python -m pytest tests/test_console_stages.py -q
"""
import json as _json
from pathlib import Path

import pytest

from kev.console import artifacts, paths as console_paths
from kev.console.stages import REGISTRY, Conflict, Invalid, JobRequest
from kev.console.stages import data as d
from kev.console.stages import deploy as dp
from kev.console.stages import eval as ev
from kev.console.stages import train as tr


def req(params=None, *, scenario="critical-value", run_name="cv-8b-lora-v1"):
    return JobRequest(scenario=scenario, run_name=run_name, params=params or {})


def flag(argv, name):
    assert name in argv, f"{name} 不在 argv 里：{argv}"
    return argv[argv.index(name) + 1]


# 每个 kind 的最小可用参数。image/deploy 需要温度（否则会因为没有 calibration 而被拒）。
SAMPLES = {"generate": {}, "distill": {}, "goldset": {}, "split": {}, "precheck": {},
           "train": {}, "baseline": {}, "benchmark": {}, "compare": {}, "calibrate": {},
           "image": {"temperature": "2.35"}, "deploy": {"temperature": "2.35"},
           "smoke": {}, "make_examples": {"data": "data/cv.jsonl"}}


# ---- 契约：作业类型齐备 -------------------------------------------------

def test_all_stage_kinds_are_registered():
    assert set(REGISTRY) == {
        "plan_size", "generate", "distill", "distill_daemon", "goldset", "goldset_audit",
        "split", "precheck", "make_examples",
        "train", "baseline", "benchmark", "compare", "calibrate",
        "image", "deploy", "smoke",
        "publish", "modal"}


def test_every_kind_that_declares_artifacts_has_a_relation():
    """artifacts.register 用 RELATION[job.kind] 查血缘关系名；缺了就退化成
    'produced_by'，血缘语义就丢了。plan_size 不声明任何产物（它只打印计划），
    所以不需要关系名。新阶段的 preview 对必填字段缺失会直接 Invalid，这里给最小可用参数。"""
    minimal = {
        "publish": {"repo": "j", "card": "c.md"},
        "modal": {"run": "x"},
        "goldset_audit": {"a": "x", "b": "y"},
        "distill_daemon": {"schedule": "03:00", "skip_exists_check": True},
        "make_examples": {"data": "data/cv.jsonl"},
    }

    def preview_of(kind):
        if kind in {"image", "deploy"}:
            return REGISTRY[kind].preview(req({"temperature": "2.35"}))
        return REGISTRY[kind].preview(req(minimal.get(kind, {})))

    for kind, spec in REGISTRY.items():
        if not preview_of(kind).artifacts_out:
            continue
        assert kind in artifacts.RELATION, f"{kind} 声明了产物但 RELATION 里没有条目"


def test_every_declared_artifact_id_resolves_to_the_right_path():
    """声明的产物 id 必须能被 resolve 解析成**正确的路径** —— 否则 register 会抛
    ValueError 打死作业完成回调（那个回调是 except: pass，静默）。

    断言「非空」是不够的：曾经把 `data/cv` 直接当 id 传进去，resolve 解析成
    `data/data/cv/summary.json`（双前缀）也能返回非空字符串，但文件永远找不到。
    """
    for kind, params in SAMPLES.items():
        built = REGISTRY[kind].preview(req(params))
        assert built.artifacts_out, f"{kind} 没有声明产物"
        for artifact_id in built.artifacts_out:
            relative = artifacts.resolve(artifact_id)
            assert relative, f"{kind} 的 {artifact_id} 解析为空"
            if relative.startswith("http"):        # endpoint 解析成 URL，不是文件路径
                continue
            # 仓库相对路径里不允许出现重复的 data/ 或 runs/ 前缀
            assert "//" not in relative, f"{kind} 的 {artifact_id} -> {relative} 有空段"
            for prefix in ("data/data/", "runs/runs/"):
                assert prefix not in relative, \
                    f"{kind} 的 {artifact_id} -> {relative} 出现双前缀 {prefix}"


def test_the_out_flag_writes_where_the_registered_artifact_will_be_read():
    """--out 写的路径必须就是产物 id resolve 出来的那个路径。

    手拼 --out 会和注册 id 各走一套逻辑：作业写完一个文件、闸门却按 id 去读另一个
    ⇒ 闸门恒失败，而且失败原因是「缺少报告」，看上去像没跑过作业。
    precheck 就是这样：--out 用 data_dir.replace('/','-') 拼出
    precheck-data-cv-train.json，而注册的 precheck:cv/train 解析成
    precheck-cv-train.json（附录 A #11 的同类错配，那次只修了一半）。

    split 的 --out 是目录（它一次写三个分区 + summary），所以也接受「--out 是所有
    产物路径的公共前缀」。
    """
    for kind, params in SAMPLES.items():
        built = REGISTRY[kind].preview(req(params))
        if "--out" not in built.argv:
            continue
        out = built.argv[built.argv.index("--out") + 1].replace("\\", "/")
        resolved = [artifacts.resolve(a).replace("\\", "/") for a in built.artifacts_out]
        # 只比对解析结果是**文件**的那些：dataset:cv / run:x / eval:x 是逻辑句柄
        # （数据集目录、run 目录），--out 与它不同形是正常的，不算错配。
        file_like = [p for p in resolved
                     if not p.startswith("http") and Path(p).suffix in (".json", ".jsonl")]
        if not file_like:
            continue
        # split 的 --out 是目录，它一次写多个文件 —— 接受「--out 是公共前缀」
        ok = out in file_like or all(p.startswith(out.rstrip("/") + "/") for p in file_like)
        assert ok, (f"{kind} 的 --out={out} 与产物 id 解析出的路径对不上：{file_like}")


def test_dataset_artifact_ids_are_relative_to_the_data_dir():
    """产物 id 里的数据集名必须相对 data/（resolve 自己会拼 DATA_DIR 前缀）。"""
    built = d.split.preview(req({"data": "data/cv", "skip_exists_check": True}))
    assert built.artifacts_out == ["dataset:cv/summary", "dataset:cv/train",
                                   "dataset:cv/calibration", "dataset:cv/development"]
    assert artifacts.resolve("dataset:cv/summary") == "data/cv/summary.json"
    assert artifacts.resolve("dataset:cv/train") == "data/cv/train.jsonl"
    assert d.precheck.preview(req({"data": "data/cv"})).artifacts_out == ["precheck:cv/train"]


def test_split_and_precheck_register_the_artifacts_the_gates_read():
    """G2/G3 读 dataset:<dir>/summary，G1 读 precheck:<dir>/<split>。漏任一个，
    对应闸门永远判失败 —— 而闸门失败会阻断训练（spec §8）。"""
    assert "dataset:cv/summary" in d.split.preview(
        req({"data": "data/cv", "skip_exists_check": True})).artifacts_out
    assert d.precheck.preview(req({"data": "data/cv"})).artifacts_out == ["precheck:cv/train"]


def test_preview_is_pure_and_repeatable():
    """preview 绝不能有副作用 —— UI 每次改表单字段都要调它。"""
    for kind, params in (("train", {}), ("generate", {"skip_exists_check": True}),
                         ("plan_size", {})):
        spec = REGISTRY[kind]
        assert spec.preview(req(params)).argv == spec.preview(req(params)).argv


# ---- 1. golden argv：与 run_matrix 前三步逐字一致 -------------------------

def test_plan_size_argv_matches_run_matrix():
    argv = d.plan_size.preview(req()).argv
    assert argv[1].endswith("plan_size.py")
    assert argv[2].endswith("critical-value.json")
    assert argv[3:] == ["--baseline-acc", "0.75", "--json"]


def test_generate_argv_matches_run_matrix():
    argv = d.generate.preview(req({"n": 787, "seed": 0, "data": "data/cv",
                                   "skip_exists_check": True})).argv
    assert argv[1].endswith("gen_critical_value.py")
    assert argv[2:] == ["--n", "787", "--out", "data/cv.jsonl", "--seed", "0"]


def test_generate_maps_hyphenated_scenario_to_underscored_module():
    argv = d.generate.preview(req(scenario="medication-review",
                                  params={"skip_exists_check": True})).argv
    assert argv[1].endswith("gen_medication_review.py")


def test_split_argv_and_its_declared_artifacts():
    built = d.split.preview(req({"data": "data/cv", "holdout": "data/cv.gold.jsonl",
                                 "development": 0.15, "calibration": 0.15, "seed": 0,
                                 "skip_exists_check": True}))
    assert built.argv[2:] == ["data/cv.jsonl", "--out", "data/cv",
                              "--calibration", "0.15", "--development", "0.15",
                              "--seed", "0", "--holdout", "data/cv.gold.jsonl"]
    assert built.artifacts_out == ["dataset:cv/summary", "dataset:cv/train",
                                   "dataset:cv/calibration", "dataset:cv/development"]


def test_goldset_argv_uses_the_sample_subcommand():
    argv = d.goldset.preview(req({"n": 200, "seed": 0, "data": "data/cv",
                                  "skip_exists_check": True})).argv
    assert argv[1].endswith("make_goldset.py")
    assert argv[2:4] == ["sample", "data/cv.jsonl"]
    assert argv[-2:] == ["--out", "data/cv.gold.jsonl"]


def test_precheck_argv_uses_the_right_tokenizer_and_partition():
    built = d.precheck.preview(req({"data": "data/cv", "split": "train",
                                    "init_from": "jaredpalmer/kev-0.8b"}))
    assert built.argv[1].endswith("precheck.py")
    assert flag(built.argv, "--init-from") == "jaredpalmer/kev-0.8b"
    assert flag(built.argv, "--split") == "train"
    # 训练上下文的预算是 kev.model.training_context()，不许在任何 argv 里硬编码
    assert not any("384" in part for part in built.argv)
    assert built.artifacts_out == ["precheck:cv/train"]   # 这里显式给了 data: "data/cv"


def test_every_script_the_stages_spawn_actually_exists():
    """编排层只组装 argv，被 spawn 的脚本是别的目录里的真实文件。

    preview() 只拼字符串 —— 文件不存在照样返回 argv。所以 golden argv 全绿
    也不代表作业跑得起来：precheck.py / smoke.py 就是这样漏掉的，
    `argv[1].endswith("precheck.py")` 永远为真，真提交才 FileNotFoundError，
    而 G1 读不到 over_limit ⇒ train 永远无法提交（附录 A #11）。

    precheck 的路径从 argv 实测取，谁改了 data.py 的拼接这里就跟着变，不会写死。
    """
    scripts = {
        "plan_size": console_paths.SKILL_SCRIPTS / "plan_size.py",
        "generate": console_paths.SKILL_SCRIPTS / "generate_data.py",
        "goldset": console_paths.GENERATORS / "make_goldset.py",
        "split": console_paths.SKILL_SCRIPTS / "split_data.py",
        "precheck": Path(d.precheck.preview(req({"data": "data/cv"})).argv[1]),
        "smoke": dp.SMOKE_SCRIPT,
        "make_examples": Path(d.make_examples.preview(req({"data": "data/cv.jsonl"})).argv[1]),
    }
    missing = {kind: str(p) for kind, p in scripts.items() if not p.exists()}
    assert missing == {}, f"stage 要 spawn 的脚本不存在，作业一起就 FileNotFoundError：{missing}"


def test_parse_plan_size_reads_both_the_json_and_the_text_form():
    assert d.parse_plan_size('{"total_records": 787}')["total_records"] == 787
    text = "development questions: 469 paired (unpaired bound 1092)\n  generate at least 787 records\n"
    assert d.parse_plan_size(text)["total_records"] == 787
    assert d.parse_plan_size("完全无关的输出") == {}


# ---- 2. 训练方式 A1 / A2 / B ---------------------------------------------

def test_a1_is_the_default_and_hot_starts_from_the_released_checkpoint():
    argv = tr.build_argv(req())
    assert argv[0:2] == ["-m", "kev.train"]
    assert flag(argv, "--init_from") == "jaredpalmer/kev-0.8b"
    assert flag(argv, "--full_ft") == "0"   # 显式传 0 比省略更清楚
    assert flag(argv, "--lora") == "16"
    assert flag(argv, "--lr") == "4e-5"
    assert flag(argv, "--replay") == "2000"
    assert flag(argv, "--lora_targets") == "all"
    assert flag(argv, "--head_dim") == "256"
    assert flag(argv, "--out") == "runs/cv-8b-lora-v1"


def test_a2_uses_the_bare_base_with_a_pinned_revision():
    """--base 的默认是 Qwen/Qwen3-0.6B-Base（train.py:376），不显式传就会训错基座。"""
    argv = tr.build_argv(req({"method": "a2"}))
    assert "--init_from" not in argv
    assert flag(argv, "--base") == "Qwen/Qwen3.5-0.8B-Base"
    assert flag(argv, "--base_revision") == "9a45d25e"


def test_full_weight_forces_bf16_weights():
    argv = tr.build_argv(req({"method": "b"}))
    assert flag(argv, "--full_ft") == "1"
    assert flag(argv, "--weights_dtype") == "bf16"
    assert flag(argv, "--dtype") == "bf16"
    assert flag(argv, "--replay") == "0"


def test_snapshot_fractions_require_max_steps():
    with pytest.raises(Invalid, match="max_steps"):
        tr.build_argv(req({"method": "b", "snapshot_fractions": "0.25,0.5,0.75"}))


def test_run_names_and_scenarios_are_validated_before_spawning():
    with pytest.raises(SystemExit):        # run_matrix.check_name 用 fullmatch，禁点号
        tr.build_argv(req(run_name="critical-value-0.8b-v1"))
    with pytest.raises(Invalid, match="未知场景"):
        d.generate.preview(req(scenario="不存在"))


def test_icd_coding_refuses_the_eight_b_track():
    with pytest.raises(Invalid, match="4B"):
        tr.build_argv(req(scenario="icd-coding"))


def test_unknown_method_is_rejected():
    with pytest.raises(Invalid, match="微调方式"):
        tr.build_argv(req({"method": "a3"}))


def test_existing_output_is_a_conflict_not_a_silent_overwrite():
    with pytest.raises(Conflict, match="已存在"):
        tr.build_argv(req({"check_exists": True, "out": "runs"}))
    with pytest.raises(Conflict, match="已存在"):
        d.generate.preview(req({"check_exists": True}))


# ---- 3. 评测：baseline / benchmark / compare / calibrate -----------------

def test_benchmark_points_at_the_development_partition():
    argv = ev.benchmark.preview(req({"data": "data/cv"})).argv
    assert argv[1:3] == ["-m", "kev.benchmark"]
    assert flag(argv, "--run") == "runs/cv-8b-lora-v1"
    assert flag(argv, "--data") == "data/cv/development.jsonl"
    assert flag(argv, "--out") == "runs/cv-8b-lora-v1-eval"


def test_baseline_scores_the_same_development_file():
    """配对 bootstrap 要求两份 report 的 suite_sha256 一致（compare.py:39-40），
    而它 = digest(数据文件)、digest 按**内容**算 —— 所以两侧必须用同一个 data 文件。"""
    base = ev.baseline.preview(req({"data": "data/cv", "baseline": "jaredpalmer/kev-0.8b"}))
    bench = ev.benchmark.preview(req({"data": "data/cv"}))
    assert flag(base.argv, "--data") == flag(bench.argv, "--data")
    assert flag(base.argv, "--run") == "jaredpalmer/kev-0.8b"
    assert flag(base.argv, "--out") == "runs/cv-8b-lora-v1-baseline-eval"


def test_suite_hash_mismatch_is_reported_before_compare_runs():
    """两侧 suite_sha256 不一致时 kev.compare 直接 ValueError（compare.py:39-40）。
    预检把它变成可读的原因。文件不存在时不预判，交给 compare 自己报错。"""
    assert ev.suite_hash_mismatch("runs/不存在-eval", "runs/也不存在-baseline-eval") == ""


def test_compare_takes_two_dirs_and_declares_a_comparison_artifact():
    built = ev.compare.preview(req())
    assert built.argv[1:3] == ["-m", "kev.compare"]
    assert flag(built.argv, "--candidate") == "runs/cv-8b-lora-v1-eval"
    assert flag(built.argv, "--reference") == "runs/cv-8b-lora-v1-baseline-eval"
    assert built.artifacts_out == ["comparison:cv-8b-lora-v1"]


def test_compare_refuses_identical_sides():
    with pytest.raises(Invalid, match="同一个目录"):
        ev.compare.preview(req({"candidate": "runs/x-eval", "reference": "runs/x-eval"}))


def test_calibrate_reads_the_rows_of_its_own_benchmark():
    built = ev.calibrate.preview(req())
    assert built.argv[1:3] == ["-m", "kev.calibrate"]
    assert flag(built.argv, "--rows") == "runs/cv-8b-lora-v1-eval/rows.json"
    assert built.artifacts_out == ["calibration:cv-8b-lora-v1"]


def test_split_must_be_one_of_the_three_partitions():
    with pytest.raises(Invalid, match="split 必须是"):
        ev.benchmark.preview(req({"split": "test"}))     # --allow-test 只能读锁定测试集


# ---- 4. 镜像 / 部署 / 冒烟 -----------------------------------------------

def test_image_builds_from_the_template_with_the_run_filled_in():
    built = dp.image.preview(req({"temperature": "2.35"}))
    assert built.argv[:3] == ["docker", "build", "-t"]
    assert built.argv[3] == "kev-cv-8b-lora-v1:2.35"
    # 用 Path 比而不是 endswith("deploy/kev-serve")：Windows 上分隔符是反斜杠
    assert Path(built.argv[-1]).parts[-2:] == ("deploy", "kev-serve")
    assert flag(built.argv, "--build-arg").startswith("KEV_SERVE_RUN=")
    assert built.artifacts_out == ["image:kev-cv-8b-lora-v1"]


def test_image_and_deploy_require_a_temperature():
    for spec in (dp.image, dp.deploy):
        with pytest.raises(Invalid, match="服务温度"):
            spec.preview(req({}))
        with pytest.raises(Invalid, match="服务温度"):
            spec.preview(req({"temperature": "0"}))


def test_deploy_starts_kev_serve_on_8008_and_never_reads_the_reserved_env():
    built = dp.deploy.preview(req({"temperature": "2.35"}))
    assert built.argv[1:3] == ["-m", "kev.serve"]
    assert flag(built.argv, "--run") == "runs/cv-8b-lora-v1"
    assert flag(built.argv, "--port") == "8008"
    assert "KEV_TEMPERATURE" not in built.env
    assert built.env["KEV_SERVE_RUN"] == "cv-8b-lora-v1"


def test_deploy_persists_at_start_because_serve_never_finishes():
    """kev.serve 是长驻进程：若按 SUCCESS 注册，产物永远不出现，端点列表永远是空的。"""
    assert dp.deploy.persist == "start"
    assert dp.image.persist == "success" and dp.smoke.persist == "success"


def test_deploy_refuses_a_second_endpoint_on_the_same_port():
    with pytest.raises(Invalid, match="8008"):
        dp.deploy.preview(req({"temperature": "2.35", "busy_port": True}))


def test_smoke_covers_all_five_scenarios_and_targets_the_endpoint():
    assert {probe["scenario"] for probe in dp.SMOKE_PROBES} == {
        "critical-value", "triage", "medication-review", "nursing-quality", "icd-coding"}
    built = dp.smoke.preview(req())
    assert flag(built.argv, "--base-url") == "http://127.0.0.1:8008"
    assert flag(built.argv, "--out") == "runs/cv-8b-lora-v1-smoke.json"
    # 产物 id 用 smoke:（resolve 有 smoke 分支），不是 eval:
    assert built.artifacts_out == ["smoke:cv-8b-lora-v1"]


def test_smoke_probe_state_fields_match_each_specs_state_example():
    """字段名对模型可见、跨记录必须一致（data-format.md §二）：改字段名等于换了一个任务。
    所以探针的 state 键必须与该场景 spec 的 state_example 完全相同，不能自造。"""
    for probe in dp.SMOKE_PROBES:
        spec = console_paths.SPECS / f"{probe['scenario']}.json"
        assert spec.is_file(), f"spec 不存在：{spec}"
        declared = set(_json.loads(spec.read_text(encoding="utf-8"))["state_example"])
        assert set(probe["state"]) == declared, \
            f"{probe['scenario']} 的探针字段与 spec 的 state_example 不符：" \
            f"多 {set(probe['state']) - declared} / 缺 {declared - set(probe['state'])}"


# ---- 5. 蒸馏轨 -----------------------------------------------------------

def test_distill_env_carries_the_base_url_but_never_a_key():
    built = d.distill.preview(req({"base_url": "https://api.ant-ling.com/v1",
                                   "model": "Ling-3.0-flash",
                                   "skip_exists_check": True}))
    assert built.env["KEV_GEN_BASE_URL"] == "https://api.ant-ling.com/v1"
    assert built.env["KEV_GEN_MODEL"] == "Ling-3.0-flash"
    # 凭据由执行器在 spawn 时从编排服务进程环境注入，永不进 env_overlay
    assert not any("KEY" in key or "TOKEN" in key for key in built.env)
    # 场景经 DB 的 spec_path 以位置参数形式传给 generate_data.py（绕开其冻结的
    # CATEGORY_SPECS 硬编码映射），不再用 --category；argv[2] 即 spec 文件绝对路径。
    assert "--category" not in built.argv
    assert str(built.argv[2]).endswith("critical-value.json")


def test_distill_rejects_more_keys_than_the_rotation_limit():
    with pytest.raises(Invalid, match="最多"):
        d.distill.preview(req({"api_keys": ["k"] * (d.MAX_DISTILL_KEYS + 1)}))
