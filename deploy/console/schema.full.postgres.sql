-- =============================================================================
-- console 数据库 · 完整建表脚本（PostgreSQL）
-- 来源：由 deploy/console 下 schema.postgres.sql + comments.postgres.sql + 旧 schema.full 内联 spec_json 合并而成
-- 表结构对齐 kev/console/db.py 的 _ddl()（SCHEMA_VERSION = 11，共 26 张表）
-- 两种后端差异：自增列用 BIGSERIAL，浮点列用 DOUBLE PRECISION。
-- 本文件包含：① 建表与索引 ② 表/字段注释 ③ 初始化数据（幂等：冲突则忽略；7 个医疗场景内联完整 spec_json）。
-- 执行顺序：建表 → 注释 → 初始数据，可重复执行（全部 IF NOT EXISTS / ON CONFLICT）。
-- =============================================================================

-- ------------------------------ ① 建表与索引 --------------------------------

CREATE TABLE IF NOT EXISTS console_meta (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS jobs (
  id            TEXT PRIMARY KEY,
  kind          TEXT NOT NULL,
  stage         TEXT NOT NULL,
  scenario      TEXT NOT NULL,
  title         TEXT NOT NULL,
  status        TEXT NOT NULL,
  request       TEXT NOT NULL,
  argv          TEXT NOT NULL,
  env_overlay   TEXT NOT NULL,
  cwd           TEXT NOT NULL,
  log_path      TEXT NOT NULL,
  artifacts_in  TEXT NOT NULL,
  artifacts_out TEXT NOT NULL,
  parent_id     TEXT REFERENCES jobs(id),
  attempt       INTEGER NOT NULL DEFAULT 1,
  daemon_id     TEXT,
  template_id   TEXT,
  project_id    TEXT NOT NULL DEFAULT '',
  bundle_id     TEXT NOT NULL DEFAULT '',
  exit_code     INTEGER,
  error         TEXT,
  created_at    TEXT NOT NULL,
  started_at    TEXT,
  finished_at   TEXT
);
CREATE INDEX IF NOT EXISTS jobs_status_idx    ON jobs(status);
CREATE INDEX IF NOT EXISTS jobs_scenario_idx  ON jobs(scenario, created_at DESC);
CREATE INDEX IF NOT EXISTS jobs_project_idx   ON jobs(project_id, created_at DESC);
CREATE INDEX IF NOT EXISTS jobs_bundle_idx    ON jobs(bundle_id, created_at DESC);

CREATE TABLE IF NOT EXISTS artifacts (
  id         TEXT PRIMARY KEY,
  kind       TEXT NOT NULL,
  name       TEXT NOT NULL,
  path       TEXT NOT NULL,
  meta       TEXT NOT NULL,
  bytes      INTEGER,
  created_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS artifacts_kind_name ON artifacts(kind, name);

CREATE TABLE IF NOT EXISTS lineage (
  parent   TEXT NOT NULL,
  child    TEXT NOT NULL,
  relation TEXT NOT NULL,
  job_id   TEXT REFERENCES jobs(id),
  PRIMARY KEY (parent, child, relation)
);

CREATE TABLE IF NOT EXISTS events (
  id     BIGSERIAL PRIMARY KEY,
  job_id TEXT NOT NULL REFERENCES jobs(id),
  ts     TEXT NOT NULL,
  stream TEXT NOT NULL,
  line   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS events_job_idx ON events(job_id, id);

CREATE TABLE IF NOT EXISTS api_keys (
  id        TEXT PRIMARY KEY,
  name      TEXT NOT NULL,
  key_hash  TEXT NOT NULL UNIQUE,
  prefix    TEXT NOT NULL,
  active    INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  revoked_at TEXT
);
CREATE INDEX IF NOT EXISTS api_keys_hash_idx ON api_keys(key_hash);

CREATE TABLE IF NOT EXISTS usage_log (
  id            BIGSERIAL PRIMARY KEY,
  key_id        TEXT NOT NULL REFERENCES api_keys(id),
  endpoint      TEXT NOT NULL,
  method        TEXT NOT NULL,
  status        INTEGER NOT NULL,
  input_tokens  INTEGER NOT NULL DEFAULT 0,
  output_tokens INTEGER NOT NULL DEFAULT 0,
  latency_ms    DOUBLE PRECISION NOT NULL,
  ts            TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS usage_log_key_ts_idx ON usage_log(key_id, ts);
CREATE INDEX IF NOT EXISTS usage_log_ts_idx      ON usage_log(ts);

CREATE TABLE IF NOT EXISTS distill_providers (
  id          TEXT PRIMARY KEY,
  name        TEXT NOT NULL,
  base_url    TEXT NOT NULL,
  model       TEXT NOT NULL,
  daily_limit INTEGER NOT NULL DEFAULT 500000,
  key_count   INTEGER NOT NULL DEFAULT 0,
  key_hints   TEXT NOT NULL DEFAULT '[]',
  active      INTEGER NOT NULL DEFAULT 1,
  created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS distill_providers_active_idx ON distill_providers(active);

CREATE TABLE IF NOT EXISTS distill_usage (
  id         BIGSERIAL PRIMARY KEY,
  job_id     TEXT NOT NULL REFERENCES jobs(id),
  provider_id TEXT NOT NULL,
  key_hash   TEXT NOT NULL,
  key_hint   TEXT NOT NULL,
  model      TEXT NOT NULL,
  base_url   TEXT NOT NULL,
  day        TEXT NOT NULL,
  tokens     INTEGER NOT NULL DEFAULT 0,
  ts         TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS distill_usage_ukd   ON distill_usage(provider_id, key_hash, day);
CREATE INDEX IF NOT EXISTS distill_usage_job_idx     ON distill_usage(job_id);
CREATE INDEX IF NOT EXISTS distill_usage_day_idx     ON distill_usage(day);

CREATE TABLE IF NOT EXISTS scenario_domains (
  id         TEXT PRIMARY KEY,
  slug       TEXT NOT NULL UNIQUE,
  label_zh   TEXT NOT NULL,
  label_en   TEXT NOT NULL,
  sort       INTEGER NOT NULL DEFAULT 0,
  -- 该域由 docs/domains/<spec_dir>/specs 供数（seed_scenarios 按它认领/新建域行）；
  -- 空串 = 手工建的域，不参与导入。
  spec_dir   TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS scenarios (
  id         TEXT PRIMARY KEY,
  domain_id  TEXT NOT NULL REFERENCES scenario_domains(id),
  slug       TEXT NOT NULL UNIQUE,
  label_zh   TEXT NOT NULL,
  label_en   TEXT NOT NULL,
  spec_path  TEXT NOT NULL,
  spec_json  TEXT,
  category   TEXT NOT NULL DEFAULT 'medical',
  -- 轨制与派生事实（kev/console/scenario_specs.derive_track）：track = rule|distill|both|llm，
  -- generator_kind = engine（spec.generator 九件套）|script（legacy gen_<场景>.py）|''，
  -- distill_yaml = 该场景的 EasyDistill 配置（仓库相对路径）或 ''，
  -- distill_yaml_content = 该 yaml 的可编辑内容（DB 为编辑真相源；空 = 未导入/未编辑），
  -- origin = 'domains' 表示行由 docs/domains 的种子导入维护（'' = 手工建）。
  track           TEXT NOT NULL DEFAULT '',
  generator_kind  TEXT NOT NULL DEFAULT '',
  distill_yaml    TEXT NOT NULL DEFAULT '',
  distill_yaml_content TEXT,
  origin          TEXT NOT NULL DEFAULT '',
  sort       INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS scenarios_slug_idx    ON scenarios(slug);
CREATE INDEX IF NOT EXISTS scenarios_domain_idx  ON scenarios(domain_id);

CREATE TABLE IF NOT EXISTS scenario_spec_history (
  id          TEXT PRIMARY KEY,
  scenario_id TEXT NOT NULL REFERENCES scenarios(id),
  spec_json   TEXT NOT NULL,
  created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS spec_history_scenario_idx ON scenario_spec_history(scenario_id, created_at DESC);

CREATE TABLE IF NOT EXISTS stage_param_specs (
  kind        TEXT PRIMARY KEY,
  schema_json TEXT NOT NULL,
  version     INTEGER NOT NULL DEFAULT 1,
  updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS stage_param_spec_history (
  id          TEXT PRIMARY KEY,
  kind        TEXT NOT NULL,
  schema_json TEXT NOT NULL,
  version     INTEGER NOT NULL,
  created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS stage_param_history_kind_idx ON stage_param_spec_history(kind, created_at DESC);

CREATE TABLE IF NOT EXISTS job_templates (
  id         TEXT PRIMARY KEY,
  kind       TEXT NOT NULL,
  name       TEXT NOT NULL,
  scenario   TEXT NOT NULL DEFAULT '',
  params     TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS job_templates_kind_idx ON job_templates(kind, updated_at DESC);

CREATE TABLE IF NOT EXISTS projects (
  id          TEXT PRIMARY KEY,
  slug        TEXT NOT NULL UNIQUE,
  name        TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  status      TEXT NOT NULL DEFAULT 'active',
  scenario    TEXT NOT NULL DEFAULT '',
  goal        TEXT NOT NULL DEFAULT '',
  archived_at TEXT,
  freeze_min_records      INTEGER NOT NULL DEFAULT 300,
  freeze_min_review_ratio DOUBLE PRECISION    NOT NULL DEFAULT 0.10,
  created_at  TEXT NOT NULL,
  updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS project_members (
  id         TEXT PRIMARY KEY,
  project_id TEXT NOT NULL REFERENCES projects(id),
  email      TEXT NOT NULL,
  name       TEXT NOT NULL DEFAULT '',
  role       TEXT NOT NULL DEFAULT 'member',
  status     TEXT NOT NULL DEFAULT 'invited',
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS project_members_project_idx ON project_members(project_id);
CREATE UNIQUE INDEX IF NOT EXISTS project_members_email_idx ON project_members(project_id, email);

CREATE TABLE IF NOT EXISTS project_quota (
  project_id            TEXT PRIMARY KEY REFERENCES projects(id),
  training_hours_limit  DOUBLE PRECISION NOT NULL DEFAULT 0,
  training_hours_used   DOUBLE PRECISION NOT NULL DEFAULT 0,
  gpu_limit             INTEGER NOT NULL DEFAULT 0,
  api_calls_limit       INTEGER NOT NULL DEFAULT 0,
  api_calls_used        INTEGER NOT NULL DEFAULT 0,
  storage_gb_limit      DOUBLE PRECISION NOT NULL DEFAULT 0,
  storage_gb_used       DOUBLE PRECISION NOT NULL DEFAULT 0,
  updated_at            TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS webhooks (
  id                TEXT PRIMARY KEY,
  project_id        TEXT NOT NULL REFERENCES projects(id),
  url               TEXT NOT NULL,
  events            TEXT NOT NULL DEFAULT '[]',
  secret            TEXT NOT NULL DEFAULT '',
  active            INTEGER NOT NULL DEFAULT 1,
  last_status       INTEGER,
  last_delivered_at TEXT,
  created_at        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS webhooks_project_idx ON webhooks(project_id);

CREATE TABLE IF NOT EXISTS invoices (
  id         TEXT PRIMARY KEY,
  project_id TEXT NOT NULL REFERENCES projects(id),
  period     TEXT NOT NULL,
  amount     DOUBLE PRECISION NOT NULL,
  currency   TEXT NOT NULL DEFAULT 'USD',
  status     TEXT NOT NULL DEFAULT 'open',
  due_at     TEXT,
  issued_at  TEXT NOT NULL,
  line_items TEXT NOT NULL DEFAULT '[]'
);
CREATE INDEX IF NOT EXISTS invoices_project_idx ON invoices(project_id, period DESC);

-- ---- v9 数据策展（Project Hub PR A，与 kev/console/db.py::_ddl 逐列一致）----
-- artifact_versions —— 产物的不可变版本快照；artifacts 是可变指针（D2），故 artifact_id 不建 FK。
CREATE TABLE IF NOT EXISTS artifact_versions (
  id          TEXT PRIMARY KEY,
  artifact_id TEXT NOT NULL,
  seq         INTEGER NOT NULL,
  job_id      TEXT NOT NULL REFERENCES jobs(id),
  path        TEXT NOT NULL,
  sha256      TEXT NOT NULL,
  records     INTEGER,
  bytes       INTEGER,
  meta        TEXT NOT NULL DEFAULT '{}',
  spec_sha256 TEXT,
  created_at  TEXT NOT NULL,
  UNIQUE (artifact_id, seq)
);
CREATE INDEX IF NOT EXISTS artifact_versions_job_idx ON artifact_versions(job_id);
CREATE INDEX IF NOT EXISTS artifact_versions_artifact_idx ON artifact_versions(artifact_id, seq DESC);

CREATE TABLE IF NOT EXISTS bundles (
  id                 TEXT PRIMARY KEY,
  project_id         TEXT NOT NULL REFERENCES projects(id),
  name               TEXT NOT NULL,
  artifact_id        TEXT NOT NULL,
  status             TEXT NOT NULL,
  sha256             TEXT,
  records            INTEGER,
  reviewed_records   INTEGER,
  reviewed_native    INTEGER,
  reviewed_inherited INTEGER,
  review_ratio       DOUBLE PRECISION,
  freeze_checks      TEXT NOT NULL DEFAULT '[]',
  manifest_path      TEXT,
  manifest_sha256    TEXT,
  frozen_at          TEXT,
  note               TEXT NOT NULL DEFAULT '',
  created_at         TEXT NOT NULL,
  updated_at         TEXT NOT NULL,
  UNIQUE (project_id, name)
);

CREATE TABLE IF NOT EXISTS bundle_members (
  bundle_id       TEXT NOT NULL REFERENCES bundles(id),
  version_id      TEXT NOT NULL REFERENCES artifact_versions(id),
  op              TEXT NOT NULL,
  ord             INTEGER NOT NULL,
  records_in      INTEGER,
  records_kept    INTEGER,
  records_dropped INTEGER,
  drop_reasons    TEXT NOT NULL DEFAULT '{}',
  PRIMARY KEY (bundle_id, version_id)
);
CREATE INDEX IF NOT EXISTS bundle_members_ord_idx ON bundle_members(bundle_id, ord);

-- origin_project_id 不建 FK：删项目时只清成 ''（D13），同 jobs.project_id 的 '' 哨兵（D14）。
CREATE TABLE IF NOT EXISTS record_reviews (
  id                TEXT PRIMARY KEY,
  scenario          TEXT NOT NULL,
  origin_project_id TEXT NOT NULL DEFAULT '',
  fingerprint       TEXT NOT NULL,
  record_id         TEXT,
  verdict           TEXT NOT NULL,
  patch             TEXT,
  fingerprint_after TEXT,
  labels            TEXT NOT NULL DEFAULT '[]',
  note              TEXT NOT NULL DEFAULT '',
  reviewer          TEXT NOT NULL DEFAULT '',
  source_version_id TEXT REFERENCES artifact_versions(id),
  created_at        TEXT NOT NULL,
  updated_at        TEXT NOT NULL,
  UNIQUE (scenario, fingerprint)
);
CREATE INDEX IF NOT EXISTS record_reviews_scenario_idx ON record_reviews(scenario, fingerprint);
CREATE INDEX IF NOT EXISTS record_reviews_project_idx ON record_reviews(origin_project_id);

CREATE TABLE IF NOT EXISTS record_review_history (
  id         TEXT PRIMARY KEY,
  review_id  TEXT NOT NULL REFERENCES record_reviews(id),
  verdict    TEXT NOT NULL,
  patch      TEXT,
  labels     TEXT NOT NULL DEFAULT '[]',
  note       TEXT NOT NULL DEFAULT '',
  reviewer   TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS review_history_review_idx ON record_review_history(review_id, created_at DESC);

CREATE TABLE IF NOT EXISTS project_releases (
  id                   TEXT PRIMARY KEY,
  project_id           TEXT NOT NULL REFERENCES projects(id),
  name                 TEXT NOT NULL,
  bundle_id            TEXT REFERENCES bundles(id),
  bundle_sha256        TEXT,
  train_job_id         TEXT REFERENCES jobs(id),
  run_artifact         TEXT,
  eval_artifact        TEXT,
  comparison_artifact  TEXT,
  regression_artifact  TEXT,
  calibration_artifact TEXT,
  metrics              TEXT NOT NULL DEFAULT '{}',
  gates_snapshot       TEXT NOT NULL DEFAULT '[]',
  verdict              TEXT NOT NULL DEFAULT 'candidate',
  note                 TEXT NOT NULL DEFAULT '',
  created_at           TEXT NOT NULL,
  UNIQUE (project_id, name)
);


-- ------------------------------ ② 表与字段注释 ------------------------------
-- 表/字段注释与 comments.postgres.sql 一致；下方已覆盖 v9 全部 26 张表（含 v9 新增列与数据策展表）。

COMMENT ON TABLE  console_meta            IS '控制台元信息键值表（如 schema_version 等全局配置）';
COMMENT ON COLUMN console_meta.key        IS '元信息键（如 schema_version）';
COMMENT ON COLUMN console_meta.value      IS '元信息值（文本存储）';

COMMENT ON TABLE  jobs                    IS '作业/任务表：记录每次训练、评测、生成等作业的元数据与生命周期';
COMMENT ON COLUMN jobs.id                 IS '作业唯一 ID';
COMMENT ON COLUMN jobs.kind               IS '作业类型（如 train / benchmark / generate 等）';
COMMENT ON COLUMN jobs.stage              IS '作业所属阶段（stage）';
COMMENT ON COLUMN jobs.scenario           IS '关联场景 slug';
COMMENT ON COLUMN jobs.title              IS '作业标题';
COMMENT ON COLUMN jobs.status             IS '作业状态（pending / running / done / error 等）';
COMMENT ON COLUMN jobs.request            IS '请求体（JSON 文本）';
COMMENT ON COLUMN jobs.argv               IS '命令行参数（JSON 文本）';
COMMENT ON COLUMN jobs.env_overlay        IS '环境变量覆盖（JSON 文本）';
COMMENT ON COLUMN jobs.cwd                IS '作业工作目录';
COMMENT ON COLUMN jobs.log_path           IS '日志文件路径';
COMMENT ON COLUMN jobs.artifacts_in       IS '输入产物列表（JSON 文本）';
COMMENT ON COLUMN jobs.artifacts_out      IS '输出产物列表（JSON 文本）';
COMMENT ON COLUMN jobs.parent_id          IS '父作业 ID（自引用，用于作业编排/重试链）';
COMMENT ON COLUMN jobs.attempt            IS '重试次数，默认 1';
COMMENT ON COLUMN jobs.daemon_id          IS '守护进程 ID（后台执行时记录）';
COMMENT ON COLUMN jobs.template_id        IS '关联作业模板 ID';
COMMENT ON COLUMN jobs.exit_code          IS '进程退出码';
COMMENT ON COLUMN jobs.error              IS '错误信息（失败时报错内容）';
COMMENT ON COLUMN jobs.created_at         IS '创建时间（ISO8601 文本）';
COMMENT ON COLUMN jobs.started_at         IS '开始时间（ISO8601 文本，可空）';
COMMENT ON COLUMN jobs.finished_at        IS '结束时间（ISO8601 文本，可空）';

COMMENT ON TABLE  artifacts               IS '产物表：作业产生的文件、数据集、模型等产物';
COMMENT ON COLUMN artifacts.id            IS '产物唯一 ID';
COMMENT ON COLUMN artifacts.kind          IS '产物类型（如 dataset / model / log 等）';
COMMENT ON COLUMN artifacts.name          IS '产物名称';
COMMENT ON COLUMN artifacts.path          IS '产物存储路径';
COMMENT ON COLUMN artifacts.meta          IS '产物元数据（JSON 文本）';
COMMENT ON COLUMN artifacts.bytes         IS '产物字节大小（可空）';
COMMENT ON COLUMN artifacts.created_at    IS '创建时间（ISO8601 文本）';

COMMENT ON TABLE  lineage                 IS '血缘表：记录产物与作业之间的依赖/衍生关系';
COMMENT ON COLUMN lineage.parent          IS '父节点标识（如产物 ID 或作业 ID）';
COMMENT ON COLUMN lineage.child           IS '子节点标识';
COMMENT ON COLUMN lineage.relation        IS '关系类型（如 derived_from / produced_by 等）';
COMMENT ON COLUMN lineage.job_id          IS '关联作业 ID（可空）';

COMMENT ON TABLE  events                  IS '作业事件/日志流：逐行记录作业的标准输出/错误等日志';
COMMENT ON COLUMN events.id               IS '自增主键';
COMMENT ON COLUMN events.job_id           IS '关联作业 ID';
COMMENT ON COLUMN events.ts               IS '日志行时间戳（ISO8601 文本）';
COMMENT ON COLUMN events.stream           IS '日志流（如 stdout / stderr）';
COMMENT ON COLUMN events.line             IS '单条日志行文本';

COMMENT ON TABLE  api_keys                IS 'API 密钥表：对外服务的访问密钥管理';
COMMENT ON COLUMN api_keys.id             IS '密钥唯一 ID';
COMMENT ON COLUMN api_keys.name           IS '密钥名称（便于识别）';
COMMENT ON COLUMN api_keys.key_hash       IS '密钥哈希值（唯一索引，不存明文）';
COMMENT ON COLUMN api_keys.prefix         IS '密钥前缀（用于展示与定位，不暴露完整密钥）';
COMMENT ON COLUMN api_keys.active         IS '是否启用（1=启用，0=禁用）';
COMMENT ON COLUMN api_keys.created_at     IS '创建时间（ISO8601 文本）';
COMMENT ON COLUMN api_keys.revoked_at     IS '撤销时间（ISO8601 文本，可空）';

COMMENT ON TABLE  usage_log               IS 'API 调用使用量日志：逐次调用的用量与耗时记录';
COMMENT ON COLUMN usage_log.id            IS '自增主键';
COMMENT ON COLUMN usage_log.key_id        IS '关联 API 密钥 ID';
COMMENT ON COLUMN usage_log.endpoint      IS '被调用的端点路径';
COMMENT ON COLUMN usage_log.method        IS 'HTTP 方法（GET / POST 等）';
COMMENT ON COLUMN usage_log.status        IS 'HTTP 响应状态码';
COMMENT ON COLUMN usage_log.input_tokens  IS '输入 token 数';
COMMENT ON COLUMN usage_log.output_tokens IS '输出 token 数';
COMMENT ON COLUMN usage_log.latency_ms    IS '请求延迟（毫秒，浮点）';
COMMENT ON COLUMN usage_log.ts            IS '调用时间戳（ISO8601 文本）';

COMMENT ON TABLE  distill_providers       IS '蒸馏/代理供应商配置：外部推理供应商的连接与额度';
COMMENT ON COLUMN distill_providers.id         IS '供应商唯一 ID';
COMMENT ON COLUMN distill_providers.name       IS '供应商名称';
COMMENT ON COLUMN distill_providers.base_url   IS '服务基础地址';
COMMENT ON COLUMN distill_providers.model      IS '使用的模型名';
COMMENT ON COLUMN distill_providers.daily_limit IS '每日 token 额度';
COMMENT ON COLUMN distill_providers.key_count  IS '已配置密钥数量';
COMMENT ON COLUMN distill_providers.key_hints  IS '密钥提示列表（JSON 文本）';
COMMENT ON COLUMN distill_providers.active     IS '是否启用（1/0）';
COMMENT ON COLUMN distill_providers.created_at IS '创建时间（ISO8601 文本）';

COMMENT ON TABLE  distill_usage           IS '蒸馏供应商用量明细：按供应商/密钥/日期聚合的消耗';
COMMENT ON COLUMN distill_usage.id         IS '自增主键';
COMMENT ON COLUMN distill_usage.job_id     IS '关联作业 ID';
COMMENT ON COLUMN distill_usage.provider_id IS '供应商 ID';
COMMENT ON COLUMN distill_usage.key_hash   IS '使用的密钥哈希';
COMMENT ON COLUMN distill_usage.key_hint   IS '密钥提示';
COMMENT ON COLUMN distill_usage.model      IS '模型名';
COMMENT ON COLUMN distill_usage.base_url   IS '服务地址';
COMMENT ON COLUMN distill_usage.day        IS '统计日期（YYYY-MM-DD）';
COMMENT ON COLUMN distill_usage.tokens     IS '当日消耗 token 数';
COMMENT ON COLUMN distill_usage.ts         IS '记录时间戳（ISO8601 文本）';

COMMENT ON TABLE  scenario_domains        IS '场景领域表：场景的顶层分类（如 medical）';
COMMENT ON COLUMN scenario_domains.id      IS '领域唯一 ID';
COMMENT ON COLUMN scenario_domains.slug    IS '领域唯一标识（唯一）';
COMMENT ON COLUMN scenario_domains.label_zh IS '领域中文名';
COMMENT ON COLUMN scenario_domains.label_en IS '领域英文名';
COMMENT ON COLUMN scenario_domains.sort     IS '展示排序';
COMMENT ON COLUMN scenario_domains.created_at IS '创建时间（ISO8601 文本）';

COMMENT ON TABLE  scenarios               IS '场景定义表：每个训练/评测场景的规格（含 spec_json）';
COMMENT ON COLUMN scenarios.id            IS '场景唯一 ID';
COMMENT ON COLUMN scenarios.domain_id     IS '关联领域 ID';
COMMENT ON COLUMN scenarios.slug          IS '场景唯一标识（唯一）';
COMMENT ON COLUMN scenarios.label_zh      IS '场景中文名';
COMMENT ON COLUMN scenarios.label_en      IS '场景英文名';
COMMENT ON COLUMN scenarios.spec_path     IS '规格文件相对路径';
COMMENT ON COLUMN scenarios.spec_json     IS '场景规格定义（JSON 文本）';
COMMENT ON COLUMN scenarios.category      IS '场景分类（默认 medical）';
COMMENT ON COLUMN scenarios.sort          IS '展示排序';
COMMENT ON COLUMN scenarios.created_at    IS '创建时间（ISO8601 文本）';
COMMENT ON COLUMN scenarios.updated_at    IS '更新时间（ISO8601 文本）';

COMMENT ON TABLE  scenario_spec_history   IS '场景规格变更历史：每次 spec 变更的快照';
COMMENT ON COLUMN scenario_spec_history.id         IS '历史记录唯一 ID';
COMMENT ON COLUMN scenario_spec_history.scenario_id IS '关联场景 ID';
COMMENT ON COLUMN scenario_spec_history.spec_json  IS '历史规格快照（JSON 文本）';
COMMENT ON COLUMN scenario_spec_history.created_at IS '快照创建时间（ISO8601 文本）';

COMMENT ON TABLE  stage_param_specs        IS '作业阶段参数 schema（单一真相源，可经 API 版本化修改）';
COMMENT ON COLUMN stage_param_specs.kind       IS '作业类型（主键，与 jobs.kind 对齐）';
COMMENT ON COLUMN stage_param_specs.schema_json IS '参数 schema 定义（JSON 文本，对齐前端 FieldSpec）';
COMMENT ON COLUMN stage_param_specs.version    IS 'schema 版本号';
COMMENT ON COLUMN stage_param_specs.updated_at IS '更新时间（ISO8601 文本）';

COMMENT ON TABLE  stage_param_spec_history IS '参数 schema 变更历史：每次 schema 变更的快照';
COMMENT ON COLUMN stage_param_spec_history.id          IS '历史记录唯一 ID';
COMMENT ON COLUMN stage_param_spec_history.kind        IS '作业类型';
COMMENT ON COLUMN stage_param_spec_history.schema_json IS '历史 schema 快照（JSON 文本）';
COMMENT ON COLUMN stage_param_spec_history.version     IS '快照对应版本号';
COMMENT ON COLUMN stage_param_spec_history.created_at IS '快照创建时间（ISO8601 文本）';

COMMENT ON TABLE  job_templates           IS '作业模板：跨会话复用/编辑某类任务的参数预设';
COMMENT ON COLUMN job_templates.id         IS '模板唯一 ID';
COMMENT ON COLUMN job_templates.kind       IS '作业类型';
COMMENT ON COLUMN job_templates.name       IS '模板名称';
COMMENT ON COLUMN job_templates.scenario   IS '关联场景 slug（默认空）';
COMMENT ON COLUMN job_templates.params     IS '预设参数（JSON 文本，默认 {}）';
COMMENT ON COLUMN job_templates.created_at IS '创建时间（ISO8601 文本）';
COMMENT ON COLUMN job_templates.updated_at IS '更新时间（ISO8601 文本）';

COMMENT ON TABLE  projects                IS '项目表（管理面 ch6）：多租户项目根实体';
COMMENT ON COLUMN projects.id             IS '项目唯一 ID';
COMMENT ON COLUMN projects.slug           IS '项目唯一标识（唯一）';
COMMENT ON COLUMN projects.name           IS '项目名称';
COMMENT ON COLUMN projects.description    IS '项目描述';
COMMENT ON COLUMN projects.created_at     IS '创建时间（ISO8601 文本）';
COMMENT ON COLUMN projects.updated_at     IS '更新时间（ISO8601 文本）';

COMMENT ON TABLE  project_members         IS '项目成员表：项目与成员的关联及角色';
COMMENT ON COLUMN project_members.id       IS '成员记录唯一 ID';
COMMENT ON COLUMN project_members.project_id IS '关联项目 ID';
COMMENT ON COLUMN project_members.email    IS '成员邮箱';
COMMENT ON COLUMN project_members.name     IS '成员名称';
COMMENT ON COLUMN project_members.role     IS '成员角色（默认 member）';
COMMENT ON COLUMN project_members.status   IS '成员状态（默认 invited）';
COMMENT ON COLUMN project_members.created_at IS '创建时间（ISO8601 文本）';

COMMENT ON TABLE  project_quota           IS '项目配额表：训练时长、GPU、API 调用、存储等限额';
COMMENT ON COLUMN project_quota.project_id           IS '关联项目 ID（主键）';
COMMENT ON COLUMN project_quota.training_hours_limit IS '训练时长上限（小时）';
COMMENT ON COLUMN project_quota.training_hours_used  IS '训练时长已用（小时）';
COMMENT ON COLUMN project_quota.gpu_limit             IS 'GPU 数量上限';
COMMENT ON COLUMN project_quota.api_calls_limit      IS 'API 调用次数上限';
COMMENT ON COLUMN project_quota.api_calls_used       IS 'API 调用已用次数';
COMMENT ON COLUMN project_quota.storage_gb_limit     IS '存储上限（GB）';
COMMENT ON COLUMN project_quota.storage_gb_used      IS '存储已用（GB）';
COMMENT ON COLUMN project_quota.updated_at          IS '更新时间（ISO8601 文本）';

COMMENT ON TABLE  webhooks                IS '项目 Webhook 表：事件回调配置';
COMMENT ON COLUMN webhooks.id              IS 'Webhook 唯一 ID';
COMMENT ON COLUMN webhooks.project_id      IS '关联项目 ID';
COMMENT ON COLUMN webhooks.url             IS '回调地址';
COMMENT ON COLUMN webhooks.events          IS '订阅事件列表（JSON 文本）';
COMMENT ON COLUMN webhooks.secret          IS '签名密钥';
COMMENT ON COLUMN webhooks.active          IS '是否启用（1/0）';
COMMENT ON COLUMN webhooks.last_status     IS '上次投递 HTTP 状态码（可空）';
COMMENT ON COLUMN webhooks.last_delivered_at IS '上次成功投递时间（ISO8601 文本，可空）';
COMMENT ON COLUMN webhooks.created_at      IS '创建时间（ISO8601 文本）';

COMMENT ON TABLE  invoices                IS '项目账单/发票表：计费周期与明细';
COMMENT ON COLUMN invoices.id             IS '账单唯一 ID';
COMMENT ON COLUMN invoices.project_id     IS '关联项目 ID';
COMMENT ON COLUMN invoices.period         IS '计费周期标识';
COMMENT ON COLUMN invoices.amount         IS '账单金额（浮点）';
COMMENT ON COLUMN invoices.currency       IS '币种（默认 USD）';
COMMENT ON COLUMN invoices.status         IS '账单状态（默认 open）';
COMMENT ON COLUMN invoices.due_at         IS '到期时间（ISO8601 文本，可空）';
COMMENT ON COLUMN invoices.issued_at      IS '开具时间（ISO8601 文本）';
COMMENT ON COLUMN invoices.line_items     IS '账单明细（JSON 文本，默认 []）';

-- ---- v9 新增列与数据策展表的注释（与 comments.postgres.sql 一致）----
COMMENT ON COLUMN jobs.project_id    IS '所属项目 id；空串是具名 legacy 哨兵（D14），永不出现在具体项目列表。';
COMMENT ON COLUMN jobs.bundle_id     IS '作业在提交那一刻显式声明它为哪个 bundle 而跑（bundles.id，D3）；空串 = 未归属。纯记账：不参与闸门、不参与冻结检查、不选训练数据。';

COMMENT ON COLUMN scenario_domains.spec_dir IS '该域由 docs/domains/<spec_dir>/specs 供数（seed_scenarios 据此认领/新建域行）；空串为手工建域、不参与导入。';

COMMENT ON COLUMN scenarios.track            IS '轨制（scenario_specs.derive_track 派生）：rule|distill|both|llm，空串未定。';
COMMENT ON COLUMN scenarios.generator_kind   IS '生成器类型：engine（spec.generator 九件套）|script（legacy gen_<场景>.py）|空串。';
COMMENT ON COLUMN scenarios.distill_yaml     IS '该场景的 EasyDistill 配置（仓库相对路径）或空串。';
COMMENT ON COLUMN scenarios.origin           IS '''domains'' 表示行由 docs/domains 种子导入维护；空串为手工建。';

COMMENT ON COLUMN projects.status                  IS '项目状态，默认 active（如 active|archived）。';
COMMENT ON COLUMN projects.scenario                IS '项目主场景 slug，默认空串。';
COMMENT ON COLUMN projects.goal                    IS '项目目标描述，默认空串。';
COMMENT ON COLUMN projects.archived_at             IS '归档时间，未归档为 NULL。';
COMMENT ON COLUMN projects.freeze_min_records      IS '冻结快照所需的最小记录数，默认 300。';
COMMENT ON COLUMN projects.freeze_min_review_ratio IS '冻结快照所需的最小标注覆盖率，默认 0.10。';

COMMENT ON TABLE  artifact_versions             IS '产物不可变版本快照：登记即算 sha256/records。artifact_id 有意不建指向 artifacts 的 FK（artifacts 是可变指针，D2）。';
COMMENT ON COLUMN artifact_versions.id          IS '版本行主键。';
COMMENT ON COLUMN artifact_versions.artifact_id IS '所属产物 id（逻辑对应 artifacts.id，不建 FK）。';
COMMENT ON COLUMN artifact_versions.seq         IS '同一产物内的版本序号，与 artifact_id 组唯一。';
COMMENT ON COLUMN artifact_versions.job_id      IS '产出该版本的作业 id（jobs.id）。';
COMMENT ON COLUMN artifact_versions.path        IS '该版本的落盘路径。';
COMMENT ON COLUMN artifact_versions.sha256      IS '内容的 sha256 摘要。';
COMMENT ON COLUMN artifact_versions.records     IS '记录条数（数据集类产物），可空。';
COMMENT ON COLUMN artifact_versions.bytes       IS '字节数，可空。';
COMMENT ON COLUMN artifact_versions.meta        IS '版本元数据（JSON 文本），默认 {}。';
COMMENT ON COLUMN artifact_versions.spec_sha256 IS '生成本版本所用场景 spec 的 sha256，可空。';
COMMENT ON COLUMN artifact_versions.created_at  IS '创建时间（UTC ISO8601）。';

COMMENT ON TABLE  bundles                    IS '冻结快照 bundle：项目内 name 唯一，汇总成员版本与冻结检查结果。';
COMMENT ON COLUMN bundles.id                 IS 'bundle 主键。';
COMMENT ON COLUMN bundles.project_id         IS '项目 id（projects.id）。';
COMMENT ON COLUMN bundles.name               IS 'bundle 名称，与 project_id 组唯一。';
COMMENT ON COLUMN bundles.artifact_id        IS 'bundle 代表的产物 id（逻辑对应 artifacts，不建 FK）。';
COMMENT ON COLUMN bundles.status             IS 'bundle 状态（如 draft|frozen）。';
COMMENT ON COLUMN bundles.sha256             IS 'bundle 内容摘要，冻结前可空。';
COMMENT ON COLUMN bundles.records            IS '记录总条数，可空。';
COMMENT ON COLUMN bundles.reviewed_records   IS '已标注记录数，可空。';
COMMENT ON COLUMN bundles.reviewed_native    IS '本项目原生标注数，可空。';
COMMENT ON COLUMN bundles.reviewed_inherited IS '跨轮继承的标注数，可空。';
COMMENT ON COLUMN bundles.review_ratio       IS '标注覆盖率（reviewed/records），可空。';
COMMENT ON COLUMN bundles.freeze_checks      IS '冻结检查项结果（JSON 数组文本），默认 []。';
COMMENT ON COLUMN bundles.manifest_path      IS '清单文件路径，可空。';
COMMENT ON COLUMN bundles.manifest_sha256    IS '清单文件摘要，可空。';
COMMENT ON COLUMN bundles.frozen_at          IS '冻结时间，未冻结为 NULL。';
COMMENT ON COLUMN bundles.note               IS '备注，默认空串。';
COMMENT ON COLUMN bundles.created_at         IS '创建时间（UTC ISO8601）。';
COMMENT ON COLUMN bundles.updated_at         IS '最后更新时间（UTC ISO8601）。';

COMMENT ON TABLE  bundle_members                 IS 'bundle 成员：关联 bundles 与 artifact_versions，记录该步操作的取舍统计。';
COMMENT ON COLUMN bundle_members.bundle_id       IS 'bundle id（bundles.id）。';
COMMENT ON COLUMN bundle_members.version_id      IS '成员产物版本 id（artifact_versions.id）。';
COMMENT ON COLUMN bundle_members.op              IS '该成员对 bundle 的操作类型（如 add|filter）。';
COMMENT ON COLUMN bundle_members.ord             IS '成员在 bundle 内的顺序。';
COMMENT ON COLUMN bundle_members.records_in      IS '进入该步的记录数，可空。';
COMMENT ON COLUMN bundle_members.records_kept    IS '该步保留的记录数，可空。';
COMMENT ON COLUMN bundle_members.records_dropped IS '该步丢弃的记录数，可空。';
COMMENT ON COLUMN bundle_members.drop_reasons    IS '丢弃原因计数（JSON 文本），默认 {}。';

COMMENT ON TABLE  record_reviews                   IS '逐条标注记录：按 (scenario, fingerprint) 唯一。origin_project_id 有意不建 FK，删项目时按 D13 将其清为空串、保留标注供跨轮继承。';
COMMENT ON COLUMN record_reviews.id                IS '标注行主键。';
COMMENT ON COLUMN record_reviews.scenario          IS '场景 slug（标注作用域）。';
COMMENT ON COLUMN record_reviews.origin_project_id IS '来源项目 id；空串为「来源已删」哨兵（不建 FK，见 D13/D14）。';
COMMENT ON COLUMN record_reviews.fingerprint       IS '被标注记录的指纹（内容哈希），与 scenario 组唯一。';
COMMENT ON COLUMN record_reviews.record_id         IS '原始记录 id，可空。';
COMMENT ON COLUMN record_reviews.verdict           IS '标注结论（如 accept|reject|edit）。';
COMMENT ON COLUMN record_reviews.patch             IS '修订补丁（JSON 文本），可空。';
COMMENT ON COLUMN record_reviews.fingerprint_after IS '应用 patch 后的新指纹，可空。';
COMMENT ON COLUMN record_reviews.labels            IS '标签列表（JSON 数组文本），默认 []。';
COMMENT ON COLUMN record_reviews.note              IS '标注备注，默认空串。';
COMMENT ON COLUMN record_reviews.reviewer          IS '标注人，默认空串。';
COMMENT ON COLUMN record_reviews.source_version_id IS '标注所依据的产物版本 id（artifact_versions.id），可空。';
COMMENT ON COLUMN record_reviews.created_at        IS '创建时间（UTC ISO8601）。';
COMMENT ON COLUMN record_reviews.updated_at        IS '最后更新时间（UTC ISO8601）。';

COMMENT ON TABLE  record_review_history            IS '标注历史：每条 record_review 覆盖前归档一份（同 scenario_spec_history 写法）。';
COMMENT ON COLUMN record_review_history.id         IS '历史行主键。';
COMMENT ON COLUMN record_review_history.review_id  IS '标注行 id（record_reviews.id）。';
COMMENT ON COLUMN record_review_history.verdict    IS '归档时的结论。';
COMMENT ON COLUMN record_review_history.patch      IS '归档时的补丁，可空。';
COMMENT ON COLUMN record_review_history.labels     IS '归档时的标签（JSON 数组文本），默认 []。';
COMMENT ON COLUMN record_review_history.note       IS '归档时的备注，默认空串。';
COMMENT ON COLUMN record_review_history.reviewer   IS '归档时的标注人，默认空串。';
COMMENT ON COLUMN record_review_history.created_at IS '归档时间（UTC ISO8601）。';

COMMENT ON TABLE  project_releases                   IS '项目发布：冻结 bundle + 训练/评测产物的结论快照，(project_id, name) 唯一。';
COMMENT ON COLUMN project_releases.id                IS '发布行主键。';
COMMENT ON COLUMN project_releases.project_id        IS '项目 id（projects.id）。';
COMMENT ON COLUMN project_releases.name              IS '发布名称，与 project_id 组唯一。';
COMMENT ON COLUMN project_releases.bundle_id         IS '关联的冻结 bundle id（bundles.id），可空。';
COMMENT ON COLUMN project_releases.bundle_sha256     IS 'bundle 内容摘要，可空。';
COMMENT ON COLUMN project_releases.train_job_id      IS '产出模型的训练作业 id（jobs.id），可空。';
COMMENT ON COLUMN project_releases.run_artifact      IS 'run 阶段产物引用，可空。';
COMMENT ON COLUMN project_releases.eval_artifact     IS '评测产物引用，可空。';
COMMENT ON COLUMN project_releases.comparison_artifact  IS '对比产物引用，可空。';
COMMENT ON COLUMN project_releases.regression_artifact  IS '回归产物引用，可空。';
COMMENT ON COLUMN project_releases.calibration_artifact IS '校准产物引用，可空。';
COMMENT ON COLUMN project_releases.metrics           IS '发布指标快照（JSON 文本），默认 {}。';
COMMENT ON COLUMN project_releases.gates_snapshot    IS '发布门禁检查结果（JSON 数组文本），默认 []。';
COMMENT ON COLUMN project_releases.verdict           IS '发布结论，默认 candidate（如 candidate|released|rejected）。';
COMMENT ON COLUMN project_releases.note              IS '备注，默认空串。';
COMMENT ON COLUMN project_releases.created_at        IS '创建时间（UTC ISO8601）。';


-- ------------------------------ ③ 初始化数据 --------------------------------
-- 与 kev/console/db.py 的幂等播种一致：冲突（按主键/唯一键）则忽略，重复执行安全。
-- schema_version 设为 11，与当前代码 SCHEMA_VERSION 一致（全新库无需再走迁移）。

INSERT INTO console_meta (key, value) VALUES ('schema_version', '11') ON CONFLICT(key) DO NOTHING;

INSERT INTO scenario_domains (id, slug, label_zh, label_en, sort, spec_dir, created_at) VALUES ('medical', 'medical', '医疗', 'Medical', 0, 'medical', '2026-01-01T00:00:00+00:00') ON CONFLICT(slug) DO NOTHING;
INSERT INTO scenario_domains (id, slug, label_zh, label_en, sort, spec_dir, created_at) VALUES ('finance', 'finance', '金融', 'Finance', 10, 'finance', '2026-01-01T00:00:00+00:00') ON CONFLICT(slug) DO NOTHING;
INSERT INTO scenario_domains (id, slug, label_zh, label_en, sort, spec_dir, created_at) VALUES ('education', 'education', '教育', 'Education', 20, 'education', '2026-01-01T00:00:00+00:00') ON CONFLICT(slug) DO NOTHING;
INSERT INTO scenario_domains (id, slug, label_zh, label_en, sort, spec_dir, created_at) VALUES ('science', 'science', '科研', 'Research', 30, 'science', '2026-01-01T00:00:00+00:00') ON CONFLICT(slug) DO NOTHING;
INSERT INTO scenario_domains (id, slug, label_zh, label_en, sort, spec_dir, created_at) VALUES ('law', 'law', '法律', 'Law', 40, 'law', '2026-01-01T00:00:00+00:00') ON CONFLICT(slug) DO NOTHING;

INSERT INTO scenarios (id, domain_id, slug, label_zh, label_en, spec_path, spec_json, category, sort, track, generator_kind, distill_yaml, origin, created_at, updated_at) VALUES ('critical-value', 'medical', 'critical-value', '危急值', 'Critical Value', 'docs/domains/medical/specs/critical-value.json', '{
  "name": "critical-value",
  "domain": "医院检验科与影像科报告复核。检验项目包括血钾、血钠、空腹血糖、肌酐、尿素氮、血气 pH、血红蛋白、血小板计数、白细胞计数、肌钙蛋白、D-二聚体。报告为中文，关键缩写与英文项目名混排（K+、Na+、GLU、Cr、pH、Hb、PLT、WBC、cTn、D-Dimer）。患者为门诊与住院混合，含成人、孕产妇与儿童。",
  "state": "一份已出具的检验或影像报告的结构化摘要：患者年龄性别、临床背景主诉（1 句）、检验项目名称与实测值（含单位）、是否含参考区间、以及报告是否遗漏了判读所需的患者信息（年龄/采样时间/单位）。不含医生结论。",
  "state_example": {
    "patient": "female 67",
    "context": "胸闷 3 天，血压 168/95 mmHg，既往 2 型糖尿病",
    "labs": {
      "K+": "2.9 mmol/L",
      "Na+": "141 mmol/L",
      "GLU": "9.8 mmol/L",
      "Cr": "96 umol/L",
      "pH": "7.36",
      "Hb": "132 g/L",
      "PLT": "213 x10^9/L",
      "WBC": "6.4 x10^9/L"
    },
    "ref_ranges_included": true,
    "missing_context": []
  },
  "questions": {
    "is_critical": {
      "type": "noul",
      "instructions": "该报告中的任一检验项目是否触及危急值（需要立即临床干预）？",
      "criteria": {
        "true": "至少一个项目超出危急值上下限，需要立即通知并干预",
        "false": "所有项目均在危急值范围内"
      }
    },
    "notify_within": {
      "type": "score",
      "instructions": "危急值应在多长时间内通知到主管医师？",
      "criteria": [
        "立即（15 分钟内）",
        "1 小时内",
        "当日内",
        "无需通知（全部项目均未触及危急值）"
      ]
    },
    "critical_item": {
      "type": "choice",
      "instructions": "触发危急值判定的是哪一类检验项目？",
      "criteria": {
        "none": "无（全部项目均未触及危急值）",
        "electrolyte": "电解质（血钾 K+、血钠 Na+）",
        "renal": "肾功能（肌酐 Cr、尿素氮）",
        "glucose_gas": "血糖与血气（血糖 GLU、血气 pH）",
        "cbc": "血常规（血红蛋白 Hb、血小板 PLT、白细胞 WBC）",
        "cardiac_coag": "心肌与凝血（肌钙蛋白 cTn、D-二聚体）"
      }
    },
    "evidence_sufficient": {
      "type": "noul",
      "instructions": "报告是否提供了判定危急值所需的全部要素（项目名、数值、单位、参考区间或判定标准）？",
      "criteria": {
        "true": "要素齐全，可直接对照阈值判定",
        "false": "缺少单位、参考区间或项目名，无法可靠判定"
      }
    }
  },
  "guidance": "危急值是本场景唯一判据：任一项目超出下表上下限即为 is_critical=true，label 取导致判定的那个项目。阈值（示例口径，实际以本院检验科危急值清单为准）：K+ <2.8 或 >6.2 mmol/L；Na+ <120 或 >160 mmol/L；GLU <2.8 或 >16.7 mmol/L；Cr >442 umol/L；pH <7.20 或 >7.60；Hb <50 或 >200 g/L；PLT <30 或 >1000 x10^9/L；WBC <1.5 或 >30 x10^9/L；cTn >0.04 ng/mL；D-Dimer >5 mg/L FEU。notify_within 由触发的项目决定，等级从 0（立即）到 3（当日内）：立即 15 分钟内适用于 K+>6.5、Na+>160 或 <120、pH<7.20、GLU>16.7 或 <2.8、cTn 升高伴胸痛、Hb<50；1 小时内的项目包括 K+ 在 2.8-3.0 或 6.2-6.5、Cr 在 442-600、PLT 在 30-50、Hb 在 50-70；其余触及危急值但未落入上述区间的为 2 小时内；仅 D-Dimer 孤立升高或 WBC 轻度异常为当日内。多个项目同时危急时 severity 取最快的一档，critical_item 取最快档中的项目。evidence_sufficient 为 false 时（缺单位、缺参考区间、缺项目名），is_critical 必须用软标签 target {\"true\":0.5,\"false\":0.5}，且 critical_item 不得凭猜测填写——证据不足即无把握。cr 阈值受年龄与性别影响很大，生成老年女性样本时 Cr 需明显更高才判危急，务必让数值与年龄方向一致。",
  "variety": [
    "科室来源：检验科、影像科、急诊、住院病房、门诊、体检中心",
    "危急值项目数（对应 is_critical 与 critical_item）：0 项全部正常、1 项触及、2 项同时触及、3 项以上同时触及、同一项目高低双侧都触及（如 K+ 同时 <2.8 且 >6.2 不可能，须只取真实方向）",
    "触发项目的六类归属（critical_item 逐项覆盖）：electrolyte（K+、Na+）、renal（Cr、尿素氮）、glucose_gas（GLU、pH）、cbc（Hb、PLT、WBC）、cardiac_coag（cTn、D-Dimer）、none（全部正常）",
    "电解质取值档（须与阈值方向一致）：K+ 正常 3.5-5.0 / 偏低 2.8-3.0 / 危急低 <2.8 / 偏高 6.2-6.5 / 危急高 >6.5；Na+ 正常 135-145 / 危急低 <120 / 危急高 >160",
    "肾功能与代谢取值档：Cr 正常 44-106 / 危急 442-600 / >600（老年女性基线更高，需明显更高才判危急）；GLU 正常 3.9-6.1 / 危急低 <2.8 / 危急高 >16.7；pH 正常 7.35-7.45 / 7.20-7.35 / <7.20 / >7.60",
    "血常规与心肌凝血取值档：Hb 正常 115-150 / 50-70 / <50；PLT 正常 125-350 / 30-50 / <30；WBC 正常 3.5-9.5 / 1.5-3.0 / <1.5 / >30；cTn <0.04 正常 / 0.04-0.1 升高 / >0.1 明显升高；D-Dimer <0.5 正常 / 0.5-5 升高 / >5 mg/L FEU",
    "通知时长档（notify_within 四档全覆盖）：0 立即（K+>6.5、Na+>160 或 <120、pH<7.20、GLU>16.7 或 <2.8、Hb<50）/ 1 小时内（K+ 2.8-3.0 或 6.2-6.5、Cr 442-600、PLT 30-50、Hb 50-70）/ 2 小时内（其余触及危急值项目）/ 3 当日内（孤立 D-Dimer 升高、WBC 轻度异常）",
    "报告完整度（对应 evidence_sufficient）：要素齐全、缺单位、缺参考区间、缺项目名、缺采样时间、缺患者年龄、两项以上同时缺失；evidence_sufficient=false 时 is_critical 必须用软标签且 critical_item 不得凭猜测填写",
    "患者人群：成人、儿童、孕产妇、老年（Cr 基线高）、肾功能不全者、透析患者",
    "临床背景：胸痛、呼吸困难、乏力、头晕、恶心呕吐、无明显症状（体检偶然发现）",
    "数值表述：带单位（mmol/L、g/L、x10^9/L、ng/mL、mg/L FEU）、仅给数值无单位、中文叙述夹英文缩写（K+、Cr、cTn、D-Dimer）、参考区间与实测值并列",
    "易错陷阱：老年女性 Cr 需明显高于 442 才判危急、儿童 Cr 基线低更易达危急、Hb 与 PLT 同时低下时不得只取其一、cTn 升高需结合胸痛才落在「立即」档"
  ]
}
', 'medical', 0, 'rule', 'script', '', 'domains', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00') ON CONFLICT(slug) DO NOTHING;

INSERT INTO scenarios (id, domain_id, slug, label_zh, label_en, spec_path, spec_json, category, sort, track, generator_kind, distill_yaml, origin, created_at, updated_at) VALUES ('diagnosis', 'medical', 'diagnosis', '诊断', 'Diagnosis', 'docs/domains/medical/specs/diagnosis.json', '{
  "name": "diagnosis",
  "domain": "门诊与急诊的初诊评估。患者因主诉就诊，需要给出初步鉴别方向、是否需要进一步检查、以及就诊紧急度。涵盖心血管、呼吸、消化、神经、泌尿、代谢内分泌、肌肉骨骼、血液肿瘤九大系统。",
  "state": "患者就诊时的结构化记录：人口学、主诉（患者原话，1-3 句）、生命体征、已完成的检验值、是否已做影像、合并症、患病时长。字段名短且跨记录固定。",
  "state_example": {
    "patient": "male 58",
    "chief_complaint": "活动后气促 2 周，伴下肢水肿",
    "vitals": "BP 152/92 mmHg, HR 104 bpm, SpO2 93%",
    "labs": {"肌钙蛋白": "0.9 ng/mL", "NT-proBNP": "3200 pg/mL", "肌酐": "96 umol/L"},
    "imaging": "未做",
    "comorbidities": ["高血压 10 年", "2 型糖尿病 8 年"],
    "duration": "2 周"
  },
  "questions": {
    "differential_direction": {
      "type": "choice",
      "instructions": "初步判断应优先考虑哪个系统的鉴别方向？",
      "criteria": {
        "cardiovascular": "心源性：胸痛、心悸、活动后气促、下肢水肿、血压异常",
        "respiratory": "呼吸系统：咳嗽咳痰、气促、喘息、胸膜相关症状",
        "gastrointestinal": "消化系统：腹痛、反酸、呕吐、腹泻、便血",
        "neurologic": "神经系统：头痛、眩晕、肢体麻木无力、意识改变、言语不清",
        "urinary": "泌尿系统：尿频尿急尿痛、血尿、肾绞痛、排尿困难",
        "endocrine": "代谢内分泌：多饮多尿、体重明显改变、怕冷乏力、血糖异常",
        "musculoskeletal": "肌肉骨骼：关节痛、腰痛、外伤、行走困难",
        "hematologic_oncologic": "血液与肿瘤：贫血貌、淋巴结肿大、盗汗、乏力消瘦",
        "undirected": "现有信息不足以定向，需先完善影像与检验"
      }
    },
    "needs_test": {
      "type": "noul",
      "instructions": "是否需要影像或实验室检查才能进一步明确诊断？",
      "criteria": {
        "true": "已有指向性线索，但仍需检查确认范围、程度或并发症",
        "false": "临床表现已足以给出方向性判断，无需追加检查"
      }
    },
    "urgency": {
      "type": "score",
      "instructions": "本次就诊的紧急程度如何？",
      "criteria": [
        "0：可按普通门诊预约，无需当日处理",
        "1：建议尽快门诊，但无需急诊",
        "2：需要急诊评估或当日处理",
        "3：存在危险信号，需立即急救"
      ]
    },
    "red_flag": {
      "type": "noul",
      "instructions": "是否存在需要立即处理的危险信号？",
      "criteria": {
        "true": "存在危险信号：意识改变、持续胸痛、明显呼吸困难、大出血、严重低血压、SpO2 下降",
        "false": "未发现危险信号"
      }
    }
  },
  "guidance": "differential_direction 优先取最紧急且最专科化的系统：任一危险信号存在时，方向仍按受累系统给出（除非主诉指向两个系统且无法判定），但 needs_test 必为 true、urgency 必为 3。三个方向并存无法判定时取 undirected，且 needs_test 为 true。urgency 3 与 red_flag true 等价：存在任一危险信号则两者同时为真。urgency 0 时 red_flag 必为 false。needs_test 为 false 仅在主诉已高度特异且体征与检验均无异常时出现，此时 urgency 不得为 2 或 3。",
  "variety": [
    "九个系统的典型主诉（differential_direction 九选项逐一覆盖）：cardiovascular（胸痛、心悸、活动后气促、下肢水肿、血压异常）、respiratory（咳嗽咳痰、气促、喘息、胸膜相关症状）、gastrointestinal（腹痛、反酸、呕吐、腹泻、便血）、neurologic（头痛、眩晕、肢体麻木无力、意识改变、言语不清）、urinary（尿频尿急尿痛、血尿、肾绞痛、排尿困难）、endocrine（多饮多尿、体重明显改变、怕冷乏力、血糖异常）、musculoskeletal（关节痛、腰痛、外伤、行走困难）、hematologic_oncologic（贫血貌、淋巴结肿大、盗汗、乏力消瘦）、undirected（三个方向并存无法判定）",
    "危险信号八项（red_flag=true 与 urgency=3 需逐项覆盖，并各自触发对应系统方向）：意识改变或晕厥、持续胸痛、明显呼吸困难、呕血或黑便、大出血、严重低血压、SpO2 下降、剧烈头痛伴喷射性呕吐",
    "紧急度档（urgency 四档全覆盖）：0 可按普通门诊预约（慢病随访、常规体检、轻症稳定且 red_flag=false）、1 建议尽快门诊但无需急诊、2 需要急诊评估或当日处理、3 存在危险信号需立即急救（此时 red_flag 必为 true）",
    "needs_test=false 的特例（需专门生成此类以覆盖该标签）：主诉已高度特异且体征与检验均无异常，此时 urgency 不得为 2 或 3",
    "undirected 的特例（需专门生成此类以覆盖该标签）：主诉同时涉及三个系统、检验与影像均无指向性证据，此时 needs_test 必为 true",
    "主诉与检验方向关系：方向一致、主诉含糊但检验有明确指向、检验完全缺失、主诉与检验方向冲突（须按最紧急且最专科化的系统仲裁）",
    "主诉长度与语气：一句话、三句话、平实叙述、焦虑、急迫、表述含糊（患者说不清部位或时间）",
    "年龄跨度：婴幼儿、儿童、青年、中年、老年、极高龄",
    "生命体征组合：全部正常、仅一项异常、多项同时异常、完全未测量",
    "合并症与用药：无、单一慢性病（高血压/糖尿病）、多病共存、既往手术史、正在服用抗凝药或降糖药",
    "是否已做影像：未做、已做且正常、已做且有异常但与主诉方向不一致、影像为决定性证据（此时 needs_test 可为 false）",
    "患病时长：数小时、数天、2-4 周、3 个月以上、慢性反复发作"
  ]
}
', 'medical', 1, 'both', 'script', 'kev/console/distill/configs/diagnosis.yaml', 'domains', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00') ON CONFLICT(slug) DO NOTHING;

INSERT INTO scenarios (id, domain_id, slug, label_zh, label_en, spec_path, spec_json, category, sort, track, generator_kind, distill_yaml, origin, created_at, updated_at) VALUES ('icd-coding', 'medical', 'icd-coding', 'ICD 编码', 'ICD Coding', 'docs/domains/medical/specs/icd-coding.json', '{
  "name": "icd-coding",
  "domain": "住院病案编码与 DRG/DIP 审核。对象为已出院病案的编码员复核场景，涉及主要诊断、其他诊断、手术操作编码，以及诊断与病历记录是否一致、编码是否在合理候选集内、是否需要编码员逐条核对。涉及疾病系统以常见内外科为主：循环、呼吸、消化、泌尿、代谢内分泌、肿瘤、骨关节、妇产。",
  "state": "一份病案的**结构化摘要**（不是病历全文）：患者年龄性别、住院天数、主要诊断与次要诊断列表（已由 HIS 导出）、手术操作名称与部位、检验与影像的关键阳性发现、既往史与合并症。用药与治疗经过只保留与诊断相关的要点（一到两句），不含病程记录全文。",
  "state_example": {
    "patient": "male 64",
    "length_of_stay_days": 9,
    "primary_dx": "急性ST段抬高型心肌梗死（前壁）",
    "secondary_dx": ["高血压3级 很高危", "2型糖尿病", "高脂血症"],
    "procedure": ["冠状动脉造影", "经皮冠状动脉药物洗脱支架置入（前降支）"],
    "key_findings": ["心电图 II III aVF V1-V6 ST段抬高0.3-0.5mV", "肌钙蛋白I 18.4 ng/mL 升高", "心脏超声 LVEF 42%"],
    "past_history": ["高血压 12 年", "2 型糖尿病 8 年", "吸烟 30 年"],
    "clinical_course": "急诊行 CAG 后植入 DES，术后规律用药，病情稳定出院"
  },
  "questions": {
    "coding_reasonable": {
      "type": "choice",
      "instructions": "病案首页填报的诊断与手术操作，在本候选集内是否合理？",
      "criteria": {
        "reasonable": "诊断与病历记录相符，诊断顺序与并发症关系正确，手术操作与记录一致",
        "questionable": "存在疑点：并发症/合并病顺序、主诊断选择、手术操作部位或层次不清，需要编码员核对",
        "wrong": "明显错误：诊断与病历记录矛盾、凭空增加诊断、主诊断与手术严重不符"
      }
    },
    "needs_coder": {
      "type": "noul",
      "instructions": "该病案是否必须由编码员逐条复核后才能入档？",
      "criteria": {
        "true": "含肿瘤诊断、罕见病、复杂手术、多系统并发症、诊断与记录不一致、疑难主诊断选择",
        "false": "诊断与手术常规清晰，可批量校验通过"
      }
    },
    "evidence_gap": {
      "type": "choice",
      "instructions": "该病案最主要的问题是什么？",
      "criteria": {
        "none": "证据链完整，诊断与记录相互印证",
        "order": "诊断顺序问题：主诊断未选为本次入院的主要病因或并发症关系颠倒",
        "missing_dx": "诊断缺失：病历中明确提及但首页未填的并发症或合并症",
        "over_dx": "过度诊断：首页诊断缺乏病历记录支持",
        "procedure_mismatch": "手术操作不符：操作名称、部位或层次与记录不一致",
        "insufficient_record": "记录不足：关键诊断依据在摘要中缺失，无法判定"
      }
    },
    "confidence_tier": {
      "type": "score",
      "instructions": "对该病案编码正确性的置信档位如何？",
      "criteria": [
        "0 = 高置信：证据链完整，判定无争议",
        "1 = 中置信：存在轻微疑点但结论方向明确",
        "2 = 低置信：关键依据缺失或矛盾，需人工裁定"
      ]
    }
  },
  "guidance": "本场景**不要求模型直接输出 ICD 编码**，只判断「病案首页填报的诊断与手术，在给定候选集内是否合理」。coding_reasonable 的判定必须以 key_findings 与 clinical_course 中可见的记录为唯一依据，不得依据常识补全病历中未提及的诊断：key_findings 与诊断列表一一对应且顺序符合「病因在前、并发症在后」时判 reasonable；主诊断是并发症而非本次入院主因、或诊断顺序颠倒（如把高血压放在急性心梗之前）判 questionable；病历记录（key_findings / clinical_course）与首页诊断直接矛盾、或首页含记录中完全未提及的诊断时判 wrong。needs_coder 为独立信号：诊断列表含恶性肿瘤（含转移瘤）、罕见病、系统性自身免疫病，或 procedure 含复杂操作（如多支血管支架、联合脏器手术、移植），或 evidence_gap 不为 none 时，即使 coding_reasonable 为 reasonable 也须 true。evidence_gap 的判定优先级：记录矛盾或凭空诊断 → over_dx 或 procedure_mismatch；主诊断选择错误或顺序颠倒 → order；记录中提到但首页未填 → missing_dx；摘要中依据不足无法判定 → insufficient_record；完全一致 → none。confidence_tier 由 evidence_gap 决定：none 且 reasonable 时必须为 0；insufficient_record 时必须为 2；其余情况按 reasonable→1、questionable→2、wrong→2 映射。特别地，即使 key_findings 支持某诊断，clinical_course 完全未提及时也判 insufficient_record 而不是 reasonable——本场景宁可交人工，不可凭医学常识替编码员做主。",
  "variety": [
    "疾病系统（覆盖 domain 列出的各系统）：循环（急性心梗、心衰、房颤、高血压 3 级）、呼吸（COPD 急性加重、肺炎、支气管肺癌、哮喘）、消化（肝硬化失代偿、急性胆囊炎、重症胰腺炎、上消化道出血）、泌尿（前列腺增生、肾结石、膀胱癌、急性肾损伤）、代谢内分泌（糖尿病酮症酸中毒、甲状腺功能减退、高钾血症）、肿瘤（肺癌根治术、消化道肿瘤化疗、转移瘤）、骨关节（全髋关节置换、脊柱融合、股骨颈骨折内固定）、妇产（剖宫产、子宫肌瘤剔除、卵巢囊肿蒂扭转）、神经（脑梗死、颅内出血、帕金森病）",
    "病案类型：单病种手术、复杂多系统并发症、肿瘤化疗、危重症转归、死亡病例、择期手术、无手术的内科住院",
    "诊断顺序问题（对应 evidence_gap=order）：主诊断正确、并发症误当主诊断、顺序颠倒（如高血压排在急性心梗之前）、主诊断为术后并发症而非入院病因、缺主诊断",
    "诊断缺失（对应 missing_dx）：病历提到但首页未填的并发症（术后肺炎、深静脉血栓、急性肾损伤、低蛋白血症）、未填的合并症（房颤、既往骨折、陈旧性脑梗）、未填的恶性肿瘤转移灶",
    "过度诊断（对应 over_dx）：凭空增加的诊断、与 key_findings 无关的诊断、与用药记录完全不相关的诊断",
    "操作不符（对应 procedure_mismatch）：操作部位不符（左侧 vs 右侧、主动脉 vs 上肢）、操作层次不清（部分切除 vs 全切除、根治 vs 姑息）、操作名称笼统（仅写「手术」）、操作与记录时间线不符",
    "记录质量：记录完整、关键依据缺失（clinical_course 完全未提及该诊断）、记录与首页直接矛盾、事后补记痕迹",
    "证据强度：key_findings 明确且与诊断一一对应、仅有笼统描述、只有诊断无任何检查依据、影像结论与检验数值矛盾",
    "needs_coder=true 的触发场景（须专门生成）：诊断含恶性肿瘤（含转移瘤）、罕见病、系统性自身免疫病、复杂手术（多支血管支架、联合脏器手术、器官移植）、evidence_gap 不为 none",
    "置信档（对应 confidence_tier 三档）：0 高置信（证据链完整且 reasonable）、1 中置信（轻微疑点但方向明确）、2 低置信（关键依据缺失或矛盾，需人工裁定；insufficient_record 时必须为 2）",
    "住院时长与转归：1-3 天、4-9 天、10 天以上、死亡、自动出院、转院",
    "主诊断表述规范度：规范术语（含部位与性质）、笼统表述（症状主导）、待排诊断（带「?」或「待排」）、英文缩写混排"
  ]
}
', 'medical', 3, 'llm', '', '', 'domains', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00') ON CONFLICT(slug) DO NOTHING;

INSERT INTO scenarios (id, domain_id, slug, label_zh, label_en, spec_path, spec_json, category, sort, track, generator_kind, distill_yaml, origin, created_at, updated_at) VALUES ('medication-review', 'medical', 'medication-review', '用药审查', 'Medication Review', 'docs/domains/medical/specs/medication-review.json', '{
  "name": "medication-review",
  "domain": "门诊与住院处方审核。药品覆盖抗感染药、降压药、降糖药、抗凝药、NSAIDs、质子泵抑制剂、镇痛药等常见类别；患者为成人、孕产妇、哺乳期妇女、儿童、老年、肝肾功能不全者。审核依据为药品说明书禁忌与剂量上限、重复用药、特殊人群禁忌、给药途径与适应症。",
  "state": "一份待审核处方的结构化摘要：患者年龄性别与生理状态（妊娠周数、哺乳、肾功能 eGFR 数值、肝功能）、过敏史、既往用药、当前处方药品与剂量频次、疗程天数（已由生成器算好，不要求模型做日期运算）、适应症诊断。字段值为中文叙述夹英文药名缩写。",
  "state_example": {
    "patient": "female 34, gestation 28 weeks",
    "state_flags": "pregnant, eGFR 88 mL/min/1.73m2",
    "allergies": "青霉素（皮疹）",
    "current_meds": ["头孢曲松 1g qd"],
    "current_rx": "甲硝唑 0.4g tid x 7天",
    "days_on_drug": 3,
    "indication": "细菌性阴道炎"
  },
  "questions": {
    "verdict": {
      "type": "choice",
      "instructions": "该处方的审核结论是什么？",
      "criteria": {
        "pass": "无问题，可直接执行",
        "conditional": "有可纠正的偏差（如剂量偏小、疗程偏短、缺少辅助用药），放行但需提示",
        "reject": "存在必须拦截的严重问题（禁忌、重复用药、超剂量、明确适应症不符）"
      }
    },
    "needs_pharmacist": {
      "type": "noul",
      "instructions": "该处方是否必须由药师复核后才能执行？",
      "criteria": {
        "true": "含高风险信号（妊娠/哺乳/儿童/老年、肝肾功能异常、多药联用、注射剂、管制类）",
        "false": "低风险，可按常规执行"
      }
    },
    "issue_type": {
      "type": "choice",
      "instructions": "该处方最突出的问题是哪一类？",
      "criteria": {
        "none": "未发现问题",
        "contraindication": "禁忌：患者对该药存在绝对禁忌（如孕妇用四环素、青霉素过敏用头孢）",
        "dose_over": "剂量超限：单次或日剂量超过说明书上限",
        "duplicate": "重复用药：与既往用药或同处方内其他药物成分重复或同类叠加",
        "special_population": "特殊人群：妊娠、哺乳、儿童、老年、肝肾功能不全中的人群限制被忽略",
        "indication_mismatch": "适应症不符：药品与所列诊断不匹配"
      }
    },
    "severity": {
      "type": "score",
      "instructions": "该处方问题的严重程度如何？",
      "criteria": [
        "0 = 无需处理",
        "1 = 提示即可（轻微偏差，不影响疗效与安全）",
        "2 = 需干预（影响疗效或有潜在风险，须修改后执行）",
        "3 = 必须拦截（禁忌或超剂量，存在严重不良事件风险）"
      ]
    }
  },
  "guidance": "verdict 由最严重的问题决定：出现 contraindication 或 dose_over 或 duplicate 判 reject；仅 special_population 或 indication_mismatch 且可纠正判 conditional；无问题判 pass。issue_type 取命中的最突出的一类，多类同时命中时按 contraindication > dose_over > duplicate > special_population > indication_mismatch 的优先级取。severity 与 verdict 严格对应：pass=0、conditional=2、reject=3，issue_type=none 时 severity 必须为 0。severity 1 仅用于「无规则命中但剂量偏离常规」的情形，此时 verdict 为 pass、issue_type 为 none。needs_pharmacist 为独立风险信号，与 verdict 无关：只要涉及妊娠、哺乳、儿童、老年、肝肾功能异常（eGFR<30 或转氨酶升高）、注射剂、管制类、或同时使用 3 种以上药物，即使 verdict 为 pass 也须 true。妊娠期禁忌示例：四环素类、喹诺酮类（权衡后）、华法林、ACEI/ARB（妊娠中晚期）、异维A酸；哺乳期：大剂量化疗、四环素；儿童：四环素（<8 岁）、喹诺酮（<18 岁）、阿司匹林（水痘/病毒感染期）；肝肾功能不全需减量或禁用头孢曲松、氨基糖苷类、万古霉素。dose_over 示例：甲硝唑单次 >0.6g、对乙酰氨基酚单次 >1g 或日剂量 >4g、头孢曲松单次 >2g（普通感染）。days_on_drug 与疗程天数字段已由生成器算好，模型只判断「疗程是否明显不合理」，绝不做日期加减运算。过敏史为「青霉素（皮疹）」时，任何青霉素类或头孢类均为 contraindication。",
  "variety": [
    "药品类别（务必覆盖）：抗感染药（头孢曲松、阿莫西林、甲硝唑、左氧氟沙星、喹诺酮类）、降压药（ACEI/ARB、钙通道阻滞剂、利尿剂、β受体阻滞剂）、降糖药（二甲双胍、磺脲类、胰岛素）、抗凝与抗血小板（华法林、低分子肝素、阿司匹林、氯吡格雷）、NSAIDs（布洛芬、双氯芬酸）、镇痛药（对乙酰氨基酚、曲马多、吗啡）、质子泵抑制剂（奥美拉唑、雷贝拉唑）、抗真菌与抗病毒药",
    "问题类型（对应 issue_type 六选项全覆盖）：none 无问题、contraindication 绝对禁忌、dose_over 剂量超限、duplicate 重复用药、special_population 特殊人群禁忌、indication_mismatch 适应症不符",
    "审核结论档（对应 verdict）：pass 无问题可执行、conditional 可纠正偏差（剂量偏小、疗程偏短、缺辅助用药、缺监测、给药频次不当）、reject 必须拦截（禁忌、重复用药、超剂量、明确适应症不符）",
    "严重度档（与 verdict 严格对应）：pass=0、conditional=2、reject=3；severity=1 仅用于「无规则命中但剂量偏离常规」，此时 verdict=pass 且 issue_type=none",
    "剂量超限的具体对照（写进 state 的实测值）：甲硝唑单次 >0.6g、对乙酰氨基酚单次 >1g 或日剂量 >4g、头孢曲松单次 >2g（普通感染）、华法林超出抗凝范围、胰岛素剂量未按体重折算",
    "禁忌的具体对照：孕妇用四环素类、青霉素过敏（皮疹）用头孢类、肝功能不全用头孢曲松、eGFR<30 用氨基糖苷类或万古霉素、哺乳期大剂量化疗",
    "重复用药的具体形态：同处方内两种成分相同的药、头孢与喹诺酮抗菌谱重叠、同机制叠加（双联 PPI、两种促泌剂）、抗凝药与 NSAIDs 并用增加出血风险",
    "特殊人群（needs_pharmacist=true 的主要触发）：孕早/中/晚期、哺乳期、新生儿与儿童（<8 岁四环素、<18 岁喹诺酮）、老年 ≥65 岁且多病共存、肝肾功能不全（eGFR<30 或转氨酶升高）、透析、注射剂、管制类、同时使用 3 种以上药物",
    "过敏史形态：有明确药物过敏（青霉素皮疹）、多种药物过敏、过敏史为空、曾有皮疹但非速发过敏（此时不得判 contraindication）",
    "用药数量：单一用药、2-3 种联用、4-5 种、5 种以上多药联用",
    "疗程与已用天数：疗程合理、偏短需延长、明显不合理（过长或过短）；days_on_drug 与疗程天数须由生成器算好，模型只判断是否明显不合理、不做日期运算",
    "给药途径与药名表述：口服片、静脉滴注、静脉推注、肌肉注射、外用、吸入；中文商品名、通用名、英文缩写（ceftriaxone / metronidazole）、中英混排；剂量写法 mg/g/ml/片/支 混用",
    "适应症不符的具体对照：抗生素用于无细菌指征的功能性消化不良、镇痛药用于与诊断无关的疼痛、降压药用于非高血压适应症",
    "边界陷阱（务必按 guidance 处理）：eGFR<30 或转氨酶升高时即使 verdict=pass 也须 needs_pharmacist=true；过敏史为「青霉素（皮疹）」时任何青霉素类或头孢类均为 contraindication；禁忌与重复用药的优先级高于剂量偏差"
  ]
}
', 'medical', 8, 'both', 'script', 'kev/console/distill/configs/medication.yaml', 'domains', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00') ON CONFLICT(slug) DO NOTHING;

INSERT INTO scenarios (id, domain_id, slug, label_zh, label_en, spec_path, spec_json, category, sort, track, generator_kind, distill_yaml, origin, created_at, updated_at) VALUES ('nursing-quality', 'medical', 'nursing-quality', '护理质量', 'Nursing Quality', 'docs/domains/medical/specs/nursing-quality.json', '{
  "name": "nursing-quality",
  "domain": "医院护理质量管控。质控维度覆盖护理评估、给药执行、护理记录、管路与设备、皮肤与压疮、跌倒与导管预防、医患沟通。对象为住院患者与门诊输液患者。质控依据为护理核心制度、检查表条目与医院质控标准。",
  "state": "一次护理质量检查的结构化摘要：患者年龄性别与护理级别、所在病区、检查时间点、涉及的具体护理环节（如静脉输液、皮下注射、留置导尿管、压疮风险评估、跌倒风险评估、护理记录书写）、检查中发现的实际情况（做了什么、记录了什么、是否规范）、患者依赖程度（是否卧床、是否留置多路管路）。",
  "state_example": {
    "patient": "male 71, bedridden",
    "ward": "神经内科 3 病区",
    "nursing_level": "一级护理",
    "check_point": "静脉输液过程",
    "observed": "输液前未核对腕带姓名，巡视记录本上 14:00 一栏空白",
    "dependencies": "留置尿管 1 条，桡动脉测压管 1 条",
    "risk_scores": "Braden 12 分（中等风险），Morse 评分 45 分（高风险）"
  },
  "questions": {
    "issue_type": {
      "type": "choice",
      "instructions": "本次检查发现的问题属于哪一类？",
      "criteria": {
        "none": "未发现问题",
        "assessment": "护理评估：入院评估、风险评估（压疮/跌倒/导管）未做或做得不完整",
        "execution": "给药与操作执行：核对、给药、输血、导管维护等操作未按规范执行",
        "record": "护理记录：记录缺失、漏项、事后补记、字迹或时间逻辑不自洽",
        "communication": "沟通与健康教育：告知不到位、知情同意缺失、宣教未落实",
        "device": "设备与管路：管路固定、标识、刻度、引流装置管理不规范"
      }
    },
    "reportable": {
      "type": "noul",
      "instructions": "该问题是否需要上报护理部（形成质量缺陷事件）？",
      "criteria": {
        "true": "构成护理不良事件或需质量改进追踪（给药错误、管路脱落、压疮发生、跌倒、非计划拔管、记录严重失真）",
        "false": "一般缺陷，可在科室质控会内整改"
      }
    },
    "severity": {
      "type": "score",
      "instructions": "该问题的严重程度如何？",
      "criteria": [
        "0 = 符合规范，无需处理",
        "1 = 轻度缺陷：流程执行不到位但未造成实际后果",
        "2 = 中度缺陷：已造成患者可观察的不适或潜在风险，需科室整改",
        "3 = 重度缺陷：构成护理不良事件，需立即上报并组织讨论"
      ]
    },
    "preventable": {
      "type": "choice",
      "instructions": "该问题的可预防性如何？",
      "criteria": {
        "preventable": "可通过规范执行与培训预防（多数护理缺陷属于此类）",
        "partially": "部分可预防，还需设备、药品或人力条件配合",
        "not_preventable": "不可预防（患者病情突变、不可避免的并发症等）"
      }
    }
  },
  "guidance": "issue_type 按检查点与 observed 的直接对应关系判定，不要外推：核对/给药/输血/操作步骤相关的问题归 execution；评估表未做或要素缺失归 assessment；记录本缺项、漏签名、时间逻辑矛盾归 record；宣教告知/解释不到位归 communication；管路固定松脱、无标识、刻度不准、引流装置更换超时归 device。reportable 为 true 的触发条件是问题造成了实际不良事件或需要跨科室质量追踪：给药错误（含给错药、漏给、剂量错误）、管路脱落与非计划拔管、压疮发生、跌倒致伤、非计划拔管、护理记录严重失真（事后补记伪造）、给药后不良反应未及时处置。severity 严格对应：issue_type=none 时 severity 必须为 0；一般执行或记录缺陷未造成后果为 1（对应 reportable=false）；已造成患者可观察不适或存在潜在风险为 2；构成不良事件为 3（reportable=true）。因此 issue_type=none 与 severity=0、reportable=false 必须同时成立。preventable 取值规则：只要缺陷源于执行动作或记录行为未按规范做，即为 preventable；仅当还牵涉设备缺陷、药品短缺、人手不足等系统因素时才是 partially；仅当问题源于患者病情本身突变（如突发动脉瘤破裂、术后并发症）时才是 not_preventable。patient 为 bedridden、dependencies 含多路管路、risk_scores 提示中高风险时，同等缺陷的 severity 应上浮一级，但前提是 observed 中确有该环节的执行或记录问题。",
  "variety": [
    "检查环节（覆盖 domain 的七个质控维度）：入院评估、压疮风险评估、跌倒风险评估、静脉输液、皮下注射、肌肉注射、口服药给药、输血核对、留置导尿管维护、留置胃管、静脉留置针管路维护、压疮护理、护理记录书写、交接班、医患沟通、健康教育宣教",
    "缺陷类型（issue_type 六选项逐一覆盖）：none 未发现问题、assessment 评估未做或要素缺失、execution 核对/给药/输血/无菌操作未按规范、record 漏项/漏签名/时间逻辑矛盾/事后补记、communication 告知不到位/知情同意缺失/宣教未落实、device 管路固定松脱/无标识/刻度不准/引流更换超时",
    "严重度档（severity 四档全覆盖，且须与 issue_type 联动）：0 符合规范（issue_type=none 时必须为 0）、1 轻度流程缺陷未造成后果、2 中度已造成可观察不适或潜在风险、3 重度构成护理不良事件",
    "不良事件类型（reportable=true 的触发，须逐项覆盖）：给药错误（给错药/漏给/剂量错误）、管路脱落、非计划拔管、压疮发生、跌倒致伤、护理记录严重失真（事后补记伪造）、给药后不良反应未及时处置",
    "可预防性（preventable 三选项全覆盖）：preventable 源于执行或记录未按规范、partially 牵涉设备缺陷/药品短缺/人手不足、not_preventable 源于患者病情突变（突发动脉瘤破裂、术后并发症）",
    "患者依赖度：自理、部分自理、卧床 bedridden、多路管路、意识障碍、术后早期活动受限",
    "护理级别：特级、一级、二级、三级",
    "病区：内科、外科、ICU、肿瘤科、老年科、产科、儿科、康复科",
    "风险评分：Braden 低/中/高风险、Morse 跌倒评分低/中/高风险并给出具体分值、评分缺失未评估",
    "时间点：交接班高峰、午间、夜间、查房时、抢救后、术前准备期",
    "检查主体与场景：护士长巡查、责任护士自查、质控科抽查、实习生带教、跨科室会诊",
    "严重度上浮规则（须按 guidance 处理）：patient 为 bedridden、dependencies 含多路管路或 risk_scores 提示中高风险时，同等缺陷的 severity 上浮一级，但前提是 observed 中确有该环节的执行或记录问题"
  ]
}
', 'medical', 10, 'rule', 'script', '', 'domains', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00') ON CONFLICT(slug) DO NOTHING;

INSERT INTO scenarios (id, domain_id, slug, label_zh, label_en, spec_path, spec_json, category, sort, track, generator_kind, distill_yaml, origin, created_at, updated_at) VALUES ('record-summary', 'medical', 'record-summary', '病历摘要', 'Record Summary', 'docs/domains/medical/specs/record-summary.json', '{
  "name": "record-summary",
  "domain": "住院病历的现病史与病程记录摘要核对。摘要由结构化要素组成：主诉、现病史要点、体格检查、诊断、用药、诊疗计划。上游医师已写下部分要素，摘要助手需要判断要素是否完整、是否需要编码员复核、以及缺陷的严重程度。不直接生成 ICD 编码，只判断完整性与是否需人工。",
  "state": "一份住院病历的结构化摘录，字段短且跨记录固定：人口学、主诉、现病史要点、查体记录、诊断列表、用药记录、诊疗计划、缺失标记。要点已由上游抽取或规则截断，不含病历全文。",
  "state_example": {
    "patient": "female 64",
    "chief_complaint": "反复右上腹疼痛 3 个月",
    "presenting_history": "3 个月前无明显诱因出现右上腹隐痛，餐后加重，伴嗳气，无反酸",
    "examination": "右上腹轻压痛，无反跳痛，肝区叩击痛阴性",
    "diagnosis": ["慢性胃炎", "幽门螺杆菌感染待排"],
    "medications": ["雷贝拉唑 20 mg qd", "阿莫西林 1000 mg tid"],
    "plan": "胃镜检查 + 幽门螺杆菌呼气试验，评估根除治疗指征",
    "missing_element": "无"
  },
  "questions": {
    "missing_element": {
      "type": "choice",
      "instructions": "摘要中缺失的是哪个要素？",
      "criteria": {
        "none": "六个要素齐全，无缺失",
        "chief_complaint": "缺主诉",
        "presenting_history": "缺现病史要点",
        "examination": "缺体格检查记录",
        "diagnosis": "缺诊断",
        "medication": "缺用药记录",
        "plan": "缺诊疗计划"
      }
    },
    "needs_coder_review": {
      "type": "noul",
      "instructions": "这份摘要是否需要编码员复核后才能用于编码？",
      "criteria": {
        "true": "需要复核：要素缺失影响诊断编码，或诊断列表与记录内容不一致",
        "false": "无需复核：要素齐全且诊断与记录一致"
      }
    },
    "severity": {
      "type": "score",
      "instructions": "摘要缺陷的严重程度如何？",
      "criteria": [
        "0：要素齐全，无缺陷",
        "1：轻度缺陷：缺主诉或现病史要点，不影响诊断判断",
        "2：中度缺陷：缺查体、诊断或用药记录，诊断可信度下降",
        "3：重度缺陷：缺诊疗计划，无法判断后续处理"
      ]
    },
    "coding_confidence": {
      "type": "score",
      "instructions": "依据这份摘要做诊断编码的置信档位如何？",
      "criteria": [
        "0：低置信 —— 关键要素缺失，编码需要额外临床信息",
        "1：中置信 —— 诊断可初步判断，但需补充要素确认",
        "2：高置信 —— 要素齐全且诊断与记录一致"
      ]
    }
  },
  "guidance": "missing_element 为 none 当且仅当六个要素全部存在；此时 severity 必为 0、needs_coder_review 必为 false、coding_confidence 必为 2。severity 由缺失要素的类型决定而非随机：缺主诉或现病史要点为 1，缺查体、诊断或用药记录为 2，缺诊疗计划为 3。needs_coder_review 为 true 当且仅当 severity >= 2。coding_confidence 由 severity 派生：severity 0 对应 2，severity 1 与 2 对应 1，severity 3 对应 0。诊断列表存在但与用药记录明显不符（用药为完全不相关类别）时，即使无要素缺失也需要编码员复核，此时 severity 取 2、coding_confidence 取 1。",
  "variety": [
    "六要素缺失组合（missing_element 七选项逐一覆盖）：全齐 none、缺主诉 chief_complaint、缺现病史要点 presenting_history、缺体格检查 examination、缺诊断 diagnosis、缺用药记录 medication、缺诊疗计划 plan、缺两项（低频但须存在）",
    "严重度档（severity 由缺失要素类型派生，不得随机）：0 六要素全齐、1 缺主诉或现病史要点、2 缺查体/诊断/用药记录、3 缺诊疗计划",
    "置信档（coding_confidence 由 severity 派生）：2 高置信（要素齐全且诊断与记录一致）、1 中置信（severity 为 1 或 2，需补充要素确认）、0 低置信（severity 为 3，缺诊疗计划无法判断后续处理）",
    "needs_coder_review=true 的两类来源（须都生成）：要素缺失影响诊断编码（severity>=2）；六要素齐全但诊断列表与用药记录明显不符（用药为完全不相关类别），此时 severity 取 2、coding_confidence 取 1",
    "科室来源：内科、外科、肿瘤科、妇产科、儿科、ICU、康复科、中医科",
    "病程阶段：入院记录、首次病程记录、阶段小结、出院小结、死亡记录、手术记录",
    "诊断数量与构成：单一诊断、并列多个诊断、待排诊断（带「待排」或「?」）、入院诊断与出院诊断不一致、并发症未列入诊断列表",
    "用药复杂度：无用药记录、单药、联合用药、特殊人群用药（孕产妇/肾功能不全/肝功能异常）、用药与诊断明显不符",
    "主诉风格：口语化（「肚子疼」）、书面化、极简（「发热」）、冗长、时间表述模糊（「这几天」）",
    "现病史要素完整度：起病时间/诱因/性质/加重缓解因素/伴随症状/既往诊疗经过——六要素齐全、仅前三项、完全缺失",
    "查体记录：生命体征齐全、仅部分系统、仅记录阳性体征、缺阴性体征、模板化复制上一份",
    "诊疗计划：明确检查计划、仅笼统记录（「对症处理」）、缺失、计划与诊断不匹配",
    "患者人群：成人、儿童、孕产妇、老年、危重、术后"
  ]
}
', 'medical', 11, 'both', 'script', 'kev/console/distill/configs/record-summary.yaml', 'domains', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00') ON CONFLICT(slug) DO NOTHING;

INSERT INTO scenarios (id, domain_id, slug, label_zh, label_en, spec_path, spec_json, category, sort, track, generator_kind, distill_yaml, origin, created_at, updated_at) VALUES ('triage', 'medical', 'triage', '分诊', 'Triage', 'docs/domains/medical/specs/triage.json', '{
  "name": "triage",
  "domain": "医院门诊与互联网医院的导诊分诊。输入为患者自述或接线员记录的中文主诉，涵盖发热、咳嗽、腹痛、胸闷胸痛、头晕头痛、关节痛、皮疹、创伤、孕产、下泌尿道症状、儿童发热等。场景含线下门诊挂号导诊与线上问诊分诊两类。",
  "state": "一位患者就诊意图的结构化摘要：年龄性别、就诊方式、主诉（患者原话或接线员记录，1-3 句，混合口语化表达与医学术语）、症状持续时间、伴随症状列表、基础疾病与用药、生命体征数值（若已知）、有无急症红旗征象描述。字段值为中文叙述。",
  "state_example": {
    "patient": "male 58",
    "channel": "线下门诊导诊台",
    "chief_complaint": "胸口压着难受，走了两条路就喘不上气，晚上睡不平",
    "duration": "3 天",
    "accompanying": ["活动后气促", "夜间不能平卧", "出汗"],
    "history": ["高血压 10 年", "长期吸烟"],
    "vitals": "BP 165/98 mmHg, HR 96 bpm, SpO2 94%",
    "red_flags": "无晕厥、无剧烈持续胸痛"
  },
  "questions": {
    "department": {
      "type": "choice",
      "instructions": "这位患者应该首先挂哪个科室？",
      "criteria": {
        "general_medicine": "内科（普通内科）",
        "cardiology": "心血管内科",
        "respiratory": "呼吸内科",
        "gastroenterology": "消化内科",
        "neurology": "神经内科",
        "orthopedics": "骨科",
        "dermatology": "皮肤科",
        "urology": "泌尿外科",
        "obstetrics_gynecology": "妇产科",
        "pediatrics": "儿科",
        "emergency": "急诊科",
        "ophthalmology": "眼科",
        "ent": "耳鼻咽喉科",
        "endocrinology": "内分泌科"
      }
    },
    "immediate_human": {
      "type": "noul",
      "instructions": "这位患者是否应当立即由人工分诊员介入（而不是直接指引其自行挂号）？",
      "criteria": {
        "true": "存在急症或高危信号，需人工立即介入",
        "false": "可按指引自行挂号"
      }
    },
    "acuity": {
      "type": "score",
      "instructions": "该患者情况的紧急程度如何？",
      "criteria": [
        "0 = 非紧急（可择期就诊）",
        "1 = 亚急性（数日内就诊）",
        "2 = 急性（当日就诊）"
      ]
    },
    "red_flag": {
      "type": "noul",
      "instructions": "是否存在需要立即急诊处理的红旗征象（胸痛、意识改变、大出血、呼吸困难、剧烈头痛伴呕吐、持续高热惊厥、孕产出血等）？"
    }
  },
  "guidance": "department 是患者应当首先挂的科室，不是所有相关科室。多症状共存时按以下优先级归属：任何红旗征象一律先判 emergency（覆盖其他一切科室规则），其次看主诉对应的系统；主诉同时涉及两个系统时，取更紧急或更专科化的那个——胸闷/心悸/活动后气促/水肿/血压极高判 cardiology 而非 general_medicine；咳嗽咳痰/气喘/发热伴呼吸道症状判 respiratory；腹痛按部位（上腹、右上腹、脐周、下腹）分别对应 gastroenterology、hepatology 类或 general_medicine、妇科；眩晕/肢体麻木无力/言语不清判 neurology；外伤/骨折/关节肿痛判 orthopedics；皮疹/瘙痒/皮损判 dermatology；尿频尿急尿痛、血尿、肾绞痛判 urology；孕产相关（停经、阴道流血、孕期不适、产检）判 obstetrics_gynecology；14 岁以下且以发热、咳嗽、腹泻、呕吐为主诉判 pediatrics（除非有明确红旗征象，则 emergency 优先）。immediate_human 为 true 当且仅当 red_flag 为 true，或存在以下高危信号：胸痛/胸闷伴出汗与气促、意识改变或晕厥、咯血或呕血、黑便、剧烈头痛伴喷射性呕吐、持续高热 >3 天伴精神萎靡、呼吸困难（SpO2<94% 或说话不能成句）、婴幼儿高热惊厥、孕期阴道流血或腹痛。acuity 与 red_flag 联动：red_flag 为 true 时 acuity 必须为 2；immediate_human 为 true 但无红旗时 acuity 为 2；可择期就诊（如复诊、慢病随访、常规体检咨询）为 0；数日内需就诊为 1。acuity=0 的样本必须 immediate_human=false。红旗征象必须由主诉或生命体征明确支持，模型不得凭科室归属反推红旗。",
  "variety": [
    "14 个科室的典型主诉（department 每一选项都须覆盖）：general_medicine（乏力、发热待查、慢病开药）、cardiology（胸闷胸痛、心悸、活动后气促、下肢水肿、血压极高）、respiratory（咳嗽咳痰、气喘、咯血、呼吸困难）、gastroenterology（上腹痛、烧心反酸、呕吐腹泻）、neurology（眩晕、头痛、肢体麻木无力、言语不清、意识改变）、orthopedics（外伤、骨折、关节肿痛、腰腿痛、行走困难）、dermatology（皮疹、瘙痒、皮损、脱发）、urology（尿频尿急尿痛、血尿、肾绞痛、排尿困难）、obstetrics_gynecology（停经、阴道流血、孕期不适、产检、妇科下腹痛）、pediatrics（14 岁以下以发热/咳嗽/腹泻/呕吐为主诉）、emergency（任何红旗征象、严重外伤、中毒、溺水、窒息）、ophthalmology（视物模糊、眼痛、飞蚊、视野缺损）、ent（鼻塞流涕、咽痛、耳鸣、鼻出血、吞咽困难）、endocrinology（多饮多尿、体重改变、怕冷乏力、血糖异常、甲状腺肿）",
    "红旗征象（red_flag 与 immediate_human 的触发源，须逐项覆盖）：胸痛、意识改变或晕厥、大出血（呕血/黑便/阴道流血）、呼吸困难（SpO2<94% 或说话不能成句）、剧烈头痛伴喷射性呕吐、持续高热 >3 天伴精神萎靡、婴幼儿高热惊厥、孕产出血或腹痛、咯血",
    "紧急度档（acuity 三档全覆盖）：0 非紧急可择期（复诊、慢病随访、常规体检咨询，且 immediate_human=false）、1 亚急性需数日内就诊、2 急性需当日就诊（red_flag=true 时必须为 2）",
    "特殊人群：婴幼儿、儿童、青少年、成人、老年、孕产妇、哺乳期女性",
    "就诊渠道：线下门诊导诊台、互联网医院图文问诊、电话分诊、自助机、基层转诊",
    "主诉风格与长度：一句话、三句话、大量口语与方言、完全口语化、夹医学术语、患者自述与护士记录混合",
    "一主诉跨多科室（须按优先级仲裁而非罗列全部）：胸闷伴气促与出汗（cardiology 优先于 general_medicine）、腹痛按部位区分（上腹/右上腹/脐周/下腹）、眩晕伴恶心（neurology）、发热伴咳嗽（14 岁以下判 pediatrics）",
    "生命体征：已测且正常、已测且异常、未知（多数线上场景缺失）、SpO2 下降、血压极高、心率过速",
    "既往史：无特殊病史、慢病多病共存、术后、肿瘤治疗中、长期服药、孕产史",
    "边界情形：罕见科室主诉、单症状可挂多科而无明确指向（判 general_medicine）、症状已缓解但要求复查、明确要求指定某科室"
  ]
}
', 'medical', 14, 'both', 'script', 'kev/console/distill/configs/inquiry.yaml', 'domains', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00') ON CONFLICT(slug) DO NOTHING;

-- 其余医疗场景（精简 seed，spec_json 由 seed_scenarios/import_domain_specs 运行时落库）：
INSERT INTO scenarios (id, domain_id, slug, label_zh, label_en, spec_path, category, sort, track, generator_kind, distill_yaml, origin, created_at, updated_at) VALUES ('follow-up-tier', 'medical', 'follow-up-tier', '出院随访分级', 'Follow-up Tiering', 'docs/domains/medical/specs/follow-up-tier.json', 'medical', 2, 'rule', 'engine', '', 'domains', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00') ON CONFLICT(slug) DO NOTHING;
INSERT INTO scenarios (id, domain_id, slug, label_zh, label_en, spec_path, category, sort, track, generator_kind, distill_yaml, origin, created_at, updated_at) VALUES ('infection-report', 'medical', 'infection-report', '感染上报分诊', 'Infection Report Triage', 'docs/domains/medical/specs/infection-report.json', 'medical', 4, 'rule', 'engine', '', 'domains', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00') ON CONFLICT(slug) DO NOTHING;
INSERT INTO scenarios (id, domain_id, slug, label_zh, label_en, spec_path, category, sort, track, generator_kind, distill_yaml, origin, created_at, updated_at) VALUES ('inquiry', 'medical', 'inquiry', '导诊', 'Inquiry', 'docs/domains/medical/specs/inquiry.json', 'medical', 5, 'distill', '', 'kev/console/distill/configs/inquiry.yaml', 'domains', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00') ON CONFLICT(slug) DO NOTHING;
INSERT INTO scenarios (id, domain_id, slug, label_zh, label_en, spec_path, category, sort, track, generator_kind, distill_yaml, origin, created_at, updated_at) VALUES ('knowledge-qa', 'medical', 'knowledge-qa', '医学知识问答', 'Medical Knowledge Q&A', 'docs/domains/medical/specs/knowledge-qa.json', 'medical', 6, 'distill', '', 'kev/console/distill/configs/knowledge-qa.yaml', 'domains', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00') ON CONFLICT(slug) DO NOTHING;
INSERT INTO scenarios (id, domain_id, slug, label_zh, label_en, spec_path, category, sort, track, generator_kind, distill_yaml, origin, created_at, updated_at) VALUES ('mdr-report', 'medical', 'mdr-report', '器械不良事件', 'Device Adverse Event Triage', 'docs/domains/medical/specs/mdr-report.json', 'medical', 7, 'distill', '', 'kev/console/distill/configs/mdr-report.yaml', 'domains', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00') ON CONFLICT(slug) DO NOTHING;
INSERT INTO scenarios (id, domain_id, slug, label_zh, label_en, spec_path, category, sort, track, generator_kind, distill_yaml, origin, created_at, updated_at) VALUES ('medication', 'medical', 'medication', '用药指导', 'Medication', 'docs/domains/medical/specs/medication.json', 'medical', 9, 'distill', '', 'kev/console/distill/configs/medication.yaml', 'domains', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00') ON CONFLICT(slug) DO NOTHING;
INSERT INTO scenarios (id, domain_id, slug, label_zh, label_en, spec_path, category, sort, track, generator_kind, distill_yaml, origin, created_at, updated_at) VALUES ('surgical-checklist', 'medical', 'surgical-checklist', '手术核查', 'Surgical Safety Checklist Review', 'docs/domains/medical/specs/surgical-checklist.json', 'medical', 12, 'distill', '', 'kev/console/distill/configs/surgical-checklist.yaml', 'domains', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00') ON CONFLICT(slug) DO NOTHING;
INSERT INTO scenarios (id, domain_id, slug, label_zh, label_en, spec_path, category, sort, track, generator_kind, distill_yaml, origin, created_at, updated_at) VALUES ('transfusion-review', 'medical', 'transfusion-review', '输血审核', 'Transfusion Review', 'docs/domains/medical/specs/transfusion-review.json', 'medical', 13, 'rule', 'engine', '', 'domains', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00') ON CONFLICT(slug) DO NOTHING;

-- 金融（finance）：
INSERT INTO scenarios (id, domain_id, slug, label_zh, label_en, spec_path, category, sort, track, generator_kind, distill_yaml, origin, created_at, updated_at) VALUES ('fin-aml-alert', 'finance', 'fin-aml-alert', '反洗钱预警复核', 'AML Alert Review', 'docs/domains/finance/specs/fin-aml-alert.json', 'finance', 0, 'rule', 'engine', '', 'domains', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00') ON CONFLICT(slug) DO NOTHING;
INSERT INTO scenarios (id, domain_id, slug, label_zh, label_en, spec_path, category, sort, track, generator_kind, distill_yaml, origin, created_at, updated_at) VALUES ('fin-collection-tier', 'finance', 'fin-collection-tier', '催收分级', 'Collection Tiering', 'docs/domains/finance/specs/fin-collection-tier.json', 'finance', 1, 'rule', 'engine', '', 'domains', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00') ON CONFLICT(slug) DO NOTHING;
INSERT INTO scenarios (id, domain_id, slug, label_zh, label_en, spec_path, category, sort, track, generator_kind, distill_yaml, origin, created_at, updated_at) VALUES ('fin-complaint-triage', 'finance', 'fin-complaint-triage', '投诉分诊', 'Complaint Triage', 'docs/domains/finance/specs/fin-complaint-triage.json', 'finance', 2, 'distill', '', 'kev/console/distill/configs/fin-complaint-triage.yaml', 'domains', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00') ON CONFLICT(slug) DO NOTHING;
INSERT INTO scenarios (id, domain_id, slug, label_zh, label_en, spec_path, category, sort, track, generator_kind, distill_yaml, origin, created_at, updated_at) VALUES ('fin-compliance-review', 'finance', 'fin-compliance-review', '营销文本合规审查', 'Marketing Compliance Review', 'docs/domains/finance/specs/fin-compliance-review.json', 'finance', 3, 'distill', '', 'kev/console/distill/configs/fin-compliance-review.yaml', 'domains', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00') ON CONFLICT(slug) DO NOTHING;
INSERT INTO scenarios (id, domain_id, slug, label_zh, label_en, spec_path, category, sort, track, generator_kind, distill_yaml, origin, created_at, updated_at) VALUES ('fin-credit-doc-review', 'finance', 'fin-credit-doc-review', '信贷资料完整性', 'Credit Document Review', 'docs/domains/finance/specs/fin-credit-doc-review.json', 'finance', 4, 'rule', 'engine', '', 'domains', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00') ON CONFLICT(slug) DO NOTHING;
INSERT INTO scenarios (id, domain_id, slug, label_zh, label_en, spec_path, category, sort, track, generator_kind, distill_yaml, origin, created_at, updated_at) VALUES ('fin-credit-score-explain', 'finance', 'fin-credit-score-explain', '征信异议分诊', 'Credit Dispute Triage', 'docs/domains/finance/specs/fin-credit-score-explain.json', 'finance', 5, 'distill', '', 'kev/console/distill/configs/fin-credit-score-explain.yaml', 'domains', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00') ON CONFLICT(slug) DO NOTHING;
INSERT INTO scenarios (id, domain_id, slug, label_zh, label_en, spec_path, category, sort, track, generator_kind, distill_yaml, origin, created_at, updated_at) VALUES ('fin-customer-intent', 'finance', 'fin-customer-intent', '客户意图', 'Customer Intent', 'docs/domains/finance/specs/fin-customer-intent.json', 'finance', 6, 'distill', '', 'kev/console/distill/configs/fin-customer-intent.yaml', 'domains', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00') ON CONFLICT(slug) DO NOTHING;
INSERT INTO scenarios (id, domain_id, slug, label_zh, label_en, spec_path, category, sort, track, generator_kind, distill_yaml, origin, created_at, updated_at) VALUES ('fin-dispute-classification', 'finance', 'fin-dispute-classification', '交易争议分类', 'Transaction Dispute Classification', 'docs/domains/finance/specs/fin-dispute-classification.json', 'finance', 7, 'distill', '', 'kev/console/distill/configs/fin-dispute-classification.yaml', 'domains', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00') ON CONFLICT(slug) DO NOTHING;
INSERT INTO scenarios (id, domain_id, slug, label_zh, label_en, spec_path, category, sort, track, generator_kind, distill_yaml, origin, created_at, updated_at) VALUES ('fin-fraud-claim-review', 'finance', 'fin-fraud-claim-review', '欺诈理赔复核', 'Fraud Claim Review', 'docs/domains/finance/specs/fin-fraud-claim-review.json', 'finance', 8, 'rule', 'engine', '', 'domains', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00') ON CONFLICT(slug) DO NOTHING;
INSERT INTO scenarios (id, domain_id, slug, label_zh, label_en, spec_path, category, sort, track, generator_kind, distill_yaml, origin, created_at, updated_at) VALUES ('fin-kyc-review', 'finance', 'fin-kyc-review', '客户尽调资料复核', 'KYC Due Diligence Review', 'docs/domains/finance/specs/fin-kyc-review.json', 'finance', 9, 'rule', 'engine', '', 'domains', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00') ON CONFLICT(slug) DO NOTHING;
INSERT INTO scenarios (id, domain_id, slug, label_zh, label_en, spec_path, category, sort, track, generator_kind, distill_yaml, origin, created_at, updated_at) VALUES ('fin-transaction-anomaly', 'finance', 'fin-transaction-anomaly', '异常交易识别', 'Transaction Anomaly', 'docs/domains/finance/specs/fin-transaction-anomaly.json', 'finance', 10, 'rule', 'engine', '', 'domains', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00') ON CONFLICT(slug) DO NOTHING;
INSERT INTO scenarios (id, domain_id, slug, label_zh, label_en, spec_path, category, sort, track, generator_kind, distill_yaml, origin, created_at, updated_at) VALUES ('fin-underwrite-triage', 'finance', 'fin-underwrite-triage', '核保分诊', 'Underwriting Triage', 'docs/domains/finance/specs/fin-underwrite-triage.json', 'finance', 11, 'rule', 'engine', '', 'domains', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00') ON CONFLICT(slug) DO NOTHING;

-- 教育（education）：
INSERT INTO scenarios (id, domain_id, slug, label_zh, label_en, spec_path, category, sort, track, generator_kind, distill_yaml, origin, created_at, updated_at) VALUES ('edu-admission-screen', 'education', 'edu-admission-screen', '招生材料预检', 'Admission Material Precheck', 'docs/domains/education/specs/edu-admission-screen.json', 'education', 0, 'rule', 'engine', '', 'domains', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00') ON CONFLICT(slug) DO NOTHING;
INSERT INTO scenarios (id, domain_id, slug, label_zh, label_en, spec_path, category, sort, track, generator_kind, distill_yaml, origin, created_at, updated_at) VALUES ('edu-answer-grading', 'education', 'edu-answer-grading', '主观题阅卷辅助', 'Subjective Answer Grading', 'docs/domains/education/specs/edu-answer-grading.json', 'education', 1, 'distill', '', 'kev/console/distill/configs/edu-answer-grading.yaml', 'domains', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00') ON CONFLICT(slug) DO NOTHING;
INSERT INTO scenarios (id, domain_id, slug, label_zh, label_en, spec_path, category, sort, track, generator_kind, distill_yaml, origin, created_at, updated_at) VALUES ('edu-cheating-risk', 'education', 'edu-cheating-risk', '考试行为异常识别', 'Exam Misconduct Risk', 'docs/domains/education/specs/edu-cheating-risk.json', 'education', 2, 'rule', 'engine', '', 'domains', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00') ON CONFLICT(slug) DO NOTHING;
INSERT INTO scenarios (id, domain_id, slug, label_zh, label_en, spec_path, category, sort, track, generator_kind, distill_yaml, origin, created_at, updated_at) VALUES ('edu-early-warning', 'education', 'edu-early-warning', '学业预警', 'Academic Early Warning', 'docs/domains/education/specs/edu-early-warning.json', 'education', 3, 'rule', 'engine', '', 'domains', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00') ON CONFLICT(slug) DO NOTHING;
INSERT INTO scenarios (id, domain_id, slug, label_zh, label_en, spec_path, category, sort, track, generator_kind, distill_yaml, origin, created_at, updated_at) VALUES ('edu-error-diagnosis', 'education', 'edu-error-diagnosis', '错因诊断', 'Error Diagnosis', 'docs/domains/education/specs/edu-error-diagnosis.json', 'education', 4, 'distill', '', 'kev/console/distill/configs/edu-error-diagnosis.yaml', 'domains', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00') ON CONFLICT(slug) DO NOTHING;
INSERT INTO scenarios (id, domain_id, slug, label_zh, label_en, spec_path, category, sort, track, generator_kind, distill_yaml, origin, created_at, updated_at) VALUES ('edu-essay-scoring', 'education', 'edu-essay-scoring', '作文评分', 'Essay Scoring', 'docs/domains/education/specs/edu-essay-scoring.json', 'education', 5, 'distill', '', 'kev/console/distill/configs/edu-essay-scoring.yaml', 'domains', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00') ON CONFLICT(slug) DO NOTHING;
INSERT INTO scenarios (id, domain_id, slug, label_zh, label_en, spec_path, category, sort, track, generator_kind, distill_yaml, origin, created_at, updated_at) VALUES ('edu-iep-review', 'education', 'edu-iep-review', 'IEP 审查', 'IEP Review Triage', 'docs/domains/education/specs/edu-iep-review.json', 'education', 6, 'distill', '', 'kev/console/distill/configs/edu-iep-review.yaml', 'domains', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00') ON CONFLICT(slug) DO NOTHING;
INSERT INTO scenarios (id, domain_id, slug, label_zh, label_en, spec_path, category, sort, track, generator_kind, distill_yaml, origin, created_at, updated_at) VALUES ('edu-knowledge-tagging', 'education', 'edu-knowledge-tagging', '知识点标注', 'Knowledge Tagging', 'docs/domains/education/specs/edu-knowledge-tagging.json', 'education', 7, 'distill', '', 'kev/console/distill/configs/edu-knowledge-tagging.yaml', 'domains', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00') ON CONFLICT(slug) DO NOTHING;
INSERT INTO scenarios (id, domain_id, slug, label_zh, label_en, spec_path, category, sort, track, generator_kind, distill_yaml, origin, created_at, updated_at) VALUES ('edu-lesson-review', 'education', 'edu-lesson-review', '教案审查', 'Lesson Plan Review', 'docs/domains/education/specs/edu-lesson-review.json', 'education', 8, 'distill', '', 'kev/console/distill/configs/edu-lesson-review.yaml', 'domains', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00') ON CONFLICT(slug) DO NOTHING;
INSERT INTO scenarios (id, domain_id, slug, label_zh, label_en, spec_path, category, sort, track, generator_kind, distill_yaml, origin, created_at, updated_at) VALUES ('edu-material-adapt', 'education', 'edu-material-adapt', '材料难度适配', 'Material Adaptation', 'docs/domains/education/specs/edu-material-adapt.json', 'education', 9, 'distill', '', 'kev/console/distill/configs/edu-material-adapt.yaml', 'domains', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00') ON CONFLICT(slug) DO NOTHING;
INSERT INTO scenarios (id, domain_id, slug, label_zh, label_en, spec_path, category, sort, track, generator_kind, distill_yaml, origin, created_at, updated_at) VALUES ('edu-question-classify', 'education', 'edu-question-classify', '试题分类定级', 'Question Classification', 'docs/domains/education/specs/edu-question-classify.json', 'education', 10, 'rule', 'engine', '', 'domains', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00') ON CONFLICT(slug) DO NOTHING;

-- 科研（science）：
INSERT INTO scenarios (id, domain_id, slug, label_zh, label_en, spec_path, category, sort, track, generator_kind, distill_yaml, origin, created_at, updated_at) VALUES ('sci-data-quality', 'science', 'sci-data-quality', '数据质量', 'Data Quality', 'docs/domains/science/specs/sci-data-quality.json', 'science', 0, 'distill', '', 'kev/console/distill/configs/sci-data-quality.yaml', 'domains', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00') ON CONFLICT(slug) DO NOTHING;
INSERT INTO scenarios (id, domain_id, slug, label_zh, label_en, spec_path, category, sort, track, generator_kind, distill_yaml, origin, created_at, updated_at) VALUES ('sci-data-sharing-review', 'science', 'sci-data-sharing-review', '数据共享审查', 'Data Sharing Review', 'docs/domains/science/specs/sci-data-sharing-review.json', 'science', 1, 'distill', '', 'kev/console/distill/configs/sci-data-sharing-review.yaml', 'domains', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00') ON CONFLICT(slug) DO NOTHING;
INSERT INTO scenarios (id, domain_id, slug, label_zh, label_en, spec_path, category, sort, track, generator_kind, distill_yaml, origin, created_at, updated_at) VALUES ('sci-ethics-review', 'science', 'sci-ethics-review', '伦理预分诊', 'Ethics Review Triage', 'docs/domains/science/specs/sci-ethics-review.json', 'science', 2, 'distill', '', 'kev/console/distill/configs/sci-ethics-review.yaml', 'domains', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00') ON CONFLICT(slug) DO NOTHING;
INSERT INTO scenarios (id, domain_id, slug, label_zh, label_en, spec_path, category, sort, track, generator_kind, distill_yaml, origin, created_at, updated_at) VALUES ('sci-experiment-normalize', 'science', 'sci-experiment-normalize', '实验记录规范化', 'Experiment Record Normalization', 'docs/domains/science/specs/sci-experiment-normalize.json', 'science', 3, 'rule', 'engine', '', 'domains', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00') ON CONFLICT(slug) DO NOTHING;
INSERT INTO scenarios (id, domain_id, slug, label_zh, label_en, spec_path, category, sort, track, generator_kind, distill_yaml, origin, created_at, updated_at) VALUES ('sci-figure-check', 'science', 'sci-figure-check', '图表预审', 'Figure Compliance Check', 'docs/domains/science/specs/sci-figure-check.json', 'science', 4, 'distill', '', 'kev/console/distill/configs/sci-figure-check.yaml', 'domains', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00') ON CONFLICT(slug) DO NOTHING;
INSERT INTO scenarios (id, domain_id, slug, label_zh, label_en, spec_path, category, sort, track, generator_kind, distill_yaml, origin, created_at, updated_at) VALUES ('sci-grant-triage', 'science', 'sci-grant-triage', '基金初筛', 'Grant Triage', 'docs/domains/science/specs/sci-grant-triage.json', 'science', 5, 'distill', '', 'kev/console/distill/configs/sci-grant-triage.yaml', 'domains', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00') ON CONFLICT(slug) DO NOTHING;
INSERT INTO scenarios (id, domain_id, slug, label_zh, label_en, spec_path, category, sort, track, generator_kind, distill_yaml, origin, created_at, updated_at) VALUES ('sci-literature-classify', 'science', 'sci-literature-classify', '文献归类', 'Literature Classification', 'docs/domains/science/specs/sci-literature-classify.json', 'science', 6, 'distill', '', 'kev/console/distill/configs/sci-literature-classify.yaml', 'domains', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00') ON CONFLICT(slug) DO NOTHING;
INSERT INTO scenarios (id, domain_id, slug, label_zh, label_en, spec_path, category, sort, track, generator_kind, distill_yaml, origin, created_at, updated_at) VALUES ('sci-metadata-fair', 'science', 'sci-metadata-fair', 'FAIR 元数据评分', 'FAIR Metadata Review', 'docs/domains/science/specs/sci-metadata-fair.json', 'science', 7, 'rule', 'engine', '', 'domains', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00') ON CONFLICT(slug) DO NOTHING;
INSERT INTO scenarios (id, domain_id, slug, label_zh, label_en, spec_path, category, sort, track, generator_kind, distill_yaml, origin, created_at, updated_at) VALUES ('sci-reproducibility', 'science', 'sci-reproducibility', '可复现性预检', 'Reproducibility Precheck', 'docs/domains/science/specs/sci-reproducibility.json', 'science', 8, 'rule', 'engine', '', 'domains', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00') ON CONFLICT(slug) DO NOTHING;
INSERT INTO scenarios (id, domain_id, slug, label_zh, label_en, spec_path, category, sort, track, generator_kind, distill_yaml, origin, created_at, updated_at) VALUES ('sci-review-triage', 'science', 'sci-review-triage', '审稿分诊', 'Review Triage', 'docs/domains/science/specs/sci-review-triage.json', 'science', 9, 'distill', '', 'kev/console/distill/configs/sci-review-triage.yaml', 'domains', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00') ON CONFLICT(slug) DO NOTHING;
INSERT INTO scenarios (id, domain_id, slug, label_zh, label_en, spec_path, category, sort, track, generator_kind, distill_yaml, origin, created_at, updated_at) VALUES ('sci-software-archive', 'science', 'sci-software-archive', '软件存档合规', 'Software Archive Review', 'docs/domains/science/specs/sci-software-archive.json', 'science', 10, 'rule', 'engine', '', 'domains', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00') ON CONFLICT(slug) DO NOTHING;
INSERT INTO scenarios (id, domain_id, slug, label_zh, label_en, spec_path, category, sort, track, generator_kind, distill_yaml, origin, created_at, updated_at) VALUES ('sci-topic-identification', 'science', 'sci-topic-identification', '研究主题识别', 'Research Topic Identification', 'docs/domains/science/specs/sci-topic-identification.json', 'science', 11, 'rule', 'engine', '', 'domains', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00') ON CONFLICT(slug) DO NOTHING;

-- 法律（law）：
INSERT INTO scenarios (id, domain_id, slug, label_zh, label_en, spec_path, category, sort, track, generator_kind, distill_yaml, origin, created_at, updated_at) VALUES ('law-adr-clause', 'law', 'law-adr-clause', '争议条款审查', 'Dispute Resolution Clause Review', 'docs/domains/law/specs/law-adr-clause.json', 'law', 0, 'distill', '', 'kev/console/distill/configs/law-adr-clause.yaml', 'domains', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00') ON CONFLICT(slug) DO NOTHING;
INSERT INTO scenarios (id, domain_id, slug, label_zh, label_en, spec_path, category, sort, track, generator_kind, distill_yaml, origin, created_at, updated_at) VALUES ('law-cause-mapping', 'law', 'law-cause-mapping', '案由映射', 'Cause of Action Mapping', 'docs/domains/law/specs/law-cause-mapping.json', 'law', 1, 'distill', '', 'kev/console/distill/configs/law-cause-mapping.yaml', 'domains', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00') ON CONFLICT(slug) DO NOTHING;
INSERT INTO scenarios (id, domain_id, slug, label_zh, label_en, spec_path, category, sort, track, generator_kind, distill_yaml, origin, created_at, updated_at) VALUES ('law-compliance-obligation', 'law', 'law-compliance-obligation', '合规义务分级', 'Compliance Obligation Tiering', 'docs/domains/law/specs/law-compliance-obligation.json', 'law', 2, 'rule', 'engine', '', 'domains', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00') ON CONFLICT(slug) DO NOTHING;
INSERT INTO scenarios (id, domain_id, slug, label_zh, label_en, spec_path, category, sort, track, generator_kind, distill_yaml, origin, created_at, updated_at) VALUES ('law-contract-clause', 'law', 'law-contract-clause', '合同条款', 'Contract Clauses', 'docs/domains/law/specs/law-contract-clause.json', 'law', 3, 'distill', '', 'kev/console/distill/configs/law-contract-clause.yaml', 'domains', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00') ON CONFLICT(slug) DO NOTHING;
INSERT INTO scenarios (id, domain_id, slug, label_zh, label_en, spec_path, category, sort, track, generator_kind, distill_yaml, origin, created_at, updated_at) VALUES ('law-contract-risk', 'law', 'law-contract-risk', '风险条款分级', 'Risk Clause Tiering', 'docs/domains/law/specs/law-contract-risk.json', 'law', 4, 'rule', 'engine', '', 'domains', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00') ON CONFLICT(slug) DO NOTHING;
INSERT INTO scenarios (id, domain_id, slug, label_zh, label_en, spec_path, category, sort, track, generator_kind, distill_yaml, origin, created_at, updated_at) VALUES ('law-dispute-focus', 'law', 'law-dispute-focus', '争议焦点', 'Dispute Focus', 'docs/domains/law/specs/law-dispute-focus.json', 'law', 5, 'distill', '', 'kev/console/distill/configs/law-dispute-focus.yaml', 'domains', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00') ON CONFLICT(slug) DO NOTHING;
INSERT INTO scenarios (id, domain_id, slug, label_zh, label_en, spec_path, category, sort, track, generator_kind, distill_yaml, origin, created_at, updated_at) VALUES ('law-evidence-chain', 'law', 'law-evidence-chain', '证据链完整性', 'Evidence Chain Integrity', 'docs/domains/law/specs/law-evidence-chain.json', 'law', 6, 'rule', 'engine', '', 'domains', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00') ON CONFLICT(slug) DO NOTHING;
INSERT INTO scenarios (id, domain_id, slug, label_zh, label_en, spec_path, category, sort, track, generator_kind, distill_yaml, origin, created_at, updated_at) VALUES ('law-ip-infringement', 'law', 'law-ip-infringement', '侵权线索分诊', 'IP Infringement Triage', 'docs/domains/law/specs/law-ip-infringement.json', 'law', 7, 'distill', '', 'kev/console/distill/configs/law-ip-infringement.yaml', 'domains', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00') ON CONFLICT(slug) DO NOTHING;
INSERT INTO scenarios (id, domain_id, slug, label_zh, label_en, spec_path, category, sort, track, generator_kind, distill_yaml, origin, created_at, updated_at) VALUES ('law-legal-doc-classify', 'law', 'law-legal-doc-classify', '文书分类', 'Legal Document Classification', 'docs/domains/law/specs/law-legal-doc-classify.json', 'law', 8, 'distill', '', 'kev/console/distill/configs/law-legal-doc-classify.yaml', 'domains', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00') ON CONFLICT(slug) DO NOTHING;
INSERT INTO scenarios (id, domain_id, slug, label_zh, label_en, spec_path, category, sort, track, generator_kind, distill_yaml, origin, created_at, updated_at) VALUES ('law-privacy-dsr', 'law', 'law-privacy-dsr', 'DSR 分诊', 'Data Subject Request Triage', 'docs/domains/law/specs/law-privacy-dsr.json', 'law', 9, 'distill', '', 'kev/console/distill/configs/law-privacy-dsr.yaml', 'domains', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00') ON CONFLICT(slug) DO NOTHING;
INSERT INTO scenarios (id, domain_id, slug, label_zh, label_en, spec_path, category, sort, track, generator_kind, distill_yaml, origin, created_at, updated_at) VALUES ('law-regulation-watch', 'law', 'law-regulation-watch', '监管新规影响分级', 'Regulation Watch', 'docs/domains/law/specs/law-regulation-watch.json', 'law', 10, 'rule', 'engine', '', 'domains', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00') ON CONFLICT(slug) DO NOTHING;
