# Project Hub v7 实现计划：数据策展 / 标注 / 结论 / 配额（续 foundation）

> **For agentic workers:** REQUIRED SUB-SKILL: 用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐 PR、逐 task 落地本计划。步骤用 checkbox（`- [ ]`）跟踪。每个 PR 是一个可独立回滚的合并单元，后端切片与配对的前端切片在同一 PR 内交错落地。

**Goal:** 把 `projects` 从「训练信息根」升级为「完整训练过程项目中枢」——落地设计稿的四条 follow-on：产物版本（`artifact_versions`）、数据策展（`bundles`/`bundle_members` + `materialize` stage + F1–F4 freeze）、人工标注（`record_reviews`/history，场景作用域跨轮继承）、结论落库（`project_releases` + gates_snapshot + lineage API）、配额真写（`add_usage`），并把前端项目中枢从当前的 5 tab 扩到样稿目标态的 6 tab（补 merge、review），逐页对齐样稿的「项目列 + 本项目/全部项目开关 + 按项目过滤与统计」。

**Architecture:** 本计划是 `2026-10-16-project-hub-foundation.md`（已合并）的**续集**，不重复其已落地的部分。foundation 落的是 §4.1 列升级（`jobs.project_id` + `projects` 六列 + `jobs_project_idx`）、`create_job` 必填 `project_id`、`POST /jobs` 的项目/场景校验、`GET /jobs?project=`、项目摘要/events、前端 5-tab 与 D12 ProjectSwitcher。本计划在其上补齐**数据策展子系统的全部行为**：新表 schema v9、版本登记、bundle 合并与物化、freeze 执行、标注覆盖层、结论快照、配额写入，以及前端 merge/review 两个 tab 和逐页项目列。所有新逻辑仍守 §2.3 反目标：bundle 是不可变产物、去重复用 `split_data.dedupe`（绝不复制实现）、标注永不改源文件、`jobs.project_id=''` 的 legacy 行永不出现在具体项目列表。下游 `kev/{train,benchmark,compare,calibrate,suite}.py` 零修改（P6）。

**Tech Stack:** Python 3.12/3.13，SQLAlchemy Core + 手写 SQL（sqlite + postgres 双方言），FastAPI（`console_router` 挂在 `/console/api/*`），pytest + `TestClient`。前端：Next.js 16 App Router（React 19）、`playground/src/lib/console.ts` API 客户端、shadcn/ui + Tailwind v4 + `.studio` 深色主题、`components/studio/primitives.tsx`；纯 helper 用 Node 内置 test runner（`node --test --experimental-strip-types`），页面/wiring 用 `npm run lint && npm run build`——无 vitest。

**Spec:** `docs/superpowers/specs/2026-10-16-project-hub-design.md`（D1–D14、§4 schema、§5 API、§6.3 状态机、§7 前端六 tab、§8 PR 分期）。**样稿**：`docs/studio-preview/project-hub-v7-demo.html`（12 视图，假数据，只做视觉/交互对齐；实现以设计稿与真实 API 契约为准）。从 spec 论证，不要重抄 spec。

---

## 0. 起点事实（写计划前已在 checkout 实测）

这些是本计划所有 PR 的前提，动手前先复核，不要按设计稿的字面假设写：

1. **schema 版本真相是 8，不是设计稿假设的 6→7。** `kev/console/db.py:27` 是 `SCHEMA_VERSION = 8`。
   - v7 = foundation 已落的 §4.1 列升级（`_migrate` 的 `if version < 7:` 块，db.py:620-638；postgres 迁移在 `deploy/console/migration_project_hub_v7.postgres.sql`）。
   - v8 = **与本设计无关**的 `scenario_domains.spec_dir` + `scenarios.{track,generator_kind,distill_yaml,origin}`（`_migrate` 的 `if version < 8:` 块，db.py:642-651）。
   - **结论：本计划的新表（`artifact_versions`/`bundles`/`bundle_members`/`record_reviews`/`record_review_history`/`project_releases`）一律落 SCHEMA_VERSION = 9**，不是设计稿 §4 标题写的「6 → 7」。这是对设计稿版本假设的**就地更正**，PR A 的迁移块用 `if version < 9:`。
2. **已实现、无需再做的后端面**（foundation 已交付，本计划只在旁边扩，不改语义）：
   - `Store.create_job(*, project_id, ...)`：keyword-only 必填，空/None → `ValueError`（db.py:661-692）。
   - `Store.list_jobs(*, status, stage, scenario, project, limit)`：`project=="legacy"` 映射 `''`；`limit=None` 不写 LIMIT（db.py:698-720）。
   - `Store.project_summary / project_events / list_project_artifacts / create_project / scenario_known / update_project`（db.py:1736-1840 区段）。
   - `jobs` 表 `_ddl` 已含 `project_id TEXT NOT NULL DEFAULT ''`（db.py:130）+ `jobs_project_idx`（db.py:139）。
   - `POST /jobs`（app.py:767-822）已校验：缺/空 `project_id`→400、幽灵项目→404、项目未绑场景→409、作业场景≠项目场景→409。
   - `GET /jobs?project=`（app.py:825-829）、`GET/POST/PUT/DELETE /projects`、`GET /projects/{id}{,/artifacts,/events}`（app.py:1100-1170）已就位。
   - `_spawn`（app.py:227-286）已把 `request.project_id` 透传进 `create_job`；`JobRequest.project_id` 已存在（base.py:54）。
3. **仍未实现、本计划要造的后端面**（grep 全仓确认无写入者/无表）：`artifact_versions`、`bundles`/`bundle_members`、`record_reviews`/`record_review_history`、`project_releases`、`add_usage`、freeze 执行、materialize stage/service。`update_project` **尚无 D9「slug 有数据后不可改」守卫**（要补）。
4. **`artifacts.register()`（artifacts.py:135-160）是版本登记与 storage 用量落点**：现有 `with store.tx():` 单事务，for artifacts_out → resolve → summarize → `put_artifact(commit=False)` → `add_lineage`。`artifact_versions` 写入紧随 `put_artifact` 同事务（PR B）；`add_usage(storage delta)` 在此触发（PR F）。`RELATION`（artifacts.py:29）需加 `"materialize": "composed_of"`（PR C）；`resolve`（artifacts.py:39）需加 `bundle:` kind 分支（PR C）。
5. **前端项目详情页当前是 5 tab**：`playground/src/app/studio/projects/[id]/page.tsx`（overview/data/trainings/results/lineage）。目标态 6 tab：`data/merge/review/trainings/results/lineage`，overview 内容并入页头摘要（样稿 demo.html:262、304-309 已示范）。
6. **两个待收口的标注入口都存在**：`playground/src/app/console/goldset/review/page.tsx`（真功能、决策只在浏览器 `exportHoldout` 下载、刷新即丢）与 `playground/src/app/studio/datasets/label/page.tsx`（4 条硬编码 ITEMS 的 mock）。PR D 用项目 `review` tab 替掉两者，仓内只剩一个逐条改标入口（§7 P7 判据）。

## 设计稿 §8 PR → 本计划 PR 映射

