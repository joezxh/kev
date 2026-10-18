# 作业的阶段归属与 bundle 轮次归属

> 数据集页（`/studio/datasets`）的作业表看不出一个作业是数据轨的哪一种活、属于哪个项目的哪一轮；提交表单的项目只能靠顶栏切换器改。本设计补两列（阶段、bundle）、把项目与 bundle 归属做成提交时的一次显式声明，并让 bundle 能被反向查回它的作业。

## 1. 意图与为什么

今天一个作业行能告诉你的：状态、id、`kind` 的英文原文、场景、运行名、创建时间、项目、耗时。缺的是研究过程中真正反复要回答的两件事：

- **这是哪一种活**。`kind` 原文（`plan_size` / `generate` / `distill_daemon` / `split`）在作业多了以后互相认不出来，用户熟悉的叫法是提交作业那张流程图上的「计划规模 / 生成数据 / 蒸馏 / 蒸馏守护 / 金标集 / 划分 / 预检 / 生成范例」。
- **它属于哪一轮**。项目列有了，但项目下面一轮一轮的 bundle 看不出来：这批 generate/distill 是为哪个 bundle 跑的，事后没法一眼对上。

## 2. 谁定的：本次的用户决定

| # | 结论 | 备注 |
|---|---|---|
| D1 | 「阶段」的粒度 = `kind` 一层 | 不是粗粒度 `stage`（data/train/…），也不是流程图的四个 phase 标题 |
| D2 | 阶段列同时显示中文名与 `kind` 英文原文 | 中文名用提交作业那张表的用词（用户的词），英文原文留着方便搜索和贴工单 |
| D3 | bundle 归属 = 提交作业那一刻显式声明 | 多对一：多个作业（**含同一阶段的多个作业**）可归属同一个 bundle |
| D4 | 深度做两层 | 数据集列表加 bundle 列 + 顶部 bundle 芯片（平铺，不分组折叠）；bundle 反查作业**两处都做，各管一件事**：芯片就地过滤 = **快查**（列表里点谁看谁，跨 bundle 横向对比），项目详情页 bundle 卡 = **审**（一屏看全为它跑过的作业 + 它名下的数据集）。C 的主从两栏不搬到数据集页 —— 审的入口只有那一处卡 |
| D5 | **不**做「作业成功后自动把产出版本挂进 bundle 成员」 | `setBundleMembers` 保持人工；这是人在场的质量闸门，自动化它不等于自动化它的判断 |
| D6 | 提交表单提供项目下拉 | 默认跟随顶栏切换器；在表单里改选后**写穿**共享状态，顶栏与列表的「当前项目 / 全部」范围随之更新。改动铺到所有提交页 |

## 3. 我定的（用户可推翻，不影响上面六条）

- **bundle 可选**。留空 = `''`，界面显示「—」。存量作业全部落在这里。
- **bundle 下拉列出该项目全部状态的 bundle**（draft / materialized / frozen / retired），带上状态字样，不禁止选 frozen/retired —— 归属是记账不是动作，冻了 bundle 也不该阻止你声明「这批数据本来是给它生产的」。
- **两列加在共享组件 `JobBoard` 上**，不替数据集页单开一套。数据集页、`/studio/jobs`、训练/评测/部署等复用它的页面一并获得（与 D6「铺到所有提交页」同构）。
- **`/console` 总览的 `JobTable` 接同一份名字表**，并把它那列现有的粗粒度 `job.stage` 的列标题从「阶段」改成「轨」，否则两个「阶段」在同一个产品里指两件不同的事。
- **数据集行的 bundle 取自产出它的那个作业**（`buildArtifactToJob` 已有这条链），作业没声明就是「—」。
- **bundle 芯片只在「当前项目」范围出现**（`api.bundles(projectId)` 是按项目取的）；切到「全部项目」时芯片消失，bundle 列照常显示名字 —— 名字靠后端在作业行里直接带出来（见 §4.3），不需要前端为每个项目各拉一次 bundle 列表。
- **命名作业模板（`job_templates`）不保存 bundle 归属**。归属是「这次提交给谁干」，不是「这类活怎么配」；模板带归属会让一个模板把作业静默塞进某个具体 bundle。
- **表单里改项目不清空已填参数**，只重取该项目的 bundle 列表并清空 bundle 选择。场景选择器保持独立（今天 `materialize` 用 `project.scenario`，其余作业用表单的 scenario，本设计不动这条规则）。
- **阶段中文名的真相源分两段**：数据轨 8 个 kind 沿用 `console.data.kind.*` 的既有用词（用户词，不改）；其余 12 个 kind 没有现成用词，直接取后端注册表的 title（见 §5.2 表），不新造名字。后端 title 同时作为整行的悬浮提示。

