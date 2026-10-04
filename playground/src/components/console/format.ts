// 控制台的纯函数：指标取值与格式化。抽出来是为了能单测，也让页面组件保持薄。
//
// 指标路径全部核对自真实产物结构（spec §8.1）。特别注意：
// **配对 CI 只在 kev.compare 的 comparison.json 里** —— kev.benchmark 的 report.json
// 没有 bootstrap 键（它写的是 paired_flip），而 G4「增益真实」正是靠它判定的。

export type MetricPath = (string | number)[];

export function metricAt(source: unknown, path: MetricPath): number | undefined {
  let node: unknown = source;
  for (const key of path) {
    if (node === null || typeof node !== "object") return undefined;
    node = (node as Record<string | number, unknown>)[key];
  }
  // 布尔是 int 的子类但不是指标 —— 显式排除，避免 true 被当成 1 画进曲线
  return typeof node === "number" && !Number.isNaN(node) ? node : undefined;
}

/**
 * 取一个子对象（top_bins / selective 这类嵌套字典）。
 * metricAt 只返回数字，取对象会全部落空，所以图表那三个组件需要这个。
 */
export function objectAt(source: unknown, path: MetricPath): Record<string, unknown> | undefined {
  let node: unknown = source;
  for (const key of path) {
    if (node === null || typeof node !== "object") return undefined;
    node = (node as Record<string | number, unknown>)[key];
  }
  return node !== null && typeof node === "object" ? (node as Record<string, unknown>) : undefined;
}

export function formatMetric(value: number | undefined, digits = 1): string {
  if (value === undefined || Number.isNaN(value)) return "—";
  return `${(value * 100).toFixed(digits)}%`;
}

export function formatNumber(value: number | undefined, digits = 3): string {
  if (value === undefined || Number.isNaN(value)) return "—";
  return value.toFixed(digits);
}

export function deltaBadge(ci95: [number, number] | undefined) {
  if (!ci95) {
    return { ok: false, label: "缺少配对 CI", detail: "先跑 baseline + benchmark + compare" };
  }
  const [low, high] = ci95;
  return low > 0
    ? { ok: true, label: "CI 排除 0", detail: `CI95 [${low.toFixed(4)}, ${high.toFixed(4)}]` }
    : {
        ok: false,
        label: "CI 含 0",
        detail: `CI95 下限 ${low.toFixed(4)} <= 0，增益不显著 —— 更多更好的数据排在收益排序第 1 位，不是加量也不是调超参`,
      };
}

const SAFE = /^[A-Za-z0-9_@%+=:,./-]+$/;

export function renderArgv(argv: string[]): string {
  return argv
    .map((part) => (SAFE.test(part) ? part : `'${part.replace(/'/g, `'\\''`)}'`))
    .join(" ");
}

export function formatDuration(seconds: number | undefined): string {
  if (seconds === undefined || Number.isNaN(seconds)) return "—";
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  const minutes = Math.floor(seconds / 60);
  return `${minutes}m ${(seconds - minutes * 60).toFixed(0)}s`;
}

/** 训练剩余时间估计。`sec` 是 kev.train 打的 s/rec。 */
export function estimateRemaining(step: number, total: number, secPerRec: number): string {
  if (!total || !step || !secPerRec) return "—";
  return formatDuration((total - step) * secPerRec);
}

export const STAGE_LABELS: Record<string, { en: string; zh: string }> = {
  data: { en: "Data", zh: "数据" },
  train: { en: "Train", zh: "训练" },
  benchmark: { en: "Score", zh: "打分" },
  compare: { en: "Compare", zh: "对比" },
  calibrate: { en: "Calibrate", zh: "校准" },
  image: { en: "Image", zh: "镜像" },
  deploy: { en: "Deploy", zh: "部署" },
};

export const STATUS_LABELS: Record<string, { en: string; zh: string }> = {
  pending: { en: "Pending", zh: "待启动" },
  queued: { en: "Queued", zh: "排队中" },
  running: { en: "Running", zh: "运行中" },
  succeeded: { en: "Succeeded", zh: "成功" },
  failed: { en: "Failed", zh: "失败" },
  canceled: { en: "Canceled", zh: "已取消" },
  interrupted: { en: "Interrupted", zh: "被中断" },
};