| 设计稿 §8 | 状态 | 本计划 |
| --- | --- | --- |
| PR1 文档 | ✅ 已完成 | — |
| PR2 schema v7 列 + Store | ✅ foundation 已落列；**新表未落** | **PR A**（schema v9 新表 + Store 骨架 + D9 slug 守卫） |
| PR3 artifact_versions + 版本/预览/导出 + integrity | ❌ | **PR B**（后端 + data tab 升级） |
| PR4 jobs.project_id + POST/GET + 摘要 + events | ✅ foundation 已落 | — |
| PR5 materialize + bundles/bundle_members + F1–F4 freeze | ❌ | **PR C**（后端 + merge tab） |
| PR6 record_reviews/history + review-queue + import + 收 goldset/review | ❌ | **PR D**（后端 + review tab） |
| PR7 project_releases + gates_snapshot + lineage API | ❌ | **PR E**（后端 + results/lineage tab） |
| PR8 前端 6 tab + ProjectSwitcher | ⚠️ foundation 落 5 tab + switcher | **PR D/E 的 tab 切片** + **PR G**（逐页项目列对齐样稿） |
| PR9 quota add_usage + §4.6 | ❌ | **PR F** |

---

## Global Constraints（每个 PR 都受这些约束）

- **测试命令**：后端 `uv run python -m pytest tests/<file> -q`；前端纯 helper `npm run test:console`，页面/wiring `npm run lint` 再 `npm run build`。CI 只跑单元测试 + playground lint/typegen。
- **schema 版本**：本计划统一用 **SCHEMA_VERSION 8 → 9**。新表进 `_ddl`（fresh 库）的 `CREATE TABLE`，旧库进 `_migrate` 的 `if version < 9:` 块；浮点列走 `_ddl`/迁移里的 `real` 占位（sqlite `REAL` / postgres `DOUBLE PRECISION`，见 db.py:621 写法），绝不硬编码单方言。`Store()` 对同一 DB 跑两次是 no-op（幂等）。
- **postgres 迁移文件**：每个动 schema 的 PR 同步在 `deploy/console/` 加一份幂等 `migration_project_hub_v9.<dialect>.sql`，与 foundation 的 `migration_project_hub_v7.postgres.sql` 同一风格（`CREATE TABLE IF NOT EXISTS` + `CREATE INDEX IF NOT EXISTS`）。
- **项目归属只走 job**：产物版本的项目归属来自 `versions.job_id → jobs.project_id` join，**不给 `artifacts` 加 `project_id` 列**（D2）。
- **legacy 不可见**：`jobs.project_id=''` 的行只出现在 `?project=legacy` 与「全部」，永不出现在任何具体项目列表（D14，foundation Review Focus 已有断言，本计划每个新聚合查询都要守）。
- **错误体**：一律用现有 `_error(kind, message, *, status, field, hint)` / `_job_error` 形状（app.py），不新造响应封装。`bundle` 名过 `run_matrix.check_name`（禁点号）。
- **不可复用/不自动改名**：frozen bundle 改成员或重物化 → 409；materialize 重名 → 409 而非覆盖（`base.Conflict` 脾气，D9/D4）。
- **改 schema 必同步 `delete_project` 级联清单**（db.py:1586-1594 区）：新表里 `bundles`/`bundle_members`/`project_releases` 随项目删除；**`record_reviews` 不随删除**（作用域是场景，D13）——只把其 `origin_project_id` 置 `''`（「来源已删」）而不删行；`record_review_history` 随行保留。这是 §4.5「级联清单唯一主动偏离」，必须写进那段注释旁。
- **不动下游**：`kev/{train,benchmark,compare,calibrate,suite}.py` 零修改（P6）。
- **降级路径不破**：既有 `/console/*` 页面、训练/评测子进程 spawn 路径、SSE 续传（`GET /jobs/{id}/stream`）在本计划每一步后仍可用。

## Cross-cutting Review Focus（spec 隐含、单个 happy-path 测不出的失败模式，各自钉到归属 PR 的断言）

- **V3 版本只增不改 + seq 同事务**：同一 artifact 两次注册得到 seq 1/2，`MAX(seq)+1` 在 `store.tx()`（BEGIN IMMEDIATE）内取，两个并发注册不撞 `UNIQUE(artifact_id, seq)`。（PR B）
- **integrity 是读时复核**：登记后手改文件 → `GET /artifacts/{id}/versions` 返回 `integrity=drift`；文件被删 → `missing`；无版本行的历史 artifact → 返回空列表而非 500。（PR B）
- **materialize 幂等到 sha256**：两个批次取并集 → 第二次跑同一 bundle 得**同 sha256**（同库同文件状态）；`drop_reasons` 的 `dup`/`state_conflict` 逐条等于 `split_data.dedupe` 的丢弃数（property test，反目标 §2.3 第 2 条）。（PR C）
- **freeze 分硬软**：F1（无 sha/无 include 成员）与 F4（产物含未处理 flag）不过 → **409 硬拒**；F2/F3（记录数/复核比例不足）不过仍 **200 + warnings**，四条 `freeze_checks` 两种情况都写全。（PR C）
- **门槛 0 行为等价**：`freeze_min_records=0` 且 `freeze_min_review_ratio=0.0` 时 freeze 与「不设门槛」逐字节一致（D11「我不想知道」）。`records+1` 的 `freeze_min_records` 必拒且 F2 的 `actual/need` 就是那两个数（P8）。（PR C）
- **标注不改源文件**：改一条答案后源 JSONL 的 sha256 **不变**；决定落 `record_reviews`，覆盖前归档一条 `record_review_history`。（PR D）
- **场景作用域跨轮继承**：`UNIQUE(scenario, fingerprint)`；第二轮重建同样记录 → 上轮 `accept/relabel` 自动生效，无需重标；`review-queue` 默认跳过已决定指纹（含继承）。空场景项目写决定 → 409。（PR D）
- **F3 分子拆 native/inherited**：只报合计会把「本轮没看、上轮看过」绿过去；`reviewed_native`（`origin_project_id=本项目`）与 `reviewed_inherited` 必须并列进 detail 与 UI。（PR C 写、PR D 拆）
- **release 证据先于宣告**：`gates_snapshot` 服务端现算落库；删掉 eval 目录后 release 仍读得出当时判定；从 release 一路反查到源记录 fingerprint（P5）。（PR E）
- **quota 有真数**：`storage_gb_used`/`training_hours_used` 经 `add_usage` 有非零真实值（§4.6：今天三列无任何写入者）。（PR F）

## PR 依赖图（合并顺序）

```
PR A (schema v9 新表 + Store 骨架 + D9 slug 守卫)
  ├─ PR B (artifact_versions 登记 + 版本/预览/导出 + integrity)   ← 依赖 A 的 artifact_versions 表
  │     └─ PR C (materialize + bundles/bundle_members + F1–F4 freeze)  ← 依赖 B 的 version_id 作 bundle 成员
  │           ├─ PR D (record_reviews/history + review-queue + import + 收 goldset/review)  ← 依赖 C 的 materialize 应用覆盖层
  │           └─ PR E (project_releases + gates_snapshot + lineage API)  ← 依赖 C 的 bundle sha
  └─ PR F (add_usage quota + §4.6)  ← 挂 PR B 的登记点与 PR C 的物化点（storage delta），可最后合
  PR G (逐页项目列 + 本项目/全部开关 + D12 polish)  ← 依赖 B/C/D/E 的读 API，纯前端，收尾合
```

