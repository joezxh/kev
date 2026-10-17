-- =============================================================================
-- Kev 控制台库：表与字段注释（PostgreSQL 专用）
--
-- 依据 kev/console/db.py 的 _ddl()（SCHEMA_VERSION = 9）逐表逐列生成，
-- 与 deploy/console/schema.postgres.sql 的表结构一一对应。
--
-- 说明：
--   * 注释语义（COMMENT ON ...）是 PostgreSQL 特性，SQLite 无对应语法，
--     故本文件仅适用于 postgresql 后端（KEV_CONSOLE_DB_BACKEND=postgres）。
--   * 幂等：COMMENT ON 为「设置」语义，重复执行只会覆盖同名注释，不报错。
--   * 单独执行：psql -f deploy/console/comments.postgres.sql <db>
--     或在建表后作为收尾步骤运行；不依赖本仓库其它迁移的顺序。
-- =============================================================================

-- ---- console_meta：库级元数据（schema 版本等 key/value）----
COMMENT ON TABLE  console_meta      IS '库级元数据键值表；schema_version 记录当前结构版本（现为 9）。';
COMMENT ON COLUMN console_meta.key   IS '元数据键，如 schema_version。';
COMMENT ON COLUMN console_meta.value IS '元数据值（字符串）。';

-- ---- jobs：编排层的作业状态机（每条一次可恢复的流水线任务）----
COMMENT ON TABLE  jobs               IS '作业主表：编排层的状态机，每个作业归属一个项目（D14）。';
COMMENT ON COLUMN jobs.id            IS '作业主键，uuid4().hex。';
COMMENT ON COLUMN jobs.kind          IS '作业类型（如 data/train/eval/distill_daemon），决定提交表单 schema 与执行 stage。';
COMMENT ON COLUMN jobs.stage         IS '作业当前所处的流水线阶段。';
COMMENT ON COLUMN jobs.scenario      IS '场景 slug（对应 scenarios.slug），可为空串。';
COMMENT ON COLUMN jobs.title         IS '作业展示标题。';
COMMENT ON COLUMN jobs.status        IS '状态机状态：pending|queued|running|succeeded|failed|canceled|interrupted；终态由 db.py 的 TERMINAL 约束转移。';
COMMENT ON COLUMN jobs.request       IS '提交时的原始请求体（JSON 文本）。';
COMMENT ON COLUMN jobs.argv          IS '实际执行的命令行参数（JSON 数组文本）。';
COMMENT ON COLUMN jobs.env_overlay   IS '作业级环境变量覆盖（JSON 文本）。';
COMMENT ON COLUMN jobs.cwd           IS '执行工作目录。';
COMMENT ON COLUMN jobs.log_path      IS '作业日志文件路径（日志文件是真相源，events 表仅供 UI 分页）。';
COMMENT ON COLUMN jobs.artifacts_in  IS '输入产物 id 列表（JSON 数组文本）。';
COMMENT ON COLUMN jobs.artifacts_out IS '输出产物 id 列表（JSON 数组文本）。';
COMMENT ON COLUMN jobs.parent_id     IS '重试时指向被重试的原作业（jobs.id），首次执行为 NULL。';
COMMENT ON COLUMN jobs.attempt       IS '第几次尝试：重试由调用方递增，默认为 1。';
COMMENT ON COLUMN jobs.daemon_id     IS '仅 distill_daemon 阶段填的循环守护 id（uuid4().hex，32 字符），供 cancel 端点设回环取消标志；其它阶段为 NULL。';
COMMENT ON COLUMN jobs.template_id   IS '作业若由命名模板发起则记录其 id 以便追溯（job_templates.id），可空。';
COMMENT ON COLUMN jobs.project_id    IS '所属项目 id；空串是具名 legacy 哨兵（D14），永不出现在具体项目列表。';
COMMENT ON COLUMN jobs.exit_code     IS '进程退出码，未结束时为 NULL。';
COMMENT ON COLUMN jobs.error         IS '失败时的错误信息，可为 NULL。';
COMMENT ON COLUMN jobs.created_at    IS '创建时间（UTC ISO8601，秒精度）。';
COMMENT ON COLUMN jobs.started_at    IS '开始执行时间，未开始为 NULL。';
COMMENT ON COLUMN jobs.finished_at   IS '结束时间，未结束为 NULL。';

