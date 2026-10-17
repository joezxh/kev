# Project Hub Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give every job a project, let a project carry its scenario, and surface a project's real training history in a new `/studio/projects/{id}` detail page backed by project-scoped read APIs.

**Architecture:** This is the vertical slice of the Project Hub spec that turns `projects` from a billing root into a pipeline root for *training information only*. It lands the schema §4.1 column upgrade (`jobs.project_id` + `projects.status/scenario/goal/archived_at/freeze_*`), makes `Store.create_job` require a non-empty `project_id` (D14), adds project-scoped reads (`GET /jobs?project=`, project summary, project artifacts, project events), then replaces the mock-free frontend with a five-tab detail page that reads those APIs. The data-curation subsystem (`artifact_versions`, `bundles`/`bundle_members`, `record_reviews`, `project_releases`, the `materialize` stage, the F1–F4 freeze execution, and the merge/review tabs) is **out of scope** — it is a follow-on plan and would ship empty tables no task here reads.

**Tech Stack:** Python 3.12/3.13, SQLAlchemy Core + hand-written SQL (sqlite + postgres dual-dialect), FastAPI (`console_router` under `/console/api/*`), pytest + `TestClient`. Frontend: Next.js 16 App Router (React 19), `playground/src/lib/console.ts` API client, shadcn/ui + Tailwind v4, Node built-in test runner (`node --test --experimental-strip-types`) for pure helpers — no vitest.

**Spec:** `docs/superpowers/specs/2026-10-16-project-hub-design.md` — this plan implements §4.1, §5 (project/job rows), §7 (detail page + console mount) and the PR4 slice of §8, under decisions D1, D11 (columns only), D12, D14. Argue from the spec; do not re-transcribe it.

## 实现状态（2026-10-17 核对：全部已落地，代码无需改动）

本计划的 9 个 Task 均已在 checkout 实测确认落地、`tests/test_console_db.py` + `tests/test_console_api.py` = 56 passed：
§4.1 列（`jobs.project_id` + `projects` 六列 + `jobs_project_idx`）、`create_job` 必填 `project_id`（TypeError-vs-ValueError）、`POST/GET /jobs?project=`、场景一致守卫、`retry_job` 保留 `project_id`、`create_project/update_project/scenario_known/project_summary/project_events/list_project_artifacts`、`console.ts`（`Project/ProjectSummary/Event` + `api.project/projectArtifacts/projectEvents/createProject`）、`project-context.ts`(+test)、`ProjectSwitcher` 持久化、`console/layout.tsx` 挂 switcher、`JobStagePage` 未选项目置灰、`studio/projects/[id]` 5-tab + `selectors.ts`(+test)、`projects/page.tsx` 链接——全部就位。

**唯一文档漂移：schema 版本号。** 本计划写「`SCHEMA_VERSION` 6 → 7 / `== 7`」在当时的确如此；§4.1 列确实由 **v7** 落库。但 v7 之后合入了一条与本设计**无关**的 **v8** 迁移（`scenario_domains.spec_dir` + `scenarios.{track,generator_kind,distill_yaml,origin}`，见 `db.py` `_migrate` 的 `if version < 8:` 块）。故当前 `db.py:27` 是 `SCHEMA_VERSION = 8`，实际测试也断言 `store.schema_version() == 8`（`test_console_db.py:354`，其注释区分 v7/v8）。下文 Task 1 里 `== 7` 的测试片段是写作时的原样，现已被 `== 8` 取代，不代表实现有出入。**本计划的数据策展新表（`artifact_versions`/`bundles`/`record_reviews`/`project_releases` 等）因此应落 v9**——该更正与后续计划在 `2026-10-16-project-hub-v7-implementation.md` §0 已详述。


## Global Constraints

- Test invocation: backend `uv run python -m pytest tests/<file> -q`; frontend pure helper `npm run test:console`; page/wiring `npm run lint` then `npm run build`.
- Dual dialect: schema columns that need a float go through `_ddl`'s `real` value (sqlite `REAL` / postgres `DOUBLE PRECISION`); never hardcode one dialect in a migration `ALTER`.
- Idempotent migration: bump `SCHEMA_VERSION` 6 → 7; new columns appear in **both** the `_ddl` `CREATE TABLE` (fresh DBs) and a `if version < 7:` block in `_migrate` guarded by `_column_exists` (existing DBs). Opening `Store()` twice on the same path is a no-op.
- `jobs.project_id` is `TEXT NOT NULL DEFAULT ''`; `''` is the **named legacy sentinel**, never a project (D14). No backfill of existing `data/critical-value/`.
- `Store.create_job`: `project_id` is a **keyword-only, no-default** parameter; missing → `TypeError`, empty/None → `ValueError` (raised inside the method). This is the real constraint, stronger than the DB default.
- `POST /jobs`: `project_id` missing or empty → **400** `field="project_id"` (no exception, no "old call still 200"). Unknown `project_id` → **404**. Job `scenario` ≠ project `scenario` → **409**; project `scenario == ''` → **409**.
- `POST /projects`: `scenario` is required and must exist in the `scenarios` table, else **400** `field="scenario"`.
- One project = one scenario, one round (D1). `/console/*` stays the only write surface and becomes project-aware (D12); the current project id is shared between `/studio` and `/console` through one `localStorage` key.
- Error bodies use the existing `_error(kind, message, *, status, field, hint)` / `_job_error` shapes — never invent a new response envelope.
- Do not modify `kev/{train,benchmark,compare,calibrate,suite}.py` (P6).