关键路径 A → B → C → D。PR E 依赖 C（bundle sha），PR F 依赖 B+C（写入点），PR G 是前端收尾，聚合 B–E 的新读 API。任何 PR 都不改下游训练/评测子进程。

---

## PR A — Schema v9：数据策展新表 + Store 骨架 + D9 slug 守卫

**对应设计稿**：§4.2–§4.5（全部新表）、§8 PR2（表的一半）、D9（slug 不可改守卫）、§4.6-1（`put_artifact` 的 `commit` 形参文档谎言，本 PR 记录并绕开，不修 docstring 以免牵动既有测试）。
**样稿视图**：无直接可视（纯 schema）；为 PR B–E 的 data/merge/review/results tab 铺表。
**依赖**：foundation 已合并（§4.1 列已落，SCHEMA_VERSION=8）。

### 目标与验收门槛
- `SCHEMA_VERSION` 8 → 9；fresh 库与升级库版本一致；对已有 v8 行的库跑 `Store()` 幂等（跑两次无变化），且既有全部 `tests/test_console_db.py` 全绿。
- 建 5 张新表：`artifact_versions`、`bundles`、`bundle_members`、`record_reviews`、`record_review_history`、`project_releases`（DDL 逐列照 §4.2–§4.5，浮点走 `real`）。
- `Store` 落地**最小骨架方法**（供 PR B–E 填充行为，本 PR 只建表 + 读写通路的形状）：`_row` 解析器 + `delete_project` 级联扩到新表（`record_reviews` 按 D13 例外只清 `origin_project_id`）。
- `update_project`：加 D9 守卫——项目下已有任何 job 或 bundle 时改 slug → `Conflict`（app 层映射 409）。

### Files
- **修改** `kev/console/db.py`：`SCHEMA_VERSION`；`_ddl` 追加 6 张 CREATE TABLE + 索引；`_migrate` 追加 `if version < 9:` 幂等块（新表用 `CREATE TABLE IF NOT EXISTS`，无需 `_column_exists`）；新增行解析常量；扩 `delete_project` 手工级联清单；`update_project` 补 D9 守卫（新增 `_project_has_rows(project_id)` 助手，JOIN jobs + bundles）。
- **新增** `deploy/console/migration_project_hub_v9.postgres.sql`：6 张表 + 索引的幂等 postgres DDL（照 foundation v7 文件风格）。
- **修改** `deploy/console/schema.full.postgres.sql` / `schema.sqlite.sql`：把新表并入全量 schema（fresh 部署）。
- **测试** `tests/test_console_db.py`：新表存在、幂等、级联、D9 守卫。

### Store 方法骨架（本 PR 只建表 + delete_project/守卫；读写行为在 B–E 填）
```python
# db.py 模块级新增（_ddl 追加）：
# artifact_versions(id TEXT PK, artifact_id TEXT NOT NULL, seq INTEGER NOT NULL,
#   job_id TEXT NOT NULL REFERENCES jobs(id), path TEXT NOT NULL, sha256 TEXT NOT NULL,
#   records INTEGER, bytes INTEGER, meta TEXT NOT NULL, spec_sha256 TEXT, created_at TEXT NOT NULL,
#   UNIQUE(artifact_id, seq))  + 两个 idx（job / artifact_id,seq DESC）
# bundles(id TEXT PK, project_id TEXT NOT NULL REFERENCES projects(id), name TEXT NOT NULL,
#   artifact_id TEXT NOT NULL, status TEXT NOT NULL, sha256 TEXT, records INTEGER,
#   reviewed_records INTEGER, reviewed_native INTEGER, reviewed_inherited INTEGER,
#   review_ratio {real}, freeze_checks TEXT NOT NULL DEFAULT '[]', manifest_path TEXT,
#   manifest_sha256 TEXT, frozen_at TEXT, note TEXT NOT NULL DEFAULT '',
#   created_at TEXT NOT NULL, updated_at TEXT NOT NULL, UNIQUE(project_id, name))
# bundle_members(bundle_id TEXT NOT NULL REFERENCES bundles(id),
#   version_id TEXT NOT NULL REFERENCES artifact_versions(id), op TEXT NOT NULL,
#   ord INTEGER NOT NULL, records_in INTEGER, records_kept INTEGER, records_dropped INTEGER,
#   drop_reasons TEXT NOT NULL DEFAULT '{}', PRIMARY KEY(bundle_id, version_id)) + ord idx
# record_reviews(id TEXT PK, scenario TEXT NOT NULL, origin_project_id TEXT NOT NULL REFERENCES projects(id),
#   fingerprint TEXT NOT NULL, record_id TEXT, verdict TEXT NOT NULL, patch TEXT,
#   fingerprint_after TEXT, labels TEXT NOT NULL DEFAULT '[]', note TEXT NOT NULL DEFAULT '',
#   reviewer TEXT NOT NULL DEFAULT '', source_version_id TEXT REFERENCES artifact_versions(id),
#   created_at TEXT NOT NULL, updated_at TEXT NOT NULL, UNIQUE(scenario, fingerprint)) + 2 idx
# record_review_history(id TEXT PK, review_id TEXT NOT NULL REFERENCES record_reviews(id),
#   verdict TEXT NOT NULL, patch TEXT, labels TEXT NOT NULL DEFAULT '[]', note TEXT NOT NULL DEFAULT '',
#   reviewer TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL) + idx(review_id, created_at DESC)
# project_releases(id TEXT PK, project_id TEXT NOT NULL REFERENCES projects(id), name TEXT NOT NULL,
#   bundle_id TEXT REFERENCES bundles(id), bundle_sha256 TEXT, train_job_id TEXT REFERENCES jobs(id),
#   run_artifact TEXT, eval_artifact TEXT, comparison_artifact TEXT, regression_artifact TEXT,
#   calibration_artifact TEXT, metrics TEXT NOT NULL DEFAULT '{}', gates_snapshot TEXT NOT NULL DEFAULT '[]',
#   verdict TEXT NOT NULL DEFAULT 'candidate', note TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL,
#   UNIQUE(project_id, name))
```
`delete_project` 级联新增：先删 `bundle_members`（经 bundles）→ `bundles` → `project_releases`；`record_reviews` **不删行**，`UPDATE record_reviews SET origin_project_id='' WHERE origin_project_id=:pid`；`record_review_history` 保留（随 review 行留）。`artifact_versions` 不删（版本是产物侧历史，D3；删项目不清空产物证据）。

### API 契约 diff
- **改** `PUT /projects/{id}`：请求体带 `slug` 且项目已有 job/bundle → **409** `{kind:"conflict", field:"slug", message:"项目已有数据，slug 不可改"}`（D9）。其余列照常可改。无新增端点（本 PR 不暴露新表读写）。

