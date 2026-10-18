// 控制台 API 客户端。所有请求走同源代理 /api/console/*，浏览器不直接连 8790。
// 凭据一律不出现：/config 只回布尔态（spec §12）。
export type JobStatus =
  | "pending" | "queued" | "running"
  | "succeeded" | "failed" | "canceled" | "interrupted";

export type Job = {
  id: string;
  kind: string;
  stage: string;
  scenario: string;
  title: string;
  status: JobStatus;
  /** 归属项目（D1/D14）：'' 是具名 legacy 哨兵，只在「全部项目」视图出现，不进任何具体项目列表。 */
  project_id: string;
  /** 归属 bundle（D3，schema v11）：提交那一刻显式声明它为哪个 bundle 而跑；'' 是未归属。 */
  bundle_id: string;
  /** 读侧 LEFT JOIN bundles 带出的可读名字；无归属或未连上时为 null。 */
  bundle_name: string | null;
  request: Record<string, unknown>;
  argv: string[];
  env_overlay: Record<string, string>;
  cwd: string;
  log_path: string;
  artifacts_in: string[];
  artifacts_out: string[];
  attempt: number;
  exit_code: number | null;
  error: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  template_id: string | null;
};

/** 作业类型「提交表单」的参数 schema（与后端 stage_param_specs + JobStagePage 对齐）。 */
export type StageParamField = {
  key: string;
  label?: string;
  kind?: "text" | "number" | "select" | "checkbox" | "textarea";
  required?: boolean;
  default?: string;
  placeholder?: string;
  hint?: string;
  options?: { value: string; label: string }[];
  optionsUrl?: string;
  /** 可一键从某来源回填本字段（如 generate 的 --n 从 plan_size 产物读 total_records）。 */
  fillFrom?: string;
};

export type StageParams = {
  kind: string;
  fields: StageParamField[];
  version: number;
  source: "db" | "default";
};

/** 命名作业模板：跨会话复用某类任务的参数预设。 */
export type JobTemplate = {
  id: string;
  kind: string;
  name: string;
  scenario: string;
  params: Record<string, string>;
  created_at: string;
  updated_at: string;
};

/** plan_size 产物的回填结果。 */
export type PlanResult = {
  scenario: string;
  total_records: number;
  artifact_id: string;
};

/** stage_param_spec_history 中的一条历史版本（每次保存都会归档旧版本）。 */
export type StageParamVersion = {
  id: string;
  kind: string;
  version: number;
  created_at: string;
  fields: StageParamField[];
};

export type Metric = {
  ep: number; step: number; total: number;
  loss: number; kl: number; anchor: number; sec: number;
};

export type Gate = { id: string; ok: boolean; detail: string; actual: string; need: string };

/** GET /stages 的响应：后端的只读阶段元数据（StageSpec 字段 + gates.STAGE_GATES 归属）。
 *  真相源在 kev/console/stages/*（REGISTRY）与 kev/console/gates.py，前端不许复制。 */
export type StageMeta = {
  kind: string; stage: string; title: string; outcome: string; gates: string[];
};

export type Artifact = {
  id: string; kind: string; name: string; path: string;
  meta: Record<string, unknown>; bytes: number | null; created_at: string;
  lineage?: { parent: string; child: string; relation: string }[];
};

export type JobDetail = Job & {
  metrics: Metric[]; metrics_dropped: number;
  artifacts: Artifact[]; notes: { kind: string }[];
};

/** GET /jobs/{id}/log 的响应：job.log 文件的尾部内容（真相源，区别于 SSE 回放的 events 表）。 */
export type JobLog = {
  job_id: string; log_path: string; name: string;
  exists: boolean; content: string; truncated: boolean;
};

/** GET /artifacts/{id}/content 的响应：产物文件的文本内容（结果页展示用）。 */
export type ArtifactContent = {
  id: string; kind: string; path: string; bytes: number | null;
  content: string; truncated: boolean;
};

/** artifact_versions 的一行（integrity 由服务端读时现算，PR B §4.2）。 */
export type ArtifactVersion = {
  id: string; artifact_id: string; seq: number; job_id: string; path: string;
  sha256: string; records: number | null; bytes: number | null;
  meta: Record<string, unknown>; spec_sha256: string | null; created_at: string;
  integrity: "ok" | "drift" | "missing";
};

/** GET /artifact-versions/{vid}/records 的响应（分页预览，行带定长指纹）。 */
export type ArtifactVersionPage = {
  version_id: string; total: number;
  records: { line_no: number; fingerprint: string; record: unknown }[];
};

