"use client";

import { useId } from "react";
import { useLang } from "@/lib/i18n";
import { formatMetric } from "./format";

/**
 * 高置信区间的可靠性（report.clean.top_bins）。
 *
 * top_bins 的键是置信度阈值（0.9 / 0.95 / 0.99），值是 {n, errors, error_rate}。
 * 画法：柱高 = 该区间内的实测准确率，横线 = 阈值本身。
 * 柱顶低于横线 = 模型在这个置信度上**过度自信** —— 0.8B 的重点监控项。
 *
 * 只有三个区间，所以画柱不画曲线；这不是完整的可靠性图（那需要分箱直方图），
 * 但它是产物里真实存在的字段，不假装有更多。
 */
export type TopBin = { n: number; errors: number; error_rate: number | null };

const W = 640, H = 200;
const PAD = { top: 14, right: 14, bottom: 30, left: 48 };
const THRESHOLDS = ["0.9", "0.95", "0.99"];

export function ReliabilityDiagram({ bins, ece }: { bins?: Record<string, TopBin>; ece?: number }) {
  const { lang } = useLang();
  const gradientId = useId();
  const present = THRESHOLDS.filter((t) => bins?.[t]?.error_rate !== null && bins?.[t] !== undefined);

  if (present.length === 0) {
    return (
      <div className="flex h-40 items-center justify-center rounded-md border border-dashed border-border text-sm text-muted-foreground">
        {lang === "zh" ? "还没有 top_bins（跑一次 benchmark 或 compare）" : "No top_bins yet (run a benchmark or compare)"}
      </div>
    );
  }

  const innerW = W - PAD.left - PAD.right;
  const innerH = H - PAD.top - PAD.bottom;
  const slot = innerW / present.length;
  const barW = Math.min(slot * 0.5, 72);
  const y = (value: number) => PAD.top + innerH - value * innerH;

  return (
    <figure className="space-y-2">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img"
           aria-label={lang === "zh" ? "高置信区间可靠性" : "top-confidence reliability"}>
        <defs>
          <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--color-chart-1)" stopOpacity="0.9" />
            <stop offset="100%" stopColor="var(--color-chart-1)" stopOpacity="0.45" />
          </linearGradient>
        </defs>
        {[0, 0.5, 1].map((fraction) => (
          <g key={fraction}>
            <line x1={PAD.left} x2={W - PAD.right} y1={y(fraction)} y2={y(fraction)}
                  stroke="var(--color-border)" strokeDasharray="3 3" />
            <text x={PAD.left - 6} y={y(fraction) + 4} textAnchor="end" fontSize="10"
                  fill="var(--color-muted-foreground)">{formatMetric(fraction, 0)}</text>
          </g>
        ))}
        {present.map((threshold, index) => {
          const bin = bins![threshold];
          const accuracy = 1 - (bin.error_rate ?? 0);
          const center = PAD.left + slot * (index + 0.5);
          const top = y(accuracy);
          const target = y(Number(threshold));
          const short = accuracy < Number(threshold);   // 柱顶低于横线 = 过度自信
          return (
            <g key={threshold}>
              <rect x={center - barW / 2} y={top} width={barW} height={PAD.top + innerH - top}
                    rx="3" fill={`url(#${gradientId})`} />
              {/* 阈值横线：柱顶应当顶到它 */}
              <line x1={center - barW / 2 - 6} x2={center + barW / 2 + 6} y1={target} y2={target}
                    stroke={short ? "var(--color-chart-5)" : "var(--color-chart-2)"} strokeWidth="2" />
              <text x={center} y={H - 16} fontSize="10" textAnchor="middle"
                    fill="var(--color-muted-foreground)">≥{threshold}</text>
              <text x={center} y={H - 4} fontSize="10" textAnchor="middle"
                    fill="var(--color-muted-foreground)">n={bin.n}</text>
            </g>
          );
        })}
      </svg>
      <figcaption className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
        <span>{lang === "zh" ? "柱=实测准确率，横线=置信度阈值" : "bar=observed accuracy, line=confidence threshold"}</span>
        <span className="text-destructive">
          {lang === "zh" ? "柱顶低于横线=过度自信" : "bar below the line=overconfident"}
        </span>
        {ece !== undefined && <span>ECE {formatMetric(ece, 2)}</span>}
      </figcaption>
    </figure>
  );
}
