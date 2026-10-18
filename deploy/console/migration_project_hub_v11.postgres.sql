-- =============================================================================
-- schema v11 增量迁移（PostgreSQL）：jobs.bundle_id
-- =============================================================================
-- 对应：SCHEMA_VERSION 10 -> 11（kev/console/db.py::_ddl 的 jobs 表追加列 +
--       jobs_bundle_idx，_migrate 的 v11 分支做幂等 ALTER）。
-- 范围：只新增 jobs.bundle_id —— 作业在提交那一刻显式声明它为哪个 bundle 而跑（D3）。
--       纯记账列：不参与闸门、不参与冻结检查、不选训练数据；空串 '' = 未归属，
--       与 jobs.project_id 的 '' legacy 哨兵（D14）同形。存量行升级后全为 ''。
--       不动 bundle 状态机、不动 bundle_members / artifact_versions 的写入路径。
-- 读侧：list_jobs / get_job 左连 bundles 取 bundles.name AS bundle_name，作业行
--       因此自带可读名字（§4.3）；这只影响 SELECT，不需要库侧变更。
-- 顺序：先 ALTER 再 CREATE INDEX —— 索引建在刚补出来的列上，反过来会撞
--       「column "bundle_id" of relation "jobs" does not exist」。应用侧的等价
--       保证是 Store._ensure_indexes：建表阶段一律不跑索引，迁移之后统一幂等补上
--       （v7 的 jobs_project_idx 当年写进建表脚本，使 schema_version=6 的存量库
--        在 Store() 启动时就崩，本机已踩过）。
-- 方言：PostgreSQL。ADD COLUMN IF NOT EXISTS / CREATE INDEX IF NOT EXISTS，
--       可重复执行（幂等）。sqlite 侧的等价升级由 Store._migrate 的 v11 分支完成，
--       无需本文件。
-- 执行库：.env 指定的 postgres 后端 —— localhost:5432 / kev_db / public。
-- 收尾：把 console_meta.schema_version 对齐到 11。
-- =============================================================================

BEGIN;

-- jobs：作业的 bundle 归属（D3）。空串是「未归属」，不是某个 bundle。
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS bundle_id TEXT NOT NULL DEFAULT '';

-- jobs_bundle_idx：从 bundle 反查为它跑过的作业（D4 的「快查」入口），按时间倒序。
CREATE INDEX IF NOT EXISTS jobs_bundle_idx ON jobs(bundle_id, created_at DESC);

COMMENT ON COLUMN jobs.bundle_id IS '作业在提交那一刻显式声明它为哪个 bundle 而跑（bundles.id，D3）；空串 = 未归属。纯记账：不参与闸门、不参与冻结检查、不选训练数据。';

-- 版本对齐 v11（行缺失则补，存在则改；幂等）。
INSERT INTO console_meta (key, value) VALUES ('schema_version', '11')
  ON CONFLICT (key) DO NOTHING;
UPDATE console_meta SET value = '11' WHERE key = 'schema_version';

COMMIT;
