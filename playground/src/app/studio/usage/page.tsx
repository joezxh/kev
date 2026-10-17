"use client";

import { useCallback, useEffect, useState } from "react";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api, type ProjectUsage } from "@/lib/console";
import { useLang } from "@/lib/i18n";
import { usePoll } from "@/components/console/usePoll";
import { useSelectedProject } from "@/lib/project-context";
import { Kpi, PageHead, Panel, Sparkline } from "@/components/studio/primitives";

type ProjectUsageRow = { id: string; name: string; slug: string; usage: ProjectUsage };

const num = (v: number, digits = 3) => (v == null ? "—" : v.toFixed(digits));

export default function StudioUsagePage() {
  const { t } = useLang();
  const loadSummary = useCallback(() => api.usageSummary(), []);
  const loadDistill = useCallback(() => api.distillUsageTotals(), []);
  const summary = usePoll(loadSummary, []);
  const distill = usePoll(loadDistill, []);

  const [projectId] = useSelectedProject();
  const [usageRows, setUsageRows] = useState<ProjectUsageRow[] | null>(null);
  const [usageError, setUsageError] = useState<string | null>(null);
  // 跨项目用量：列表接口只返回原始项目行，逐个项目读 summary 的真实三列（PR F §4.6-2）。
  useEffect(() => {
    let alive = true;
    api.projects()
      .then((ps) => Promise.all(ps.map((p) =>
        api.project(p.id).then((s) => ({ id: p.id, name: p.name, slug: p.slug, usage: s.usage })))))
      .then((rows) => {
        if (!alive) return;
        setUsageRows(rows);
        setUsageError(null);
      })
      .catch((e) => {
        if (alive) setUsageError(String(e?.message ?? e));
      });
    return () => {
      alive = false;
    };
  }, []);
  const current = usageRows?.find((r) => r.id === projectId) ?? null;

  const totalCalls = summary.value.reduce((a, r) => a + r.calls, 0);
  const totalTokens = summary.value.reduce((a, r) => a + r.input_tokens + r.output_tokens, 0);
  const totalDistill = distill.value.reduce((a, r) => a + r.tokens, 0);
  const distillSeries = distill.value.map((d) => d.tokens);

  return (
    <div className="space-y-6">
      <PageHead title={t("studio.usage.title")} subtitle={t("studio.usage.subtitle")} />

      <Panel title={t("studio.usage.projectSection")} desc={t("studio.usage.projectSectionDesc")}>
        {usageError ? (
          <p className="text-sm text-red-400">{usageError}</p>
        ) : usageRows === null ? (
          <p className="text-sm text-muted-foreground">…</p>
        ) : (
          <div className="space-y-4">
            {current ? (
              <div>
                <p className="mb-2 text-xs text-muted-foreground">
                  {t("studio.usage.currentProject")}: {current.name} ({current.slug})
                </p>
                <div className="grid grid-cols-3 gap-3">
                  <Kpi label={t("studio.usage.storageGb")} value={num(current.usage.storage_gb_used)} />
                  <Kpi label={t("studio.usage.trainHours")} value={num(current.usage.training_hours_used, 2)} />
                  <Kpi label={t("studio.usage.apiCalls")} value={current.usage.api_calls_used.toLocaleString()} />
                </div>
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">{t("studio.usage.noProjectSelected")}</p>
            )}
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{t("studio.usage.projectCol")}</TableHead>
                  <TableHead className="text-right">{t("studio.usage.storageGb")}</TableHead>
                  <TableHead className="text-right">{t("studio.usage.trainHours")}</TableHead>
                  <TableHead className="text-right">{t("studio.usage.apiCalls")}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {usageRows.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={4} className="text-sm text-muted-foreground">{t("studio.usage.empty")}</TableCell>
                  </TableRow>
                ) : usageRows.map((r) => (
                  <TableRow key={r.id} className={r.id === projectId ? "bg-muted/40" : undefined}>
                    <TableCell>{r.name} <span className="text-xs text-muted-foreground">({r.slug})</span></TableCell>
                    <TableCell className="text-right font-mono text-xs">{num(r.usage.storage_gb_used)}</TableCell>
                    <TableCell className="text-right font-mono text-xs">{num(r.usage.training_hours_used, 2)}</TableCell>
                    <TableCell className="text-right font-mono text-xs">{r.usage.api_calls_used.toLocaleString()}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </Panel>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Kpi label={t("studio.usage.calls")} value={totalCalls.toLocaleString()} />
        <Kpi label={t("studio.usage.tokens")} value={totalTokens.toLocaleString()} />
        <Kpi label={t("studio.usage.distill")} value={totalDistill.toLocaleString()} />
        <Kpi label={t("studio.usage.byKey")} value={<span className="text-base">{summary.value.length}</span>} />
      </div>

      <Panel title={t("studio.usage.byKey")}>
        {summary.value.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t("studio.usage.empty")}</p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t("studio.apikeys.name")}</TableHead>
                <TableHead className="text-right">{t("studio.usage.calls")}</TableHead>
                <TableHead className="text-right">{t("studio.usage.tokens")}</TableHead>
                <TableHead className="text-right">{t("studio.usage.latency")}</TableHead>
                <TableHead className="text-right">p99</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {summary.value.map((r) => (
                <TableRow key={r.id}>
                  <TableCell>{r.name}</TableCell>
                  <TableCell className="text-right font-mono text-xs">{r.calls.toLocaleString()}</TableCell>
                  <TableCell className="text-right font-mono text-xs">{(r.input_tokens + r.output_tokens).toLocaleString()}</TableCell>
                  <TableCell className="text-right font-mono text-xs">{r.avg_latency_ms ?? "—"}</TableCell>
                  <TableCell className="text-right font-mono text-xs">{r.p99_latency_ms}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </Panel>

      <Panel title={t("studio.usage.distill")} desc={t("studio.usage.total")}>
        {distill.value.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t("studio.usage.empty")}</p>
        ) : (
          <div className="space-y-3">
            <Sparkline data={distillSeries} color="#06b6d4" width={280} height={36} />
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{t("studio.usage.day")}</TableHead>
                  <TableHead className="text-right">{t("studio.usage.tokens")}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {distill.value.slice(-14).reverse().map((d) => (
                  <TableRow key={d.day}>
                    <TableCell className="font-mono text-xs">{d.day}</TableCell>
                    <TableCell className="text-right font-mono text-xs">{d.tokens.toLocaleString()}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </Panel>
    </div>
  );
}
