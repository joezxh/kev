"use client";

import { useCallback } from "react";
import Link from "next/link";
import { useLang } from "@/lib/i18n";
import { api } from "@/lib/console";
import { usePoll } from "@/components/console/usePoll";
import { Kpi, PageHead, Panel, StatusBadge } from "@/components/studio/primitives";

const SECTIONS = [
  { href: "/studio/domains", titleKey: "studio.overview.section.data", descKey: "studio.nav.domains" },
  { href: "/studio/train", titleKey: "studio.overview.section.lifecycle", descKey: "studio.nav.lifecycle" },
  { href: "/studio/apikeys", titleKey: "studio.overview.section.system", descKey: "studio.nav.system" },
  { href: "/studio/projects", titleKey: "studio.overview.section.admin", descKey: "studio.nav.admin" },
];

export default function StudioOverviewPage() {
  const { t, lang } = useLang();
  const load = useCallback(() => api.jobs(), []);
  const { value: jobs } = usePoll(load, []);

  const count = (s: string) => jobs.filter((j) => j.status === s).length;
  const recent = jobs.slice(0, 8);

  return (
    <div className="space-y-6">
      <PageHead title={t("studio.overview.title")} subtitle={t("studio.overview.subtitle")} />

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Kpi label={t("studio.board.kpi.total")} value={jobs.length} />
        <Kpi label={t("studio.board.kpi.running")} value={<span className="text-[#3b82f6]">{count("running")}</span>} />
        <Kpi label={t("studio.board.kpi.succeeded")} value={<span className="text-[#22c55e]">{count("succeeded")}</span>} />
        <Kpi label={t("studio.board.kpi.failed")} value={<span className="text-[#ef4444]">{count("failed")}</span>} />
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
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
                <span className="ml-auto font-mono text-xs text-muted-foreground">{job.kind}</span>
              </Link>
            ))}
          </div>
        )}
      </Panel>
    </div>
  );
}