## 4. 后端

### 4.1 schema v11

`jobs` 表新增一列，沿用 `project_id` 定下的规矩：**空串是哨兵，不用 NULL**（D14 那条 legacy 语义在这里长得一样）。

```
jobs.bundle_id  TEXT NOT NULL DEFAULT ''
CREATE INDEX IF NOT EXISTS jobs_bundle_idx ON jobs(bundle_id, created_at DESC)
```

- `kev/console/db.py`：`SCHEMA_VERSION` 10 → 11，`_migrate()` 加 `if version < 11:` 分支，用现成的 `_column_exists` 做幂等 ALTER。
- ⚠️ **索引不能跟建表一起跑**（v10 提交时坐实的顺序陷阱）。`Store.__init__` 先 `_init_schema()`（整份 `_ddl` 跑完，建表与建索引混在一起）再 `_migrate()`，而 `_migrate()` 开头 `version >= SCHEMA_VERSION` 就直接 return。所以 `jobs_bundle_idx` 假设在建表脚本里跑，任何 schema < 11 的存量库都会在列被 ALTER 之前先撞上 `CREATE INDEX ... ON jobs(bundle_id)` → `no such column`。v7 的 `jobs_project_idx` 已经在这么坑人：本机那份 `schema_version=6` 的 `data/console/kev-console.db` 使 `test_cancel_endpoint_refuses_without_executor` 与 `test_proxy_kev_returns_503_when_training_active` 在**干净 HEAD 上也红**（已把旧库拷进基线 worktree 验过）。
  - 只把新索引写进 `_migrate()` 的 `if version < 11:` 分支也不对：`initdb`（`kev/console/__main__.py`）直接执行 `schema.*.sql` 建库，里面的 `console_meta.schema_version` 天生就是当前值，`_migrate()` 一早退，这个索引就永远不存在了。
  - **做法（本轮实现）**：`_ddl` 文本保留 `jobs_bundle_idx`（与 `jobs_project_idx` 并列，两份生成件与 `schema.full` 都跟着完整）；`_init_schema()` 跑之前用 `_INDEX_STATEMENT` 把所有 `CREATE INDEX` 摘出去，新增的 `Store._ensure_indexes()` 在 `_migrate()` 之后把 `_ddl` 里的每一条索引幂等补上（与版本无关）。顺手把 v7 留下的那个坑一并填了：旧库现在能开机，上面两条红转绿。
- ⚠️ **v11 叠在尚未提交的 v10 工作之上**。当前工作区里 `db.py`、`app.py`、`paths.py`、`deploy/console/*` 有未提交的 v10 改动（`scenarios.distill_yaml_content` + `migration_project_hub_v10.postgres.sql` + scenarios 编辑器）。落笔前先确认 v10 已提交，否则版本边界会串。（已处理：v10 作为 `feat/project-hub-v10` 分支的 f1cf169 落库，v11 从它上头开分支。）
- `_ROW_COLUMNS` 加 `bundle_id`；`create_job(..., bundle_id="")`；`list_jobs(..., bundle=None)` 加一个过滤条件。

### 4.2 端点

- `POST /console/api/jobs` 接受 `bundle_id`：非空时校验 bundle 存在（未知 → `_error("validation", status=404)`）且 `bundle["project_id"] == payload["project_id"]`（跨项目 → `_error("validation", status=400, field="bundle_id")`）。缺省或空串 → `''`。沿用 `app.py` 既有的 `_error` 结构，不新增异常类型。
- `GET /console/api/jobs` 加 `bundle` 查询参数（与现有 `status/stage/scenario/project` 同一路子）。
- `POST /console/api/jobs/{id}/retry` 新作业继承被重试作业的 `bundle_id`（与它继承 `template_id` 同理：重试是同一件事的第二次尝试）。
- `_spawn` 把它传给 `create_job`。`preview_job` 不需要知道归属。

### 4.3 读侧带出 bundle 名字

