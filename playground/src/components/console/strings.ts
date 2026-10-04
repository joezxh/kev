// 控制台文案。形状沿用 src/lib/i18n.tsx 的 {en, zh}，由 app/layout 注入全局 dict，
// 保持 t() 单一入口 —— 不引入第二套 i18n。
//
// 医疗场景默认中文优先（docs/medical 全中文），但英文也必须完整：模型卡与 Hub 上
// 的医疗模型发布走英文。
export const CONSOLE_STRINGS = {
  "console.title": { en: "Medical fine-tune console", zh: "医疗微调控制台" },
  "console.subtitle": {
    en: "Five stages, fourteen job kinds, one shared dataset. Every form shows the exact command it will run.",
    zh: "五个阶段、十四种作业、共用一份数据。每个表单都显示它将执行的完整命令。",
  },
  "console.back": { en: "← kev", zh: "← kev" },
  "console.nav.overview": { en: "Overview", zh: "总览" },
  "console.nav.data": { en: "1 · Data", zh: "1 · 数据" },
  "console.nav.train": { en: "2 · Train", zh: "2 · 训练" },
  "console.nav.eval": { en: "3 · Evaluate", zh: "3 · 评测" },
  "console.nav.image": { en: "4 · Image", zh: "4 · 镜像" },
  "console.nav.deploy": { en: "5 · Deploy", zh: "5 · 部署" },

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
} as const;