"use client";
import { formatNumber } from "./format";
import type { UsageDay } from "@/lib/console";

const W = 640, H = 200, PAD = { top: 12, right: 12, bottom: 24, left: 46 };

export function UsageChart({ days }: { days: UsageDay[] }) {
  if (days.length < 2) return <p className="text-xs text-muted-foreground">还需要更多数据点</p>;
  const innerW = W - PAD.left - PAD.right, innerH = H - PAD.top - PAD.bottom;
  const maxTok = Math.max(...days.map((d) => d.input_tokens + d.output_tokens), 1);
  const x = (i: number) => PAD.left + (i / (days.length - 1)) * innerW;
  const y = (v: number) => PAD.top + innerH - (v / maxTok) * innerH;
  const line = (pick: (d: UsageDay) => number) =>
    days.map((d, i) => `${i === 0 ? "M" : "L"}${x(i)},${y(pick(d))}`).join(" ");
  const last = days[days.length - 1];
  return (
    <figure className="space-y-2">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label="token usage">
        {[0, 0.5, 1].map((f) => (
          <g key={f}>
            <line x1={PAD.left} x2={W - PAD.right} y1={y(maxTok * f)} y2={y(maxTok * f)} stroke="var(--color-border)" strokeDasharray="3 3" />
            <text x={PAD.left - 6} y={y(maxTok * f) + 4} textAnchor="end" fontSize="10" fill="var(--color-muted-foreground)">{formatNumber(maxTok * f, 0)}</text>
          </g>
        ))}
        <path d={line((d) => d.input_tokens + d.output_tokens)} fill="none" stroke="var(--color-chart-1)" strokeWidth={1.6} strokeLinejoin="round" />
      </svg>
      <figcaption className="text-xs text-muted-foreground">
        {last.date} · {formatNumber(last.input_tokens + last.output_tokens, 0)} tok
      </figcaption>
    </figure>
  );
}
