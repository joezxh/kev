-- =============================================================================
-- Project Hub v7 —— schema v9 增量迁移（PostgreSQL）：数据策展新表
-- =============================================================================
-- 对应：SCHEMA_VERSION 8 -> 9（kev/console/db.py::_ddl 追加的六张表与
--       _migrate 的 v9 版本边界注释）。
-- 范围：只包含本轮「数据策展」新增的结构——
--         * artifact_versions：产物的不可变版本快照（artifacts 是可变指针，D2，
--           artifact_id 不建指向 artifacts 的 FK）。
--         * bundles / bundle_members：项目内冻结的数据集快照及其成员顺序。
--         * record_reviews / record_review_history：逐条标注与覆盖前归档。
--           origin_project_id 有意不建 FK：删项目时按 D13 只把它清成 ''
--           （「来源已删」）而保留标注行，同 jobs.project_id 的 '' 哨兵（D14）。
--         * project_releases：项目结论（指标 + gates 快照 + verdict）。
--       不含早已存在的表/列；sqlite 侧的等价升级由 Store._init_schema 的
--       CREATE TABLE IF NOT EXISTS 完成，无需本文件。
-- 方言：PostgreSQL。全程 CREATE TABLE/INDEX IF NOT EXISTS，可重复执行（幂等）。
-- 执行库：.env 指定的 postgres 后端 —— localhost:5432 / kev_db / public。
-- 收尾：把 console_meta.schema_version 对齐到 9。
-- =============================================================================

BEGIN;

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

-- 版本对齐 v9（行缺失则补，存在则改；幂等）。
INSERT INTO console_meta (key, value) VALUES ('schema_version', '9')
  ON CONFLICT (key) DO NOTHING;
UPDATE console_meta SET value = '9' WHERE key = 'schema_version';

COMMIT;