## Review Focus

These are failure modes the spec implies but no single happy-path test pins; each gets its assertion added to the owning task.

- **Ghost project**: `POST /jobs` with a `project_id` that is not in `projects` must be refused (404), not silently attached — the alternative is P1's 100% built on dangling rows. (Task 2)
- **Two different refusals**: `create_job` missing `project_id` (`TypeError`) vs `project_id=''` (`ValueError`) are distinct; a caller cannot satisfy "belongs to a project" by passing empty. (Task 2)
- **Legacy invisibility**: a `project_id=''` row appears only under `?project=legacy` and under "all", never inside a concrete project's list. (Task 2)
- **Upgrade is boring**: applying v7 to a database that already has v6 rows must leave every existing job readable (`get_job` returns `project_id == ''`) and every pre-existing test green. (Task 1)
- **One key, two faces**: the project shown on `/studio/projects/{id}` and the project a `/console` submission writes into are the same because both read one `localStorage` key; a second key would let them diverge. (Tasks 7 & 8)

---

### Task 1: Schema v7 — the §4.1 column upgrade

**Files:**
- Modify: `kev/console/db.py` (`SCHEMA_VERSION`, `_ddl` jobs + projects tables, `_ROW_COLUMNS`, `_migrate`)
- Test: `tests/test_console_db.py`

**Interfaces:**
- Consumes: nothing (first task).
- Produces: `jobs.project_id TEXT NOT NULL DEFAULT ''` + `CREATE INDEX jobs_project_idx ON jobs(project_id, created_at DESC)`; `projects.status TEXT NOT NULL DEFAULT 'active'`, `projects.scenario TEXT NOT NULL DEFAULT ''`, `projects.goal TEXT NOT NULL DEFAULT ''`, `projects.archived_at TEXT`, `projects.freeze_min_records INTEGER NOT NULL DEFAULT 300`, `projects.freeze_min_review_ratio {real} NOT NULL DEFAULT 0.10`. `SCHEMA_VERSION == 7`. `_ROW_COLUMNS` gains `"project_id"` (so `get_job`/`list_jobs` project rows carry it). `create_job` is **unchanged** in this task — its INSERT omits `project_id`, so both dialects apply the `DEFAULT ''` and existing callers stay green.

- [ ] **Step 1: Write the failing test** — in `tests/test_console_db.py`, add

```python
def test_schema_v7_adds_project_columns(store):
    assert store.schema_version() == 7
    assert store._column_exists("jobs", "project_id")
    for col in ("status", "scenario", "goal", "archived_at",
                "freeze_min_records", "freeze_min_review_ratio"):
        assert store._column_exists("projects", col)

def test_new_job_defaults_to_legacy_sentinel(store):
    job_id = store.create_job(  # still no project_id kwarg in this task
        kind="train", stage="train", scenario="triage", title="t", request={},
        argv=["x"], env_overlay={}, cwd=".", log_path="l.log",
        artifacts_in=[], artifacts_out=[])
    assert store.get_job(job_id)["project_id"] == ""

def test_store_reopens_idempotently(tmp_path):
    path = tmp_path / "kev-console.db"
    first = Store(path)
    version = first.schema_version()
    second = Store(path)
    assert second.schema_version() == version == 7
```

- [ ] **Step 2: Run test to verify it fails** — `uv run python -m pytest tests/test_console_db.py -k "v7 or legacy_sentinel or idempotent" -v` → FAIL (`schema_version() == 6`, `_column_exists` False).
- [ ] **Step 3: Implement** — set `SCHEMA_VERSION = 7`. In `_ddl`, add `project_id TEXT NOT NULL DEFAULT ''` to the `jobs` table and the six columns to `projects`; add `CREATE INDEX IF NOT EXISTS jobs_project_idx ON jobs(project_id, created_at DESC);`. In `_migrate`, add a `if version < 7:` block that, for each of the six `projects` columns and the `jobs.project_id` column, checks `_column_exists` before issuing `ALTER TABLE ... ADD COLUMN ...` inside `with self.engine.begin()`; use `real = "DOUBLE PRECISION" if self.backend.startswith("postgres") else "REAL"` for `freeze_min_review_ratio`; the index uses `CREATE INDEX IF NOT EXISTS`. Add `"project_id"` to `_ROW_COLUMNS`. Follow the exact style of the existing `version < 5` / `version < 6` blocks.
- [ ] **Step 4: Run test to verify it passes** — `uv run python -m pytest tests/test_console_db.py -q` → PASS (all, incl. the pre-existing create_job/state-machine tests).
- [ ] **Step 5: Commit** — `git add kev/console/db.py tests/test_console_db.py && git commit -m "feat(console): schema v7 — jobs.project_id + project columns (§4.1)"`