-- ---- artifacts：可变的产物指针（版本快照见 artifact_versions）----
COMMENT ON TABLE  artifacts           IS '产物登记表：kind+name 唯一，path 为可变指针（D2），历史版本另存 artifact_versions。';
COMMENT ON COLUMN artifacts.id         IS '产物主键。';
COMMENT ON COLUMN artifacts.kind       IS '产物类型（如 dataset/checkpoint/report）。';
COMMENT ON COLUMN artifacts.name       IS '产物名称，与 kind 组合唯一。';
COMMENT ON COLUMN artifacts.path       IS '产物当前所在路径（可变，指向最新一次写入）。';
COMMENT ON COLUMN artifacts.meta       IS '产物元数据（JSON 文本）。';
COMMENT ON COLUMN artifacts.bytes      IS '产物字节数，可空。';
COMMENT ON COLUMN artifacts.created_at IS '创建时间（UTC ISO8601）。';

-- ---- lineage：产物/作业之间的血缘边 ----
COMMENT ON TABLE  lineage           IS '血缘关系表：连接产物或作业的父子节点。';
COMMENT ON COLUMN lineage.parent     IS '父节点 id。';
COMMENT ON COLUMN lineage.child      IS '子节点 id。';
COMMENT ON COLUMN lineage.relation   IS '关系类型（如 derived_from/produced_by）。';
COMMENT ON COLUMN lineage.job_id     IS '建立该血缘的作业 id，可空。';

-- ---- events：供 UI 的可分页日志尾巴 ----
COMMENT ON TABLE  events          IS '作业事件流：仅供前端首屏回填与 Last-Event-ID 续传，真相源是日志文件。';
COMMENT ON COLUMN events.id        IS '自增主键（Postgres 为 BIGSERIAL）。';
COMMENT ON COLUMN events.job_id    IS '所属作业 id（jobs.id）。';
COMMENT ON COLUMN events.ts        IS '事件时间戳（UTC ISO8601）。';
COMMENT ON COLUMN events.stream    IS '输出流：stdout|stderr 等。';
COMMENT ON COLUMN events.line      IS '事件行文本。';

-- ---- api_keys：推理服务的 API 密钥 ----
COMMENT ON TABLE  api_keys            IS '对外 API 密钥表：仅存哈希，明文不落库。';
COMMENT ON COLUMN api_keys.id          IS '密钥主键。';
COMMENT ON COLUMN api_keys.name        IS '密钥展示名。';
COMMENT ON COLUMN api_keys.key_hash    IS '密钥哈希，唯一；用于鉴权比对。';
COMMENT ON COLUMN api_keys.prefix      IS '密钥前缀（用于展示识别，非机密）。';
COMMENT ON COLUMN api_keys.active      IS '是否启用：1 启用，0 停用。';
COMMENT ON COLUMN api_keys.created_at  IS '创建时间（UTC ISO8601）。';
COMMENT ON COLUMN api_keys.revoked_at  IS '吊销时间，未吊销为 NULL。';

-- ---- usage_log：API 调用流水与用量 ----
COMMENT ON TABLE  usage_log                IS 'API 调用日志：按密钥与时间统计用量、延迟与错误。';
COMMENT ON COLUMN usage_log.id             IS '自增主键（Postgres 为 BIGSERIAL）。';
COMMENT ON COLUMN usage_log.key_id         IS '调用所用密钥 id（api_keys.id）。';
COMMENT ON COLUMN usage_log.endpoint       IS '被调用的端点路径。';
COMMENT ON COLUMN usage_log.method         IS 'HTTP 方法。';
COMMENT ON COLUMN usage_log.status         IS 'HTTP 响应状态码。';
COMMENT ON COLUMN usage_log.input_tokens   IS '输入 token 数，默认 0。';
COMMENT ON COLUMN usage_log.output_tokens  IS '输出 token 数，默认 0。';
COMMENT ON COLUMN usage_log.latency_ms     IS '本次调用延迟（毫秒）。';
COMMENT ON COLUMN usage_log.ts             IS '调用时间戳（UTC ISO8601）。';

