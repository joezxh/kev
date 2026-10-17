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
  exit_code     INTEGER,
  error         TEXT,
  created_at    TEXT NOT NULL,
  started_at    TEXT,
  finished_at   TEXT
);
CREATE INDEX IF NOT EXISTS jobs_status_idx   ON jobs(status);
CREATE INDEX IF NOT EXISTS jobs_scenario_idx ON jobs(scenario, created_at DESC);
CREATE INDEX IF NOT EXISTS jobs_project_idx  ON jobs(project_id, created_at DESC);

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
  id     INTEGER PRIMARY KEY AUTOINCREMENT,
  job_id TEXT NOT NULL REFERENCES jobs(id),
  ts     TEXT NOT NULL,
  stream TEXT NOT NULL,
  line   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS events_job_idx ON events(job_id, id);

CREATE TABLE IF NOT EXISTS api_keys (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  key_hash TEXT NOT NULL UNIQUE,
  prefix TEXT NOT NULL,
  active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  revoked_at TEXT
);
CREATE INDEX IF NOT EXISTS api_keys_hash_idx ON api_keys(key_hash);

CREATE TABLE IF NOT EXISTS usage_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  key_id TEXT NOT NULL REFERENCES api_keys(id),
  endpoint TEXT NOT NULL,
  method TEXT NOT NULL,
  status INTEGER NOT NULL,
  input_tokens INTEGER NOT NULL DEFAULT 0,
  output_tokens INTEGER NOT NULL DEFAULT 0,
  latency_ms REAL NOT NULL,
  ts TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS usage_log_key_ts_idx ON usage_log(key_id, ts);
CREATE INDEX IF NOT EXISTS usage_log_ts_idx ON usage_log(ts);

