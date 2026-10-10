"""两级场景（域 / 场景）管理：种子、CRUD、双语、spec 文件读写、自定义场景蒸馏。

Run: uv run python -m pytest tests/test_console_scenarios.py -q
"""
import pytest

from fastapi.testclient import TestClient
from kev.console.app import create_app
from kev.console.db import Store


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(store=Store(tmp_path / "db.sqlite"))) as c:
        yield c


def _tree(client):
    return client.get("/console/api/scenario-domains").json()


def flag(argv, name):
    """取 --name 对应的值，找不到返回 None（与 test_console_stages 同口径）。"""
    return argv[argv.index(name) + 1] if name in argv else None


# ---- 种子 ---------------------------------------------------------------

def test_seed_is_idempotent_and_bilingual(client):
    tree = _tree(client)
    domains = {d["slug"]: d for d in tree}
    assert "medical" in domains
    medical = domains["medical"]
    assert medical["label_zh"] == "医疗" and medical["label_en"] == "Medical"
    slugs = {s["slug"] for s in medical["scenarios"]}
    # run_matrix 已知的医疗场景全部落库（含 icd-coding）
    assert {"critical-value", "icd-coding", "triage"} <= slugs
    # 7 个基础医疗场景 + 3 个蒸馏轨补回（inquiry / medication / knowledge-qa）
    assert len(medical["scenarios"]) == 10
    cv = next(s for s in medical["scenarios"] if s["slug"] == "critical-value")
    assert cv["label_zh"] == "危急值" and cv["label_en"] == "Critical Value"
    assert cv["spec_path"] == "docs/medical/specs/critical-value.json"


def test_seed_does_not_duplicate_on_reinit(client):
    # 同一个库再建一次 app，种子不应翻倍
    store = client.app.state.store
    store.seed_scenarios()
    medical = next(d for d in store.list_scenario_tree() if d["slug"] == "medical")
    assert len(medical["scenarios"]) == 10


# ---- 域 / 场景 CRUD ------------------------------------------------------

