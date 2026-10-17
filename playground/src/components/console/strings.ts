// 控制台文案。形状沿用 src/lib/i18n.tsx 的 {en, zh}，由 app/layout 注入全局 dict，
// 保持 t() 单一入口 —— 不引入第二套 i18n。
//
// 医疗场景默认中文优先（docs/medical 全中文），但英文也必须完整：模型卡与 Hub 上
// 的医疗模型发布走英文。
export const CONSOLE_STRINGS = {
  "console.title": { en: "fine-tune console", zh: "微调控制台" },
  "console.subtitle": {
    en: "Eight tabs, eighteen job kinds, one shared dataset. Every form shows the exact command it will run.",
    zh: "八个标签页、十八种作业、共用一份数据。每个表单都显示它将执行的完整命令。",
  },
  "console.back": { en: "← kev", zh: "← kev" },
  "console.nav.overview": { en: "Overview", zh: "总览" },
  "console.nav.data": { en: "1 · Data", zh: "1 · 数据" },
  "console.nav.train": { en: "2 · Train", zh: "2 · 训练" },
  "console.nav.eval": { en: "3 · Evaluate", zh: "3 · 评测" },
  "console.nav.image": { en: "4 · Image", zh: "4 · 镜像" },
  "console.nav.deploy": { en: "5 · Deploy", zh: "5 · 部署" },
  "console.nav.apikeys": { en: "6 · API Keys", zh: "6 · API Keys" },
  "console.nav.usage": { en: "7 · Usage", zh: "7 · 用量" },
  "console.nav.distill": { en: "8 · Distill config", zh: "8 · 蒸馏配置" },
  "console.nav.scenarios": { en: "9 · Scenarios", zh: "9 · 场景管理" },
  "console.nav.stageschemas": { en: "Stage schema", zh: "作业表单配置" },
  "console.nav.studio": { en: "Studio", zh: "Studio" },

  "console.apikeys.name": { en: "Name", zh: "名称" },
  "console.apikeys.create": { en: "Create key", zh: "创建 key" },
  "console.apikeys.createHint": { en: "create one first", zh: "先去创建一个" },
  "console.apikeys.use": { en: "API key", zh: "API key" },
  "console.apikeys.shownOnce": { en: "Key created. Its id is the credential (no secret to copy):", zh: "key 已创建。其 id 即凭据（无需复制任何密钥）：" },
  "console.apikeys.copyNow": { en: "Select it in the playground dropdown to use it; the server validates the id.", zh: "在首页下拉中选中即可使用；服务端按 id 校验存在且启用。" },
  "console.apikeys.status": { en: "Status", zh: "状态" },
  "console.apikeys.active": { en: "active", zh: "启用" },
  "console.apikeys.revoked": { en: "revoked", zh: "已撤销" },
  "console.apikeys.calls": { en: "calls", zh: "调用" },
  "console.apikeys.lastUsed": { en: "last used", zh: "最后调用" },
  "console.apikeys.revoke": { en: "Revoke", zh: "撤销" },
  "console.apikeys.reactivate": { en: "Re-enable", zh: "重新启用" },
  "console.apikeys.total": { en: "total {n}", zh: "共 {n} 条" },
  "console.apikeys.pageOf": { en: "page {page} / {total}", zh: "第 {page} / {total} 页" },
  "console.apikeys.prev": { en: "Prev", zh: "上一页" },
  "console.apikeys.next": { en: "Next", zh: "下一页" },
  "console.apikeys.pageSize": { en: "Rows per page", zh: "每页" },
  "console.apikeys.goTo": { en: "Go to", zh: "跳至" },
  "console.apikeys.pageUnit": { en: "page", zh: "页" },
  "console.apikeys.go": { en: "Go", zh: "跳转" },

  "console.usage.title": { en: "Usage", zh: "用量" },
  "console.usage.kev": { en: "Kev core interface usage", zh: "Kev 核心接口用量" },
  "console.usage.distill": { en: "Distillation 3rd-party usage", zh: "蒸馏第三方模型用量" },

  "console.distill.created": { en: "provider saved (keys stored server-side only)", zh: "配置已保存（密钥仅存于服务端）" },
  "console.distill.edit": { en: "Edit", zh: "编辑" },
  "console.distill.save": { en: "Save changes", zh: "保存修改" },
  "console.distill.keepKeys": { en: "leave keys blank to keep the existing ones", zh: "留空则保留现有密钥" },
  "console.distill.keys": { en: "API keys (one per line)", zh: "API Key（每行一个）" },
  "console.distill.create": { en: "Save config", zh: "保存配置" },
  "console.distill.deactivate": { en: "Deactivate", zh: "停用" },

  "console.argv.preview": { en: "Command preview", zh: "将要执行的命令" },
  "console.argv.copy": { en: "Copy", zh: "复制" },
  "console.argv.hint": {
    en: "Every field maps to a flag below. Nothing is hidden — the runbook's value is that you can read the command.",
    zh: "表单每个字段都对应下面一个开关。没有任何隐藏 —— 执行手册的价值就在于命令可读。",
  },

  "console.method": { en: "Fine-tune method", zh: "微调方式" },
  "console.method.a1": { en: "A1 · LoRA warm start (recommended)", zh: "A1 · LoRA 热启动（推荐起步）" },
  "console.method.a2": { en: "A2 · LoRA from bare base", zh: "A2 · LoRA 从裸基座" },
  "console.method.b": { en: "B · full-weight (24GB+ or multi-GPU)", zh: "B · 全参数（需 24GB+ 或多卡）" },
  "console.train.data": { en: "Training partition", zh: "训练分区" },
  "console.train.monitor": { en: "Loss", zh: "损失曲线" },
  "console.train.metricsMissing": {
    en: "This run wrote no training_metrics.json (--stop_after exits early), so peak memory and gradient norms are unavailable.",
    zh: "本次运行没有写 training_metrics.json（--stop_after 早退会跳过），因此没有峰值显存与梯度范数。",
  },
  "console.train.risk08b": { en: "Known limits of the 0.8B track", zh: "0.8B 轨的已知限制" },
  "console.train.risk08bBody": {
    en: "Date arithmetic 0.35 (4B: 0.65) — which is why every spec here pre-computes dates into days_on_drug / length_of_stay_days / duration. Knowledge comes from the base (MMLU-Pro as low as 0.230), so it is not suited to ICD coding. Tool routing When2Call 0.133 is below chance — never use it to decide whether to consult a guideline. 0.8B also overconfident more easily, so hold mean_conf vs acc and confident_error_rate to a tighter line than 4B.",
    zh: "日期算术 0.35（4B 0.65）—— 所以本项目的 spec 一律把日期预计算成 days_on_drug / length_of_stay_days / duration。知识由基座决定（MMLU-Pro 低至 0.230），不适合病历编码。工具路由 When2Call 0.133 低于机会水平 —— 不要让它判断「是否需要翻阅指南」。0.8B 还更容易过度自信，mean_conf vs acc 与 confident_error_rate 要比 4B 卡得更严。",
  },

  "console.data.datasets": { en: "Datasets", zh: "数据集" },
  "console.data.import": { en: "Import JSONL", zh: "导入 JSONL" },
  "console.data.export": { en: "Export", zh: "导出" },
  "console.data.synthesize": { en: "Synthesize", zh: "合成" },
  "console.data.rareLabel": {
    en: "Under 5% — the trainer warns and the model learns that boundary poorly. Fix the generator's quota, do not dilute it by asking for more records.",
    zh: "占比低于 5% —— 训练器会告警，模型学不好这条边界。要调生成器配额，不要靠加 --n 稀释。",
  },
  "console.data.phiWarning": {
    en: "Possible patient identifier detected. Nothing was rewritten: de-identification happens upstream, before the generator, never here.",
    zh: "检测到可能的患者标识。未做任何改写 —— 脱敏在进入生成器之前完成，不在这里。",
  },

  // 数据作业种类（顶部切换菜单）：英文沿用代码标识，中文给出中文名。
  "console.data.kind.plan_size": { en: "plan_size", zh: "计划规模" },
  "console.data.kind.generate": { en: "generate", zh: "生成数据" },
  "console.data.kind.distill": { en: "distill", zh: "蒸馏" },
  "console.data.kind.distill_daemon": { en: "distill_daemon", zh: "蒸馏守护" },
  "console.data.kind.goldset": { en: "goldset", zh: "金标集" },
  "console.data.kind.split": { en: "split", zh: "划分" },
  "console.data.kind.precheck": { en: "precheck", zh: "预检" },
  "console.data.kind.make_examples": { en: "make_examples", zh: "生成范例" },

  "console.eval.gates": { en: "Acceptance gates", zh: "验收门槛" },
  "console.eval.allPass": { en: "all pass", zh: "全部通过" },
  "console.eval.blocked": { en: "{n} not passing", zh: "{n} 道未通过" },
  "console.eval.g4hint": {
    en: "A CI spanning 0 means the data is too thin or the gain too small. Better data ranks first — not more records, not other hyperparameters.",
    zh: "CI 含 0 说明数据太薄或增益太小。收益排序第 1 位是「更多更好的数据」，不是加量、也不是调超参。",
  },
  "console.eval.calibration": { en: "Temperature arms", zh: "温度四臂" },
  "console.eval.overconfident": {
    en: "mean_conf above acc means overconfident — the failure mode to watch on 0.8B.",
    zh: "mean_conf 高于 acc 就是过度自信 —— 0.8B 上要盯的失败模式。",
  },

  "console.image.build": { en: "Build image", zh: "构建镜像" },
  "console.image.list": { en: "Images", zh: "镜像" },
  "console.image.noBake": {
    en: "Weights are not baked in: medical models must never be published publicly, so the image resolves the checkpoint at run time.",
    zh: "权重不烘进镜像：医疗模型禁止公开发布，镜像在运行时解析 checkpoint。",
  },
  "console.deploy.endpoints": { en: "Endpoints", zh: "端点" },
  "console.deploy.smoke": { en: "Smoke test", zh: "冒烟测试" },
  "console.deploy.rollback": { en: "Roll back", zh: "回滚" },
  "console.deploy.priorWarning": {
    en: "Training prior is balanced; the real critical-value rate is 1-3%. Re-calibrate the cut-off on real traffic. The model advises, a human confirms.",
    zh: "训练先验是均衡的，线上危急值实际只占 1-3%。阈值须用真实流量重新标定。模型建议，人工确认。",
  },
  "console.deploy.modelAdvisory": {
    en: "This is the existing Q&A page; it already proxies to port 8008, so it talks to the newly deployed model with no extra wiring.",
    zh: "这是现有的问答页；它已经代理到 8008 端口，所以无需任何额外接线就能打到新部署的模型。",
  },

  "console.jobs.cancel": { en: "Cancel", zh: "取消" },
  "console.jobs.retry": { en: "Retry under a new name", zh: "换名重试" },
  "console.jobs.detail": { en: "Detail", zh: "详情" },
  "console.jobs.artifacts": { en: "Artifacts and lineage", zh: "产物与血缘" },
  "console.jobs.interrupted": {
    en: "The orchestrator restarted while this job was live. Retrying continues under a new name; the old directory is kept for audit.",
    zh: "编排服务在此作业运行中重启过。重试会换一个新名字继续；旧目录保留以供审计。",
  },
  "console.jobs.gateBlocked": {
    en: "Blocked by an acceptance gate — this is a configuration problem, not a failed run, so nothing was recorded.",
    zh: "被验收门槛拦下 —— 这是配置问题而不是失败的运行，所以什么也没记。",
  },
  "console.jobs.follow": { en: "Follow output", zh: "跟随输出" },
  "console.jobs.paused": { en: "Following paused", zh: "已暂停跟随" },
  "console.jobs.metricPoints": { en: "showing the last {n} points ({d} dropped)", zh: "仅显示最近 {n} 点（已丢弃 {d} 点）" },
  "console.jobs.empty": { en: "No jobs yet.", zh: "还没有作业。" },
  "console.jobs.loading": { en: "Loading…", zh: "加载中…" },
  "console.jobs.back": { en: "Back", zh: "返回" },
  "console.jobs.scenario": { en: "Scenario", zh: "场景" },
  "console.jobs.run": { en: "Run", zh: "运行名" },
  "console.jobs.attempt": { en: "Attempt", zh: "尝试" },
  "console.jobs.created": { en: "Created", zh: "创建时间" },
  "console.jobs.command": { en: "Command", zh: "执行命令" },
  "console.jobs.view": { en: "view", zh: "查看" },
  "console.jobs.noError": { en: "No error message recorded.", zh: "未记录错误信息。" },
  "console.common.cancel": { en: "Cancel", zh: "取消" },
  "console.common.close": { en: "Close", zh: "关闭" },

  "console.nav.publish": { en: "6 · Publish", zh: "6 · 发布" },
  "console.nav.modal": { en: "7 · Modal", zh: "7 · Modal" },
  "console.nav.goldset": { en: "Goldset", zh: "金标集" },

  "console.publish.run": { en: "checkpoint dir", zh: "checkpoint 目录" },
  "console.publish.repo": { en: "Hub repo", zh: "Hub 仓库" },
  "console.publish.card": { en: "model card markdown", zh: "模型卡 markdown 路径" },
  "console.publish.message": { en: "commit message", zh: "提交说明" },
  "console.publish.private": { en: "private repo", zh: "私有仓库" },
  "console.publish.tag": { en: "Hub tag", zh: "Hub 标签" },
  "console.publish.revision": { en: "branch", zh: "分支" },
  "console.publish.replace": { en: "replace revision", zh: "替换分支内容" },
  "console.publish.hint": {
    en: "Pushes the checkpoint to the Hugging Face Hub. Credentials come from HF_TOKEN on the orchestrator; never entered here.",
    zh: "把 checkpoint 推到 Hugging Face Hub。凭据来自编排服务的 HF_TOKEN，绝不在此填写。",
  },

  "console.modal.run": { en: "KEV_SERVE_RUN", zh: "部署运行名" },
  "console.modal.gpu": { en: "GPU", zh: "GPU" },
  "console.modal.appName": { en: "app name", zh: "App 名" },
  "console.modal.ref": { en: "commit pin", zh: "commit 钉" },
  "console.modal.hint": {
    en: "Runs `modal deploy` against the Modal CLI on the orchestrator. The endpoint lives on Modal, not on local port 8008.",
    zh: "在编排服务上执行 `modal deploy`。端点落在 Modal 远端，不在本地 8008 端口。",
  },

  "console.goldset.auditA": { en: "labelling A", zh: "标注 A" },
  "console.goldset.auditB": { en: "labelling B", zh: "标注 B" },
  "console.goldset.auditOut": { en: "disagreement out", zh: "分歧输出" },
  "console.goldset.threshold": { en: "disagreement threshold", zh: "分歧率阈值" },
  "console.goldset.auditHint": {
    en: "Compares two independent labellings; exit non-zero when the worst-question disagreement exceeds the threshold (CI gate).",
    zh: "比对两份独立标注；最差问题的分歧率超过阈值时以非 0 退出（可作 CI 闸门）。",
  },
  "console.goldset.reviewTitle": { en: "Gold-set review", zh: "金标人工审校" },
  "console.goldset.reviewHint": {
    en: "Edit each record's labels, then export a holdout file for split --holdout. Gold never enters train.",
    zh: "逐条改标签，导出 holdout 文件供 split --holdout 使用。金标永不进 train。",
  },
  "console.goldset.exportHoldout": { en: "Export holdout", zh: "导出金标" },
  "console.goldset.openReview": { en: "Open review UI", zh: "打开审校页" },

  "console.benchmark.remote": { en: "remote endpoint", zh: "远程端点" },
  "console.benchmark.remoteModel": { en: "remote model", zh: "远程模型" },
  "console.benchmark.remoteConcurrency": { en: "remote concurrency", zh: "远程并发" },
  "console.benchmark.suite": { en: "frozen suite", zh: "冻结 suite" },
  "console.benchmark.allowTest": { en: "allow test split", zh: "允许 test 分区" },
  "console.benchmark.dateFacts": { en: "with date facts", zh: "套用 date_facts" },
  "console.benchmark.rotations": { en: "rotations", zh: "旋转次数" },

  "console.distill.schedule": { en: "schedule (HH:MM)", zh: "调度 (HH:MM)" },
  "console.distill.dailyLimit": { en: "daily token limit", zh: "每日 token 上限" },
  "console.distill.stateDir": { en: "state dir", zh: "状态目录" },
  "console.distill.daemonHint": {
    en: "Daemon mode sleeps until the local HH:MM each day after distilling its daily quota; cancel kills the whole tree.",
    zh: "守护模式每天蒸馏到当日配额后睡到本地 HH:MM；取消即杀整棵树。",
  },

  "console.train.advanced": { en: "Advanced training switches", zh: "训练高级开关" },

  "console.scenarios.title": { en: "Scenario management", zh: "场景管理" },
  "console.scenarios.subtitle": {
    en: "Two-level taxonomy: a domain groups scenarios. Each scenario points to a spec JSON (prompts & config) and can be edited in place.",
    zh: "两级分类：一级域聚合二级场景。每个场景指向一份 spec JSON（提示词与配置），可在此直接编辑。",
  },
  "console.scenarios.newDomain": { en: "New domain", zh: "新建域" },
  "console.scenarios.newScenario": { en: "New scenario", zh: "新建场景" },
  "console.scenarios.search": { en: "Search scenarios…", zh: "搜索场景…" },
  "console.scenarios.empty": {
    en: "No scenarios yet. Create a domain, then add scenarios under it and point each to a spec JSON.",
    zh: "还没有场景。先建一个域，再在其下添加场景，并为每个场景指定一份 spec JSON。",
  },
  "console.scenarios.labelZh": { en: "Chinese label", zh: "中文标签" },
  "console.scenarios.labelEn": { en: "English label", zh: "英文标签" },
  "console.scenarios.domain": { en: "Domain", zh: "所属域" },
  "console.scenarios.slug": { en: "Slug", zh: "Slug" },
  "console.scenarios.specPath": { en: "Spec path (relative to repo root)", zh: "Spec 路径（相对仓库根）" },
  "console.scenarios.category": { en: "Category", zh: "分类" },
  "console.scenarios.sort": { en: "Sort", zh: "排序" },
  "console.scenarios.exists": { en: "spec file found", zh: "spec 文件存在" },
  "console.scenarios.missing": { en: "spec file missing", zh: "spec 文件缺失" },
  "console.scenarios.save": { en: "Save", zh: "保存" },
  "console.scenarios.delete": { en: "Delete", zh: "删除" },
  "console.scenarios.confirmDelete": {
    en: "Delete this item? This cannot be undone.", zh: "确认删除？此操作不可撤销。",
  },
  "console.scenarios.specEditor": { en: "Spec configuration (prompts & config)", zh: "Spec 配置（提示词与配置）" },
  "console.scenarios.specSave": { en: "Save config", zh: "保存配置" },
  "console.scenarios.editScenario": { en: "Edit scenario", zh: "编辑场景" },
  "console.scenarios.specFieldHelp": { en: "Spec field reference", zh: "spec 字段说明" },
  "console.scenarios.specSaved": { en: "spec saved", zh: "配置已保存" },
  "console.scenarios.specInvalid": { en: "Invalid JSON or missing required fields", zh: "JSON 非法或缺少必要字段" },
  "console.scenarios.specLoadFailed": { en: "Could not load spec file", zh: "无法读取 spec 文件" },
  "console.scenarios.domainDeleteCascade": {
    en: "Deleting a domain also removes its scenarios.", zh: "删除域会一并删除其下所有场景。",
  },
  "console.cascade.domain": { en: "Domain", zh: "领域" },
  "console.cascade.scenario": { en: "Scenario", zh: "场景" },
  "console.cascade.scenarioPlaceholder": { en: "select a domain first", zh: "请先选择领域" },

  // ---- studio (Wave C of the studio rollout plan) ----
  // The studio module is a parallel shell that mirrors the existing /console
  // pages but groups navigation by lifecycle (data / train-eval-deploy /
  // system) instead of by stage. The first pages land as thin wrappers over
  // the same /api/console/* contracts; the goal is navigation + layout.
  "studio.title": { en: "Studio", zh: "Studio" },
  "studio.subtitle": {
    en: "Lifecycle shell: data, train → eval → deploy, system. Backed by the same /console/api/* contracts as the legacy console.",
    zh: "生命周期外壳：数据 / 训练→评测→部署 / 系统。复用 /console/api/* 同一套 HTTP 契约。",
  },
  "studio.nav.data": { en: "Data", zh: "数据" },
  "studio.nav.lifecycle": { en: "Lifecycle", zh: "生命周期" },
  "studio.nav.system": { en: "System", zh: "系统" },
  "studio.nav.domains": { en: "Domains & scenarios", zh: "域与场景" },
  "studio.nav.datasets": { en: "Datasets", zh: "数据集" },
  "studio.nav.goldset": { en: "Goldset", zh: "金标集" },
  "studio.nav.train": { en: "Train", zh: "训练" },
  "studio.nav.eval": { en: "Evaluate", zh: "评测" },
  "studio.nav.deploy": { en: "Deploy", zh: "部署" },
  "studio.nav.publish": { en: "Publish", zh: "发布" },
  "studio.nav.overview": { en: "Overview", zh: "总览" },
  "studio.nav.apikeys": { en: "API keys", zh: "API Keys" },
  "studio.nav.usage": { en: "Usage", zh: "用量" },
  "studio.placeholder": {
    en: "This studio page lands in a later Wave C commit. The legacy /console/{kind} tab is the working surface for now.",
    zh: "本 Studio 页面将在后续 Wave C 提交中落地。短期内使用 /console/{kind} 作为工作面板。",
  },

  // ---- studio Wave C surface (prototype dark IDE skin) ----
  "studio.nav.monitoring": { en: "Monitoring", zh: "运维监控" },
  "studio.nav.admin": { en: "Admin", zh: "管理" },
  "studio.nav.projects": { en: "Projects", zh: "项目" },
  "studio.nav.members": { en: "Members", zh: "成员" },
  "studio.nav.quota": { en: "Quota", zh: "配额" },
  "studio.nav.webhooks": { en: "Webhooks", zh: "Webhook" },
  "studio.nav.billing": { en: "Billing", zh: "计费" },

  "studio.tab.run": { en: "Run", zh: "运行" },
  "studio.tab.records": { en: "Records", zh: "记录" },
  "studio.tab.monitor": { en: "Monitoring", zh: "资源监控" },
  "studio.tab.compare": { en: "Compare", zh: "对比" },
  "studio.tab.canary": { en: "Canary & Rollback", zh: "灰度回滚" },
  "studio.tab.health": { en: "Probe Health", zh: "探测健康" },
  "studio.tab.metrics": { en: "Metrics", zh: "指标" },
  "studio.tab.label": { en: "Label", zh: "标注" },

  "studio.projects.description": { en: "Description", zh: "描述" },

  "studio.members.invite": { en: "Invite member", zh: "邀请成员" },
  "studio.members.email": { en: "Email", zh: "邮箱" },
  "studio.members.name": { en: "Name", zh: "姓名" },
  "studio.members.role": { en: "Role", zh: "角色" },
  "studio.members.status": { en: "Status", zh: "状态" },

  "studio.quota.training_hours": { en: "Training hours", zh: "训练时长" },
  "studio.quota.gpu": { en: "GPU", zh: "GPU" },
  "studio.quota.api_calls": { en: "API calls", zh: "API 调用" },
  "studio.quota.storage": { en: "Storage", zh: "存储" },
  "studio.quota.limit": { en: "limit", zh: "限额" },
  "studio.quota.used": { en: "used", zh: "已用" },
  "studio.quota.set": { en: "Set limits", zh: "设置限额" },

  "studio.webhooks.url": { en: "URL", zh: "地址" },
  "studio.webhooks.events": { en: "Events", zh: "事件" },
  "studio.webhooks.secret": { en: "Secret", zh: "密钥" },
  "studio.webhooks.active": { en: "Active", zh: "启用" },
  "studio.webhooks.ping": { en: "Ping", zh: "探测" },
  "studio.webhooks.last_status": { en: "Last status", zh: "最近状态" },
  "studio.webhooks.new": { en: "New webhook", zh: "新建 webhook" },

  "studio.billing.period": { en: "Period", zh: "周期" },
  "studio.billing.amount": { en: "Amount", zh: "金额" },
  "studio.billing.currency": { en: "Currency", zh: "币种" },
  "studio.billing.status": { en: "Status", zh: "状态" },
  "studio.billing.due": { en: "Due", zh: "到期" },
  "studio.billing.issued": { en: "Issued", zh: "出账" },
  "studio.billing.plan": { en: "Current plan", zh: "当前套餐" },
  "studio.billing.invoice": { en: "Invoice", zh: "发票" },

  "studio.board.search": { en: "Search id, kind, scenario…", zh: "搜索 id / kind / 场景…" },
  "studio.board.empty": { en: "No jobs match.", zh: "没有匹配的作业。" },
  "studio.board.col.status": { en: "Status", zh: "状态" },
  "studio.board.col.id": { en: "id", zh: "作业 id" },
  "studio.board.col.kind": { en: "kind", zh: "类型" },
  "studio.board.col.scenario": { en: "scenario", zh: "场景" },
  "studio.board.col.run": { en: "run", zh: "运行名" },
  "studio.board.col.created": { en: "created", zh: "创建时间" },
  "studio.board.kpi.total": { en: "Total", zh: "总数" },
  "studio.board.kpi.running": { en: "Running", zh: "运行中" },
  "studio.board.kpi.succeeded": { en: "Succeeded", zh: "成功" },
  "studio.board.kpi.failed": { en: "Failed", zh: "失败" },
  "studio.board.all": { en: "All", zh: "全部" },
  "studio.board.prev": { en: "Prev", zh: "上一页" },
  "studio.board.next": { en: "Next", zh: "下一页" },
  "studio.board.pageOf": { en: "Page {page} / {total}", zh: "第 {page} / {total} 页" },

  // ---- 作业详情条与文件查看弹窗（JobFiles，datasets  jobs 栏用）----
  "studio.jobfiles.outputs": { en: "Outputs", zh: "输出产物" },
  "studio.jobfiles.inputs": { en: "Inputs", zh: "输入" },
  "studio.jobfiles.script": { en: "Script", zh: "执行脚本" },
  "studio.jobfiles.none": { en: "— none", zh: "— 无" },
  "studio.jobfiles.loading": { en: "Loading…", zh: "加载中…" },
  "studio.jobfiles.truncated": { en: "(large file, tail shown)", zh: "（文件较大，仅显示尾部）" },
  "studio.jobfiles.clickFile": { en: "Click to view the file content in a dialog", zh: "点击弹窗查看文件内容" },
  "studio.jobfiles.clickScript": { en: "Click to view the command this job ran", zh: "点击弹窗查看本作业实际执行的命令" },

  // 阶段页「提交作业」折叠面板标题
  "console.job.form": { en: "Submit job", zh: "提交作业" },

  // ---- 提交页右栏顶部的只读「操作解析」卡（StageInsights）----
  "console.insights.title": { en: "Step insights", zh: "操作解析" },
  "console.insights.step": { en: "What this step does", zh: "步骤说明" },
  "console.insights.inputs": { en: "Inputs", zh: "入参" },
  "console.insights.outputs": { en: "Outputs", zh: "输出产物" },
  "console.insights.gates": { en: "Gates on this stage", zh: "本阶段受闸" },
  "console.insights.outcome": {
    en: "After success (backend StageSpec.outcome)", zh: "成功后的下一步（后端 StageSpec.outcome）",
  },
  "console.insights.note": {
    en: "Purpose, inputs and outputs below are maintained in strings.ts; the gate assignment and next-step note come from the backend (GET /console/api/stages).",
    zh: "下方的步骤目的、入参与产物说明维护在 strings.ts；闸门归属与完成后动作取自后端接口（GET /console/api/stages）。",
  },

  "studio.datasets.tab.datasets": { en: "Datasets", zh: "数据集" },
  "studio.datasets.tab.jobs": { en: "Dataset jobs", zh: "数据集 Jobs" },
  "studio.datasets.tab.submit": { en: "Submit job", zh: "提交作业" },
  "studio.datasets.col.scenario": { en: "Scenario", zh: "场景" },
  "studio.datasets.col.domain": { en: "Domain", zh: "领域" },
  "studio.datasets.col.records": { en: "Records", zh: "记录数" },
  "studio.datasets.col.invalid": { en: "Invalid lines", zh: "非法行" },
  "studio.datasets.col.job": { en: "Generated by", zh: "生成作业" },
  "studio.datasets.col.path": { en: "Path", zh: "路径" },
  "studio.datasets.col.noJob": { en: "—", zh: "—" },
  "studio.datasets.rowsPerPage": { en: "Rows / page", zh: "每页行数" },
  "studio.datasets.clearFilter": { en: "All", zh: "全部" },
  "studio.datasets.filterActive": { en: "Filtered by {label}", zh: "按 {label} 筛选" },

  "studio.overview.title": { en: "Studio overview", zh: "Studio 总览" },
  "studio.overview.subtitle": {
    en: "Data → train → eval → deploy, end to end. Same /console/api/* contracts, lifecycle navigation.",
    zh: "数据 → 训练 → 评测 → 部署，端到端。复用 /console/api/* 契约，按生命周期导航。",
  },
  "studio.overview.recent": { en: "Recent jobs", zh: "最近作业" },
  "studio.overview.viewAll": { en: "View all jobs", zh: "查看全部作业" },
  "studio.overview.sections": { en: "Lifecycle", zh: "生命周期模块" },
  "studio.overview.section.data": { en: "Data generation", zh: "数据生成" },
  "studio.overview.section.lifecycle": { en: "Train · Eval · Deploy", zh: "训练 · 评测 · 部署" },
  "studio.overview.section.system": { en: "System & API", zh: "系统与 API" },
  "studio.overview.section.admin": { en: "Admin & billing", zh: "管理与计费" },
  "studio.overview.open": { en: "Open", zh: "进入" },

  "studio.monitoring.title": { en: "Monitoring & ops", zh: "监控与运维" },
  "studio.monitoring.subtitle": {
    en: "Resource health, alerts, events and audit trail. Live data is sourced from the job orchestrator.",
    zh: "资源健康、告警、事件与审计。实时数据取自作业编排层。",
  },
  "studio.monitoring.tab.resources": { en: "Resources", zh: "资源" },
  "studio.monitoring.tab.alerts": { en: "Alerts", zh: "告警" },
  "studio.monitoring.tab.events": { en: "Events", zh: "事件" },
  "studio.monitoring.tab.audit": { en: "Audit", zh: "审计" },
  "studio.monitoring.empty": { en: "Nothing here yet.", zh: "暂无数据。" },

  "studio.domains.title": { en: "Domains & scenarios", zh: "域与场景" },
  "studio.domains.subtitle": {
    en: "Two-level catalogue: a domain groups scenarios. Scenarios drive every job's --scenario.",
    zh: "两级目录：域聚合场景。场景决定每个作业的 --scenario。",
  },
  "studio.domains.newDomain": { en: "New domain", zh: "新建域" },
  "studio.domains.newScenario": { en: "New scenario", zh: "新建场景" },
  "studio.domains.edit": { en: "Edit", zh: "编辑" },
  "studio.domains.delete": { en: "Delete", zh: "删除" },
  "studio.domains.save": { en: "Save", zh: "保存" },
  "studio.domains.cancel": { en: "Cancel", zh: "取消" },
  "studio.domains.slug": { en: "slug", zh: "slug" },
  "studio.domains.labelZh": { en: "Label (zh)", zh: "中文名" },
  "studio.domains.labelEn": { en: "Label (en)", zh: "英文名" },
  "studio.domains.specPath": { en: "spec path", zh: "spec 路径" },
  "studio.domains.category": { en: "category", zh: "分类" },
  "studio.domains.spec": { en: "Spec", zh: "配置" },
  "studio.domains.scenarios": { en: "scenarios", zh: "场景" },
  "studio.domains.noScenarios": { en: "no scenarios", zh: "暂无场景" },
  "studio.domains.deleteConfirm": {
    en: "Delete this domain and all its scenarios?", zh: "删除该域及其下所有场景？",
  },
  "studio.domains.saved": { en: "Saved", zh: "已保存" },
  "studio.domains.loadFailed": { en: "Could not load", zh: "加载失败" },
  "studio.domains.scenarioCount": { en: "{n} scenarios", zh: "{n} 个场景" },

  "studio.datasets.detail": { en: "Dataset detail", zh: "数据集详情" },
  "studio.datasets.records": { en: "records", zh: "记录数" },
  "studio.datasets.invalid": { en: "invalid", zh: "非法行" },
  "studio.datasets.lineage": { en: "lineage", zh: "血缘" },
  "studio.datasets.export": { en: "Export", zh: "导出" },
  "studio.datasets.content": { en: "Content", zh: "内容" },
  "studio.datasets.noContent": { en: "No text content.", zh: "无文本内容。" },

  "studio.goldset.title": { en: "Goldset & labelling", zh: "金标集与标注" },
  "studio.goldset.subtitle": {
    en: "Divergence audit between two labellings, plus the review queue.",
    zh: "两份标注的分歧审计，以及复核队列。",
  },
  "studio.goldset.review": { en: "Open review", zh: "打开复核" },
  "studio.goldset.emptyReview": { en: "No disagreements queued.", zh: "暂无分歧待复核。" },

  "studio.train.records": { en: "Training records", zh: "训练记录" },
  "studio.train.monitor": { en: "Resource monitor", zh: "资源监控" },
  "studio.train.noMetrics": { en: "No running or recent training job to chart.", zh: "没有正在运行或近期的训练作业可绘图。" },

  "studio.eval.report": { en: "Eval report", zh: "评测报告" },
  "studio.eval.compare": { en: "Compare", zh: "对比" },
  "studio.eval.noComparison": { en: "Run baseline + benchmark + compare first.", zh: "请先运行 baseline + benchmark + compare。" },
  "studio.eval.reference": { en: "Reference (baseline)", zh: "对照（基线）" },
  "studio.eval.candidate": { en: "Candidate (finetuned)", zh: "候选（微调后）" },
  "studio.eval.metric": { en: "Metric", zh: "指标" },

  "studio.deploy.canary": { en: "Canary & rollback", zh: "灰度与回滚" },
  "studio.deploy.health": { en: "Probes & health", zh: "探测与健康" },
  "studio.deploy.metrics": { en: "Service metrics", zh: "服务指标" },
  "studio.deploy.endpoints": { en: "Endpoints", zh: "端点" },
  "studio.deploy.noEndpoints": { en: "No endpoints yet.", zh: "暂无端点。" },
  "studio.deploy.canaryHint": {
    en: "Shift a fraction of traffic to the new revision, watch error rate, then promote or roll back.",
    zh: "将部分流量切到新版本，观察错误率，再全量或回滚。",
  },

  "studio.apikeys.title": { en: "API keys", zh: "API Keys" },
  "studio.apikeys.subtitle": {
    en: "Issue, revoke and reactivate keys for System One endpoints.", zh: "为 System One 端点发放、吊销与恢复密钥。",
  },
  "studio.apikeys.create": { en: "Create key", zh: "创建密钥" },
  "studio.apikeys.name": { en: "Name", zh: "名称" },
  "studio.apikeys.prefix": { en: "Prefix", zh: "前缀" },
  "studio.apikeys.calls": { en: "Calls", zh: "调用" },
  "studio.apikeys.tokens": { en: "Tokens", zh: "Tokens" },
  "studio.apikeys.lastUsed": { en: "Last used", zh: "最近使用" },
  "studio.apikeys.created": { en: "Created", zh: "创建时间" },
  "studio.apikeys.revoke": { en: "Revoke", zh: "吊销" },
  "studio.apikeys.reactivate": { en: "Reactivate", zh: "恢复" },
  "studio.apikeys.active": { en: "active", zh: "启用" },
  "studio.apikeys.revoked": { en: "revoked", zh: "已吊销" },
  "studio.apikeys.empty": { en: "No keys yet.", zh: "暂无密钥。" },
  "studio.apikeys.createdToast": { en: "Key created — copy it now, it won't be shown again.", zh: "密钥已创建——请立即复制，不会再次显示。" },
  "studio.apikeys.revokedToast": { en: "Key revoked.", zh: "密钥已吊销。" },
  "studio.apikeys.reactivatedToast": { en: "Key reactivated.", zh: "密钥已恢复。" },
  "studio.apikeys.reveal": { en: "Copy key", zh: "复制密钥" },

  "studio.usage.title": { en: "Usage", zh: "用量" },
  "studio.usage.subtitle": {
    en: "Per-key call and token volume, plus distillation provider spend.", zh: "按密钥的调用与 token 量，以及蒸馏提供方支出。",
  },
  "studio.usage.byKey": { en: "By key", zh: "按密钥" },
  "studio.usage.distill": { en: "Distillation spend", zh: "蒸馏支出" },
  "studio.usage.day": { en: "day", zh: "日期" },
  "studio.usage.tokens": { en: "tokens", zh: "tokens" },
  "studio.usage.calls": { en: "calls", zh: "调用" },
  "studio.usage.latency": { en: "latency", zh: "延迟" },
  "studio.usage.total": { en: "Total", zh: "合计" },
  "studio.usage.empty": { en: "No usage recorded.", zh: "暂无用量记录。" },

  "studio.usage.projectSection": {
    en: "Project quota usage", zh: "项目配额用量",
  },
  "studio.usage.projectSectionDesc": {
    en: "Real storage and training-hour counters written by version registration and successful training.",
    zh: "由版本登记与训练成功落库的真实存储与训练时长计数。",
  },
  "studio.usage.currentProject": { en: "Current project", zh: "当前项目" },
  "studio.usage.allProjects": { en: "All projects", zh: "全部项目" },
  "studio.usage.storageGb": { en: "Storage (GB)", zh: "存储 (GB)" },
  "studio.usage.trainHours": { en: "Training hours", zh: "训练时长" },
  "studio.usage.apiCalls": { en: "API calls", zh: "API 调用" },
  "studio.usage.projectCol": { en: "Project", zh: "项目" },
  "studio.usage.noProjectSelected": {
    en: "No project selected — the table below lists every project's usage.",
    zh: "未选择项目——下方表格列出每个项目的用量。",
  },

  "studio.admin.comingSoon": {
    en: "This surface is planned for a later Wave C commit. The API contract is not live yet.",
    zh: "该模块计划在后续 Wave C 提交中落地，对应 API 尚未上线。",
  },
  "studio.admin.projects.title": { en: "Projects", zh: "项目" },
  "studio.admin.members.title": { en: "Members", zh: "成员" },
  "studio.admin.quota.title": { en: "Quota", zh: "配额" },
  "studio.admin.webhooks.title": { en: "Webhooks", zh: "Webhook" },
  "studio.admin.billing.title": { en: "Billing", zh: "计费" },
  "studio.admin.manage": { en: "Manage", zh: "管理" },
} as const;

