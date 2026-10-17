"use client";

import { useCallback, useState } from "react";
import Link from "next/link";
import { useLang } from "@/lib/i18n";
import { api } from "@/lib/console";
import { usePoll } from "@/components/console/usePoll";
import { EmptyState, FilterChip, Kpi, PageHead, Panel, StatusBadge } from "@/components/studio/primitives";
import { useProjects } from "@/components/studio/ProjectSwitcher";
import { useSelectedProject } from "@/lib/project-context";
import { cn } from "cn";

const TABS = ["resources", "alerts", "events", "audit"] as const;
type Tab = (typeof TABS)[number];

export default function StudioMonitoringPage() {
  const { t } = useLang();
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
      )}

      {(tab === "alerts" || tab === "audit") && (
        <EmptyState title={t("studio.monitoring.empty")} />
      )}
    </div>
  );
}
