"use client";

import { useCallback } from "react";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api } from "@/lib/console";
import { useLang } from "@/lib/i18n";
import { usePoll } from "@/components/console/usePoll";
import { Kpi, PageHead, Panel, Sparkline } from "@/components/studio/primitives";

export default function StudioUsagePage() {
  const { t } = useLang();
  const loadSummary = useCallback(() => api.usageSummary(), []);
  const loadDistill = useCallback(() => api.distillUsageTotals(), []);
  const summary = usePoll(loadSummary, []);
  const distill = usePoll(loadDistill, []);

  const totalCalls = summary.value.reduce((a, r) => a + r.calls, 0);
  const totalTokens = summary.value.reduce((a, r) => a + r.input_tokens + r.output_tokens, 0);
  const totalDistill = distill.value.reduce((a, r) => a + r.tokens, 0);
  const distillSeries = distill.value.map((d) => d.tokens);

  return (
    <div className="space-y-6">
      <PageHead title={t("studio.usage.title")} subtitle={t("studio.usage.subtitle")} />

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