// ============================================================================
// 操作解析（STAGE_INSIGHTS）：「提交作业」页右栏顶部的按 kind 步骤解析。
//
// 真相源（改动时逐一核对，防止前后端漂移）：
// - 阶段定义与 outcome：kev/console/stages/{data,train,eval,deploy,publish,modal}.py 的
//   StageSpec。卡片里「本阶段受闸」与「完成后下一步」**不在这里写** —— 走只读接口
//   GET /console/api/stages（app.get_stages 从 REGISTRY + gates.STAGE_GATES 组装）。
// - 闸门语义：kev/console/gates.py 的 G1..G7；闸→产物键：gates._BUILDERS。
// - 产物 id 与路径：各阶段 build() 的 artifacts_out + kev/console/artifacts.py 的
//   resolve/RELATION（血缘名）。
// - 字段默认值：各阶段 build() 读 params 的默认 + 各提交页的 FieldSpec。
// 后端没有中英双语的描述性字段（StageSpec 只有中文 outcome），所以步骤目的、
// 入参含义与产物去向的文案集中在这里；未知 kind 退回 STAGE_INSIGHT_GENERIC。
// ============================================================================
export type InsightText = { en: string; zh: string };
export type InsightItem = { name: string; text: InsightText };
export type StageInsight = { summary: InsightText; inputs: InsightItem[]; outputs: InsightItem[] };