### 前后端配对与依赖
- 纯后端。无前端切片（前端在 B–E/G 各自消费对应表时再动）。
- 后续所有 PR 依赖本 PR 的表存在，故必须先合。

### 回滚
- `git revert` 本 PR commit 即可（只加表 + 幂等迁移块 + update_project 守卫，无数据写路径改动）。已建 v9 表对旧代码不可见（旧代码不查它们），revert 后 SCHEMA_VERSION 回 8 但库里的 v9 表成为惰性死表，下次升级重建无冲突（`IF NOT EXISTS`）。postgres 迁移文件同步 revert。

### 检查点
- `- [ ]` 写失败测试：`test_schema_v9_adds_curation_tables(store)` 断言 `store.schema_version()==9` 且 6 表 `_table_exists`；`test_idempotent_v9(store)` 同库跑两次 `Store()` 无变化；`test_delete_project_cascade_preserves_reviews`：建 review → 删 origin 项目 → review 行仍在、`origin_project_id==''`；`test_slug_guard_rejects_when_has_job`。**先跑验证 FAIL**。
- `- [ ]` 实现 `_ddl` + `_migrate` + `delete_project` + `update_project` 守卫，`uv run python -m pytest tests/test_console_db.py -q` → PASS；`uv run python -m pytest tests/ -q -k "console or rounds or app"` 既有全绿（迁移期不回归）。
- `- [ ]` postgres 侧：本地起库跑 `migration_project_hub_v9.postgres.sql` 两次无错。
- `- [ ]` commit：`feat(console): schema v9 curation tables + D9 slug guard`。

---

## PR B — artifact_versions 登记 + 版本/预览/导出 API + integrity

**对应设计稿**：§4.2、§5（`GET /artifacts/{id}/versions`、`/artifact-versions/{vid}/records`、`/export`）、D3、§8 PR3；P2。
**样稿视图**：项目详情 **data tab**（demo.html:313-324，「产物版本」表：artifact × seq × records × sha256 × integrity × 来源作业，行展开预览 50 条走 `?q&verdict`）。
**依赖**：PR A（`artifact_versions` 表）。

### 目标与验收门槛
- `artifacts.register()` 在 `put_artifact` 之后、同事务写一条 `artifact_versions`：登记即算 sha256/records/bytes/meta/spec_sha256，`seq = MAX(seq)+1`。
- 三个只读 API：版本列表（每项现算 `integrity: ok|drift|missing`）、版本记录预览/检索（`limit ≤ 500`，行带 fingerprint）、版本导出（StreamingResponse，抄 `export_dataset`）。
- P2 判据：同一 artifact 两次注册 → seq 1/2 且 sha256 与 `sha256sum` 一致；改文件后 `integrity=drift`；历史无版本 artifact 读列表返回 `[]` 非 500。

### Files
- **修改** `kev/console/artifacts.py`：`register()` 内 `with store.tx():` 追加 `store.record_artifact_version(...)`（commit=False 同事务）；`sha256`/`records` 计算助手 `_hash_and_count(path)`。
- **修改** `kev/console/db.py`：新增 `record_artifact_version(artifact_id, job_id, path, sha256, records, bytes, meta, spec_sha256)`（内部取 `MAX(seq)+1` 同事务）、`list_artifact_versions(artifact_id)`、`get_artifact_version(vid)`、`artifact_version_job(vid)`。
- **修改** `kev/console/app.py`：新增 3 端点（下）。integrity 现算复用 `artifacts.resolve()` + `_hash_and_count`。
- **前端修改** `playground/src/lib/console.ts`：新增 `ArtifactVersion` 类型 + `api.artifactVersions(id)`、`api.artifactVersionRecords(vid, {offset,limit,q,verdict})`、`api.artifactVersionExportUrl(vid)`。
- **前端修改** `playground/src/app/studio/projects/[id]/page.tsx`：`DataTab` 从「产物列表」升级为「版本表」（读 `api.projectArtifacts` → 每 artifact `api.artifactVersions`，展开行预览）。
- **测试** `tests/test_console_artifacts.py`（新增或扩）：版本登记、seq 递增、integrity 三态、预览分页、无版本返回空。

### API 契约 diff（新增）
```
GET /console/api/artifacts/{id}/versions -> [{id, artifact_id, seq, job_id, path, sha256,
     records, bytes, meta, spec_sha256, created_at, integrity:"ok"|"drift"|"missing"}]
     404 未知 artifact；历史无版本 -> []
GET /console/api/artifact-versions/{vid}/records?offset=0&limit=100&q=&verdict=
     -> {version_id, total, records:[{line_no, fingerprint, record}]}  limit 上限 500（同 read_events）
     404 未知 version
GET /console/api/artifact-versions/{vid}/export -> StreamingResponse（文件名策略同 export_dataset）
```

### 前后端配对与依赖
- 后端登记 + 读 API 先行；data tab 前端切片在同 PR 后半，消费 `api.artifactVersions`。integrity 在服务端算，前端只渲染徽标（`ok`→绿、`drift`→黄、`missing`→红），对齐样稿 data tab。
- 依赖 PR A。PR C 的 bundle 成员用 `version_id`，故 C 依赖 B。

### 回滚
- `revert` commit：`register` 回到不写版本行；3 端点删除；data tab 回到产物列表。已写入的 `artifact_versions` 行无害（旧代码不读）。

### 检查点
- `- [ ]` 失败测试：`test_register_writes_version_seq` 两次注册同 artifact → seq [1,2]；`test_integrity_drift_missing`（改文件 / 删文件）；`test_versions_history_empty_not_500`。跑 FAIL。
- `- [ ]` 实现后端 → `uv run python -m pytest tests/test_console_artifacts.py -q` PASS。
- `- [ ]` 前端：`console.ts` 类型 + `npm run test:console`（若有纯 selector）；`page.tsx` data tab → `npm run lint && npm run build` PASS。
- `- [ ]` commit：`feat(console): artifact_versions registry + integrity read APIs + project data tab`。

---

## PR C — materialize stage + bundles/bundle_members + manifest + F1–F4 freeze

**对应设计稿**：§4.3、§5（bundles/members/materialize/freeze/freeze-policy/diff）、§6.2/§6.3 状态机、§5 新 stage `materialize`、D4/D5/D11、§8 PR5；P3/P8。
**样稿视图**：项目详情 **merge tab**（demo.html:327-350：有序成员 + 三态 op include/exclude/overlay、右列 `records_kept`/`drop_reasons`/`review_ratio`、物化/冻结按钮、preview 显示 argv）；freeze_checks 红绿表（demo.html:282-298）。
**依赖**：PR B（bundle 成员是 `artifact_versions` 的 `version_id`）。

