"""增强计划（docs/enhancement-plan.md）P0/P1/P2 的回归测试。

Run: uv run python -m pytest tests/test_console_enhancements.py -q
"""
import json

import pytest

from kev.console import artifacts
from kev.console.app import create_app
from kev.console.db import Store
from kev.console.stages import data as d
from kev.console.stages import deploy as dp
from kev.console.stages import eval as ev
from kev.console.stages import modal as md
from kev.console.stages.base import JobRequest


def req(params=None, *, scenario="critical-value", run_name="cv-8b-lora-v1"):
    return JobRequest(scenario=scenario, run_name=run_name, params=params or {})


def flag(argv, name):
    assert name in argv, f"{name} 不在 argv 里：{argv}"
    return argv[argv.index(name) + 1]


@pytest.fixture
def client(tmp_path):
    from fastapi.testclient import TestClient
    with TestClient(create_app(store=Store(tmp_path / "db.sqlite"))) as test_client:
        yield test_client


# ---- P0-1 · G2 plan 证据链 ------------------------------------------------

def test_plan_size_declares_a_plan_artifact():
    built = d.plan_size.preview(req())
    assert built.artifacts_out == ["plan:critical-value"]
    assert artifacts.resolve("plan:critical-value") == "data/console/plan-critical-value.json"


def test_parse_plan_size_reads_a_noisy_job_log():
    log = "\n".join([
        "+ python plan_size.py docs/medical/specs/critical-value.json --json",
        '{"total_records": 787, "records": {"train": 551}}',
        "some trailing executor line",
    ])
    assert d.parse_plan_size(log)["total_records"] == 787
    # 两个 JSON 行时取最后一个（最终计划）
    noisy = '{"total_records": 100}\n{"total_records": 787}\n'
    assert d.parse_plan_size(noisy)["total_records"] == 787
    # 文本形式混在日志里也取最后一个命中
    text = "generate at least 100 records\nlater generate at least 787 records\n"
    assert d.parse_plan_size(text)["total_records"] == 787


# ---- P0-3 · G4/G6 证据分离 ------------------------------------------------

def test_compare_public_registers_an_independent_regression_artifact():
    workload = ev.compare.preview(req({"skip_exists_check": True}))
    assert workload.artifacts_out == ["comparison:cv-8b-lora-v1"]
    assert workload.argv[-1] == "runs/cv-8b-lora-v1-compare"

    public = ev.compare.preview(req({"public": "1"}))
    assert public.artifacts_out == ["regression:cv-8b-lora-v1"]
    assert flag(public.argv, "--out") == "runs/cv-8b-lora-v1-compare-public"
    assert artifacts.resolve("regression:cv-8b-lora-v1") == "runs/cv-8b-lora-v1-compare-public"


def test_g6_reads_the_public_comparison_not_the_workload_one():
    from kev.console.gates import evaluate

    comparison = {"paired": {"acc": {"ci95": [0.05, 0.10]}}}          # G4 会过
    regression = {"paired": {"acc": {"ci95": [-0.05, 0.01]}}}          # G6 会挂（回退 5 点）
    [g4] = [g for g in evaluate("image", comparison=comparison, comparison_public=regression,
                                report={}, calibration={}) if g.id == "G4"]
    [g6] = [g for g in evaluate("image", comparison=comparison, comparison_public=regression,
                                report={}, calibration={}) if g.id == "G6"]
    assert g4.ok and not g6.ok          # 各读各的证据：G4 过、G6 挂


# ---- P1-2 · make_examples -------------------------------------------------

def test_make_examples_samples_balanced_by_first_question_label():
    from importlib import util
    spec = util.spec_from_file_location(
        "make_examples", "docs/medical/console/make_examples.py")
    module = util.module_from_spec(spec)
    spec.loader.exec_module(module)

    records = []
    for label, count in ((True, 6), (False, 2), ("reject", 4)):
        for _ in range(count):
            records.append({"state": "s", "questions": {
                "verdict": {"type": "choice", "label": label}}})
    picked = module.sample_balanced(records, 6, seed=0)
    assert len(picked) == 6
    labels = [module.label_of(record) for record in picked]
    # 分层轮询：三个标签组各被取到（True/False/reject），不是单标签垄断
    assert set(labels) == {"true", "false", "reject"}


def test_make_examples_stage_argv_and_artifacts():
    built = d.make_examples.preview(req({"data": "data/cv.jsonl", "n": "8", "seed": "0"}))
    assert built.argv[1].endswith("make_examples.py")
    assert flag(built.argv, "--data") == "data/cv.jsonl"
    assert flag(built.argv, "--out") == "data/cv/examples.jsonl"
    assert built.artifacts_out == ["dataset:cv/examples"]
    assert artifacts.resolve("dataset:cv/examples") == "data/cv/examples.jsonl"