export const STAGE_INSIGHTS: Record<string, StageInsight> = {
  // ---- 数据轨（stages/data.py）----
  plan_size: {
    summary: {
      en: "Step 1 of the data track: estimate how many records the scenario needs from its spec and a 0.75 baseline accuracy, producing total_records for generation.",
      zh: "数据轨第 1 步：按场景 spec 与基线精度 0.75 估算训练需要多少条记录，产出供生成使用的 total_records。",
    },
    inputs: [
      { name: "scenario", text: { en: "Required. Picks the spec JSON the estimate is computed from.", zh: "必填。决定读哪份场景 spec 来估算。" } },
    ],
    outputs: [
      { name: "plan:<scenario>", text: {
        en: "The plan JSON (data/console/plan-*.json, G2's evidence). generate's form fills --n from it with one click; G2 later compares it with split's summary record count. Missing it makes G2 fail with \"missing plan\" and blocks train.",
        zh: "计划文件（data/console/plan-*.json，G2 的证据）：generate 表单可一键把 total_records 回填到 --n；G2 拿它与 split 的 summary 记录数比对。缺失时 G2 判「缺少 plan」而失败，train 无法提交。",
      } },
    ],
  },
  generate: {
    summary: {
      en: "Data track: synthesize decision records with the programmatic rule engine (labels come from rules, fully reproducible). Samples like \"missing evidence\" that distillation cannot label must come from here.",
      zh: "数据轨：用程序化规则引擎合成决策记录（label 由规则给出，可复现）；「证据缺失」这类蒸馏写不了的样本必须靠它。",
    },
    inputs: [
      { name: "scenario", text: { en: "Required. Selects gen_<scenario>.py; four-B-only scenarios are refused here.", zh: "必填。决定调哪个 gen_<scenario>.py；4B-only 场景在本阶段被拒。" } },
      { name: "n", text: { en: "Default 787 (the planned record count). Controls generation scale — fix rare labels via the generator's quota, not by inflating n.", zh: "默认 787（计划记录数）。控制生成规模 —— 稀有标签要调生成器配额，不是加大 --n。" } },
      { name: "seed", text: { en: "Default 0. Same seed and n reproduce the file byte for byte.", zh: "默认 0。同 seed 同 n 逐字复现。" } },
      { name: "data", text: { en: "Default data/<scenario>; the output pool is <data>.jsonl. Directories are never reused (409).", zh: "默认 data/<scenario>，原始池写到 <data>.jsonl；目录不可复用（冲突报 409）。" } },
    ],
    outputs: [
      { name: "dataset:<name>", text: {
        en: "The raw pool <data>.jsonl (registered as a dataset artifact with generated_from lineage, artifacts.py::RELATION). Consumed by goldset (sampling) and split (partitioning). Without it there is nothing to split, so train's dataset:<scenario>/train never exists.",
        zh: "原始池 <data>.jsonl：注册为 dataset 产物并写 generated_from 血缘（artifacts.py::RELATION）。被 goldset（抽样）与 split（划分）消费。缺失则 split 无米下锅，train 的 dataset:<scenario>/train 永远不存在。",
      } },
    ],
  },
  distill: {
    summary: {
      en: "The distillation branch of the data track: a third-party LLM writes labels for the same states. It can only write label — soft targets like \"missing evidence\" still need generate.",
      zh: "数据轨的蒸馏支路：调第三方 LLM 为同一批 state 生成 label；蒸馏轨只能写 label，不会写软标签 target。",
    },
    inputs: [
      { name: "provider_id", text: { en: "Optional. Picks a server-side distill config (base_url/model/keys injected from the secret store; the browser never sees keys). Empty falls back to process env.", zh: "选填。指定服务端保存的蒸馏配置（base_url/model/keys 由密钥库注入，浏览器不经手）；留空则沿用进程环境变量。" } },
      { name: "n", text: { en: "Default 787. Controls how many records this batch generates.", zh: "默认 787。控制本批生成规模。" } },
      { name: "examples / n_examples", text: { en: "Optional. A labelled JSONL of few-shot style examples (make_examples' product); without it the model freestyles and quality drops.", zh: "选填。few-shot 风格范例文件（make_examples 的产物）及每批条数（默认 4）；缺范例时只能靠文字描述，质量明显偏低。" } },
      { name: "data / category", text: { en: "Output file is <data>/<category>.jsonl; defaults follow the scenario.", zh: "输出文件为 <data>/<category>.jsonl；默认随场景。" } },
    ],
    outputs: [
      { name: "dataset:<name>/<category>", text: {
        en: "The distilled JSONL, registered as a dataset artifact. split partitions every JSONL under the directory, so distilled records join the training set through split. Missing it only means the distillation branch contributes nothing.",
        zh: "蒸馏记录文件，注册为 dataset 产物。split 会把目录下所有 jsonl 一起划分，蒸馏样本经由它进入训练集。缺失只是蒸馏支路没有贡献。",
      } },
    ],
  },
  distill_daemon: {
    summary: {
      en: "Daemonized distillation: sleeps until the local HH:MM each day after burning its daily quota, for multi-day large batches. Cancelling kills the whole process tree.",
      zh: "长驻版蒸馏：每天蒸到当日 token 配额后睡到本地 HH:MM 再继续，适合跨多日凑大规模数据；取消即杀整棵进程树。",
    },
    inputs: [
      { name: "schedule", text: { en: "Required HH:MM — without it the stage builder refuses the job.", zh: "必填 HH:MM；缺失时阶段直接报 Invalid。" } },
      { name: "provider_id / api_keys", text: { en: "Credential source; at most 6 keys rotated per day.", zh: "凭据来源；每日额度最多轮换 6 个 key。" } },
      { name: "daily_limit", text: { en: "Daily token cap per key (default 500000, or the provider config's).", zh: "每日 token 上限（默认 500000，或由蒸馏配置给出）。" } },
      { name: "state_dir", text: { en: "Where distill state/usage is written; the default fixed directory is what usage collection reads — moving it silently breaks the usage page.", zh: "蒸馏状态与用量落盘目录；缺省的固定目录正是用量采集读取的位置，改错会静默断链。" } },
    ],
    outputs: [
      { name: "（无产物注册）", text: {
        en: "Deliberately declares no artifact id (Persist.START, artifacts_out empty): the file grows over time and does not exist at spawn. Its JSONL lands on the same path distill uses and goes through split later; distill usage is written to its own table.",
        zh: "有意不声明产物 id（长驻作业、artifacts_out 为空）：产出文件随时间增长、启动时还不存在。产出的 jsonl 与 distill 同路径，之后照常 split；蒸馏用量单独写入用量表供页面展示。",
      } },
    ],
  },
  goldset: {
    summary: {
      en: "Data-track QC: draw a stratified sample of gold-label candidates from the raw pool for human review.",
      zh: "数据轨质检：从原始池按标签分层抽一批金标候选，交人工审校。",
    },
    inputs: [
      { name: "data", text: { en: "The source pool directory (generate/distill output).", zh: "源池目录（generate/distill 的产出）。" } },
      { name: "n / seed", text: { en: "Sample size (default 200) and reproducibility seed (default 0).", zh: "抽样条数（默认 200）与可复现 seed（默认 0）。" } },
      { name: "out", text: { en: "Default <data>.gold.jsonl; existing files are refused.", zh: "默认 <data>.gold.jsonl；已存在则拒绝。" } },
    ],
    outputs: [
      { name: "dataset:<name>.gold", text: {
        en: "The gold sample. After manual review it enters evaluation through split --holdout; gold must never enter train (contaminating the test set is the medical red line). Missing it just leaves no gold audit.",
        zh: "金标候选文件：人工审校后经 split --holdout 接入评估；金标永不进 train（污染测试集是医疗红线）。缺失只是没有这一批金标可审。",
      } },
    ],
  },
  goldset_audit: {
    summary: {
      en: "A diagnostic job (not part of the pipeline): compare two independent labellings and exit non-zero when the worst-question disagreement exceeds the threshold, so CI can block.",
      zh: "诊断作业（不在流水线内）：比对两份独立标注，最差问题分歧率超阈值时以非 0 退出，供 CI 拦截。",
    },
    inputs: [
      { name: "a / b", text: { en: "Both required: two independent labellings of the same states (usually two vendors).", zh: "均必填：同一批 state 的两份独立标注（通常来自两个厂商模型）。" } },
      { name: "threshold", text: { en: "Disagreement gate, default 0.05.", zh: "分歧率阈值，默认 0.05。" } },
      { name: "out", text: { en: "Optional file for the disagreement samples.", zh: "选填：分歧样本输出文件。" } },
    ],
    outputs: [
      { name: "（无产物注册）", text: {
        en: "Registers nothing (artifacts_in/out are empty) — it reads files and reports through the exit code. Disagreement samples go to the human review queue.",
        zh: "不注册任何产物（artifacts_in/out 皆空）：只读文件、用退出码说话。分歧样本进人工审校池。",
      } },
    ],
  },
  split: {
    summary: {
      en: "The data track's merge point: convert every source JSONL into Kev record format and partition train / calibration / development (plus an optional gold holdout).",
      zh: "数据轨汇合点：把各来源 jsonl 转成 Kev 记录格式，按比例划出 train / calibration / development（另可接金标 holdout）。",
    },
    inputs: [
      { name: "data", text: { en: "Default data/<scenario>; reads <data>.jsonl and writes partitions into <data>/.", zh: "默认 data/<scenario>：读 <data>.jsonl，分区写进 <data>/ 目录。" } },
      { name: "calibration / development", text: { en: "Partition ratios, default 0.15 each; the rest is train.", zh: "两个评估分区的比例，默认各 0.15，其余进 train。" } },
      { name: "holdout", text: { en: "Optional reviewed gold file; lands as a holdout partition that never mixes into train.", zh: "选填。审校后的金标文件，作为 holdout 分区接入、永不混入 train。" } },
      { name: "seed", text: { en: "Default 0 — the partition assignment must be reproducible for paired comparisons.", zh: "默认 0 —— 分区归属必须可复现，配对比较才成立。" } },
    ],
    outputs: [
      { name: "dataset:<name>/summary", text: {
        en: "Record counts and label distribution. G2 compares its records with the plan; G3 reads the label distribution. Forgetting to register it made G2/G3 fail forever once (the incident recorded at the top of artifacts.py).",
        zh: "整份分区摘要：G2 拿 records 数与 plan 比对，G3 查稀有标签占比。历史上漏注册过一次，G2/G3 永远失败（artifacts.py 头注记载）。",
      } },
      { name: "dataset:<name>/train", text: {
        en: "The trainer's --data target (train's artifacts_in; lineage split_into). Missing it: train cannot even be submitted.",
        zh: "训练器的 --data 目标（train 注册时以它为 artifacts_in，血缘 split_into）。缺失则 train 无从提交。",
      } },
      { name: "dataset:<name>/development", text: {
        en: "Scored by baseline and benchmark — both MUST point at this same file or compare refuses on suite_sha256. Also the source of rows.json for calibrate.",
        zh: "baseline 与 benchmark 的打分数据：两次必须指向同一份文件，否则 compare 因 suite_sha256 不一致拒绝对比；也是 calibrate 的 rows.json 之源。",
      } },
      { name: "dataset:<name>/calibration", text: {
        en: "The calibration partition kept out of training by construction; precheck can screen it too.",
        zh: "按构造不参训的标定分区；precheck 也可对它预检。",
      } },
    ],
  },
  precheck: {
    summary: {
      en: "The last data gate before training: replay every record through the initial checkpoint's tokenizer and count rows that would exceed the context limit.",
      zh: "训练前最后一道数据闸：用初始 checkpoint 的 tokenizer 预演每条记录，统计会超 token 上限的行。",
    },
    inputs: [
      { name: "data", text: { en: "The split output directory.", zh: "split 的输出目录。" } },
      { name: "split", text: { en: "One of train/calibration/development, default train.", zh: "train/calibration/development 三选一，默认 train。" } },
      { name: "init_from", text: { en: "Default jaredpalmer/kev-0.8b — decides the tokenizer; keep it aligned with what train will warm-start from.", zh: "默认 jaredpalmer/kev-0.8b：决定用哪个 tokenizer，应与将来训练的 init 对齐。" } },
    ],
    outputs: [
      { name: "precheck:<name>/<split>", text: {
        en: "The precheck report (data/console/precheck-*.json). G1 reads its over_limit — it must be 0 before train is accepted. Missing report: G1 fails with \"缺少 precheck 报告\", which is what a path/id mismatch used to look like (appendix A #11).",
        zh: "预检报告（data/console/precheck-*.json）：G1 读它的 over_limit，必须为 0 才放行 train。报告缺失时 G1 判「缺少 precheck 报告」（路径与产物 id 各走一套的历史事故就是这副症状）。",
      } },
    ],
  },
  make_examples: {
    summary: {
      en: "Balance-sample few-shot style examples from a labelled JSONL, closing the loop back into distill's --examples.",
      zh: "从一份已标注 JSONL 里按标签均衡抽 few-shot 范例，回流给 distill 的 --examples，形成闭环。",
    },
    inputs: [
      { name: "data", text: { en: "Required: a labelled JSONL (e.g. generate's raw pool).", zh: "必填：一份已标注的 JSONL（如 generate 的原始池）。" } },
      { name: "n / seed", text: { en: "Example count (default 8) and seed (default 0).", zh: "范例条数（默认 8）与 seed（默认 0）。" } },
      { name: "out", text: { en: "Default <data>/examples.jsonl.", zh: "默认 <data>/examples.jsonl。" } },
    ],
    outputs: [
      { name: "dataset:<name>/examples", text: {
        en: "The example file; its path goes into distill's --examples. Without it distillation has only text descriptions to lean on and the style drifts.",
        zh: "范例文件：路径填进 distill 的 --examples。缺失时蒸馏只能靠文字描述，风格易漂。",
      } },
    ],
  },

  // ---- 训练轨（stages/train.py）----
  train: {
    summary: {
      en: "Start of the train track: SFT on the train partition with kev.train (A1 LoRA warm start / A2 LoRA from a bare base / B full-weight). Submitting runs the three data gates G1-G3 first.",
      zh: "训练轨起点：kev.train 在 split 的 train 分区上 SFT（A1 LoRA 热启动 / A2 裸基座 LoRA / B 全参数）；提交前先过 G1-G3 三道数据闸。",
    },
    inputs: [
      { name: "scenario", text: { en: "Required. Four-B-only scenarios refuse the 0.8B methods (run_matrix.FOUR_B_ONLY).", zh: "必填。4B-only 场景禁用 0.8B 轨方法（run_matrix.FOUR_B_ONLY）。" } },
      { name: "run_name", text: { en: "Required; must pass run_matrix.check_name (fullmatch, no dots — write 8b, never 0.8b). It becomes the artifact id run:<run_name>.", zh: "必填，过 run_matrix.check_name（fullmatch、禁点号，尺寸写 8b）；产物 id 就是 run:<run_name>，下游全靠它指认候选。" } },
      { name: "method", text: { en: "a1 (default) / a2 / b; each pre-packs init_from, base, lr, replay per the runbook.", zh: "a1（默认）/ a2 / b；三种方式预填 init_from、base、lr、replay（runbook §〇）。" } },
      { name: "data", text: { en: "Default data/<scenario>/train.jsonl — the split product G1/G2/G3 just certified.", zh: "默认 data/<scenario>/train.jsonl：即刚被 G1-G3 认证的 split 产物。" } },
      { name: "lr / replay", text: { en: "Track defaults (0.8B 4e-5, 4B 2e-5); on regression halve lr and keep --replay 2000.", zh: "按轨预置（0.8B 4e-5、4B 2e-5）；出现回归时 lr 减半、保留 --replay 2000。" } },
    ],
    outputs: [
      { name: "run:<run_name>", text: {
        en: "runs/<run_name>: checkpoint + training_config.json + training_metrics.json (lineage trained_on). Consumed as the candidate by baseline/benchmark and referenced by image/deploy/publish. Missing it leaves every downstream step without a candidate — G4/G5 cannot even be evaluated.",
        zh: "runs/<run_name>：checkpoint + training_config.json + training_metrics.json（血缘 trained_on）。被 benchmark 作为候选打分，被 image/deploy/publish 引用。缺失则下游整链无从指认候选，G4/G5 谈不上。",
      } },
    ],
  },

  // ---- 评测轨（stages/eval.py）----
  baseline: {
    summary: {
      en: "The control side: score the reference checkpoint zero-shot on the same development.jsonl — half of the paired CI, because a single benchmark run cannot prove the gain is real.",
      zh: "对照轨：用零样本基座打同一份 development.jsonl —— 它是配对 CI 的另一半（单次 benchmark 判不了「增益真实」）。",
    },
    inputs: [
      { name: "baseline", text: { en: "The reference checkpoint (default jaredpalmer/kev-0.8b) — the thing the candidate is compared against.", zh: "参照 checkpoint（默认 jaredpalmer/kev-0.8b）：候选就是与它比较。" } },
      { name: "data / split", text: { en: "Default development. MUST be the same file benchmark used, or compare refuses on suite_sha256.", zh: "默认 development：必须与 benchmark 指向同一份文件，否则 compare 因 suite_sha256 不一致拒收。" } },
      { name: "run_name", text: { en: "Decides the output directory and the eval:<run_name>-baseline artifact id.", zh: "决定输出目录与产物 id eval:<run_name>-baseline。" } },
    ],
    outputs: [
      { name: "eval:<run_name>-baseline", text: {
        en: "runs/<name>-baseline-eval/report.json — the reference side of compare. Missing it: compare fails and G4 has no evidence, so image/deploy stay blocked.",
        zh: "runs/<name>-baseline-eval/report.json：compare 的 reference 侧。缺失则 compare 无法运行，G4 没有证据，image/deploy 被拦死。",
      } },
    ],
  },
  benchmark: {
    summary: {
      en: "Score the candidate on the development partition: accuracy, ECE/Brier/NLL, selective coverage — G5's evidence and the source of rows.json.",
      zh: "候选打分：在开发集分区上给训练产物（或任意端点）算 acc/ECE/Brier 等指标 —— G5 的证据之源，rows.json 也在这里。",
    },
    inputs: [
      { name: "run", text: { en: "The candidate checkpoint, default runs/<run_name>; remote scoring (--remote) bypasses it.", zh: "候选 checkpoint，默认 runs/<run_name>；用 remote 打端点时不读本地产物。" } },
      { name: "data / split 或 suite", text: { en: "--data (a partition file) and --suite (a frozen suite) are mutually exclusive; keep the file identical to baseline's.", zh: "--data（本地分区）与 --suite（冻结套件）互斥；用文件时必须与 baseline 同一份。" } },
      { name: "allow_test / date_facts / rotations", text: { en: "Opt-ins: read the locked test split, apply date facts, run permutation checks.", zh: "可选项：读锁定 test 分区、套用 date_facts、排列一致性旋转次数。" } },
    ],
    outputs: [
      { name: "eval:<run_name>", text: {
        en: "runs/<name>-eval: report.json (G5's evidence; the candidate side of compare) and rows.json (calibrate's input). Missing it: G5 and G7 both fail and compare has no candidate.",
        zh: "runs/<name>-eval：report.json（G5 的证据、compare 的 candidate 侧）与 rows.json（calibrate 的入参）。缺失则 G5/G7 一起失败，compare 也没有候选可用。",
      } },
    ],
  },
  compare: {
    summary: {
      en: "Paired record-level bootstrap between the candidate and reference reports — the only local way to decide \"the gain is real\" (G4). No gate of its own: it produces gate evidence.",
      zh: "对两份 report 做逐记录配对 bootstrap，产出增益 CI —— 「增益真实吗」的唯一本地判法。它自身不设闸，而是产出闸门证据。",
    },
    inputs: [
      { name: "candidate / reference", text: { en: "The two eval directories, defaults derived from run_name. They must differ, and their suite_sha256 must match.", zh: "两个 eval 目录，默认按 run_name 推导；两者不能同目录，且 suite_sha256 必须一致。" } },
      { name: "public", text: { en: "public=1 switches to the public-suite regression comparison (G6's evidence); its artifact type is separate so the two never overwrite each other (gates.py comment).", zh: "public=1 切到公开套件回归对比（G6 证据）；产物类型独立，与 workload compare 互不覆盖（见 gates.py 注释）。" } },
    ],
    outputs: [
      { name: "comparison:<run_name>", text: {
        en: "runs/<name>-compare: G4 reads acc.ci95 (a CI spanning 0 means the gain is not real); G5 combines it with the report.",
        zh: "runs/<name>-compare：G4 读 acc.ci95（CI 含 0 即增益不成立），G5 联合 report 一起判。",
      } },
      { name: "regression:<run_name>", text: {
        en: "public=1 only: G6 checks the public-accuracy drop stays within 2 points. Missing either compare: image/deploy are refused by G4/G5/G6.",
        zh: "仅 public=1：G6 检查公开精度降幅不超 2 点。任一 compare 缺失，image/deploy 都会被 G4/G5/G6 拦下。",
      } },
    ],
  },
  calibrate: {
    summary: {
      en: "Fit the serving temperature on benchmark's rows.json and report four arms (raw / shipped / workload in-sample / group-disjoint OOF). Produces G7's evidence; no gate of its own.",
      zh: "在 benchmark 写出的 rows.json 上拟合服务温度，报告四臂对比（raw / shipped / workload 内样 / 分组离样 OOF）。产出 G7 证据；自身不设闸。",
    },
    inputs: [
      { name: "rows", text: { en: "Must be a rows.json written by kev.benchmark (default runs/<run_name>-eval/rows.json) — logits plus inference_temperature.", zh: "必须是 kev.benchmark 写出的 rows.json（默认 runs/<run_name>-eval/rows.json）：带 logits 与 inference_temperature。" } },
      { name: "out", text: { en: "Default calibration.json next to the rows.", zh: "默认与 rows 同目录的 calibration.json。" } },
    ],
    outputs: [
      { name: "calibration:<run_name>", text: {
        en: "calibration.json: workload_temperature is the ONLY legal temperature source for deploy (its parameter prompt says so), and G7 checks workload_oof ECE <= shipped ECE. Missing it: image/deploy submissions are refused with 400 \"缺少服务温度\".",
        zh: "calibration.json：workload_temperature 是部署温度的唯一合法来源（deploy 表单的红字就指向它），G7 校验 workload_oof ECE 不劣于 shipped。缺失时 image/deploy 提交直接被 400「缺少服务温度」拒绝。",
      } },
    ],
  },

  // ---- 交付轨（stages/deploy.py / publish.py / modal.py）----
  image: {
    summary: {
      en: "Build the serving image from deploy/kev-serve/Dockerfile. Weights are NOT baked in — medical models are never published, the image resolves the checkpoint at run time. Submitting runs the model-quality gates G4-G7.",
      zh: "交付轨：用 deploy/kev-serve/Dockerfile 构建服务镜像。权重不烘进镜像——医疗模型禁止公开，运行时才解析 checkpoint；提交前过模型质量闸 G4-G7。",
    },
    inputs: [
      { name: "run_name", text: { en: "Required. Which run is baked into KEV_SERVE_RUN.", zh: "必填。把哪个 run 打进构建参数 KEV_SERVE_RUN。" } },
      { name: "temperature", text: { en: "Required; take workload_temperature from calibration.json — never fit on development.jsonl (balanced prior != clinical prior).", zh: "必填；从 calibration.json 的 workload_temperature 取，绝不在 development 上拟合（均衡先验 != 真实临床先验）。" } },
    ],
    outputs: [
      { name: "image:kev-<run_name>", text: {
        en: "A docker tag kev-<run_name>:<temperature> (artifacts.resolve returns the tag itself). Consumed by containerised deployment. Missing it only blocks container delivery — the local deploy job does not depend on it.",
        zh: "docker 标签 kev-<run_name>:<temperature>（artifacts.resolve 直接返回 tag）。被容器化部署消费；缺失只影响镜像交付，本地 deploy 不依赖它。",
      } },
    ],
  },
  deploy: {
    summary: {
      en: "Launch a long-lived kev.serve endpoint on the orchestrator. The existing Q&A page already proxies to port 8008, so nothing on the front end needs rewiring. Model-quality gates G4-G7 apply before submission.",
      zh: "启动本地长驻的 kev.serve 端点：现有问答页的 rewrite 已指向 8008，部署完前端零改动即可打新模型。提交前同样过 G4-G7。",
    },
    inputs: [
      { name: "run_name / run", text: { en: "Which trained run serves; the checkpoint directory defaults to runs/<run_name>.", zh: "部署哪个训练产物；checkpoint 目录默认 runs/<run_name>。" } },
      { name: "temperature", text: { en: "Required, from calibration (see calibrate).", zh: "必填，取自 calibrate 的 calibration.json。" } },
      { name: "port", text: { en: "Default 8008; two live endpoints need a different port plus a matching playground rewrite.", zh: "默认 8008；双端点共存要换端口并同步改 playground 的 rewrite。" } },
    ],
    outputs: [
      { name: "endpoint:<port>", text: {
        en: "Registered immediately after spawn (Persist.START: a daemon never \"completes\"). Consumed as smoke's base_url and by the endpoint list / rollback. Without it the endpoint list stays forever empty.",
        zh: "spawn 后立刻注册（Persist.START：长驻进程永不「完成」）；被 smoke 用作 base_url，被端点页与回滚列表消费。缺失则端点列表永远为空。",
      } },
    ],
  },
  smoke: {
    summary: {
      en: "End-to-end probe after deploy: one case per scenario, checking the p distribution shape and argmax — a wrong shape means bad weights or field names, don't just read the score.",
      zh: "部署后的端到端探针：各场景打一例，看 p 分布形状与 argmax —— 别只看分数，形状不对说明权重或字段名有问题。",
    },
    inputs: [
      { name: "base_url", text: { en: "The deploy product, default http://127.0.0.1:8008.", zh: "deploy 的端点产物，默认 http://127.0.0.1:8008。" } },
      { name: "run_name", text: { en: "Decides the report file name smoke:<run_name>.", zh: "决定报告名 smoke:<run_name>。" } },
    ],
    outputs: [
      { name: "smoke:<run_name>", text: {
        en: "runs/<name>-smoke.json — the go-live record. Missing it leaves only a verbal \"it works\".",
        zh: "runs/<name>-smoke.json：上线留痕。缺失时「能用」就只是口头说法。",
      } },
    ],
  },
  publish: {
    summary: {
      en: "Push a trained checkpoint to the Hugging Face Hub with kev.publish. Medical models stay private; HF_TOKEN is injected by the orchestrator and never reaches the browser.",
      zh: "把训练产物推到 Hugging Face Hub（kev.publish）。医疗模型一律私有仓；HF_TOKEN 由编排服务注入，绝不下发浏览器。",
    },
    inputs: [
      { name: "repo", text: { en: "Required: the Hub repo id.", zh: "必填：目标 Hub 仓库 id。" } },
      { name: "card", text: { en: "Required: the model card markdown (kev.publish demands --card).", zh: "必填：model card 的 markdown 路径（kev.publish 强制 --card）。" } },
      { name: "run", text: { en: "Default runs/<run_name>/checkpoint.", zh: "默认 runs/<run_name>/checkpoint。" } },
      { name: "private / replace / tag / revision", text: { en: "Optional switches; --private creates a private repo first, --replace rewrites a branch.", zh: "可选开关：--private 先建私有仓，--replace 替换分支内容。" } },
    ],
    outputs: [
      { name: "（不注册本地产物）", text: {
        en: "artifacts_out is empty by design: the destination is the Hub remote, and the commit is recorded in checkpoint/hub.json. Missing repo/card fails with 400 before the process starts.",
        zh: "有意不注册本地产物（artifacts_out 为空）：去向是 Hub 远端，提交记录在 checkpoint/hub.json。缺 repo/card 会在起进程前被 400 拒掉。",
      } },
    ],
  },
  modal: {
    summary: {
      en: "Remote deployment: run modal deploy scripts/kev_modal.py on the orchestrator. All controls go through environment variables (KEV_SERVE_RUN etc.) — the script takes no argv flags — and the endpoint lives on Modal, not on local 8008.",
      zh: "远端部署：在编排机上执行 modal deploy scripts/kev_modal.py。控制全部走环境变量（KEV_SERVE_RUN 等），脚本没有 argparse 参数；端点落在 Modal 远端，不在本地 8008。",
    },
    inputs: [
      { name: "run", text: { en: "Required (KEV_SERVE_RUN): a local runs/<name> or a Hub id.", zh: "必填（KEV_SERVE_RUN）：本地 runs/<name> 或 Hub id。" } },
      { name: "gpu", text: { en: "Default L4.", zh: "默认 L4。" } },
      { name: "app_name", text: { en: "Default kev-finetune — Modal shows the URL by workspace/app name.", zh: "默认 kev-finetune；Modal 按 workspace/app 名给出 URL。" } },
      { name: "ref", text: { en: "Optional commit pin (KEV_REF).", zh: "选填：钉住的 commit（KEV_REF）。" } },
    ],
    outputs: [
      { name: "endpoint:modal-<run>", text: {
        en: "Registered so the deploy page can at least show what was deployed (meta.modal=True); liveness must be probed on the Modal URL — the local machine cannot check it.",
        zh: "注册这条只为让部署页「看得到部署过什么」（meta.modal=True）；在线状态要去探 Modal URL，本机探不了活。",
      } },
    ],
  },
};