def test_domain_and_scenario_crud(client):
    resp = client.post("/console/api/scenario-domains", json={
        "slug": "finance", "label_zh": "金融", "label_en": "Finance"})
    assert resp.status_code == 201, resp.text
    domain_id = resp.json()["id"]

    resp = client.post("/console/api/scenarios", json={
        "domain_id": domain_id, "slug": "risk", "label_zh": "风控",
        "label_en": "Risk", "spec_path": "docs/medical/specs/diagnosis.json"})
    assert resp.status_code == 201, resp.text
    scenario = resp.json()
    assert scenario["category"] == "medical"

    # 树含新域与新场景
    tree = _tree(client)
    finance = next(d for d in tree if d["slug"] == "finance")
    assert any(s["slug"] == "risk" for s in finance["scenarios"])

    # 更新标签
    resp = client.put(f"/console/api/scenarios/{scenario['id']}", json={
        "label_zh": "风险控制", "category": "finance"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["label_zh"] == "风险控制"
    assert resp.json()["category"] == "finance"

    # 删除场景后删域（级联）
    assert client.delete(f"/console/api/scenarios/{scenario['id']}").json()["deleted"]
    assert client.delete(f"/console/api/scenario-domains/{domain_id}").json()["deleted"]
    assert not any(d["slug"] == "finance" for d in _tree(client))


def test_scenario_slug_must_be_unique(client):
    domain_id = client.post("/console/api/scenario-domains", json={
        "slug": "edu", "label_zh": "教育", "label_en": "Education"}).json()["id"]
    payload = {"domain_id": domain_id, "slug": "dup", "label_zh": "重复",
               "label_en": "Dup", "spec_path": "docs/medical/specs/diagnosis.json"}
    assert client.post("/console/api/scenarios", json=payload).status_code == 201
    assert client.post("/console/api/scenarios", json=payload).status_code == 409


def test_validation_requires_labels_and_spec(client):
    domain_id = client.post("/console/api/scenario-domains", json={
        "slug": "law", "label_zh": "法律", "label_en": "Law"}).json()["id"]
    # 缺英文标签
    assert client.post("/console/api/scenarios", json={
        "domain_id": domain_id, "slug": "x", "label_zh": "X",
        "label_en": "", "spec_path": "docs/medical/specs/diagnosis.json"}).status_code == 400
    # 非 .json
    assert client.post("/console/api/scenarios", json={
        "domain_id": domain_id, "slug": "y", "label_zh": "Y", "label_en": "Y",
        "spec_path": "foo.txt"}).status_code == 400


# ---- spec 文件读写（沙箱在仓库根内） ------------------------------------

def test_spec_read_write_within_repo_root(client, tmp_path):
    # 指向仓库内的 gitignored 文件，避免改动源码
    spec_rel = "data/console/_test_spec.json"
    from kev.console import paths as _paths
    (_paths.ROOT / spec_rel).unlink(missing_ok=True)  # 幂等，避免重跑残留
    domain_id = client.post("/console/api/scenario-domains", json={
        "slug": "tst", "label_zh": "测试", "label_en": "Test"}).json()["id"]
    scenario = client.post("/console/api/scenarios", json={
        "domain_id": domain_id, "slug": "tspec", "label_zh": "规格",
        "label_en": "Spec", "spec_path": spec_rel}).json()

    # 文件尚不存在
    assert client.get(f"/console/api/scenarios/tspec/spec").status_code == 404

    good = '{"name":"t","domain":"d","state":"s","questions":{"q":{"type":"noul","instructions":"?"}}}'
    assert client.put(f"/console/api/scenarios/tspec/spec", json={"content": good}).json()["saved"]
    assert client.get(f"/console/api/scenarios/tspec/spec").json()["content"] == good

    # 非法 JSON 被拒
    assert client.put(f"/console/api/scenarios/tspec/spec",
                      json={"content": "{not json"}).status_code == 400
    # 缺必要字段被拒
    assert client.put(f"/console/api/scenarios/tspec/spec",
                      json={"content": '{"name":"x"}'}).status_code == 400

    # 清理（连同写出的 spec 文件，避免干扰重跑）
    client.delete(f"/console/api/scenarios/{scenario['id']}")
    client.delete(f"/console/api/scenario-domains/{domain_id}")
    from kev.console import paths as _paths
    (_paths.ROOT / spec_rel).unlink(missing_ok=True)


def test_spec_write_refuses_path_outside_repo(client):
    domain_id = client.post("/console/api/scenario-domains", json={
        "slug": "tst2", "label_zh": "测试", "label_en": "Test"}).json()["id"]
    scenario = client.post("/console/api/scenarios", json={
        "domain_id": domain_id, "slug": "tspec2", "label_zh": "规格",
        "label_en": "Spec", "spec_path": "data/console/_test_spec2.json"}).json()
    # 即便内容合法，路径若越界也应被拒；这里路径在根内但用绝对越界路径验证守卫
    # 通过直接写越界 spec_path 场景不可行（创建时已限 .json），故验证写入守卫：
    # 把场景 spec_path 改成越界后再写会触发 ValueError。
    from kev.console.db import store
    store().update_scenario(scenario["id"], spec_path="../escape.json")
    resp = client.put(f"/console/api/scenarios/tspec2/spec",
                      json={"content": '{"name":"t","domain":"d","state":"s","questions":{}}'})
    assert resp.status_code == 400
    client.delete(f"/console/api/scenarios/{scenario['id']}")
    client.delete(f"/console/api/scenario-domains/{domain_id}")


# ---- 自定义场景蒸馏走 spec 路径（解耦冻结的 CATEGORY_SPECS） ------------

def test_distill_build_passes_spec_path_for_custom_scenario(client):
    from kev.console.stages import data as d
    from kev.console.stages.base import JobRequest

    domain_id = client.post("/console/api/scenario-domains", json={
        "slug": "custom", "label_zh": "自定义", "label_en": "Custom"}).json()["id"]
    # 自定义 slug 不在 generate_data.py 的 CATEGORY_SPECS 里
    client.post("/console/api/scenarios", json={
        "domain_id": domain_id, "slug": "my-custom", "label_zh": "我的场景",
        "label_en": "My Custom", "spec_path": "docs/medical/specs/diagnosis.json"})

    built = d.distill.preview(JobRequest(
        scenario="my-custom", run_name="mc-v1",
        params={"skip_exists_check": True}))
    # 不再用 --category，而是把 spec 文件绝对路径作为位置参数
    assert "--category" not in built.argv
    assert str(built.argv[2]).endswith("diagnosis.json")


def test_distill_build_passes_examples_few_shot(client):
    """--examples / --n-examples 应透传到 generate_data.py（few-shot 风格范例）。"""
    from kev.console.stages import data as d
    from kev.console.stages.base import JobRequest

    base = {"skip_exists_check": True}
    # 不传 examples：argv 里不应出现该参数
    without = d.distill.preview(JobRequest(
        scenario="critical-value", run_name="cv-1", params=dict(base)))
    assert "--examples" not in without.argv
    assert "--n-examples" not in without.argv

    # 传 examples：两个参数都要透传，且 n_examples 可选覆盖
    with_ex = d.distill.preview(JobRequest(
        scenario="critical-value", run_name="cv-2",
        params={**base, "examples": "data/cv/train.jsonl", "n_examples": "6"}))
    assert flag(with_ex.argv, "--examples") == "data/cv/train.jsonl"
    assert flag(with_ex.argv, "--n-examples") == "6"

    # 只传 examples 时 n_examples 用默认 4
    default_n = d.distill.preview(JobRequest(
        scenario="critical-value", run_name="cv-3",
        params={**base, "examples": "data/cv/train.jsonl"}))
    assert flag(default_n.argv, "--n-examples") == "4"
