"""两级场景（域 / 场景）管理：种子、CRUD、双语、spec 文件读写、自定义场景蒸馏。

Run: uv run python -m pytest tests/test_console_scenarios.py -q
"""
import pytest

from fastapi.testclient import TestClient
from kev.console import scenario_specs
from kev.console.app import create_app
from kev.console.db import Store


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(store=Store(tmp_path / "db.sqlite"))) as c:
        yield c


def _tree(client):
    return client.get("/console/api/scenario-domains").json()


def _expected(domain_slug):
    """docs/domains/<domain>/specs 里应有的场景（清单来自 scenario_specs，测试不写死数字）。"""
    return [e for e in scenario_specs.entries() if e.domain.slug == domain_slug]


# write_spec_file 只收合法 spec（name/domain/state/questions 四件必非空）
STALE_SPEC = '{"name": "stale", "domain": "d", "state": "s", "questions": {"q": {"type": "noul"}}}'


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
    # 医疗场景全部落库（含 icd-coding）
    assert {"critical-value", "icd-coding", "triage"} <= slugs
    # 与 docs/domains/medical/specs 的文件清单一字不差
    assert len(medical["scenarios"]) == len(_expected("medical"))
    cv = next(s for s in medical["scenarios"] if s["slug"] == "critical-value")
    assert cv["label_zh"] == "危急值" and cv["label_en"] == "Critical Value"
    assert cv["spec_path"] == "docs/domains/medical/specs/critical-value.json"


def test_seed_registers_all_five_domains(client):
    """docs/domains 的五个领域全部登记，每个领域的场景数与 spec 文件数一致。"""
    tree = {d["slug"]: d for d in _tree(client)}
    assert {d.slug for d in scenario_specs.domains()} <= set(tree)
    for domain in scenario_specs.domains():
        row = tree[domain.slug]
        assert row["spec_dir"] == domain.spec_dir
        assert {s["slug"] for s in row["scenarios"]} == {e.slug for e in _expected(domain.slug)}


def test_seed_tracks_match_readme(client):
    """库里的 track 与 docs/domains/README.md §1 的「轨制」列一致（派生事实不靠注释）。"""
    listed = scenario_specs.readme_scenarios()
    rows = {s["slug"]: s for d in _tree(client) for s in d["scenarios"]}
    assert set(listed) <= set(rows)
    for slug, (domain, _label, track_text) in listed.items():
        assert rows[slug]["track"] == scenario_specs.README_TRACK[track_text], slug
    # 规则轨带生成器形态，蒸馏轨带 EasyDistill 配置路径
    for slug, row in rows.items():
        if row["track"] in ("rule", "both"):
            assert row["generator_kind"] in ("engine", "script"), slug
        if row["track"] in ("distill", "both"):
            assert row["distill_yaml"].endswith(".yaml"), slug


def test_seed_does_not_duplicate_on_reinit(client):
    # 同一个库再建一次 app，种子不应翻倍
    store = client.app.state.store
    store.seed_scenarios()
    medical = next(d for d in store.list_scenario_tree() if d["slug"] == "medical")
    assert len(medical["scenarios"]) == len(_expected("medical"))


def test_seed_force_overwrites_spec_and_keeps_history(client):
    """seed_scenarios(force=True) 以文件为准覆盖 spec_json，覆写前的库内内容进历史表。"""
    store = client.app.state.store
    entry = _expected("medical")[0]
    store.write_spec_file(entry.slug, STALE_SPEC)
    before = len(store.list_spec_history(entry.slug))
    stats = store.seed_scenarios(force=True)
    assert stats["specs_written"] >= 1
    assert store.get_scenario_by_slug(entry.slug)["spec_json"] == entry.content
    assert len(store.list_spec_history(entry.slug)) == before + 1


def test_seed_preserves_user_edits_without_force(client):
    """不带 force 时不覆盖用户改过的库内内容（seed 只刷派生列）。"""
    store = client.app.state.store
    slug = _expected("medical")[0].slug
    store.write_spec_file(slug, STALE_SPEC)
    store.seed_scenarios()
    assert store.get_scenario_by_slug(slug)["spec_json"] == STALE_SPEC