// 未知 kind 的通用占位：同样使用 JobStagePage 的页面（新增阶段、旧后端没有
// /console/api/stages）都走这里，卡片只给骨架说明不给假事实。
export const STAGE_INSIGHT_GENERIC: StageInsight = {
  summary: {
    en: "No detailed analysis is registered for this job kind yet. Read the command preview below and the job's own form hints; structured metadata (stage, outcome, gates) comes from GET /console/api/stages when the backend provides it.",
    zh: "这种作业类型还没有登记详细解析。请以下方的命令预览与表单提示为准；结构信息（阶段、完成后动作、闸门归属）在后端可用时取自 GET /console/api/stages。",
  },
  inputs: [
    { name: "scenario", text: { en: "Usually required: picks the scenario spec.", zh: "通常必填：决定读哪份场景 spec。" } },
    { name: "run_name", text: { en: "Required for jobs that write products; must pass run_matrix.check_name.", zh: "会写产物的作业必填；需过 run_matrix.check_name（禁点号）。" } },
  ],
  outputs: [
    { name: "—", text: {
      en: "See the job detail page after submission: registered artifacts and lineage are listed there (artifacts.register in kev/console/artifacts.py).",
      zh: "提交后看作业详情页：注册了哪些产物与血缘都列在那里（kev/console/artifacts.py 的 register）。",
    } },
  ],
};