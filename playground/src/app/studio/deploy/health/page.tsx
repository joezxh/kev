"use client";

import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useLang } from "@/lib/i18n";
import { StudioTabs } from "@/components/studio/StudioTabs";
import { PageHead, Panel, StatusBadge } from "@/components/studio/primitives";

const DEPLOY_TABS = [
  { href: "/studio/deploy", labelKey: "studio.tab.run" },
  { href: "/studio/deploy/canary", labelKey: "studio.tab.canary" },
  { href: "/studio/deploy/health", labelKey: "studio.tab.health" },
  { href: "/studio/deploy/metrics", labelKey: "studio.tab.metrics" },
];

type Health = "succeeded" | "running" | "failed";
const ENDPOINTS = [
  { path: "/v1/decide", status: "succeeded" as Health, p50: 38, p95: 71, uptime: 99.98, last: "2s ago" },
  { path: "/v1/score", status: "succeeded" as Health, p50: 41, p95: 88, uptime: 99.95, last: "1s ago" },
  { path: "/healthz", status: "succeeded" as Health, p50: 4, p95: 9, uptime: 100, last: "0s ago" },
  { path: "/v1/explain", status: "running" as Health, p50: 120, p95: 340, uptime: 98.2, last: "5s ago" },
  { path: "/v1/batch", status: "failed" as Health, p50: 0, p95: 0, uptime: 91.4, last: "41s ago" },
];

export default function DeployHealthPage() {
  const { t, lang } = useLang();
  return (
    <div className="space-y-6">
      <StudioTabs tabs={DEPLOY_TABS} />
      <PageHead
        title={t("studio.tab.health")}
        subtitle={lang === "zh" ? "探测端点健康、延迟与最近探测结果。" : "Probe endpoint health, latency and last probe result."}
      />

      <Panel desc={lang === "zh" ? "探测端点" : "Probed endpoints"}>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>endpoint</TableHead>
              <TableHead>status</TableHead>
              <TableHead className="text-right">p50 (ms)</TableHead>
              <TableHead className="text-right">p95 (ms)</TableHead>
              <TableHead className="text-right">uptime</TableHead>
              <TableHead className="text-right">last probe</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {ENDPOINTS.map((e) => (
              <TableRow key={e.path}>
                <TableCell className="font-mono text-xs">{e.path}</TableCell>
                <TableCell>
                  <StatusBadge
                    status={e.status}
                    label={lang === "zh" ? (e.status === "succeeded" ? "健康" : e.status === "running" ? "降级" : "故障") : e.status}
                  />
                </TableCell>
                <TableCell className="text-right font-mono text-xs">{e.p50 || "—"}</TableCell>
                <TableCell className="text-right font-mono text-xs">{e.p95 || "—"}</TableCell>
                <TableCell className="text-right font-mono text-xs">{e.uptime}%</TableCell>
                <TableCell className="text-right font-mono text-xs text-muted-foreground">{e.last}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Panel>
    </div>
  );
}
