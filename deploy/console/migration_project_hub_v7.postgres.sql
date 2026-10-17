-- =============================================================================
-- Project Hub Foundation —— schema v7 增量迁移（PostgreSQL）
-- =============================================================================
-- 对应：SCHEMA_VERSION 6 -> 7（kev/console/db.py::_migrate 的 `version < 7` 分支
--       与 _ddl() 中 jobs / projects 的最新形状）。
-- 范围：只包含本轮「Project Hub Foundation」相对上一版 schema 新增/变更的结构——
--         * jobs.project_id 列 + jobs_project_idx 索引（D14：每个作业归属一个项目；
--           '' 是具名 legacy 哨兵）。
--         * projects 表升级为「流水线根」新增的 6 列：status / scenario / goal /
--           archived_at / freeze_min_records / freeze_min_review_ratio（D1、F1-F4 freeze 策略）。
--       不含早已存在的表/列，也不含 project_events / list_project_artifacts /
--       project_summary 这类纯读取方法（它们不改动 schema）。
-- 方言：PostgreSQL。全程 IF NOT EXISTS + 默认值回填，可重复执行（幂等）；既有行
--       （例如已存在的 project）会被 NOT NULL 列的 DEFAULT 自动补齐。
-- 执行库：.env 指定的 postgres 后端 —— localhost:5432 / kev_db / public。
-- 收尾：把 console_meta.schema_version 对齐到 7。
-- =============================================================================

BEGIN;

-- jobs：作业归属项目（D14）。空串 '' 是 legacy 哨兵，不是某个项目。
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS project_id TEXT NOT NULL DEFAULT '';

-- jobs_project_idx：按项目 + 时间倒序读某项目全部作业（项目详情页/汇总走这条）。
CREATE INDEX IF NOT EXISTS jobs_project_idx ON jobs(project_id, created_at DESC);

-- projects：从「账单根」升级为「流水线根」的 6 列，与 _ddl() 的类型/默认值逐条一致。
ALTER TABLE projects ADD COLUMN IF NOT EXISTS status                  TEXT    NOT NULL DEFAULT 'active';
ALTER TABLE projects ADD COLUMN IF NOT EXISTS scenario                TEXT    NOT NULL DEFAULT '';
ALTER TABLE projects ADD COLUMN IF NOT EXISTS goal                    TEXT    NOT NULL DEFAULT '';
ALTER TABLE projects ADD COLUMN IF NOT EXISTS archived_at             TEXT;
ALTER TABLE projects ADD COLUMN IF NOT EXISTS freeze_min_records      INTEGER NOT NULL DEFAULT 300;
ALTER TABLE projects ADD COLUMN IF NOT EXISTS freeze_min_review_ratio DOUBLE PRECISION NOT NULL DEFAULT 0.10;

-- 版本对齐 v7（行缺失则补，存在则改；幂等）。
INSERT INTO console_meta (key, value) VALUES ('schema_version', '7')
  ON CONFLICT (key) DO NOTHING;
UPDATE console_meta SET value = '7' WHERE key = 'schema_version';

COMMIT;
