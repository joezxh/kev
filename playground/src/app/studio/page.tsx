"use client";

import { useCallback, useState } from "react";
import Link from "next/link";
import { useLang } from "@/lib/i18n";
import { api } from "@/lib/console";
import { usePoll } from "@/components/console/usePoll";
import { FilterChip, Kpi, PageHead, Panel, StatusBadge } from "@/components/studio/primitives";
import { useProjects } from "@/components/studio/ProjectSwitcher";
import { useSelectedProject } from "@/lib/project-context";

// 项目中心的快捷入口：数据 / 训练评测 / 部署发布（对齐样稿三张生命周期卡）。
const SECTIONS = [
  { href: "/studio/datasets", titleKey: "studio.overview.card.data", descKey: "studio.overview.card.dataDesc" },
  { href: "/studio/train", titleKey: "studio.overview.card.lifecycle", descKey: "studio.overview.card.lifecycleDesc" },
  { href: "/studio/deploy", titleKey: "studio.overview.card.ship", descKey: "studio.overview.card.shipDesc" },
];

export default function StudioOverviewPage() {
  const { t } = useLang();
  const load = useCallback(() => api.jobs(), []);
  const { value: jobs } = usePoll(load, []);

  // 项目归属（D14）：选了项目默认只看本项目，可切「全部项目」；未选项目时列表天然全量、无开关。
  const [projectId] = useSelectedProject();
  const { projects } = useProjects();
  const [scopeSel, setScopeSel] = useState<"current" | "all" | null>(null);
  const scope = scopeSel ?? (projectId ? "current" : "all");
  const projectName = (id: string) => projects.find((p) => p.id === id)?.name ?? id.slice(0, 6);
  const scoped = scope === "current" && projectId ? jobs.filter((j) => j.project_id === projectId) : jobs;

  const count = (s: string) => scoped.filter((j) => j.status === s).length;
  const recent = scoped.slice(0, 8);

  return (
    <div className="space-y-6">
      <PageHead title={t("studio.overview.title")} subtitle={t("studio.overview.subtitle")} />

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

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Kpi label={t("studio.board.kpi.total")} value={scoped.length} />
        <Kpi label={t("studio.board.kpi.running")} value={<span className="text-[#3b82f6]">{count("running")}</span>} />
        <Kpi label={t("studio.board.kpi.succeeded")} value={<span className="text-[#22c55e]">{count("succeeded")}</span>} />
        <Kpi label={t("studio.board.kpi.failed")} value={<span className="text-[#ef4444]">{count("failed")}</span>} />
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        {SECTIONS.map((s) => (
          <Link key={s.href} href={s.href} className="rounded-md border border-border bg-[#111111] p-4 transition-colors hover:border-primary/60">
            <div className="text-sm font-medium">{t(s.titleKey)}</div>
            <div className="mt-1 text-xs text-muted-foreground">{t(s.descKey)}</div>
            <div className="mt-3 text-xs text-primary">{t("studio.overview.open")} →</div>
          </Link>
        ))}
      </div>

      <Panel title={t("studio.overview.recent")} desc={t("studio.overview.viewAll")}>
        {recent.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t("studio.board.empty")}</p>
        ) : (
          <div className="divide-y divide-border/60">
            {recent.map((job) => (
              <Link key={job.id} href={`/studio/jobs/${job.id}`} className="flex items-center gap-3 py-2 text-sm transition-colors hover:bg-[#161616]">
                <StatusBadge status={job.status} />
                <span className="font-mono text-xs text-muted-foreground">{job.id}</span>
                <span className="text-xs">{job.scenario}</span>
                <span className="text-xs text-muted-foreground">
                  {job.project_id ? projectName(job.project_id) : t("studio.board.legacy")}
                </span>
                <span className="ml-auto font-mono text-xs text-muted-foreground">{job.kind}</span>
              </Link>
            ))}
          </div>
        )}
      </Panel>
    </div>
  );
}
