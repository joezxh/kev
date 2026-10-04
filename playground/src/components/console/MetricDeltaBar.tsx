"use client";

import { useLang } from "@/lib/i18n";
import { formatMetric } from "./format";

/**
 * baseline vs 微调 的指标差（手写 SVG，不引图表库 —— 见 LossChart 的说明）。
 *
 * 方向必须逐个指标判断：ECE / Brier / NLL / AURC / confident_error_rate 越低越好，
 * acc 与 coverage_* 越高越好。弄反了会把退步画成进步 —— 这是医疗验收里最不该犯的错。
 */
const LOWER_IS_BETTER = new Set([
  "ece", "brier", "nll", "aurc", "confident_error_rate", "error_rate_at_0_9",
]);

export type MetricPair = { name: string; reference?: number; candidate?: number };

const W = 640;
const LABEL_W = 168;
const VALUE_W = 92;
const ROW_H = 28;

export function MetricDeltaBar({ pairs }: { pairs: MetricPair[] }) {
  const { lang } = useLang();
  const usable = pairs.filter(
    (pair) => pair.reference !== undefined && pair.candidate !== undefined);

  if (usable.length === 0) {
    return (
      <div className="flex h-24 items-center justify-center rounded-md border border-dashed border-border text-sm text-muted-foreground">
        {lang === "zh" ? "还没有 compare 产物（需要 baseline + benchmark + compare）" : "No comparison yet (needs baseline + benchmark + compare)"}
      </div>
    );
  }

  const deltas = usable.map((pair) => ({
    ...pair,
    delta: (pair.candidate as number) - (pair.reference as number),
    better: LOWER_IS_BETTER.has(pair.name)
      ? (pair.candidate as number) < (pair.reference as number)
      : (pair.candidate as number) > (pair.reference as number),
  }));
  const scale = Math.max(...deltas.map((d) => Math.abs(d.delta)), 0.01);
  const plotW = W - LABEL_W - VALUE_W;
  const zero = LABEL_W + plotW / 2;
  const height = deltas.length * ROW_H + 28;

  return (
    <figure className="space-y-2">
      <svg viewBox={`0 0 ${W} ${height}`} className="w-full" role="img"
           aria-label={lang === "zh" ? "指标差" : "metric deltas"}>
        {/* 零线：左边是退步，右边是进步 */}
        <line x1={zero} x2={zero} y1={8} y2={height - 20}
              stroke="var(--color-border)" strokeWidth="1" />
        <text x={zero} y={height - 6} fontSize="10" textAnchor="middle"
              fill="var(--color-muted-foreground)">0</text>
        {deltas.map((row, index) => {
          const y = 10 + index * ROW_H;
          const width = (Math.abs(row.delta) / scale) * (plotW / 2 - 4);
          const x = row.delta >= 0 ? zero : zero - width;
          return (
            <g key={row.name}>
              <text x={LABEL_W - 8} y={y + 14} fontSize="11" textAnchor="end"
                    fill="var(--color-foreground)">{row.name}</text>
              <rect x={x} y={y + 4} width={Math.max(width, 1)} height={14} rx="2"
                    fill={row.better ? "var(--color-chart-2)" : "var(--color-chart-5)"}
                    opacity="0.85" />
              <text x={W - 4} y={y + 14} fontSize="10" textAnchor="end"
                    fill={row.better ? "var(--color-chart-2)" : "var(--color-chart-5)"}>
                {row.delta >= 0 ? "+" : ""}{formatMetric(row.delta, 2)}
              </text>
            </g>
          );
        })}
      </svg>
      <figcaption className="text-xs text-muted-foreground">
        {lang === "zh"
          ? "绿=改善，红=退步。注意 acc 提高而 confident_error_rate 也提高，是过度自信不是进步。"
          : "Green=improved, red=regressed. Accuracy up while confident_error_rate also up is overconfidence, not progress."}
      </figcaption>
    </figure>
  );
}
