"use client";

import { useCallback, useMemo, useState } from "react";
import Link from "next/link";
import { useLang } from "@/lib/i18n";
import { api } from "@/lib/console";
import { usePoll } from "@/components/console/usePoll";
import { EmptyState, FilterChip, Kpi, PageHead, Panel, StatusBadge } from "@/components/studio/primitives";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { useProjects } from "@/components/studio/ProjectSwitcher";
import { useSelectedProject } from "@/lib/project-context";
import { cn } from "cn";

const TABS = ["resources", "alerts", "events", "audit"] as const;
type Tab = (typeof TABS)[number];

export default function StudioMonitoringPage() {
  const { t, lang } = useLang();
  const zh = lang === "zh";
  const [tab, setTab] = useState<Tab>("resources");
  const load = useCallback(() => api.jobs(), []);
  const { value: jobs } = usePoll(load, []);
  // 项目归属（D14）：默认只看当前项目，可切回全量；未选项目时列表天然全量。
  const [projectId] = useSelectedProject();
  const { projects } = useProjects();
  const [scopeSel, setScopeSel] = useState<"current" | "all" | null>(null);
  const scope = scopeSel ?? (projectId ? "current" : "all");
  const projectName = (id: string) => projects.find((p) => p.id === id)?.name ?? id.slice(0, 6);
  const scoped =
    scope === "current" && projectId ? jobs.filter((j) => j.project_id === projectId) : jobs;
  const count = (s: string) => scoped.filter((j) => j.status === s).length;

  // 跨项目事件统计（req 5）：以 jobs 建模事件流，按 project_id 分组计数（含 legacy 行），纯客户端聚合。
  const stats = useMemo(() => {
    const map = new Map<string, { total: number; running: number; failed: number }>();
    for (const j of jobs) {
      const key = j.project_id || "";
      const row = map.get(key) ?? { total: 0, running: 0, failed: 0 };
      row.total += 1;
      if (j.status === "running") row.running += 1;
      if (j.status === "failed") row.failed += 1;
      map.set(key, row);
    }
    return [...map.entries()].map(([pid, v]) => ({ pid, ...v })).sort((a, b) => b.total - a.total);
  }, [jobs]);

  return (
    <div className="space-y-6">
      <PageHead title={t("studio.monitoring.title")} subtitle={t("studio.monitoring.subtitle")} />

      {projectId && (
        <div className="flex items-center gap-1">
          <FilterChip active={scope === "current"} onClick={() => setScopeSel("current")}>
            {t("studio.board.scopeCurrent")}
          </FilterChip>
          <FilterChip active={scope === "all"} onClick={() => setScopeSel("all")}>
            {t("studio.board.scopeAll")}
          </FilterChip>
        </div>
      )}

      <div className="flex gap-1 border-b border-border">
        {TABS.map((name) => (
          <button
            key={name}
            type="button"
            onClick={() => setTab(name)}
            className={cn(
              "border-b-2 px-3 py-2 text-[13px] transition-colors",
              tab === name ? "border-primary text-foreground" : "border-transparent text-muted-foreground hover:text-foreground",
            )}
          >
            {t(`studio.monitoring.tab.${name}`)}
          </button>
        ))}
      </div>

      {tab === "resources" && (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <Kpi label={t("studio.board.kpi.total")} value={scoped.length} />
            <Kpi label={t("studio.board.kpi.running")} value={<span className="text-[#3b82f6]">{count("running")}</span>} />
            <Kpi label={t("studio.board.kpi.succeeded")} value={<span className="text-[#22c55e]">{count("succeeded")}</span>} />
            <Kpi label={t("studio.board.kpi.failed")} value={<span className="text-[#ef4444]">{count("failed")}</span>} />
          </div>
          <Panel title="orchestrator" desc="jobs">
            <p className="text-xs text-muted-foreground">{t("studio.monitoring.empty")}</p>
          </Panel>
        </div>
      )}

      {tab === "events" && (
        <div className="space-y-4">
          <Panel
            title={zh ? "跨项目事件统计" : "Cross-project event stats"}
            desc={zh ? "以作业为事件流，按项目分组（含遗留）" : "jobs as the event stream, grouped by project (legacy included)"}
          >
            {stats.length === 0 ? (
              <EmptyState title={t("studio.monitoring.empty")} />
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>{t("studio.board.col.project")}</TableHead>
                    <TableHead className="text-right">{zh ? "事件数" : "events"}</TableHead>
                    <TableHead className="text-right">{t("studio.board.kpi.running")}</TableHead>
                    <TableHead className="text-right">{t("studio.board.kpi.failed")}</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {stats.map((s) => (
                    <TableRow key={s.pid || "__legacy__"}>
                      <TableCell className="text-xs">
                        {s.pid ? projectName(s.pid) : <span className="text-muted-foreground/60">{t("studio.board.legacy")}</span>}
                      </TableCell>
                      <TableCell className="text-right font-mono text-xs">{s.total}</TableCell>
                      <TableCell className="text-right font-mono text-xs text-[#3b82f6]">{s.running}</TableCell>
                      <TableCell className="text-right font-mono text-xs text-[#ef4444]">{s.failed}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </Panel>

          <Panel title={t("studio.monitoring.tab.events")}>
            {scoped.length === 0 ? (
              <EmptyState title={t("studio.monitoring.empty")} />
            ) : (
              <div className="divide-y divide-border/60">
                {scoped.slice(0, 12).map((job) => (
                  <Link key={job.id} href={`/studio/jobs/${job.id}`} className="flex items-center gap-3 py-2 text-sm transition-colors hover:bg-[#161616]">
                    <span className="font-mono text-xs text-muted-foreground">{job.created_at.slice(0, 19)}</span>
                    <StatusBadge status={job.status} />
                    <span className="text-xs">{job.kind}</span>
                    <span className="text-xs text-muted-foreground">
                      {job.project_id ? projectName(job.project_id) : t("studio.board.legacy")}
                    </span>
                    <span className="ml-auto text-xs text-muted-foreground">{job.scenario}</span>
                  </Link>
                ))}
              </div>
            )}
          </Panel>
        </div>
      )}

      {(tab === "alerts" || tab === "audit") && (
        <EmptyState title={t("studio.monitoring.empty")} />
      )}
    </div>
  );
}
