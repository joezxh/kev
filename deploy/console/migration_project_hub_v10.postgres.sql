-- =============================================================================
-- schema v10 增量迁移（PostgreSQL）：scenarios.distill_yaml_content
-- =============================================================================
-- 对应：SCHEMA_VERSION 9 -> 10（kev/console/db.py::_ddl 的 scenarios 表追加列，
--       _migrate 的 v10 分支：ALTER + _backfill_distill_yaml）。
-- 范围：只新增 scenarios.distill_yaml_content —— distill yaml 的可编辑内容存库，
--       DB 成为编辑真相源；既有的 distill_yaml（仓库相对路径）列保留做参考/回退
--       （read_distill_yaml 内容为空时回退读该路径文件）。
--       不含早已存在的表/列；sqlite 侧的等价升级由 Store._migrate 的 v10 分支
--       （ALTER TABLE ... ADD COLUMN）完成，无需本文件。
-- 回填：本文件只加列，不回填内容。存量库的 distill_yaml_content 由应用启动时的
--       seed_scenarios（内容为空且 distill_yaml 路径文件存在时读文件写入）或
--       _migrate 的 _backfill_distill_yaml 幂等补齐。
-- 方言：PostgreSQL。ADD COLUMN IF NOT EXISTS，可重复执行（幂等）。
-- 执行库：.env 指定的 postgres 后端 —— localhost:5432 / kev_db / public。
-- 收尾：把 console_meta.schema_version 对齐到 10。
-- =============================================================================

BEGIN;

ALTER TABLE scenarios ADD COLUMN IF NOT EXISTS distill_yaml_content TEXT;

COMMENT ON COLUMN scenarios.distill_yaml_content IS '该 yaml 的可编辑内容（DB 为编辑真相源；空 = 未导入/未编辑，read_distill_yaml 回退读 distill_yaml 路径文件）。';

-- 版本对齐 v10（行缺失则补，存在则改；幂等）。
INSERT INTO console_meta (key, value) VALUES ('schema_version', '10')
  ON CONFLICT (key) DO NOTHING;
UPDATE console_meta SET value = '10' WHERE key = 'schema_version';

COMMIT;