def test_migrate_v8_from_legacy_shape(tmp_path):
    """旧库（v7 结构 + 手工建的 research 域）重开即迁移：补五列、按别名认领、不插重复域。

    复现的是真实情形：旧库里科研域是用户手工建的，slug 叫 research（目录叫 science），
    域行与场景行都没有 v8 的 spec_dir/track/generator_kind/distill_yaml/origin。
    """
    import sqlalchemy as sa
    path = tmp_path / "legacy.sqlite"
    store = Store(path)
    store._conn().execute(sa.text(
        "UPDATE scenario_domains SET slug='research', label_zh='科研', spec_dir=''"
        " WHERE slug='science'"))
    for table, column in (("scenario_domains", "spec_dir"), ("scenarios", "track"),
                          ("scenarios", "generator_kind"), ("scenarios", "distill_yaml"),
                          ("scenarios", "origin")):
        store._conn().execute(sa.text(f"ALTER TABLE {table} DROP COLUMN {column}"))
    store._conn().execute(
        sa.text("UPDATE console_meta SET value='7' WHERE key='schema_version'"))
    store.engine.dispose()

    migrated = Store(path)          # 建表跳过（已存在），_migrate 补列 + 重新播种
    try:
        assert migrated.schema_version() == 11  # 迁移收敛到当前 SCHEMA_VERSION（v10 起含 distill_yaml_content，v11 起含 jobs.bundle_id）
        tree = {d["slug"]: d for d in migrated.list_scenario_tree()}
        # 认领旧行而不是新建一条同义域（不插重复域也不重命名用户的 slug）
        assert "research" in tree and "science" not in tree
        assert tree["research"]["spec_dir"] == "science"
        assert {s["slug"] for s in tree["research"]["scenarios"]} == {e.slug for e in _expected("science")}
        assert len(migrated.list_scenario_slugs()) == len(scenario_specs.entries())
        # 补回来的列全部重新填好（ALTER 只能给默认值，靠种子重算）
        assert all(s["track"] for d in tree.values() for s in d["scenarios"])
    finally:
        migrated.engine.dispose()


# ---- 域 / 场景 CRUD ------------------------------------------------------

