"use client";

import { ReactNode } from "react";
import { cn } from "cn";

/** 原型风格的状态徽标：近黑底 + 彩色点，running 带脉冲。 */
const STATUS_TONE: Record<string, { bg: string; fg: string; dot: string; pulse?: boolean }> = {
  succeeded: { bg: "#14532d", fg: "#22c55e", dot: "#22c55e" },
  running: { bg: "#1e3a8a", fg: "#3b82f6", dot: "#3b82f6", pulse: true },
  pending: { bg: "#1c1c1c", fg: "#8b8b8b", dot: "#5c5c5c" },
  queued: { bg: "#1c1c1c", fg: "#8b8b8b", dot: "#5c5c5c" },
  failed: { bg: "#7f1d1d", fg: "#ef4444", dot: "#ef4444" },
  canceled: { bg: "#1c1c1c", fg: "#5c5c5c", dot: "#5c5c5c" },
  interrupted: { bg: "#1c1c1c", fg: "#5c5c5c", dot: "#5c5c5c" },
};

export function StatusBadge({ status, label }: { status: string; label?: string }) {
  const tone = STATUS_TONE[status] ?? STATUS_TONE.pending;
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[11px] font-medium"
      style={{ background: tone.bg, color: tone.fg }}
    >
      <span
        className={cn("h-1.5 w-1.5 rounded-full", tone.pulse && "animate-pulse")}
        style={{ background: tone.dot }}
      />
      {label ?? status}
    </span>
  );
}

export function PageHead({
  title,
  subtitle,
  actions,
}: {
  title: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <div className="mb-6 flex items-start justify-between gap-4">
      <div>
        <h1 className="text-[22px] font-semibold tracking-tight">{title}</h1>
        {subtitle && <p className="mt-1 text-[13px] text-muted-foreground">{subtitle}</p>}
      </div>
      {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
    </div>
  );
}

export function Panel({
  title,
  desc,
  actions,
  children,
  className,
}: {
  title?: ReactNode;
  desc?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={cn("rounded-md border border-border bg-[#111111]", className)}>
      {(title || actions) && (
        <div className="flex items-center justify-between gap-3 border-b border-border px-4 py-3">
          <div>
            {title && <h3 className="text-[13px] font-semibold">{title}</h3>}
            {desc && <div className="text-xs text-muted-foreground">{desc}</div>}
          </div>
          {actions}
        </div>
      )}
      <div className="p-4">{children}</div>
    </section>
  );
}

export function Kpi({
  label,
  value,
  delta,
  deltaUp,
  children,
}: {
  label: string;
  value: ReactNode;
  delta?: string;
  deltaUp?: boolean;
  children?: ReactNode;
}) {
  return (
    <div className="rounded-md border border-border bg-[#111111] p-3.5">
      <div className="text-[11px] uppercase tracking-wide text-muted-foreground">{label}</div>
      <div className="mt-1.5 text-[26px] font-semibold leading-none tracking-tight">{value}</div>
      {delta && (
        <div className={cn("mt-1.5 text-[11px]", deltaUp ? "text-[#22c55e]" : "text-[#ef4444]")}>
          {delta}
        </div>
      )}
      {children && <div className="mt-2">{children}</div>}
    </div>
  );
}

export function Sparkline({
  data,
  color = "#3b82f6",
  width = 140,
  height = 28,
}: {
  data: number[];
  color?: string;
  width?: number;
  height?: number;
}) {
  if (data.length < 2) return <div style={{ height }} />;
  const min = Math.min(...data);
  const max = Math.max(...data);
  const span = max - min || 1;
  const points = data
    .map((v, i) => {
      const x = (i / (data.length - 1)) * width;
      const y = height - ((v - min) / span) * (height - 2) - 1;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
  return (
    <svg width={width} height={height} className="overflow-visible">
      <polyline points={points} fill="none" stroke={color} strokeWidth={1.5} strokeLinejoin="round" />
    </svg>
  );
}

export function EmptyState({
  title,
  hint,
  action,
}: {
  title: string;
  hint?: string;
  action?: ReactNode;
}) {
  return (
    <div className="rounded-md border border-dashed border-border p-8 text-center">
      <div className="text-sm text-muted-foreground">{title}</div>
      {hint && <div className="mt-1 text-xs text-muted-foreground/70">{hint}</div>}
      {action && <div className="mt-3 flex justify-center">{action}</div>}
    </div>
  );
}

export function Toolbar({ children }: { children: ReactNode }) {
  return <div className="mb-3 flex flex-wrap items-center gap-2">{children}</div>;
}

export function SearchInput({
  value,
  onChange,
  placeholder,
}: {
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
}) {
  return (
    <div className="relative min-w-[200px] flex-1">
      <span className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground">
        ⌕
      </span>
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="w-full rounded border border-border bg-[#111111] py-1.5 pl-8 pr-3 text-[13px] outline-none focus:border-primary"
      />
    </div>
  );
}

export function FilterChip({
  active,
  onClick,
  children,
}: {
  active?: boolean;
  onClick?: () => void;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "rounded border px-2.5 py-1.5 text-xs transition-colors",
        active
          ? "border-primary bg-[#1e3a8a] text-[#3b82f6]"
          : "border-border bg-[#111111] text-muted-foreground hover:text-foreground",
      )}
    >
      {children}
    </button>
  );
}

export function Drawer({
  open,
  onClose,
  title,
  subtitle,
  children,
  footer,
}: {
  open: boolean;
  onClose: () => void;
  title: ReactNode;
  subtitle?: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
}) {
  if (!open) return null;
  return (
    <>
      <div className="fixed inset-0 z-50 bg-black/50" onClick={onClose} />
      <div className="fixed right-0 top-0 z-[51] flex h-full w-[640px] max-w-[92vw] flex-col border-l border-border bg-[#111111]">
        <div className="flex items-center justify-between border-b border-border px-5 py-3.5">
          <div>
            <h2 className="text-[15px] font-semibold">{title}</h2>
            {subtitle && <div className="mt-0.5 text-xs text-muted-foreground">{subtitle}</div>}
          </div>
          <button
            type="button"
            onClick={onClose}
            className="text-muted-foreground transition-colors hover:text-foreground"
            aria-label="close"
          >
            ✕
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-5">{children}</div>
        {footer && (
          <div className="flex justify-end gap-2 border-t border-border px-5 py-3">{footer}</div>
        )}
      </div>
    </>
  );
}

/** 两列表单栅格（原型 .form-grid）。 */
export function FormGrid({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className={cn("grid grid-cols-1 gap-3 sm:grid-cols-2", className)}>{children}</div>
  );
}

export function Field({
  label,
  hint,
  children,
  full,
}: {
  label: string;
  hint?: string;
  children: ReactNode;
  full?: boolean;
}) {
  return (
    <div className={cn("flex flex-col gap-1", full && "sm:col-span-2")}>
      <label className="text-[11px] uppercase tracking-wide text-muted-foreground">{label}</label>
      {children}
      {hint && <div className="text-[11px] text-muted-foreground/70">{hint}</div>}
    </div>
  );
}