---

### Task 2: Every job belongs to a project — Store, submit path, project filter

**Files:**
- Modify: `kev/console/db.py` (`create_job`, `list_jobs`), `kev/console/stages/base.py` (`JobRequest`), `kev/console/app.py` (`_spawn`, `submit_job`, `get_jobs`, `retry_job`)
- Test: `tests/test_console_db.py`, `tests/test_console_api.py`

**Interfaces:**
- Consumes: `jobs.project_id` column + `projects` table (Task 1).
- Produces:
  - `Store.create_job(self, *, project_id, kind, stage, scenario, title, request, argv, env_overlay, cwd, log_path, artifacts_in, artifacts_out, parent_id=None, attempt=1, daemon_id=None, template_id=None) -> str` — `project_id` is keyword-only with **no default**; raises `ValueError` if falsy or `''`; INSERT writes it.
  - `Store.list_jobs(self, *, status=None, stage=None, scenario=None, project=None, limit=200) -> list[dict]` — `project=<id>` filters `project_id = :project`; `project="legacy"` filters `project_id = ''`; `project=None` returns all.
  - `JobRequest` gains `project_id: str = Field(default="")`.
  - `POST /console/api/jobs` — 400 `field="project_id"` when missing/empty; 404 when the project row does not exist. `GET /console/api/jobs?project=` accepted. `retry_job` preserves `job["project_id"]`.

- [ ] **Step 1: Write the failing Store tests** — in `tests/test_console_db.py`:

```python
def test_create_job_requires_project_id(store):
    pid = store.create_project("p", "P")
    with pytest.raises(TypeError):  # missing keyword
        store.create_job(kind="train", stage="train", scenario="triage", title="t",
            request={}, argv=["x"], env_overlay={}, cwd=".", log_path="l.log",
            artifacts_in=[], artifacts_out=[])
    with pytest.raises(ValueError):  # empty sentinel is not a project
        store.create_job(project_id="", kind="train", stage="train", scenario="triage",
            title="t", request={}, argv=["x"], env_overlay={}, cwd=".", log_path="l.log",
            artifacts_in=[], artifacts_out=[])
    job_id = store.create_job(project_id=pid, kind="train", stage="train",
        scenario="triage", title="t", request={}, argv=["x"], env_overlay={}, cwd=".",
        log_path="l.log", artifacts_in=[], artifacts_out=[])
    assert store.get_job(job_id)["project_id"] == pid

def test_list_jobs_filters_by_project(store):
    a, b = store.create_project("a", "A"), store.create_project("b", "B")
    def kw(pid, title):
        return dict(project_id=pid, kind="train", stage="train", scenario="triage",
            title=title, request={}, argv=["x"], env_overlay={}, cwd=".",
            log_path="l.log", artifacts_in=[], artifacts_out=[])
    store.create_job(**kw(a, "a1")); store.create_job(**kw(b, "b1"))
    assert {j["title"] for j in store.list_jobs(project=a)} == {"a1"}
    assert store.list_jobs(project=a) and all(j["project_id"] == a for j in store.list_jobs(project=a))
```

- [ ] **Step 2: Run to verify fail** — `uv run python -m pytest tests/test_console_db.py -k "requires_project_id or filters_by_project" -v` → FAIL (`TypeError: unexpected keyword` / filter ignored).
- [ ] **Step 3: Implement Store side** — make `project_id` the first keyword-only param of `create_job` (no default), `raise ValueError("project_id 必填")` when `not project_id`, and add `project_id` to the INSERT column list and bind dict. Add the `project` clause to `list_jobs` following the existing `(column, value)` loop, mapping the literal `"legacy"` to `''`. Then update every existing `store.create_job(...)` call in `tests/test_console_db.py` to pass `project_id=store.create_project(...)` (add a `project_id` fixture returning `store.create_project("fx", "Fx")`).
- [ ] **Step 4: Run Store tests to verify pass** — `uv run python -m pytest tests/test_console_db.py -q` → PASS.
- [ ] **Step 5: Wire the submit path** — add `project_id: str = Field(default="")` to `JobRequest`. In `app.py::_spawn`, pass `project_id=request.project_id` to all three `store.create_job(...)` calls (service-binding, daemon, Popen). In `submit_job`, before `_spawn`, when `not (payload.get("project_id") or "").strip()` return `_error("validation", "project_id 必填", status=400, field="project_id")`; when `store.get_project(payload["project_id"])` is None return `_error("validation", f"未知项目 {payload['project_id']}", status=404)`. In `get_jobs`, accept `project: str | None = None` and forward to `list_jobs`. In `retry_job`, add `"project_id": job["project_id"]` to the rebuilt `payload`.
- [ ] **Step 6: Write the failing API tests** — in `tests/test_console_api.py`, extend the `submit` helper to accept a project and add cases:

```python
def _mk_project(client, slug="cv", name="CV"):
    r = client.post("/console/api/projects", json={"slug": slug, "name": name})
    assert r.status_code in (200, 201)
    return r.json()["id"]

def test_submit_requires_project(client):
    r = client.post("/console/api/jobs", json={"kind": "train", "scenario": "triage",
        "run_name": "cv-1", "params": {}})
    assert r.status_code == 400 and r.json()["error"]["field"] == "project_id"

def test_submit_unknown_project(client):
    r = client.post("/console/api/jobs", json={"kind": "train", "scenario": "triage",
        "run_name": "cv-1", "params": {}, "project_id": "does-not-exist"})
    assert r.status_code == 404

def test_submit_lists_by_project(client):
    pid = _mk_project(client)
    r = client.post("/console/api/jobs", json={"kind": "train", "scenario": "triage",
        "run_name": "cv-1", "params": {}, "project_id": pid})
    assert r.status_code == 200
    listed = client.get(f"/console/api/jobs?project={pid}").json()
    assert [j["id"] for j in listed] == [r.json()["id"]]
```

Update the existing `submit()` helper and `make_job(store, ...)` in `tests/test_console_api.py` to pass a real `project_id` (create a project on the store first), so pre-existing submit/SSE tests stay green.
- [ ] **Step 7: Run API tests to verify pass** — `uv run python -m pytest tests/test_console_api.py -q` → PASS.
- [ ] **Step 8: Commit** — `git add kev/console/db.py kev/console/stages/base.py kev/console/app.py tests/test_console_db.py tests/test_console_api.py && git commit -m "feat(console): jobs belong to a project; create_job requires project_id (D14)"`

---

### Task 3: Projects carry their scenario — create/update + `POST /projects` validation

**Files:**
- Modify: `kev/console/db.py` (`create_project`, `update_project`, add `scenario_known`), `kev/console/app.py` (`create_project` route, `update_project` route)
- Test: `tests/test_console_db.py`, `tests/test_console_api.py`

**Interfaces:**
- Consumes: `projects.scenario/status/goal/archived_at/freeze_*` columns + the `scenarios` table (Task 1, existing).
- Produces:
  - `Store.create_project(self, slug, name, description="", scenario="", status="active", goal="", freeze_min_records=300, freeze_min_review_ratio=0.10) -> str` — writes the new columns.
  - `Store.update_project(self, project_id, *, name=None, slug=None, description=None, scenario=None, status=None, goal=None, archived_at=None, freeze_min_records=None, freeze_min_review_ratio=None) -> dict | None` — sets only provided fields; returns the updated row.
  - `Store.scenario_known(self, slug: str) -> bool` — `SELECT 1 FROM scenarios WHERE slug = :slug` (the `scenarios` table is keyed by slug; if the column differs, read the real name from the existing scenarios route before writing).
  - `POST /console/api/projects` — 400 `field="scenario"` when `scenario` is empty or `not scenario_known(scenario)`; otherwise 201 with the project row (now including `scenario/status/goal/freeze_*`).

- [ ] **Step 1: Write the failing Store test** — in `tests/test_console_db.py`:

```python
def test_create_project_persists_scenario(store):
    pid = store.create_project("cv-2026-10", "CV Oct", scenario="critical-value", goal="ship")
    p = store.get_project(pid)
    assert p["scenario"] == "critical-value" and p["goal"] == "ship"
    assert p["status"] == "active" and p["freeze_min_records"] == 300
```

- [ ] **Step 2: Run to verify fail** — `uv run python -m pytest tests/test_console_db.py -k persists_scenario -v` → FAIL (`TypeError: unexpected keyword 'scenario'`).
- [ ] **Step 3: Implement Store** — extend `create_project` to bind the new columns (keep positional `slug, name, description` for back-compat); extend `update_project` with the new optional fields using the existing `sets/params` pattern; add `scenario_known(slug)`. Read the existing `scenarios` table shape from `db.py` before assuming its key column.
- [ ] **Step 4: Run Store test to verify pass** — `uv run python -m pytest tests/test_console_db.py -k persists_scenario -v` → PASS.
- [ ] **Step 5: Write the failing API test** — in `tests/test_console_api.py`:

```python
def test_create_project_requires_known_scenario(client):
    missing = client.post("/console/api/projects", json={"slug": "s", "name": "S"})
    assert missing.status_code == 400 and missing.json()["error"]["field"] == "scenario"
    unknown = client.post("/console/api/projects", json={"slug": "s", "name": "S", "scenario": "nope"})
    assert unknown.status_code == 400
```

- [ ] **Step 6: Implement route** — in `create_project`, after slug/name checks, require `scenario` present and `store.scenario_known(scenario)`, else `_error(..., status=400, field="scenario", hint="场景必须已存在")`; pass `scenario`/`goal`/`description` into `store.create_project`. Allow `update_project` route to forward the new optional keys.
- [ ] **Step 7: Run to verify pass** — `uv run python -m pytest tests/test_console_api.py -k requires_known_scenario -v` → PASS.
- [ ] **Step 8: Commit** — `git add kev/console/db.py kev/console/app.py tests/test_console_db.py tests/test_console_api.py && git commit -m "feat(console): projects carry a required, known scenario (D1)"`

---

### Task 4: Cross-project scenario guard on submission

**Files:**
- Modify: `kev/console/app.py` (`submit_job`, `retry_job`)
- Test: `tests/test_console_api.py`

**Interfaces:**
- Consumes: `submit_job`'s existing 400/404 project checks (Task 2) and `project["scenario"]` (Task 3).
- Produces: in `submit_job`, after the project is confirmed to exist: when `project["scenario"] == ""` return 409 (`先给项目补上场景再提交`); when the job's `scenario` (from `payload`/`JobRequest`) ≠ `project["scenario"]` return 409. `retry_job` inherits the same guard because it re-runs `submit_job`'s validation path.

- [ ] **Step 1: Write the failing test** — in `tests/test_console_api.py` (create a scenario via the existing scenario route or a `store.create_scenario` helper, then a project bound to it):

```python
def test_submit_rejects_scenario_mismatch(client):
    client.post("/console/api/scenarios", json={...})          # a real, existing scenario "aaa"
    pid = client.post("/console/api/projects", json={"slug": "p", "name": "P", "scenario": "aaa"}).json()["id"]
    r = client.post("/console/api/jobs", json={"kind": "train", "scenario": "bbb",
        "run_name": "cv-1", "params": {}, "project_id": pid})
    assert r.status_code == 409

def test_submit_rejects_project_without_scenario(client):
    # legacy project: scenario == '' (e.g. created before D1, scenario left blank)
    pid = client.app.state.store.create_project("legacy", "Legacy")  # scenario defaults to ''
    r = client.post("/console/api/jobs", json={"kind": "train", "scenario": "triage",
        "run_name": "cv-1", "params": {}, "project_id": pid})
    assert r.status_code == 409
```

- [ ] **Step 2: Run to verify fail** — `uv run python -m pytest tests/test_console_api.py -k "scenario_mismatch or without_scenario" -v` → FAIL (returns 200).
- [ ] **Step 3: Implement** — in `submit_job`, fetch `project = store.get_project(payload["project_id"])` (already fetched for the 404 check); after that, `if not project["scenario"]: return _error("conflict", ..., status=409, hint="先补场景")`; `if request.scenario != project["scenario"]: return _error("conflict", f"作业场景 {request.scenario} 与项目场景 {project['scenario']} 不一致", status=409)`. Place both before `_spawn`.
- [ ] **Step 4: Run to verify pass** — `uv run python -m pytest tests/test_console_api.py -k "scenario_mismatch or without_scenario" -v` → PASS.
- [ ] **Step 5: Commit** — `git add kev/console/app.py tests/test_console_api.py && git commit -m "feat(console): job scenario must match its project (D1)"`

---

### Task 5: Project-scoped reads — summary, artifacts, events

**Files:**
- Modify: `kev/console/db.py` (`project_summary`, `list_project_artifacts`, `project_events`), `kev/console/app.py` (`get_project` route, add `GET /projects/{id}/artifacts`, `GET /projects/{id}/events`)
- Test: `tests/test_console_db.py`, `tests/test_console_api.py`

**Interfaces:**
- Consumes: `list_jobs(project=)` (Task 2), `artifacts`/`lineage`/`events` tables (existing), `get_artifact` (existing, `db.py:735`).
- Produces:
  - `Store.project_events(self, project_id, *, after_id=0, limit=200) -> list[dict]` — `SELECT events.* FROM events JOIN jobs ON events.job_id = jobs.id WHERE jobs.project_id = :p AND events.id > :after_id ORDER BY events.id` (cursor semantics match `read_events`; `events.id` is the global autoincrement, so cross-job ordering is natural — D10).
  - `Store.list_project_artifacts(self, project_id) -> list[dict]` — distinct artifact ids across the project's jobs' `artifacts_in + artifacts_out`, resolved via `get_artifact`, `None`s dropped. No new table (D2: attribution flows `jobs.project_id`, not an `artifacts.project_id` column).
  - `Store.project_summary(self, project_id) -> dict | None` — `get_project` row **plus** `jobs` count, `artifacts` count, `recent_events` (last 5 via `project_events`), `stages` = `{stage: last job status}` over the project's jobs, and the `freeze_*` policy fields. Keeps every original column so existing `api.project(id)` callers still read `slug/name/description`.
  - Routes: `GET /console/api/projects/{id}` returns `project_summary`; `GET /console/api/projects/{id}/artifacts`; `GET /console/api/projects/{id}/events?after_id=`.