### 目标与验收门槛
- 新产物 kind `bundle`：`artifacts.resolve()` 加 `bundle:<slug>/<name>` → `data/<project-slug>/bundles/<name>.jsonl`；`RELATION` 加 `"materialize": "composed_of"`。
- 新 stage `materialize`：`StageSpec("materialize", "data", "合成训练快照", ..., service="data.materialize")`，走 `LocalExecutor.spawn_callable`（与 `eval.benchmark` 同服务路径），`artifacts_in` = 各成员 version 的 artifact id，`artifacts_out` = `bundle:<slug>/<name>`。`stage_params.DEFAULT_SCHEMAS["materialize"]` 只放 `note`/`overwrite` 标量，成员由 `PUT .../members` 管。
- service `data.materialize`：按 `ord` 读成员 JSONL，`overlay` 应用 `record_reviews` 覆盖层（**本 PR 只接管道：有覆盖层就用，PR D 落表后自动生效**），统一过一次 `split_data.dedupe`（import，不复制），写 `.jsonl` + `.manifest.json`（新文件，重名 Conflict），逐成员落 `bundle_members.records_kept/records_dropped/drop_reasons{dup,state_conflict,review_drop,review_unresolved}`，回写 `bundles.sha256/records/review_ratio/reviewed_*`，`register()` 走 version + lineage(composed_of)。
- bundle CRUD + freeze：建 draft、全量替换成员、物化、freeze 跑 F1–F4、`PUT .../freeze-policy` 改门槛。状态机 draft↔materialized→frozen→retired（§6.3）。
- P3：两次跑同一 bundle → 同 sha256。P8：`freeze_min_records=records+1` 必拒且 F2 actual/need 对得上。

### Files
- **修改** `kev/console/artifacts.py`：`resolve()` 加 `bundle:` 分支；`RELATION["materialize"]="composed_of"`；`summarize()` 加 `bundle` meta 形状。
- **修改** `kev/console/stages/data.py`：新增 `materialize = StageSpec(...)` + `_materialize(request)`（组 preview argv，纯函数）；加入 `DATA_STAGES` 元组（data.py:422）。
- **修改** `kev/console/services/data.py`：新增 `materialize(store, job, ...)` 服务实现（读成员、overlay、`split_data.dedupe`、写文件+manifest、回写 bundles/bundle_members）。
- **修改** `kev/console/stage_params.py`：`DEFAULT_SCHEMAS["materialize"] = {fields:[note, overwrite]}`。
- **修改** `kev/console/db.py`：bundle 方法 `create_bundle / get_bundle / list_bundles / replace_bundle_members / set_bundle_members_stats / update_bundle_materialization / freeze_bundle(写 freeze_checks+frozen_at+status) / set_freeze_policy`。
- **修改** `kev/console/app.py`：5 端点（下）+ `_spawn` 服务绑定识别 materialize（走已有 service 分支）。
- **前端修改** `playground/src/lib/console.ts`：`Bundle`/`BundleMember`/`FreezeCheck` 类型 + `api.createBundle/setBundleMembers/materialize/freeze/setFreezePolicy/bundleDiff`。
- **前端修改** `playground/src/app/studio/projects/[id]/page.tsx`：**新增 `merge` tab**（成员拖拽定 ord、op 三态、右列统计、freeze 按钮挂 F1–F4 清单、预演调 preview）；tab 数组从 5 扩到 6（overview 内容并入页头摘要，对齐样稿）。
- **测试** `tests/test_console_bundles.py`（新增）+ `tests/test_console_materialize.py`（dedupe property test）。

### API 契约 diff（新增）
```
POST /console/api/projects/{id}/bundles                {name, note?} -> 201 Bundle(draft)
     name 过 check_name；重名 409
PUT  /console/api/projects/{id}/bundles/{name}/members [{version_id, op:"include"|"exclude"|"overlay", ord}]
     全量替换；仅 draft 可改，materialized/frozen -> 409
POST /console/api/projects/{id}/bundles/{name}/materialize -> 202 {job_id}（起 kind=materialize 作业）
POST /console/api/projects/{id}/bundles/{name}/freeze  ->
     200 {bundle, warnings:[{id,actual,need}]}（F2/F3 不过）
     409 {freeze_checks:[F1..F4]}（F1/F4 不过）；两条都写全四条 freeze_checks + frozen_at（成功时）
PUT  /console/api/projects/{id}/freeze-policy          {freeze_min_records, freeze_min_review_ratio} -> 200 Project
     只改门槛，不追溯已 frozen 的 bundle
GET  /console/api/bundles/{id}/diff?other=<id>         -> {only_left:[fp], only_right:[fp], changed:[{fp,...}]}
```
F1–F4（D11）：F1 `materialized`（sha 非空且 records 非空且 ≥1 include 成员）；F4 `no_unresolved`（产物无未处理 flag）—— **不过 409 硬拒**；F2 `records >= freeze_min_records`、F3 `review_ratio >= freeze_min_review_ratio`—— **不过仍 200，带 warnings**。四条都落 `bundles.freeze_checks`，形状抄 `gates.Gate` `{id,ok,detail,actual,need}`。

### 前后端配对与依赖
- 后端 stage/service/表写路径先行；merge tab 前端切片消费 bundle CRUD + freeze。冻结门槛就地可编（`PUT freeze-policy`）+ freeze_checks 红绿在 merge tab 与页头摘要（对齐样稿 demo.html:282-298）。
- overlay 覆盖层：PR C 管道预留（`data.materialize` 里按 scenario 查 `record_reviews`，无表则空），PR D 落表后不改 materialize 即继承生效。
- 依赖 PR B（version_id）。PR D 的 review-queue 依赖 materialize 产出；PR E 的 release 依赖 bundle sha。

### 回滚
- `revert`：materialize stage 出 REGISTRY、5 端点删、merge tab 移除、bundle 方法删。已物化的 bundle JSONL 文件保留（旧产物永久保留），已写 bundle 行惰性。F1–F4 未落 freeze 调用即不触发。

### 检查点
- `- [ ]` 失败测试：`test_union_idempotent_sha`（两批并集两次跑同 sha）；`test_drop_reasons_match_dedupe`（property：`dup`+`state_conflict` == `split_data.dedupe` 丢弃数）；`test_freeze_f1_f4_hard_refuse`（409）；`test_freeze_f2_f3_warn_only`（200+warnings）；`test_threshold_zero_byte_identical`；`test_p8_min_records_plus_one_refuses`（F2 actual/need）。跑 FAIL。
- `- [ ]` 实现 materialize service 复用 `split_data.dedupe`（**grep 确认 import 而非复制实现**，反目标 §2.3）。
- `- [ ]` `uv run python -m pytest tests/test_console_bundles.py tests/test_console_materialize.py -q` PASS。
- `- [ ]` 前端 merge tab + 6 tab 改造 → `npm run lint && npm run build` PASS。
- `- [ ]` commit：`feat(console): materialize stage + bundles + F1-F4 freeze + merge tab`。

---

## PR D — record_reviews/history + review-queue + import/export + 收掉 goldset/review 与 label mock