`list_jobs` / `get_job` 的 SELECT 左连 `bundles` 取 `bundles.name AS bundle_name`，作业行因此自带可读名字，前端显示不必再查一遍。sqlite 与 postgres 都支持这个写法的 LEFT JOIN。

### 4.4 迁移与 schema 文件（四份，一次到位）

- 新增 `deploy/console/migration_project_hub_v11.postgres.sql`：`ALTER TABLE jobs ADD COLUMN IF NOT EXISTS bundle_id TEXT NOT NULL DEFAULT ''` + `CREATE INDEX IF NOT EXISTS`，重复执行不报错（postgres 那边没得跑 `_init_schema`，库已存在时也不会先建索引再补列，因为这里顺序是我们自己写的）。
- 同步 `schema.sqlite.sql`、`schema.postgres.sql`（两份由 `scripts/gen_console_schema.py` 从 `_ddl` 生成，改完 `_ddl` 必须重跑；v10 那轮没跑，本次一并补齐）与 `schema.full.postgres.sql` 里 `jobs` 的建表段：加 `bundle_id` 列与 `jobs_bundle_idx`（脚本文本保持完整；Store 自己不在建表阶段跑索引，见 §4.1）。
- `comments.postgres.sql` 给 `jobs.bundle_id` 加 `COMMENT ON COLUMN`（PostgreSQL 的 `COMMENT ON` 是设置语义，重复执行只覆盖，可安全重跑；SQLite 不支持 COMMENT，那边只留行内 `--` 注释）。

### 4.5 不动的东西

stage 注册表、闸门、bundle 状态机、`bundle_members`、`artifact_versions` 的写入路径。`bundle_id` 纯记账：不参与任何校验、不参与训练数据选择、不触发冻结检查。

## 5. 前端

### 5.1 提交表单（`JobStagePage`，铺到所有提交页）

- 表单顶部加**项目下拉**：初值取 `useSelectedProject()`（跟随顶栏），改选时调用同一个 setter —— 它内部走 `writeSelectedProject`，会广播 `kev:project-changed`，顶栏切换器和各页的「当前项目 / 全部」范围订阅了这个事件，于是自己跟着更新，不需要新造状态。
- 项目下面加 **bundle 下拉**：`api.bundles(projectId)`，选项文案 `名字 · 状态`，第一项是「（不归属任何 bundle）」；项目变更即重取列表并清空已选。
- 提交 payload 多带 `bundle_id`。

### 5.2 阶段名字表

把 `console.data.kind.*` 扩成覆盖全部 20 个 kind 的一份键表（数据集页的提交流程图与列表列共用它）。数据轨 8 个沿用现词；其余 12 个取注册表 title：

| kind | 中文 | | kind | 中文 |
|---|---|---|---|---|
| plan_size | 计划规模 | | train | SFT 训练 |
| generate | 生成数据 | | baseline | 基线打分（零样本对照） |
| distill | 蒸馏 | | benchmark | 开发集打分 |
| distill_daemon | 蒸馏守护 | | compare | 配对 bootstrap 对比 |
| goldset | 金标集 | | calibrate | 温度拟合 |
| goldset_audit | 金标分歧审计 | | image | 构建部署镜像 |
| split | 划分 | | deploy | 启动 System One 端点 |
| precheck | 预检 | | smoke | 冒烟测试 |
| make_examples | 生成范例 | | publish | 发布到 Hub |
| materialize | 合成训练快照 | | modal | Modal 部署 |

（`stages/__init__.py` 的注释写着「14 种作业」，实际注册的是 20 种 —— 顺手改正那句注释，别的不动。）

### 5.3 作业表（`JobBoard`，数据集页/`/studio/jobs`/训练/评测/部署共用）

- 新增**阶段**列：`中文名 kind原文`，悬浮显示后端 title。
- 新增 **bundle** 列：`api.stages()` 之外再用 `job.bundle_name`；有归属时是一个可点链接（点了设 `externalFilter` 到该 bundle），没归属显示「—」。
- 顶部加 bundle 芯片一排（仅「当前项目」范围）：当前项目的各 bundle + 「全部」，与现有的状态芯片、下钻清除按钮是同一套 `FilterChip`。
- 搜索框的匹配范围加 kind 中文名与 bundle 名 —— 打「蒸馏守护」应该能搜到 `distill_daemon`。
- 这一层的定位是**快查**：芯片只改列表的可见行，不展开任何详情；要看全一个 bundle 归到 §5.5 的卡里去审。

