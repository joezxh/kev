-- =============================================================================
-- console 数据库 · 表与字段注释（备注）脚本
-- 适用后端：PostgreSQL（COMMENT ON 为 PostgreSQL 语法；SQLite 不支持列/表注释）
-- 来源：kev/console/db.py 的 _ddl()（SCHEMA_VERSION = 6，共 20 张表）
-- 用法：在已建表（见 schema.full.postgres.sql）之后执行本文件即可补全注释。
-- =============================================================================

-- ----------------------------- console_meta --------------------------------
COMMENT ON TABLE  console_meta            IS '控制台元信息键值表（如 schema_version 等全局配置）';
COMMENT ON COLUMN console_meta.key        IS '元信息键（如 schema_version）';
COMMENT ON COLUMN console_meta.value      IS '元信息值（文本存储）';

-- -------------------------------- jobs --------------------------------------
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

-- ------------------------------ artifacts -----------------------------------
COMMENT ON TABLE  artifacts               IS '产物表：作业产生的文件、数据集、模型等产物';
COMMENT ON COLUMN artifacts.id            IS '产物唯一 ID';
COMMENT ON COLUMN artifacts.kind          IS '产物类型（如 dataset / model / log 等）';
COMMENT ON COLUMN artifacts.name          IS '产物名称';
COMMENT ON COLUMN artifacts.path          IS '产物存储路径';
COMMENT ON COLUMN artifacts.meta          IS '产物元数据（JSON 文本）';
COMMENT ON COLUMN artifacts.bytes         IS '产物字节大小（可空）';
COMMENT ON COLUMN artifacts.created_at    IS '创建时间（ISO8601 文本）';

-- ------------------------------- lineage -----------------------------------
COMMENT ON TABLE  lineage                 IS '血缘表：记录产物与作业之间的依赖/衍生关系';
COMMENT ON COLUMN lineage.parent          IS '父节点标识（如产物 ID 或作业 ID）';
COMMENT ON COLUMN lineage.child           IS '子节点标识';
COMMENT ON COLUMN lineage.relation        IS '关系类型（如 derived_from / produced_by 等）';
COMMENT ON COLUMN lineage.job_id          IS '关联作业 ID（可空）';

-- -------------------------------- events ------------------------------------
COMMENT ON TABLE  events                  IS '作业事件/日志流：逐行记录作业的标准输出/错误等日志';
COMMENT ON COLUMN events.id               IS '自增主键';
COMMENT ON COLUMN events.job_id           IS '关联作业 ID';
COMMENT ON COLUMN events.ts               IS '日志行时间戳（ISO8601 文本）';
COMMENT ON COLUMN events.stream           IS '日志流（如 stdout / stderr）';
COMMENT ON COLUMN events.line             IS '单条日志行文本';

-- ------------------------------- api_keys -----------------------------------
COMMENT ON TABLE  api_keys                IS 'API 密钥表：对外服务的访问密钥管理';
COMMENT ON COLUMN api_keys.id             IS '密钥唯一 ID';
COMMENT ON COLUMN api_keys.name           IS '密钥名称（便于识别）';
COMMENT ON COLUMN api_keys.key_hash       IS '密钥哈希值（唯一索引，不存明文）';
COMMENT ON COLUMN api_keys.prefix         IS '密钥前缀（用于展示与定位，不暴露完整密钥）';
COMMENT ON COLUMN api_keys.active         IS '是否启用（1=启用，0=禁用）';
COMMENT ON COLUMN api_keys.created_at     IS '创建时间（ISO8601 文本）';
COMMENT ON COLUMN api_keys.revoked_at    IS '撤销时间（ISO8601 文本，可空）';

-- ------------------------------- usage_log ----------------------------------
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

-- --------------------------- distill_providers ------------------------------
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

-- ----------------------------- distill_usage --------------------------------
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

-- --------------------------- scenario_domains -------------------------------
COMMENT ON TABLE  scenario_domains        IS '场景领域表：场景的顶层分类（如 medical）';
COMMENT ON COLUMN scenario_domains.id      IS '领域唯一 ID';
COMMENT ON COLUMN scenario_domains.slug   IS '领域唯一标识（唯一）';
COMMENT ON COLUMN scenario_domains.label_zh IS '领域中文名';
COMMENT ON COLUMN scenario_domains.label_en IS '领域英文名';
COMMENT ON COLUMN scenario_domains.sort    IS '展示排序';
COMMENT ON COLUMN scenario_domains.created_at IS '创建时间（ISO8601 文本）';

-- ------------------------------- scenarios ----------------------------------
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

-- ------------------------- scenario_spec_history ---------------------------
COMMENT ON TABLE  scenario_spec_history   IS '场景规格变更历史：每次 spec 变更的快照';
COMMENT ON COLUMN scenario_spec_history.id         IS '历史记录唯一 ID';
COMMENT ON COLUMN scenario_spec_history.scenario_id IS '关联场景 ID';
COMMENT ON COLUMN scenario_spec_history.spec_json  IS '历史规格快照（JSON 文本）';
COMMENT ON COLUMN scenario_spec_history.created_at IS '快照创建时间（ISO8601 文本）';