/** GET /files/content 的响应：仓库相对文件（data/ 与 runs/ 下）的文本内容，
 *  用于查看那些不是注册产物、而是直接写路径的作业入参。 */
export type FileContent = {
  path: string; bytes: number | null;
  content: string; truncated: boolean;
};

export type ConsoleError = {
  kind: string; message: string; field: string; hint: string; stderr_tail: string;
};

/** 编排层返回的错误体。前端按 kind 分派：validation/conflict 提示重试，gate 展开闸门面板。 */
export class ApiError extends Error {
  constructor(readonly detail: ConsoleError) {
    super(detail.hint ? `${detail.message} —— ${detail.hint}` : detail.message);
    this.name = "ApiError";
  }

  /** 闸门失败时 stderr_tail 里是 JSON 数组（G1–G7 的明细）。 */
  gates(): Gate[] {
    if (this.detail.kind !== "gate") return [];
    try {
      return JSON.parse(this.detail.stderr_tail) as Gate[];
    } catch {
      return [];
    }
  }
}

export type ApiKey = {
  id: string; name: string; prefix: string; active: boolean;
  created_at: string; revoked_at: string | null;
  calls: number; input_tokens: number; output_tokens: number; last_used: string | null;
};
export type UsageRow = {
  id: string; name: string; prefix: string; active: boolean;
  calls: number; input_tokens: number; output_tokens: number;
  avg_latency_ms: number | null; p99_latency_ms: number; last_used: string | null;
};
export type UsageDay = {
  date: string; calls: number; input_tokens: number; output_tokens: number;
  avg_latency_ms: number | null;
};

export type DistillProvider = {
  id: string; name: string; base_url: string; model: string;
  daily_limit: number; key_count: number; key_hints: string[]; active: boolean; created_at: string;
};
export type DistillUsageRow = {
  provider_id: string; key_hint: string; model: string;
  tokens: number; days: number; last_day: string | null; daily_limit: number;
};

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api/console/${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    cache: "no-store",
  });
  // 先读原文再解析：上游空 body（如 405/204）直接 response.json() 会抛
  // "Unexpected end of JSON input"，换成可读的错误。
  const text = await response.text();
  if (!text) {
    if (response.ok) return {} as T;
    throw new ApiError({
      kind: "upstream",
      message: `空响应 (HTTP ${response.status} ${response.statusText})`,
      field: "", hint: "上游未返回 JSON；检查代理是否透传了该请求方法（如 DELETE/PUT）。",
      stderr_tail: "",
    });
  }
  const payload = JSON.parse(text);
  if (!response.ok) throw new ApiError(payload?.error ?? {
    kind: "executor", message: `HTTP ${response.status} ${response.statusText}`, field: "", hint: "", stderr_tail: "",
  });
  return payload as T;
}