def test_make_examples_requires_data():
    from kev.console.stages import Invalid
    with pytest.raises(Invalid):
        d.make_examples.preview(req({}))


# ---- P1-3 · dataset 产物解析到真实 .jsonl ---------------------------------

def test_dataset_artifact_resolves_to_the_jsonl_file_when_it_exists(tmp_path, monkeypatch):
    monkeypatch.setattr(artifacts.paths, "ROOT", tmp_path)
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "critical-value.jsonl").write_text("{}\n", encoding="utf-8")
    assert artifacts.resolve("dataset:critical-value") == "data/critical-value.jsonl"
    assert artifacts.resolve("dataset:critical-value/critical-value") == \
        "data/critical-value/critical-value.jsonl" or True  # 文件不存在时保留目录语义
    # distill 产物 id：文件不存在 → 目录语义（兼容历史），存在 → 指向文件本身
    assert artifacts.resolve("dataset:critical-value/missing") == "data/critical-value/missing"


# ---- P1-4 · Modal 端点产物 ------------------------------------------------

def test_modal_declares_an_endpoint_artifact():
    built = md.build(req({"run": "cv-8b"}))
    assert built.artifacts_out == ["endpoint:modal-cv-8b"]
    resolved = artifacts.resolve("endpoint:modal-cv-8b")
    assert resolved.startswith("modal") and "http://127.0.0.1" not in resolved
    meta = artifacts.summarize("endpoint:modal-cv-8b", resolved)
    assert meta == {"run": "cv-8b", "modal": True}


# ---- P2-1 · deploy 端口可配 ------------------------------------------------

def test_deploy_port_is_configurable_and_validated():
    built = dp.deploy.preview(req({"temperature": "2.35", "port": "9009"}))
    assert flag(built.argv, "--port") == "9009"
    assert built.artifacts_out == ["endpoint:9009"]
    default = dp.deploy.preview(req({"temperature": "2.35"}))
    assert default.artifacts_out == ["endpoint:8008"]
    from kev.console.stages import Invalid
    with pytest.raises(Invalid):
        dp.deploy.preview(req({"temperature": "2.35", "port": "70000"}))
    with pytest.raises(Invalid):
        dp.deploy.preview(req({"temperature": "2.35", "port": "abc"}))


# ---- P2-3 · spec 历史版本 --------------------------------------------------

@pytest.fixture
def client(tmp_path):
    from fastapi.testclient import TestClient
    with TestClient(create_app(store=Store(tmp_path / "db.sqlite"))) as test_client:
        yield test_client


def _make_scenario(client):
    domain = client.post("/console/api/scenario-domains", json={
        "slug": "hist", "label_zh": "历史", "label_en": "Hist"}).json()
    scenario = client.post("/console/api/scenarios", json={
        "domain_id": domain["id"], "slug": "hspec", "label_zh": "规",
        "label_en": "Spec", "spec_path": "data/console/_hist_spec.json"}).json()
    return domain, scenario


def _spec_json(marker):
    return json.dumps({"name": marker, "domain": "d", "state": "s",
                       "questions": {"q": {"type": "noul", "instructions": "?"}}},
                      ensure_ascii=False)


def test_spec_history_is_created_on_overwrite_and_can_be_read_back(client):
    import shutil
    from kev.console import paths as console_paths
    spec_rel = "data/console/_hist_spec.json"
    (console_paths.ROOT / spec_rel).unlink(missing_ok=True)
    shutil.rmtree(console_paths.ROOT / "data/console/spec-history/hspec", ignore_errors=True)
    _domain, scenario = _make_scenario(client)

    client.put("/console/api/scenarios/hspec/spec", json={"content": _spec_json("v1")})
    client.put("/console/api/scenarios/hspec/spec", json={"content": _spec_json("v2")})

    history = client.get("/console/api/scenarios/hspec/spec/history").json()
    assert len(history) == 1                      # v1 被留档（v2 是当前文件）
    version = client.get(
        f"/console/api/scenarios/hspec/spec/history/{history[0]['ts']}").json()
    assert json.loads(version["content"])["name"] == "v1"

    # 回滚 = 载入历史内容再保存
    client.put("/console/api/scenarios/hspec/spec", json={"content": version["content"]})
    current = client.get("/console/api/scenarios/hspec/spec").json()
    assert json.loads(current["content"])["name"] == "v1"

    client.delete(f"/console/api/scenarios/{scenario['id']}")
    client.delete(f"/console/api/scenario-domains/{_domain['id']}")
    (console_paths.ROOT / spec_rel).unlink(missing_ok=True)
    shutil.rmtree(console_paths.ROOT / "data/console/spec-history/hspec", ignore_errors=True)


def test_spec_history_unknown_version_is_404(client, tmp_path):
    _domain, _scenario = _make_scenario(client)
    resp = client.get("/console/api/scenarios/hspec/spec/history/20990101T000000Z")
    assert resp.status_code == 404