-- --------------------------- stage_param_specs -----------------------------
COMMENT ON TABLE  stage_param_specs        IS '作业阶段参数 schema（单一真相源，可经 API 版本化修改）';
COMMENT ON COLUMN stage_param_specs.kind       IS '作业类型（主键，与 jobs.kind 对齐）';
COMMENT ON COLUMN stage_param_specs.schema_json IS '参数 schema 定义（JSON 文本，对齐前端 FieldSpec）';
COMMENT ON COLUMN stage_param_specs.version    IS 'schema 版本号';
COMMENT ON COLUMN stage_param_specs.updated_at IS '更新时间（ISO8601 文本）';

-- ----------------------- stage_param_spec_history --------------------------
COMMENT ON TABLE  stage_param_spec_history IS '参数 schema 变更历史：每次 schema 变更的快照';
COMMENT ON COLUMN stage_param_spec_history.id          IS '历史记录唯一 ID';
COMMENT ON COLUMN stage_param_spec_history.kind        IS '作业类型';
COMMENT ON COLUMN stage_param_spec_history.schema_json IS '历史 schema 快照（JSON 文本）';
COMMENT ON COLUMN stage_param_spec_history.version     IS '快照对应版本号';
COMMENT ON COLUMN stage_param_spec_history.created_at IS '快照创建时间（ISO8601 文本）';

-- ----------------------------- job_templates -------------------------------
COMMENT ON TABLE  job_templates           IS '作业模板：跨会话复用/编辑某类任务的参数预设';
COMMENT ON COLUMN job_templates.id         IS '模板唯一 ID';
COMMENT ON COLUMN job_templates.kind       IS '作业类型';
COMMENT ON COLUMN job_templates.name       IS '模板名称';
COMMENT ON COLUMN job_templates.scenario   IS '关联场景 slug（默认空）';
COMMENT ON COLUMN job_templates.params     IS '预设参数（JSON 文本，默认 {}）';
COMMENT ON COLUMN job_templates.created_at IS '创建时间（ISO8601 文本）';
COMMENT ON COLUMN job_templates.updated_at IS '更新时间（ISO8601 文本）';

-- -------------------------------- projects ----------------------------------
COMMENT ON TABLE  projects                IS '项目表（管理面 ch6）：多租户项目根实体';
COMMENT ON COLUMN projects.id             IS '项目唯一 ID';
COMMENT ON COLUMN projects.slug           IS '项目唯一标识（唯一）';
COMMENT ON COLUMN projects.name           IS '项目名称';
COMMENT ON COLUMN projects.description    IS '项目描述';
COMMENT ON COLUMN projects.created_at     IS '创建时间（ISO8601 文本）';
COMMENT ON COLUMN projects.updated_at     IS '更新时间（ISO8601 文本）';

-- ---------------------------- project_members ------------------------------
COMMENT ON TABLE  project_members         IS '项目成员表：项目与成员的关联及角色';
COMMENT ON COLUMN project_members.id       IS '成员记录唯一 ID';
COMMENT ON COLUMN project_members.project_id IS '关联项目 ID';
COMMENT ON COLUMN project_members.email    IS '成员邮箱';
COMMENT ON COLUMN project_members.name     IS '成员名称';
COMMENT ON COLUMN project_members.role     IS '成员角色（默认 member）';
COMMENT ON COLUMN project_members.status   IS '成员状态（默认 invited）';
COMMENT ON COLUMN project_members.created_at IS '创建时间（ISO8601 文本）';

-- ----------------------------- project_quota -------------------------------
COMMENT ON TABLE  project_quota           IS '项目配额表：训练时长、GPU、API 调用、存储等限额';
COMMENT ON COLUMN project_quota.project_id          IS '关联项目 ID（主键）';
COMMENT ON COLUMN project_quota.training_hours_limit IS '训练时长上限（小时）';
COMMENT ON COLUMN project_quota.training_hours_used  IS '训练时长已用（小时）';
COMMENT ON COLUMN project_quota.gpu_limit            IS 'GPU 数量上限';
COMMENT ON COLUMN project_quota.api_calls_limit      IS 'API 调用次数上限';
COMMENT ON COLUMN project_quota.api_calls_used       IS 'API 调用已用次数';
COMMENT ON COLUMN project_quota.storage_gb_limit    IS '存储上限（GB）';
COMMENT ON COLUMN project_quota.storage_gb_used     IS '存储已用（GB）';
COMMENT ON COLUMN project_quota.updated_at          IS '更新时间（ISO8601 文本）';

-- -------------------------------- webhooks ---------------------------------
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

-- -------------------------------- invoices ---------------------------------
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
