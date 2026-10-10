"use client";

import { useCallback, useState } from "react";
import Link from "next/link";
import { useLang } from "@/lib/i18n";
import { api, type Job } from "@/lib/console";
import { usePoll } from "@/components/console/usePoll";
import { EmptyState, FilterChip, Kpi, SearchInput, StatusBadge, Toolbar } from "./primitives";

function durationOf(job: Job): string {
  if (!job.started_at) return "—";
  const end = job.finished_at ? new Date(job.finished_at) : new Date();
  const secs = Math.max(0, (end.getTime() - new Date(job.started_at).getTime()) / 1000);
  if (secs < 60) return `${secs.toFixed(0)}s`;
  const m = Math.floor(secs / 60);
  return `${m}m ${(secs - m * 60).toFixed(0)}s`;
}

const STATUS_FILTERS = ["all", "running", "succeeded", "failed", "pending", "canceled"];

export function JobBoard({
  stage,
  kinds,
  hrefFor,
}: {
  stage?: string;
  kinds?: string[];
  hrefFor: (id: string) => string;
}) {
  const { t, lang } = useLang();
  const load = useCallback(() => api.jobs(stage ? { stage } : undefined), [stage]);
  const { value: jobs, error } = usePoll<Job[]>(load, []);

  const [q, setQ] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");

  const filtered = jobs.filter((job) => {
    if (kinds && !kinds.includes(job.kind)) return false;
    if (statusFilter !== "all" && job.status !== statusFilter) return false;
    if (q) {
      const hay = `${job.id} ${job.kind} ${job.scenario} ${job.title}`.toLowerCase();
      if (!hay.includes(q.toLowerCase())) return false;
    }
    return true;
  });

  const count = (s: string) => jobs.filter((j) => j.status === s).length;

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Kpi label={t("studio.board.kpi.total")} value={jobs.length} />
        <Kpi
          label={t("studio.board.kpi.running")}
          value={<span className="text-[#3b82f6]">{count("running")}</span>}
        />
        <Kpi
          label={t("studio.board.kpi.succeeded")}
          value={<span className="text-[#22c55e]">{count("succeeded")}</span>}
        />
        <Kpi
          label={t("studio.board.kpi.failed")}
          value={<span className="text-[#ef4444]">{count("failed")}</span>}
        />
      </div>

      <Toolbar>
        <SearchInput value={q} onChange={setQ} placeholder={t("studio.board.search")} />
        {STATUS_FILTERS.map((s) => (
          <FilterChip key={s} active={statusFilter === s} onClick={() => setStatusFilter(s)}>
            {s === "all" ? t("studio.board.all") : s}
          </FilterChip>
        ))}
      </Toolbar>

      {error && <p className="text-xs text-[#ef4444]">{error}</p>}

      {filtered.length === 0 ? (
        <EmptyState title={t("studio.board.empty")} />
      ) : (
        <div className="overflow-hidden rounded-md border border-border">
          <table className="w-full border-collapse text-[13px]">
            <thead>
              <tr className="border-b border-border text-left text-[11px] uppercase tracking-wide text-muted-foreground">
                <th className="px-3 py-2">{t("studio.board.col.status")}</th>
                <th className="px-3 py-2">{t("studio.board.col.id")}</th>
                <th className="px-3 py-2">{t("studio.board.col.kind")}</th>
                <th className="px-3 py-2">{t("studio.board.col.scenario")}</th>
                <th className="px-3 py-2">{t("studio.board.col.run")}</th>
                <th className="px-3 py-2">{t("studio.board.col.created")}</th>
                <th className="px-3 py-2 text-right">⏱</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((job) => (
                <tr key={job.id} className="border-b border-border/60 transition-colors hover:bg-[#161616]">
                  <td className="px-3 py-2">
                    <Link href={hrefFor(job.id)}>
                      <StatusBadge status={job.status} />
                    </Link>
                  </td>
                  <td className="px-3 py-2 font-mono text-xs">{job.id}</td>
                  <td className="px-3 py-2 font-mono text-xs text-muted-foreground">{job.kind}</td>
                  <td className="px-3 py-2">{job.scenario}</td>
                  <td className="px-3 py-2 font-mono text-xs">{job.title}</td>
                  <td className="px-3 py-2 text-xs text-muted-foreground">{job.created_at.slice(0, 19)}</td>
                  <td className="px-3 py-2 text-right text-xs text-muted-foreground">{durationOf(job)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