**对应设计稿**：§4.4、§5（reviews/{fp} upsert、reviews 列表、review-queue、reviews/import）、§6.2 时序、D6/D7/D13、§8 PR6；P4/P7。
**样稿视图**：项目详情 **review tab**（demo.html:353-370：键盘优先队列 `Enter/y` accept、`1-9` 重标、`x` drop、`f` flag、`e` 导出、`u` 撤销，抽屉编辑 state/question，顶部「已复核 N / 总 M = x%」+ 距 F3 门槛差多少，默认跳过已决定含继承）。
**依赖**：PR C（materialize 的 overlay 管道已预留，本 PR 落表后自动生效；review-queue 从 include 成员的行抽样）。

### 目标与验收门槛
- `record_reviews`（场景作用域 `UNIQUE(scenario, fingerprint)`）+ `record_review_history`（覆盖前归档，`REVIEW_HISTORY_LIMIT=20`，抄 `SPEC_HISTORY_LIMIT` 写法）读写。
- fingerprint = `sha256(canonical {state,questions})`，与 `split_data` 重复判定同一规范化函数（D7）；`edit`/`relabel` 存 `patch`（仅新值）+ `fingerprint_after`。
- 四条写入约束：`origin_project_id` 的项目 `scenario` 必须等于行上 `scenario`；项目 `scenario==''` → **409**（先补场景才能标）；改一条答案**源文件 sha256 不变**。
- review-queue：服务端抽样，`seed` 固定 → 换机器同批（抄 `tools/review` spot-check）；**默认跳过已决定指纹含继承**（D13 的可感受效果）。
- import：`reviews.jsonl`（`tools/review` 导出格式 `{id,verdict,label,proposed_label,note,reviewed_at}`）逐行按 fingerprint（无 id 按 record_id 反查）落库，回报 `{imported, unmatched}`。
- **收掉两个入口**：`console/goldset/review/page.tsx` 与 `studio/datasets/label/page.tsx` 由项目 review tab 替掉，仓内只剩一个逐条改标入口（P7：`tests/test_conventions.py` 扫描不再含硬编码数据行）。
- F3 分子拆 `reviewed_native`（origin=本项目）/`reviewed_inherited`，回写 PR C 的 materialize。

### Files
- **修改** `kev/console/db.py`：`REVIEW_HISTORY_LIMIT=20`；方法 `upsert_record_review(scenario, origin_project_id, fingerprint, verdict, patch, labels, note, reviewer, record_id, source_version_id)`（覆盖前 archive）、`list_record_reviews(scenario, *, verdict, labels, origin, page)`、`review_queue(project_id, *, limit, seed, include_decided)`、`import_reviews(project_id, rows)`、`record_review_for(fingerprint, scenario)`；`delete_project` 级联按 D13 例外（PR A 已建，此处只复核行为）。
- **修改** `kev/console/services/data.py`：`materialize` 的 overlay 应用点接 `record_review_for`（管道 PR C 已留，这里查表）；回写 `reviewed_native/inherited`。
- **修改** `kev/console/app.py`：4 端点（下）。
- **前端修改** `playground/src/lib/console.ts`：`Review`/`ReviewQueueItem`/`ReviewImportResult` 类型 + `api.upsertReview/listReviews/reviewQueue/importReviews`。
- **前端修改** `playground/src/app/studio/projects/[id]/page.tsx`：**新增 `review` tab**（键盘优先队列 + 抽屉编辑 state/question，键位对齐 `tools/review`）。
- **前端删除/改指** `playground/src/app/console/goldset/review/page.tsx`（重定向到项目 review tab 或删）、`playground/src/app/studio/datasets/label/page.tsx`（删 mock）。
- **测试** `tests/test_console_reviews.py`（新增）：源文件不变、场景作用域继承、空场景 409、history 裁剪、import unmatched、queue 跳过已决定。

### API 契约 diff（新增）
```
PUT  /console/api/projects/{id}/reviews/{fingerprint}
     {verdict:"accept"|"relabel"|"edit"|"drop"|"flag", patch?, labels?, note?, reviewer?, record_id?, source_version_id?}
     -> 200 Review；覆盖前自动 archive 一条 history
     409 项目 scenario==''（先补场景）；409 origin 项目 scenario≠行 scenario
GET  /console/api/projects/{id}/reviews?verdict=&labels=&origin=self|inherited|all&page=
     -> {items:[Review + origin_project_slug], total}   （默认 all，让继承来的看得见从哪轮来）
GET  /console/api/projects/{id}/review-queue?limit=50&seed=42&include_decided=0
     -> {items:[{fingerprint, record, existing_verdict?}], count}   默认跳过已决定含继承
POST /console/api/projects/{id}/reviews/import   {rows:[reviews.jsonl 行]} -> {imported, unmatched:[{row, reason}]}
```

### 前后端配对与依赖
- 后端表 + API 先行；review tab 前端切片同 PR。materialize overlay（PR C 预留管道）与 F3 native/inherited 拆分在本 PR 打通（跨 C/D）。收口两个旧入口是**破坏性前端改动**，故 review tab 必须先用真 API 建好再删旧页。
- 依赖 PR C。PR G 的 goldset 页「逐条改标入口已收进项目详情」文案依赖本 PR。

### 回滚
- `revert`：4 端点删、review tab 移除、`record_reviews` 方法删。旧入口页 `git revert` 复原（其删除是本 PR 的一个 commit）。已落库的 review 行惰性（旧代码不读）。**注意**：删旧页要独立成一个 commit，方便单独回滚不误伤 review tab。

### 检查点
- `- [ ]` 失败测试：`test_source_sha_unchanged_after_relabel`；`test_scenario_scope_inherits_next_round`（第二轮同 fingerprint 命中上轮决定）；`test_empty_scenario_409`；`test_history_archived_before_overwrite`（+ `REVIEW_HISTORY_LIMIT` 裁剪）；`test_import_unmatched_reported`；`test_queue_skips_decided_including_inherited`。跑 FAIL。
- `- [ ]` 实现 → `uv run python -m pytest tests/test_console_reviews.py tests/test_console_materialize.py -q` PASS（overlay 应用后 materialize 测试仍绿）。
- `- [ ]` 前端 review tab → `npm run lint && npm run build`；`uv run python -m pytest tests/test_conventions.py -q`（goldset/label 硬编码行消失）。
- `- [ ]` commit（两个）：`feat(console): record_reviews scenario-scoped + review-queue + import + review tab`；`refactor(playground): retire browser-only goldset/label review in favor of project review tab`。

---

## PR E — project_releases + gates_snapshot 落库 + lineage API

**对应设计稿**：§4.5、§5（`POST /projects/{id}/releases`、`GET .../releases/{rid}`、`GET /projects/{id}/lineage`）、§6.3 release 状态机、§7 results/lineage tab、D8、§8 PR7；P5。
**样稿视图**：项目详情 **results tab**（demo.html:384-392：releases 表 name × acc × ECE × Brier × AURC × G1-G7 × verdict，点进去回溯链）+ **lineage tab**（demo.html:395-407：DAG，节点按 kind 上色，边标 relation，`composed_of`/`overlay`）。
**依赖**：PR C（release 引 bundle sha）。

