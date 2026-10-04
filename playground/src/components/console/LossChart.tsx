"use client";

import { useId } from "react";
import { formatNumber } from "./format";
import type { Metric } from "@/lib/console";

const SERIES = [
  { key: "loss", color: "var(--color-chart-1)" },
  { key: "kl", color: "var(--color-chart-2)" },
  { key: "anchor", color: "var(--color-chart-3)" },
] as const;

const W = 640, H = 200;
const PAD = { top: 12, right: 12, bottom: 24, left: 46 };

/**
 * 手写 SVG，不用图表库：仓库无图表库依赖，answer-card.tsx 已有手写条形先例，
 * 而这三个序列的数据形态就是几十个点。色板取自 globals.css 已定义却一直没用过的
 * --color-chart-1..5。
 *
 * 实时指标的上限就是日志 tail（kev.train 没有 checkpoint 级指标），
 * 所以溢出时如实显示「仅显示最近 N 点」，不假装有更多。
 */
export function LossChart({ points, dropped = 0 }: { points: Metric[]; dropped?: number }) {
  const gradientId = useId();

  if (points.length < 2) {
    return (
      <div className="flex h-40 items-center justify-center rounded-md border border-dashed border-border text-sm text-muted-foreground">
        {points.length === 0
          ? "等待第一条进度日志（kev.train 每 10 个优化步打一行）"
          : "还需要更多数据点才能画曲线"}
      </div>
    );
  }

  const innerW = W - PAD.left - PAD.right;
  const innerH = H - PAD.top - PAD.bottom;
  const maxValue = Math.max(...points.flatMap((p) => SERIES.map((s) => p[s.key])), 1e-6);
  const last = points[points.length - 1];
  const x = (index: number) => PAD.left + (index / (points.length - 1)) * innerW;
  const y = (value: number) => PAD.top + innerH - (value / maxValue) * innerH;
  const line = (pick: (point: Metric) => number) =>
    points.map((point, index) => `${index === 0 ? "M" : "L"}${x(index)},${y(pick(point))}`).join(" ");

  return (
    <figure className="space-y-2">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img"
           aria-label={`loss ${formatNumber(last.loss)}`}>
        <defs>
          <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--color-chart-1)" stopOpacity="0.25" />
            <stop offset="100%" stopColor="var(--color-chart-1)" stopOpacity="0" />
          </linearGradient>
        </defs>
        {[0, 0.5, 1].map((fraction) => (
          <g key={fraction}>
            <line x1={PAD.left} x2={W - PAD.right} y1={y(maxValue * fraction)} y2={y(maxValue * fraction)}
                  stroke="var(--color-border)" strokeDasharray="3 3" />
            <text x={PAD.left - 6} y={y(maxValue * fraction) + 4} textAnchor="end" fontSize="10"
                  fill="var(--color-muted-foreground)">{formatNumber(maxValue * fraction, 2)}</text>
          </g>
        ))}
        <path
          d={`${line((p) => p.loss)} L${x(points.length - 1)},${PAD.top + innerH} L${x(0)},${PAD.top + innerH} Z`}
          fill={`url(#${gradientId})`}
        />
        {SERIES.map((series) => (
          <path key={series.key} d={line((p) => p[series.key])} fill="none"
                stroke={series.color} strokeWidth={series.key === "loss" ? 1.8 : 1.2}
                strokeLinejoin="round" />
        ))}
        <text x={PAD.left} y={H - 8} fontSize="10" fill="var(--color-muted-foreground)">
          ep{last.ep} step {last.step}/{last.total}
        </text>
        <text x={W - PAD.right} y={H - 8} textAnchor="end" fontSize="10"
              fill="var(--color-muted-foreground)">{formatNumber(last.sec)}s/rec</text>
      </svg>
      <figcaption className="flex flex-wrap items-center gap-4 text-xs text-muted-foreground">
        {SERIES.map((series) => (
          <span key={series.key} className="inline-flex items-center gap-1.5">
            <span className="h-0.5 w-4 rounded" style={{ background: series.color }} />
            {series.key} {formatNumber(last[series.key])}
          </span>
        ))}
        {dropped > 0 && (
          <span>仅显示最近 {points.length} 点（已丢弃 {dropped} 点）</span>
        )}
      </figcaption>
    </figure>
  );
}