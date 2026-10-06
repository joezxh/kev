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
};

export type Metric = {
  ep: number; step: number; total: number;
  loss: number; kl: number; anchor: number; sec: number;
};

export type Gate = { id: string; ok: boolean; detail: string; actual: string; need: string };

export type Artifact = {
  id: string; kind: string; name: string; path: string;
  meta: Record<string, unknown>; bytes: number | null; created_at: string;
  lineage?: { parent: string; child: string; relation: string }[];
};

export type JobDetail = Job & {
  metrics: Metric[]; metrics_dropped: number;
  artifacts: Artifact[]; notes: { kind: string }[];
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
  const payload = await response.json();
  if (!response.ok) throw new ApiError(payload?.error ?? {
    kind: "executor", message: response.statusText, field: "", hint: "", stderr_tail: "",
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

  jobs: (filter?: { status?: JobStatus; stage?: string; scenario?: string }) => {
    const query = new URLSearchParams(
      Object.entries(filter ?? {}).filter(([, value]) => value) as [string, string][],
    ).toString();
    return call<Job[]>(`jobs${query ? `?${query}` : ""}`);
  },
  job: (id: string) => call<JobDetail>(`jobs/${id}`),
  preview: (payload: { kind: string; scenario: string; run_name: string;
                       params: Record<string, unknown> }) =>
    call<{ argv: string[]; env: Record<string, string>; outcome: string }>("jobs/preview", {
      method: "POST", body: JSON.stringify(payload),
    }),
  submit: (payload: { kind: string; scenario: string; run_name: string;
                      params: Record<string, unknown> }) =>
    call<Job>("jobs", { method: "POST", body: JSON.stringify(payload) }),
  cancel: (id: string) => call<{ canceled: boolean }>(`jobs/${id}/cancel`, { method: "POST" }),
  retry: (id: string) => call<Job>(`jobs/${id}/retry`, { method: "POST" }),

  artifacts: (kind?: string) => call<Artifact[]>(`artifacts${kind ? `?kind=${kind}` : ""}`),
  gates: (stage: string, scenario: string, runName = "") =>
    call<Gate[]>(`gates/${stage}?scenario=${encodeURIComponent(scenario)}` +
                 (runName ? `&run_name=${encodeURIComponent(runName)}` : "")),
  endpoints: () => call<{ endpoints: Artifact[] }>("endpoints"),

  apikeys: () => call<ApiKey[]>("apikeys"),
  createApiKey: (name: string) =>
    call<{ key: string } & ApiKey>("apikeys", { method: "POST", body: JSON.stringify({ name }) }),
  revokeApiKey: (id: string) => call<{ revoked: boolean }>(`apikeys/${id}`, { method: "DELETE" }),
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