export const api = {
  config: (scenario?: string) =>
    call<{ scenarios: string[]; serve_port: number;
           credentials: Record<string, boolean>;
           methods: Record<string, { title: string; lr: string; allowed: boolean }> }>(
      `config${scenario ? `?scenario=${encodeURIComponent(scenario)}` : ""}`),
  scenarios: () => call<{ name: string; questions: number }[]>("scenarios"),

  datasets: () => call<Artifact[]>("datasets"),
  dataset: (id: string) =>
    call<Artifact & { lineage: unknown[] }>(`datasets/${encodeURIComponent(id)}`),
  exportUrl: (id: string) => `/api/console/datasets/${encodeURIComponent(id)}/export`,

  jobs: (filter?: { status?: JobStatus; stage?: string; scenario?: string; project?: string; bundle?: string }) => {
    const query = new URLSearchParams(
      Object.entries(filter ?? {}).filter(([, value]) => value) as [string, string][],
    ).toString();
    return call<Job[]>(`jobs${query ? `?${query}` : ""}`);
  },
  job: (id: string) => call<JobDetail>(`jobs/${id}`),
  jobLog: (id: string) => call<JobLog>(`jobs/${id}/log`),
  preview: (payload: { kind: string; scenario: string; run_name: string;
                       params: Record<string, unknown> }) =>
    call<{ argv: string[]; env: Record<string, string>; outcome: string }>("jobs/preview", {
      method: "POST", body: JSON.stringify(payload),
    }),
  submit: (payload: { kind: string; scenario: string; run_name: string; project_id: string;
                      params: Record<string, unknown>; template_id?: string; bundle_id?: string }) =>
    call<Job>("jobs", { method: "POST", body: JSON.stringify(payload) }),

  // ---- stage param specs + plan 回填 + 作业模板 -------------------
  stageParams: (kind: string) =>
    call<StageParams>(`stage/${encodeURIComponent(kind)}/params`),
  saveStageParams: (kind: string, fields: StageParamField[]) =>
    call<StageParams>(`stage/${encodeURIComponent(kind)}/params`, {
      method: "PUT", body: JSON.stringify({ fields }),
    }),
  stageParamVersions: (kind: string) =>
    call<StageParamVersion[]>(`stage/${encodeURIComponent(kind)}/params/versions`),
  rollbackStageParams: (kind: string, version: number) =>
    call<StageParams>(`stage/${encodeURIComponent(kind)}/params/rollback`, {
      method: "POST", body: JSON.stringify({ version }),
    }),
  plan: (scenario: string) =>
    call<PlanResult>(`plan/${encodeURIComponent(scenario)}`),

  /** 全量阶段元数据（静态注册表）：供提交页的「操作解析」卡取 outcome 与闸门归属。 */
  stages: () => call<Record<string, StageMeta>>("stages"),

  jobTemplates: (kind?: string) =>
    call<JobTemplate[]>(`job-templates${kind ? `?kind=${encodeURIComponent(kind)}` : ""}`),
  createJobTemplate: (p: { kind: string; name: string; scenario?: string; params: Record<string, string> }) =>
    call<JobTemplate>("job-templates", { method: "POST", body: JSON.stringify(p) }),
  updateJobTemplate: (id: string, p: { name?: string; scenario?: string; params?: Record<string, string> }) =>
    call<JobTemplate>(`job-templates/${id}`, { method: "PUT", body: JSON.stringify(p) }),
  deleteJobTemplate: (id: string) =>
    call<{ deleted: boolean }>(`job-templates/${id}`, { method: "DELETE" }),
  cancel: (id: string) => call<{ canceled: boolean }>(`jobs/${id}/cancel`, { method: "POST" }),
  retry: (id: string) => call<Job>(`jobs/${id}/retry`, { method: "POST" }),
  /** 删作业并级联删它产生的数据；purge=false 只删数据库足迹、保留磁盘文件。返回各级联计数。 */
  deleteJob: (id: string, purge = true) =>
    call<{ deleted: boolean; job_id: string; events: number; distill_usage: number;
           lineage: number; versions: number; artifacts: number; files: number; bytes: number }>(
      `jobs/${id}?purge=${purge}`, { method: "DELETE" }),

  artifacts: (kind?: string) => call<Artifact[]>(`artifacts${kind ? `?kind=${kind}` : ""}`),
  artifactContent: (id: string) =>
    call<ArtifactContent>(`artifacts/${encodeURIComponent(id)}/content`),
  /** 产物的不可变版本列表（每项服务端现算 integrity）；未知产物 404，历史无版本返回 []。 */
  artifactVersions: (id: string) =>
    call<ArtifactVersion[]>(`artifacts/${encodeURIComponent(id)}/versions`),
  /** 版本快照的 JSONL 分页预览（逐行带定长指纹）。 */
  artifactVersionRecords: (vid: string, opts?: { offset?: number; limit?: number; q?: string; verdict?: string }) => {
    const q = new URLSearchParams();
    if (opts?.offset) q.set("offset", String(opts.offset));
    if (opts?.limit) q.set("limit", String(opts.limit));
    if (opts?.q) q.set("q", opts.q);
    if (opts?.verdict) q.set("verdict", opts.verdict);
    const qs = q.toString();
    return call<ArtifactVersionPage>(`artifact-versions/${vid}/records${qs ? `?${qs}` : ""}`);
  },
  /** 版本导出走同源代理直链（不 fetch，交给浏览器下载）。 */
  artifactVersionExportUrl: (vid: string) => `/api/console/artifact-versions/${vid}/export`,
  /** 只读白名单文件内容（data/ 与 runs/ 下的仓库相对路径）。 */
  fileContent: (path: string) =>
    call<FileContent>(`files/content?path=${encodeURIComponent(path)}`),
  gates: (stage: string, scenario: string, runName = "") =>
    call<Gate[]>(`gates/${stage}?scenario=${encodeURIComponent(scenario)}` +
                 (runName ? `&run_name=${encodeURIComponent(runName)}` : "")),
  endpoints: () => call<{ endpoints: Artifact[] }>("endpoints"),

  apikeys: (page = 1, page_size = 20) =>
    call<{ items: ApiKey[]; total: number; page: number; page_size: number }>(
      `apikeys?page=${page}&page_size=${page_size}`),
  // 首页下拉需要全部启用 key：?all=1 返回全集。
  apikeysAll: () => call<ApiKey[]>("apikeys?all=1"),
  createApiKey: (name: string) =>
    call<{ key: string } & ApiKey>("apikeys", { method: "POST", body: JSON.stringify({ name }) }),
  revokeApiKey: (id: string) => call<{ revoked: boolean }>(`apikeys/${id}`, { method: "DELETE" }),
  reactivateApiKey: (id: string) =>
    call<{ reactivated: boolean }>(`apikeys/${id}/reactivate`, { method: "POST" }),
  usageSummary: (from?: string, to?: string) => {
    const q = new URLSearchParams();
    if (from) q.set("from", from);
    if (to) q.set("to", to);
    return call<UsageRow[]>(`usage${q.toString() ? `?${q}` : ""}`);
  },
  usageTimeseries: (keyId: string, from?: string, to?: string) => {
    const q = new URLSearchParams();
    if (from) q.set("from", from);
    if (to) q.set("to", to);
    return call<UsageDay[]>(`usage/${keyId}${q.toString() ? `?${q}` : ""}`);
  },

  distillProviders: () => call<DistillProvider[]>("distill-providers"),
  createDistillProvider: (p: { name: string; base_url: string; model: string; daily_limit: number; keys: string[] }) =>
    call<DistillProvider>("distill-providers", { method: "POST", body: JSON.stringify(p) }),
  deactivateDistillProvider: (id: string) =>
    call<{ deactivated: boolean }>(`distill-providers/${id}`, { method: "DELETE" }),
  updateDistillProvider: (id: string, p: { name?: string; base_url?: string; model?: string; daily_limit?: number; keys?: string[] }) =>
    call<DistillProvider>(`distill-providers/${id}`, { method: "PUT", body: JSON.stringify(p) }),
  distillUsage: (providerId?: string, from?: string, to?: string) => {
    const q = new URLSearchParams();
    if (providerId) q.set("provider_id", providerId);
    if (from) q.set("from", from);
    if (to) q.set("to", to);
    return call<DistillUsageRow[]>(`distill-usage${q.toString() ? `?${q}` : ""}`);
  },
  distillJobUsage: (jobId: string, from?: string, to?: string) => {
    const q = new URLSearchParams();
    if (from) q.set("from", from);
    if (to) q.set("to", to);
    return call<DistillUsageRow[]>(`distill/${jobId}/usage${q.toString() ? `?${q}` : ""}`);
  },

  // ---- scenario domains & scenarios (two-level, bilingual) ---------------
  scenarioDomains: (lang = "zh") =>
    call<ScenarioTree[]>(`scenario-domains?lang=${encodeURIComponent(lang)}`),
  createDomain: (p: { slug: string; label_zh: string; label_en: string; sort?: number }) =>
    call<ScenarioDomain>("scenario-domains", { method: "POST", body: JSON.stringify(p) }),
  updateDomain: (id: string, p: { label_zh?: string; label_en?: string; sort?: number }) =>
    call<ScenarioDomain>(`scenario-domains/${id}`, { method: "PUT", body: JSON.stringify(p) }),
  deleteDomain: (id: string) =>
    call<{ deleted: boolean }>(`scenario-domains/${id}`, { method: "DELETE" }),

  createScenario: (p: { domain_id: string; slug: string; label_zh: string; label_en: string;
                         spec_path: string; category?: string; sort?: number }) =>
    call<Scenario>("scenarios", { method: "POST", body: JSON.stringify(p) }),
  updateScenario: (id: string, p: { domain_id?: string; label_zh?: string; label_en?: string;
                                     spec_path?: string; category?: string; sort?: number }) =>
    call<Scenario>(`scenarios/${id}`, { method: "PUT", body: JSON.stringify(p) }),
  deleteScenario: (id: string) =>
    call<{ deleted: boolean }>(`scenarios/${id}`, { method: "DELETE" }),

  scenarioSpec: (slug: string) =>
    call<{ slug: string; content: string }>(`scenarios/${encodeURIComponent(slug)}/spec`),
  saveScenarioSpec: (slug: string, content: string) =>
    call<{ slug: string; saved: boolean }>(`scenarios/${encodeURIComponent(slug)}/spec`,
      { method: "PUT", body: JSON.stringify({ content }) }),
  specHistory: (slug: string) =>
    call<{ ts: string }[]>(`scenarios/${encodeURIComponent(slug)}/spec/history`),
  specHistoryVersion: (slug: string, ts: string) =>
    call<{ slug: string; ts: string; content: string }>(
      `scenarios/${encodeURIComponent(slug)}/spec/history/${encodeURIComponent(ts)}`),

  // ---- distill yaml 内容（DB 为编辑真相源，任务 3）----
  scenarioDistillYaml: (slug: string) =>
    call<{ slug: string; path: string; content: string }>(
      `scenarios/${encodeURIComponent(slug)}/distill-yaml`),
  saveScenarioDistillYaml: (slug: string, content: string) =>
    call<{ slug: string; saved: boolean }>(`scenarios/${encodeURIComponent(slug)}/distill-yaml`,
      { method: "PUT", body: JSON.stringify({ content }) }),

  // Generator tab API
  generatorPreview: (scenario: string, body: { generator: unknown; distill: unknown; state_example: unknown }) =>
    fetch(`/console/api/scenarios/${encodeURIComponent(scenario)}/generator/preview`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }).then((r) => r.json()),
  generatorDryRun: (scenario: string, body: { n: number; seed: number }) =>
    fetch(`/console/api/scenarios/${encodeURIComponent(scenario)}/generator/dry-run`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }).then((r) => r.json()),
  generatorValidate: (scenario: string, body: { generator: unknown; distill: unknown }) =>
    fetch(`/console/api/scenarios/${encodeURIComponent(scenario)}/generator/validate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }).then((r) => r.json()),

  distillUsageTotals: (from?: string, to?: string) => {
    const q = new URLSearchParams();
    if (from) q.set("from_day", from);
    if (to) q.set("to_day", to);
    return call<DistillUsageTotal[]>(`distill-usage/totals${q.toString() ? `?${q}` : ""}`);
  },

  // ---- ch6 管理面：projects / members / quota / webhooks / invoices ----
  projects: () => call<Project[]>("projects"),
  createProject: (p: { slug: string; name: string; description?: string;
                       scenario: string; goal?: string }) =>
    call<Project>("projects", { method: "POST", body: JSON.stringify(p) }),
  project: (id: string) => call<ProjectSummary>(`projects/${id}`),
  projectArtifacts: (id: string) => call<Artifact[]>(`projects/${id}/artifacts`),
  projectEvents: (id: string, afterId?: number) =>
    call<Event[]>(`projects/${id}/events${afterId ? `?after_id=${afterId}` : ""}`),
  updateProject: (id: string, p: { name?: string; slug?: string; description?: string; scenario?: string }) =>
    call<Project>(`projects/${id}`, { method: "PUT", body: JSON.stringify(p) }),
  deleteProject: (id: string) => call<{ deleted: boolean }>(`projects/${id}`, { method: "DELETE" }),

  // ---- 数据策展：bundles / materialize / freeze / policy / diff（PR C）----
  bundles: (projectId: string) => call<Bundle[]>(`projects/${projectId}/bundles`),
  bundle: (projectId: string, name: string) =>
    call<BundleDetail>(`projects/${projectId}/bundles/${encodeURIComponent(name)}`),
  createBundle: (projectId: string, p: { name: string; note?: string }) =>
    call<Bundle>(`projects/${projectId}/bundles`, { method: "POST", body: JSON.stringify(p) }),
  setBundleMembers: (projectId: string, name: string,
                     members: { version_id: string; op: string; ord: number }[]) =>
    call<BundleDetail>(`projects/${projectId}/bundles/${encodeURIComponent(name)}/members`,
      { method: "PUT", body: JSON.stringify(members) }),
  materializeBundle: (projectId: string, name: string) =>
    call<{ job_id: string }>(`projects/${projectId}/bundles/${encodeURIComponent(name)}/materialize`,
      { method: "POST" }),
  freezeBundle: (projectId: string, name: string) =>
    call<FreezeResult>(`projects/${projectId}/bundles/${encodeURIComponent(name)}/freeze`,
      { method: "POST" }),
  setFreezePolicy: (projectId: string, p: { freeze_min_records?: number; freeze_min_review_ratio?: number }) =>
    call<Project>(`projects/${projectId}/freeze-policy`, { method: "PUT", body: JSON.stringify(p) }),
  bundleDiff: (bundleId: string, other: string) =>
    call<BundleDiff>(`bundles/${bundleId}/diff?other=${encodeURIComponent(other)}`),

  // ---- 人工标注：reviews / review-queue / import（PR D）----
  upsertReview: (projectId: string, fingerprint: string,
                 p: { verdict: ReviewVerdict; patch?: unknown; labels?: string[]; note?: string;
                      reviewer?: string; record_id?: string; source_version_id?: string;
                      fingerprint_after?: string }) =>
    call<Review>(`projects/${projectId}/reviews/${encodeURIComponent(fingerprint)}`,
      { method: "PUT", body: JSON.stringify(p) }),
  listReviews: (projectId: string, q?: { verdict?: string; labels?: string; origin?: string; page?: number }) => {
    const s = new URLSearchParams();
    if (q?.verdict) s.set("verdict", q.verdict);
    if (q?.labels) s.set("labels", q.labels);
    if (q?.origin) s.set("origin", q.origin);
    if (q?.page) s.set("page", String(q.page));
    return call<ReviewPage>(`projects/${projectId}/reviews${s.toString() ? `?${s}` : ""}`);
  },
  reviewQueue: (projectId: string, q?: { limit?: number; seed?: number; include_decided?: 0 | 1 }) => {
    const s = new URLSearchParams();
    if (q?.limit != null) s.set("limit", String(q.limit));
    if (q?.seed != null) s.set("seed", String(q.seed));
    if (q?.include_decided) s.set("include_decided", "1");
    return call<ReviewQueue>(`projects/${projectId}/review-queue${s.toString() ? `?${s}` : ""}`);
  },
  importReviews: (projectId: string, rows: Record<string, unknown>[]) =>
    call<ReviewImportResult>(`projects/${projectId}/reviews/import`,
      { method: "POST", body: JSON.stringify({ rows }) }),

  // ---- 结论 / 血缘：releases + lineage（PR E）----
  createRelease: (projectId: string, p: ReleaseCreatePayload) =>
    call<Release>(`projects/${projectId}/releases`, { method: "POST", body: JSON.stringify(p) }),
  projectReleases: (projectId: string) => call<Release[]>(`projects/${projectId}/releases`),
  getRelease: (projectId: string, releaseId: string) =>
    call<Release>(`projects/${projectId}/releases/${encodeURIComponent(releaseId)}`),
  projectLineage: (projectId: string) => call<Lineage>(`projects/${projectId}/lineage`),

  members: (projectId: string) => call<Member[]>(`projects/${projectId}/members`),
  inviteMember: (projectId: string, p: { email: string; name?: string; role?: string; status?: string }) =>
    call<Member>(`projects/${projectId}/members`, { method: "POST", body: JSON.stringify(p) }),
  updateMember: (projectId: string, memberId: string, p: { role?: string; status?: string; name?: string }) =>
    call<Member>(`projects/${projectId}/members/${memberId}`, { method: "PUT", body: JSON.stringify(p) }),
  removeMember: (projectId: string, memberId: string) =>
    call<{ deleted: boolean }>(`projects/${projectId}/members/${memberId}`, { method: "DELETE" }),

  quota: (projectId: string) => call<Quota>(`projects/${projectId}/quota`),
  setQuota: (projectId: string, p: {
    training_hours_limit?: number; gpu_limit?: number;
    api_calls_limit?: number; storage_gb_limit?: number;
  }) => call<Quota>(`projects/${projectId}/quota`, { method: "PUT", body: JSON.stringify(p) }),

  webhooks: (projectId: string) => call<Webhook[]>(`projects/${projectId}/webhooks`),
  createWebhook: (projectId: string, p: { url: string; events: string[]; secret?: string }) =>
    call<Webhook>(`projects/${projectId}/webhooks`, { method: "POST", body: JSON.stringify(p) }),
  updateWebhook: (projectId: string, webhookId: string, p: { url?: string; events?: string[]; secret?: string; active?: boolean }) =>
    call<Webhook>(`projects/${projectId}/webhooks/${webhookId}`, { method: "PUT", body: JSON.stringify(p) }),
  deleteWebhook: (projectId: string, webhookId: string) =>
    call<{ deleted: boolean }>(`projects/${projectId}/webhooks/${webhookId}`, { method: "DELETE" }),
  pingWebhook: (projectId: string, webhookId: string) =>
    call<{ status: number }>(`projects/${projectId}/webhooks/${webhookId}/ping`, { method: "POST" }),

  invoices: (projectId: string, period?: string) => {
    const q = new URLSearchParams();
    if (period) q.set("period", period);
    return call<Invoice[]>(`projects/${projectId}/invoices${q.toString() ? `?${q}` : ""}`);
  },
  createInvoice: (projectId: string, p: { period: string; amount: number; currency?: string; status?: string; due_at?: string; line_items?: unknown[] }) =>
    call<Invoice>(`projects/${projectId}/invoices`, { method: "POST", body: JSON.stringify(p) }),
};

export type DistillUsageTotal = { day: string; tokens: number };

export type Scenario = {
  id: string; slug: string; label: string; label_zh: string; label_en: string;
  spec_path: string; category: string; sort: number; exists: boolean;
  // 轨制派生列（scenario_specs.derive_track，后端 list_scenario_tree 已返回）：
  // track = rule|distill|both|llm|''，generator_kind = engine|script|''。
  track: string; generator_kind: string; distill_yaml?: string; origin?: string;
};
export type ScenarioDomain = {
  id: string; slug: string; label: string; label_zh: string; label_en: string;
  sort: number; scenarios: Scenario[];
};
export type ScenarioTree = ScenarioDomain;

// ---- ch6 管理面资源 ----------------------------------------------------
export type Project = {
  id: string; slug: string; name: string; description: string;
  status: string; scenario: string; goal: string; archived_at: string | null;
  freeze_min_records: number; freeze_min_review_ratio: number;
  created_at: string; updated_at: string;
};
/** 项目事件流的一行（events 表经 jobs.project_id 归属，D10）。 */
export type Event = {
  id: number; job_id: string; ts: string; stream: string; line: string;
};

/** bundle 状态机（§6.3）：draft ↔ materialized → frozen → retired。 */
export type BundleStatus = "draft" | "materialized" | "frozen" | "retired";

/** bundles 表的一行（PR C）：物化后带 sha256/records/review_ratio + freeze_checks。 */
export type Bundle = {
  id: string; project_id: string; name: string; artifact_id: string;
  status: BundleStatus; sha256: string | null; records: number | null;
  reviewed_records: number | null; reviewed_native: number | null;
  reviewed_inherited: number | null; review_ratio: number | null;
  freeze_checks: Gate[]; manifest_path: string | null; manifest_sha256: string | null;
  frozen_at: string | null; note: string; created_at: string; updated_at: string;
};

/** bundle_members join 版本后的一行：op 三态 + 物化统计（drop_reasons 四键）。 */
export type BundleMember = {
  bundle_id: string; version_id: string; op: "include" | "exclude" | "overlay"; ord: number;
  records_in: number | null; records_kept: number | null; records_dropped: number | null;
  drop_reasons: Record<string, number>;
  source_artifact: string; source_path: string; version_records: number | null;
};

/** GET .../bundles/{name} 带回成员；端点写回时也带。 */
export type BundleDetail = Bundle & { members: BundleMember[] };

/** POST .../freeze 的响应：软门槛不过时 200 + warnings（仍冻结），F1/F4 硬拒走 409。 */
export type FreezeResult = { bundle: Bundle; warnings: Gate[] };

/** GET /bundles/{id}/diff?other= 的响应（按记录指纹比较）。 */
export type BundleDiff = {
  only_left: string[]; only_right: string[]; common: string[];
  changed: { fingerprint: string; from: unknown; to: unknown }[];
};

/** verdict 五态（PR D，D6）：accept/relabel/edit/drop/flag。 */
export type ReviewVerdict = "accept" | "relabel" | "edit" | "drop" | "flag";

/** record_reviews 的一行（PR D，场景作用域 UNIQUE(scenario,fingerprint)）：
 * patch 存仅新值、fingerprint_after 存改后内容指纹；origin_project_slug 供继承溯源。 */
export type Review = {
  id: string; scenario: string; origin_project_id: string; fingerprint: string;
  record_id: string | null; verdict: ReviewVerdict; patch: Record<string, unknown> | null;
  fingerprint_after: string | null; labels: string[]; note: string; reviewer: string;
  source_version_id: string | null; created_at: string; updated_at: string;
  origin_project_slug?: string;
};

/** GET /projects/{id}/reviews 的响应（含继承来的）。 */
export type ReviewPage = { items: Review[]; total: number };

/** GET /projects/{id}/review-queue 的一项：待标注记录 + 已有决定（include_decided 时）。 */
export type ReviewQueueItem = {
  fingerprint: string; record: Record<string, unknown>; existing_verdict?: ReviewVerdict;
};
export type ReviewQueue = { items: ReviewQueueItem[]; count: number };

/** POST /projects/{id}/reviews/import 的回报：逐行落库 + unmatched 原因。 */
export type ReviewImportResult = {
  imported: number;
  unmatched: { row: Record<string, unknown>; reason: string }[];
};

/** verdict 三态（PR E，D8 状态机）：candidate/accepted/rejected。 */
export type ReleaseVerdict = "candidate" | "accepted" | "rejected";

/** project_releases 的一行（PR E §4.5）：gates_snapshot/metrics 服务端现算落库，
 * 产物指针可空；metrics 七键来自 eval/comparison 产物，snapshot 是落库时的闸判定形状。 */
export type Release = {
  id: string; project_id: string; name: string;
  bundle_id: string | null; bundle_sha256: string | null; train_job_id: string | null;
  run_artifact: string | null; eval_artifact: string | null; comparison_artifact: string | null;
  regression_artifact: string | null; calibration_artifact: string | null;
  metrics: { acc?: number | null; ece?: number | null; brier?: number | null; aurc?: number | null;
    coverage?: number | null; ci95?: [number, number] | null; delta?: number | null };
  gates_snapshot: Gate[]; verdict: ReleaseVerdict; note: string; created_at: string;
};

/** POST /projects/{id}/releases 的请求体：只引用产物，不提交数字（服务端现算）。 */
export type ReleaseCreatePayload = {
  name: string; bundle_id?: string; train_job_id?: string; run_artifact?: string;
  eval_artifact?: string; comparison_artifact?: string; regression_artifact?: string;
  calibration_artifact?: string; verdict?: ReleaseVerdict; note?: string;
};

/** GET /projects/{id}/lineage 的一项节点 / 一条边（PR E D10，前端只渲染）。 */
export type LineageNode = { id: string; kind: string; version: number | null };
export type LineageEdge = { parent: string; child: string; relation: string; job_id?: string | null };
export type Lineage = { nodes: LineageNode[]; edges: LineageEdge[] };

/** GET /projects/{id} 的响应：Project 原始列 + 派生计数/阶段/最近事件（Task 5 project_summary）。
 *  usage 是 PR F 落库的真实配额用量（§4.6-2），只加字段、向后兼容。 */
export type ProjectUsage = {
  storage_gb_used: number; training_hours_used: number; api_calls_used: number;
};
export type ProjectSummary = Project & {
  jobs: number; artifacts: number;
  recent_events: Event[]; stages: Record<string, JobStatus>;
  usage: ProjectUsage;
};
export type Member = {
  id: string; project_id: string; email: string; name: string;
  role: "owner" | "admin" | "member" | "viewer";
  status: "invited" | "active";
  created_at: string;
};
export type Quota = {
  project_id: string;
  training_hours_limit: number; training_hours_used: number;
  gpu_limit: number; api_calls_limit: number; api_calls_used: number;
  storage_gb_limit: number; storage_gb_used: number;
  updated_at: string;
};
export type Webhook = {
  id: string; project_id: string; url: string; events: string[];
  secret: string; active: boolean; last_status: number | null;
  last_delivered_at: string | null; created_at: string;
};
export type Invoice = {
  id: string; project_id: string; period: string; amount: number;
  currency: string; status: "open" | "paid" | "void";
  due_at: string | null; issued_at: string; line_items: unknown[];
};

/**
 * 订阅作业的 SSE 日志流。
 *
 * EventSource 断线自动重连时**沿用原 URL**，Last-Event-ID 由浏览器自动带成 header，
 * 编排层据此从 events 表续传（Task 2 评审发现：只读 after_id 查询参数会全量重放）。
 * 所以这里**不要**把 lastEventId 拼进 URL —— 那会与 header 打架。
 */
export function streamJob(jobId: string, afterId = 0): EventSource {
  return new EventSource(`/api/console/jobs/${jobId}/stream?after_id=${afterId}`);
}

export function subscribeStream(
  source: EventSource,
  handlers: {
    onLog?: (event: { id: number; line: string; stream: string }) => void;
    onMetric?: (metric: Metric) => void;
    onStatus?: (status: { status: JobStatus; exit_code: number | null }) => void;
  },
): () => void {
  // 每个事件单独绑一次：JSON.parse 的结果需要断言到各自的具体形状，
  // 走同一个泛型 bind 会让 TS 只推导出 { id: number } 然后在调用点报错。
  if (handlers.onLog) {
    source.addEventListener("log", ((event: MessageEvent<string>) =>
      handlers.onLog!(JSON.parse(event.data) as { id: number; line: string; stream: string })
    ) as EventListener);
  }
  if (handlers.onMetric) {
    source.addEventListener("metric", ((event: MessageEvent<string>) =>
      handlers.onMetric!(JSON.parse(event.data) as Metric)
    ) as EventListener);
  }
  if (handlers.onStatus) {
    source.addEventListener("status", ((event: MessageEvent<string>) => {
      handlers.onStatus!(JSON.parse(event.data) as { status: JobStatus; exit_code: number | null });
      source.close();
    }) as EventListener);
  }
  return () => source.close();
}