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
} as const;