- [ ] **Step 1: Write the failing Store test** — in `tests/test_console_db.py`:

```python
def test_project_reads_are_scoped(store):
    a, b = store.create_project("a", "A"), store.create_project("b", "B")
    common = dict(kind="train", stage="train", scenario="triage", title="t",
        request={}, argv=["x"], env_overlay={}, cwd=".", log_path="l.log",
        artifacts_in=[], artifacts_out=["dataset:a/train"])
    ja = store.create_job(project_id=a, **common)
    store.create_job(project_id=b, kind="train", stage="train", scenario="triage",
        title="t", request={}, argv=["x"], env_overlay={}, cwd=".", log_path="l.log",
        artifacts_in=[], artifacts_out=["dataset:b/train"])
    store.append_events(ja, [("log", "hello")])
    summary = store.project_summary(a)
    assert summary["jobs"] == 1 and summary["stages"]["train"]
    assert store.project_events(a) and not store.project_events(b)
    arts = store.list_project_artifacts(a)  # only a's outputs resolve
```

- [ ] **Step 2: Run to verify fail** — `uv run python -m pytest tests/test_console_db.py -k project_reads_are_scoped -v` → FAIL (`AttributeError`).
- [ ] **Step 3: Implement Store methods** — `project_events` (JOIN, cursor), `list_project_artifacts` (set of ids over `list_jobs(project=project_id, limit=None-or-large)`, resolve, drop `None`), `project_summary` (compose `get_project` + the three counts + `recent_events` + `stages`). Mirror existing read style (`self._conn().execute(text(...)).mappings()`).
- [ ] **Step 4: Run Store test to verify pass** — `uv run python -m pytest tests/test_console_db.py -k project_reads_are_scoped -v` → PASS.
- [ ] **Step 5: Write the failing API test + wire routes** — add `GET /console/api/projects/{id}/artifacts` and `GET /console/api/projects/{id}/events` routes delegating to the new Store methods (404 via `_error` when `get_project` is None), and change `get_project` to return `store.project_summary(project_id)`. Test:

```python
def test_project_events_endpoint(client):
    pid = client.app.state.store.create_project("a", "A", scenario="")  # scenario check not on this path
    # seed a job + event, then:
    r = client.get(f"/console/api/projects/{pid}/events")
    assert r.status_code == 200 and "events" in r.json()
```

- [ ] **Step 6: Run to verify pass** — `uv run python -m pytest tests/test_console_api.py -k project_events_endpoint -v` → PASS.
- [ ] **Step 7: Commit** — `git add kev/console/db.py kev/console/app.py tests/test_console_db.py tests/test_console_api.py && git commit -m "feat(console): project summary + project-scoped artifacts/events reads"`

---

### Task 6: Frontend API client — types and project-scoped methods

**Files:**
- Modify: `playground/src/lib/console.ts`
- Test: none at runtime (types-only + thin `fetch` wrappers; verified by `npm run build`). If a query-string helper is extracted, add `playground/src/lib/console.test.ts` (node:test) for it.

**Interfaces:**
- Consumes: the API shapes from Tasks 2–5.
- Produces:
  - `Project` type += `scenario: string; status: string; goal: string; archived_at: string | null; freeze_min_records: number; freeze_min_review_ratio: number;` (plus existing fields).
  - `ProjectSummary = Project & { jobs: number; artifacts: number; recent_events: Event[]; stages: Record<string, JobStatus>; }`.
  - `api.jobs(filter)` accepts `project?: string` (added to the `URLSearchParams` entries).
  - `api.project(id) -> ProjectSummary`; new `api.projectArtifacts(id)`, `api.projectEvents(id, afterId?)`.
  - `api.submit(payload)` payload type += `project_id: string` (required). `api.createProject(p)` `p` type += `scenario: string; goal?: string`.

- [ ] **Step 1: Add the `project` filter to `api.jobs`** — extend the filter union with `project?: string`; no behavior change when absent.
- [ ] **Step 2: Extend types + add methods** — update `Project`, add `ProjectSummary`, change `api.project` return type, add `api.projectArtifacts` / `api.projectEvents`, add `project_id` to the `submit` payload type and `scenario`/`goal` to `createProject`.
- [ ] **Step 3: Verify it compiles** — `npm run lint && npm run build` (from `playground/`) → PASS (no type errors). If the client `call` proxy needs an `events`/`artifacts` route path, confirm they match the FastAPI paths added in Task 5.
- [ ] **Step 4: Commit** — `git add playground/src/lib/console.ts && git commit -m "feat(playground): project-scoped API client methods + summary types"`