CREATE TABLE IF NOT EXISTS distill_providers (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  base_url TEXT NOT NULL,
  model TEXT NOT NULL,
  daily_limit INTEGER NOT NULL DEFAULT 500000,
  key_count INTEGER NOT NULL DEFAULT 0,
  key_hints TEXT NOT NULL DEFAULT '[]',
  active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS distill_providers_active_idx ON distill_providers(active);

CREATE TABLE IF NOT EXISTS distill_usage (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  job_id TEXT NOT NULL REFERENCES jobs(id),
  provider_id TEXT NOT NULL,
  key_hash TEXT NOT NULL,
  key_hint TEXT NOT NULL,
  model TEXT NOT NULL,
  base_url TEXT NOT NULL,
  day TEXT NOT NULL,
  tokens INTEGER NOT NULL DEFAULT 0,
  ts TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS distill_usage_ukd ON distill_usage(provider_id, key_hash, day);
CREATE INDEX IF NOT EXISTS distill_usage_job_idx ON distill_usage(job_id);
CREATE INDEX IF NOT EXISTS distill_usage_day_idx ON distill_usage(day);

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
CREATE INDEX IF NOT EXISTS scenarios_slug_idx   ON scenarios(slug);
CREATE INDEX IF NOT EXISTS scenarios_domain_idx ON scenarios(domain_id);

CREATE TABLE IF NOT EXISTS scenario_spec_history (
  id          TEXT PRIMARY KEY,
  scenario_id TEXT NOT NULL REFERENCES scenarios(id),
  spec_json   TEXT NOT NULL,
  created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS spec_history_scenario_idx ON scenario_spec_history(scenario_id, created_at DESC);

-- 作业类型「提交表单」参数 schema：单一真相源，落库后可经 API 改（版本化）。
-- 结构与前端 JobStagePage 的 FieldSpec 对齐；default 与各 StageSpec.build() 默认值一致。
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

-- 命名作业模板：跨会话复用/编辑某类任务的参数预设。
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

-- ch6 管理面：projects / members / quota / webhooks / invoices
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
  freeze_min_review_ratio REAL    NOT NULL DEFAULT 0.10,
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
  project_id           TEXT PRIMARY KEY REFERENCES projects(id),
  training_hours_limit REAL NOT NULL DEFAULT 0,
  training_hours_used  REAL NOT NULL DEFAULT 0,
  gpu_limit            INTEGER NOT NULL DEFAULT 0,
  api_calls_limit      INTEGER NOT NULL DEFAULT 0,
  api_calls_used       INTEGER NOT NULL DEFAULT 0,
  storage_gb_limit     REAL NOT NULL DEFAULT 0,
  storage_gb_used      REAL NOT NULL DEFAULT 0,
  updated_at           TEXT NOT NULL
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
  amount     REAL NOT NULL,
  currency   TEXT NOT NULL DEFAULT 'USD',
  status     TEXT NOT NULL DEFAULT 'open',
  due_at     TEXT,
  issued_at  TEXT NOT NULL,
  line_items TEXT NOT NULL DEFAULT '[]'
);
CREATE INDEX IF NOT EXISTS invoices_project_idx ON invoices(project_id, period DESC);

-- ---- v9 数据策展（Project Hub PR A，与 kev/console/db.py::_ddl 逐列一致）----
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
  review_ratio       REAL,
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

-- ---- 初始数据（领域与场景登记；spec 内容由 scripts/import_domain_specs.py 或控制台启动时的 seed_scenarios 落库）----
INSERT OR IGNORE INTO console_meta (key, value) VALUES ('schema_version', '9');
INSERT OR IGNORE INTO scenario_domains (id, slug, label_zh, label_en, sort, spec_dir, created_at) VALUES ('medical', 'medical', '医疗', 'Medical', 0, 'medical', '2026-01-01T00:00:00+00:00');
INSERT OR IGNORE INTO scenario_domains (id, slug, label_zh, label_en, sort, spec_dir, created_at) VALUES ('finance', 'finance', '金融', 'Finance', 10, 'finance', '2026-01-01T00:00:00+00:00');
INSERT OR IGNORE INTO scenario_domains (id, slug, label_zh, label_en, sort, spec_dir, created_at) VALUES ('education', 'education', '教育', 'Education', 20, 'education', '2026-01-01T00:00:00+00:00');
INSERT OR IGNORE INTO scenario_domains (id, slug, label_zh, label_en, sort, spec_dir, created_at) VALUES ('science', 'science', '科研', 'Research', 30, 'science', '2026-01-01T00:00:00+00:00');
INSERT OR IGNORE INTO scenario_domains (id, slug, label_zh, label_en, sort, spec_dir, created_at) VALUES ('law', 'law', '法律', 'Law', 40, 'law', '2026-01-01T00:00:00+00:00');
INSERT OR IGNORE INTO scenarios (id, domain_id, slug, label_zh, label_en, spec_path, category, sort, track, generator_kind, distill_yaml, origin, created_at, updated_at) VALUES ('critical-value', 'medical', 'critical-value', '危急值', 'Critical Value', 'docs/domains/medical/specs/critical-value.json', 'medical', 0, 'rule', 'script', '', 'domains', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00');
INSERT OR IGNORE INTO scenarios (id, domain_id, slug, label_zh, label_en, spec_path, category, sort, track, generator_kind, distill_yaml, origin, created_at, updated_at) VALUES ('diagnosis', 'medical', 'diagnosis', '诊断', 'Diagnosis', 'docs/domains/medical/specs/diagnosis.json', 'medical', 1, 'both', 'script', 'kev/console/distill/configs/diagnosis.yaml', 'domains', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00');
INSERT OR IGNORE INTO scenarios (id, domain_id, slug, label_zh, label_en, spec_path, category, sort, track, generator_kind, distill_yaml, origin, created_at, updated_at) VALUES ('follow-up-tier', 'medical', 'follow-up-tier', '出院随访分级', 'Follow-up Tiering', 'docs/domains/medical/specs/follow-up-tier.json', 'medical', 2, 'rule', 'engine', '', 'domains', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00');
INSERT OR IGNORE INTO scenarios (id, domain_id, slug, label_zh, label_en, spec_path, category, sort, track, generator_kind, distill_yaml, origin, created_at, updated_at) VALUES ('icd-coding', 'medical', 'icd-coding', 'ICD 编码', 'ICD Coding', 'docs/domains/medical/specs/icd-coding.json', 'medical', 3, 'llm', '', '', 'domains', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00');
INSERT OR IGNORE INTO scenarios (id, domain_id, slug, label_zh, label_en, spec_path, category, sort, track, generator_kind, distill_yaml, origin, created_at, updated_at) VALUES ('infection-report', 'medical', 'infection-report', '感染上报分诊', 'Infection Report Triage', 'docs/domains/medical/specs/infection-report.json', 'medical', 4, 'rule', 'engine', '', 'domains', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00');
INSERT OR IGNORE INTO scenarios (id, domain_id, slug, label_zh, label_en, spec_path, category, sort, track, generator_kind, distill_yaml, origin, created_at, updated_at) VALUES ('inquiry', 'medical', 'inquiry', '导诊', 'Inquiry', 'docs/domains/medical/specs/inquiry.json', 'medical', 5, 'distill', '', 'kev/console/distill/configs/inquiry.yaml', 'domains', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00');
INSERT OR IGNORE INTO scenarios (id, domain_id, slug, label_zh, label_en, spec_path, category, sort, track, generator_kind, distill_yaml, origin, created_at, updated_at) VALUES ('knowledge-qa', 'medical', 'knowledge-qa', '医学知识问答', 'Medical Knowledge Q&A', 'docs/domains/medical/specs/knowledge-qa.json', 'medical', 6, 'distill', '', 'kev/console/distill/configs/knowledge-qa.yaml', 'domains', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00');
INSERT OR IGNORE INTO scenarios (id, domain_id, slug, label_zh, label_en, spec_path, category, sort, track, generator_kind, distill_yaml, origin, created_at, updated_at) VALUES ('mdr-report', 'medical', 'mdr-report', '器械不良事件', 'Device Adverse Event Triage', 'docs/domains/medical/specs/mdr-report.json', 'medical', 7, 'distill', '', 'kev/console/distill/configs/mdr-report.yaml', 'domains', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00');
INSERT OR IGNORE INTO scenarios (id, domain_id, slug, label_zh, label_en, spec_path, category, sort, track, generator_kind, distill_yaml, origin, created_at, updated_at) VALUES ('medication-review', 'medical', 'medication-review', '用药审查', 'Medication Review', 'docs/domains/medical/specs/medication-review.json', 'medical', 8, 'both', 'script', 'kev/console/distill/configs/medication.yaml', 'domains', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00');
INSERT OR IGNORE INTO scenarios (id, domain_id, slug, label_zh, label_en, spec_path, category, sort, track, generator_kind, distill_yaml, origin, created_at, updated_at) VALUES ('medication', 'medical', 'medication', '用药指导', 'Medication', 'docs/domains/medical/specs/medication.json', 'medical', 9, 'distill', '', 'kev/console/distill/configs/medication.yaml', 'domains', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00');
INSERT OR IGNORE INTO scenarios (id, domain_id, slug, label_zh, label_en, spec_path, category, sort, track, generator_kind, distill_yaml, origin, created_at, updated_at) VALUES ('nursing-quality', 'medical', 'nursing-quality', '护理质量', 'Nursing Quality', 'docs/domains/medical/specs/nursing-quality.json', 'medical', 10, 'rule', 'script', '', 'domains', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00');
INSERT OR IGNORE INTO scenarios (id, domain_id, slug, label_zh, label_en, spec_path, category, sort, track, generator_kind, distill_yaml, origin, created_at, updated_at) VALUES ('record-summary', 'medical', 'record-summary', '病历摘要', 'Record Summary', 'docs/domains/medical/specs/record-summary.json', 'medical', 11, 'both', 'script', 'kev/console/distill/configs/record-summary.yaml', 'domains', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00');
INSERT OR IGNORE INTO scenarios (id, domain_id, slug, label_zh, label_en, spec_path, category, sort, track, generator_kind, distill_yaml, origin, created_at, updated_at) VALUES ('surgical-checklist', 'medical', 'surgical-checklist', '手术核查', 'Surgical Safety Checklist Review', 'docs/domains/medical/specs/surgical-checklist.json', 'medical', 12, 'distill', '', 'kev/console/distill/configs/surgical-checklist.yaml', 'domains', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00');
INSERT OR IGNORE INTO scenarios (id, domain_id, slug, label_zh, label_en, spec_path, category, sort, track, generator_kind, distill_yaml, origin, created_at, updated_at) VALUES ('transfusion-review', 'medical', 'transfusion-review', '输血审核', 'Transfusion Review', 'docs/domains/medical/specs/transfusion-review.json', 'medical', 13, 'rule', 'engine', '', 'domains', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00');
INSERT OR IGNORE INTO scenarios (id, domain_id, slug, label_zh, label_en, spec_path, category, sort, track, generator_kind, distill_yaml, origin, created_at, updated_at) VALUES ('triage', 'medical', 'triage', '分诊', 'Triage', 'docs/domains/medical/specs/triage.json', 'medical', 14, 'both', 'script', 'kev/console/distill/configs/inquiry.yaml', 'domains', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00');
INSERT OR IGNORE INTO scenarios (id, domain_id, slug, label_zh, label_en, spec_path, category, sort, track, generator_kind, distill_yaml, origin, created_at, updated_at) VALUES ('fin-aml-alert', 'finance', 'fin-aml-alert', '反洗钱预警复核', 'AML Alert Review', 'docs/domains/finance/specs/fin-aml-alert.json', 'finance', 0, 'rule', 'engine', '', 'domains', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00');
INSERT OR IGNORE INTO scenarios (id, domain_id, slug, label_zh, label_en, spec_path, category, sort, track, generator_kind, distill_yaml, origin, created_at, updated_at) VALUES ('fin-collection-tier', 'finance', 'fin-collection-tier', '催收分级', 'Collection Tiering', 'docs/domains/finance/specs/fin-collection-tier.json', 'finance', 1, 'rule', 'engine', '', 'domains', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00');
INSERT OR IGNORE INTO scenarios (id, domain_id, slug, label_zh, label_en, spec_path, category, sort, track, generator_kind, distill_yaml, origin, created_at, updated_at) VALUES ('fin-complaint-triage', 'finance', 'fin-complaint-triage', '投诉分诊', 'Complaint Triage', 'docs/domains/finance/specs/fin-complaint-triage.json', 'finance', 2, 'distill', '', 'kev/console/distill/configs/fin-complaint-triage.yaml', 'domains', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00');
INSERT OR IGNORE INTO scenarios (id, domain_id, slug, label_zh, label_en, spec_path, category, sort, track, generator_kind, distill_yaml, origin, created_at, updated_at) VALUES ('fin-compliance-review', 'finance', 'fin-compliance-review', '营销文本合规审查', 'Marketing Compliance Review', 'docs/domains/finance/specs/fin-compliance-review.json', 'finance', 3, 'distill', '', 'kev/console/distill/configs/fin-compliance-review.yaml', 'domains', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00');
INSERT OR IGNORE INTO scenarios (id, domain_id, slug, label_zh, label_en, spec_path, category, sort, track, generator_kind, distill_yaml, origin, created_at, updated_at) VALUES ('fin-credit-doc-review', 'finance', 'fin-credit-doc-review', '信贷资料完整性', 'Credit Document Review', 'docs/domains/finance/specs/fin-credit-doc-review.json', 'finance', 4, 'rule', 'engine', '', 'domains', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00');
INSERT OR IGNORE INTO scenarios (id, domain_id, slug, label_zh, label_en, spec_path, category, sort, track, generator_kind, distill_yaml, origin, created_at, updated_at) VALUES ('fin-credit-score-explain', 'finance', 'fin-credit-score-explain', '征信异议分诊', 'Credit Dispute Triage', 'docs/domains/finance/specs/fin-credit-score-explain.json', 'finance', 5, 'distill', '', 'kev/console/distill/configs/fin-credit-score-explain.yaml', 'domains', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00');
INSERT OR IGNORE INTO scenarios (id, domain_id, slug, label_zh, label_en, spec_path, category, sort, track, generator_kind, distill_yaml, origin, created_at, updated_at) VALUES ('fin-customer-intent', 'finance', 'fin-customer-intent', '客户意图', 'Customer Intent', 'docs/domains/finance/specs/fin-customer-intent.json', 'finance', 6, 'distill', '', 'kev/console/distill/configs/fin-customer-intent.yaml', 'domains', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00');
INSERT OR IGNORE INTO scenarios (id, domain_id, slug, label_zh, label_en, spec_path, category, sort, track, generator_kind, distill_yaml, origin, created_at, updated_at) VALUES ('fin-dispute-classification', 'finance', 'fin-dispute-classification', '交易争议分类', 'Transaction Dispute Classification', 'docs/domains/finance/specs/fin-dispute-classification.json', 'finance', 7, 'distill', '', 'kev/console/distill/configs/fin-dispute-classification.yaml', 'domains', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00');
INSERT OR IGNORE INTO scenarios (id, domain_id, slug, label_zh, label_en, spec_path, category, sort, track, generator_kind, distill_yaml, origin, created_at, updated_at) VALUES ('fin-fraud-claim-review', 'finance', 'fin-fraud-claim-review', '欺诈理赔复核', 'Fraud Claim Review', 'docs/domains/finance/specs/fin-fraud-claim-review.json', 'finance', 8, 'rule', 'engine', '', 'domains', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00');
INSERT OR IGNORE INTO scenarios (id, domain_id, slug, label_zh, label_en, spec_path, category, sort, track, generator_kind, distill_yaml, origin, created_at, updated_at) VALUES ('fin-kyc-review', 'finance', 'fin-kyc-review', '客户尽调资料复核', 'KYC Due Diligence Review', 'docs/domains/finance/specs/fin-kyc-review.json', 'finance', 9, 'rule', 'engine', '', 'domains', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00');
INSERT OR IGNORE INTO scenarios (id, domain_id, slug, label_zh, label_en, spec_path, category, sort, track, generator_kind, distill_yaml, origin, created_at, updated_at) VALUES ('fin-transaction-anomaly', 'finance', 'fin-transaction-anomaly', '异常交易识别', 'Transaction Anomaly', 'docs/domains/finance/specs/fin-transaction-anomaly.json', 'finance', 10, 'rule', 'engine', '', 'domains', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00');
INSERT OR IGNORE INTO scenarios (id, domain_id, slug, label_zh, label_en, spec_path, category, sort, track, generator_kind, distill_yaml, origin, created_at, updated_at) VALUES ('fin-underwrite-triage', 'finance', 'fin-underwrite-triage', '核保分诊', 'Underwriting Triage', 'docs/domains/finance/specs/fin-underwrite-triage.json', 'finance', 11, 'rule', 'engine', '', 'domains', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00');
INSERT OR IGNORE INTO scenarios (id, domain_id, slug, label_zh, label_en, spec_path, category, sort, track, generator_kind, distill_yaml, origin, created_at, updated_at) VALUES ('edu-admission-screen', 'education', 'edu-admission-screen', '招生材料预检', 'Admission Material Precheck', 'docs/domains/education/specs/edu-admission-screen.json', 'education', 0, 'rule', 'engine', '', 'domains', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00');
INSERT OR IGNORE INTO scenarios (id, domain_id, slug, label_zh, label_en, spec_path, category, sort, track, generator_kind, distill_yaml, origin, created_at, updated_at) VALUES ('edu-answer-grading', 'education', 'edu-answer-grading', '主观题阅卷辅助', 'Subjective Answer Grading', 'docs/domains/education/specs/edu-answer-grading.json', 'education', 1, 'distill', '', 'kev/console/distill/configs/edu-answer-grading.yaml', 'domains', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00');
INSERT OR IGNORE INTO scenarios (id, domain_id, slug, label_zh, label_en, spec_path, category, sort, track, generator_kind, distill_yaml, origin, created_at, updated_at) VALUES ('edu-cheating-risk', 'education', 'edu-cheating-risk', '考试行为异常识别', 'Exam Misconduct Risk', 'docs/domains/education/specs/edu-cheating-risk.json', 'education', 2, 'rule', 'engine', '', 'domains', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00');
INSERT OR IGNORE INTO scenarios (id, domain_id, slug, label_zh, label_en, spec_path, category, sort, track, generator_kind, distill_yaml, origin, created_at, updated_at) VALUES ('edu-early-warning', 'education', 'edu-early-warning', '学业预警', 'Academic Early Warning', 'docs/domains/education/specs/edu-early-warning.json', 'education', 3, 'rule', 'engine', '', 'domains', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00');
INSERT OR IGNORE INTO scenarios (id, domain_id, slug, label_zh, label_en, spec_path, category, sort, track, generator_kind, distill_yaml, origin, created_at, updated_at) VALUES ('edu-error-diagnosis', 'education', 'edu-error-diagnosis', '错因诊断', 'Error Diagnosis', 'docs/domains/education/specs/edu-error-diagnosis.json', 'education', 4, 'distill', '', 'kev/console/distill/configs/edu-error-diagnosis.yaml', 'domains', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00');
INSERT OR IGNORE INTO scenarios (id, domain_id, slug, label_zh, label_en, spec_path, category, sort, track, generator_kind, distill_yaml, origin, created_at, updated_at) VALUES ('edu-essay-scoring', 'education', 'edu-essay-scoring', '作文评分', 'Essay Scoring', 'docs/domains/education/specs/edu-essay-scoring.json', 'education', 5, 'distill', '', 'kev/console/distill/configs/edu-essay-scoring.yaml', 'domains', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00');
INSERT OR IGNORE INTO scenarios (id, domain_id, slug, label_zh, label_en, spec_path, category, sort, track, generator_kind, distill_yaml, origin, created_at, updated_at) VALUES ('edu-iep-review', 'education', 'edu-iep-review', 'IEP 审查', 'IEP Review Triage', 'docs/domains/education/specs/edu-iep-review.json', 'education', 6, 'distill', '', 'kev/console/distill/configs/edu-iep-review.yaml', 'domains', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00');
INSERT OR IGNORE INTO scenarios (id, domain_id, slug, label_zh, label_en, spec_path, category, sort, track, generator_kind, distill_yaml, origin, created_at, updated_at) VALUES ('edu-knowledge-tagging', 'education', 'edu-knowledge-tagging', '知识点标注', 'Knowledge Tagging', 'docs/domains/education/specs/edu-knowledge-tagging.json', 'education', 7, 'distill', '', 'kev/console/distill/configs/edu-knowledge-tagging.yaml', 'domains', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00');
INSERT OR IGNORE INTO scenarios (id, domain_id, slug, label_zh, label_en, spec_path, category, sort, track, generator_kind, distill_yaml, origin, created_at, updated_at) VALUES ('edu-lesson-review', 'education', 'edu-lesson-review', '教案审查', 'Lesson Plan Review', 'docs/domains/education/specs/edu-lesson-review.json', 'education', 8, 'distill', '', 'kev/console/distill/configs/edu-lesson-review.yaml', 'domains', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00');
INSERT OR IGNORE INTO scenarios (id, domain_id, slug, label_zh, label_en, spec_path, category, sort, track, generator_kind, distill_yaml, origin, created_at, updated_at) VALUES ('edu-material-adapt', 'education', 'edu-material-adapt', '材料难度适配', 'Material Adaptation', 'docs/domains/education/specs/edu-material-adapt.json', 'education', 9, 'distill', '', 'kev/console/distill/configs/edu-material-adapt.yaml', 'domains', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00');
INSERT OR IGNORE INTO scenarios (id, domain_id, slug, label_zh, label_en, spec_path, category, sort, track, generator_kind, distill_yaml, origin, created_at, updated_at) VALUES ('edu-question-classify', 'education', 'edu-question-classify', '试题分类定级', 'Question Classification', 'docs/domains/education/specs/edu-question-classify.json', 'education', 10, 'rule', 'engine', '', 'domains', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00');
INSERT OR IGNORE INTO scenarios (id, domain_id, slug, label_zh, label_en, spec_path, category, sort, track, generator_kind, distill_yaml, origin, created_at, updated_at) VALUES ('sci-data-quality', 'science', 'sci-data-quality', '数据质量', 'Data Quality', 'docs/domains/science/specs/sci-data-quality.json', 'science', 0, 'distill', '', 'kev/console/distill/configs/sci-data-quality.yaml', 'domains', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00');
INSERT OR IGNORE INTO scenarios (id, domain_id, slug, label_zh, label_en, spec_path, category, sort, track, generator_kind, distill_yaml, origin, created_at, updated_at) VALUES ('sci-data-sharing-review', 'science', 'sci-data-sharing-review', '数据共享审查', 'Data Sharing Review', 'docs/domains/science/specs/sci-data-sharing-review.json', 'science', 1, 'distill', '', 'kev/console/distill/configs/sci-data-sharing-review.yaml', 'domains', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00');
INSERT OR IGNORE INTO scenarios (id, domain_id, slug, label_zh, label_en, spec_path, category, sort, track, generator_kind, distill_yaml, origin, created_at, updated_at) VALUES ('sci-ethics-review', 'science', 'sci-ethics-review', '伦理预分诊', 'Ethics Review Triage', 'docs/domains/science/specs/sci-ethics-review.json', 'science', 2, 'distill', '', 'kev/console/distill/configs/sci-ethics-review.yaml', 'domains', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00');
INSERT OR IGNORE INTO scenarios (id, domain_id, slug, label_zh, label_en, spec_path, category, sort, track, generator_kind, distill_yaml, origin, created_at, updated_at) VALUES ('sci-experiment-normalize', 'science', 'sci-experiment-normalize', '实验记录规范化', 'Experiment Record Normalization', 'docs/domains/science/specs/sci-experiment-normalize.json', 'science', 3, 'rule', 'engine', '', 'domains', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00');
INSERT OR IGNORE INTO scenarios (id, domain_id, slug, label_zh, label_en, spec_path, category, sort, track, generator_kind, distill_yaml, origin, created_at, updated_at) VALUES ('sci-figure-check', 'science', 'sci-figure-check', '图表预审', 'Figure Compliance Check', 'docs/domains/science/specs/sci-figure-check.json', 'science', 4, 'distill', '', 'kev/console/distill/configs/sci-figure-check.yaml', 'domains', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00');
INSERT OR IGNORE INTO scenarios (id, domain_id, slug, label_zh, label_en, spec_path, category, sort, track, generator_kind, distill_yaml, origin, created_at, updated_at) VALUES ('sci-grant-triage', 'science', 'sci-grant-triage', '基金初筛', 'Grant Triage', 'docs/domains/science/specs/sci-grant-triage.json', 'science', 5, 'distill', '', 'kev/console/distill/configs/sci-grant-triage.yaml', 'domains', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00');
INSERT OR IGNORE INTO scenarios (id, domain_id, slug, label_zh, label_en, spec_path, category, sort, track, generator_kind, distill_yaml, origin, created_at, updated_at) VALUES ('sci-literature-classify', 'science', 'sci-literature-classify', '文献归类', 'Literature Classification', 'docs/domains/science/specs/sci-literature-classify.json', 'science', 6, 'distill', '', 'kev/console/distill/configs/sci-literature-classify.yaml', 'domains', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00');
INSERT OR IGNORE INTO scenarios (id, domain_id, slug, label_zh, label_en, spec_path, category, sort, track, generator_kind, distill_yaml, origin, created_at, updated_at) VALUES ('sci-metadata-fair', 'science', 'sci-metadata-fair', 'FAIR 元数据评分', 'FAIR Metadata Review', 'docs/domains/science/specs/sci-metadata-fair.json', 'science', 7, 'rule', 'engine', '', 'domains', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00');
INSERT OR IGNORE INTO scenarios (id, domain_id, slug, label_zh, label_en, spec_path, category, sort, track, generator_kind, distill_yaml, origin, created_at, updated_at) VALUES ('sci-reproducibility', 'science', 'sci-reproducibility', '可复现性预检', 'Reproducibility Precheck', 'docs/domains/science/specs/sci-reproducibility.json', 'science', 8, 'rule', 'engine', '', 'domains', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00');
INSERT OR IGNORE INTO scenarios (id, domain_id, slug, label_zh, label_en, spec_path, category, sort, track, generator_kind, distill_yaml, origin, created_at, updated_at) VALUES ('sci-review-triage', 'science', 'sci-review-triage', '审稿分诊', 'Review Triage', 'docs/domains/science/specs/sci-review-triage.json', 'science', 9, 'distill', '', 'kev/console/distill/configs/sci-review-triage.yaml', 'domains', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00');
INSERT OR IGNORE INTO scenarios (id, domain_id, slug, label_zh, label_en, spec_path, category, sort, track, generator_kind, distill_yaml, origin, created_at, updated_at) VALUES ('sci-software-archive', 'science', 'sci-software-archive', '软件存档合规', 'Software Archive Review', 'docs/domains/science/specs/sci-software-archive.json', 'science', 10, 'rule', 'engine', '', 'domains', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00');
INSERT OR IGNORE INTO scenarios (id, domain_id, slug, label_zh, label_en, spec_path, category, sort, track, generator_kind, distill_yaml, origin, created_at, updated_at) VALUES ('sci-topic-identification', 'science', 'sci-topic-identification', '研究主题识别', 'Research Topic Identification', 'docs/domains/science/specs/sci-topic-identification.json', 'science', 11, 'rule', 'engine', '', 'domains', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00');
INSERT OR IGNORE INTO scenarios (id, domain_id, slug, label_zh, label_en, spec_path, category, sort, track, generator_kind, distill_yaml, origin, created_at, updated_at) VALUES ('law-adr-clause', 'law', 'law-adr-clause', '争议条款审查', 'Dispute Resolution Clause Review', 'docs/domains/law/specs/law-adr-clause.json', 'law', 0, 'distill', '', 'kev/console/distill/configs/law-adr-clause.yaml', 'domains', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00');
INSERT OR IGNORE INTO scenarios (id, domain_id, slug, label_zh, label_en, spec_path, category, sort, track, generator_kind, distill_yaml, origin, created_at, updated_at) VALUES ('law-cause-mapping', 'law', 'law-cause-mapping', '案由映射', 'Cause of Action Mapping', 'docs/domains/law/specs/law-cause-mapping.json', 'law', 1, 'distill', '', 'kev/console/distill/configs/law-cause-mapping.yaml', 'domains', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00');
INSERT OR IGNORE INTO scenarios (id, domain_id, slug, label_zh, label_en, spec_path, category, sort, track, generator_kind, distill_yaml, origin, created_at, updated_at) VALUES ('law-compliance-obligation', 'law', 'law-compliance-obligation', '合规义务分级', 'Compliance Obligation Tiering', 'docs/domains/law/specs/law-compliance-obligation.json', 'law', 2, 'rule', 'engine', '', 'domains', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00');
INSERT OR IGNORE INTO scenarios (id, domain_id, slug, label_zh, label_en, spec_path, category, sort, track, generator_kind, distill_yaml, origin, created_at, updated_at) VALUES ('law-contract-clause', 'law', 'law-contract-clause', '合同条款', 'Contract Clauses', 'docs/domains/law/specs/law-contract-clause.json', 'law', 3, 'distill', '', 'kev/console/distill/configs/law-contract-clause.yaml', 'domains', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00');
INSERT OR IGNORE INTO scenarios (id, domain_id, slug, label_zh, label_en, spec_path, category, sort, track, generator_kind, distill_yaml, origin, created_at, updated_at) VALUES ('law-contract-risk', 'law', 'law-contract-risk', '风险条款分级', 'Risk Clause Tiering', 'docs/domains/law/specs/law-contract-risk.json', 'law', 4, 'rule', 'engine', '', 'domains', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00');
INSERT OR IGNORE INTO scenarios (id, domain_id, slug, label_zh, label_en, spec_path, category, sort, track, generator_kind, distill_yaml, origin, created_at, updated_at) VALUES ('law-dispute-focus', 'law', 'law-dispute-focus', '争议焦点', 'Dispute Focus', 'docs/domains/law/specs/law-dispute-focus.json', 'law', 5, 'distill', '', 'kev/console/distill/configs/law-dispute-focus.yaml', 'domains', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00');
INSERT OR IGNORE INTO scenarios (id, domain_id, slug, label_zh, label_en, spec_path, category, sort, track, generator_kind, distill_yaml, origin, created_at, updated_at) VALUES ('law-evidence-chain', 'law', 'law-evidence-chain', '证据链完整性', 'Evidence Chain Integrity', 'docs/domains/law/specs/law-evidence-chain.json', 'law', 6, 'rule', 'engine', '', 'domains', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00');
INSERT OR IGNORE INTO scenarios (id, domain_id, slug, label_zh, label_en, spec_path, category, sort, track, generator_kind, distill_yaml, origin, created_at, updated_at) VALUES ('law-ip-infringement', 'law', 'law-ip-infringement', '侵权线索分诊', 'IP Infringement Triage', 'docs/domains/law/specs/law-ip-infringement.json', 'law', 7, 'distill', '', 'kev/console/distill/configs/law-ip-infringement.yaml', 'domains', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00');
INSERT OR IGNORE INTO scenarios (id, domain_id, slug, label_zh, label_en, spec_path, category, sort, track, generator_kind, distill_yaml, origin, created_at, updated_at) VALUES ('law-legal-doc-classify', 'law', 'law-legal-doc-classify', '文书分类', 'Legal Document Classification', 'docs/domains/law/specs/law-legal-doc-classify.json', 'law', 8, 'distill', '', 'kev/console/distill/configs/law-legal-doc-classify.yaml', 'domains', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00');
INSERT OR IGNORE INTO scenarios (id, domain_id, slug, label_zh, label_en, spec_path, category, sort, track, generator_kind, distill_yaml, origin, created_at, updated_at) VALUES ('law-privacy-dsr', 'law', 'law-privacy-dsr', 'DSR 分诊', 'Data Subject Request Triage', 'docs/domains/law/specs/law-privacy-dsr.json', 'law', 9, 'distill', '', 'kev/console/distill/configs/law-privacy-dsr.yaml', 'domains', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00');
INSERT OR IGNORE INTO scenarios (id, domain_id, slug, label_zh, label_en, spec_path, category, sort, track, generator_kind, distill_yaml, origin, created_at, updated_at) VALUES ('law-regulation-watch', 'law', 'law-regulation-watch', '监管新规影响分级', 'Regulation Watch', 'docs/domains/law/specs/law-regulation-watch.json', 'law', 10, 'rule', 'engine', '', 'domains', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00');
