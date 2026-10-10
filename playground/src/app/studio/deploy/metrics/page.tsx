"use client";

import { useLang } from "@/lib/i18n";
import { StudioTabs } from "@/components/studio/StudioTabs";
import { PageHead, Panel, Kpi, Sparkline } from "@/components/studio/primitives";

const DEPLOY_TABS = [
  { href: "/studio/deploy", labelKey: "studio.tab.run" },
  { href: "/studio/deploy/canary", labelKey: "studio.tab.canary" },
  { href: "/studio/deploy/health", labelKey: "studio.tab.health" },
  { href: "/studio/deploy/metrics", labelKey: "studio.tab.metrics" },
];

const qps = [182, 175, 190, 201, 188, 205, 212, 199, 210, 223, 218, 231];
const p95 = [61, 64, 59, 72, 68, 70, 66, 71, 69, 74, 73, 71];
const err = [0.012, 0.009, 0.014, 0.011, 0.008, 0.01, 0.012, 0.009, 0.011, 0.008, 0.01, 0.009];
const avail = [99.98, 99.97, 99.99, 99.98, 99.99, 99.98, 99.97, 99.99, 99.98, 99.99, 99.98, 99.99];

export default function DeployMetricsPage() {
  const { t, lang } = useLang();
  return (
    <div className="space-y-6">
      <StudioTabs tabs={DEPLOY_TABS} />
      <PageHead
        title={t("studio.tab.metrics")}
        subtitle={lang === "zh" ? "在线服务指标：QPS、延迟、错误率与可用性。" : "Online service metrics: QPS, latency, error rate and availability."}
      />

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Kpi label="QPS" value="231" delta="+13.5%" deltaUp>
          <Sparkline data={qps} color="#3b82f6" />
        </Kpi>
        <Kpi label="p95 latency" value="71 ms" delta="−3 ms" deltaUp>
          <Sparkline data={p95} color="#f59e0b" />
        </Kpi>
        <Kpi label="error rate" value="0.9%" delta="−0.2pt" deltaUp>
          <Sparkline data={err} color="#ef4444" />
        </Kpi>
        <Kpi label="availability" value="99.99%">
          <Sparkline data={avail} color="#22c55e" />
        </Kpi>
      </div>

      <Panel title={lang === "zh" ? "请求量（近 12 个采样点）" : "Request volume (last 12 samples)"}>
        <Sparkline data={qps} color="#3b82f6" width={720} height={120} />
      </Panel>
      <Panel title={lang === "zh" ? "尾延迟 p95" : "Tail latency p95"}>
        <Sparkline data={p95} color="#f59e0b" width={720} height={120} />
      </Panel>
    </div>
  );
}