---

### Task 7: Shared project context — `localStorage` persistence

**Files:**
- Create: `playground/src/lib/project-context.ts`, `playground/src/lib/project-context.test.ts`
- Modify: `playground/src/components/studio/ProjectSwitcher.tsx`

**Interfaces:**
- Consumes: nothing from prior frontend tasks (self-contained).
- Produces:
  - `const PROJECT_STORAGE_KEY = "kev.project.id"` (the single key `/studio` and `/console` share).
  - `readSelectedProject(): string | null`, `writeSelectedProject(id: string | null): void` — both no-op-safe when `window` is undefined (SSR), matching the `typeof window !== "undefined"` guard pattern already in `i18n.tsx` and the usage page.
  - `useSelectedProject(): [string | null, (id: string) => void]` — reads on mount, writes through the helper.
  - `ProjectSwitcher` calls `writeSelectedProject` inside `onChange` so the dropdown persists across pages.

- [ ] **Step 1: Write the failing helper test** — `playground/src/lib/project-context.test.ts`:

```ts
import assert from "node:assert/strict";
import { describe, it, beforeEach } from "node:test";
import { PROJECT_STORAGE_KEY, readSelectedProject, writeSelectedProject } from "./project-context.ts";

describe("project-context", () => {
  beforeEach(() => {
    const mem = new Map<string, string>();
    (globalThis as any).window = {
      localStorage: { getItem: (k: string) => mem.get(k) ?? null,
                      setItem: (k: string, v: string) => mem.set(k, v) },
    };
  });
  it("round-trips the selected project through one key", () => {
    writeSelectedProject("abc");
    assert.equal(readSelectedProject(), "abc");
    assert.equal(PROJECT_STORAGE_KEY, "kev.project.id");
  });
  it("is SSR-safe (no window)", () => {
    delete (globalThis as any).window;
    assert.equal(readSelectedProject(), null);
    writeSelectedProject("x"); // must not throw
  });
});
```

- [ ] **Step 2: Run to verify fail** — `npm run test:console` → FAIL (module not found).
- [ ] **Step 3: Implement `project-context.ts`** — the key, the two pure helpers with the `typeof window` guard, and `useSelectedProject` (`useState` initialised in a `useEffect`). Then in `ProjectSwitcher.tsx` call `writeSelectedProject(id)` alongside the existing `onChange`.
- [ ] **Step 4: Run to verify pass** — `npm run test:console` → PASS. `npm run build` → PASS.
- [ ] **Step 5: Commit** — `git add playground/src/lib/project-context.ts playground/src/lib/project-context.test.ts playground/src/components/studio/ProjectSwitcher.tsx && git commit -m "feat(playground): persist selected project to one shared localStorage key"`

---

### Task 8: `/console` becomes the project-aware write surface

**Files:**
- Modify: `playground/src/app/console/layout.tsx`, `playground/src/components/console/JobStagePage.tsx`

**Interfaces:**
- Consumes: `useSelectedProject` (Task 7), `api.submit({ ..., project_id })` (Task 6), `ProjectSwitcher` (Task 7).
- Produces: the console layout header renders `<ProjectSwitcher>` bound to `useSelectedProject`; `JobStagePage` reads the selected project and passes `project_id` in its `api.submit` call, disabling the submit button (with a "先选项目" note) when none is selected — so `/console` never emits a 400.

- [ ] **Step 1: Mount the switcher in the layout** — in `console/layout.tsx`, inside the existing console/studio cross-link block (lines 36-53), render a small project picker wired to `useSelectedProject()` (reuse `ProjectSwitcher` or its select markup). Selection persists via Task 7's key.
- [ ] **Step 2: Pass the project into submit** — in `JobStagePage.tsx`, read `const [projectId] = useSelectedProject();` and change the `api.submit({...})` call (line 190) to include `project_id: projectId ?? ""`. When `!projectId`, disable the submit button and show `先选项目 / Select a project first` (do not send). On a backend 400/404/409 the existing `catch` already surfaces `apiError.detail` — verify the `project_id`/scenario messages render (they carry `field`/`hint`).
- [ ] **Step 3: Verify the app builds and links** — `npm run lint && npm run build` → PASS. Manually confirm a submission carries `project_id` (browser network tab, or a quick `npm run dev` smoke).
- [ ] **Step 4: Commit** — `git add playground/src/app/console/layout.tsx playground/src/components/console/JobStagePage.tsx && git commit -m "feat(playground): console submit is project-scoped (D12)"`

---

### Task 9: `/studio/projects/[id]` detail page + list link

