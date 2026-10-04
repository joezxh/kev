"use client";

import { useId } from "react";
import { useLang } from "@/lib/i18n";
import { formatMetric } from "./format";

/**
 * 选择性覆盖 vs 错误率（report.clean.selective + coverage_at_*_error）。
 *
 * 读的是「在给定错误率上限下能自动接受多少决策」—— 医疗场景真正关心的量：
 * 不是准确率有多高，而是**敢不敢让模型自己说了算**。
 *
 * 数据来源两类，形状不同但都落在同一条曲线上：
 *   selective["0.5"|"0.8"]  -> {coverage, accuracy}          （固定覆盖率，看准确率）
 *   coverage_at_5pct_error  -> 在错误率 ≤5% 前提下的覆盖率    （固定错误率，看覆盖率）
 * 只有 4 个点，如实画折线，不做平滑插值。
 */
export type SelectiveBin = { coverage: number; accuracy: number; confidence_cutoff: number };

const W = 640, H = 200;
const PAD = { top: 14, right: 16, bottom: 30, left: 48 };

export function CoverageCurve({ selective, coverageAt5Pct, coverageAt1Pct }: {
  selective?: Record<string, SelectiveBin>;
  coverageAt5Pct?: number;
  coverageAt1Pct?: number;
}) {
  const { lang } = useLang();
  const clipId = useId();

  const points: { x: number; y: number; label: string }[] = [];
  for (const [fraction, bin] of Object.entries(selective ?? {})) {
    if (bin && Number.isFinite(bin.coverage) && Number.isFinite(bin.accuracy)) {
      points.push({ x: bin.coverage, y: 1 - bin.accuracy, label: `sel ${fraction}` });
    }
  }
  if (Number.isFinite(coverageAt5Pct)) {
    points.push({ x: coverageAt5Pct as number, y: 0.05, label: "err≤5%" });
  }
  if (Number.isFinite(coverageAt1Pct)) {
    points.push({ x: coverageAt1Pct as number, y: 0.01, label: "err≤1%" });
  }
  points.sort((a, b) => a.x - b.x);

  if (points.length < 2) {
    return (
      <div className="flex h-40 items-center justify-center rounded-md border border-dashed border-border text-sm text-muted-foreground">
        {lang === "zh" ? "还不足两个覆盖点（需要 selective 与 coverage_at_*_error）" : "Fewer than two coverage points yet (needs selective and coverage_at_*_error)"}
      </div>
    );
  }

  const innerW = W - PAD.left - PAD.right;
  const innerH = H - PAD.top - PAD.bottom;
  const maxY = Math.max(...points.map((p) => p.y), 0.05);
  const px = (value: number) => PAD.left + value * innerW;
  const py = (value: number) => PAD.top + innerH - (value / maxY) * innerH;

  return (
    <figure className="space-y-2">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img"
           aria-label={lang === "zh" ? "覆盖-错误率曲线" : "coverage vs error rate"}>
        <defs>
          <clipPath id={clipId}>
            <rect x={PAD.left} y={PAD.top} width={innerW} height={innerH} />
          </clipPath>
        </defs>
        {[0, 0.5, 1].map((fraction) => (
          <g key={fraction}>
            <line x1={PAD.left} x2={W - PAD.right} y1={py(maxY * fraction)} y2={py(maxY * fraction)}
                  stroke="var(--color-border)" strokeDasharray="3 3" />
            <text x={PAD.left - 6} y={py(maxY * fraction) + 4} textAnchor="end" fontSize="10"
                  fill="var(--color-muted-foreground)">{formatMetric(maxY * fraction, 0)}</text>
          </g>
        ))}
        <g clipPath={`url(#${clipId})`}>
          <path d={points.map((p, i) => `${i === 0 ? "M" : "L"}${px(p.x)},${py(p.y)}`).join(" ")}
                fill="none" stroke="var(--color-chart-3)" strokeWidth="1.8" strokeLinejoin="round" />
          {points.map((point) => (
            <g key={point.label}>
              <circle cx={px(point.x)} cy={py(point.y)} r="3.5" fill="var(--color-chart-3)" />
              <text x={px(point.x) + 6} y={py(point.y) - 4} fontSize="9"
                    fill="var(--color-muted-foreground)">{point.label}</text>
            </g>
          ))}
        </g>
        <text x={PAD.left} y={H - 6} fontSize="10" fill="var(--color-muted-foreground)">
          coverage 0
        </text>
        <text x={W - PAD.right} y={H - 6} textAnchor="end" fontSize="10"
              fill="var(--color-muted-foreground)">coverage 100%</text>
      </svg>
      <figcaption className="text-xs text-muted-foreground">
        {lang === "zh"
          ? "纵轴是错误率。曲线越靠右下越好：同样的错误率能自动接受更多决策。"
          : "Y axis is error rate. Lower-right is better: more decisions automated at the same error rate."}
      </figcaption>
    </figure>
  );
}