### 5.4 数据集表（`DatasetTable`）

加**阶段**列（产出该数据集的作业的 kind 名）与 **bundle** 列（同一作业的归属），以及顶部 bundle 芯片筛选。平铺加列，**不做分组折叠**，也**不加主从两栏**（D4：数据集页只做快查，审在 §5.5）。

### 5.5 项目详情页的 bundle 卡

bundle 那一行展开后列出：**为它跑过的作业**（`jobs.filter(j => j.bundle_id === bundle.id)`，显示阶段中文名 + 状态）与**它名下的数据集**。数据获取沿用页面已有的 `api.jobs({ project })` + `api.bundles(id)`，按 `bundle_id` 前端过滤即可，不为这个新开端点。

注意这个文件已经 1096 行，新卡按现有 `Panel`/tab 组件的写法挂在既有 bundle 区旁边，不要再往那个组件函数体里塞逻辑（把它拆成独立子组件）。

### 5.6 类型与文案

- `lib/console.ts`：`Job` 加 `bundle_id: string` 与 `bundle_name: string | null`；`api.submit` 的入参加 `bundle_id`；`api.jobs` 的查询参数加 `bundle`。
- `strings.ts`：新列头、芯片标签、空归属文案（中英双语，跟现有 `studio.board.col.*` 一路）。
- 作业详情页 `JobDetailPanel` 头部一并显示 bundle 名。

## 6. 非目标与反目标

- 不做自动挂成员（D5）。
- 不做按 bundle 折叠成树的分组视图。
- 不在数据集页或作业页长出主从两栏（master-detail）：两处入口的分工是快查 vs 审，不是同一个功能做两遍。
- 不让 `bundle_id` 参与闸门、冻结检查或训练数据选择。
- 不改 bundle 的状态机、不改 `artifact_versions` 的产生方式。
- 反目标：技术上把两列都加上了，但两处列表（数据集 / 作业）各用一套阶段名字或各拼一份 bundle 文案 —— 那正是这次要消灭的东西，比不加列更糟。

## 7. 验收

**后端**（`uv run python -m pytest tests/test_console_bundles.py tests/test_console_api.py -q`，按 kev-verify 流程再跑全量）：

1. 带 `bundle_id` 提交 → 落库 → `GET /console/api/jobs/{id}` 回显该 id 与 `bundle_name`。
2. `GET /console/api/jobs?bundle=<id>` 只回该 bundle 的作业，且同 bundle 同 kind 的多个作业都在。
3. 未知 bundle → 404；bundle 属于别的项目 → 400 `field="bundle_id"`。
4. 不带 `bundle_id` 提交 → `''`，行为与今天逐字节一致（现有 56 个 console 测试不许变红）。
5. retry 出来的新作业继承 `bundle_id`。
6. v11 迁移幂等：同一库连跑两遍迁移 SQL 不报错；旧库升级后 `bundle_id` 全为 `''`。
7. **旧库能开机**：拿一个 `schema_version` < 11 的 sqlite 文件（可以直接用 v6 那份形状）`Store(db_path=...)` 能起来，`jobs` 有 `bundle_id`，`jobs_bundle_idx` 与 `jobs_project_idx` 都在，存量行的 `bundle_id` 为 `''`。这条同时把 v7 留下的 `_init_schema` 先于 `_migrate` 的陷阱钉住：v11 只要不写这条测试，就会栽在同一个坑里。

**前端**：`npm run test:console`（阶段名字表覆盖全部 20 个 kind、列渲染、bundle 空值显示「—」）+ `npm run lint` + typegen；手动确认四件事 —— 数据集页两个标签都出现两列、芯片能筛能清、提交表单换项目后顶栏与列表范围同步、项目详情页 bundle 卡能反查作业。

## 8. 遗留（不在本次范围，值得单独一轮）

- 「意图」与「事实」目前仍是两套：作业声明的 bundle ≠ `bundle_members` 里真实的成员。等这套归属攒下足够多的行，值得回头核一次「声明给了 A 却挂进了 B」的不一致率，再决定要不要做成校验。
- `distill_daemon` 这类长驻守护作业，一天一轮地跑，但归属在提交那一次就定死了。守护跑第 N 天时塞进的数据还算不算当初那个 bundle，是个真问题，本设计只负责把它如实记下来。