### 目标与验收门槛
- `project_releases` 落一行结论：bundle_id/sha + train_job + run/eval/comparison/regression/calibration 产物 + `metrics{acc,ece,brier,aurc,coverage,ci95,delta}` + `gates_snapshot`（`gates.evaluate()` 原样形状，**服务端现算落库，客户端不提交数字**）+ verdict（candidate/accepted/rejected）。
- `GET /projects/{id}/lineage` → `{nodes:[{id,kind,version}], edges:[{parent,child,relation,job_id}]}`（D10 只 JOIN 既有 `lineage` 表 + `bundle_members` 的 composed_of/overlay 边）。
- P5 判据：从 release 一路反查到源记录 fingerprint；**删掉 eval 目录后 release 仍读得出当时判定**（因为 snapshot 已落库）。

### Files
- **修改** `kev/console/db.py`：`create_release(...)`（写 gates_snapshot 时调 `gates.evaluate`）、`get_release(rid)`、`list_releases(project_id)`、`project_lineage(project_id)`。
- **修改** `kev/console/app.py`：3 端点（下）。
- **前端修改** `playground/src/lib/console.ts`：`Release`/`Lineage` 类型 + `api.createRelease/getRelease/projectLineage`。
- **前端修改** `playground/src/app/studio/projects/[id]/page.tsx`：`ResultsTab` 从「per-job metrics」升级为 **releases 表**（读 `api.projectReleases`）；`LineageTab` 从「产物 lineage 边列表」升级为调 `api.projectLineage` 的 DAG（节点上色）。
- **测试** `tests/test_console_releases.py`：snapshot 落库、eval 目录删除仍可读、回溯链、lineage 图形状。

### API 契约 diff（新增）
```
POST /console/api/projects/{id}/releases
     {name, bundle_id?, train_job_id?, run_artifact?, eval_artifact?, comparison_artifact?,
      regression_artifact?, calibration_artifact?, verdict?, note?}
     -> 201 Release（gates_snapshot 服务端现算，不接受客户端提交的数字）；重名 409
GET  /console/api/projects/{id}/releases          -> [Release]
GET  /console/api/projects/{id}/releases/{rid}     -> Release（含 gates_snapshot + metrics + 回溯指针）
GET  /console/api/projects/{id}/lineage           -> {nodes:[{id,kind,version}], edges:[{parent,child,relation,job_id}]}
     404 未知项目
```

### 前后端配对与依赖
- 后端 release + lineage 先行；results/lineage tab 前端切片同 PR 升级。lineage API 聚合 `lineage` 表 + bundle 边，前端只渲染。
- 依赖 PR C。PR G 的 publish 页「project_releases 为结论真相」文案依赖本 PR。

### 回滚
- `revert`：3 端点删、results/lineage tab 回到 foundation 形态、release 方法删。已落 release 行惰性。lineage 表本身没改（只新读法）。

### 检查点
- `- [ ]` 失败测试：`test_release_snapshot_survives_eval_removal`；`test_release_backchain_to_fingerprint`（release → bundle_members → versions → jobs → reviews）；`test_lineage_nodes_edges_shape`。跑 FAIL。
- `- [ ]` 实现 → `uv run python -m pytest tests/test_console_releases.py -q` PASS。
- `- [ ]` 前端 results/lineage 升级 → `npm run lint && npm run build` PASS。
- `- [ ]` commit：`feat(console): project_releases + gates_snapshot + lineage API; upgrade results/lineage tabs`。

---

## PR F — add_usage 配额真写 + §4.6 文档-代码不一致

**对应设计稿**：§4.6-2（三列无写入者）、§8 PR9、D10 副作用；§5 usage 按项目聚合。
**样稿视图**：**用量页**（demo.html:512：上方当前项目、下方跨项目明细，`storage_gb_used`/`training_hours_used` 不再是一排 0）；**运维监控页**（demo.html:537：`GET /projects/{id}/events` 跨作业时间线，可按项目过滤或跨项目统计，D10）。
**依赖**：PR B（版本登记 storage delta）、PR C（物化 storage delta、train 时长）。

### 目标与验收门槛
- `add_usage(project_id, **deltas)`：单条 UPDATE 落 `project_quota.storage_gb_used/training_hours_used/api_calls_used`（今天三列无任何写入者，§4.6-2），不与 `_exists`/`register` 事务纠缠。
- 调用点：`artifacts.register()` 写版本时落 storage 字节增量；`materialize` 完成时落 bundle 字节；train 作业成功时按 `finished_at - started_at` 落 hours。
- `GET /projects/{id}` 摘要与 `GET /usage` 暴露按项目聚合的用量；运维监控走已有 `GET /projects/{id}/events`（D10 不新表）。
- §4.6-1：`Store.tx()` docstring 说「不要调会自己 commit 的方法（put_artifact/add_lineage commit=True）」，但 `commit` 形参对 `_Conn` 无作用（是否留事务由 `_local.in_tx` 决定）。**新增方法照 `_Conn` 真实语义写**，不在本 PR 改旧 docstring 措辞以外行为（仅更正注释，避免牵动既有测试）。

### Files
- **修改** `kev/console/db.py`：`add_usage(project_id, *, storage_bytes=0, training_seconds=0, api_calls=0)`（单条 UPDATE，浮点/整型按 quota 列类型）；更正 `tx()` 注释（§4.6-1）。
- **修改** `kev/console/artifacts.py`：`register()` 同事务后调 `add_usage(storage delta)`（版本字节增量）。
- **修改** `kev/console/services/data.py`（materialize）与 `app.py`（train on_finished）：落 storage/hours。
- **修改** `kev/console/app.py`：`GET /projects/{id}` 摘要带 quota；如需，`GET /usage` 支持 `project=` 聚合。
- **前端修改** `playground/src/lib/console.ts`：`Quota` 已有 `*_used`；补 `api.projectUsage(id)`（若摘要未带）。
- **前端修改** `playground/src/app/studio/usage/page.tsx` + 运维监控页：项目列 + 本项目/全部开关 + 真数展示（与 PR G 视觉一致，用量数据本 PR 落地）。
- **测试** `tests/test_console_quota.py`：add_usage 累加、register/materialize/train 触发点。

### API 契约 diff
- `GET /console/api/projects/{id}` 响应 `ProjectSummary` **新增** `usage:{storage_gb_used, training_hours_used, api_calls_used}`（原形状向后兼容，只加字段）。
- `GET /console/api/usage` **可选新增** `project=` 查询参（默认全部，向后兼容既有调用）。

### 前后端配对与依赖
- 后端写入点 + 摘要扩展先行；用量/监控页前端切片展示真数（视觉与 PR G 对齐）。依赖 B/C 的写入点存在。

### 回滚
- `revert`：`add_usage` 调用点删（三列回到不动）、摘要字段删、页面前端回到占位。已累加的数不影响读取路径。

### 检查点
- `- [ ]` 失败测试：`test_add_usage_accumulates`；`test_register_bumps_storage_used`；`test_train_success_bumps_hours`。跑 FAIL。
- `- [ ]` 实现 → `uv run python -m pytest tests/test_console_quota.py -q` PASS。
- `- [ ]` 前端用量/监控页 → `npm run lint && npm run build` PASS。
- `- [ ]` commit：`feat(console): add_usage wiring so quota shows real numbers`。