def test_domain_and_scenario_crud(client):
    # 用未登记的领域 slug：finance 已由 docs/domains 种子建好（重复建会 409）
    resp = client.post("/console/api/scenario-domains", json={
        "slug": "retail", "label_zh": "零售", "label_en": "Retail"})
    assert resp.status_code == 201, resp.text
    domain_id = resp.json()["id"]

    resp = client.post("/console/api/scenarios", json={
        "domain_id": domain_id, "slug": "risk", "label_zh": "风控",
        "label_en": "Risk", "spec_path": "docs/domains/medical/specs/diagnosis.json"})
    assert resp.status_code == 201, resp.text
    scenario = resp.json()
    assert scenario["category"] == "medical"

    # 树含新域与新场景
    tree = _tree(client)
    retail = next(d for d in tree if d["slug"] == "retail")
    assert any(s["slug"] == "risk" for s in retail["scenarios"])

    # 更新标签
    resp = client.put(f"/console/api/scenarios/{scenario['id']}", json={
        "label_zh": "风险控制", "category": "retail"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["label_zh"] == "风险控制"
    assert resp.json()["category"] == "retail"

    # 删除场景后删域（级联）
    assert client.delete(f"/console/api/scenarios/{scenario['id']}").json()["deleted"]
    assert client.delete(f"/console/api/scenario-domains/{domain_id}").json()["deleted"]
    assert not any(d["slug"] == "retail" for d in _tree(client))


def test_domain_spec_dir_and_scenario_track(client):
    """建域可带 spec_dir，建/改场景可带轨制；track 只认四个值（留空 = 未判定）。"""
    resp = client.post("/console/api/scenario-domains", json={
        "slug": "retail2", "label_zh": "零售二", "label_en": "Retail2", "spec_dir": "retail2"})
    assert resp.status_code == 201, resp.text
    domain_id = resp.json()["id"]
    assert next(d for d in _tree(client) if d["slug"] == "retail2")["spec_dir"] == "retail2"

    payload = {"domain_id": domain_id, "slug": "tracked", "label_zh": "定轨",
               "label_en": "Tracked", "spec_path": "docs/domains/medical/specs/diagnosis.json"}
    assert client.post("/console/api/scenarios", json={**payload, "track": "nonsense"}).status_code == 400
    resp = client.post("/console/api/scenarios", json={**payload, "track": "distill",
                                                       "distill_yaml": "x/y.yaml"})
    assert resp.status_code == 201, resp.text
    scenario = resp.json()
    assert (scenario["track"], scenario["distill_yaml"]) == ("distill", "x/y.yaml")

    resp = client.put(f"/console/api/scenarios/{scenario['id']}", json={"track": "both"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["track"] == "both"
    # 空串是「清空未判定」，合法
    assert client.put(f"/console/api/scenarios/{scenario['id']}",
                      json={"track": ""}).json()["track"] == ""

    client.delete(f"/console/api/scenarios/{scenario['id']}")
    client.delete(f"/console/api/scenario-domains/{domain_id}")


def test_scenario_slug_must_be_unique(client):
    domain_id = client.post("/console/api/scenario-domains", json={
        "slug": "edu", "label_zh": "教育", "label_en": "Education"}).json()["id"]
    payload = {"domain_id": domain_id, "slug": "dup", "label_zh": "重复",
               "label_en": "Dup", "spec_path": "docs/domains/medical/specs/diagnosis.json"}
    assert client.post("/console/api/scenarios", json=payload).status_code == 201
    assert client.post("/console/api/scenarios", json=payload).status_code == 409


def test_validation_requires_labels_and_spec(client):
    domain_id = client.post("/console/api/scenario-domains", json={
        "slug": "legal", "label_zh": "法条", "label_en": "Legal"}).json()["id"]
    # 缺英文标签
    assert client.post("/console/api/scenarios", json={
        "domain_id": domain_id, "slug": "x", "label_zh": "X",
        "label_en": "", "spec_path": "docs/domains/medical/specs/diagnosis.json"}).status_code == 400
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
        "label_en": "My Custom", "spec_path": "docs/domains/medical/specs/diagnosis.json"})

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


# ---- 轨制 / 生成器列（任务 1）+ distill_yaml 内容列（任务 3） ------------

def _distill_scenario_with_file(store):
    """找一个 distill_yaml 路径指向真实仓库文件的种子场景，返回 (slug, rel)；无则 (None, None)。"""
    from kev.console import paths as _paths
    for domain in store.list_scenario_tree():
        for s in domain["scenarios"]:
            rel = s.get("distill_yaml")
            if rel and (_paths.ROOT / rel).is_file():
                return s["slug"], rel
    return None, None


def test_tree_rows_carry_track_and_generator_kind(client):
    """(a) list_scenario_tree 每行都带 track / generator_kind 键（前端徽标据此渲染）。"""
    store = client.app.state.store
    rows = [s for d in store.list_scenario_tree() for s in d["scenarios"]]
    assert rows
    for s in rows:
        assert "track" in s and "generator_kind" in s, s["slug"]
        # track 只可能是四值或空（未判定）
        assert s["track"] in ("rule", "distill", "both", "llm", ""), s["slug"]
        assert s["generator_kind"] in ("engine", "script", ""), s["slug"]


def test_seed_backfills_distill_yaml_content_from_file(client):
    """(b) distill_yaml_content 列存在，且 seed 从 distill_yaml 指向的仓库文件回填内容。"""
    store = client.app.state.store
    assert store._column_exists("scenarios", "distill_yaml_content")
    slug, rel = _distill_scenario_with_file(store)
    assert slug, "种子场景里应至少有一个带真实 distill_yaml 文件的蒸馏轨场景"
    from kev.console import paths as _paths
    file_text = (_paths.ROOT / rel).read_text(encoding="utf-8")
    # seed 已把文件内容写进内容列；read 优先返回 DB 内容
    assert store.get_scenario_by_slug(slug)["distill_yaml_content"] == file_text
    assert store.read_distill_yaml(slug) == file_text


def test_read_distill_yaml_falls_back_to_file_then_empty(client):
    """内容列清空后 read 回退读仓库文件；无 distill_yaml 路径的场景返回空串且不抛。"""
    import sqlalchemy as sa
    from kev.console import paths as _paths
    store = client.app.state.store
    slug, rel = _distill_scenario_with_file(store)
    assert slug
    store._conn().execute(
        sa.text("UPDATE scenarios SET distill_yaml_content=NULL WHERE slug=:s"), {"s": slug})
    assert store.read_distill_yaml(slug) == (_paths.ROOT / rel).read_text(encoding="utf-8")
    # 非蒸馏轨场景（distill_yaml 为空）读内容为空串
    rule_slug = next((s["slug"] for d in store.list_scenario_tree()
                      for s in d["scenarios"] if not s.get("distill_yaml")), None)
    assert rule_slug and store.read_distill_yaml(rule_slug) == ""


def test_distill_yaml_roundtrip_validation_and_404(client):
    """(c) GET/PUT distill-yaml 往返一致；非法 YAML 被拒 400 且不落库；未知场景 404。"""
    store = client.app.state.store
    slug, _ = _distill_scenario_with_file(store)
    assert slug
    good = "job_type: advanced_instruct_distill\nbackend:\n  type: openai\n  model: m\nresume: true\n"
    resp = client.put(f"/console/api/scenarios/{slug}/distill-yaml", json={"content": good})
    assert resp.status_code == 200 and resp.json()["saved"], resp.text
    body = client.get(f"/console/api/scenarios/{slug}/distill-yaml").json()
    assert body["slug"] == slug and body["content"] == good
    assert body["path"].endswith(".yaml")
    # 非法 YAML -> 400 validation（field=content），原内容不变
    bad = client.put(f"/console/api/scenarios/{slug}/distill-yaml", json={"content": "a: b: c: [unclosed"})
    assert bad.status_code == 400
    assert bad.json()["error"]["kind"] == "validation" and bad.json()["error"]["field"] == "content"
    assert client.get(f"/console/api/scenarios/{slug}/distill-yaml").json()["content"] == good
    # 未知场景 -> 404
    assert client.get("/console/api/scenarios/__nope__/distill-yaml").status_code == 404
    assert client.put("/console/api/scenarios/__nope__/distill-yaml",
                      json={"content": "a: 1"}).status_code == 404


def test_write_distill_yaml_idempotent_and_not_overwritten_by_reseed(client):
    """(d) write 幂等；用户编辑过的内容不被 seed（非 force）覆盖。"""
    store = client.app.state.store
    slug, _ = _distill_scenario_with_file(store)
    assert slug
    edited = "job_type: custom_edited\nresume: false\n"
    store.write_distill_yaml(slug, edited)
    assert store.read_distill_yaml(slug) == edited
    store.write_distill_yaml(slug, edited)  # 幂等
    assert store.read_distill_yaml(slug) == edited
    store.seed_scenarios()  # 非 force：不覆盖已编辑内容
    assert store.read_distill_yaml(slug) == edited


def test_write_distill_yaml_rejects_invalid(client):
    """write_distill_yaml 对非法 YAML 抛 ValueError，且不改动原内容。"""
    store = client.app.state.store
    slug, _ = _distill_scenario_with_file(store)
    assert slug
    before = store.read_distill_yaml(slug)
    with pytest.raises(ValueError):
        store.write_distill_yaml(slug, ":\n  - a: [unclosed")
    assert store.read_distill_yaml(slug) == before


def test_distill_yaml_file_materializes_db_content(client):
    """物化：DB 内容写到 data/console/distill-configs/<slug>.yaml（镜像 spec_file_path）。"""
    store = client.app.state.store
    slug, _ = _distill_scenario_with_file(store)
    assert slug
    edited = "job_type: materialized\nresume: true\n"
    store.write_distill_yaml(slug, edited)
    path = store.distill_yaml_file(slug)
    try:
        assert path is not None and path.name == f"{slug}.yaml"
        assert path.read_text(encoding="utf-8") == edited
    finally:
        if path is not None:
            path.unlink(missing_ok=True)