**Files:**
- Create: `playground/src/app/studio/projects/[id]/page.tsx` (+ tab sub-components in the same directory or `components/studio/project/`)
- Modify: `playground/src/app/studio/projects/page.tsx`
- Test: `playground/src/components/studio/project/selectors.test.ts` (node:test) for any pure selector (e.g. `groupJobsByStage`, `latestJobPerStage`) used by the tabs.

**Interfaces:**
- Consumes: `api.project(id) -> ProjectSummary`, `api.jobs({ project })`, `api.projectArtifacts(id)`, `api.projectEvents(id)`, `api.job(id) -> JobDetail` (metrics + artifacts), all from Tasks 5–6.
- Produces: a page with a URL param `{ id }` (`use(params)` like `studio/jobs/[id]/page.tsx`) and five tabs that read **real** APIs — **Overview** (goal, status, each stage's last job status, freeze policy fields, recent events tail), **Data** (`api.projectArtifacts` table), **Trainings** (`api.jobs({ project: id, stage: "train" })` + per-job link to `studio/jobs/[id]`), **Results** (per-job metrics from `api.job(id)` — `report.json`-shaped reads; no releases yet), **Lineage** (`api.projectArtifacts` + `api.artifact`/dataset lineage; a list/graph of edges). The **merge** and **review** tabs are intentionally absent (they need `bundles`/`record_reviews`, follow-on plan).

- [ ] **Step 1: Write the failing selector test** — e.g. `groupJobsByStage(jobs)` returns `{ train: <latest>, eval: ... }` by `created_at`; put it in `selectors.ts` and assert with plain objects in `selectors.test.ts`.
- [ ] **Step 2: Run to verify fail** — `npm run test:console` → FAIL (module not found).
- [ ] **Step 3: Implement selectors + page** — implement the pure selectors to green; build `page.tsx` as a client component that loads the five read APIs (via `useProjects`-style `useEffect` + `api.*`) into a tab shell (reuse `PageHead`, `Panel`, `Table`, `StatusBadge` from `components/studio/primitives`). Each tab renders only real data; empty states use `EmptyState`.
- [ ] **Step 4: Run selector test + build to verify pass** — `npm run test:console && npm run lint && npm run build` → PASS.
- [ ] **Step 5: Link from the list page** — in `studio/projects/page.tsx`, wrap the `name` cell (line 88) in `<Link href={`/studio/projects/${p.id}`}>{p.name}</Link>` (import `Link` from `next/link`).
- [ ] **Step 6: Commit** — `git add playground/src/app/studio/projects playground/src/components/studio/project playground/src/app/studio/projects/page.tsx && git commit -m "feat(playground): project detail page with real training-history tabs"`

---

## Follow-on plans (explicitly not in this one)

- **Data curation** — `artifact_versions` (§4.2, next schema version), the `materialize` stage, `bundles`/`bundle_members` (§4.3), the F1–F4 freeze **execution** + `PUT /projects/{id}/freeze-policy`, and the **merge** tab. Columns exist from Task 1; behavior does not.
- **Annotation** — `record_reviews`/`record_review_history` (§4.4, D6/D13, scenario-scoped, review-queue, `reviews.jsonl` import) and the **review** tab; retire `console/goldset/review`.
- **Conclusions** — `project_releases` (§4.5, D8), gates-snapshot persistence, the **results**-as-releases upgrade, and `GET /projects/{id}/lineage` as a graph.
- **Quota writes** — `add_usage` (§4.6) so the quota page shows real numbers.

## Self-Review (author pass — complete before handing off)

1. **Spec coverage:** §4.1 columns → Task 1 (freeze_* columns land, their F1–F4 behavior deferred and named). D14 hard-required `project_id` + P1 → Task 2. D1 scenario-bound project → Tasks 3–4. §5 read rows (`GET /jobs?project`, `GET /projects/{id}` summary, `/events`) → Tasks 2 & 5. D12 `/console` mount + persistence → Tasks 7–8. §7 detail page → Task 9 (five read-only tabs; merge/review deferred with reason). Out-of-scope sections listed above.
2. **Step scan:** each step is one action; test steps carry assertions, code steps carry signatures + spec-pinned values, verification steps carry command + expected result. No "TBD"/"handle edge cases".
3. **Type consistency:** `create_job(project_id=...)`, `list_jobs(project=...)`, `project_summary/project_events/list_project_artifacts`, `ProjectSummary`, `PROJECT_STORAGE_KEY`, `api.submit({ project_id })` are defined once and referenced identically by later tasks.
4. **Review Focus:** ghost-project 404 (T2), TypeError-vs-ValueError (T2), legacy invisibility (T2 filter test), idempotent upgrade (T1), one-key sharing (T7/T8) each have a named assertion.
5. **Proportion:** plan is shorter than the 700-line spec; SQL and API contracts cite §4/§5 rather than re-transcribe.