-- ---- distill_providers：蒸馏数据生成的教师模型提供方 ----
COMMENT ON TABLE  distill_providers              IS '蒸馏（distill）教师模型提供方注册表。';
COMMENT ON COLUMN distill_providers.id           IS '提供方主键。';
COMMENT ON COLUMN distill_providers.name         IS '提供方可读名。';
COMMENT ON COLUMN distill_providers.base_url     IS 'API 基础地址。';
COMMENT ON COLUMN distill_providers.model        IS '使用的模型名。';
COMMENT ON COLUMN distill_providers.daily_limit  IS '每日 token 用量上限，默认 500000。';
COMMENT ON COLUMN distill_providers.key_count    IS '已登记密钥数量，默认 0。';
COMMENT ON COLUMN distill_providers.key_hints    IS '密钥提示（脱敏后）列表（JSON 数组文本），默认 []。';
COMMENT ON COLUMN distill_providers.active       IS '是否启用：1 启用，0 停用。';
COMMENT ON COLUMN distill_providers.created_at   IS '创建时间（UTC ISO8601）。';

-- ---- distill_usage：按 (provider, key, day) 记账的蒸馏用量 ----
COMMENT ON TABLE  distill_usage            IS '蒸馏用量台账：(provider_id, key_hash, day) 唯一，累计当日 token。';
COMMENT ON COLUMN distill_usage.id         IS '自增主键（Postgres 为 BIGSERIAL）。';
COMMENT ON COLUMN distill_usage.job_id     IS '产生该用量的作业 id（jobs.id）。';
COMMENT ON COLUMN distill_usage.provider_id IS '提供方 id（distill_providers.id）。';
COMMENT ON COLUMN distill_usage.key_hash   IS '所用密钥哈希。';
COMMENT ON COLUMN distill_usage.key_hint   IS '所用密钥的脱敏提示。';
COMMENT ON COLUMN distill_usage.model      IS '模型名。';
COMMENT ON COLUMN distill_usage.base_url   IS 'API 基础地址。';
COMMENT ON COLUMN distill_usage.day        IS '记账日（日期字符串），与 provider+key 组唯一键。';
COMMENT ON COLUMN distill_usage.tokens     IS '当日累计 token 数，默认 0。';
COMMENT ON COLUMN distill_usage.ts         IS '记录时间戳（UTC ISO8601）。';

-- ---- scenario_domains：场景所属业务域 ----
COMMENT ON TABLE  scenario_domains            IS '场景域字典表（医疗/金融/教育/科研/法律等）。';
COMMENT ON COLUMN scenario_domains.id         IS '域主键。';
COMMENT ON COLUMN scenario_domains.slug       IS '域 slug，唯一。';
COMMENT ON COLUMN scenario_domains.label_zh   IS '中文展示名。';
COMMENT ON COLUMN scenario_domains.label_en   IS '英文展示名。';
COMMENT ON COLUMN scenario_domains.sort       IS '展示排序，默认 0。';
COMMENT ON COLUMN scenario_domains.spec_dir   IS '该域由 docs/domains/<spec_dir>/specs 供数（seed_scenarios 据此认领/新建域行）；空串为手工建域、不参与导入。';
COMMENT ON COLUMN scenario_domains.created_at IS '创建时间（UTC ISO8601）。';

