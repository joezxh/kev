"use client";

import { cn } from "cn";

// Matches StatusBadge in primitives.tsx so the bar never disagrees with the pill.
const STATUS_COLOR: Record<string, string> = {
  succeeded: "#22c55e",
  running: "#3b82f6",
  pending: "#8b8b8b",
  queued: "#8b8b8b",
  failed: "#ef4444",
  canceled: "#5c5c5c",
  interrupted: "#5c5c5c",
};

export function JobProgressBar({
  status,
  progress,
  label,
}: {
  status:
    | "running"
    | "pending"
    | "succeeded"
    | "failed"
    | "canceled"
    | "interrupted";
  progress?: number;
  label?: string;
}) {
  const color = STATUS_COLOR[status] ?? STATUS_COLOR.pending;
  const indeterminate = status === "running" && progress === undefined;
  const pct =
    progress === undefined
      ? 100
      : Math.max(0, Math.min(1, progress)) * 100;

  return (
    <div className="w-full">
      {(label || progress !== undefined) && (
        <div className="mb-1 flex items-center justify-between text-[11px] text-muted-foreground">
          {label && <span>{label}</span>}
          {progress !== undefined && (
            <span className="font-mono">{Math.round(pct)}%</span>
          )}
        </div>
      )}
      <div className="h-1 w-full overflow-hidden rounded-full bg-[#1c1c1c]">
        {indeterminate ? (
          <div
            className="h-full w-1/3 animate-pulse opacity-60"
            style={{ background: color }}
          />
        ) : (
          <div
            className={cn(
              "h-full transition-all",
              status === "running" && progress !== undefined && "animate-pulse",
            )}
            style={{ background: color, width: `${pct}%` }}
          />
        )}
      </div>
    </div>
  );
}