---

## PR G — 逐页项目列 + 本项目/全部项目开关 + D12 polish（对齐样稿）

**对应设计稿**：§7（前端项目关联四行 + 贯穿改动）、D12/D14（legacy 只归「全部」不归任何项目）、§8 PR8（前端剩余切片）。
**样稿视图**：数据集（demo.html:413）、金标集（430）、训练（441）、评测（455）、部署（479）、发布（490）、总览（186）、用量（512）、运维监控（537）——每页「项目」列 + 本项目/全部项目开关 + 按项目过滤/统计；总览 KPI 随开关联动（样稿 `renderOv`）。
**依赖**：PR B–F 的读 API（versions/bundles/reviews/releases/quota）就位；foundation 的 ProjectSwitcher + `kev.project.id`（layout.tsx:59、project-context.ts）已在。

### 目标与验收门槛
- 所有与项目相关的**读/列表页**默认只列当前项目（`?project=` 或 `api.jobs({project})`），顶部一个「本项目 / 全部项目」开关回到今天的全量；legacy 行（`project_id=''`）只在「全部」出现，不进任何具体项目列表（D14）。
- 各列表加「项目」列（用 `ProjectSwitcher` 的项目名解析 id）。
- 总览/运维监控/用量：按项目过滤或跨项目统计，切换时 KPI、副标题、最近作业表联动（对齐样稿 `renderOv`）。
- `console.ts` 的 `Job` 类型补 `project_id` 字段（当前缺，样稿项目列需要）。
- 复用现有 shadcn/ui + `.studio` 深色主题 + `primitives.tsx`；不引新依赖、不重写页面骨架。

### Files（均为**修改**，改造而非重写）
- **修改** `playground/src/lib/console.ts`：`Job` 加 `project_id: string`；补各读方法（若前面 PR 未补全）。
- **修改**（studio 读页，逐页加项目列 + 本项目/全部开关 + 按项目过滤/统计）：
  - `playground/src/app/studio/datasets/page.tsx`、`goldset/page.tsx`、`train/page.tsx`、`eval/page.tsx`、`deploy/page.tsx`、`publish/page.tsx`、`overview/page.tsx`、`usage/page.tsx`、`jobs/[id]/page.tsx`（项目徽标）
  - 运维监控走 `overview`/`usage` 或既有 events 页
- **修改**（console 写页：从共享 context 取 `project_id` 塞进 `api.submit`，409/400 原文渲染在提交按钮旁）：`playground/src/app/console/{datasets,train,eval,images,deploy,goldset}/page.tsx`（foundation 已让 `api.submit` 带 `project_id`，这里确认每页都从 `useSelectedProject()` 取值且无项目时置灰说明「先选项目」）。
- **修改** `playground/src/components/studio/ProjectSwitcher.tsx`：确认持久化经 `project-context`（已 `kev.project.id`），无项目时列表页开关落到「全部」并提示。
- **测试/校验**：无新纯 helper 则靠 `npm run lint && npm run build`；若有 `projectScope(jobs, projectId)` 之类纯 selector，加 `*.test.ts`（node:test）断言 legacy 只在 all。

### API 契约 diff
- 无新后端端点（复用 foundation 的 `?project=` 与 PR B–F 读 API）。纯前端消费 + `Job.project_id` 类型补全。

### 前后端配对与依赖
- 纯前端收尾，聚合前序 PR 的读 API 与 foundation 的 D12 外壳。必须在 B–F 合完（读 API 有数）后合，否则项目列全空。

### 回滚
- 每页改动独立小 commit，按页 revert；开关默认「全部」时行为回到今天（不破坏既有页面）。`Job.project_id` 类型补全是纯增量，revert 不影响后端。

### 检查点
- `- [ ]` `console.ts` 加 `project_id` → `npm run build` 类型通过。
- `- [ ]` 各 studio 读页项目列 + 开关：`npm run lint && npm run build` PASS；手动核对样稿对应视图（项目列、本项目/全部切换、总览 KPI 联动、legacy 半透明行只在「全部」）。
- `- [ ]` 若加纯 selector → `npm run test:console` PASS。
- `- [ ]` commit（按页分组）：`feat(playground): project column + current/all toggle across studio pages per v7 mock`。

---

## 覆盖度自查（作者 pass，交接前完成）

1. **spec 覆盖**：§4.2→PR B；§4.3→PR C；§4.4→PR D；§4.5→PR E；§4.6→PR A（级联例外）+ PR F；§5 全部新端点→PR B/C/D/E/F；§6.2→PR C/D；§6.3→PR C（bundle）/PR E（release）；§7 六 tab→PR B(data)/C(merge)/D(review)/E(results+lineage)/G(逐页项目列)；D1–D14：D2/D3(B)、D4/D5/D11(C)、D6/D7/D13(D)、D8(E)、D9(A)、D10(C 边/E lineage/F events)、D12(G，foundation 已挂 switcher)、D14(全局约束 + G legacy 只归全部)、D1(foundation 已，本计划守)。§8 PR2/PR3/PR5/PR6/PR7/PR9 全部有归属，PR1/PR4 与 PR8 的 5-tab/switcher 切片在 foundation（本计划不重复）。
2. **schema 版本更正**：设计稿 §4 标题「6 → 7」是 v1 假设；实测 `SCHEMA_VERSION=8`，本计划新表落 **v9**（§0 第 1 条），PR A 迁移用 `if version < 9:`，postgres 落 `migration_project_hub_v9.postgres.sql`。
3. **衔接 foundation**：本计划假设 §4.1 列、`create_job` 必填、`POST/GET /jobs?project`、项目摘要/events、前端 5-tab、D12 ProjectSwitcher 均已合并；不重做，只在其旁扩。foundation「Follow-on plans」四条 = 本计划 PR A–F。
4. **步骤扫描**：每 PR 有目标/验收、新增 vs 修改文件、API 契约 diff（状态码齐全）、前后端配对与依赖、回滚、D+§编号、样稿视图、可验证检查点（pytest / `npm run build` / lint / typegen / test:console）。无「TBD」。
5. **降级路径**：每 PR 回滚都说明旧行为不破坏；PR G 开关默认「全部」= 今天行为；SSE/子进程 spawn 不动。
6. **不成比例**：本计划短于 700 行 spec；SQL/API 引用 §4/§5 而非重抄。

## 明确不做（本计划范围外）

- 多人协作 / 鉴权层（§2.2：`/console/api/*` 无 auth 是已知缺陷，本设计记录不修）。
- 产物全量文件副本（D3：只登记 sha256 + 复核，不复制）。
- 一致性统计 / 裁决队列 / 标注员绩效（D6：单人标注）。
- bundle 变 eval suite（§2.2）。
- Modal 云端项目同步（§2.2）。
- `data/critical-value/` 历史回填（D14：历史行 `project_id` 保持 `''`，不造历史 job/version）。