-- ---- scenarios：可编排的场景（决策任务模板）----
COMMENT ON TABLE  scenarios              IS '场景表：一行一个决策场景，spec 内容存 spec_json，历史见 scenario_spec_history。';
COMMENT ON COLUMN scenarios.id           IS '场景主键。';
COMMENT ON COLUMN scenarios.domain_id    IS '所属域 id（scenario_domains.id）。';
COMMENT ON COLUMN scenarios.slug         IS '场景 slug，唯一（jobs.scenario 引用它）。';
COMMENT ON COLUMN scenarios.label_zh     IS '中文展示名。';
COMMENT ON COLUMN scenarios.label_en     IS '英文展示名。';
COMMENT ON COLUMN scenarios.spec_path    IS 'spec 文件路径（仓库相对）；运行时以 spec_json 为准。';
COMMENT ON COLUMN scenarios.spec_json    IS '场景 spec 的当前内容（JSON 文本），运行时真相源；可空。';
COMMENT ON COLUMN scenarios.category     IS '场景分类，默认 medical。';
COMMENT ON COLUMN scenarios.track        IS '轨制（scenario_specs.derive_track 派生）：rule|distill|both|llm，空串未定。';
COMMENT ON COLUMN scenarios.generator_kind IS '生成器类型：engine（spec.generator 九件套）|script（legacy gen_<场景>.py）|空串。';
COMMENT ON COLUMN scenarios.distill_yaml IS '该场景的 EasyDistill 配置（仓库相对路径）或空串。';
COMMENT ON COLUMN scenarios.distill_yaml_content IS '该 yaml 的可编辑内容（DB 为编辑真相源；空 = 未导入/未编辑，read_distill_yaml 回退读 distill_yaml 路径文件）。';
COMMENT ON COLUMN scenarios.origin       IS '''domains'' 表示行由 docs/domains 种子导入维护；空串为手工建。';
COMMENT ON COLUMN scenarios.sort         IS '展示排序，默认 0。';
COMMENT ON COLUMN scenarios.created_at   IS '创建时间（UTC ISO8601）。';
COMMENT ON COLUMN scenarios.updated_at   IS '最后更新时间（UTC ISO8601）。';

-- ---- scenario_spec_history：场景 spec 的历史版本（覆盖前归档）----
COMMENT ON TABLE  scenario_spec_history            IS '场景 spec 历史版本：每次改动覆盖前归档一份。';
COMMENT ON COLUMN scenario_spec_history.id          IS '历史行主键。';
COMMENT ON COLUMN scenario_spec_history.scenario_id IS '场景 id（scenarios.id）。';
COMMENT ON COLUMN scenario_spec_history.spec_json   IS '该版本的 spec 内容（JSON 文本）。';
COMMENT ON COLUMN scenario_spec_history.created_at  IS '归档时间（UTC ISO8601）。';

-- ---- stage_param_specs：作业类型「提交表单」参数 schema（单一真相源）----
COMMENT ON TABLE  stage_param_specs            IS '作业类型参数 schema：落库后可经 API 修改，版本化；结构对齐前端 JobStagePage 的 FieldSpec。';
COMMENT ON COLUMN stage_param_specs.kind       IS '作业类型（主键），与 jobs.kind 对应。';
COMMENT ON COLUMN stage_param_specs.schema_json IS '参数 schema（JSON 文本），default 与各 StageSpec.build() 默认值一致。';
COMMENT ON COLUMN stage_param_specs.version    IS 'schema 版本号，默认 1。';
COMMENT ON COLUMN stage_param_specs.updated_at IS '最后更新时间（UTC ISO8601）。';

-- ---- stage_param_spec_history：参数 schema 的历史版本 ----
COMMENT ON TABLE  stage_param_spec_history             IS '参数 schema 历史版本：按 kind 归档每一次变更。';
COMMENT ON COLUMN stage_param_spec_history.id          IS '历史行主键。';
COMMENT ON COLUMN stage_param_spec_history.kind        IS '作业类型。';
COMMENT ON COLUMN stage_param_spec_history.schema_json IS '该版本的参数 schema（JSON 文本）。';
COMMENT ON COLUMN stage_param_spec_history.version     IS '该版本的版本号。';
COMMENT ON COLUMN stage_param_spec_history.created_at  IS '归档时间（UTC ISO8601）。';

-- ---- job_templates：命名作业模板（跨会话复用参数预设）----
COMMENT ON TABLE  job_templates            IS '命名作业模板：跨会话复用/编辑某类任务的参数预设。';
COMMENT ON COLUMN job_templates.id         IS '模板主键。';
COMMENT ON COLUMN job_templates.kind       IS '适用作业类型（jobs.kind）。';
COMMENT ON COLUMN job_templates.name       IS '模板名称。';
COMMENT ON COLUMN job_templates.scenario   IS '模板绑定的场景 slug，默认空串。';
COMMENT ON COLUMN job_templates.params     IS '参数预设（JSON 文本），默认 {}。';
COMMENT ON COLUMN job_templates.created_at IS '创建时间（UTC ISO8601）。';
COMMENT ON COLUMN job_templates.updated_at IS '最后更新时间（UTC ISO8601）。';

-- ---- projects：项目（ch6 管理面的流水线根）----
COMMENT ON TABLE  projects                     IS '项目表：一切作业/产物/发布的归属根（ch6 管理面）。';
COMMENT ON COLUMN projects.id                  IS '项目主键。';
COMMENT ON COLUMN projects.slug                IS '项目 slug，唯一。';
COMMENT ON COLUMN projects.name                IS '项目展示名。';
COMMENT ON COLUMN projects.description         IS '项目描述，默认空串。';
COMMENT ON COLUMN projects.status              IS '项目状态，默认 active（如 active|archived）。';
COMMENT ON COLUMN projects.scenario            IS '项目主场景 slug，默认空串。';
COMMENT ON COLUMN projects.goal                IS '项目目标描述，默认空串。';
COMMENT ON COLUMN projects.archived_at         IS '归档时间，未归档为 NULL。';
COMMENT ON COLUMN projects.freeze_min_records  IS '冻结快照所需的最小记录数，默认 300。';
COMMENT ON COLUMN projects.freeze_min_review_ratio IS '冻结快照所需的最小标注覆盖率，默认 0.10。';
COMMENT ON COLUMN projects.created_at          IS '创建时间（UTC ISO8601）。';
COMMENT ON COLUMN projects.updated_at          IS '最后更新时间（UTC ISO8601）。';

-- ---- project_members：项目成员与角色 ----
COMMENT ON TABLE  project_members            IS '项目成员：(project_id, email) 唯一，含角色与邀请状态。';
COMMENT ON COLUMN project_members.id         IS '成员行主键。';
COMMENT ON COLUMN project_members.project_id IS '项目 id（projects.id）。';
COMMENT ON COLUMN project_members.email      IS '成员邮箱。';
COMMENT ON COLUMN project_members.name       IS '成员展示名，默认空串。';
COMMENT ON COLUMN project_members.role       IS '角色，默认 member（如 owner|member）。';
COMMENT ON COLUMN project_members.status     IS '成员状态，默认 invited（如 invited|active）。';
COMMENT ON COLUMN project_members.created_at IS '创建时间（UTC ISO8601）。';

-- ---- project_quota：项目配额与用量（每项目一行）----
COMMENT ON TABLE  project_quota                     IS '项目资源配额与已用量：主键即 project_id，一项目一行。';
COMMENT ON COLUMN project_quota.project_id           IS '项目 id（projects.id），主键。';
COMMENT ON COLUMN project_quota.training_hours_limit IS '训练机时上限，0 表示不限。';
COMMENT ON COLUMN project_quota.training_hours_used  IS '已用训练机时。';
COMMENT ON COLUMN project_quota.gpu_limit            IS 'GPU 数量上限，0 表示不限。';
COMMENT ON COLUMN project_quota.api_calls_limit      IS 'API 调用次数上限，0 表示不限。';
COMMENT ON COLUMN project_quota.api_calls_used       IS '已用 API 调用次数。';
COMMENT ON COLUMN project_quota.storage_gb_limit     IS '存储上限（GB），0 表示不限。';
COMMENT ON COLUMN project_quota.storage_gb_used      IS '已用存储（GB）。';
COMMENT ON COLUMN project_quota.updated_at           IS '最后更新时间（UTC ISO8601）。';

-- ---- webhooks：项目事件回调 ----
COMMENT ON TABLE  webhooks                   IS '项目 Webhook：向外部 URL 推送事件，含签名密钥与最近投递状态。';
COMMENT ON COLUMN webhooks.id                IS 'Webhook 主键。';
COMMENT ON COLUMN webhooks.project_id        IS '项目 id（projects.id）。';
COMMENT ON COLUMN webhooks.url               IS '回调 URL。';
COMMENT ON COLUMN webhooks.events            IS '订阅事件类型列表（JSON 数组文本），默认 []。';
COMMENT ON COLUMN webhooks.secret            IS '签名密钥，默认空串。';
COMMENT ON COLUMN webhooks.active            IS '是否启用：1 启用，0 停用。';
COMMENT ON COLUMN webhooks.last_status       IS '最近一次投递的 HTTP 状态码，未投递为 NULL。';
COMMENT ON COLUMN webhooks.last_delivered_at IS '最近一次投递时间，未投递为 NULL。';
COMMENT ON COLUMN webhooks.created_at        IS '创建时间（UTC ISO8601）。';

-- ---- invoices：项目账单 ----
COMMENT ON TABLE  invoices             IS '项目账单：按 period 记账，含金额、状态与明细行。';
COMMENT ON COLUMN invoices.id          IS '账单主键。';
COMMENT ON COLUMN invoices.project_id  IS '项目 id（projects.id）。';
COMMENT ON COLUMN invoices.period      IS '账期（日期字符串）。';
COMMENT ON COLUMN invoices.amount      IS '账单金额。';
COMMENT ON COLUMN invoices.currency    IS '币种，默认 USD。';
COMMENT ON COLUMN invoices.status      IS '账单状态，默认 open（如 open|paid）。';
COMMENT ON COLUMN invoices.due_at      IS '到期时间，可为 NULL。';
COMMENT ON COLUMN invoices.issued_at   IS '出账时间（UTC ISO8601）。';
COMMENT ON COLUMN invoices.line_items  IS '账单项明细（JSON 数组文本），默认 []。';

-- ---- artifact_versions：产物的不可变版本快照（v9 数据策展）----
COMMENT ON TABLE  artifact_versions            IS '产物不可变版本快照：登记即算 sha256/records。artifact_id 有意不建指向 artifacts 的 FK（artifacts 是可变指针，D2）。';
COMMENT ON COLUMN artifact_versions.id         IS '版本行主键。';
COMMENT ON COLUMN artifact_versions.artifact_id IS '所属产物 id（逻辑对应 artifacts.id，不建 FK）。';
COMMENT ON COLUMN artifact_versions.seq        IS '同一产物内的版本序号，与 artifact_id 组唯一。';
COMMENT ON COLUMN artifact_versions.job_id     IS '产出该版本的作业 id（jobs.id）。';
COMMENT ON COLUMN artifact_versions.path       IS '该版本的落盘路径。';
COMMENT ON COLUMN artifact_versions.sha256     IS '内容的 sha256 摘要。';
COMMENT ON COLUMN artifact_versions.records    IS '记录条数（数据集类产物），可空。';
COMMENT ON COLUMN artifact_versions.bytes      IS '字节数，可空。';
COMMENT ON COLUMN artifact_versions.meta       IS '版本元数据（JSON 文本），默认 {}。';
COMMENT ON COLUMN artifact_versions.spec_sha256 IS '生成本版本所用场景 spec 的 sha256，可空。';
COMMENT ON COLUMN artifact_versions.created_at IS '创建时间（UTC ISO8601）。';

-- ---- bundles：冻结的数据快照（一组产物版本 + 冻结检查）----
COMMENT ON TABLE  bundles                   IS '冻结快照 bundle：项目内 name 唯一，汇总成员版本与冻结检查结果。';
COMMENT ON COLUMN bundles.id                IS 'bundle 主键。';
COMMENT ON COLUMN bundles.project_id        IS '项目 id（projects.id）。';
COMMENT ON COLUMN bundles.name              IS 'bundle 名称，与 project_id 组唯一。';
COMMENT ON COLUMN bundles.artifact_id       IS 'bundle 代表的产物 id（逻辑对应 artifacts，不建 FK）。';
COMMENT ON COLUMN bundles.status            IS 'bundle 状态（如 draft|frozen）。';
COMMENT ON COLUMN bundles.sha256            IS 'bundle 内容摘要，冻结前可空。';
COMMENT ON COLUMN bundles.records           IS '记录总条数，可空。';
COMMENT ON COLUMN bundles.reviewed_records  IS '已标注记录数，可空。';
COMMENT ON COLUMN bundles.reviewed_native   IS '本项目原生标注数，可空。';
COMMENT ON COLUMN bundles.reviewed_inherited IS '跨轮继承的标注数，可空。';
COMMENT ON COLUMN bundles.review_ratio      IS '标注覆盖率（reviewed/records），可空。';
COMMENT ON COLUMN bundles.freeze_checks     IS '冻结检查项结果（JSON 数组文本），默认 []。';
COMMENT ON COLUMN bundles.manifest_path     IS '清单文件路径，可空。';
COMMENT ON COLUMN bundles.manifest_sha256   IS '清单文件摘要，可空。';
COMMENT ON COLUMN bundles.frozen_at         IS '冻结时间，未冻结为 NULL。';
COMMENT ON COLUMN bundles.note              IS '备注，默认空串。';
COMMENT ON COLUMN bundles.created_at        IS '创建时间（UTC ISO8601）。';
COMMENT ON COLUMN bundles.updated_at        IS '最后更新时间（UTC ISO8601）。';

-- ---- bundle_members：bundle 与其成员产物版本的关联（含裁剪统计）----
COMMENT ON TABLE  bundle_members               IS 'bundle 成员：关联 bundles 与 artifact_versions，记录该步操作的取舍统计。';
COMMENT ON COLUMN bundle_members.bundle_id     IS 'bundle id（bundles.id）。';
COMMENT ON COLUMN bundle_members.version_id    IS '成员产物版本 id（artifact_versions.id）。';
COMMENT ON COLUMN bundle_members.op            IS '该成员对 bundle 的操作类型（如 add|filter）。';
COMMENT ON COLUMN bundle_members.ord           IS '成员在 bundle 内的顺序。';
COMMENT ON COLUMN bundle_members.records_in    IS '进入该步的记录数，可空。';
COMMENT ON COLUMN bundle_members.records_kept  IS '该步保留的记录数，可空。';
COMMENT ON COLUMN bundle_members.records_dropped IS '该步丢弃的记录数，可空。';
COMMENT ON COLUMN bundle_members.drop_reasons  IS '丢弃原因计数（JSON 文本），默认 {}。';

-- ---- record_reviews：逐条标注（作用域是场景，供下一轮继承）----
COMMENT ON TABLE  record_reviews                 IS '逐条标注记录：按 (scenario, fingerprint) 唯一。origin_project_id 有意不建 FK，删项目时按 D13 将其清为空串、保留标注供跨轮继承。';
COMMENT ON COLUMN record_reviews.id              IS '标注行主键。';
COMMENT ON COLUMN record_reviews.scenario        IS '场景 slug（标注作用域）。';
COMMENT ON COLUMN record_reviews.origin_project_id IS '来源项目 id；空串为「来源已删」哨兵（不建 FK，见 D13/D14）。';
COMMENT ON COLUMN record_reviews.fingerprint     IS '被标注记录的指纹（内容哈希），与 scenario 组唯一。';
COMMENT ON COLUMN record_reviews.record_id       IS '原始记录 id，可空。';
COMMENT ON COLUMN record_reviews.verdict         IS '标注结论（如 accept|reject|edit）。';
COMMENT ON COLUMN record_reviews.patch           IS '修订补丁（JSON 文本），可空。';
COMMENT ON COLUMN record_reviews.fingerprint_after IS '应用 patch 后的新指纹，可空。';
COMMENT ON COLUMN record_reviews.labels          IS '标签列表（JSON 数组文本），默认 []。';
COMMENT ON COLUMN record_reviews.note            IS '标注备注，默认空串。';
COMMENT ON COLUMN record_reviews.reviewer        IS '标注人，默认空串。';
COMMENT ON COLUMN record_reviews.source_version_id IS '标注所依据的产物版本 id（artifact_versions.id），可空。';
COMMENT ON COLUMN record_reviews.created_at      IS '创建时间（UTC ISO8601）。';
COMMENT ON COLUMN record_reviews.updated_at      IS '最后更新时间（UTC ISO8601）。';

-- ---- record_review_history：标注覆盖前的历史归档 ----
COMMENT ON TABLE  record_review_history           IS '标注历史：每条 record_review 覆盖前归档一份（同 scenario_spec_history 写法）。';
COMMENT ON COLUMN record_review_history.id        IS '历史行主键。';
COMMENT ON COLUMN record_review_history.review_id IS '标注行 id（record_reviews.id）。';
COMMENT ON COLUMN record_review_history.verdict   IS '归档时的结论。';
COMMENT ON COLUMN record_review_history.patch     IS '归档时的补丁，可空。';
COMMENT ON COLUMN record_review_history.labels    IS '归档时的标签（JSON 数组文本），默认 []。';
COMMENT ON COLUMN record_review_history.note      IS '归档时的备注，默认空串。';
COMMENT ON COLUMN record_review_history.reviewer  IS '归档时的标注人，默认空串。';
COMMENT ON COLUMN record_review_history.created_at IS '归档时间（UTC ISO8601）。';

-- ---- project_releases：项目结论发布（训练/评测产物的快照与门禁）----
COMMENT ON TABLE  project_releases                 IS '项目发布：冻结 bundle + 训练/评测产物的结论快照，(project_id, name) 唯一。';
COMMENT ON COLUMN project_releases.id              IS '发布行主键。';
COMMENT ON COLUMN project_releases.project_id      IS '项目 id（projects.id）。';
COMMENT ON COLUMN project_releases.name            IS '发布名称，与 project_id 组唯一。';
COMMENT ON COLUMN project_releases.bundle_id       IS '关联的冻结 bundle id（bundles.id），可空。';
COMMENT ON COLUMN project_releases.bundle_sha256   IS 'bundle 内容摘要，可空。';
COMMENT ON COLUMN project_releases.train_job_id    IS '产出模型的训练作业 id（jobs.id），可空。';
COMMENT ON COLUMN project_releases.run_artifact    IS 'run 阶段产物引用，可空。';
COMMENT ON COLUMN project_releases.eval_artifact   IS '评测产物引用，可空。';
COMMENT ON COLUMN project_releases.comparison_artifact  IS '对比产物引用，可空。';
COMMENT ON COLUMN project_releases.regression_artifact  IS '回归产物引用，可空。';
COMMENT ON COLUMN project_releases.calibration_artifact IS '校准产物引用，可空。';
COMMENT ON COLUMN project_releases.metrics         IS '发布指标快照（JSON 文本），默认 {}。';
COMMENT ON COLUMN project_releases.gates_snapshot  IS '发布门禁检查结果（JSON 数组文本），默认 []。';
COMMENT ON COLUMN project_releases.verdict         IS '发布结论，默认 candidate（如 candidate|released|rejected）。';
COMMENT ON COLUMN project_releases.note            IS '备注，默认空串。';
COMMENT ON COLUMN project_releases.created_at      IS '创建时间（UTC ISO8601）。';
